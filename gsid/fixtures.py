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
# Real regulations (D-domain tracker) — curated reference of live frameworks.
# Facts (effective dates, reporting windows) reflect the enacted texts; verify
# national transposition specifics against the linked official source.
# --------------------------------------------------------------------------
def reference_regulations() -> list[dict]:
    return [
        {
            "id": "reg_nis2", "title": "NIS2 Directive (EU 2022/2555) — cybersecurity risk & incident reporting",
            "jurisdiction": "European Union", "framework": "NIS2", "status": "enforced",
            "effective_date": "2024-10-18",
            "affected": "Essential & important entities: energy, transport, banking, health, water, digital infrastructure, ICT service management, public administration, and larger manufacturers.",
            "obligations": "Risk-management measures, management-body accountability, supply-chain security, and incident handling proportionate to risk.",
            "reporting": "Early warning within 24h of awareness; incident notification within 72h; final report within one month.",
            "penalties": "Up to €10m or 2% of global turnover (essential entities); management liability per national transposition.",
            "implications": "Formalize incident-reporting runbooks and OT/IT convergence controls; confirm in-scope status under national law.",
            "prep_steps": "Confirm scope; map the 24/72h/1-month workflow; test timelines; brief the management body on accountability.",
            "source_url": "https://eur-lex.europa.eu/eli/dir/2022/2555/oj",
        },
        {
            "id": "reg_dora", "title": "DORA (EU 2022/2554) — Digital Operational Resilience Act",
            "jurisdiction": "European Union", "framework": "DORA", "status": "enforced",
            "effective_date": "2025-01-17",
            "affected": "Financial entities (banks, insurers, investment firms, crypto-asset providers) and their critical ICT third-party providers.",
            "obligations": "ICT risk-management framework, resilience testing (incl. threat-led penetration testing), and oversight of ICT third parties.",
            "reporting": "Classify and report major ICT-related incidents to competent authorities within regulatory deadlines; maintain a register of information on ICT contracts.",
            "penalties": "Supervisory measures and periodic penalty payments (up to 1% of average daily worldwide turnover for critical ICT providers).",
            "implications": "Map ICT concentration risk; align incident classification with DORA thresholds; update third-party contract clauses.",
            "prep_steps": "Build the register of information; define incident classification; schedule resilience testing.",
            "source_url": "https://eur-lex.europa.eu/eli/reg/2022/2554/oj",
        },
        {
            "id": "reg_cer", "title": "CER Directive (EU 2022/2557) — resilience of critical entities",
            "jurisdiction": "European Union", "framework": "CER", "status": "enforced",
            "effective_date": "2024-10-18",
            "affected": "Entities designated critical across energy, transport, banking, health, water, food, digital infrastructure and public administration.",
            "obligations": "Resilience risk assessments, physical resilience measures, background checks where permitted, and incident notification.",
            "reporting": "Notify significant incidents to the competent authority per national rules.",
            "penalties": "Set by national transposition; oversight by designated authorities.",
            "implications": "Pairs physical resilience with NIS2 cyber duties — align business-impact analysis and site criticality.",
            "prep_steps": "Confirm designation; integrate CER into enterprise risk management; run it alongside the NIS2 workstream.",
            "source_url": "https://eur-lex.europa.eu/eli/dir/2022/2557/oj",
        },
        {
            "id": "reg_csddd", "title": "CSDDD (EU 2024/1760) — Corporate Sustainability Due Diligence",
            "jurisdiction": "European Union", "framework": "CSDDD", "status": "enacted",
            "effective_date": "2027-07-26",
            "affected": "Large EU companies and non-EU companies with substantial EU turnover; effects cascade to suppliers in the chain of activities.",
            "obligations": "Human-rights and environmental due diligence across the chain of activities, plus a climate transition plan.",
            "reporting": "Publish due-diligence outcomes; phased application begins 2027 for the largest companies.",
            "penalties": "Fines set by member states (turnover-based) and civil liability for harms.",
            "implications": "Extend supplier screening beyond security to human-rights/environmental risk; expect cascaded questionnaires.",
            "prep_steps": "Map the chain of activities; establish grievance mechanisms; prepare the climate transition plan.",
            "source_url": "https://eur-lex.europa.eu/eli/dir/2024/1760/oj",
        },
        {
            "id": "reg_cbam", "title": "EU CBAM (Reg 2023/956) — Carbon Border Adjustment Mechanism",
            "jurisdiction": "European Union", "framework": "CBAM", "status": "effective",
            "effective_date": "2026-01-01",
            "affected": "Importers into the EU of iron & steel, aluminium, cement, fertilisers, electricity and hydrogen.",
            "obligations": "Definitive regime from 2026: authorised CBAM declarant status, purchase/surrender of CBAM certificates for embedded emissions.",
            "reporting": "Annual CBAM declaration of embedded emissions; the transitional reporting phase ran from Oct 2023.",
            "penalties": "Penalties for missing certificate surrender, broadly aligned with the EU ETS excess-emissions penalty.",
            "implications": "Obtain verified emissions data from non-EU suppliers; budget for certificate costs in landed price.",
            "prep_steps": "Register as an authorised declarant; collect supplier emissions data; model certificate exposure.",
            "source_url": "https://taxation-customs.ec.europa.eu/carbon-border-adjustment-mechanism_en",
        },
        {
            "id": "reg_eudr", "title": "EUDR (EU 2023/1115) — Deforestation-free products regulation",
            "jurisdiction": "European Union", "framework": "EUDR", "status": "effective",
            "effective_date": "2025-12-30",
            "affected": "Operators and traders placing cattle, cocoa, coffee, oil palm, rubber, soya and wood (and derived products) on the EU market.",
            "obligations": "Due diligence proving products are deforestation-free and legal, with geolocation of production plots.",
            "reporting": "Submit due-diligence statements via the EU information system; large operators from 30 Dec 2025, SMEs from 30 Jun 2026.",
            "penalties": "Fines up to at least 4% of EU turnover, confiscation of products/revenues, exclusion from public procurement.",
            "implications": "Collect plot-level geolocation from agricultural suppliers; integrate traceability into procurement.",
            "prep_steps": "Identify in-scope commodities; obtain geolocation data; build the due-diligence statement workflow.",
            "source_url": "https://environment.ec.europa.eu/topics/forests/deforestation/regulation-deforestation-free-products_en",
        },
        {
            "id": "reg_ai_act", "title": "EU AI Act (Reg 2024/1689) — risk-based AI regulation",
            "jurisdiction": "European Union", "framework": "EU AI Act", "status": "effective",
            "effective_date": "2026-08-02",
            "affected": "Providers and deployers of AI systems placed on or used in the EU market.",
            "obligations": "Phased: prohibited practices since Feb 2025; general-purpose AI duties since Aug 2025; high-risk system obligations from Aug 2026.",
            "reporting": "Serious-incident reporting for high-risk systems; conformity assessment and registration in the EU database.",
            "penalties": "Up to €35m or 7% of global turnover for prohibited-practice breaches.",
            "implications": "Inventory AI systems and classify by risk tier; assign accountability for high-risk deployments.",
            "prep_steps": "Build an AI system inventory; screen for prohibited uses; prepare conformity documentation for high-risk uses.",
            "source_url": "https://eur-lex.europa.eu/eli/reg/2024/1689/oj",
        },
        {
            "id": "reg_ctpat", "title": "US CTPAT — Customs-Trade Partnership Against Terrorism (Minimum Security Criteria)",
            "jurisdiction": "United States (CBP)", "framework": "CTPAT", "status": "enforced",
            "effective_date": "2020-01-01",
            "affected": "CTPAT-certified importers, carriers, and eligible supply-chain partners seeking trade-facilitation benefits.",
            "obligations": "Maintain the Minimum Security Criteria across cybersecurity, conveyance & seal, physical access, and agricultural security.",
            "reporting": "Report incidents/anomalies to CBP; complete the annual security profile review and post-incident corrective actions.",
            "penalties": "Suspension or removal from the program and loss of trade-facilitation benefits.",
            "implications": "Sync seal chain-of-custody and site controls with current cargo-theft advisories.",
            "prep_steps": "Re-verify seal procedures; validate access control & CCTV; close open corrective actions.",
            "source_url": "https://www.cbp.gov/border-security/ports-entry/cargo-security/ctpat",
        },
    ]


