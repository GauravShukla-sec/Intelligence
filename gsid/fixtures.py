"""Demo fixtures — CLEARLY MARKED illustrative scenarios.

IMPORTANT: These are synthetic, illustrative scenarios used to demonstrate the
platform's analysis when live sources are not configured. They are NOT current
news. Every demo story is flagged `is_demo=True`, uses demo citation URLs on
the reserved `demo.example.org` domain, and the UI labels them "DEMO DATA".

The scenarios are plausible and security-relevant so the analysis is realistic,
but names, quotations, figures and links are fictional and must never be
presented as real reporting.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .store import DraftClaim, DraftSource, StoryDraft

# Anchor demo timestamps to "recent" relative to an assumed run date so the
# freshness UI behaves. These remain clearly demo regardless of real date.
_BASE = datetime(2026, 7, 23, 6, 0, tzinfo=timezone.utc)


def _iso(hours_ago: float) -> str:
    return (_BASE - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _demo_url(slug: str) -> str:
    return f"https://demo.example.org/illustrative/{slug}"


# Approximate display coordinates by primary country (schematic map only).
_COUNTRY_COORDS = {
    "ye": (12.6, 43.4), "de": (51.1, 10.4), "mx": (19.4, -99.1),
    "in": (19.0, 72.8), "kr": (35.1, 129.0), "ke": (-1.29, 36.8),
    "us": (38.9, -77.0), "es": (40.4, -3.7), "th": (15.8, 100.9),
    "kz": (43.2, 76.9), "au": (-19.3, 146.8),
}


def demo_stories() -> list[StoryDraft]:
    stories = _demo_stories()
    for s in stories:  # populate map coordinates where not explicitly set
        if s.lat is None and s.primary_country in _COUNTRY_COORDS:
            s.lat, s.lon = _COUNTRY_COORDS[s.primary_country]
    return stories


def _demo_stories() -> list[StoryDraft]:
    return [
        # 1) MENA — maritime chokepoint / supply chain (critical alert)
        StoryDraft(
            story_id="demo_redsea_transit",
            headline="[DEMO] Shipping advisories tighten as vessels reroute around a key maritime chokepoint",
            body=(
                "Several container lines issued advisories recommending vessels avoid a "
                "narrow strait after a series of attacks and incidents against commercial "
                "shipping. Two operators suspended transits and announced diversions adding "
                "an estimated 10–14 days to Asia–Europe freight, and port congestion is "
                "building at alternate hubs, disrupting logistics schedules. A regional naval "
                "coalition reported increased patrols amid warnings of further escalation. "
                "No crew casualties have been confirmed by authorities."
            ),
            category="supply_chain",
            location_text="Regional maritime chokepoint (MENA)",
            primary_country="ye",
            countries=["ye", "eg", "sa", "sg", "nl"],
            lat=12.6, lon=43.4,
            event_time=_iso(6),
            status="ongoing",
            sources=[
                DraftSource("International maritime security bulletin (DEMO)",
                            _demo_url("maritime-advisory"), tier=1, source_type="international_org",
                            country="int", is_primary=True, title="Advisory: transit risk elevated",
                            published_at=_iso(7)),
                DraftSource("Global wire service (DEMO)", _demo_url("wire-reroute"), tier=2,
                            source_type="wire", country="gb", title="Carriers divert around strait",
                            published_at=_iso(6)),
                DraftSource("Regional outlet (DEMO)", _demo_url("regional-strait"), tier=3,
                            source_type="newspaper", country="eg", title="Local port impact grows",
                            published_at=_iso(5)),
            ],
            claims=[
                DraftClaim("A maritime security body recommended vessels avoid the strait.",
                           claim_type="official_claim", attributed_to="maritime security bulletin",
                           corroboration="primary", source_index=0),
                DraftClaim("Two operators announced diversions adding 10–14 days to transit.",
                           claim_type="fact", attributed_to="global wire service",
                           corroboration="multiple", source_index=1),
                DraftClaim("Reports of crew casualties remain unconfirmed by authorities.",
                           claim_type="inference", attributed_to="analyst judgment",
                           corroboration="none", source_index=2),
            ],
            events=[
                {"occurred": _iso(30), "title": "First incident reported", "detail": "Initial advisory issued."},
                {"occurred": _iso(12), "title": "Carriers announce diversions", "detail": "Two operators reroute."},
                {"occurred": _iso(6), "title": "Patrols increased", "detail": "Coalition reports response."},
            ],
            is_demo=True,
        ),
        # 2) Europe — NIS2 regulatory (regulatory)
        StoryDraft(
            story_id="demo_nis2_enforcement",
            headline="[DEMO] National regulator publishes first NIS2 enforcement guidance and reporting portal",
            body=(
                "A European national competent authority published guidance clarifying "
                "incident-reporting timelines under its NIS2 transposition, including the "
                "24-hour early-warning and 72-hour notification expectations for essential "
                "and important entities, and opened an online reporting portal. The guidance "
                "confirms the framework is in effect for in-scope entities."
            ),
            category="regulatory",
            location_text="European Union member state",
            primary_country="de",
            countries=["de", "eu"],
            event_time=_iso(20),
            status="effective",
            sources=[
                DraftSource("National competent authority (DEMO)", _demo_url("nis2-guidance"),
                            tier=1, source_type="regulator", country="de", is_primary=True,
                            title="NIS2 incident-reporting guidance", published_at=_iso(20)),
                DraftSource("EU affairs outlet (DEMO)", _demo_url("nis2-analysis"), tier=3,
                            source_type="newspaper", country="be", title="What the guidance means",
                            published_at=_iso(18)),
            ],
            claims=[
                DraftClaim("The authority published NIS2 incident-reporting guidance and a portal.",
                           claim_type="official_claim", attributed_to="national competent authority",
                           corroboration="primary", source_index=0),
                DraftClaim("Guidance restates 24-hour early-warning and 72-hour notification steps.",
                           claim_type="fact", attributed_to="national competent authority",
                           corroboration="single", source_index=0),
            ],
            is_demo=True,
        ),
        # 3) LATAM — cargo theft / organized crime (supply chain + physical)
        StoryDraft(
            story_id="demo_latam_cargo",
            headline="[DEMO] Organized cargo-theft ring targets logistics corridor; authorities announce task force",
            body=(
                "Police reported a rise in organized cargo theft along a major highway "
                "corridor, including hijackings of trucks carrying electronics and "
                "pharmaceuticals. A federal task force was announced. Industry associations "
                "urged shippers to review seal integrity and route security."
            ),
            category="supply_chain",
            location_text="Major highway logistics corridor (Latin America)",
            primary_country="mx",
            countries=["mx"],
            event_time=_iso(40),
            status="ongoing",
            sources=[
                DraftSource("Federal police statement (DEMO)", _demo_url("cargo-taskforce"),
                            tier=1, source_type="government", country="mx", is_primary=True,
                            title="Task force on cargo theft", published_at=_iso(40)),
                DraftSource("Logistics trade association (DEMO)", _demo_url("cargo-advisory"),
                            tier=3, source_type="industry", country="mx",
                            title="Shipper security advisory", published_at=_iso(38)),
            ],
            claims=[
                DraftClaim("Police reported increased organized cargo theft on the corridor.",
                           claim_type="official_claim", attributed_to="federal police",
                           corroboration="primary", source_index=0),
                DraftClaim("An industry group advised reviewing seal integrity and routing.",
                           claim_type="fact", attributed_to="trade association",
                           corroboration="single", source_index=1),
            ],
            is_demo=True,
        ),
        # 4) South Asia — civil unrest near sites (physical + people)
        StoryDraft(
            story_id="demo_southasia_unrest",
            headline="[DEMO] Large protests over fuel prices disrupt movement near an industrial belt",
            body=(
                "Escalating demonstrations against fuel-price increases blocked several "
                "arterial roads near an industrial zone, and clashes with police were "
                "reported. Local authorities imposed a curfew and temporary movement "
                "restrictions in two districts during evening hours. Most factories remained "
                "operational but reported staff-access delays and disruption to inbound "
                "trucking. No serious injuries were confirmed by officials."
            ),
            category="physical_corporate",
            location_text="Industrial belt, South Asia",
            primary_country="in",
            countries=["in"],
            event_time=_iso(10),
            status="developing",
            sources=[
                DraftSource("State police notice (DEMO)", _demo_url("unrest-restrictions"),
                            tier=1, source_type="government", country="in", is_primary=True,
                            title="Temporary movement restrictions", published_at=_iso(10)),
                DraftSource("National newspaper (DEMO)", _demo_url("unrest-report"), tier=2,
                            source_type="newspaper", country="in", title="Protests block roads",
                            published_at=_iso(9)),
                DraftSource("Local reporter social post (DEMO)", _demo_url("unrest-social"),
                            tier=4, source_type="social", country="in",
                            title="Unverified footage of gatherings", published_at=_iso(8)),
            ],
            claims=[
                DraftClaim("Authorities imposed evening movement restrictions in two districts.",
                           claim_type="official_claim", attributed_to="state police",
                           corroboration="primary", source_index=0),
                DraftClaim("Facilities stayed operational but reported staff-access delays.",
                           claim_type="witness_report", attributed_to="national newspaper",
                           corroboration="single", source_index=1),
                DraftClaim("Circulating footage of crowd size is unverified.",
                           claim_type="rumor", attributed_to="social media",
                           corroboration="none", source_index=2),
            ],
            is_demo=True,
        ),
        # 5) East Asia — cyber-physical / OT (cyber-physical)
        StoryDraft(
            story_id="demo_eastasia_ot",
            headline="[DEMO] Ransomware disrupts a regional logistics operator's terminal systems",
            body=(
                "A logistics operator disclosed a ransomware incident affecting terminal "
                "operating systems and industrial control processes at two port facilities, "
                "forcing a shutdown of automated gates, manual fallback processing and "
                "significant cargo delays. The company said safety systems were unaffected "
                "and engaged incident responders. A national CERT issued a related advisory "
                "on intrusions into operational technology at logistics hubs."
            ),
            category="cyber_physical",
            location_text="Port terminals, East Asia",
            primary_country="kr",
            countries=["kr"],
            event_time=_iso(16),
            status="ongoing",
            sources=[
                DraftSource("Company disclosure (DEMO)", _demo_url("ot-disclosure"), tier=1,
                            source_type="corporate", country="kr", is_primary=True,
                            title="Notice of cybersecurity incident", published_at=_iso(16)),
                DraftSource("National CERT advisory (DEMO)", _demo_url("ot-cert"), tier=1,
                            source_type="government", country="kr", is_primary=True,
                            title="Advisory on terminal-system intrusions", published_at=_iso(15)),
                DraftSource("Trade press (DEMO)", _demo_url("ot-tradepress"), tier=3,
                            source_type="newspaper", country="sg", title="Gate delays reported",
                            published_at=_iso(14)),
            ],
            claims=[
                DraftClaim("The operator disclosed ransomware affecting terminal systems.",
                           claim_type="official_claim", attributed_to="company disclosure",
                           corroboration="primary", source_index=0),
                DraftClaim("The company states safety systems were unaffected.",
                           claim_type="official_claim", attributed_to="company disclosure",
                           corroboration="single", source_index=0),
                DraftClaim("A national CERT issued a related advisory.",
                           claim_type="fact", attributed_to="national CERT",
                           corroboration="primary", source_index=1),
            ],
            is_demo=True,
        ),
        # 6) Sub-Saharan Africa — natural hazard (natural)
        StoryDraft(
            story_id="demo_ssa_flood",
            headline="[DEMO] Seasonal flooding damages road links and a distribution hub",
            body=(
                "Heavy seasonal rains caused flooding that damaged bridges on a key inland "
                "route and inundated part of a distribution hub. A regional disaster agency "
                "issued alerts and opened relief coordination. Power was intermittent in "
                "affected districts."
            ),
            category="natural_hazard",
            location_text="Inland districts, Sub-Saharan Africa",
            primary_country="ke",
            countries=["ke"],
            event_time=_iso(28),
            status="ongoing",
            sources=[
                DraftSource("Regional disaster agency (DEMO)", _demo_url("flood-alert"), tier=1,
                            source_type="government", country="ke", is_primary=True,
                            title="Flood alert and relief coordination", published_at=_iso(28)),
                DraftSource("Humanitarian update (DEMO)", _demo_url("flood-humanitarian"),
                            tier=1, source_type="humanitarian", country="int",
                            title="Situation report", published_at=_iso(26)),
            ],
            claims=[
                DraftClaim("Flooding damaged bridges on a key inland route.",
                           claim_type="official_claim", attributed_to="disaster agency",
                           corroboration="primary", source_index=0),
                DraftClaim("Power was intermittent in affected districts.",
                           claim_type="witness_report", attributed_to="humanitarian update",
                           corroboration="single", source_index=1),
            ],
            is_demo=True,
        ),
        # 7) North America — sanctions / export control (regulatory)
        StoryDraft(
            story_id="demo_na_sanctions",
            headline="[DEMO] New export-control listing adds entities in a critical-components sector",
            body=(
                "A national authority added several entities to an export-control list, "
                "restricting transfers of certain dual-use components. The measure takes "
                "effect after a short wind-down period. Compliance teams must screen order "
                "books and distributor networks for exposure."
            ),
            category="regulatory",
            location_text="North America (national measure)",
            primary_country="us",
            countries=["us", "cn"],
            event_time=_iso(22),
            status="enacted",
            sources=[
                DraftSource("Export-control authority (DEMO)", _demo_url("export-listing"),
                            tier=1, source_type="regulator", country="us", is_primary=True,
                            title="Entity list update", published_at=_iso(22)),
            ],
            claims=[
                DraftClaim("The authority added entities to an export-control list.",
                           claim_type="official_claim", attributed_to="export-control authority",
                           corroboration="primary", source_index=0),
                DraftClaim("The measure takes effect after a short wind-down period.",
                           claim_type="fact", attributed_to="export-control authority",
                           corroboration="single", source_index=0),
            ],
            is_demo=True,
        ),
        # 8) Europe — energy / continuity (continuity)
        StoryDraft(
            story_id="demo_eu_grid",
            headline="[DEMO] Grid operator warns of rolling load management during heat-driven demand peak",
            body=(
                "A transmission operator warned that a prolonged heatwave could require "
                "short, planned load-management steps during evening peaks. Industrial users "
                "were asked to prepare demand-response plans. No unplanned outages had "
                "occurred at the time of the notice."
            ),
            category="continuity",
            location_text="Southern Europe",
            primary_country="es",
            countries=["es"],
            event_time=_iso(13),
            status="developing",
            sources=[
                DraftSource("Transmission system operator (DEMO)", _demo_url("grid-notice"),
                            tier=1, source_type="government", country="es", is_primary=True,
                            title="Load-management preparedness notice", published_at=_iso(13)),
                DraftSource("Business daily (DEMO)", _demo_url("grid-business"), tier=2,
                            source_type="newspaper", country="es", title="Industry asked to prepare",
                            published_at=_iso(12)),
            ],
            claims=[
                DraftClaim("The operator warned of possible short planned load-management steps.",
                           claim_type="official_claim", attributed_to="transmission operator",
                           corroboration="primary", source_index=0),
                DraftClaim("No unplanned outages had occurred at the time of the notice.",
                           claim_type="fact", attributed_to="transmission operator",
                           corroboration="single", source_index=0),
            ],
            is_demo=True,
        ),
        # 9) Southeast Asia — geopolitical / border (geopolitical)
        StoryDraft(
            story_id="demo_sea_border",
            headline="[DEMO] Border crossing sees intermittent closures amid a bilateral dispute",
            body=(
                "A land border crossing experienced intermittent closures during a bilateral "
                "dispute over transit fees. Freight queues lengthened. Both governments said "
                "talks were ongoing. Passenger movement was periodically suspended."
            ),
            category="geopolitical",
            location_text="Land border crossing, Southeast Asia",
            primary_country="th",
            countries=["th", "mm"],
            event_time=_iso(34),
            status="developing",
            sources=[
                DraftSource("Government statement (DEMO)", _demo_url("border-statement"),
                            tier=1, source_type="government", country="th", is_primary=True,
                            title="Statement on border operations", published_at=_iso(34)),
                DraftSource("Regional wire (DEMO)", _demo_url("border-wire"), tier=2,
                            source_type="wire", country="sg", title="Freight queues lengthen",
                            published_at=_iso(33)),
            ],
            claims=[
                DraftClaim("The crossing saw intermittent closures amid a fee dispute.",
                           claim_type="official_claim", attributed_to="government statement",
                           corroboration="primary", source_index=0),
                DraftClaim("Both governments said talks were ongoing.",
                           claim_type="official_claim", attributed_to="government statement",
                           corroboration="single", source_index=0),
            ],
            is_demo=True,
        ),
        # 10) Global — disinformation / cyber-physical (cyber-physical, lower score)
        StoryDraft(
            story_id="demo_global_deepfake",
            headline="[DEMO] Deepfake audio impersonating an executive circulates before earnings",
            body=(
                "A synthetic audio clip impersonating a company executive circulated on "
                "social platforms ahead of an earnings call. The company said the clip was "
                "fabricated. Security teams flagged the incident as an information-manipulation "
                "and social-engineering risk."
            ),
            category="cyber_physical",
            location_text="Global (online)",
            primary_country="us",
            countries=["us"],
            event_time=_iso(5),
            status="developing",
            sources=[
                DraftSource("Company statement (DEMO)", _demo_url("deepfake-statement"),
                            tier=1, source_type="corporate", country="us", is_primary=True,
                            title="Statement on fabricated audio", published_at=_iso(5)),
                DraftSource("Security vendor blog (DEMO)", _demo_url("deepfake-vendor"),
                            tier=3, source_type="vendor", country="us",
                            title="Analysis of the clip", published_at=_iso(4)),
            ],
            claims=[
                DraftClaim("The company said the circulating executive audio was fabricated.",
                           claim_type="official_claim", attributed_to="company statement",
                           corroboration="primary", source_index=0),
                DraftClaim("A vendor characterized it as an information-manipulation risk.",
                           claim_type="analyst_judgment", attributed_to="security vendor",
                           corroboration="single", source_index=1),
            ],
            is_demo=True,
        ),
        # 11) Central Asia — no-material-change style low-severity (economic/social)
        StoryDraft(
            story_id="demo_ca_labor",
            headline="[DEMO] Localized transport-sector strike ends after wage agreement",
            body=(
                "A short strike by transport workers in one city ended after a wage "
                "agreement. Services resumed. The dispute did not spread to other regions."
            ),
            category="economic_social",
            location_text="Regional city, Central Asia",
            primary_country="kz",
            countries=["kz"],
            event_time=_iso(50),
            status="resolved",
            sources=[
                DraftSource("Local outlet (DEMO)", _demo_url("labor-resolved"), tier=3,
                            source_type="newspaper", country="kz", title="Strike ends",
                            published_at=_iso(50)),
            ],
            claims=[
                DraftClaim("A transport-sector strike ended after a wage agreement.",
                           claim_type="fact", attributed_to="local outlet",
                           corroboration="single", source_index=0),
            ],
            is_demo=True,
        ),
        # 12) Australia/Pacific — natural hazard (moderate)
        StoryDraft(
            story_id="demo_ap_cyclone",
            headline="[DEMO] Meteorological agency issues cyclone watch for a coastal industrial region",
            body=(
                "A national meteorological agency issued a cyclone watch for a coastal region "
                "hosting ports and processing facilities, forecasting damaging winds within "
                "48–72 hours. Authorities advised preparedness measures. No landfall had "
                "occurred at the time of the watch."
            ),
            category="natural_hazard",
            location_text="Coastal industrial region, Australia/Pacific",
            primary_country="au",
            countries=["au"],
            event_time=_iso(8),
            status="developing",
            sources=[
                DraftSource("Meteorological agency (DEMO)", _demo_url("cyclone-watch"), tier=1,
                            source_type="government", country="au", is_primary=True,
                            title="Cyclone watch issued", published_at=_iso(8)),
            ],
            claims=[
                DraftClaim("The agency issued a cyclone watch forecasting damaging winds in 48–72h.",
                           claim_type="official_claim", attributed_to="meteorological agency",
                           corroboration="primary", source_index=0),
            ],
            is_demo=True,
        ),
    ]


# --------------------------------------------------------------------------
# Demo regulations (D-domain tracker)
# --------------------------------------------------------------------------
def demo_regulations() -> list[dict]:
    return [
        {
            "id": "reg_nis2", "title": "[DEMO] NIS2 Directive transposition & reporting guidance",
            "jurisdiction": "EU member state", "framework": "NIS2", "status": "effective",
            "effective_date": "2024-10-18", "story_id": "demo_nis2_enforcement",
            "affected": "Essential & important entities in scope (many manufacturers, logistics, digital infrastructure).",
            "obligations": "Risk-management measures, governance accountability, supply-chain security, incident handling.",
            "reporting": "Early warning within 24h; incident notification within 72h; final report within 1 month.",
            "penalties": "Administrative fines and management-liability provisions per national transposition.",
            "implications": "Formalize incident-reporting runbooks; align OT/physical-security convergence controls.",
            "prep_steps": "Confirm in-scope status; map reporting workflow; test 24/72h timelines; brief management.",
            "source_url": _demo_url("nis2-guidance"),
        },
        {
            "id": "reg_ctpat", "title": "[DEMO] CTPAT Minimum Security Criteria — periodic review reminder",
            "jurisdiction": "United States (CBP)", "framework": "CTPAT", "status": "enforced",
            "effective_date": "2020-01-01",
            "affected": "CTPAT-certified importers, carriers, and eligible supply-chain partners.",
            "obligations": "Maintain MSC across cybersecurity, conveyance/seal, physical access, and agricultural criteria.",
            "reporting": "Report incidents/anomalies; annual security profile review; address post-incident corrective actions.",
            "penalties": "Suspension/removal from the program; loss of trade-facilitation benefits.",
            "implications": "Sync seal chain-of-custody and site controls with current cargo-theft advisories.",
            "prep_steps": "Re-verify seal procedures; validate access control & CCTV; close open corrective actions.",
            "source_url": _demo_url("ctpat-msc"),
        },
        {
            "id": "reg_export", "title": "[DEMO] Export-control entity-list update (critical components)",
            "jurisdiction": "North America", "framework": "Export Control", "status": "enacted",
            "effective_date": "2026-08-01", "story_id": "demo_na_sanctions",
            "affected": "Exporters, distributors and OEMs handling listed dual-use components.",
            "obligations": "Screen counterparties against updated list; obtain licenses where required.",
            "reporting": "Maintain screening records; report attempted prohibited transactions.",
            "penalties": "Civil/criminal penalties; denial of export privileges.",
            "implications": "Immediate order-book and distributor screening; hold shipments pending review.",
            "prep_steps": "Re-run restricted-party screening; brief trade-compliance and sales; document decisions.",
            "source_url": _demo_url("export-listing"),
        },
        {
            "id": "reg_cer", "title": "[DEMO] CER Directive — critical-entity resilience obligations (proposal-to-effective tracker)",
            "jurisdiction": "European Union", "framework": "CER", "status": "effective",
            "effective_date": "2024-10-18",
            "affected": "Entities designated critical in energy, transport, manufacturing, food, and more.",
            "obligations": "Resilience risk assessments, resilience measures, incident notification, background checks where permitted.",
            "reporting": "Notify significant incidents to the competent authority per national rules.",
            "penalties": "Per national transposition; oversight and enforcement by designated authorities.",
            "implications": "Aligns physical resilience with cyber (NIS2); update BIA and site criticality.",
            "prep_steps": "Confirm designation status; integrate CER into ERM; align with NIS2 workstream.",
            "source_url": _demo_url("cer-directive"),
        },
    ]


# --------------------------------------------------------------------------
# Demo quiz questions & scenarios
# --------------------------------------------------------------------------
def demo_quiz() -> list[dict]:
    return [
        {
            "id": "q_confidence", "difficulty": 2,
            "question": "A single social-media video is the only source for a claimed factory fire. "
                        "What confidence level is appropriate before corroboration?",
            "options": ["Confirmed", "High", "Moderate", "Unverified"],
            "answer_index": 3,
            "explanation": "A single, uncorroborated social signal is 'Unverified' until a stronger "
                           "source confirms it. Use it as an alerting signal only.",
        },
        {
            "id": "q_nis2_timeline", "difficulty": 2,
            "question": "Under a typical NIS2 transposition, what is the early-warning window after "
                        "becoming aware of a significant incident?",
            "options": ["24 hours", "72 hours", "7 days", "30 days"],
            "answer_index": 0,
            "explanation": "An early warning is expected within 24 hours, an incident notification "
                           "within 72 hours, and a final report within one month.",
        },
        {
            "id": "q_relevance_top", "difficulty": 1,
            "question": "In this platform's relevance model, which dimension carries the most points?",
            "options": ["Regulatory impact", "Threat to people/employee safety",
                        "Cyber-physical impact", "Reputational impact"],
            "answer_index": 1,
            "explanation": "Threat to people/employee safety is weighted highest (20 points), "
                           "reflecting duty-of-care priority.",
        },
        {
            "id": "q_velocity", "difficulty": 3,
            "question": "'Risk velocity' primarily describes:",
            "options": ["How likely a risk is", "How severe the impact is",
                        "How quickly a risk materializes into impact", "How many sites are affected"],
            "answer_index": 2,
            "explanation": "Velocity is the speed at which a risk moves from onset to impact — key "
                           "for deciding response tempo.",
        },
    ]


def demo_scenarios() -> list[dict]:
    return [
        {
            "id": "scn_protest", "story_id": "demo_southasia_unrest",
            "title": "Protests near an industrial belt",
            "prompt": "You manage security for a facility 20 km from expanding fuel-price protests. "
                      "Transport is operational but evening movement restrictions are in force in two "
                      "districts and night-shift staff are concerned. What do you do first?",
            "principle": "Proportionate response + duty of care: validate exposure and communicate "
                         "before disrupting operations.",
            "options": [
                {"text": "Immediately shut the site and send everyone home.",
                 "strengths": "Maximally cautious for safety.",
                 "blindspots": "Likely disproportionate; creates its own movement risk during "
                               "restrictions; operational and financial impact without validated threat.",
                 "better": "Validate the specific threat to your access routes first; adjust shift "
                           "timing rather than blanket closure."},
                {"text": "Do nothing; wait for the next news cycle.",
                 "strengths": "No overreaction.",
                 "blindspots": "Ignores a live duty-of-care signal and movement restrictions; fails "
                               "to communicate with concerned staff.",
                 "better": "At minimum, monitor official sources and send staff a clear status update."},
                {"text": "Validate route/threat exposure, brief staff, and adjust night-shift logistics.",
                 "strengths": "Proportionate: confirms real exposure, addresses duty of care, keeps "
                              "operations where safe.",
                 "blindspots": "Requires timely, accurate local information and a working notification channel.",
                 "better": "This is the strongest first move; pair it with defined escalation triggers."},
                {"text": "Escalate to executive crisis management immediately.",
                 "strengths": "Ensures leadership awareness.",
                 "blindspots": "Premature for a localized, contained event; risks alert fatigue and "
                               "diverts crisis resources.",
                 "better": "Escalate only if indicators (spread, injuries, route loss) deteriorate."},
            ],
        },
    ]
