"""Headline geocoding: a marker asserts a fact, so precision beats coverage."""

import pytest

from gsid import geocode


def city(headline, countries):
    hit = geocode.locate(headline, countries)
    return hit["city"] if hit else None


class TestAccepts:
    @pytest.mark.parametrize("headline, countries, expected", [
        ("Deadly strike on Kyiv warehouse prompts evacuations", ["ua"], "Kyiv"),
        ("Pakistan: Islamabad hospital fire kills at least 14 infants", ["pk"], "Islamabad"),
        ("Germany blames Russia for Leipzig airport drone attack", ["de", "ru"], "Leipzig"),
        ("Bordeaux wildfire burns 3,100 hectares, 20,000 evacuated", ["fr"], "Bordeaux"),
        ("Thousands protest in Ljubljana as Slovenia opens embassy", ["si"], "Ljubljana"),
    ])
    def test_locates_the_event(self, headline, countries, expected):
        assert city(headline, countries) == expected

    def test_multiword_names_beat_their_suffix(self):
        # "New Delhi" must not resolve as "Delhi": candidates run longest-first.
        assert city("Xi Jinping arrives in New Delhi for BRICS summit", ["in"]) == "New Delhi"


class TestRefusals:
    def test_no_country_tag_refuses_to_guess(self):
        assert geocode.locate("Explosion reported in Paris", []) is None

    def test_country_anchor_blocks_the_wrong_hemisphere(self):
        # Paris, Texas must never capture a story tagged only to France, and the
        # reverse must hold too — the tag constrains, it never invents.
        assert city("Paris police disperse crowd", ["us"]) != "Paris" or \
            geocode.locate("Paris police disperse crowd", ["us"])["country"] == "us"

    @pytest.mark.parametrize("headline, countries", [
        # Common English words that happen to be city names.
        ("Mobile phones seized in raid on prison", ["us"]),
        # A crude-oil benchmark, not a London suburb.
        ("Oil prices hit $100 as Brent crude surges", ["gb"]),
    ])
    def test_ambiguous_words_are_never_plotted(self, headline, countries):
        assert geocode.locate(headline, countries) is None

    @pytest.mark.parametrize("headline, countries", [
        ("Washington says strikes on Iran will continue", ["us"]),
        ("Damascus slams 'blatant violation' of sovereignty", ["sy"]),
        ("South Korea shortens war games, citing Washington request", ["kr", "us"]),
        ("Seoul drops denuclearisation-first stance on Pyongyang", ["kr", "kp"]),
        ("Saudi deal contingent on Riyadh normalising relations", ["sa"]),
    ])
    def test_capital_as_government_is_not_a_location(self, headline, countries):
        """A capital standing in for its government is an actor, not a place."""
        assert geocode.locate(headline, countries) is None

    def test_one_locative_mention_rescues_the_marker(self):
        assert city("Moscow denies strike on Moscow suburb", ["ru"]) == "Moscow"

    def test_attack_verbs_are_not_treated_as_metonymy(self):
        """Excluding "hits"/"strikes" would drop genuine locations."""
        assert city("Russia hits Kyiv with deadly missile strikes", ["ua", "ru"]) == "Kyiv"


def test_summary_is_not_consulted():
    """Summaries name what a story is about, not where it happened.

    Feeding them in geocoded a Kyiv factory strike to Moscow, so `locate` reads
    the headline alone. Guard the signature so that cannot quietly come back.
    """
    import inspect
    assert list(inspect.signature(geocode.locate).parameters) == ["headline", "countries"]


def test_missing_gazetteer_disables_geocoding(monkeypatch, tmp_path):
    monkeypatch.setattr(geocode, "_DATA", tmp_path / "absent.json")
    monkeypatch.setattr(geocode, "_index", None)
    assert geocode.locate("Deadly strike on Kyiv warehouse", ["ua"]) is None
    geocode._index = None          # let other tests reload the real gazetteer
