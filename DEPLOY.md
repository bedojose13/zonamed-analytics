# Desplegar Zonamed Analytics en la nube (gratis) — acceso desde el celular sin la PC

Esta guía deja la app accesible desde cualquier lugar con datos móviles, en una URL fija, sin
necesidad de que tu PC esté encendida. Usa 4 servicios gratuitos: **Neon** (Postgres),
**Render** (API FastAPI), **Streamlit Community Cloud** (frontend) y **API-Football** (datos
reales de la Dimayor, temporada 2024 — el plan gratuito no cubre la temporada en curso).

---

## 1. Crear el repositorio en GitHub

1. Entra a [github.com/new](https://github.com/new) con tu cuenta `bedojose13`.
2. Nombre del repo: `zonamed-analytics` (o el que prefieras). Déjalo **público**.
3. En tu PC, dentro de `zonamed-analytics/`:

```powershell
git remote add origin https://github.com/bedojose13/zonamed-analytics.git
git push -u origin main
```

---

## 2. Base de datos: Neon (Postgres gratis, sin expiración)

1. Entra a [neon.tech](https://neon.tech), crea cuenta gratis, "New Project" → `zonamed`.
2. Copia el **Connection string** (`postgresql://usuario:clave@ep-xxxx.neon.tech/neondb?sslmode=require`).
3. No hace falta crear tablas a mano: la app las crea solas al arrancar.

---

## 3. Datos reales: API-Football (gratis)

1. Entra a [dashboard.api-football.com/register](https://dashboard.api-football.com/register)
   y crea cuenta gratis.
2. Copia tu **API Key** del dashboard.
3. **Importante — límite real:** el plan gratis da 100 llamadas/día y 10 llamadas/minuto, y
   **no cubre la temporada en curso** (solo 2022-2024). La app usa la temporada 2024 completa
   como base histórica real — ver `app/scripts/sync_real_data.py` para el detalle de por qué y
   cómo se reparte el backfill en varios días.

---

## 4. API: Render (Docker, gratis)

1. Entra a [render.com](https://render.com), crea cuenta gratis con GitHub.
2. "New +" → **"Blueprint"** → conecta tu repo. Render detecta `render.yaml` y propone el
   servicio `zonamed-api`.
3. Completa las variables de entorno que pide (todas con `sync: false`, o sea las pegas tú):
   - `ZONAMED_DATABASE_URL`: el connection string de Neon, pero con el prefijo cambiado a
     `postgresql+psycopg://` (no `postgresql://`). Ejemplo:
     `postgresql+psycopg://usuario:clave@ep-xxxx.neon.tech/neondb?sslmode=require`
   - `ZONAMED_FOOTBALL_API_KEY`: tu API key de API-Football del paso 3.
   - `ZONAMED_ADMIN_SYNC_TOKEN`: inventa cualquier texto secreto (ej. una contraseña larga
     aleatoria) — lo vas a necesitar en el paso 6 para el cron.
4. Confirma y deja que Render construya la imagen Docker (unos minutos la primera vez).
5. Copia la URL pública que te da, algo como `https://zonamed-api.onrender.com`.
6. Verifica entrando a esa URL en el navegador — el campo `bootstrap.stage` te dice en qué va
   (`"syncing"` mientras trae equipos/calendario/estadísticas reales, `"training"` mientras
   entrena, `"ready"` cuando termina esta corrida). Es normal que en cada arranque avance solo
   un poco más del backfill histórico (limitado por el cupo diario de la API).

**Nota (plan free de Render):** el servicio "duerme" tras ~15 min sin tráfico; el primer
request tras dormir tarda unos segundos en despertar — normal, no es un error. Cada vez que
despierta, también avanza un poco más el backfill (por eso conviene el cron del paso 6).

---

## 5. Frontend: Streamlit Community Cloud (gratis)

1. Entra a [share.streamlit.io](https://share.streamlit.io), inicia sesión con GitHub.
2. "New app" → tu repo, branch `main`, **Main file path**: `frontend/Home.py`.
3. "Advanced settings" → **Secrets**:
   ```
   ZONAMED_API_URL = "https://zonamed-api.onrender.com"
   ```
4. Deploy. Te da tu URL pública, algo como `https://zonamed-analytics-....streamlit.app`.
5. **Importante**: en la configuración de la app (⋮ → Settings → Sharing), verifica que esté
   marcada como **"Public"** — si no, pide iniciar sesión para verla.

---

## 6. Cron gratuito para avanzar el backfill todos los días (GitHub Actions)

El backfill histórico de córners/tarjetas por partido avanza solo cada vez que el servicio de
Render arranca (incluida cada vez que despierta de dormir), pero si nadie visita la app en un
día, ese día no avanza. Este repo ya trae un workflow (`.github/workflows/sync-cron.yml`) que
llama a `POST /admin/sync` una vez al día automáticamente, gratis, sin depender de visitas:

1. En GitHub, entra al repo → **Settings** → **Secrets and variables** → **Actions**.
2. Agrega dos "New repository secret":
   - `ZONAMED_API_URL` = `https://zonamed-api.onrender.com` (tu URL real de Render, sin `/` final)
   - `ZONAMED_ADMIN_SYNC_TOKEN` = el mismo texto secreto que pusiste en Render en el paso 4.
3. Listo — corre solo todos los días a las 13:00 UTC. Para probarlo ya mismo sin esperar: pestaña
   **Actions** del repo → "Sync diario de datos reales" → **Run workflow**.

---

## 7. En tu celular Android

1. Abre Chrome y entra a tu URL de Streamlit — funciona con datos móviles, sin tocar la PC.
2. Menú (⋮) → **"Agregar a pantalla de inicio"**.

---

## Nota sobre "Próximos Partidos"

Como la app usa la temporada **2024 completa** (ya terminada) en vez de la temporada en curso
(bloqueada en el plan gratuito de la API), **todos** los partidos están FINALIZADOS — la vista
"Próximos Partidos" quedará vacía siempre con este dataset, y eso es esperado, no un error. La
vista útil para auditar el motor con datos 100% reales es **"Partidos Jugados"** (real vs.
proyectado). Si más adelante quieres partidos realmente futuros, hay que pasar al plan pago de
API-Football (cubre la temporada en curso) — avísame si llegas a ese punto.

---

## Actualizar la app después de cambios

```powershell
git add -A
git commit -m "describe el cambio"
git push
```

Render y Streamlit Cloud redespliegan solos con cada push. Si cambias el schema de la base de
datos (nuevas columnas/tablas), borra y recrea las tablas en Neon antes del siguiente deploy —
avísame y te ayudo con ese paso puntual, no conviene automatizarlo sin confirmarlo primero.
