# Cómo publicar este sistema en la web

El sistema es un solo servidor (`backend_epi.py`, solo librería estándar de Python)
que sirve la página, los datos de referencia (`data/*.js`), la API (usuarios,
proyectos, documentos) y el puente hacia la IA de Claude.

```
sistema_formulacion_epi.html   página (≈0,5 MB)
data/logo.js                   logo MINEDUC
data/jardines.js               base JUNJI/VTF, áreas de influencia, coordenadas
data/poblacion.js              población 0-5 por manzana (Censo 2024) y proyección INE
backend_epi.py                 servidor
```

Los archivos de `data/` se envían comprimidos (gzip) y quedan en caché del
navegador: la primera visita descarga ≈1,3 MB en vez de 4,8 MB, y las
siguientes casi nada.

## 0. Antes de subir nada: secretos

- **Nunca** dejes tokens o claves dentro de la carpeta del proyecto sin que
  estén en `.gitignore`. `sistema-formulacion.txt`, `.env` y similares ya
  están excluidos.
- El repositorio tiene un *hook* local (`.git/hooks/pre-commit`) que bloquea
  commits que contengan algo con forma de token de GitHub o clave de Anthropic.
- Antes de `git push`, revisa con `git status` qué vas a subir.

## 1. Probar en tu computador como si estuviera online

Doble clic en **`simular_online.bat`**. Levanta el servidor con la misma
configuración que tendría en Railway (variables de entorno, carpeta de datos
separada en `datos_simulacion/`, clave de administración) y abre el navegador
en http://localhost:8790. Para cerrarlo, cierra la ventana negra.

## 2. Subir los cambios a GitHub

El repositorio ya está conectado a `github.com/luchoalvear/FORMULATUJARDIN`.

```
git status          (revisa que no aparezcan archivos con claves)
git add -A
git commit -m "Descripción del cambio"
git push
```

## 3. Railway

1. https://railway.app → "New Project" → "Deploy from GitHub repo" → elige el repositorio.
2. Railway detecta Python y usa el `Procfile` (`web: python backend_epi.py`).

### 3.1 Volume (obligatorio)

Sin esto, cada redeploy borra usuarios y proyectos.

1. En el servicio → "Volumes" → "New Volume" → montar en `/data`.
2. En "Variables": `DATA_DIR` = `/data`.

### 3.2 Variables de entorno

| Variable | Obligatoria | Para qué |
|---|---|---|
| `DATA_DIR` | Sí | Carpeta del Volume (`/data`). |
| `ADMIN_KEY` | Sí | Clave inicial de administración, larga y que solo tú conozcas. Permite entrar al panel de administración (crear/editar/eliminar usuarios). Después puedes definir otra clave desde el mismo panel; `ADMIN_KEY` sigue sirviendo de respaldo si la olvidas. |
| `ANTHROPIC_API_KEY` | Recomendada | Tu clave de Claude. Con ella, la redacción con IA funciona para todas las cuentas con sesión iniciada, sin que cada cliente ponga su clave; la clave nunca llega al navegador. Sin ella, cada usuario debe ingresar la suya en Configuración. |
| `CLAUDE_MODEL` | No | Modelo de IA (por defecto `claude-opus-5-5`). Cámbialo aquí cuando salga uno nuevo, sin tocar el código. |
| `CLAUDE_MAX_TOKENS` | No | Largo máximo de cada respuesta de IA (por defecto 4096 ≈ 3.000 palabras). |
| `CORS_ORIGINS` | No | Solo si otra página web (otro dominio) necesita llamar a la API. Normalmente se deja vacía. |

Railway define `PORT` solo.

### 3.3 Health check (opcional)

En "Settings" → "Healthcheck Path" puedes poner `/api/salud`.

## 4. Seguridad incluida

- Claves de usuario con PBKDF2 (100.000 iteraciones), mínimo 8 caracteres.
- Bloqueo temporal tras 5 intentos fallidos de login (15 minutos, por IP y usuario).
- La clave de administración viaja en una cabecera (`X-Admin-Key`), no en la URL, y los logs nunca registran parámetros de URL.
- La clave de administración definida desde el panel se guarda cifrada (PBKDF2) en la base de datos, nunca en texto plano.
- Bloqueo temporal tras 5 intentos fallidos de clave de administración (15 minutos, por IP).
- Cerrar sesión invalida el token en el servidor; cambiar la clave de un usuario cierra sus sesiones.
- Sesiones vencidas se limpian automáticamente.
- Límite de tamaño por solicitud (archivos de hasta 40 MB).
- La API solo acepta llamadas de la misma página (sin CORS abierto).

## 5. Dar acceso a un cliente

Entra al panel de administración (en la pantalla de login) con tu clave de
administración y crea la cuenta. Si cambias la clave de administración, las
cuentas ya creadas siguen funcionando.

### Cambiar la clave de administración

En el panel de administración, abajo, usa **"Cambiar clave de administración"**:
pide la clave actual y la nueva dos veces (mínimo 8 caracteres; admite tildes,
ñ y espacios). Desde ese momento entras con la nueva. La `ADMIN_KEY` de Railway
sigue funcionando como respaldo: si olvidas la clave del panel, entra con
`ADMIN_KEY` y define otra.
