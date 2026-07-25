"""HTTP API + brief + challenge + timezone-independence tests."""

from __future__ import annotations

import json

import pytest

from gsid.config import Config


@pytest.fixture()
def ro_client(tmp_path):
    """A public read-only deployment with a known admin token."""
    from gsid.app import create_app
    cfg = Config(
        db_path=str(tmp_path / "ro.sqlite3"),
        data_mode="demo",
        ai_provider="heuristic",
        public_readonly=True,
        admin_token="s3cret-admin",
    )
    app = create_app(cfg)
    app.testing = True
    with app.test_client() as cl:
        yield cl


def test_readonly_blocks_writes_without_admin(ro_client):
    m = ro_client.get("/api/meta").get_json()
    assert m["public_readonly"] is True and m["is_admin"] is False
    # A config write is rejected for anonymous visitors.
    r = ro_client.put("/api/preferences", json={"countries": ["us"]})
    assert r.status_code == 403 and r.get_json()["error"] == "read_only"


def test_readonly_allows_writes_with_admin_token(ro_client):
    hdr = {"X-GSID-Token": "s3cret-admin"}
    assert ro_client.get("/api/admin/check", headers=hdr).get_json()["is_admin"] is True
    r = ro_client.put("/api/preferences", json={"countries": ["us"]}, headers=hdr)
    assert r.status_code == 200


def test_readonly_still_allows_viewing(ro_client):
    assert ro_client.get("/api/stories").status_code == 200
    assert ro_client.get("/api/brief").status_code == 200


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.get_json()["status"] == "ok"


def test_meta_has_scales(client):
    m = client.get("/api/meta").get_json()
    assert "regions" in m and "categories" in m
    assert m["scales"]["confidence"] == ["Unverified", "Low", "Moderate", "High", "Confirmed"]


def test_stories_list_and_detail(client):
    stories = client.get("/api/stories?limit=5").get_json()["stories"]
    assert stories
    sid = stories[0]["id"]
    detail = client.get(f"/api/stories/{sid}").get_json()
    assert detail["id"] == sid
    assert "claims" in detail and "citations" in detail and "scoring" in detail


def test_story_404(client):
    assert client.get("/api/stories/nope").status_code == 404


def test_brief_sections(client):
    b = client.get("/api/brief?data_mode=demo").get_json()
    for key in ["executive_snapshot", "global_risk_pulse", "critical_alerts",
                "regional_watch", "regulations", "supply_chain_watch",
                "cyber_physical_watch", "outlook", "todays_lesson",
                "executive_talking_points"]:
        assert key in b


def test_challenge(client):
    sid = client.get("/api/stories?limit=1").get_json()["stories"][0]["id"]
    findings = client.get(f"/api/stories/{sid}/challenge").get_json()["findings"]
    assert isinstance(findings, list) and findings


def test_search(client):
    r = client.get("/api/search?q=ransomware").get_json()
    assert r["query"] == "ransomware"
    assert any("ransomware" in s["headline"].lower() for s in r["stories"])


def test_quiz_answer_verified_server_side(client):
    q = client.get("/api/quiz").get_json()["questions"][0]
    r = client.post("/api/quiz/answer",
                    json={"question_id": q["id"], "choice_index": q["answer_index"]})
    assert r.get_json()["correct"] is True


def test_export_endpoint(client):
    sid = client.get("/api/stories?limit=1").get_json()["stories"][0]["id"]
    r = client.post(f"/api/stories/{sid}/export?kind=risk_register")
    assert r.status_code == 200
    assert "risk_title" in r.get_json()


def test_saved_flow(client):
    sid = client.get("/api/stories?limit=1").get_json()["stories"][0]["id"]
    assert client.post("/api/saved", json={"story_id": sid}).status_code == 200
    saved = client.get("/api/saved").get_json()["saved"]
    assert any(s["story_id"] == sid for s in saved)
    assert client.delete(f"/api/saved/{sid}").status_code == 200


def test_travel_endpoint_resolves_code_and_name(client):
    by_code = client.get("/api/travel?country=es").get_json()
    assert by_code["country_name"] == "Spain"
    assert "official_links" in by_code and by_code["official_links"]
    by_name = client.get("/api/travel?country=Spain").get_json()
    assert by_name["country"] == "es"


def test_travel_unknown_country(client):
    assert client.get("/api/travel?country=zzz").status_code == 400


def test_meta_includes_countries(client):
    m = client.get("/api/meta").get_json()
    assert isinstance(m.get("countries"), list) and len(m["countries"]) > 100
    assert any(c["code"] == "es" and c["name"] == "Spain" for c in m["countries"])


def test_feed_health_endpoint(client):
    data = client.get("/api/feeds/health").get_json()
    assert "feeds" in data and isinstance(data["feeds"], list)
    assert data["feeds"], "registry should list feeds even before any poll"
    f = data["feeds"][0]
    assert {"feed_id", "name", "status", "tier"} <= set(f)


def test_security_headers(client):
    r = client.get("/api/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "Content-Security-Policy" in r.headers


def test_ingest_disabled_in_demo(client):
    r = client.post("/api/ingest")
    assert r.status_code == 400
    assert r.get_json()["error"] == "ingestion_disabled"


def test_timezone_independence_of_stored_times(client):
    """Internal times must be UTC ISO 'Z' strings regardless of display tz."""
    s = client.get("/api/stories?limit=1").get_json()["stories"][0]
    assert s["last_updated"].endswith("Z")
