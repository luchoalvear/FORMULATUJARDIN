# Cómo publicar este sistema en la web

El código ya está listo (servidor único, rutas relativas, `.gitignore`,
`requirements.txt`, `Procfile`) y comiteado en este repositorio git local.
Solo faltan estos pasos, que requieren tus propias cuentas.

## 1. Crear el repositorio en GitHub

1. Entra a https://github.com/new
2. Ponle un nombre (el que quieras).
3. Déjalo **vacío**: no marques "Add a README", "Add .gitignore" ni "license"
   (ya los tienes en este repo y chocarían al subir).
4. Clic en "Create repository".
5. Copia la URL que te muestra (termina en `.git`).

## 2. Conectar este repo local y subirlo

Desde la carpeta del proyecto, en la terminal:

```
git remote add origin https://github.com/TU_USUARIO/TU_REPO.git
git branch -M main
git push -u origin main
```

La primera vez te va a pedir iniciar sesión en GitHub.

## 3. Crear cuenta y proyecto en Railway

1. Entra a https://railway.app (puedes entrar directo con tu cuenta de GitHub).
2. "New Project" → "Deploy from GitHub repo" → elige el repositorio que
   acabas de subir.
3. Railway detecta que es Python y lo despliega automáticamente.

## 4. Agregar el Volume — MUY IMPORTANTE, no te lo saltes

Sin este paso, cada vez que Railway vuelva a desplegar (por ejemplo al subir
un cambio de código) se pierden las cuentas de usuario y los proyectos
guardados.

1. Dentro del servicio, pestaña "Volumes" → "New Volume".
2. Móntalo en la ruta `/data`.
3. En "Variables" del servicio, agrega: `DATA_DIR` = `/data`.

## 4.1 Agregar la clave de acceso (ADMIN_KEY) — para controlar quién puede crear cuentas

El registro público está cerrado por defecto: nadie puede crear una cuenta sin
conocer esta clave. Así controlas manualmente quién tiene acceso al sistema
(por ejemplo, solo la compartes con clientes que ya pagaron).

1. En "Variables" del servicio (mismo lugar que `DATA_DIR`), agrega:
   `ADMIN_KEY` = una clave larga que solo tú conozcas (ej. una frase random).
2. Para dar acceso a alguien: entra tú mismo al formulario "Crear cuenta" del
   sistema y créala por esa persona, usando esa clave — o pásale la clave
   directamente si prefieres que se registre ella misma.
3. Si más adelante quieres cambiar quién puede registrarse, solo cambias el
   valor de `ADMIN_KEY` en Railway (las cuentas ya creadas no se ven afectadas).

## 5. Listo

Railway te asigna un dominio con HTTPS automático
(`tu-proyecto.up.railway.app`). Ábrelo — debería verse y funcionar igual que
en tu computador, con la base de jardines JUNJI, la normativa, el catálogo de
precios, y los datos de población/proyección del INE ya incluidos en el
código (no dependen de nada externo).

## Actualizaciones futuras

Cuando quieras subir cambios de código más adelante:

```
git add -A
git commit -m "Descripción del cambio"
git push
```

Railway vuelve a desplegar solo al detectar el push. Los datos de usuarios
y proyectos no se pierden porque quedan en el Volume, no en el código.
