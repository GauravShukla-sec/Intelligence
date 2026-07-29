"""Controlled vocabularies shared across the whole system.

Keeping regions, categories, and rating scales in one place ensures the
scoring engine, ingestion pipeline, API and UI all speak the same language.
"""

from __future__ import annotations

import re

# --------------------------------------------------------------------------
# Regions (used for the Regional Security Watch and the map)
# --------------------------------------------------------------------------
REGIONS: list[dict[str, str]] = [
    {"id": "north_america", "name": "North America"},
    {"id": "latam_caribbean", "name": "Latin America & Caribbean"},
    {"id": "europe", "name": "Europe"},
    {"id": "mena", "name": "Middle East & North Africa"},
    {"id": "subsaharan_africa", "name": "Sub-Saharan Africa"},
    {"id": "south_asia", "name": "South Asia"},
    {"id": "central_asia", "name": "Central Asia"},
    {"id": "east_asia", "name": "East Asia"},
    {"id": "southeast_asia", "name": "Southeast Asia"},
    {"id": "australia_pacific", "name": "Australia & Pacific"},
    {"id": "global", "name": "Global / Multiple"},
]
REGION_IDS = [r["id"] for r in REGIONS]
REGION_NAMES = {r["id"]: r["name"] for r in REGIONS}

# Country (ISO alpha-2 lowercased) -> region. Not exhaustive; extend freely.
COUNTRY_REGION: dict[str, str] = {
    # North America
    "us": "north_america", "ca": "north_america",
    # Latin America & Caribbean
    "mx": "latam_caribbean", "br": "latam_caribbean", "ar": "latam_caribbean",
    "cl": "latam_caribbean", "co": "latam_caribbean", "pe": "latam_caribbean",
    "ve": "latam_caribbean", "ec": "latam_caribbean", "pa": "latam_caribbean",
    "ht": "latam_caribbean", "gt": "latam_caribbean",
    # Europe
    "gb": "europe", "fr": "europe", "de": "europe", "hu": "europe",
    "es": "europe", "it": "europe", "pl": "europe", "nl": "europe",
    "be": "europe", "se": "europe", "no": "europe", "fi": "europe",
    "dk": "europe", "ie": "europe", "pt": "europe", "at": "europe",
    "cz": "europe", "sk": "europe", "ro": "europe", "gr": "europe",
    "ua": "europe", "rs": "europe", "ch": "europe", "eu": "europe",
    # MENA
    "il": "mena", "ps": "mena", "eg": "mena", "sa": "mena", "ae": "mena",
    "ir": "mena", "iq": "mena", "sy": "mena", "lb": "mena", "jo": "mena",
    "ye": "mena", "ly": "mena", "tn": "mena", "dz": "mena", "ma": "mena",
    "qa": "mena", "kw": "mena", "om": "mena", "bh": "mena", "tr": "mena",
    # Sub-Saharan Africa
    "ng": "subsaharan_africa", "za": "subsaharan_africa", "ke": "subsaharan_africa",
    "et": "subsaharan_africa", "gh": "subsaharan_africa", "sd": "subsaharan_africa",
    "cd": "subsaharan_africa", "ml": "subsaharan_africa", "ne": "subsaharan_africa",
    "bf": "subsaharan_africa", "so": "subsaharan_africa", "mz": "subsaharan_africa",
    # South Asia
    "in": "south_asia", "pk": "south_asia", "bd": "south_asia", "lk": "south_asia",
    "np": "south_asia", "af": "south_asia",
    # Central Asia
    "kz": "central_asia", "uz": "central_asia", "kg": "central_asia",
    "tj": "central_asia", "tm": "central_asia",
    # East Asia
    "cn": "east_asia", "jp": "east_asia", "kr": "east_asia", "kp": "east_asia",
    "tw": "east_asia", "hk": "east_asia", "mn": "east_asia",
    # Southeast Asia
    "sg": "southeast_asia", "my": "southeast_asia", "th": "southeast_asia",
    "vn": "southeast_asia", "id": "southeast_asia", "ph": "southeast_asia",
    "mm": "southeast_asia", "kh": "southeast_asia", "la": "southeast_asia",
    # Australia & Pacific
    "au": "australia_pacific", "nz": "australia_pacific", "pg": "australia_pacific",
    "fj": "australia_pacific",
    # Russia spans regions; treat as Europe/East for watch purposes.
    "ru": "europe",
}


