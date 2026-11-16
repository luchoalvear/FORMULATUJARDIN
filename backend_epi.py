"""
Servidor unico del Sistema de Formulacion - JUNJI: sirve el HTML estatico,
la API (auth + proyectos + documentos, SQLite) y hace de proxy a la API de
Claude (evita el bloqueo CORS del navegador contra api.anthropic.com).
Solo libreria estandar de Python — un solo proceso, listo para correr local
o desplegar en un host como Railway.

Uso local:
    py backend_epi.py
    Abre http://localhost:8790

Variables de entorno (para despliegue):
    PORT               Puerto a escuchar (Railway la define automáticamente).
    DATA_DIR           Carpeta donde viven la base de datos y los documentos subidos.
                       Debe apuntar a un volumen persistente en producción (si no,
                       se pierden los datos en cada redeploy). Por defecto, la misma
                       carpeta del script (sirve para uso local).
    ADMIN_KEY          Clave de administración inicial (crear/editar/eliminar usuarios).
                       Desde el panel de Administración se puede definir otra clave,
                       que queda guardada cifrada en la base de datos; ADMIN_KEY sigue
                       sirviendo como clave de respaldo por si se olvida la del panel.
                       Sin ninguna de las dos, el registro y la administración quedan cerrados.
    ANTHROPIC_API_KEY  (opcional) Clave de Claude del servidor. Si está definida,
                       la IA funciona para todos los usuarios con sesión iniciada
                       sin que cada uno ingrese su propia clave (y no se expone
                       al navegador). Si no, cada usuario usa la suya.
    CLAUDE_MODEL       (opcional) Modelo de Claude a usar. Por defecto: claude-opus-5-5.
    CLAUDE_MAX_TOKENS  (opcional) Máximo de tokens por respuesta de IA. Por defecto: 4096.
    CORS_ORIGINS       (opcional) Orígenes extra permitidos, separados por coma.
                       No hace falta si el HTML lo sirve este mismo servidor.
"""
import http.server
import socketserver
import json
import os
import sqlite3
import hashlib
import secrets
import re
import datetime
import base64
import binascii
import mimetypes
import urllib.parse
import urllib.request
import urllib.error
import gzip
import shutil
import threading
import time
from pathlib import Path

PORT = int(os.environ.get('PORT', 8790))
# Clave compartida requerida para crear cuentas nuevas (evita registro público abierto). Si no
# está configurada, el registro queda cerrado por defecto (falla-cerrado, no abierto).
ADMIN_KEY = os.environ.get('ADMIN_KEY', '')
DATA_DIR = Path(os.environ.get('DATA_DIR', Path(__file__).parent))
DB_PATH = DATA_DIR / 'epi_sistema.db'
UPLOADS_DIR = DATA_DIR / 'uploads'
BASE_DIR = Path(__file__).parent
STATIC_HTML = BASE_DIR / 'sistema_formulacion_epi.html'
DATA_ESTATICA_DIR = BASE_DIR / 'data'  # bases embebidas (jardines, población, etc.) separadas del HTML
ANTHROPIC_URL = 'https://api.anthropic.com/v1/messages'
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '').strip()
CLAUDE_MODEL = os.environ.get('CLAUDE_MODEL', 'claude-opus-5-5').strip()
CLAUDE_MAX_TOKENS = int(os.environ.get('CLAUDE_MAX_TOKENS', 4096))
CLAUDE_TIMEOUT_SEG = 180
CORS_ORIGINS = {o.strip() for o in os.environ.get('CORS_ORIGINS', '').split(',') if o.strip()}
TOKEN_DIAS_VALIDEZ = 30
MAX_UPLOAD_BYTES = 40 * 1024 * 1024  # 40MB por archivo (planos CAD pueden ser grandes)
# El archivo viaja en base64 dentro de un JSON (~33% más grande), más un margen para el resto del body.
MAX_BODY_BYTES = int(MAX_UPLOAD_BYTES * 1.4) + 1024 * 1024
EXTENSIONES_PERMITIDAS = {'pdf', 'jpg', 'jpeg', 'png', 'docx', 'xlsx', 'dwg', 'dxf'}
LARGO_MINIMO_CLAVE = 8

# Límite de intentos de login fallidos (en memoria): N fallos en la ventana bloquean por el resto de ella.
LOGIN_MAX_FALLOS = 5
LOGIN_VENTANA_SEG = 15 * 60
_fallos_login = {}  # clave (ip|usuario) -> [timestamps de fallos]
_fallos_lock = threading.Lock()


def _registrar_fallo_login(clave):
    ahora = time.time()
    with _fallos_lock:
        lista = [t for t in _fallos_login.get(clave, []) if ahora - t < LOGIN_VENTANA_SEG]
        lista.append(ahora)
        _fallos_login[clave] = lista


def _login_bloqueado(clave):
    ahora = time.time()
    with _fallos_lock:
        lista = [t for t in _fallos_login.get(clave, []) if ahora - t < LOGIN_VENTANA_SEG]
        _fallos_login[clave] = lista
        if len(lista) >= LOGIN_MAX_FALLOS:
            return int(LOGIN_VENTANA_SEG - (ahora - lista[0])) + 1
        return 0


def _limpiar_fallos_login(clave):
    with _fallos_lock:
        _fallos_login.pop(clave, None)