# --------------------------------------------------------------------------
# Demo regulations (illustrative; only used in demo/hybrid mode)
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
        # ---- difficulty 1 (fundamentals) ----
        {
            "id": "q_advisory_level4", "difficulty": 1,
            "question": "On the standard 1–4 travel-advisory scale, which level means 'Do not travel'?",
            "options": ["Level 1", "Level 2", "Level 3", "Level 4"],
            "answer_index": 3,
            "explanation": "Level 4 is the most severe — 'Do not travel'. Level 1 is 'exercise normal "
                           "precautions'.",
        },
        {
            "id": "q_tier1", "difficulty": 1,
            "question": "A 'Tier 1' source on this desk is:",
            "options": ["A viral social-media post", "A primary/authoritative source such as a "
                        "government agency", "An anonymous tip", "An opinion column"],
            "answer_index": 1,
            "explanation": "Tier 1 = primary/authoritative (e.g., CISA, a foreign ministry). Tier 4 = "
                           "unverified signal.",
        },
        {
            "id": "q_alert_fatigue", "difficulty": 1,
            "question": "Critical Alerts are restricted to prompt-action items mainly to:",
            "options": ["Increase engagement", "Avoid alert fatigue and preserve signal",
                        "Satisfy regulators", "Rank sources"],
            "answer_index": 1,
            "explanation": "If everything is an alert, nothing is. Reserving alerts for action-worthy "
                           "items keeps them meaningful.",
        },
        {
            "id": "q_duty_of_care", "difficulty": 1,
            "question": "'Duty of care' in corporate security refers to:",
            "options": ["Maximizing margin", "The obligation to protect employee/traveller safety",
                        "Data-retention policy", "Vendor selection"],
            "answer_index": 1,
            "explanation": "Duty of care is the organisation's responsibility for the safety of its "
                           "people — it drives the highest relevance weighting.",
        },
        {
            "id": "q_domain_sanctions", "difficulty": 1,
            "question": "A new sanctions designation belongs primarily in which domain?",
            "options": ["Natural hazards", "Laws, Regulations & Compliance", "Cyber-physical",
                        "Employee safety"],
            "answer_index": 1,
            "explanation": "Sanctions are a regulatory/compliance matter, though they often carry "
                           "supply-chain second-order effects.",
        },
        # ---- difficulty 2 (applied) ----
        {
            "id": "q_circular", "difficulty": 2,
            "question": "Three outlets all trace back to the same single wire report. This is:",
            "options": ["Independent corroboration", "Circular reporting", "A primary source",
                        "Confirmed intelligence"],
            "answer_index": 1,
            "explanation": "Repetition of one origin is not corroboration — the desk flags this as "
                           "circular reporting so it doesn't inflate confidence.",
        },
        {
            "id": "q_consensus_worstcase", "difficulty": 2,
            "question": "Two governments rate a destination Level 2 and Level 4. A worst-case "
                        "cross-government consensus reports:",
            "options": ["Level 2", "The average (Level 3)", "Level 4", "No level"],
            "answer_index": 2,
            "explanation": "Worst-case never hides a stricter advisory behind a milder one, so the "
                           "consensus is Level 4 — with the divergence flagged.",
        },
        {
            "id": "q_ctpat", "difficulty": 2,
            "question": "CTPAT is primarily concerned with:",
            "options": ["Data privacy", "Supply-chain and customs security", "Aviation safety",
                        "Financial disclosure"],
            "answer_index": 1,
            "explanation": "CTPAT (Customs-Trade Partnership Against Terrorism) secures the supply "
                           "chain into the US.",
        },
        {
            "id": "q_kev", "difficulty": 2,
            "question": "CISA's KEV catalog lists vulnerabilities that are:",
            "options": ["Theoretical", "Known to be actively exploited", "Already patched everywhere",
                        "Low severity"],
            "answer_index": 1,
            "explanation": "KEV = Known Exploited Vulnerabilities — evidence of active exploitation, so "
                           "they're prioritised for remediation.",
        },
        {
            "id": "q_geo_scope", "difficulty": 2,
            "question": "A development confined to one facility with no spillover is best scoped as:",
            "options": ["Global", "Regional", "National", "Local"],
            "answer_index": 3,
            "explanation": "Geographic scope should match the actual footprint; over-scoping distorts "
                           "prioritisation.",
        },
        {
            "id": "q_provenance", "difficulty": 2,
            "question": "The soundest way to raise confidence in a claim is to:",
            "options": ["Repeat it more often", "Obtain independent corroboration from a higher-tier "
                        "source", "Wait 24 hours", "Increase its prominence"],
            "answer_index": 1,
            "explanation": "Confidence rises with independent, higher-tier corroboration — not with "
                           "repetition or time alone.",
        },
        # ---- difficulty 3 (nuanced) ----
        {
            "id": "q_low_likelihood_high_impact", "difficulty": 3,
            "question": "A low-likelihood but catastrophic-impact event should generally be:",
            "options": ["Ignored as improbable", "Assessed and monitored with contingency planning",
                        "Treated as certain", "Immediately escalated as an active alert"],
            "answer_index": 1,
            "explanation": "Tail risks warrant contingency planning and monitoring even when unlikely — "
                           "impact, not just probability, drives preparedness.",
        },
        {
            "id": "q_second_order", "difficulty": 3,
            "question": "'Second-order' supply-chain impact refers to:",
            "options": ["The first report of an event", "Downstream effects propagating beyond the "
                        "directly affected area", "A second news source", "A backup supplier"],
            "answer_index": 1,
            "explanation": "Second-order effects ripple through interconnected suppliers, routes and "
                           "markets — often exceeding the immediate footprint.",
        },
        {
            "id": "q_partial_warning", "difficulty": 3,
            "question": "A government issues a *partial* (single-region) travel warning. At country "
                        "level it is best treated as:",
            "options": ["Do not travel anywhere in the country", "A prompt to assess that specific "
                        "region, not the whole country", "Irrelevant", "Stronger than a full warning"],
            "answer_index": 1,
            "explanation": "A regional warning is specific; applying it blanket-wide over-reads the "
                           "risk. Assess the named area against your footprint.",
        },
        {
            "id": "q_source_bias", "difficulty": 3,
            "question": "Relying only on English-language wires most directly risks:",
            "options": ["Circular reporting", "Geographic and source bias / blind spots",
                        "Higher confidence", "Faster velocity"],
            "answer_index": 1,
            "explanation": "A narrow source base introduces blind spots; diverse, regional sources "
                           "reduce bias. The desk red-teams for exactly this.",
        },
        {
            "id": "q_trend_vs_status", "difficulty": 3,
            "question": "A story shows 'Status: contained' but 'Trend: deteriorating'. This means:",
            "options": ["A data error", "Contained now, but the indicators are worsening",
                        "The event is over", "It should be deleted"],
            "answer_index": 1,
            "explanation": "Status is the current state; trend is the direction. Contained-but-worsening "
                           "means watch for escalation.",
        },
        {
            "id": "q_staleness", "difficulty": 3,
            "question": "An advisory re-listed on every feed poll but with unchanged content should:",
            "options": ["Generate a new alert each poll", "Not be treated as 'new' unless it materially "
                        "changed", "Raise its confidence", "Be removed"],
            "answer_index": 1,
            "explanation": "Change-detection avoids churn: only a genuine level/content change is 'new'. "
                           "Re-listing the same advice is not an update.",
        },
    ]