def region_for_country(code: str | None) -> str:
    if not code:
        return "global"
    return COUNTRY_REGION.get(code.strip().lower(), "global")


# Human-readable country names — full ISO 3166-1 alpha-2 set so any travel
# destination resolves. (Region mapping in COUNTRY_REGION is a subset; unmapped
# codes default to the "global" region, which is an acceptable fallback.)
COUNTRY_NAMES: dict[str, str] = {
    "af": "Afghanistan", "ax": "Åland Islands", "al": "Albania", "dz": "Algeria",
    "as": "American Samoa", "ad": "Andorra", "ao": "Angola", "ai": "Anguilla",
    "ag": "Antigua and Barbuda", "ar": "Argentina", "am": "Armenia", "aw": "Aruba",
    "au": "Australia", "at": "Austria", "az": "Azerbaijan", "bs": "Bahamas",
    "bh": "Bahrain", "bd": "Bangladesh", "bb": "Barbados", "by": "Belarus",
    "be": "Belgium", "bz": "Belize", "bj": "Benin", "bm": "Bermuda", "bt": "Bhutan",
    "bo": "Bolivia", "ba": "Bosnia and Herzegovina", "bw": "Botswana", "br": "Brazil",
    "vg": "British Virgin Islands", "bn": "Brunei", "bg": "Bulgaria",
    "bf": "Burkina Faso", "bi": "Burundi", "kh": "Cambodia", "cm": "Cameroon",
    "ca": "Canada", "cv": "Cape Verde", "ky": "Cayman Islands",
    "cf": "Central African Republic", "td": "Chad", "cl": "Chile", "cn": "China",
    "co": "Colombia", "km": "Comoros", "cg": "Congo", "cd": "DR Congo",
    "ck": "Cook Islands", "cr": "Costa Rica", "ci": "Côte d'Ivoire", "hr": "Croatia",
    "cu": "Cuba", "cw": "Curaçao", "cy": "Cyprus", "cz": "Czechia", "dk": "Denmark",
    "dj": "Djibouti", "dm": "Dominica", "do": "Dominican Republic", "ec": "Ecuador",
    "eg": "Egypt", "sv": "El Salvador", "gq": "Equatorial Guinea", "er": "Eritrea",
    "ee": "Estonia", "sz": "Eswatini", "et": "Ethiopia", "fk": "Falkland Islands",
    "fo": "Faroe Islands", "fj": "Fiji", "fi": "Finland", "fr": "France",
    "pf": "French Polynesia", "ga": "Gabon", "gm": "Gambia", "ge": "Georgia",
    "de": "Germany", "gh": "Ghana", "gi": "Gibraltar", "gr": "Greece",
    "gl": "Greenland", "gd": "Grenada", "gu": "Guam", "gt": "Guatemala",
    "gg": "Guernsey", "gn": "Guinea", "gw": "Guinea-Bissau", "gy": "Guyana",
    "ht": "Haiti", "hn": "Honduras", "hk": "Hong Kong", "hu": "Hungary",
    "is": "Iceland", "in": "India", "id": "Indonesia", "ir": "Iran", "iq": "Iraq",
    "ie": "Ireland", "im": "Isle of Man", "il": "Israel", "it": "Italy",
    "jm": "Jamaica", "jp": "Japan", "je": "Jersey", "jo": "Jordan",
    "kz": "Kazakhstan", "ke": "Kenya", "ki": "Kiribati", "kp": "North Korea",
    "kr": "South Korea", "kw": "Kuwait", "kg": "Kyrgyzstan", "la": "Laos",
    "lv": "Latvia", "lb": "Lebanon", "ls": "Lesotho", "lr": "Liberia", "ly": "Libya",
    "li": "Liechtenstein", "lt": "Lithuania", "lu": "Luxembourg", "mo": "Macao",
    "mg": "Madagascar", "mw": "Malawi", "my": "Malaysia", "mv": "Maldives",
    "ml": "Mali", "mt": "Malta", "mh": "Marshall Islands", "mr": "Mauritania",
    "mu": "Mauritius", "mx": "Mexico", "fm": "Micronesia", "md": "Moldova",
    "mc": "Monaco", "mn": "Mongolia", "me": "Montenegro", "ms": "Montserrat",
    "ma": "Morocco", "mz": "Mozambique", "mm": "Myanmar", "na": "Namibia",
    "nr": "Nauru", "np": "Nepal", "nl": "Netherlands", "nc": "New Caledonia",
    "nz": "New Zealand", "ni": "Nicaragua", "ne": "Niger", "ng": "Nigeria",
    "mk": "North Macedonia", "no": "Norway", "om": "Oman", "pk": "Pakistan",
    "pw": "Palau", "ps": "Palestinian Territories", "pa": "Panama",
    "pg": "Papua New Guinea", "py": "Paraguay", "pe": "Peru", "ph": "Philippines",
    "pl": "Poland", "pt": "Portugal", "pr": "Puerto Rico", "qa": "Qatar",
    "ro": "Romania", "ru": "Russia", "rw": "Rwanda", "ws": "Samoa",
    "sm": "San Marino", "st": "São Tomé and Príncipe", "sa": "Saudi Arabia",
    "sn": "Senegal", "rs": "Serbia", "sc": "Seychelles", "sl": "Sierra Leone",
    "sg": "Singapore", "sx": "Sint Maarten", "sk": "Slovakia", "si": "Slovenia",
    "sb": "Solomon Islands", "so": "Somalia", "za": "South Africa",
    "ss": "South Sudan", "es": "Spain", "lk": "Sri Lanka", "kn": "Saint Kitts and Nevis",
    "lc": "Saint Lucia", "vc": "Saint Vincent and the Grenadines", "sd": "Sudan",
    "sr": "Suriname", "se": "Sweden", "ch": "Switzerland", "sy": "Syria",
    "tw": "Taiwan", "tj": "Tajikistan", "tz": "Tanzania", "th": "Thailand",
    "tl": "Timor-Leste", "tg": "Togo", "to": "Tonga", "tt": "Trinidad and Tobago",
    "tn": "Tunisia", "tr": "Turkey", "tm": "Turkmenistan", "tc": "Turks and Caicos",
    "tv": "Tuvalu", "ug": "Uganda", "ua": "Ukraine", "ae": "United Arab Emirates",
    "gb": "United Kingdom", "us": "United States", "uy": "Uruguay",
    "uz": "Uzbekistan", "vu": "Vanuatu", "va": "Vatican City", "ve": "Venezuela",
    "vn": "Vietnam", "ye": "Yemen", "zm": "Zambia", "zw": "Zimbabwe",
    "eu": "European Union",
}

