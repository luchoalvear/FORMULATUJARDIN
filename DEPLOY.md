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
