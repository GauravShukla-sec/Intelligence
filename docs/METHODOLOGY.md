# Methodology: risk scoring & source quality

## Relevance score (0–100)

Implemented in [`gsid/scoring.py`](../gsid/scoring.py). Each dimension is scored by
an **intensity in [0, 1]** produced by the analyzer, multiplied by the dimension's
maximum points. **Every awarded point carries a human-readable rationale** shown in
the story's "Relevance score" panel — the system never emits an unexplained number.

| Dimension | Max points |
|-----------|-----------:|
| Threat to people / employee safety | 20 |
| Threat to facilities / physical assets | 15 |
| Operational / business-continuity impact | 15 |
| Supply-chain / transportation impact | 15 |
| Legal / regulatory / compliance impact | 15 |
| Geopolitical escalation potential | 10 |
| Cyber-physical impact | 5 |
| Executive / reputational impact | 5 |
| **Total** | **100** |

The **heuristic analyzer** derives intensities from transparent keyword lexicons
(see `gsid/analysis/heuristic.py`), with a category prior ensuring the labelled
category is never zero. A **model-backed analyzer** (Anthropic/OpenAI) produces the
same intensities via a strict JSON schema. Because the scoring function is pure and
deterministic, identical signals always yield identical scores.

## Categorical ratings

Derived from the composite score, signals, and evidence, each with a rationale:

- **Impact** — Low / Moderate / High / Critical (Critical if score ≥ 75 *or* a
  direct life-safety signal ≥ 0.9).
- **Urgency** — Immediate / 24 Hours / 7 Days / Long-Term (from velocity + life safety).
- **Geographic scope** — Local / National / Regional / Global (from affected-country count).
- **Likelihood** — Rare … Almost Certain (from certainty language in reporting).
- **Velocity** — Slow / Developing / Fast / Immediate (from pace/escalation cues).
- **Trend** — Improving / Stable / Deteriorating / Rapidly Deteriorating (escalation vs de-escalation cues).
- **Confidence** — see below.

## Confidence model

Mapped transparently from evidence quality (`derive_confidence`):

| Level | Rule |
|-------|------|
| **Confirmed** | Primary/authoritative evidence **and** ≥ 2 reliable sources |
| **High** | Tier ≤ 2 **and** ≥ 2 sources (no primary) |
| **Moderate** | Tier ≤ 2 single source, **or** tier-3 multiple sources |
| **Low** | Tier-3 single source, or conflicting evidence |
| **Unverified** | Tier-4 / single social / unsupported signal |

## Critical-alert gating

To avoid alert fatigue, a story is surfaced as a **Critical Alert** only when it is
**High or Critical impact**, **Immediate or 24-Hour urgency**, and scores **≥ 45** —
and never on Unverified confidence unless impact is Critical.

## Source-quality model (tiers)

| Tier | Meaning | Examples |
|-----:|---------|----------|
| **1** | Primary / authoritative | governments, regulators, courts, UN/WHO/USGS, official corporate disclosures, original legislation |
| **2** | High-quality independent reporting | Reuters, AP, BBC, FT, Bloomberg, Guardian, Al Jazeera, DW, France 24, The Hindu, SCMP |
| **3** | Specialist / research | think tanks, maritime/supply-chain intelligence, cybersecurity vendors, academia, NGOs |
| **4** | Early-warning / unverified signal | social media, local unverified reports, imagery |

Tier-4 material is treated as an **alerting signal only** and labelled Unverified
until corroborated. Assessment focuses on **method, evidence, ownership, transparency
and corroboration** — not mechanical political labels.

## Freshness & duplication

- `first_seen` and `last_updated` (material update) are tracked per story.
- Near-duplicate coverage is clustered; re-ingesting a matching headline **merges new
  citations and bumps freshness** rather than duplicating the story.
- Likely **circular/syndicated** reporting is flagged so confidence does not rise
  from mere repetition.

## Worked example

The demo story *"Shipping advisories tighten…"* scores ~59/100: strong supply-chain
and operational signals, a life-safety signal (incidents against shipping), and
geopolitical escalation, corroborated by a primary maritime bulletin plus wire and
regional reporting → **Confidence: Confirmed, Impact: Critical, Urgency: Immediate**,
and it qualifies as a Critical Alert. Open the story and expand the score panel to
see each dimension's points and rationale.
