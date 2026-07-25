# Global Security Intelligence Desk — production image
FROM python:3.12-slim

# Runtime env: no .pyc, unbuffered logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GSID_ENV=production \
    GSID_HOST=0.0.0.0 \
    GSID_PORT=8000 \
    GSID_DB_PATH=/data/gsid.sqlite3

WORKDIR /app

# Install dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App source
COPY . .

# Persistent data dir (mount a volume here so the SQLite DB survives restarts)
RUN mkdir -p /data && \
    addgroup --system gsid && adduser --system --ingroup gsid gsid && \
    chown -R gsid:gsid /app /data
USER gsid
VOLUME ["/data"]

EXPOSE 8000

# Container-level healthcheck hits the app's health endpoint (respects $PORT).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request,sys; p=os.environ.get('PORT','8000'); sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{p}/api/health',timeout=4).status==200 else 1)"

# Single worker + threads so the in-process daily refresh scheduler runs once.
# Shell form so ${PORT} (set by Render / Cloud Run / etc.) expands; defaults to 8000.
CMD gunicorn --workers 1 --threads 8 --timeout 120 --bind 0.0.0.0:${PORT:-8000} wsgi:app
