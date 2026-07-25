# Hosting for a solo student (free, no IT team)

Three ways to share the desk, easiest first. All are free.

---

## Quick share from your laptop (Cloudflare Tunnel)

No account, no signup. Gives a temporary public link while your Mac is on and
the command is running. Great for showing a friend or professor.

1. Download the single binary (Apple Silicon shown; use `-amd64` on Intel):
   ```bash
   curl -L -o cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-arm64 && chmod +x cloudflared
   ```
2. Make sure the desk is running locally (it already is at http://127.0.0.1:8000).
3. Start the tunnel:
   ```bash
   ./cloudflared tunnel --url http://localhost:8000
   ```
4. It prints a `https://<random>.trycloudflare.com` link — share that.
   Stop it with **Ctrl+C**. The link changes each run.

> ⚠️ Your **local** desk runs in full-control mode, so anyone with the link
> could change settings. For public sharing, run it read-only first (see the
> bottom of this file) or just use it for quick, trusted demos.

---

## Always-on free hosting — Render (recommended)

A permanent `https://yourapp.onrender.com` link that works even when your
laptop is off. Free tier sleeps when idle and wakes on the next visit (~30s).

1. Put this project in a **GitHub repo** (see "Push to GitHub" below).
2. Go to **render.com** → sign up with GitHub (free).
3. **New → Blueprint** → pick your repo. Render reads `render.yaml` and fills
   everything in (public read-only, daily refresh, auto-generated secrets).
4. Click **Apply**. First build takes a few minutes; then you get your URL.
5. To edit settings on the hosted site, get your **admin token**: Render
   dashboard → your service → **Environment** → reveal `GSID_ADMIN_TOKEN`.
   Paste it in the desk under **Settings → Unlock admin**.

Storage is ephemeral on the free plan — fine, because the desk re-seeds demo
data and re-ingests live feeds automatically.

---

## Always-on free hosting — Hugging Face Spaces

Also free, no credit card, very student-friendly.

1. Go to **huggingface.co** → sign up → **New Space**.
2. Space SDK: **Docker** (blank template). Visibility: Public.
3. Push this repo's files into the Space (via git, or the web uploader).
4. Open the Space's `README.md` and paste the metadata block from
   [`deploy/huggingface-space-README.md`](../deploy/huggingface-space-README.md)
   at the very top (it sets `sdk: docker` and `app_port: 8000`).
5. In the Space **Settings → Variables and secrets**, add:
   - `GSID_DATA_MODE = hybrid`
   - `GSID_INGEST_EVERY_HOURS = 24`
   - `GSID_PUBLIC_READONLY = true`
   - `GSID_PUBLIC_ALLOW_REFRESH = true`
   - `GSID_DB_PATH = /tmp/gsid.sqlite3`  ← keeps the DB in a writable dir
   - `GSID_ADMIN_TOKEN = <a long random string>` (secret)
   - `GSID_SECRET_KEY = <a long random string>` (secret)
6. The Space builds and serves at `https://huggingface.co/spaces/<you>/<name>`.

Generate a random token/secret:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## Push to GitHub (needed for Render / HF-via-git)

From the project folder:
```bash
git init && git add -A && git commit -m "Global Security Intelligence Desk"
```
Then create an empty repo on github.com and follow its "push an existing
repository" lines. The included `.gitignore` keeps `.env`, the local database,
and logs out of the repo.

> Never commit a real `.env`. Set secrets in the host's dashboard instead.

---

## Make the shared version safe (read-only)

For anything you share widely, run in **public read-only** mode so visitors
can view + refresh but not change your settings. Render and Hugging Face above
already set this. To do it locally too, add to `.env`:
```
GSID_PUBLIC_READONLY=true
GSID_PUBLIC_ALLOW_REFRESH=true
GSID_ADMIN_TOKEN=your-long-random-token
```
See [`docs/DEPLOYMENT.md`](DEPLOYMENT.md) for the full reference.
