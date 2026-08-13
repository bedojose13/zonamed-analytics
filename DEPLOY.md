# Desplegar Zonamed Analytics en la nube (gratis) — acceso desde el celular sin la PC

Esta guía deja la app accesible desde cualquier lugar con datos móviles, en una URL fija, sin
necesidad de que tu PC esté encendida. Usa 3 servicios gratuitos: **Neon** (base de datos
Postgres), **Render** (API FastAPI) y **Streamlit Community Cloud** (frontend). El repo ya está
listo (`git init` + primer commit hechos); solo faltan las cuentas y conectarlas.

---

## 1. Crear el repositorio en GitHub

1. Entra a [github.com/new](https://github.com/new) con tu cuenta `bedojose13`.
2. Nombre del repo: `zonamed-analytics` (o el que prefieras). Déjalo **público** (Render y
   Streamlit Cloud gratis funcionan mejor/más simple con repos públicos) y NO marques "Add
   README" (ya tenemos uno).
3. Copia la URL que te da GitHub (algo como `https://github.com/bedojose13/zonamed-analytics.git`).
4. En tu PC, dentro de `zonamed-analytics/`, corre:

```powershell
git remote add origin https://github.com/bedojose13/zonamed-analytics.git
git push -u origin main
```

La primera vez te pedirá iniciar sesión — se abrirá el navegador para autenticarte con GitHub
(o te pedirá un Personal Access Token si usas HTTPS con usuario/clave). Sigue las instrucciones
en pantalla.

---

## 2. Base de datos: Neon (Postgres gratis, sin expiración)

1. Entra a [neon.tech](https://neon.tech) y crea una cuenta gratis (puedes usar tu GitHub).
2. "New Project" → nómbralo `zonamed` → región cualquiera cercana → crear.
3. En el dashboard del proyecto, copia el **Connection string** (algo como
   `postgresql://usuario:clave@ep-xxxx.neon.tech/neondb?sslmode=require`).
4. Guárdalo, lo necesitas en el paso siguiente. (No hace falta crear tablas a mano: la app las
   crea solas al arrancar por primera vez — ver `app/core/bootstrap.py`.)

---

## 3. API: Render (Docker, gratis)

1. Entra a [render.com](https://render.com) y crea una cuenta gratis con GitHub.
2. "New +" → **"Blueprint"** → conecta tu repo `zonamed-analytics`. Render detecta el archivo
   `render.yaml` del repo y propone crear el servicio `zonamed-api` automáticamente.
3. Cuando te pida la variable `ZONAMED_DATABASE_URL`, pega el connection string de Neon del
   paso 2, pero **cambia el prefijo** de `postgresql://` a `postgresql+psycopg://` (el resto
   igual). Ejemplo:
   `postgresql+psycopg://usuario:clave@ep-xxxx.neon.tech/neondb?sslmode=require`
4. Confirma y deja que Render construya la imagen Docker (tarda unos minutos la primera vez).
5. Cuando termine, arriba verás la URL pública del servicio, algo como:
   `https://zonamed-api.onrender.com`
6. Verifica que funciona abriendo `https://zonamed-api.onrender.com/partidos/proximos` en el
   navegador — el primer request puede tardar ~30-60s porque el bootstrap automático siembra
   los datos sintéticos y entrena los modelos contra la base de Neon (solo pasa una vez).

**Nota (plan free de Render):** el servicio "duerme" tras ~15 min sin tráfico y el primer
request tras dormir tarda unos segundos en despertar — normal en el plan gratis, no es un error.

---

## 4. Frontend: Streamlit Community Cloud (gratis)

1. Entra a [share.streamlit.io](https://share.streamlit.io) e inicia sesión con GitHub.
2. "New app" → elige el repo `zonamed-analytics`, branch `main`.
3. **Main file path**: `frontend/Home.py`
4. Antes de desplegar, abre **"Advanced settings"** → sección **Secrets** y pega:
   ```
   ZONAMED_API_URL = "https://zonamed-api.onrender.com"
   ```
   (usa la URL real que te dio Render en el paso 3.5, sin la barra `/` final)
5. Clic en **Deploy**. En 1-2 minutos te da tu URL pública, algo como:
   `https://zonamed-analytics-bedojose13.streamlit.app`

---

## 5. En tu celular Android

1. Abre Chrome y entra a tu URL de Streamlit (`https://....streamlit.app`) — ya funciona con
   datos móviles, sin tocar la PC.
2. Menú (⋮) → **"Agregar a pantalla de inicio"** → le pones nombre (p. ej. "Zonamed") → Agregar.
3. Te queda un ícono en el celular que abre la app a pantalla completa, como una app nativa.

---

## Actualizar la app después de cambios

Cada vez que edites código y quieras publicar los cambios:

```powershell
git add -A
git commit -m "describe el cambio"
git push
```

Render y Streamlit Cloud detectan el push a GitHub y redespliegan solos. Si cambiaste algo del
motor de predicción y quieres forzar un reentrenamiento limpio, borra la base en Neon (o crea
un branch nuevo) — el bootstrap automático la vuelve a poblar y entrenar desde cero.
