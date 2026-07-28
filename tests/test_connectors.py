"""Connector registry / non-RSS connector tests."""

from __future__ import annotations

from gsid.ingestion.connectors import (
    FEED_BY_ID,
    CanadaAdvisoryConnector,
    GermanyAdvisoryConnector,
    RssConnector,
    _epoch_to_utc_iso,
    make_connector,
)


# A trimmed sample matching the shape of
# https://data.international.gc.ca/travel-voyage/index-updated.json
CA_SAMPLE = {
    "metadata": {"generated": {"timestamp": 1785181216}},
    "data": {
        "CA": {  # level 1 (normal precautions) -> excluded
            "country-eng": "Canada",
            "advisory-state": 0,
            "date-published": {"timestamp": 1783516606},
            "eng": {"name": "Canada", "url-slug": "canada",
                    "advisory-text": "Take normal security precautions"},
        },
        "FR": {  # level 2 (high caution) -> included
            "country-eng": "France",
            "country-iso": "FR",
            "advisory-state": 1,
            "date-published": {"timestamp": 1783516606},
            "eng": {"name": "France", "url-slug": "france",
                    "advisory-text": "Exercise a high degree of caution",
                    "recent-updates": "Demonstrations section updated"},
        },
        "AF": {  # level 4 (avoid all travel) -> included
            "country-eng": "Afghanistan",
            "advisory-state": 3,
            "date-published": {"timestamp": 1783516606},
            "eng": {"name": "Afghanistan", "url-slug": "afghanistan",
                    "advisory-text": "Avoid all travel"},
        },
    },
}


# A trimmed sample matching the German Auswärtiges Amt /travelwarning shape.
DE_SAMPLE = {
    "response": {
        "lastModified": 1757063288,  # scalar, must be skipped
        "111": {  # baseline safety notice, no active warning -> excluded
            "countryName": "Portugal", "countryCode": "PT", "iso3CountryCode": "PRT",
            "title": "Portugal: Reise- und Sicherheitshinweise",
            "warning": False, "partialWarning": False,
            "situationWarning": False, "situationPartWarning": False,
            "lastModified": 1757063288,
        },
        "222": {  # full travel warning -> included
            "countryName": "Jemen", "countryCode": "YE", "iso3CountryCode": "YEM",
            "title": "Jemen: Reise- und Sicherheitshinweise",
            "warning": True, "partialWarning": False,
            "situationWarning": False, "situationPartWarning": False,
            "lastModified": 1757063288,
        },
        "333": {  # partial warning as stringified bool -> included
            "countryName": "Mexiko", "countryCode": "MX", "iso3CountryCode": "MEX",
            "title": "Mexiko: Reise- und Sicherheitshinweise",
            "warning": "False", "partialWarning": "True",
            "situationWarning": "False", "situationPartWarning": "False",
            "lastModified": 1757063288,
        },
    }
}


def _parse(payload):
    return CanadaAdvisoryConnector(FEED_BY_ID["ca_gac_travel"])._items(payload)


def _parse_de(payload):
    return GermanyAdvisoryConnector(FEED_BY_ID["de_aa_travel"])._items(payload)


def test_canada_parser_filters_to_level_two_and_above():
    items = _parse(CA_SAMPLE)
    names = sorted(i.title.split(" — ")[0] for i in items)
    assert names == ["Afghanistan", "France"]  # Canada (level 1) dropped


def test_canada_parser_builds_geo_taggable_items():
    items = {i.title.split(" — ")[0]: i for i in _parse(CA_SAMPLE)}
    fr = items["France"]
    # Title leads with destination name so pipeline geo-tagging resolves it.
    assert fr.title.startswith("France — ")
    assert fr.link == "https://travel.gc.ca/destinations/france"
    assert fr.is_travel_advisory is True
    assert fr.tier == 1 and fr.country == "ca"
    assert "high degree of caution" in fr.summary
    assert "Demonstrations section updated" in fr.summary  # recent-updates folded in
    assert fr.published_at.endswith("Z")
    assert fr.subject_country == "fr"  # authoritative destination ISO passed through


def test_canada_parser_tolerates_missing_and_malformed_entries():
    assert _parse({}) == []
    assert _parse({"data": {"X": {}}}) == []                 # no state -> skipped
    assert _parse({"data": {"X": {"advisory-state": "?"}}}) == []  # non-int state


def test_epoch_helper():
    assert _epoch_to_utc_iso(1783516606).endswith("Z")
    assert _epoch_to_utc_iso(0) == ""
    assert _epoch_to_utc_iso(None) == ""
    assert _epoch_to_utc_iso("nope") == ""


def test_germany_parser_filters_to_active_warnings():
    items = {i.title.split(" — ")[0]: i for i in _parse_de(DE_SAMPLE)}
    assert set(items) == {"Jemen", "Mexiko"}  # Portugal (baseline) dropped
    ye = items["Jemen"]
    assert ye.subject_country == "ye"  # authoritative 2-letter ISO
    assert ye.link.endswith("/ReiseUndSicherheit/222")  # deterministic deep-link
    assert ye.language == "de" and ye.tier == 1 and ye.country == "de"
    assert items["Mexiko"].title.endswith("Partial travel warning")  # string bool honored


def test_germany_parser_tolerates_empty_and_scalars():
    assert _parse_de({}) == []
    assert _parse_de({"response": {"lastModified": 123}}) == []


def test_make_connector_dispatches_by_kind():
    assert isinstance(make_connector(FEED_BY_ID["ca_gac_travel"]), CanadaAdvisoryConnector)
    assert isinstance(make_connector(FEED_BY_ID["de_aa_travel"]), GermanyAdvisoryConnector)
    assert isinstance(make_connector(FEED_BY_ID["us_state_travel"]), RssConnector)
    assert isinstance(make_connector(FEED_BY_ID["bbc_world"]), RssConnector)


def test_australia_feed_uses_browser_user_agent():
    au = FEED_BY_ID["au_smartraveller"]
    assert au.is_travel_advisory is True
    assert au.user_agent.startswith("Mozilla/")  # UA override set for bot protection
