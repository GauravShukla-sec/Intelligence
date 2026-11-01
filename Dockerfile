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

# Refresh the system trust store on every build.
#
# The desk makes outbound HTTPS to ~25 external feeds through urllib, which on
# Debian validates against /etc/ssl/certs rather than a bundled certifi. The
# base image pins whatever ca-certificates shipped when that tag was built, so
# a distrust decision made afterwards is not picked up by a plain rebuild.
#
# Prompted by the October 2026 eMudhra incident: private keys for eight
# intermediate CAs were derivable from their public certificates (insufficient
# randomness at generation), letting anyone mint certificates that clients
# chaining to the affected roots would accept. Mozilla distrusted them via
# OneCRL on 2026-10-17 and emergency-distrusted emSign ECC Root CA - G3 on
# 2026-10-20; eMudhra revoked all eight on 2026-10-18.
#
# For an intelligence desk the relevant attack is not credential theft but
# input poisoning: an attacker positioned on the network could present a forged
# certificate for a feed host and inject fabricated reporting into the corpus.
RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates && \
    update-ca-certificates && \
    rm -rf /var/lib/apt/lists/*

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
