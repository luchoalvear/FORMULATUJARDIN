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
    PORT      Puerto a escuchar (Railway la define automáticamente).
    DATA_DIR  Carpeta donde viven la base de datos y los documentos subidos.
              Debe apuntar a un volumen persistente en producción (si no,
              se pierden los datos en cada redeploy). Por defecto, la misma
              carpeta del script (sirve para uso local).
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
from pathlib import Path

PORT = int(os.environ.get('PORT', 8790))
DATA_DIR = Path(os.environ.get('DATA_DIR', Path(__file__).parent))
DB_PATH = DATA_DIR / 'epi_sistema.db'
UPLOADS_DIR = DATA_DIR / 'uploads'
STATIC_HTML = Path(__file__).parent / 'sistema_formulacion_epi.html'
ANTHROPIC_URL = 'https://api.anthropic.com/v1/messages'
TOKEN_DIAS_VALIDEZ = 30
MAX_UPLOAD_BYTES = 40 * 1024 * 1024  # 40MB por archivo (planos CAD pueden ser grandes)
EXTENSIONES_PERMITIDAS = {'pdf', 'jpg', 'jpeg', 'png', 'docx', 'xlsx', 'dwg', 'dxf'}


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
    ''')
    conn.commit()
    conn.close()
    UPLOADS_DIR.mkdir(exist_ok=True)


def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    derivado = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), 100000)
    return salt, derivado.hex()


def verificar_password(password, salt, hash_esperado):
    _, calculado = hash_password(password, salt)
    return secrets.compare_digest(calculado, hash_esperado)


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


def usuario_publico(u):
    return {
        'id': u['id'], 'nombre': u['nombre'], 'username': u['username'],
        'institucion': u['institucion'], 'rol': u['rol'], 'slep': u['slep']
    }


class Handler(http.server.BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')

    def _enviar_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self._cors()
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _enviar_binario(self, status, contenido, content_type, nombre_descarga):
        self.send_response(status)
        self._cors()
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(contenido)))
        ascii_fallback = re.sub(r'[^A-Za-z0-9._-]', '_', nombre_descarga) or 'archivo'
        nombre_codificado = urllib.parse.quote(nombre_descarga)
        self.send_header('Content-Disposition', f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{nombre_codificado}")
        self.end_headers()
        self.wfile.write(contenido)

    def _leer_json(self):
        length = int(self.headers.get('Content-Length', 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode('utf-8'))
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

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_POST(self):
        if self.path == '/v1/messages':
            return self._proxy_claude()
        if self.path == '/api/registro':
            return self._registro()
        if self.path == '/api/login':
            return self._login()
        if self.path == '/api/proyectos':
            return self._crear_proyecto()
        m = re.match(r'^/api/proyectos/(\d+)/documentos$', self.path)
        if m:
            return self._subir_documento(int(m.group(1)))
        self._enviar_json(404, {'error': 'No encontrado'})

    def do_GET(self):
        if self.path == '/api/me':
            return self._me()
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

    def do_PUT(self):
        m = re.match(r'^/api/proyectos/(\d+)$', self.path)
        if m:
            return self._actualizar_proyecto(int(m.group(1)))
        self._enviar_json(404, {'error': 'No encontrado'})

    def do_DELETE(self):
        m = re.match(r'^/api/proyectos/(\d+)/documentos/(\d+)$', self.path)
        if m:
            return self._eliminar_documento(int(m.group(1)), int(m.group(2)))
        m = re.match(r'^/api/proyectos/(\d+)$', self.path)
        if m:
            return self._eliminar_proyecto(int(m.group(1)))
        self._enviar_json(404, {'error': 'No encontrado'})

    # --- handlers ---

    def _registro(self):
        body = self._leer_json()
        nombre = (body.get('nombre') or '').strip()
        username = (body.get('username') or '').strip().lower()
        password = body.get('password') or ''
        if not nombre or not username or len(password) < 4:
            return self._enviar_json(400, {'error': 'Nombre, usuario y una clave de al menos 4 caracteres son obligatorios'})

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

        conn = get_db()
        fila = conn.execute('SELECT * FROM usuarios WHERE username = ?', (username,)).fetchone()
        conn.close()

        if not fila or not verificar_password(password, fila['password_salt'], fila['password_hash']):
            return self._enviar_json(401, {'error': 'Usuario o clave incorrectos'})

        token = crear_sesion(fila['id'])
        self._enviar_json(200, {'token': token, 'usuario': usuario_publico(fila)})

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
        conn = get_db()
        conn.execute('DELETE FROM proyectos WHERE id = ? AND usuario_id = ?', (proyecto_id, usuario['id']))
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
        if self.path not in ('/', '/sistema_formulacion_epi.html'):
            return self._enviar_json(404, {'error': 'No encontrado'})
        if not STATIC_HTML.exists():
            return self._enviar_json(500, {'error': 'No se encontró sistema_formulacion_epi.html junto al servidor'})
        contenido = STATIC_HTML.read_bytes()
        self.send_response(200)
        self._cors()
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(contenido)))
        self.end_headers()
        self.wfile.write(contenido)

    def _proxy_claude(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length) if length else b''
        req = urllib.request.Request(
            ANTHROPIC_URL,
            data=body,
            method='POST',
            headers={
                'x-api-key': self.headers.get('x-api-key', ''),
                'anthropic-version': self.headers.get('anthropic-version', '2023-06-01'),
                'content-type': 'application/json',
            },
        )
        try:
            with urllib.request.urlopen(req) as resp:
                status = resp.status
                data = resp.read()
        except urllib.error.HTTPError as e:
            status = e.code
            data = e.read()
        except Exception as e:
            return self._enviar_json(502, {'error': str(e)})

        self.send_response(status)
        self._cors()
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        print('[servidor]', self.address_string(), *args)


class ServidorEPI(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


if __name__ == '__main__':
    inicializar_db()
    server = ServidorEPI(('0.0.0.0', PORT), Handler)
    print(f'Sistema de Formulación corriendo en el puerto {PORT}')
    print(f'Base de datos y documentos en: {DATA_DIR}')
    print('Deja esta ventana abierta mientras uses el sistema.')
    server.serve_forever()
