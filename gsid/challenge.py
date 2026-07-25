"""'Challenge This Analysis' — a structured red-team of a story.

Deterministically inspects a fully-assembled story and flags analytical
weaknesses across the required dimensions: missing perspectives, contradictory
evidence, weak assumptions, stale information, over/understated risk,
geographic bias, source concentration, and circular reporting.

Each finding is advisory and explains *why* it fired, so the analyst can judge
it — the tool never silently changes ratings.
"""

from __future__ import annotations

from datetime import datetime, timezone


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def challenge(story: dict, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    findings: list[dict] = []
    citations = story.get("citations", [])
    claims = story.get("claims", [])
    analysis = story.get("analysis", {})

    def add(dim: str, severity: str, text: str):
        findings.append({"dimension": dim, "severity": severity, "finding": text})

    # --- Source concentration ---
    if len(citations) <= 1:
        add("Source concentration", "high",
            "Only one citation supports this story. Treat as single-sourced and seek "
            "independent corroboration before acting.")
    else:
        origins = {c.get("source_name") for c in citations}
        if len(origins) == 1:
            add("Source concentration", "high",
                "Multiple citations trace to a single publisher — effectively single-sourced.")

    # --- Circular reporting ---
    if any(c.get("is_circular") for c in citations):
        add("Circular reporting", "medium",
            "Citations were flagged as syndicated/circular (many outlets, one origin). "
            "Confidence should not rise simply from repetition.")

    # --- Missing perspectives ---
    countries = story.get("countries", [])
    source_countries = {c.get("source_country") for c in citations if c.get("source_country")}
    if countries and source_countries and not (set(countries) & source_countries):
        add("Missing perspectives", "medium",
            "No cited source originates from the affected country/countries. A credible "
            "local/regional perspective may be missing.")
    if len(story.get("narratives", [])) < 2 and len(citations) >= 2:
        add("Missing perspectives", "low",
            "No competing narrative was captured. Check whether a materially different "
            "interpretation exists before treating framing as settled.")

    # --- Geographic bias (source diversity) ---
    if source_countries and len(source_countries) == 1:
        add("Geographic bias", "low",
            f"All sources originate from one country ({next(iter(source_countries))}). "
            "Consider a source from a different region for balance.")

    # --- Contradictory / unverified evidence ---
    unverified = [c for c in claims if c.get("claim_type") in ("rumor", "disinformation")]
    if unverified:
        add("Contradictory / unverified evidence", "medium",
            f"{len(unverified)} claim(s) are typed rumor/disinformation. Ensure these are "
            "not driving the risk rating.")
    disputes = [c for c in claims if c.get("stance") == "disputes"]
    if disputes:
        add("Contradictory evidence", "medium",
            "At least one claim disputes others. Reconcile before finalizing confidence.")

    # --- Weak assumptions ---
    inferences = [c for c in claims if c.get("claim_type") in ("inference", "forecast", "scenario")]
    if inferences:
        add("Weak assumptions", "low",
            f"{len(inferences)} element(s) are inference/forecast/scenario rather than fact. "
            "Verify they are labelled as judgment, not established fact.")

    # --- Stale information ---
    last = _parse(story.get("last_updated"))
    if last is not None:
        age_h = (now - last).total_seconds() / 3600.0
        if age_h > 72 and story.get("velocity") in ("Fast", "Immediate"):
            add("Stale information", "high",
                f"Story is ~{int(age_h)}h old but rated fast-moving. Re-verify before relying.")
        elif age_h > 168:
            add("Stale information", "low",
                f"Story is ~{int(age_h/24)} days old; confirm it is still current.")

    # --- Overstated impact ---
    if story.get("impact") in ("High", "Critical") and story.get("confidence") in ("Unverified", "Low"):
        add("Overstated impact", "high",
            "Impact is rated High/Critical on Low/Unverified confidence. The impact may be "
            "overstated relative to the evidence.")
    # --- Understated risk ---
    signals = analysis.get("signals", {})
    if signals.get("people_safety", 0) >= 0.6 and story.get("impact") in ("Low", "Moderate"):
        add("Understated risk", "medium",
            "A strong life-safety signal is present but impact is rated Low/Moderate. "
            "Re-check whether people-impact is understated.")

    if not findings:
        add("Overall", "info",
            "No structural weaknesses detected by the automated red-team. This is not a "
            "guarantee of accuracy — human review still applies.")

    # Sort by severity for display.
    order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    findings.sort(key=lambda f: order.get(f["severity"], 4))
    return findings
