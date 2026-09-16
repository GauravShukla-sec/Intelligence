"""Cross-run event matching and evidence recomputation.

An evidence gate that requires two independent Tier-1/2 sources is unreachable
while every story has one, so these two behaviours are load-bearing for any
Critical-promotion policy.
"""

from __future__ import annotations

import pytest

from gsid.ingestion.dedup import (
    MAX_MATCH_KM, _km_apart, cluster_items, find_matching_story, jaccard, signature,
)

# The Leipzig airport drone attack, as five outlets actually filed it. These
# were stored as five separate stories, which is what kept the corpus
# 90% single-source.
LEIPZIG = [
    "Germany says Russia behind Leipzig airport drone attack",
    "Germany says Russia behind attempted drone attack at Leipzig airport",
    "Germany blames Russia for drone attack at Leipzig airport",
    "Germany blames Russia for attempted drone attack at Leipzig airport",
    "Germany blames Russia for Leipzig airport drone attack, orders Russian consulate shut",
]
# Later developments on the same subject that are NOT the same event.
FOLLOW_UPS = [
    "EU summons Russian envoy over failed Leipzig drone attack",
    "Germany plans anti-drone shield over Leipzig attack — report",
]


class TestHeadlineOnlySimilarity:
    def test_body_inclusion_collapses_similarity(self):
        """Jaccard over a token bag is dominated by the larger set.

        Real summaries for these stories ran 111-737 characters. With them
        included the same pair scores below any usable threshold, which is why
        clustering had been near-inoperative.
        """
        a, b = LEIPZIG[0], LEIPZIG[1]
        # Distinct vocabulary, not repeated filler: `signature` is a set, so
        # repetition does not grow the token bag and would not reproduce the
        # effect. Real summaries differ in wording, which is what dilutes.
        short_body = "Berlin officials confirmed the unmanned aircraft crossed restricted airspace."
        long_body = (
            "Investigators examining wreckage recovered near the perimeter fence "
            "believe the device originated abroad, according to two people briefed "
            "on preliminary findings, while prosecutors weigh charges and airlines "
            "reschedule departures disrupted throughout the evening."
        )
        head_only = jaccard(signature(a), signature(b))
        with_bodies = jaccard(signature(f"{a} {short_body}"),
                              signature(f"{b} {long_body}"))
        assert head_only >= 0.5, head_only
        assert with_bodies < 0.5, (
            f"headline-only {head_only:.2f} but {with_bodies:.2f} with bodies; "
            "the body must not be part of the similarity signal")

    def test_same_event_headlines_cluster_together(self):
        clusters = cluster_items(LEIPZIG, threshold=0.5)
        biggest = max(clusters, key=len)
        assert len(biggest) >= 4, f"expected one event, got {clusters}"

    @pytest.mark.parametrize("follow_up", FOLLOW_UPS)
    def test_later_developments_stay_separate(self, follow_up):
        """A diplomatic response is a different event from the attack."""
        assert all(jaccard(signature(follow_up), signature(h)) < 0.5 for h in LEIPZIG)


class TestGeoGuard:
    def test_distant_coordinates_are_different_events(self):
        """GDACS boilerplate is near-identical across continents; a fire in
        Mozambique once scored Namibian coordinates through text similarity."""
        assert _km_apart(-19.0, 34.0, -22.0, 17.0) > MAX_MATCH_KM

    def test_nearby_coordinates_are_the_same_event(self):
        assert _km_apart(51.4, 12.2, 51.4, 12.3) < MAX_MATCH_KM


class TestFindMatchingStory:
    @pytest.fixture
    def conn(self, tmp_path):
        from gsid import db
        c = db.connect(tmp_path / "t.sqlite3")
        db.init_db(c)
        return c

    def _insert(self, conn, sid, headline, *, lat=None, lon=None, status="developing"):
        conn.execute(
            "INSERT INTO story(id,headline,summary,category,primary_region,status,"
            "is_demo,first_seen,last_updated,lat,lon) "
            "VALUES (?,?,'','geopolitical','europe',?,0,"
            "        datetime('now'),datetime('now'),?,?)",
            (sid, headline, status, lat, lon))
        conn.commit()

    def test_matches_a_stored_event(self, conn):
        self._insert(conn, "s1", LEIPZIG[0])
        assert find_matching_story(conn, LEIPZIG[1]) == "s1"

    def test_returns_none_for_an_unrelated_event(self, conn):
        self._insert(conn, "s1", LEIPZIG[0])
        assert find_matching_story(conn, "Ferry fire kills 35 in the Philippines") is None

    def test_advisories_are_never_matched(self, conn):
        """Advisory boilerplate is near-identical across destinations; they are
        keyed by destination at save time instead."""
        self._insert(conn, "s1", "Travel advisory: France", status="advisory")
        assert find_matching_story(conn, "Travel advisory: Germany") is None

    def test_distant_coordinates_block_a_text_match(self, conn):
        self._insert(conn, "s1", "Green forest fire notification in Mozambique",
                     lat=-19.0, lon=34.0)
        assert find_matching_story(
            conn, "Green forest fire notification in Namibia",
            lat=-22.0, lon=17.0) is None

    def test_outside_the_window_is_not_matched(self, conn):
        conn.execute(
            "INSERT INTO story(id,headline,summary,category,primary_region,status,"
            "is_demo,first_seen,last_updated) VALUES "
            "('old',?,'','geopolitical','europe','developing',0,"
            " '2020-01-01T00:00:00Z','2020-01-01T00:00:00Z')",
            (LEIPZIG[0],))
        conn.commit()
        assert find_matching_story(conn, LEIPZIG[1]) is None

    def test_no_row_cap_hides_a_better_match(self, conn):
        """A LIMIT made the result a function of ingestion order: at current
        volume a 72-hour window already holds ~470 stories."""
        for i in range(450):
            self._insert(conn, f"pad{i}", f"Unrelated municipal notice number {i}")
        self._insert(conn, "target", LEIPZIG[0])
        assert find_matching_story(conn, LEIPZIG[1]) == "target"