def demo_scenarios() -> list[dict]:
    return [
        {
            "id": "scn_protest",
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
        {
            "id": "scn_ransomware",
            "title": "Ransomware at a supplier",
            "prompt": "A Tier-1 supplier reports a ransomware incident that has taken their order "
                      "system offline. They can't confirm whether your data or delivery schedule is "
                      "affected. Your production line has ~6 days of buffer stock. What is your first move?",
            "principle": "Validate exposure and preserve options before committing to costly "
                         "switches; treat unconfirmed scope as developing, not resolved.",
            "options": [
                {"text": "Immediately switch all orders to an alternate supplier.",
                 "strengths": "Removes dependence on the affected supplier fast.",
                 "blindspots": "Expensive and possibly unnecessary before scope is known; alternates "
                               "may need qualification; burns goodwill.",
                 "better": "Confirm impact to your specific SKUs/schedule and buffer first, in parallel "
                           "with readying an alternate."},
                {"text": "Ask the supplier for scope, containment status and expected recovery; check "
                         "your own exposure and buffer coverage; ready an alternate in parallel.",
                 "strengths": "Proportionate: establishes real exposure, uses the buffer window, keeps "
                              "a fallback warm without premature cost.",
                 "blindspots": "Depends on the supplier communicating honestly and promptly.",
                 "better": "Strongest first move; set a decision deadline tied to buffer depletion."},
                {"text": "Wait for the supplier's final incident report before doing anything.",
                 "strengths": "Avoids overreaction.",
                 "blindspots": "Final reports can take weeks; your 6-day buffer may lapse first.",
                 "better": "Act on interim information against a buffer-based deadline."},
                {"text": "Pay to expedite whatever inventory you can, immediately.",
                 "strengths": "Builds cushion.",
                 "blindspots": "Spends before knowing if there's a real shortfall; may not address the "
                               "actual failure point.",
                 "better": "Size any expedite to the validated gap, not to anxiety."},
            ],
        },
        {
            "id": "scn_port_closure",
            "title": "Sudden port disruption on a key route",
            "prompt": "A labour action closes a port that handles ~30% of your inbound sea freight, "
                      "with no announced end date. Diversions to the next port add ~5 days and cost. "
                      "How do you respond?",
            "principle": "Match the response to route criticality and confirmed duration; avoid both "
                         "denial and panic re-routing.",
            "options": [
                {"text": "Assume it resolves in a day or two and hold.",
                 "strengths": "No wasted diversion cost if it's brief.",
                 "blindspots": "Open-ended closures often run long; waiting erodes lead time you can't "
                               "recover.",
                 "better": "Set a go/no-go trigger and pre-book diversion capacity now."},
                {"text": "Identify which shipments are time-critical, pre-book diversion/alternate-mode "
                         "capacity for those, and set a trigger to divert the rest if closure persists.",
                 "strengths": "Prioritises by criticality, secures scarce alternate capacity early, "
                              "keeps a decision rule.",
                 "blindspots": "Requires shipment-level visibility and quick carrier coordination.",
                 "better": "Strongest move; brief customers on any at-risk commitments proactively."},
                {"text": "Divert everything to the alternate port immediately.",
                 "strengths": "Simple, removes exposure to the closed port.",
                 "blindspots": "Pays the 5-day + cost penalty on non-urgent freight too; may congest "
                               "the alternate.",
                 "better": "Divert by priority, not wholesale."},
                {"text": "Escalate to the executive team for a decision.",
                 "strengths": "Ensures visibility for a material disruption.",
                 "blindspots": "Escalation without options/recommendation slows response.",
                 "better": "Escalate with a recommended plan and trigger, not just the problem."},
            ],
        },
        {
            "id": "scn_advisory_escalation",
            "title": "Advisory escalates mid-trip",
            "prompt": "Two employees are already in-country when the destination's advisory jumps from "
                      "Level 2 to Level 3 ('reconsider travel') for the region they're in, citing rising "
                      "unrest. They are safe and their meetings finish in 48 hours. What do you do?",
            "principle": "Duty of care with proportionality: act on the specific change, keep the "
                         "travellers informed, and avoid creating new risk through hasty movement.",
            "options": [
                {"text": "Order them to leave on the next available flight regardless of timing.",
                 "strengths": "Maximally cautious.",
                 "blindspots": "Rushed movement during unrest can be riskier than sheltering; may be "
                               "disproportionate to a Level 3 (not Level 4).",
                 "better": "Assess routes/airport access and the specific threat before mandating "
                           "immediate departure."},
                {"text": "Do nothing; they're safe and nearly done.",
                 "strengths": "No disruption.",
                 "blindspots": "Ignores a live change in official risk and duty-of-care communication.",
                 "better": "At minimum contact them, confirm status, and review contingency options."},
                {"text": "Contact them, confirm safety and location, review the specific regional "
                         "warning and airport/route access, and set departure triggers.",
                 "strengths": "Proportionate duty of care: informed, keeps options open, tied to real "
                              "indicators.",
                 "blindspots": "Needs a reliable comms channel and current local information.",
                 "better": "Strongest first move; define what would trigger early extraction."},
                {"text": "Escalate to executive crisis management immediately.",
                 "strengths": "Leadership awareness.",
                 "blindspots": "Premature for a Level-3, travellers-safe situation; risks alert fatigue.",
                 "better": "Escalate if it reaches Level 4 or access deteriorates."},
            ],
        },
        {
            "id": "scn_reporting_duty",
            "title": "A possible regulatory reporting clock",
            "prompt": "Your security team detects a significant network intrusion at an EU operating "
                      "entity. Under NIS2-style rules an early warning may be due within 24 hours. "
                      "Forensics are still confirming scope. What is the priority?",
            "principle": "Meet mandatory notification windows on time with what you know; regulatory "
                         "duties don't wait for a complete picture.",
            "options": [
                {"text": "Wait until forensics fully confirm scope before notifying anyone.",
                 "strengths": "Avoids reporting inaccuracies.",
                 "blindspots": "Can blow the 24-hour early-warning window; late notification is itself a "
                               "violation.",
                 "better": "File the early warning with current known facts; update as forensics mature."},
                {"text": "Confirm the applicable jurisdictions/entities and reporting clocks, and "
                         "prepare an early warning with current facts while forensics continue.",
                 "strengths": "Protects compliance timing and preserves accuracy through updates.",
                 "blindspots": "Requires knowing which regimes apply to which entity.",
                 "better": "Strongest move; loop in legal/compliance to own the filing."},
                {"text": "Publicly disclose the breach immediately to be safe.",
                 "strengths": "Maximum transparency.",
                 "blindspots": "Premature public disclosure can be legally and operationally damaging "
                               "and may not be what the regulation requires.",
                 "better": "Follow the required regulator notification path first; coordinate any public "
                           "statement with legal."},
                {"text": "Treat it purely as a technical incident and skip compliance.",
                 "strengths": "Faster technical response.",
                 "blindspots": "Ignores a legal duty with real penalties; the two tracks must run "
                               "together.",
                 "better": "Run containment and the notification clock in parallel."},
            ],
        },
        {
            "id": "scn_flood_warehouse",
            "title": "Flood warning near a distribution hub",
            "prompt": "A credible 48–72h forecast warns of major flooding near your main regional "
                      "distribution centre. It's operational now. Moving stock is costly and the "
                      "forecast has uncertainty. What is your first move?",
            "principle": "Use the lead time a forecast buys: stage reversible protective actions and "
                         "define triggers rather than betting on a single outcome.",
            "options": [
                {"text": "Do nothing until flooding actually begins.",
                 "strengths": "No cost if the forecast misses.",
                 "blindspots": "Wastes the warning lead time; once water rises, options collapse.",
                 "better": "Take low-regret protective steps now and set escalation triggers."},
                {"text": "Fully evacuate and relocate all inventory immediately.",
                 "strengths": "Maximally protective of stock.",
                 "blindspots": "Expensive and disruptive against an uncertain forecast; may be "
                               "unnecessary.",
                 "better": "Prioritise critical/high-value and low-lying stock; stage the rest on a "
                           "trigger."},
                {"text": "Move critical and flood-exposed stock to safe levels, confirm drainage/"
                         "barriers and staff safety, and set trigger levels to escalate as the forecast "
                         "firms up.",
                 "strengths": "Low-regret and proportionate: protects the most exposed value, keeps "
                              "operations, scales with the forecast.",
                 "blindspots": "Needs current forecast tracking and clear trigger ownership.",
                 "better": "Strongest first move; pre-arrange alternate fulfilment if the DC goes down."},
                {"text": "Escalate to executives and await instructions.",
                 "strengths": "Leadership visibility.",
                 "blindspots": "Consumes lead time; escalation without a plan delays protective action.",
                 "better": "Act on low-regret steps now; escalate with a recommendation."},
            ],
        },
    ]