# Reverse lookup (lowercased name -> code), plus a few common aliases.
NAME_TO_ISO: dict[str, str] = {name.lower(): code for code, name in COUNTRY_NAMES.items()}
NAME_TO_ISO.update({
    "usa": "us", "u.s.": "us", "u.s.a.": "us", "america": "us", "uk": "gb",
    "u.k.": "gb", "britain": "gb", "great britain": "gb", "uae": "ae",
    "south korea": "kr", "north korea": "kp", "czech republic": "cz",
    "the gambia": "gm", "drc": "cd", "democratic republic of the congo": "cd",
    "saudi": "sa", "russian": "ru", "chinese": "cn", "ukrainian": "ua",
})


# --------------------------------------------------------------------------
# Country-mention extraction — tag a story to the countries it is ABOUT,
# not to its publisher. Names of >=4 chars are matched with word boundaries
# (so "Niger" never matches "Nigeria"); the ambiguous 2-letter US/UK are
# matched case-sensitively as uppercase tokens to avoid the pronoun "us".
# --------------------------------------------------------------------------
_MENTION_NAMES = sorted(
    (n for n in NAME_TO_ISO if len(n) >= 4),
    key=len, reverse=True,  # longest first so "south korea" beats "korea"
)
_MENTION_RE = re.compile(
    r"\b(" + "|".join(re.escape(n) for n in _MENTION_NAMES) + r")\b",
    re.IGNORECASE,
)
_ABBR_RE = [
    (re.compile(r"\bU\.?S\.?A?\.?\b"), "us"),   # US, USA, U.S., U.S.A.
    (re.compile(r"\bU\.?K\.?\b"), "gb"),        # UK, U.K.
]


def mentioned_countries(text: str | None, limit: int = 8) -> list[str]:
    """ISO-2 codes of countries named in the text, in first-seen order.

    Used to geo-tag a development to its subject countries. Case-insensitive
    for full names; case-sensitive for the US/UK abbreviations.
    """
    if not text:
        return []
    found: list[str] = []
    seen: set[str] = set()
    for rx, code in _ABBR_RE:
        if code not in seen and rx.search(text):
            seen.add(code)
            found.append(code)
    for m in _MENTION_RE.finditer(text):
        code = NAME_TO_ISO.get(m.group(1).lower())
        if code and code not in seen:
            seen.add(code)
            found.append(code)
            if len(found) >= limit:
                break
    return found


