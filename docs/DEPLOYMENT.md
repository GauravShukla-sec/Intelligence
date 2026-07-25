# Deployment Guide — public, read-only desk

This guide gets the Global Security Intelligence Desk online so **anyone can
open it, browse, and refresh** the data — while **settings and watchlists stay
locked** behind an admin token.

- View + refresh: open to everyone.
- Change settings / watchlist / feeds: requires the **admin token**.
- Saved stories & quiz progress: private to each visitor's browser (localStorage).

---

## 1. The access model (how "no other rights" works)

Set these environment variables:

| Variable | Value | Effect |
|----------|-------|--------|
| `GSID_PUBLIC_READONLY` | `true` | Locks all config writes behind the admin token |
| `GSID_ADMIN_TOKEN` | *(long random string)* | Unlocks editing when entered in Settings → "Unlock admin" |
| `GSID_PUBLIC_ALLOW_REFRESH` | `true` | Lets any visitor trigger a refresh (rate-limited). Set `false` for view-only |
| `GSID_DATA_MODE` | `hybrid` or `live` | Enables real feeds |
| `GSID_INGEST_EVERY_HOURS` | `24` | Auto-refresh once a day so data stays current with no clicks |

Visitors see a 🔒 "public read-only" banner in Settings. An admin pastes the
token under **Settings → Admin access → Unlock admin** to edit.

Generate a strong admin token:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## 2. Run it with Docker (works anywhere)

The repo ships a `Dockerfile` and `docker-compose.yml` preconfigured for the
public read-only mode.

```bash
# 1. Edit docker-compose.yml — set GSID_SECRET_KEY and GSID_ADMIN_TOKEN.
# 2. Build and start:
docker compose up -d --build
# 3. Open http://localhost:8000
```

The SQLite database is stored in a named volume (`gsid-data`) so it survives
restarts. Logs: `docker compose logs -f`. Stop: `docker compose down`.

Build/run the image directly (no compose):
```bash
docker build -t gsid:latest .
docker run -d -p 8000:8000 -v gsid-data:/data \
  -e GSID_SECRET_KEY="$(python -c 'import secrets;print(secrets.token_urlsafe(32))')" \
  -e GSID_DATA_MODE=hybrid -e GSID_INGEST_EVERY_HOURS=24 \
  -e GSID_PUBLIC_READONLY=true -e GSID_PUBLIC_ALLOW_REFRESH=true \
  -e GSID_ADMIN_TOKEN="your-admin-token" \
  --name gsid gsid:latest
```

---

## 3. Put it on the internet

Pick the host that matches your environment. All of them just run the Docker
image above.

### Azure — best fit for a Microsoft enterprise
**Azure Container Apps** (simplest) or **App Service for Containers**. Your
IT/cloud team runs this; it also goes through their security review because the
app makes outbound calls to public news/gov RSS feeds.

```bash
# Build & push to Azure Container Registry, then create a Container App.
az acr build --registry <ACR_NAME> --image gsid:latest .

az containerapp create \
  --name gsid --resource-group <RG> --environment <ACA_ENV> \
  --image <ACR_NAME>.azurecr.io/gsid:latest \
  --target-port 8000 --ingress external \
  --min-replicas 1 --max-replicas 1 \
  --env-vars GSID_ENV=production GSID_DATA_MODE=hybrid \
             GSID_INGEST_EVERY_HOURS=24 GSID_PUBLIC_READONLY=true \
             GSID_PUBLIC_ALLOW_REFRESH=true \
             GSID_SECRET_KEY=secretref:secret-key \
             GSID_ADMIN_TOKEN=secretref:admin-token
```
- Keep **min & max replicas = 1** (single instance) because the SQLite DB and
  the in-process refresh scheduler assume one process. For multiple replicas,
  switch to a shared database and disable the in-process scheduler
  (`GSID_INGEST_EVERY_HOURS=0`) — see §4.
- Persist `/data` with an **Azure Files** mount so the DB survives restarts.
- Store `GSID_SECRET_KEY` / `GSID_ADMIN_TOKEN` as Container App **secrets**.

### Fly.io / Render / Railway (quick public URL)
Any container host works. Attach a persistent volume/disk mounted at `/data`,
set the env vars from §1, expose port 8000.

### A plain VM (Ubuntu, etc.)
Install Docker, copy the repo, `docker compose up -d --build`, then put Nginx or
Caddy in front for HTTPS. Example Caddyfile:
```
desk.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

---

## 4. Scaling beyond one instance (optional)

The default single-instance setup is intentional and fine for a team-sized
audience. To run multiple replicas behind a load balancer:

1. Move off SQLite to a shared database (e.g. Postgres). The data layer is
   isolated in `gsid/db.py` + `gsid/repository.py` + `gsid/store.py`.
2. Set `GSID_INGEST_EVERY_HOURS=0` and run ingestion as a **separate scheduled
   job** (one container/cron calling `python run.py --ingest`), so only one
   process writes new stories.

---

## 5. Security checklist before going public

- [ ] Set a strong, unique `GSID_SECRET_KEY` and `GSID_ADMIN_TOKEN`.
- [ ] Serve over **HTTPS** (host platform or a reverse proxy). The app already
      sends a strict Content-Security-Policy, `X-Frame-Options: DENY`, and
      `nosniff`.
- [ ] Keep `GSID_PUBLIC_READONLY=true` so visitors can't change shared config.
- [ ] Decide on `GSID_PUBLIC_ALLOW_REFRESH` (rate-limited; set `false` for
      strictly view-only and rely on the daily auto-refresh).
- [ ] Mount a persistent volume at `/data`.
- [ ] Review the outbound feed list in `gsid/ingestion/connectors.py` against
      your organisation's egress policy.
