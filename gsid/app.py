"""Flask application factory and HTTP API.

Serves the single-page frontend and a JSON API. Includes security headers,
lightweight in-memory rate limiting, optional shared-token auth for mutating
endpoints, structured logging, and consistent error handling.
"""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict, deque
from functools import wraps

from flask import Flask, g, jsonify, request, send_from_directory, Response

from . import brief as brief_mod
from . import db, exports, repository
from .analysis import get_analyzer
from .challenge import challenge
from .config import Config, load_config
from .seed import seed_all
from .taxonomy import (
    ACTION_TYPES, CATEGORIES, CONFIDENCE_LEVELS, COUNTRY_NAMES, GEO_SCOPE_LEVELS,
    IMPACT_LEVELS, LIKELIHOOD_LEVELS, REGIONS, TREND_LEVELS, URGENCY_LEVELS,
    VELOCITY_LEVELS, SOURCE_TIERS, resolve_country,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("gsid.app")

WEB_DIR = "web"


# --------------------------------------------------------------------------
# Rate limiting (simple sliding window, per-IP, per-endpoint-group)
# --------------------------------------------------------------------------
class RateLimiter:
    def __init__(self):
        self._hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str, limit: int, window: float) -> bool:
        now = time.time()
        dq = self._hits[key]
        while dq and dq[0] < now - window:
            dq.popleft()
        if len(dq) >= limit:
            return False
        dq.append(now)
        return True


