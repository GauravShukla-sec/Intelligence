# Architecture

## 1. Discovery summary

The working directory was empty and **Node.js is not installed** in the target
environment; Python 3.13 with Flask, feedparser and pytest is available with
working outbound network. The brief prefers Next.js but explicitly requires that
the app *actually run* in the environment. The deciding constraint is therefore
runtime availability, and the chosen stack is **Python / Flask + SQLite** with a
**zero-build vanilla-JS frontend**. This preserves every functional requirement
(provider-agnostic AI, ingestion pipeline, persistence, full-text search, exports)
without a toolchain the environment cannot provide.

## 2. Component overview

```
run.py                      Entry point (server / --ingest / --seed / --reset)
gsid/
  config.py                 Env-driven config (+ tiny .env parser; no secrets in code)
  taxonomy.py               Controlled vocabularies: regions, categories, scales, tiers
  schema.sql                Full relational schema (all required entities)
  db.py                     sqlite3 wrapper, UTC helpers, audit log, FTS sync/search
  scoring.py                Explainable 0–100 relevance model + rating derivations
  analysis/                 Provider-agnostic AI abstraction
    base.py                   AnalysisInput / AnalysisResult / AnalyzerProtocol
    heuristic.py              Deterministic no-API analyzer (default)
    llm.py                    Anthropic + OpenAI analyzers (lazy, with fallback)
    registry.py               get_analyzer(config) selection
  ingestion/
    connectors.py             Feed registry + RssConnector (public feeds only)
    sanitize.py               HTML strip, prompt-injection defang, URL validation
    dedup.py                  Signatures, Jaccard clustering, circular-report flag
    pipeline.py               fetch -> filter -> cluster -> draft -> store
  store.py                  Draft -> analyze -> score -> persist (shared by demo+live)
  repository.py             Read side: assemble stories, filters, regional watch
  brief.py                  Daily brief assembly (12 sections)
  exports.py                Risk register, corrective action, CSV/JSON, email, etc.
  challenge.py              "Challenge This Analysis" red-team engine
  fixtures.py               Clearly-marked demo scenarios, regulations, quiz, scenario
  seed.py                   Idempotent DB seeding + default preferences
  app.py                    Flask app factory + REST API + security controls
  web/                      Frontend (index.html + static css/js), served by Flask
tests/                      pytest suite
docs/                       This documentation set
```

### Request/data flow

```
                    ┌──────────── demo fixtures ────────────┐
                    │                                        ▼
RSS feeds ──▶ connectors ──▶ sanitize ──▶ dedup/cluster ──▶ StoryDraft
                                                              │
                                            store.save_story  ▼
                                     analyzer.analyze() ─▶ AnalysisResult (signals + sections)
                                              │
                                     scoring.score_relevance() + rating derivations
                                              │
                                              ▼
                                        SQLite (story, claim, citation, …) + FTS
                                              │
                    repository / brief / exports / challenge  ▼
                                              │
                                         Flask JSON API  ──▶  vanilla-JS SPA
```

The **single `store.save_story` code path** is used by both demo fixtures and the
live pipeline, so demo and live data are structurally identical and every claim is
linked to its exact source.

## 3. Data model

Implemented in [`gsid/schema.sql`](../gsid/schema.sql). Entities:

- **story** — top-level clustered development with ratings + JSON analysis/scoring
- **event** — timeline entries (a story has many)
- **claim** — provenance-typed assertion linked to the **exact** `source`
- **citation** — direct links with publication/access times + circular flag
- **source** — publisher with tier (1–4), type, country, ownership/transparency notes
- **narrative** — competing perspectives for narrative comparison
- **regulation** — full lifecycle (rumor→proposal→draft→enacted→effective→enforced)
- **alert** — materialized critical-alert record
- **indicator / action** — monitor indicators + categorized recommended actions
- **region / country** — geography + region mapping
- **organization / site / supplier / route** — asset registers (personalization)
- **preference** — user watchlist/settings
- **saved_item** — saved stories
- **quiz_question / quiz_result / scenario** — learning
- **daily_brief** — assembled brief snapshots
- **audit_log** — transparent trail of automated analysis + manual changes
- **story_fts** — FTS5 full-text index

Internal timestamps are **UTC ISO-8601 `Z` strings**; timezone conversion is a
presentation concern handled in the browser.

## 4. Source-ingestion strategy

1. **Fetch** each enabled feed with a timeout + descriptive User-Agent. Failures
   are logged and skipped (graceful fallback), never fatal.
2. **Relevance pre-filter** — tier-1 official feeds pass automatically; others must
   match the security keyword set (keeps the desk focused, not a news dump).
3. **Cluster** near-duplicate/syndicated coverage across all feeds by token-shingle
   Jaccard similarity; flag likely **circular reporting** (many items, one origin).
4. **Draft** one `StoryDraft` per cluster (lead = highest-tier / richest item),
   refine the category by keyword, attach all cluster members as citations.
5. **Persist** via `store.save_story`, which runs the analyzer, scores, derives
   confidence from source tiers, dedups against existing stories (freshness merge),
   and reindexes FTS.

## 5. Verification & bias-control model

See [METHODOLOGY.md](METHODOLOGY.md) and [BIAS_AND_LIMITATIONS.md](BIAS_AND_LIMITATIONS.md).
Highlights: provenance-typed claims; confidence derived transparently from source
tier + corroboration + primary-source presence; narrative comparison without
mechanical political labels; the automated **Challenge This Analysis** red-team;
and a "show only confirmed facts" filter.

## 6. Security & privacy controls

See [SECURITY_PRIVACY.md](SECURITY_PRIVACY.md). Highlights: retrieved content treated
as untrusted (HTML stripped, injection phrasings defanged, delimited in LLM prompts);
URL/scheme validation; CSP + security headers; in-memory rate limiting; optional
shared-token auth for mutating endpoints; audit log; no secrets in code.

## Testing

`python -m pytest` runs 44 tests across `tests/`:

| File | Focus |
|------|-------|
| `test_scoring.py` | relevance model bounds, weighting, rating + confidence derivation, alert gating |
| `test_dedup.py` | signatures, Jaccard, clustering, dedup keys, circular detection |
| `test_sanitize.py` | HTML stripping, prompt-injection defang, URL validation, truncation |
| `test_store_and_repo.py` | write/read round-trip, **claim→source traceability**, dedup merge, injection neutralization, filters, conflicting/unverified claims |
| `test_exports.py` | risk-register fields + math, CSV parseability, email format, error handling |
| `test_api.py` | all endpoints, brief sections, challenge, search, quiz, saved flow, security headers, auth gating, UTC handling |

Frontend behaviour (rendering of every view, map, modal, challenge, exports, filters,
responsive layout, timezone display) was verified interactively in a browser.
