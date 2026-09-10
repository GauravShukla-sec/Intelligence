# Bias & limitations statement

This tool is a **decision-support aid**, not an authoritative intelligence source.
Read this before relying on any output.

## What the desk does to reduce distortion

- Separates **verified facts** from claims, and types every claim by provenance
  (fact / official claim / witness / analyst judgment / inference / forecast /
  scenario / rumor / disinformation).
- Links each claim to its **exact source** and shows source **tier, ownership and
  transparency** notes.
- Prefers **global source diversity** (feeds span the Americas, Europe, MENA,
  Sub-Saharan Africa, South/Central/East/Southeast Asia and the Pacific).
- Provides **narrative comparison** and an automated **"Challenge This Analysis"**
  red-team that actively looks for missing perspectives, contradictions, weak
  assumptions, staleness, over/understated risk, geographic bias, source
  concentration and circular reporting.
- Avoids **false balance**, avoids inferring motives without evidence, and does
  **not** use nationality, religion, ethnicity or political affiliation as a proxy
  for risk.
- States a **confidence level** and shows what is unknown.

## Known limitations

- **Heuristic analyzer is keyword-based.** The default (no-API) analyzer infers
  signals from lexicons. It can miss nuance, under- or over-score edge cases, and
  cannot truly read context. A model-backed analyzer improves nuance but introduces
  its own model biases; neither removes the need for human review.
- **Clustering is approximate.** Token-shingle Jaccard clustering can occasionally
  merge distinct events with similar wording (e.g. multiple earthquakes) or fail to
  merge genuinely duplicate coverage phrased very differently. Treat clusters as a
  starting point.
- **Source diversity depends on configuration.** The default feed list leans toward
  large international outlets that publish machine-readable RSS. Genuinely balanced
  coverage requires operators to add regional/local feeds relevant to their footprint.
- **The cross-government advisory view is Western-only.** The desk compares travel
  advisories from the US, UK, Canada, Australia and Germany. Four of those five are
  Five Eyes partners and the fifth is a close NATO ally, so they share intelligence
  assessments. Two consequences follow, and neither is visible in the interface:
  agreement between them is weaker corroboration than five independent sources
  would be, and their divergence maps the spread *within* one broad Western
  viewpoint rather than the full range of state assessments. No non-Western
  government advisory source is included. This is not a deliberate editorial
  choice — as of 2026-09-10, Japan MOFA, India MEA, Korea MOFA and Mexico SRE were
  each checked and none publishes a machine-readable advisory feed, so the gap
  reflects what is technically available rather than what would be desirable.
- **US sources are the largest single bloc.** Five of 22 enabled feeds, and four of
  twelve tier-1 official sources, are US government or US media (State Department,
  CISA, Federal Register, USGS). Where a story's framing derives mainly from those,
  it carries a US institutional perspective. Operators serving non-US organisations
  should weigh this when reading geopolitical analysis, and consider adding local
  official sources for their own jurisdiction.
- **Language.** Non-English handling retains original metadata but the bundled
  pipeline does not translate; add a translation step in a connector if required.
- **No live web crawling.** Ingestion is limited to configured public feeds/APIs.
  The desk does not scrape arbitrary pages, bypass access controls, or use
  paywalled/leaked content.
- **Demo data is fictional.** Demo scenarios are illustrative and must never be read
  as current events; they exist to exercise the analysis.
- **Ratings are models, not truth.** Scores and forecasts are structured judgments,
  not certainties. Do not treat any AI/heuristic output as a factual guarantee.

## Analyst responsibilities

- Corroborate material claims against primary sources before acting.
- Use "Challenge This Analysis" and "Show only confirmed facts" on anything you plan
  to escalate.
- Calibrate recommended actions to your organization's actual footprint and risk
  tolerance; the desk's recommendations are deliberately proportionate defaults.
