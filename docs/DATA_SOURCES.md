# Data-source configuration

## Modes

`GSID_DATA_MODE` controls what the desk serves:

| Mode | Behaviour |
|------|-----------|
| `demo` (default) | Only clearly-labelled demo fixtures. No network. Ingestion disabled. |
| `live` | Live-ingested stories only. |
| `hybrid` | Demo fixtures **and** live stories side by side. |

## Enabling live ingestion

```bash
# .env
GSID_DATA_MODE=hybrid
GSID_ENABLED_FEEDS=            # blank = all feeds with enabled_by_default=True
GSID_INGEST_INTERVAL_MINUTES=30
GSID_FETCH_TIMEOUT_SECONDS=15
```

Run a cycle:

```bash
python run.py --ingest         # CLI
```

or use **Watchlist & Settings → Run live ingestion now** in the UI (rate-limited by
`GSID_INGEST_INTERVAL_MINUTES`).

### Auto-refresh (scheduling)

There are two ways to make the desk refresh itself. Neither is on by default.

**Option A — built-in scheduler (simplest).** While the server is running, ingest
automatically every N hours. Set:

```bash
GSID_DATA_MODE=hybrid          # or live
GSID_INGEST_EVERY_HOURS=24     # daily; use 6 for four times a day, etc. (0 = off)
python run.py
```

The app runs one cycle ~20s after startup, then every N hours, logging each run and
recording it in the audit log (`scheduled_ingest`). This only runs while the server
process is up, so pair it with a process manager (or systemd/launchd) that keeps the
server running and restarts it on reboot.

**Option B — OS scheduler (survives reboots without the web server).** Wrap
`python run.py --ingest` in cron / a systemd timer / macOS launchd, e.g. every 30
minutes:

```
*/30 * * * *  cd /path/to/app && GSID_DATA_MODE=hybrid /path/to/python run.py --ingest >> ingest.log 2>&1
```

On macOS, a `launchd` `.plist` with `StartCalendarInterval` gives you a reliable daily
run even across reboots.

## Built-in feed registry

Defined in [`gsid/ingestion/connectors.py`](../gsid/ingestion/connectors.py). Each
feed has an id, tier, source type, country, region hint, category hint, and an
`enabled_by_default` flag. A representative selection:

| id | Source | Tier | Region hint |
|----|--------|-----:|-------------|
| `un_news` | UN News | 1 | global |
| `who_news` | WHO — News (health emergencies & outbreaks) | 1 | global |
| `usgs_quakes` | USGS significant earthquakes | 1 | global |
| `gdacs` | GDACS disaster alerts | 1 | global |
| `reliefweb` | ReliefWeb (UN OCHA) — currently Cloudflare-blocked | 1 | global |
| `cisa_alerts` | CISA cyber advisories | 1 | north_america |
| `eu_presscorner` | European Commission press releases (EU sanctions/NIS2/CER/trade) | 1 | europe |
| `us_fedreg_dhs` | US Federal Register — Homeland Security rules (CTPAT/customs/sanctions) | 1 | north_america |
| `gov_uk_travel` | UK FCDO travel advice (per-destination) | 1 | global |
| `us_state_travel` | US State Dept travel advisories (per-destination) | 1 | global |
| `bbc_world` | BBC World | 2 | global |
| `aljazeera` | Al Jazeera English | 2 | mena |
| `dw_world` | Deutsche Welle | 2 | europe |
| `france24` | France 24 | 2 | europe |
| `guardian_world` | The Guardian | 2 | global |
| `npr_world` | NPR World | 2 | global |
| `thehindu` | The Hindu | 2 | south_asia |
| `scmp` | South China Morning Post | 2 | east_asia |
| `batimes` | Buenos Aires Times | 3 | latam_caribbean |
| `allafrica` | AllAfrica (pan-African aggregator) | 3 | subsaharan_africa |

> Feed URLs are maintained against live endpoints. Government/regulator RSS
> endpoints change often; retired feeds (ENISA, OFAC recent-actions, WHO DON,
> The East African) were replaced with live equivalents. `reliefweb` currently
> returns a bot-challenge (HTTP 202) and fails gracefully — GDACS and WHO cover
> the same disaster/health ground until it recovers.

Enable a specific subset:

```bash
GSID_ENABLED_FEEDS=un_news,usgs_quakes,bbc_world,aljazeera,cisa_alerts
```

## Adding a feed

Append a `FeedDef` to `FEED_REGISTRY`:

```python
FeedDef(
    "my_feed", "My Regional Outlet", "https://example.org/rss",
    tier=3, source_type="newspaper", country="ng",
    region_hint="subsaharan_africa", category_hint="geopolitical",
    ownership="…", transparency="…", enabled_by_default=False,
)
```

## Adding a non-RSS connector (official API / compliant search)

Implement the `Connector` protocol — a class with `fetch() -> list[FeedItem]` — and
call it from the pipeline. This is where you would integrate an official government
API or a **compliant** web-search provider. Keep to public, permissible data; do not
bypass access controls.

## Legal & ethical notes

- The fetcher identifies itself with a descriptive User-Agent and honours timeouts.
- Only public feeds intended for syndication are included by default. **You** must
  confirm each feed's terms of use and robots policy in your jurisdiction.
- The desk never bypasses paywalls, CAPTCHAs, authentication or robots restrictions,
  and never uses stolen, leaked or unlawfully obtained content.
