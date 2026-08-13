# Imagen de la API (FastAPI) para desplegar en Render u otro host que soporte Docker.
# Se usa Docker (en vez del buildpack nativo de Python del host) para fijar exactamente la
# misma versión de Python usada en desarrollo local, sin depender de qué versiones tenga
# disponibles el proveedor en un momento dado.
FROM python:3.14-slim

WORKDIR /srv

# Dependencias del sistema requeridas por psycopg (driver Postgres) y por compilaciones nativas
# ocasionales de numpy/scipy si no hay wheel exacto disponible para la imagen.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Render inyecta el puerto real en $PORT; localmente por defecto usamos 8000.
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.api.main:app --host 0.0.0.0 --port ${PORT}"]