def resolve_country(text: str | None) -> str | None:
    """Best-effort map a country name / FCDO URL slug to an ISO alpha-2 code."""
    if not text:
        return None
    key = text.strip().lower()
    if key in COUNTRY_NAMES:  # already a code
        return key
    if key in NAME_TO_ISO:
        return NAME_TO_ISO[key]
    # FCDO slugs look like "foreign-travel-advice/spain" or "the-gambia"
    slug = key.rsplit("/", 1)[-1].replace("-", " ").strip()
    return NAME_TO_ISO.get(slug)


def country_name(code: str | None) -> str:
    if not code:
        return "—"
    return COUNTRY_NAMES.get(code.strip().lower(), code.upper())


# --------------------------------------------------------------------------
# Security categories (the eight domains A–H plus regulatory)
# --------------------------------------------------------------------------
CATEGORIES: list[dict[str, str]] = [
    {"id": "geopolitical", "name": "Geopolitical Risk", "letter": "A"},
    {"id": "physical_corporate", "name": "Physical & Corporate Security", "letter": "B"},
    {"id": "supply_chain", "name": "Supply-Chain & Trade Security", "letter": "C"},
    {"id": "regulatory", "name": "Laws, Regulations & Compliance", "letter": "D"},
    {"id": "cyber_physical", "name": "Cyber-Physical & Technology Risk", "letter": "E"},
    {"id": "natural_hazard", "name": "Natural Hazards & Climate Security", "letter": "F"},
    {"id": "economic_social", "name": "Economic & Social Conditions", "letter": "G"},
    {"id": "continuity", "name": "Business Continuity & Resilience", "letter": "H"},
]
CATEGORY_IDS = [c["id"] for c in CATEGORIES]
CATEGORY_NAMES = {c["id"]: c["name"] for c in CATEGORIES}

# --------------------------------------------------------------------------
# Rating scales (ordered low -> high where relevant)
# --------------------------------------------------------------------------
URGENCY_LEVELS = ["Long-Term", "7 Days", "24 Hours", "Immediate"]
GEO_SCOPE_LEVELS = ["Local", "National", "Regional", "Global"]
IMPACT_LEVELS = ["Low", "Moderate", "High", "Critical"]
LIKELIHOOD_LEVELS = ["Rare", "Unlikely", "Possible", "Likely", "Almost Certain"]
VELOCITY_LEVELS = ["Slow", "Developing", "Fast", "Immediate"]
CONFIDENCE_LEVELS = ["Unverified", "Low", "Moderate", "High", "Confirmed"]
TREND_LEVELS = ["Improving", "Stable", "Deteriorating", "Rapidly Deteriorating"]

# Regulatory lifecycle status (D requires we never present a proposal as law)
REG_STATUS = ["rumor", "proposal", "draft", "enacted", "effective", "enforced"]

# Recommended-action verbs
ACTION_TYPES = ["Monitor", "Validate", "Assess", "Communicate", "Mitigate", "Escalate"]

# Source tiers (1 authoritative -> 4 early-warning signal)
SOURCE_TIERS = {
    1: "Primary / authoritative",
    2: "High-quality independent reporting",
    3: "Specialist / research",
    4: "Early-warning / unverified signal",
}

# Claim provenance types (analytical guardrail: distinguish these clearly)
CLAIM_TYPES = [
    "fact",
    "official_claim",
    "witness_report",
    "analyst_judgment",
    "inference",
    "forecast",
    "scenario",
    "rumor",
    "disinformation",
]

# --------------------------------------------------------------------------
# Default personalization (suggested watchlist)
# --------------------------------------------------------------------------
DEFAULT_WATCHLIST_COUNTRIES = [
    "us", "eu", "gb", "in", "cn", "mx", "br", "hu", "fr", "de",
]

DEFAULT_TOPICS = [
    "corporate security", "grc", "site security", "nis2", "ctpat",
    "critical infrastructure", "supply chains", "civil unrest", "terrorism",
    "workplace violence", "cargo theft", "customs", "sanctions",
    "physical security", "cyber-physical risk", "business continuity",
    "industrial security",
]


def clamp_scale(value: str, scale: list[str], default: str) -> str:
    """Return value if it is a member of scale, else default."""
    return value if value in scale else default