# Caché de archivos estáticos: ruta -> (mtime, bytes, bytes_gzip, etag)
_cache_estaticos = {}
_cache_lock = threading.Lock()


def leer_estatico(ruta):
    mtime = ruta.stat().st_mtime
    with _cache_lock:
        cacheado = _cache_estaticos.get(ruta)
        if cacheado and cacheado[0] == mtime:
            return cacheado
    contenido = ruta.read_bytes()
    comprimido = gzip.compress(contenido, compresslevel=6)
    etag = '"' + hashlib.sha1(contenido).hexdigest()[:20] + '"'
    entrada = (mtime, contenido, comprimido, etag)
    with _cache_lock:
        _cache_estaticos[ruta] = entrada
    return entrada


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def inicializar_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            username TEXT NOT NULL UNIQUE,
            password_salt TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            institucion TEXT,
            rol TEXT,
            slep TEXT,
            fecha_creacion TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sesiones (
            token TEXT PRIMARY KEY,
            usuario_id INTEGER NOT NULL,
            fecha_creacion TEXT NOT NULL,
            fecha_expiracion TEXT NOT NULL,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        );

        CREATE TABLE IF NOT EXISTS proyectos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            nombre TEXT NOT NULL,
            bip TEXT,
            data TEXT NOT NULL,
            fecha_creacion TEXT NOT NULL,
            fecha_modificacion TEXT NOT NULL,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        );

        CREATE TABLE IF NOT EXISTS documentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proyecto_id INTEGER NOT NULL,
            categoria TEXT NOT NULL,
            nombre_archivo TEXT NOT NULL,
            nombre_original TEXT NOT NULL,
            tamano INTEGER NOT NULL,
            fecha_subida TEXT NOT NULL,
            FOREIGN KEY (proyecto_id) REFERENCES proyectos(id)
        );

        CREATE TABLE IF NOT EXISTS configuracion (
            clave TEXT PRIMARY KEY,
            valor TEXT NOT NULL
        );
    ''')
    conn.commit()
    conn.close()
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    limpiar_sesiones_expiradas()


def limpiar_sesiones_expiradas():
    conn = get_db()
    conn.execute('DELETE FROM sesiones WHERE fecha_expiracion <= ?', (ahora_iso(),))
    conn.commit()
    conn.close()


def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    derivado = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), 100000)
    return salt, derivado.hex()


def verificar_password(password, salt, hash_esperado):
    _, calculado = hash_password(password, salt)
    return secrets.compare_digest(calculado, hash_esperado)


def leer_config(clave):
    conn = get_db()
    fila = conn.execute('SELECT valor FROM configuracion WHERE clave = ?', (clave,)).fetchone()
    conn.close()
    return fila['valor'] if fila else None


def clave_admin_guardada():
    """(salt, hash) de la clave de administración definida desde el panel, o None si no hay."""
    salt, hash_ = leer_config('admin_salt'), leer_config('admin_hash')
    return (salt, hash_) if salt and hash_ else None


def guardar_clave_admin(nueva):
    salt, hash_ = hash_password(nueva)
    conn = get_db()
    conn.executemany(
        'INSERT INTO configuracion (clave, valor) VALUES (?, ?) ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor',
        [('admin_salt', salt), ('admin_hash', hash_), ('admin_clave_fecha', ahora_iso())]
    )
    conn.commit()
    conn.close()


def administracion_habilitada():
    return bool(ADMIN_KEY.strip()) or clave_admin_guardada() is not None


def ahora_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def crear_sesion(usuario_id):
    conn = get_db()
    token = secrets.token_hex(32)
    expiracion = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=TOKEN_DIAS_VALIDEZ)).isoformat()
    conn.execute(
        'INSERT INTO sesiones (token, usuario_id, fecha_creacion, fecha_expiracion) VALUES (?, ?, ?, ?)',
        (token, usuario_id, ahora_iso(), expiracion)
    )
    conn.commit()
    conn.close()
    return token


def usuario_desde_token(token):
    if not token:
        return None
    conn = get_db()
    fila = conn.execute('''
        SELECT u.* FROM sesiones s JOIN usuarios u ON u.id = s.usuario_id
        WHERE s.token = ? AND s.fecha_expiracion > ?
    ''', (token, ahora_iso())).fetchone()
    conn.close()
    return dict(fila) if fila else None


def validar_datos_usuario(nombre, username, password):
    if not nombre or not username:
        return 'Nombre y usuario son obligatorios'
    if not re.fullmatch(r'[a-z0-9._-]{3,40}', username):
        return 'El usuario debe tener entre 3 y 40 caracteres: letras sin tilde, números, punto, guion o guion bajo'
    if len(password) < LARGO_MINIMO_CLAVE:
        return f'La clave debe tener al menos {LARGO_MINIMO_CLAVE} caracteres'
    return None


def usuario_publico(u):
    return {
        'id': u['id'], 'nombre': u['nombre'], 'username': u['username'],
        'institucion': u['institucion'], 'rol': u['rol'], 'slep': u['slep']
    }


class BodyDemasiadoGrande(Exception):
    pass


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def end_headers(self):
        # Si respondemos sin haber leído el body de la solicitud (p. ej. 401 antes de leer un archivo),
        # cerramos la conexión: si no, esos bytes se interpretarían como una nueva solicitud.
        try:
            pendiente = int(self.headers.get('Content-Length', 0) or 0) > 0 and not getattr(self, '_body_leido', False)
        except (ValueError, AttributeError):
            pendiente = False
        if pendiente:
            self.send_header('Connection', 'close')
            self.close_connection = True
        super().end_headers()

    def _cors(self):
        # El HTML lo sirve este mismo servidor (mismo origen), así que no hace falta CORS abierto.
        # Solo se responde a orígenes explícitamente autorizados vía CORS_ORIGINS.
        origen = self.headers.get('Origin', '')
        if origen and origen in CORS_ORIGINS:
            self.send_header('Access-Control-Allow-Origin', origen)
            self.send_header('Vary', 'Origin')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Admin-Key, x-api-key, anthropic-version')

    def _cabeceras_seguridad(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'SAMEORIGIN')
        self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')

    def _acepta_gzip(self):
        return 'gzip' in (self.headers.get('Accept-Encoding') or '').lower()

    def _enviar_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        comprimir = len(body) > 2048 and self._acepta_gzip()
        if comprimir:
            body = gzip.compress(body, compresslevel=5)
        self.send_response(status)
        self._cors()
        self._cabeceras_seguridad()
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        if comprimir:
            self.send_header('Content-Encoding', 'gzip')
            self.send_header('Vary', 'Accept-Encoding')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _ip_cliente(self):
        # Detrás del proxy de Railway la IP real viene en X-Forwarded-For.
        reenviada = (self.headers.get('X-Forwarded-For') or '').split(',')[0].strip()
        return reenviada or self.client_address[0]

    def _clave_admin_recibida(self, body=None):
        # Preferir la cabecera (no queda en logs ni historial); el body se acepta por compatibilidad.
        return self.headers.get('X-Admin-Key') or ((body or {}).get('admin_key') if isinstance(body, dict) else '') or ''

    def _despachar(self, metodo):
        self._body_leido = False
        try:
            metodo()
        except BodyDemasiadoGrande:
            self.close_connection = True
            self._enviar_json(413, {'error': f'La solicitud supera el máximo permitido ({MAX_UPLOAD_BYTES // (1024 * 1024)}MB por archivo)'})
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
        except Exception as e:  # nunca dejar al cliente sin respuesta
            print('[servidor] ERROR no controlado:', repr(e))
            try:
                self._enviar_json(500, {'error': 'Error interno del servidor'})
            except Exception:
                self.close_connection = True

    def _enviar_binario(self, status, contenido, content_type, nombre_descarga):
        self.send_response(status)
        self._cors()
        self._cabeceras_seguridad()
        self.send_header('Cache-Control', 'private, no-store')
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(contenido)))
        ascii_fallback = re.sub(r'[^A-Za-z0-9._-]', '_', nombre_descarga) or 'archivo'
        nombre_codificado = urllib.parse.quote(nombre_descarga)
        self.send_header('Content-Disposition', f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{nombre_codificado}")
        self.end_headers()
        self.wfile.write(contenido)

    def _leer_body_crudo(self):
        try:
            length = int(self.headers.get('Content-Length', 0) or 0)
        except ValueError:
            length = 0
        if length <= 0:
            return b''
        if length > MAX_BODY_BYTES:
            raise BodyDemasiadoGrande()
        datos = self.rfile.read(length)
        self._body_leido = True
        return datos

    def _leer_json(self):
        raw = self._leer_body_crudo()
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode('utf-8'))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _token_actual(self):
        auth = self.headers.get('Authorization', '')
        if auth.startswith('Bearer '):
            return auth[7:]
        return None

    def _requerir_usuario(self):
        usuario = usuario_desde_token(self._token_actual())
        if not usuario:
            self._enviar_json(401, {'error': 'Sesion invalida o expirada'})
            return None
        return usuario

    def _proyecto_de_usuario(self, proyecto_id, usuario_id):
        conn = get_db()
        fila = conn.execute('SELECT id FROM proyectos WHERE id = ? AND usuario_id = ?', (proyecto_id, usuario_id)).fetchone()
        conn.close()
        return fila is not None

    def _clave_admin_query_o_header(self):
        # Compatibilidad: versiones antiguas del frontend mandaban la clave en la URL (?admin_key=).
        if self.headers.get('X-Admin-Key'):
            return self.headers.get('X-Admin-Key')
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        return (qs.get('admin_key') or [''])[0]

    def _admin_autorizado(self, clave):
        # Se compara en bytes UTF-8 (compare_digest falla con texto no ASCII: tildes, ñ) e ignorando
        # espacios sobrantes. El frontend envía la clave codificada (encodeURIComponent) en la cabecera,
        # porque las cabeceras HTTP no admiten cualquier carácter; se acepta también sin codificar.
        # Vale la clave definida desde el panel (guardada cifrada) o, como respaldo, ADMIN_KEY de Railway.
        recibida = (clave or '').strip()
        candidatos = {recibida}
        try:
            candidatos.add(urllib.parse.unquote(recibida, errors='strict').strip())
        except Exception:
            pass
        try:
            # Una cabecera sin codificar con tildes llega decodificada como latin-1
            candidatos.add(recibida.encode('latin-1').decode('utf-8').strip())
        except Exception:
            pass
        candidatos = [c for c in candidatos if c]
        if not candidatos:
            return False
        esperada = ADMIN_KEY.strip()
        if esperada:
            esperada_b = esperada.encode('utf-8')
            if any(secrets.compare_digest(c.encode('utf-8'), esperada_b) for c in candidatos):
                return True
        guardada = clave_admin_guardada()
        if guardada:
            salt, hash_ = guardada
            if any(verificar_password(c, salt, hash_) for c in candidatos):
                return True
        return False

    def _verificar_admin(self, clave, mensaje='Clave de administración incorrecta'):
        # Igual que el login: tras varios fallos desde la misma IP se bloquea un rato (evita adivinar la clave).
        clave_intentos = f'admin|{self._ip_cliente()}'
        espera = _login_bloqueado(clave_intentos)
        if espera:
            minutos = max(1, round(espera / 60))
            self._enviar_json(429, {'error': f'Demasiados intentos fallidos. Espera unos {minutos} minuto(s) antes de volver a intentar.'})
            return False
        if not self._admin_autorizado(clave):
            _registrar_fallo_login(clave_intentos)
            self._enviar_json(403, {'error': mensaje})
            return False
        _limpiar_fallos_login(clave_intentos)
        return True

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header('Content-Length', '0')
        self.end_headers()

    def do_GET(self):
        self._despachar(self._rutear_get)

    def do_POST(self):
        self._despachar(self._rutear_post)

    def do_PUT(self):
        self._despachar(self._rutear_put)

    def do_DELETE(self):
        self._despachar(self._rutear_delete)

    def _rutear_post(self):
        if self.path == '/api/logout':
            return self._logout()
        if self.path == '/v1/messages':
            return self._proxy_claude()
        if self.path == '/api/registro':
            return self._registro()
        if self.path == '/api/login':
            return self._login()
        if self.path == '/api/admin/usuarios':
            return self._admin_crear_usuario()
        if self.path == '/api/proyectos':
            return self._crear_proyecto()
        m = re.match(r'^/api/proyectos/(\d+)/documentos$', self.path)
        if m:
            return self._subir_documento(int(m.group(1)))
        self._enviar_json(404, {'error': 'No encontrado'})

    def _rutear_get(self):
        ruta = self.path.split('?', 1)[0]
        if ruta == '/api/salud':
            return self._enviar_json(200, {'ok': True})
        if ruta == '/api/config':
            return self._config_publica()
        if self.path == '/api/me':
            return self._me()
        if self.path.startswith('/api/admin/usuarios'):
            return self._admin_listar_usuarios()
        if self.path == '/api/proyectos':
            return self._listar_proyectos()
        m = re.match(r'^/api/proyectos/(\d+)/documentos/(\d+)$', self.path)
        if m:
            return self._descargar_documento(int(m.group(1)), int(m.group(2)))
        m = re.match(r'^/api/proyectos/(\d+)/documentos$', self.path)
        if m:
            return self._listar_documentos(int(m.group(1)))
        m = re.match(r'^/api/proyectos/(\d+)$', self.path)
        if m:
            return self._obtener_proyecto(int(m.group(1)))
        if self.path.startswith('/api/'):
            return self._enviar_json(404, {'error': 'No encontrado'})
        return self._servir_estatico()

    def _rutear_put(self):
        if self.path == '/api/admin/clave':
            return self._admin_cambiar_clave()
        m = re.match(r'^/api/admin/usuarios/(\d+)$', self.path)
        if m:
            return self._admin_editar_usuario(int(m.group(1)))
        m = re.match(r'^/api/proyectos/(\d+)$', self.path)
        if m:
            return self._actualizar_proyecto(int(m.group(1)))
        self._enviar_json(404, {'error': 'No encontrado'})

    def _rutear_delete(self):
        ruta = self.path.split('?', 1)[0]
        m = re.match(r'^/api/admin/usuarios/(\d+)$', ruta)
        if m:
            return self._admin_eliminar_usuario(int(m.group(1)))
        m = re.match(r'^/api/proyectos/(\d+)/documentos/(\d+)$', ruta)
        if m:
            return self._eliminar_documento(int(m.group(1)), int(m.group(2)))
        m = re.match(r'^/api/proyectos/(\d+)$', ruta)
        if m:
            return self._eliminar_proyecto(int(m.group(1)))
        self._enviar_json(404, {'error': 'No encontrado'})

    # --- handlers ---

    def _registro(self):
        body = self._leer_json()
        if not self._verificar_admin(self._clave_admin_recibida(body), 'Clave de acceso al sistema incorrecta'):
            return

        nombre = (body.get('nombre') or '').strip()
        username = (body.get('username') or '').strip().lower()
        password = body.get('password') or ''
        error = validar_datos_usuario(nombre, username, password)
        if error:
            return self._enviar_json(400, {'error': error})

        conn = get_db()
        existe = conn.execute('SELECT id FROM usuarios WHERE username = ?', (username,)).fetchone()
        if existe:
            conn.close()
            return self._enviar_json(400, {'error': 'Ese nombre de usuario ya existe'})

        salt, hash_ = hash_password(password)
        cur = conn.execute(
            'INSERT INTO usuarios (nombre, username, password_salt, password_hash, institucion, rol, slep, fecha_creacion) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (nombre, username, salt, hash_, body.get('institucion'), body.get('rol'), body.get('slep'), ahora_iso())
        )
        usuario_id = cur.lastrowid
        conn.commit()
        fila = conn.execute('SELECT * FROM usuarios WHERE id = ?', (usuario_id,)).fetchone()
        conn.close()

        token = crear_sesion(usuario_id)
        self._enviar_json(201, {'token': token, 'usuario': usuario_publico(fila)})

    def _login(self):
        body = self._leer_json()
        username = (body.get('username') or '').strip().lower()
        password = body.get('password') or ''

        clave_intentos = f'{self._ip_cliente()}|{username}'
        espera = _login_bloqueado(clave_intentos)
        if espera:
            minutos = max(1, round(espera / 60))
            return self._enviar_json(429, {'error': f'Demasiados intentos fallidos. Espera unos {minutos} minuto(s) antes de volver a intentar.'})

        conn = get_db()
        fila = conn.execute('SELECT * FROM usuarios WHERE username = ?', (username,)).fetchone()
        conn.close()

        if not fila or not verificar_password(password, fila['password_salt'], fila['password_hash']):
            _registrar_fallo_login(clave_intentos)
            return self._enviar_json(401, {'error': 'Usuario o clave incorrectos'})

        _limpiar_fallos_login(clave_intentos)
        limpiar_sesiones_expiradas()
        token = crear_sesion(fila['id'])
        self._enviar_json(200, {'token': token, 'usuario': usuario_publico(fila)})

    def _logout(self):
        token = self._token_actual()
        if token:
            conn = get_db()
            conn.execute('DELETE FROM sesiones WHERE token = ?', (token,))
            conn.commit()
            conn.close()
        self._enviar_json(200, {'ok': True})

    def _config_publica(self):
        # Lo que el frontend necesita saber del servidor (nunca expone claves).
        self._enviar_json(200, {
            'ia_clave_servidor': bool(ANTHROPIC_API_KEY),
            'ia_modelo': CLAUDE_MODEL,
            'ia_max_tokens': CLAUDE_MAX_TOKENS,
            'registro_habilitado': administracion_habilitada(),
            'largo_minimo_clave': LARGO_MINIMO_CLAVE,
        })

    def _me(self):
        usuario = self._requerir_usuario()
        if not usuario:
            return
        self._enviar_json(200, {'usuario': usuario_publico(usuario)})

    def _listar_proyectos(self):
        usuario = self._requerir_usuario()
        if not usuario:
            return
        conn = get_db()
        filas = conn.execute(
            'SELECT id, nombre, bip, data, fecha_creacion, fecha_modificacion FROM proyectos WHERE usuario_id = ? ORDER BY fecha_modificacion DESC',
            (usuario['id'],)
        ).fetchall()
        conn.close()

        proyectos = []
        for f in filas:
            try:
                data = json.loads(f['data'])
                completados = len((data.get('ui') or {}).get('modulos_completados') or [])
            except Exception:
                completados = 0
            proyectos.append({
                'id': f['id'], 'nombre': f['nombre'], 'bip': f['bip'],
                'avance_pct': round(completados / 9 * 100),
                'fecha_creacion': f['fecha_creacion'], 'fecha_modificacion': f['fecha_modificacion']
            })
        self._enviar_json(200, {'proyectos': proyectos})

    def _crear_proyecto(self):
        usuario = self._requerir_usuario()
        if not usuario:
            return
        body = self._leer_json()
        nombre = body.get('nombre') or 'Nuevo proyecto sin nombre'
        data = body.get('data') or {}
        conn = get_db()
        ahora = ahora_iso()
        cur = conn.execute(
            'INSERT INTO proyectos (usuario_id, nombre, bip, data, fecha_creacion, fecha_modificacion) VALUES (?, ?, ?, ?, ?, ?)',
            (usuario['id'], nombre, (data.get('proyecto') or {}).get('bip'), json.dumps(data), ahora, ahora)
        )
        proyecto_id = cur.lastrowid
        conn.commit()
        conn.close()
        self._enviar_json(201, {'id': proyecto_id})

    def _obtener_proyecto(self, proyecto_id):
        usuario = self._requerir_usuario()
        if not usuario:
            return
        conn = get_db()
        fila = conn.execute('SELECT * FROM proyectos WHERE id = ? AND usuario_id = ?', (proyecto_id, usuario['id'])).fetchone()
        conn.close()
        if not fila:
            return self._enviar_json(404, {'error': 'Proyecto no encontrado'})
        self._enviar_json(200, {'id': fila['id'], 'nombre': fila['nombre'], 'data': json.loads(fila['data'])})

    def _actualizar_proyecto(self, proyecto_id):
        usuario = self._requerir_usuario()
        if not usuario:
            return
        body = self._leer_json()
        data = body.get('data')
        if data is None:
            return self._enviar_json(400, {'error': 'Falta el campo data'})

        conn = get_db()
        existe = conn.execute('SELECT id FROM proyectos WHERE id = ? AND usuario_id = ?', (proyecto_id, usuario['id'])).fetchone()
        if not existe:
            conn.close()
            return self._enviar_json(404, {'error': 'Proyecto no encontrado'})

        nombre = (data.get('proyecto') or {}).get('nombre')
        bip = (data.get('proyecto') or {}).get('bip')
        ahora = ahora_iso()
        conn.execute(
            'UPDATE proyectos SET data = ?, nombre = COALESCE(?, nombre), bip = ?, fecha_modificacion = ? WHERE id = ?',
            (json.dumps(data), nombre, bip, ahora, proyecto_id)
        )
        conn.commit()
        conn.close()
        self._enviar_json(200, {'ok': True, 'fecha_modificacion': ahora})

    def _eliminar_proyecto(self, proyecto_id):
        usuario = self._requerir_usuario()
        if not usuario:
            return
        if not self._proyecto_de_usuario(proyecto_id, usuario['id']):
            return self._enviar_json(404, {'error': 'Proyecto no encontrado'})
        conn = get_db()
        try:
            # Primero los documentos (la llave foránea impide borrar un proyecto que aún los tiene)
            conn.execute('DELETE FROM documentos WHERE proyecto_id = ?', (proyecto_id,))
            conn.execute('DELETE FROM proyectos WHERE id = ? AND usuario_id = ?', (proyecto_id, usuario['id']))
            conn.commit()
        finally:
            conn.close()
        # Y luego los archivos físicos subidos de ese proyecto
        carpeta = UPLOADS_DIR / str(proyecto_id)
        if carpeta.is_dir():
            shutil.rmtree(carpeta, ignore_errors=True)
        self._enviar_json(200, {'ok': True})

    def _admin_listar_usuarios(self):
        if not self._verificar_admin(self._clave_admin_query_o_header()):
            return
        conn = get_db()
        filas = conn.execute('''
            SELECT u.id, u.nombre, u.username, u.institucion, u.fecha_creacion,
                   (SELECT COUNT(*) FROM proyectos p WHERE p.usuario_id = u.id) AS cantidad_proyectos
            FROM usuarios u ORDER BY u.nombre
        ''').fetchall()
        conn.close()
        self._enviar_json(200, {'usuarios': [dict(f) for f in filas]})

    def _admin_crear_usuario(self):
        body = self._leer_json()
        if not self._verificar_admin(self._clave_admin_recibida(body)):
            return
        nombre = (body.get('nombre') or '').strip()
        username = (body.get('username') or '').strip().lower()
        password = body.get('password') or ''
        error = validar_datos_usuario(nombre, username, password)
        if error:
            return self._enviar_json(400, {'error': error})
        conn = get_db()
        existe = conn.execute('SELECT id FROM usuarios WHERE username = ?', (username,)).fetchone()
        if existe:
            conn.close()
            return self._enviar_json(400, {'error': 'Ese nombre de usuario ya existe'})
        salt, hash_ = hash_password(password)
        cur = conn.execute(
            'INSERT INTO usuarios (nombre, username, password_salt, password_hash, institucion, fecha_creacion) VALUES (?, ?, ?, ?, ?, ?)',
            (nombre, username, salt, hash_, body.get('institucion'), ahora_iso())
        )
        conn.commit()
        conn.close()
        self._enviar_json(201, {'id': cur.lastrowid})

    def _admin_editar_usuario(self, usuario_id):
        body = self._leer_json()
        if not self._verificar_admin(self._clave_admin_recibida(body)):
            return
        conn = get_db()
        existe = conn.execute('SELECT id FROM usuarios WHERE id = ?', (usuario_id,)).fetchone()
        if not existe:
            conn.close()
            return self._enviar_json(404, {'error': 'Usuario no encontrado'})

        nombre = (body.get('nombre') or '').strip()
        institucion = body.get('institucion')
        nueva_password = body.get('nueva_password') or ''
        if not nombre:
            conn.close()
            return self._enviar_json(400, {'error': 'El nombre no puede quedar vacío'})
        if nueva_password and len(nueva_password) < LARGO_MINIMO_CLAVE:
            conn.close()
            return self._enviar_json(400, {'error': f'La nueva clave debe tener al menos {LARGO_MINIMO_CLAVE} caracteres'})

        if nueva_password:
            salt, hash_ = hash_password(nueva_password)
            conn.execute(
                'UPDATE usuarios SET nombre = ?, institucion = ?, password_salt = ?, password_hash = ? WHERE id = ?',
                (nombre, institucion, salt, hash_, usuario_id)
            )
            # Cambiar la clave cierra las sesiones abiertas de ese usuario
            conn.execute('DELETE FROM sesiones WHERE usuario_id = ?', (usuario_id,))
        else:
            conn.execute('UPDATE usuarios SET nombre = ?, institucion = ? WHERE id = ?', (nombre, institucion, usuario_id))
        conn.commit()
        conn.close()
        self._enviar_json(200, {'ok': True})

    def _admin_cambiar_clave(self):
        # La clave actual viaja en X-Admin-Key; la nueva en el body (JSON, admite tildes y ñ sin codificar).
        body = self._leer_json()
        if not self._verificar_admin(self.headers.get('X-Admin-Key') or '', 'La clave actual no es correcta'):
            return
        nueva = (body.get('nueva_clave') or '').strip()
        if len(nueva) < LARGO_MINIMO_CLAVE:
            return self._enviar_json(400, {'error': f'La nueva clave debe tener al menos {LARGO_MINIMO_CLAVE} caracteres'})
        if len(nueva) > 200:
            return self._enviar_json(400, {'error': 'La nueva clave es demasiado larga (máximo 200 caracteres)'})
        guardar_clave_admin(nueva)
        print('[servidor] Clave de administración cambiada desde el panel')
        self._enviar_json(200, {'ok': True})

    def _admin_eliminar_usuario(self, usuario_id):
        if not self._verificar_admin(self._clave_admin_query_o_header()):
            return
        conn = get_db()
        tiene_proyectos = conn.execute('SELECT COUNT(*) c FROM proyectos WHERE usuario_id = ?', (usuario_id,)).fetchone()['c']
        if tiene_proyectos:
            conn.close()
            return self._enviar_json(409, {'error': f'Este usuario tiene {tiene_proyectos} proyecto(s) y no se puede eliminar. Elimina o reasigna sus proyectos primero.'})
        conn.execute('DELETE FROM sesiones WHERE usuario_id = ?', (usuario_id,))
        conn.execute('DELETE FROM usuarios WHERE id = ?', (usuario_id,))
        conn.commit()
        conn.close()
        self._enviar_json(200, {'ok': True})

    def _subir_documento(self, proyecto_id):
        usuario = self._requerir_usuario()
        if not usuario:
            return
        if not self._proyecto_de_usuario(proyecto_id, usuario['id']):
            return self._enviar_json(404, {'error': 'Proyecto no encontrado'})

        body = self._leer_json()
        categoria = (body.get('categoria') or '').strip()
        nombre_original = (body.get('nombre_original') or '').strip()
        contenido_base64 = body.get('contenido_base64') or ''

        if not categoria or not nombre_original or not contenido_base64:
            return self._enviar_json(400, {'error': 'Faltan categoria, nombre_original o contenido_base64'})

        extension = nombre_original.rsplit('.', 1)[-1].lower() if '.' in nombre_original else ''
        if extension not in EXTENSIONES_PERMITIDAS:
            return self._enviar_json(400, {'error': f'Extensión no permitida: .{extension}'})

        try:
            contenido = base64.b64decode(contenido_base64, validate=True)
        except (binascii.Error, ValueError):
            return self._enviar_json(400, {'error': 'contenido_base64 inválido'})

        if len(contenido) > MAX_UPLOAD_BYTES:
            return self._enviar_json(400, {'error': f'El archivo supera el máximo permitido ({MAX_UPLOAD_BYTES // (1024 * 1024)}MB)'})

        carpeta_proyecto = UPLOADS_DIR / str(proyecto_id)
        carpeta_proyecto.mkdir(parents=True, exist_ok=True)
        nombre_archivo = f'{secrets.token_hex(16)}.{extension}'
        (carpeta_proyecto / nombre_archivo).write_bytes(contenido)

        conn = get_db()
        ahora = ahora_iso()
        cur = conn.execute(
            'INSERT INTO documentos (proyecto_id, categoria, nombre_archivo, nombre_original, tamano, fecha_subida) VALUES (?, ?, ?, ?, ?, ?)',
            (proyecto_id, categoria, nombre_archivo, nombre_original, len(contenido), ahora)
        )
        doc_id = cur.lastrowid
        conn.commit()
        conn.close()

        self._enviar_json(201, {
            'id': doc_id, 'categoria': categoria, 'nombre_original': nombre_original,
            'tamano': len(contenido), 'fecha_subida': ahora
        })

    def _listar_documentos(self, proyecto_id):
        usuario = self._requerir_usuario()
        if not usuario:
            return
        if not self._proyecto_de_usuario(proyecto_id, usuario['id']):
            return self._enviar_json(404, {'error': 'Proyecto no encontrado'})

        conn = get_db()
        filas = conn.execute(
            'SELECT id, categoria, nombre_original, tamano, fecha_subida FROM documentos WHERE proyecto_id = ? ORDER BY fecha_subida DESC',
            (proyecto_id,)
        ).fetchall()
        conn.close()
        self._enviar_json(200, {'documentos': [dict(f) for f in filas]})

    def _descargar_documento(self, proyecto_id, doc_id):
        usuario = self._requerir_usuario()
        if not usuario:
            return
        if not self._proyecto_de_usuario(proyecto_id, usuario['id']):
            return self._enviar_json(404, {'error': 'Proyecto no encontrado'})

        conn = get_db()
        fila = conn.execute('SELECT * FROM documentos WHERE id = ? AND proyecto_id = ?', (doc_id, proyecto_id)).fetchone()
        conn.close()
        if not fila:
            return self._enviar_json(404, {'error': 'Documento no encontrado'})

        ruta = UPLOADS_DIR / str(proyecto_id) / fila['nombre_archivo']
        if not ruta.exists():
            return self._enviar_json(404, {'error': 'El archivo ya no existe en el servidor'})

        content_type = mimetypes.guess_type(fila['nombre_original'])[0] or 'application/octet-stream'
        self._enviar_binario(200, ruta.read_bytes(), content_type, fila['nombre_original'])

    def _eliminar_documento(self, proyecto_id, doc_id):
        usuario = self._requerir_usuario()
        if not usuario:
            return
        if not self._proyecto_de_usuario(proyecto_id, usuario['id']):
            return self._enviar_json(404, {'error': 'Proyecto no encontrado'})

        conn = get_db()
        fila = conn.execute('SELECT * FROM documentos WHERE id = ? AND proyecto_id = ?', (doc_id, proyecto_id)).fetchone()
        if not fila:
            conn.close()
            return self._enviar_json(404, {'error': 'Documento no encontrado'})

        conn.execute('DELETE FROM documentos WHERE id = ?', (doc_id,))
        conn.commit()
        conn.close()

        ruta = UPLOADS_DIR / str(proyecto_id) / fila['nombre_archivo']
        if ruta.exists():
            ruta.unlink()

        self._enviar_json(200, {'ok': True})

    def _servir_estatico(self):
        ruta_url = urllib.parse.unquote(self.path.split('?', 1)[0])
        if ruta_url in ('/', '/sistema_formulacion_epi.html'):
            archivo, tipo, cache = STATIC_HTML, 'text/html; charset=utf-8', 'no-cache'
        else:
            m = re.fullmatch(r'/data/([A-Za-z0-9_-]+\.js)', ruta_url)
            if not m:
                return self._enviar_json(404, {'error': 'No encontrado'})
            archivo, tipo = DATA_ESTATICA_DIR / m.group(1), 'application/javascript; charset=utf-8'
            # Los datos cambian solo al desplegar: el navegador revalida con ETag (respuesta 304, sin re-descargar)
            cache = 'public, max-age=3600, must-revalidate'
        if not archivo.is_file():
            return self._enviar_json(404, {'error': f'No se encontró {archivo.name} junto al servidor'})

        _, contenido, comprimido, etag = leer_estatico(archivo)
        if self.headers.get('If-None-Match') == etag:
            self.send_response(304)
            self.send_header('ETag', etag)
            self.send_header('Cache-Control', cache)
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        usar_gzip = self._acepta_gzip()
        cuerpo = comprimido if usar_gzip else contenido
        self.send_response(200)
        self._cabeceras_seguridad()
        self.send_header('Content-Type', tipo)
        self.send_header('Cache-Control', cache)
        self.send_header('ETag', etag)
        self.send_header('Vary', 'Accept-Encoding')
        if usar_gzip:
            self.send_header('Content-Encoding', 'gzip')
        self.send_header('Content-Length', str(len(cuerpo)))
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(cuerpo)

    def do_HEAD(self):
        self._despachar(self._servir_estatico)

    def _proxy_claude(self):
        raw = self._leer_body_crudo()
        try:
            payload = json.loads(raw.decode('utf-8')) if raw else {}
        except Exception:
            return self._enviar_json(400, {'error': {'message': 'Solicitud inválida'}})
        if not isinstance(payload, dict):
            return self._enviar_json(400, {'error': {'message': 'Solicitud inválida'}})

        if ANTHROPIC_API_KEY:
            # Con clave del servidor: solo usuarios con sesión pueden usar la IA (la clave la paga el dueño)
            if not usuario_desde_token(self._token_actual()):
                return self._enviar_json(401, {'error': {'message': 'Inicia sesión para usar la redacción asistida por IA'}})
            api_key = ANTHROPIC_API_KEY
        else:
            api_key = (self.headers.get('x-api-key') or '').strip()
            if not api_key:
                return self._enviar_json(400, {'error': {'message': 'Falta la clave de API de Claude (configúrala en Configuración)'}})

        # El servidor decide el modelo y el tope de tokens (evita abusos y deja el modelo configurable sin tocar el HTML)
        payload['model'] = CLAUDE_MODEL
        try:
            pedido = int(payload.get('max_tokens') or CLAUDE_MAX_TOKENS)
        except (TypeError, ValueError):
            pedido = CLAUDE_MAX_TOKENS
        payload['max_tokens'] = max(1, min(pedido, CLAUDE_MAX_TOKENS))

        req = urllib.request.Request(
            ANTHROPIC_URL,
            data=json.dumps(payload).encode('utf-8'),
            method='POST',
            headers={
                'x-api-key': api_key,
                'anthropic-version': self.headers.get('anthropic-version', '2023-06-01'),
                'content-type': 'application/json',
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=CLAUDE_TIMEOUT_SEG) as resp:
                status = resp.status
                data = resp.read()
        except urllib.error.HTTPError as e:
            status = e.code
            data = e.read()
        except Exception as e:
            print('[servidor] Error contactando a Claude:', repr(e))
            return self._enviar_json(502, {'error': {'message': 'No se pudo contactar al servicio de IA. Intenta de nuevo en unos minutos.'}})

        self.send_response(status)
        self._cors()
        self._cabeceras_seguridad()
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        # Nunca registrar la query string (podría contener claves de versiones antiguas del frontend)
        args = tuple(re.sub(r'\?\S*', '', a, count=1) if isinstance(a, str) and a.startswith(('GET ', 'POST ', 'PUT ', 'DELETE ', 'HEAD ')) else a for a in args)
        print('[servidor]', self._ip_cliente(), format % args)


class ServidorEPI(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


if __name__ == '__main__':
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    inicializar_db()
    server = ServidorEPI(('0.0.0.0', PORT), Handler)
    print(f'Sistema de Formulación corriendo en el puerto {PORT}')
    print(f'Base de datos y documentos en: {DATA_DIR}')
    print(f'IA: modelo {CLAUDE_MODEL}, máx. {CLAUDE_MAX_TOKENS} tokens, ' + ('clave del servidor' if ANTHROPIC_API_KEY else 'cada usuario usa su propia clave'))
    if not administracion_habilitada():
        print('AVISO: ADMIN_KEY no está definida (ni hay clave de administración guardada) — el registro y la administración de usuarios quedan cerrados.')
    print('Deja esta ventana abierta mientras uses el sistema.')
    server.serve_forever()
