-- Global Security Intelligence Desk — relational schema (SQLite)
-- Internal timestamps are ISO-8601 UTC strings (see db.utcnow()).
-- The model links Claims to the exact Source supporting/disputing them, and a
-- Story aggregates multiple Events, Claims, Citations and a Risk assessment.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- Regions & countries -----------------------------------------------------
CREATE TABLE IF NOT EXISTS region (
    id   TEXT PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS country (
    code      TEXT PRIMARY KEY,   -- ISO alpha-2, lowercase
    name      TEXT NOT NULL,
    region_id TEXT REFERENCES region(id)
);

-- Sources & citations -----------------------------------------------------
CREATE TABLE IF NOT EXISTS source (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,        -- publisher / organisation
    url           TEXT,                 -- home / feed url
    tier          INTEGER NOT NULL DEFAULT 3,  -- 1..4
    source_type   TEXT,                 -- government|wire|newspaper|regulator|ngo|social|...
    country       TEXT,                 -- publisher country (ISO-2)
    language      TEXT DEFAULT 'en',
    ownership     TEXT,                 -- ownership / funding note for transparency
    transparency  TEXT,                 -- methodology / transparency note
    is_demo       INTEGER NOT NULL DEFAULT 0
);

-- Stories (top-level clustered development) --------------------------------
CREATE TABLE IF NOT EXISTS story (
    id                TEXT PRIMARY KEY,
    headline          TEXT NOT NULL,
    summary           TEXT,                 -- "What happened"
    category          TEXT NOT NULL,        -- taxonomy category id
    primary_region    TEXT,                 -- region id
    primary_country   TEXT,                 -- ISO-2
    location_text     TEXT,                 -- human-readable location
    lat               REAL,
    lon               REAL,

    event_time        TEXT,                 -- UTC ISO; when the event occurred
    first_seen        TEXT NOT NULL,        -- UTC ISO; when we first ingested it
    last_updated      TEXT NOT NULL,        -- UTC ISO; last material update
    status            TEXT,                 -- developing|ongoing|contained|resolved|...

    -- Ratings (see scoring.py; every value is explained in *_rationale)
    relevance_score   INTEGER NOT NULL DEFAULT 0,
    urgency           TEXT,
    geo_scope         TEXT,
    impact            TEXT,
    likelihood        TEXT,
    velocity          TEXT,
    confidence        TEXT,
    trend             TEXT,

    is_alert          INTEGER NOT NULL DEFAULT 0,  -- surfaced in Critical Alerts
    is_demo           INTEGER NOT NULL DEFAULT 0,
    dedup_key         TEXT,                 -- normalized clustering key

    -- Travel-advisory consensus (normalized 1..4 across governments; 0 = n/a)
    advisory_level    INTEGER NOT NULL DEFAULT 0,  -- worst-case level across sources
    advisory_json     TEXT,                 -- {consensus,lowest,spread,diverges,sources[]}

    analysis_json     TEXT,                 -- structured AI/heuristic analysis blob
    scoring_json      TEXT                  -- per-dimension score breakdown + rationale
);
CREATE INDEX IF NOT EXISTS idx_story_category ON story(category);
CREATE INDEX IF NOT EXISTS idx_story_region ON story(primary_region);
CREATE INDEX IF NOT EXISTS idx_story_updated ON story(last_updated);
CREATE INDEX IF NOT EXISTS idx_story_dedup ON story(dedup_key);

-- Story <-> country (many-to-many, "potentially affected") -----------------
CREATE TABLE IF NOT EXISTS story_country (
    story_id TEXT NOT NULL REFERENCES story(id) ON DELETE CASCADE,
    country  TEXT NOT NULL,
    PRIMARY KEY (story_id, country)
);

-- Events (a story has one or more events; a timeline) ----------------------
CREATE TABLE IF NOT EXISTS event (
    id         TEXT PRIMARY KEY,
    story_id   TEXT NOT NULL REFERENCES story(id) ON DELETE CASCADE,
    occurred   TEXT,                 -- UTC ISO
    title      TEXT NOT NULL,
    detail     TEXT,
    ordinal    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_event_story ON event(story_id);

-- Claims (each linked to the exact source; provenance-typed) ---------------
CREATE TABLE IF NOT EXISTS claim (
    id            TEXT PRIMARY KEY,
    story_id      TEXT NOT NULL REFERENCES story(id) ON DELETE CASCADE,
    text          TEXT NOT NULL,
    claim_type    TEXT NOT NULL DEFAULT 'fact',   -- taxonomy.CLAIM_TYPES
    attributed_to TEXT,                            -- who is making the claim
    stance        TEXT NOT NULL DEFAULT 'supports',-- supports|disputes|contextualizes
    corroboration TEXT,                            -- none|single|multiple|primary
    source_id     TEXT REFERENCES source(id),      -- the EXACT source
    confidence    TEXT
);
CREATE INDEX IF NOT EXISTS idx_claim_story ON claim(story_id);

-- Citations (direct links backing claims / the story) ----------------------
CREATE TABLE IF NOT EXISTS citation (
    id            TEXT PRIMARY KEY,
    story_id      TEXT NOT NULL REFERENCES story(id) ON DELETE CASCADE,
    claim_id      TEXT REFERENCES claim(id) ON DELETE CASCADE,
    source_id     TEXT REFERENCES source(id),
    title         TEXT,
    url           TEXT NOT NULL,
    published_at  TEXT,                 -- UTC ISO (publication time)
    accessed_at   TEXT,                 -- UTC ISO (when we retrieved it)
    orig_language TEXT DEFAULT 'en',
    orig_headline TEXT,                 -- retained for multilingual sources
    is_primary    INTEGER NOT NULL DEFAULT 0,
    is_circular   INTEGER NOT NULL DEFAULT 0,  -- flagged as circular/syndicated
    advisory_level INTEGER NOT NULL DEFAULT 0  -- this govt's normalized 1..4 (0 = n/a)
);
CREATE INDEX IF NOT EXISTS idx_citation_story ON citation(story_id);

-- Narrative comparison (competing perspectives on the same story) ----------
CREATE TABLE IF NOT EXISTS narrative (
    id          TEXT PRIMARY KEY,
    story_id    TEXT NOT NULL REFERENCES story(id) ON DELETE CASCADE,
    label       TEXT NOT NULL,        -- e.g. "Source Group A"
    who         TEXT,                 -- who advances this narrative
    claim       TEXT NOT NULL,        -- the narrative's core assertion
    evidence    TEXT,                 -- evidence offered
    ordinal     INTEGER NOT NULL DEFAULT 0
);

-- Recommended actions ------------------------------------------------------
CREATE TABLE IF NOT EXISTS action (
    id        TEXT PRIMARY KEY,
    story_id  TEXT NOT NULL REFERENCES story(id) ON DELETE CASCADE,
    action_type TEXT NOT NULL,        -- Monitor|Validate|Assess|Communicate|Mitigate|Escalate
    text      TEXT NOT NULL,
    ordinal   INTEGER NOT NULL DEFAULT 0
);

-- Indicators to monitor ----------------------------------------------------
CREATE TABLE IF NOT EXISTS indicator (
    id        TEXT PRIMARY KEY,
    story_id  TEXT NOT NULL REFERENCES story(id) ON DELETE CASCADE,
    text      TEXT NOT NULL,
    direction TEXT,                    -- improvement|deterioration|both
    ordinal   INTEGER NOT NULL DEFAULT 0
);

-- Regulations (D domain) — full lifecycle tracking -------------------------
CREATE TABLE IF NOT EXISTS regulation (
    id             TEXT PRIMARY KEY,
    story_id       TEXT REFERENCES story(id) ON DELETE SET NULL,
    title          TEXT NOT NULL,
    jurisdiction   TEXT NOT NULL,
    framework      TEXT,               -- NIS2|CER|CTPAT|AEO|GDPR|CSDDD|...
    status         TEXT NOT NULL,      -- rumor|proposal|draft|enacted|effective|enforced
    effective_date TEXT,               -- ISO date if known
    affected       TEXT,               -- organisations affected
    obligations    TEXT,               -- key obligations
    reporting      TEXT,               -- reporting timelines
    penalties      TEXT,               -- penalties / enforcement risk
    implications   TEXT,               -- practical implications
    prep_steps     TEXT,               -- recommended preparation
    source_url     TEXT,               -- link to original government/regulatory text
    updated_at     TEXT,
    is_demo        INTEGER NOT NULL DEFAULT 0
);

-- Alerts (materialized critical-alert records) -----------------------------
CREATE TABLE IF NOT EXISTS alert (
    id            TEXT PRIMARY KEY,
    story_id      TEXT NOT NULL REFERENCES story(id) ON DELETE CASCADE,
    people_impact     TEXT,
    facility_impact   TEXT,
    operational_impact TEXT,
    recommended_action TEXT,
    created_at    TEXT
);

-- Organizations, sites, suppliers, routes, assets --------------------------
CREATE TABLE IF NOT EXISTS organization (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT
);
CREATE TABLE IF NOT EXISTS site (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, country TEXT, city TEXT,
    lat REAL, lon REAL, criticality TEXT, site_type TEXT, notes TEXT
);
CREATE TABLE IF NOT EXISTS supplier (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, country TEXT, tier INTEGER,
    category TEXT, notes TEXT
);
CREATE TABLE IF NOT EXISTS route (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, mode TEXT, waypoints TEXT, notes TEXT
);

-- User preferences (single default profile; extend for multi-user) ---------
CREATE TABLE IF NOT EXISTS preference (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- Saved items & watchlist --------------------------------------------------
CREATE TABLE IF NOT EXISTS saved_item (
    id        TEXT PRIMARY KEY,
    story_id  TEXT NOT NULL REFERENCES story(id) ON DELETE CASCADE,
    note      TEXT,
    saved_at  TEXT
);

-- Quiz questions & scenarios ----------------------------------------------
CREATE TABLE IF NOT EXISTS quiz_question (
    id          TEXT PRIMARY KEY,
    question    TEXT NOT NULL,
    options_json TEXT NOT NULL,      -- JSON array of options
    answer_index INTEGER NOT NULL,
    explanation TEXT,
    difficulty  INTEGER NOT NULL DEFAULT 2,  -- 1 easy .. 3 hard
    story_id    TEXT REFERENCES story(id) ON DELETE SET NULL,
    is_demo     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS scenario (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    prompt      TEXT NOT NULL,
    options_json TEXT NOT NULL,      -- JSON array of {text, strengths, blindspots, better}
    principle   TEXT,
    story_id    TEXT REFERENCES story(id) ON DELETE SET NULL,
    is_demo     INTEGER NOT NULL DEFAULT 0
);

-- Local quiz performance (client also tracks; server aggregate optional) ---
CREATE TABLE IF NOT EXISTS quiz_result (
    id          TEXT PRIMARY KEY,
    question_id TEXT REFERENCES quiz_question(id) ON DELETE CASCADE,
    correct     INTEGER NOT NULL,
    answered_at TEXT
);

-- Daily briefs (assembled snapshots) --------------------------------------
CREATE TABLE IF NOT EXISTS daily_brief (
    id          TEXT PRIMARY KEY,
    brief_date  TEXT NOT NULL,       -- ISO date (UTC)
    payload_json TEXT NOT NULL,      -- fully assembled brief
    created_at  TEXT NOT NULL
);

-- Audit log (automated analysis + manual changes) -------------------------
CREATE TABLE IF NOT EXISTS audit_log (
    id         TEXT PRIMARY KEY,
    ts         TEXT NOT NULL,
    actor      TEXT NOT NULL,        -- system|ingestion|user|ai:<provider>
    action     TEXT NOT NULL,
    entity     TEXT,
    entity_id  TEXT,
    detail     TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts);

-- Feed health (per-feed ingestion status for the Settings indicator) -------
CREATE TABLE IF NOT EXISTS feed_health (
    feed_id      TEXT PRIMARY KEY,
    name         TEXT,
    url          TEXT,
    tier         INTEGER,
    last_run     TEXT,      -- UTC ISO of the last poll attempt
    last_success TEXT,      -- UTC ISO of the last poll that returned items
    last_count   INTEGER NOT NULL DEFAULT 0,
    status       TEXT,      -- ok | empty | error
    error        TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0
);

-- Advisory change-detection state (one row per government feed + destination)-
-- Lets ingestion catch a level/content change even when the advisory URL is
-- unchanged, and skip no-op churn from feeds that re-list every country.
CREATE TABLE IF NOT EXISTS advisory_state (
    feed_id       TEXT NOT NULL,      -- ingestion feed id (e.g. ca_gac_travel)
    dest_country  TEXT NOT NULL,      -- ISO-2 destination the advice is about
    level         INTEGER NOT NULL DEFAULT 0,   -- current normalized 1..4
    prev_level    INTEGER NOT NULL DEFAULT 0,   -- level before the last change
    content_hash  TEXT,               -- hash of level+text, for change detection
    last_modified TEXT,               -- source-provided publication time (UTC ISO)
    changed_at    TEXT,               -- when we last detected a material change
    last_seen     TEXT,               -- last run this advisory was observed
    PRIMARY KEY (feed_id, dest_country)
);

-- Full-text search over stories (standalone FTS, populated in code) --------
CREATE VIRTUAL TABLE IF NOT EXISTS story_fts USING fts5(
    story_id UNINDEXED, headline, summary, location_text, body
);
