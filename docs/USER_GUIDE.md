# User guide (for a global-security / GRC professional)

## Orientation

The left rail is your workflow. Times display in the timezone selected top-right
(internally everything is UTC). The DEMO banner appears whenever demo data is present.

## Views

- **Executive Dashboard** — 60-second posture read: global risk posture meter, alert
  count, deteriorating/improving regions, top developments, and the 24–72h watchlist.
  Start here each morning.
- **Daily Brief** — the full 12-section brief: executive snapshot, global risk pulse,
  critical alerts, regional watch (with explicit "No material change identified"),
  laws & regulations, supply-chain watch, cyber-physical watch, 30/60/90 outlook,
  today's security lesson, links to the scenario & quiz, and executive talking points.
- **Critical Alerts** — only prompt-action developments (impact + urgency + score
  gated). Each shows people/facility/operational impact and a recommended action.
- **Stories** — filter by region, country, category, impact, urgency, confidence,
  trend; "verified only" and "alerts only" toggles; sort by relevance/recency/urgency.
  Export the filtered set to CSV/JSON (Power BI-friendly).
- **World / Region** — schematic map; click a dot to open a development or a region
  area to filter. Region tiles below show counts.
- **Regional Watch / Supply-Chain / Cyber-Physical** — focused feeds for those remits.
- **Regulatory Tracker** — lifecycle status (a proposal is never shown as enacted
  law), with jurisdiction, framework, effective date, obligations, reporting timelines,
  penalties, implications, prep steps and the original source link.
- **Saved** — your flagged developments.
- **Learn & Exercise** — an interactive decision **scenario** (choose, then see
  strengths / blind spots / better steps / principle) and an **adaptive quiz** (local
  score, difficulty rises as you improve).
- **Transparency & Audit** — source-tier and confidence definitions, the scoring
  model, and the audit log of automated + manual actions.
- **Watchlist & Settings** — configure countries, sites, suppliers, routes, travel
  destinations, industries, regulations, priority topics, risk tolerance, timezone,
  report time and briefing length; save your access token; trigger live ingestion.

## Working a story (story detail page)

Read top-to-bottom: ratings row → what happened → verified facts → **claims with
provenance types** → background → narrative comparison → why it matters globally →
**why this matters to your work** → risk pathway → timeline → questions to ask today
→ recommended actions. The right column holds the **explained relevance score**,
rating rationale, potentially-affected register, indicators to monitor, and the full
**sources/transparency** panel.

Tools on each story:

- **★ Save** — add to Saved.
- **⚔ Challenge this analysis** — runs the red-team (missing perspectives,
  contradictions, weak assumptions, staleness, over/understated risk, geographic bias,
  source concentration, circular reporting). Use before escalating.
- **✓ Show only confirmed facts** — hides claims that aren't facts/primary-corroborated.
- **⇩ Export as…** — one click to:
  - **Risk-register entry** (threat, vulnerability, existing controls, control gaps,
    likelihood/impact, inherent/residual risk, treatment strategy, owner, target date,
    monitoring indicators, sources, last reviewed) — paste straight into Resolver/GRC.
  - **Corrective action**, **Executive summary**, **Travel-security note**,
    **Email to leadership**, **Risk-register CSV**, **Full JSON**.

## Suggested daily routine

1. Dashboard → posture + alerts.
2. Critical Alerts → validate exposure for anything High/Critical.
3. Daily Brief → regional watch + regulations + supply-chain.
4. For each escalation candidate: open the story → Challenge → export a risk-register
   entry or leadership email.
5. Learn & Exercise → 3-question check to stay sharp.

## Personalization

Set your **countries of operation, sites, suppliers, routes and travel destinations**
in Settings so "Potentially affected" and "Questions you should ask today" map to your
real footprint. Preferences persist server-side (token required if auth is enabled).
