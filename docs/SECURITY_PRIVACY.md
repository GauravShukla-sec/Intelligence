# Security & privacy

## Handling of retrieved content (prompt-injection & untrusted data)

Retrieved web/RSS content is treated as **untrusted data, never as instructions**:

- HTML/markup and `<script>`/`<style>` blocks are stripped (`ingestion/sanitize.py`).
- Common prompt-injection phrasings ("ignore previous instructions", "system prompt",
  fake role tags, "reveal your API key", …) are **defanged** to
  `[neutralized-instruction]` before any analyzer sees the text; the count is audit-logged.
- Model-backed analyzers additionally wrap story text in a delimited
  `<UNTRUSTED_CONTENT>` block with an explicit instruction to treat it as data only.
- Over-long content is truncated to a bounded length.

## Input / output validation

- **URL validation:** only `http`/`https` with a plausible host are accepted; others
  are rejected before storage or display (blocks `javascript:` and similar).
- Citation and source URLs open with `rel="noopener noreferrer"` and `target="_blank"`.
- API responses are JSON; the SPA builds DOM via `textContent`/typed helpers (no
  `innerHTML` interpolation of untrusted values), reducing XSS risk.

## HTTP security controls

- **Security headers** on every response: `Content-Security-Policy` (self-only
  scripts/styles/connections, `frame-ancestors 'none'`), `X-Content-Type-Options`,
  `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Permissions-Policy`.
- **Rate limiting:** in-memory sliding window per IP for the API (240/min) and a
  separate, configurable window for the outbound ingestion trigger.
- **Authentication (optional):** set `GSID_AUTH_ENABLED=true` + `GSID_ACCESS_TOKEN`
  to require a shared token (`X-GSID-Token`) on mutating endpoints (preferences,
  saved items, ingestion). For multi-user deployments, replace with a real identity
  provider and per-user rows.

## Secrets

- **No secrets in code.** All configuration comes from environment variables (or a
  local `.env`, git-ignored). `.env.example` contains **placeholders only**.
- API keys for optional AI providers are read from the environment and never logged
  or returned by the API. Internal prompts are not exposed via the API.

## Privacy & data minimization

- The desk collects only public, security-relevant information from configured feeds.
- It does **not** collect personal data unrelated to legitimate security analysis and
  must not be used to profile individuals by protected characteristics.
- Watchlist/site/supplier data you enter is stored locally in SQLite; treat that DB as
  sensitive and protect it accordingly (filesystem permissions, backups, encryption at
  rest per your policy).

## Audit trail

Automated analysis and manual changes are recorded in the `audit_log` table and
viewable under **Transparency & Audit** (actor, action, entity, timestamp, detail).

## Production hardening checklist

- Run behind a production WSGI server (e.g. gunicorn) + TLS-terminating reverse proxy.
- Set a strong `GSID_SECRET_KEY`, `GSID_ENV=production`, and enable auth.
- Move rate limiting to a shared store (e.g. Redis) if running multiple workers.
- Restrict outbound network egress to your approved feed hosts.
- Confirm the terms of use / robots policy for every feed you enable.