class TestMergePromotesEvidence:
    """A merge must be able to change the verdict.

    `derive_confidence` reads best tier, independent source count and whether
    any source is primary. Before this, `_merge_into_existing` appended the
    citation and stopped, so a second Tier-1 source could never lift a story off
    Low/Unverified — and the alert gate rejects those outright. Corroboration
    was being recorded and then ignored.
    """

    @pytest.fixture
    def env(self, tmp_path):
        from gsid import db
        from gsid.analysis.heuristic import HeuristicAnalyzer
        conn = db.connect(tmp_path / "t.sqlite3")
        db.init_db(conn)
        return conn, HeuristicAnalyzer()

    @staticmethod
    def _draft(headline, source_name, tier, *, primary=False, url=None):
        from gsid.store import DraftSource, StoryDraft
        return StoryDraft(
            headline=headline,
            body="Officials confirmed casualties at the site.",
            category="geopolitical",
            primary_country="de",
            countries=["de"],
            event_time="",
            sources=[DraftSource(
                name=source_name, url=url or f"https://example.test/{source_name}",
                tier=tier, is_primary=primary, title=headline)],
        )

    def _evidence(self, conn, sid):
        row = conn.execute(
            "SELECT confidence, is_alert, "
            "  (SELECT COUNT(DISTINCT source_id) FROM citation WHERE story_id=?) srcs "
            "FROM story WHERE id=?", (sid, sid)).fetchone()
        return row["confidence"], bool(row["is_alert"]), row["srcs"]

    def test_second_independent_source_merges_and_raises_confidence(self, env):
        from gsid.store import save_story
        conn, analyzer = env
        first = save_story(conn, self._draft(LEIPZIG[0], "Reuters", 2), analyzer)
        conf_before, _, srcs_before = self._evidence(conn, first)

        second = save_story(conn, self._draft(LEIPZIG[1], "AP", 2), analyzer)
        conf_after, _, srcs_after = self._evidence(conn, first)

        assert second == first, "the second outlet should merge, not create a story"
        assert srcs_after == srcs_before + 1 == 2
        assert conf_after != conf_before, (
            f"confidence stayed {conf_before} after corroboration")

    def test_merge_is_recorded_in_the_audit_trail(self, env):
        """Governance requires the promotion be attributable, not silent."""
        from gsid.store import save_story
        conn, analyzer = env
        sid = save_story(conn, self._draft(LEIPZIG[0], "Reuters", 2), analyzer)
        save_story(conn, self._draft(LEIPZIG[1], "AP", 2), analyzer)
        actions = [r["action"] for r in conn.execute(
            "SELECT action FROM audit_log WHERE entity_id=?", (sid,))]
        assert "merge_citation" in actions
        assert "recompute_evidence" in actions

    def test_unrelated_event_does_not_merge(self, env):
        from gsid.store import save_story
        conn, analyzer = env
        a = save_story(conn, self._draft(LEIPZIG[0], "Reuters", 2), analyzer)
        b = save_story(conn, self._draft(
            "Ferry fire kills 35 off the Philippines", "AFP", 2), analyzer)
        assert a != b

    def test_same_url_twice_does_not_inflate_corroboration(self, env):
        """Re-ingesting one feed item must not look like a second source."""
        from gsid.store import save_story
        conn, analyzer = env
        d1 = self._draft(LEIPZIG[0], "Reuters", 2, url="https://example.test/same")
        sid = save_story(conn, d1, analyzer)
        d2 = self._draft(LEIPZIG[1], "Reuters", 2, url="https://example.test/same")
        save_story(conn, d2, analyzer)
        _, _, srcs = self._evidence(conn, sid)
        assert srcs == 1, f"one URL counted as {srcs} sources"