def create_app(config: Config | None = None) -> Flask:
    config = config or load_config()
    app = Flask(__name__, static_folder=None)
    app.config["SECRET_KEY"] = config.secret_key
    app.config["GSID"] = config
    limiter = RateLimiter()

    # ---- DB lifecycle ----
    def get_conn():
        if "conn" not in g:
            g.conn = db.connect(config.db_file)
        return g.conn

    @app.teardown_appcontext
    def close_conn(exc):  # noqa: ARG001
        conn = g.pop("conn", None)
        if conn is not None:
            conn.close()

    # Initialize schema + seed once at startup.
    with app.app_context():
        conn = db.connect(config.db_file)
        db.init_db(conn)
        seed_all(conn, config)
        conn.close()

    analyzer = get_analyzer(config)
    app.config["ANALYZER"] = analyzer
    log.info("analyzer provider: %s", getattr(analyzer, "name", "unknown"))

    # Optional in-process auto-refresh (opt-in; off unless configured).
    from .scheduler import maybe_start_scheduler
    maybe_start_scheduler(config, analyzer)

    # ---- security headers ----
    @app.after_request
    def security_headers(resp: Response):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "font-src 'self'; script-src 'self'; connect-src 'self'; "
            "frame-ancestors 'none'; base-uri 'self'",
        )
        resp.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        return resp

    @app.before_request
    def rate_limit():
        ip = request.headers.get("X-Forwarded-For", request.remote_addr or "local")
        if request.path.startswith("/api/"):
            if not limiter.allow(f"api:{ip}", limit=240, window=60):
                return jsonify({"error": "rate_limited"}), 429

    # ---- auth / roles ----
    def is_admin() -> bool:
        """True when the request carries the admin token (unlocks writes)."""
        token = request.headers.get("X-GSID-Token", "")
        return bool(config.admin_token) and token == config.admin_token

    def require_auth(fn):
        """Global auth gate (only enforced when GSID_AUTH_ENABLED=true)."""
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if config.auth_enabled and not is_admin() \
                    and request.headers.get("X-GSID-Token", "") != config.access_token:
                return jsonify({"error": "unauthorized"}), 401
            return fn(*args, **kwargs)
        return wrapper

    def require_admin_write(fn):
        """Gate for config writes (settings/watchlist/saved-on-server).

        In public read-only mode these require the admin token; otherwise they
        fall back to the global auth behaviour.
        """
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if config.public_readonly and not is_admin():
                return jsonify({
                    "error": "read_only",
                    "detail": "This is a public read-only deployment. An admin "
                              "token is required to change settings or watchlists.",
                }), 403
            if config.auth_enabled and not is_admin() \
                    and request.headers.get("X-GSID-Token", "") != config.access_token:
                return jsonify({"error": "unauthorized"}), 401
            return fn(*args, **kwargs)
        return wrapper

    def data_mode_param() -> str | None:
        m = request.args.get("data_mode")
        if m in ("demo", "live", "all"):
            return None if m == "all" else m
        # default: reflect configured mode
        if config.data_mode == "demo":
            return "demo"
        if config.data_mode == "live":
            return "live"
        return None  # hybrid -> all

    # ======================================================================
    # Frontend
    # ======================================================================
    @app.route("/")
    def index():
        return send_from_directory(_web_path(app), "index.html")

    @app.route("/static/<path:filename>")
    def static_files(filename):
        return send_from_directory(_web_path(app, "static"), filename)

    # ======================================================================
    # Meta
    # ======================================================================
    @app.get("/api/meta")
    def meta():
        return jsonify({
            "app": "Global Security Intelligence Desk",
            "version": _version(),
            "data_mode": config.data_mode,
            "ai_provider": getattr(analyzer, "name", "heuristic"),
            "auth_enabled": config.auth_enabled,
            "public_readonly": config.public_readonly,
            "public_allow_refresh": config.public_allow_refresh,
            "is_admin": is_admin(),
            "regions": REGIONS,
            "categories": CATEGORIES,
            "scales": {
                "urgency": URGENCY_LEVELS, "geo_scope": GEO_SCOPE_LEVELS,
                "impact": IMPACT_LEVELS, "likelihood": LIKELIHOOD_LEVELS,
                "velocity": VELOCITY_LEVELS, "confidence": CONFIDENCE_LEVELS,
                "trend": TREND_LEVELS, "action_types": ACTION_TYPES,
            },
            "source_tiers": SOURCE_TIERS,
            "countries": sorted(
                ({"code": c, "name": n} for c, n in COUNTRY_NAMES.items()),
                key=lambda x: x["name"],
            ),
        })

    # ======================================================================
    # Stories
    # ======================================================================
    @app.get("/api/stories")
    def stories():
        f = _filters_from_request()
        f["data_mode"] = f.get("data_mode") or data_mode_param()
        limit = min(int(request.args.get("limit", 100)), 300)
        offset = int(request.args.get("offset", 0))
        return jsonify({"stories": repository.list_stories(get_conn(), f, limit, offset)})

    @app.get("/api/stories/<story_id>")
    def story_detail(story_id):
        s = repository.get_story(get_conn(), story_id)
        if not s:
            return jsonify({"error": "not_found"}), 404
        return jsonify(s)

    @app.get("/api/stories/<story_id>/challenge")
    def story_challenge(story_id):
        s = repository.get_story(get_conn(), story_id)
        if not s:
            return jsonify({"error": "not_found"}), 404
        return jsonify({"story_id": story_id, "findings": challenge(s)})

    @app.post("/api/stories/<story_id>/export")
    def story_export(story_id):
        s = repository.get_story(get_conn(), story_id)
        if not s:
            return jsonify({"error": "not_found"}), 404
        kind = request.args.get("kind", "risk_register")
        try:
            if kind == "risk_register_csv":
                return Response(
                    exports.risk_register_csv([exports.risk_register_entry(s)]),
                    mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=risk_{story_id}.csv"})
            if kind == "story_json":
                return Response(json.dumps(s, indent=2), mimetype="application/json")
            result = exports.export_story(s, kind)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        db.audit(get_conn(), "user", "export", "story", story_id, kind)
        get_conn().commit()
        if isinstance(result, str):
            return Response(result, mimetype="text/plain")
        return jsonify(result)

    # ======================================================================
    # Brief / alerts / regional / regulations / map
    # ======================================================================
    @app.get("/api/brief")
    def brief():
        b = brief_mod.build_brief(get_conn(), data_mode_param())
        return jsonify(b)

    @app.get("/api/alerts")
    def alerts():
        return jsonify({"alerts": repository.list_alerts(get_conn(), data_mode_param())})

    @app.get("/api/regional")
    def regional():
        return jsonify({"regions": repository.regional_watch(get_conn(), data_mode_param())})

    @app.get("/api/regulations")
    def regulations():
        return jsonify({"regulations": repository.list_regulations(get_conn(), data_mode_param())})

    @app.get("/api/map")
    def map_points():
        f = {"data_mode": data_mode_param()}
        rows = repository.list_stories(get_conn(), f, limit=300)
        pts = [r for r in rows if r.get("lat") is not None and r.get("lon") is not None]
        return jsonify({"points": pts,
                        "region_counts": repository.counts_by_region(get_conn(), data_mode_param())})

    @app.get("/api/admin/check")
    def admin_check():
        """Let the frontend validate an admin token to unlock editing."""
        return jsonify({"is_admin": is_admin(),
                        "public_readonly": config.public_readonly})

    @app.get("/api/feeds/health")
    def feeds_health():
        return jsonify({"feeds": repository.feed_health(get_conn()),
                        "data_mode": config.data_mode})

    @app.get("/api/travel")
    def travel():
        raw = request.args.get("country", "")
        code = resolve_country(raw)
        if not code:
            return jsonify({"error": "unknown_country",
                            "detail": "Provide a valid country code or name."}), 400
        return jsonify(repository.travel_brief(get_conn(), code, data_mode_param()))

    @app.get("/api/search")
    def search():
        q = request.args.get("q", "")
        ids = db.search_stories(get_conn(), q, limit=50)
        if not ids:
            return jsonify({"query": q, "stories": []})
        results = repository.list_stories(get_conn(), {"ids": ids}, limit=50)
        # preserve rank order
        order = {sid: i for i, sid in enumerate(ids)}
        results.sort(key=lambda s: order.get(s["id"], 999))
        return jsonify({"query": q, "stories": results})

    # ======================================================================
    # Preferences / watchlist
    # ======================================================================
    @app.get("/api/preferences")
    def get_preferences():
        rows = get_conn().execute("SELECT key, value FROM preference").fetchall()
        prefs = {}
        for r in rows:
            v = r["value"]
            try:
                prefs[r["key"]] = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                prefs[r["key"]] = v
        return jsonify(prefs)

    @app.put("/api/preferences")
    @require_admin_write
    def set_preferences():
        payload = request.get_json(silent=True) or {}
        conn = get_conn()
        for k, v in payload.items():
            val = json.dumps(v) if isinstance(v, (list, dict)) else str(v)
            conn.execute("INSERT OR REPLACE INTO preference(key,value) VALUES (?,?)", (k, val))
        db.audit(conn, "user", "update_preferences", detail=list(payload.keys()))
        conn.commit()
        return jsonify({"ok": True})

    # ======================================================================
    # Saved items
    # ======================================================================
    @app.get("/api/saved")
    def list_saved():
        rows = get_conn().execute(
            "SELECT si.id, si.story_id, si.note, si.saved_at FROM saved_item si "
            "ORDER BY si.saved_at DESC").fetchall()
        saved = db.rows_to_dicts(rows)
        for item in saved:
            s = repository.get_story(get_conn(), item["story_id"])
            item["story"] = s
        return jsonify({"saved": saved})

    @app.post("/api/saved")
    @require_admin_write
    def add_saved():
        payload = request.get_json(silent=True) or {}
        story_id = payload.get("story_id")
        if not story_id:
            return jsonify({"error": "story_id required"}), 400
        conn = get_conn()
        existing = conn.execute(
            "SELECT id FROM saved_item WHERE story_id=?", (story_id,)).fetchone()
        if existing:
            return jsonify({"ok": True, "id": existing["id"], "already": True})
        sid = db.new_id("save_")
        conn.execute(
            "INSERT INTO saved_item(id,story_id,note,saved_at) VALUES (?,?,?,?)",
            (sid, story_id, payload.get("note", ""), db.utcnow()))
        conn.commit()
        return jsonify({"ok": True, "id": sid})

    @app.delete("/api/saved/<item_id>")
    @require_admin_write
    def del_saved(item_id):
        conn = get_conn()
        conn.execute("DELETE FROM saved_item WHERE id=? OR story_id=?", (item_id, item_id))
        conn.commit()
        return jsonify({"ok": True})

    # ======================================================================
    # Quiz & scenario
    # ======================================================================
    @app.get("/api/quiz")
    def quiz():
        level = request.args.get("level")
        sql = "SELECT id, question, options_json, answer_index, explanation, difficulty FROM quiz_question"
        params: list = []
        if level:
            sql += " WHERE difficulty <= ?"
            params.append(int(level))
        sql += " ORDER BY RANDOM() LIMIT 3"
        rows = get_conn().execute(sql, params).fetchall()
        out = []
        for r in rows:
            out.append({
                "id": r["id"], "question": r["question"],
                "options": json.loads(r["options_json"]),
                "answer_index": r["answer_index"],  # client checks; also verified server-side
                "explanation": r["explanation"], "difficulty": r["difficulty"],
            })
        return jsonify({"questions": out})

    @app.post("/api/quiz/answer")
    def quiz_answer():
        payload = request.get_json(silent=True) or {}
        qid = payload.get("question_id")
        choice = payload.get("choice_index")
        row = get_conn().execute(
            "SELECT answer_index, explanation FROM quiz_question WHERE id=?", (qid,)).fetchone()
        if not row:
            return jsonify({"error": "not_found"}), 404
        correct = int(choice) == row["answer_index"]
        conn = get_conn()
        conn.execute(
            "INSERT INTO quiz_result(id,question_id,correct,answered_at) VALUES (?,?,?,?)",
            (db.new_id("qr_"), qid, 1 if correct else 0, db.utcnow()))
        conn.commit()
        return jsonify({"correct": correct, "answer_index": row["answer_index"],
                        "explanation": row["explanation"]})

    @app.get("/api/scenario/<scenario_id>")
    def scenario(scenario_id):
        row = get_conn().execute("SELECT * FROM scenario WHERE id=?", (scenario_id,)).fetchone()
        if not row:
            return jsonify({"error": "not_found"}), 404
        return jsonify({
            "id": row["id"], "title": row["title"], "prompt": row["prompt"],
            "options": json.loads(row["options_json"]), "principle": row["principle"],
            "story_id": row["story_id"],
        })

    @app.get("/api/scenarios")
    def scenarios():
        rows = get_conn().execute("SELECT id, title, story_id FROM scenario").fetchall()
        return jsonify({"scenarios": db.rows_to_dicts(rows)})

    # ======================================================================
    # Exports (bulk)
    # ======================================================================
    @app.get("/api/export/stories.csv")
    def export_stories_csv():
        f = _filters_from_request()
        f["data_mode"] = f.get("data_mode") or data_mode_param()
        rows = repository.list_stories(get_conn(), f, limit=300)
        return Response(exports.stories_to_csv(rows), mimetype="text/csv",
                        headers={"Content-Disposition": "attachment; filename=gsid_stories.csv"})

    @app.get("/api/export/stories.json")
    def export_stories_json():
        f = _filters_from_request()
        f["data_mode"] = f.get("data_mode") or data_mode_param()
        rows = repository.list_stories(get_conn(), f, limit=300)
        return Response(json.dumps(rows, indent=2), mimetype="application/json",
                        headers={"Content-Disposition": "attachment; filename=gsid_stories.json"})

    # ======================================================================
    # Live ingestion trigger
    # ======================================================================
    @app.post("/api/ingest")
    @require_auth
    def ingest():
        # In public read-only mode, refresh is open only if allowed (admins always).
        if config.public_readonly and not config.public_allow_refresh and not is_admin():
            return jsonify({"error": "read_only",
                            "detail": "Refresh is disabled on this public deployment."}), 403
        ip = request.headers.get("X-Forwarded-For", request.remote_addr or "local")
        window = config.ingest_interval_minutes * 60
        if not limiter.allow(f"ingest:{ip}", limit=1, window=window):
            return jsonify({"error": "ingest_rate_limited",
                            "retry_after_seconds": window}), 429
        if config.data_mode == "demo":
            return jsonify({"error": "ingestion_disabled",
                            "detail": "Set GSID_DATA_MODE=live or hybrid to enable."}), 400
        from .ingestion.pipeline import IngestionPipeline
        pipeline = IngestionPipeline(get_conn(), config, analyzer)
        try:
            result = pipeline.run()
        except Exception as exc:  # pragma: no cover
            log.exception("ingestion failed")
            return jsonify({"error": "ingestion_failed", "detail": str(exc)}), 500
        return jsonify(result)

    # ======================================================================
    # Audit log (transparency)
    # ======================================================================
    @app.get("/api/audit")
    def audit_view():
        rows = get_conn().execute(
            "SELECT ts, actor, action, entity, entity_id, detail FROM audit_log "
            "ORDER BY ts DESC LIMIT 200").fetchall()
        return jsonify({"audit": db.rows_to_dicts(rows)})

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok", "version": _version()})

    @app.errorhandler(404)
    def not_found(e):  # noqa: ARG001
        if request.path.startswith("/api/"):
            return jsonify({"error": "not_found"}), 404
        return send_from_directory(_web_path(app), "index.html")

    @app.errorhandler(500)
    def server_error(e):  # noqa: ARG001
        log.exception("unhandled error")
        return jsonify({"error": "server_error"}), 500

    return app


# --------------------------------------------------------------------------
def _filters_from_request() -> dict:
    args = request.args
    f: dict = {}
    for key in ("category", "region", "country", "impact", "urgency",
                "confidence", "trend", "sort", "since"):
        if args.get(key):
            f[key] = args.get(key)
    if args.get("min_score"):
        f["min_score"] = args.get("min_score")
    if args.get("alerts_only") in ("1", "true"):
        f["alerts_only"] = True
    if args.get("verified_only") in ("1", "true"):
        f["verified_only"] = True
    if args.get("data_mode") in ("demo", "live"):
        f["data_mode"] = args.get("data_mode")
    return f


def _web_path(app: Flask, *parts: str) -> str:
    import os
    base = os.path.join(os.path.dirname(__file__), WEB_DIR, *parts)
    return base


def _version() -> str:
    from . import __version__
    return __version__
