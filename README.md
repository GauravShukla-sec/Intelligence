# Global Security Intelligence Desk (GSID)

A practical intelligence desk that converts worldwide developments into
**corporate global-security intelligence** — with verification structure,
transparent sourcing, explainable risk scoring, and a direct connection to
day-to-day security, GRC, supply-chain and compliance work.

It is **not** a generic news aggregator. Every development is worked into a
structured template that answers: *what happened, why, what's the evidence,
what's uncertain, how are sources framing it, why it matters to a multinational,
who could be affected, and what a security/risk professional should do next.*

> **Data honesty:** Out of the box the desk runs in **demo mode** with clearly
> labelled illustrative scenarios (`[DEMO]`, `demo.example.org` links, a persistent
> "DEMO DATA" banner). Demo content is **never** presented as current news. Live
> RSS ingestion from public, legally-accessible feeds is opt-in.

---

## Why this stack

The reference environment has **no Node.js**, but Python 3.13 + Flask are
available. The app is therefore built as a **Python / Flask + SQLite**
application with a **zero-build, vanilla-JS** frontend. It runs with no
external services and no API keys. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
for the full rationale and design.

- **Backend:** Flask, SQLite (stdlib `sqlite3`, WAL), FTS5 full-text search.
- **Ingestion:** modular connectors, `feedparser` for RSS/Atom.
- **AI analysis:** provider-agnostic abstraction — **heuristic (default, no key)**,
  Anthropic, or OpenAI — behind one interface.
- **Frontend:** responsive, accessible SPA (no framework, no build step).
- **Tests:** `pytest` (44 tests).

---

## Quick start

```bash
# 1. (optional) create a virtualenv
python -m venv .venv && source .venv/bin/activate

# 2. install dependencies (Flask + feedparser + pytest)
pip install -r requirements.txt

# 3. copy the environment template (all placeholders; safe defaults)
cp .env.example .env

# 4. run — seeds demo data automatically on first start
python run.py
```

Open **http://127.0.0.1:8000**. You'll land on the Executive Dashboard with the
demo dataset loaded and the DEMO banner visible.

Useful commands:

```bash
python run.py            # start the web server (demo mode by default)
python run.py --seed     # (re)seed demo data
python run.py --reset    # delete DB then reseed demo data
python run.py --ingest   # run one live ingestion cycle (requires live mode)
python -m pytest         # run the test suite
```

---

## What's included

**Views:** Executive Dashboard · Daily Brief (all 12 sections) · Critical Alerts ·
Stories (with full filter set) · Story Detail (full template) · World/Region map ·
Regional Watch · Regulatory Tracker · Supply-Chain Watch · Cyber-Physical Watch ·
Saved · Learn & Exercise (scenario + adaptive quiz) · Transparency & Audit ·
Watchlist & Settings · Search.

**Per-story intelligence template:** headline, location, category, event/verified
times, status, **relevance score (0–100 with per-dimension rationale)**, urgency,
impact, likelihood, velocity, confidence, trend; what happened; verified facts;
claims & uncertainties (**provenance-typed**: fact / official claim / witness /
analyst judgment / inference / forecast / scenario / rumor / disinformation);
background; **narrative comparison**; why it matters globally; **why this matters to
your work**; potentially affected (countries, functions, infrastructure); **risk
pathway**; indicators to monitor; **questions you should ask today**; recommended
actions (Monitor / Validate / Assess / Communicate / Mitigate / Escalate); and
**sources with tiers, links, publication + access times, and circular-reporting flags.**

**Interactivity:** clickable map, expandable analysis, timeline, competing-narrative
comparison, score-explanation bars, **"Challenge This Analysis"** red-team,
"Show only confirmed facts", scenario exercise, adaptive quiz, and one-click
**exports**: risk-register entry, corrective action, executive summary, travel note,
email-to-leadership, Power BI-friendly CSV/JSON.

---

## Enabling live data

Demo mode never touches the network. To ingest **real, public** feeds:

```bash
# in .env
GSID_DATA_MODE=hybrid          # demo + live side by side (or "live" for live only)
GSID_ENABLED_FEEDS=            # blank = all default feeds, or a comma-separated allowlist
```

```bash
python run.py --ingest         # one cycle from the command line
# or click "Run live ingestion now" in Watchlist & Settings
```

The built-in registry (see [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md)) includes
public feeds from the UN, WHO, USGS, GDACS, ReliefWeb, BBC, Al Jazeera, DW,
France 24, The Guardian, The Hindu, SCMP, CISA, UK FCDO travel advice and more.
The fetcher sends a descriptive User-Agent, honours timeouts, and **does not bypass
paywalls, CAPTCHAs, authentication or robots restrictions.** You are responsible for
confirming each feed's terms of use in your jurisdiction.

To use a model-backed analyzer instead of the heuristic one:

```bash
GSID_AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-...            # pip install anthropic
# or
GSID_AI_PROVIDER=openai
OPENAI_API_KEY=sk-...               # pip install openai
```

If the key is missing or the SDK errors, the desk **automatically falls back** to
the heuristic analyzer — it never hard-fails on a missing credential.

---

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — components, data model, pipeline.
- [Methodology](docs/METHODOLOGY.md) — risk-scoring model + source-quality model.
- [Bias & Limitations](docs/BIAS_AND_LIMITATIONS.md) — honest statement of limits.
- [Security & Privacy](docs/SECURITY_PRIVACY.md) — controls and guidance.
- [Data Sources](docs/DATA_SOURCES.md) — configuring & adding connectors.
- [User Guide](docs/USER_GUIDE.md) — how a security professional uses each view.

---

## Testing

```bash
python -m pytest
```

Covers: risk scoring, dedup/clustering, sanitization & prompt-injection defense,
URL validation, store/read round-trips, **claim-to-source traceability**, dedup
merge, filtering, exports, the full HTTP API, brief assembly, challenge engine,
auth gating, security headers, and UTC/timezone handling. See
[docs/ARCHITECTURE.md#testing](docs/ARCHITECTURE.md#testing).

## License / status

Reference implementation. Review the bias, security and data-source docs before
any production use, and replace the demo dataset with configured live sources.
