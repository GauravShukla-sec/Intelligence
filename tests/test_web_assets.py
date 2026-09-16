"""Static-asset invariants for the no-build-step frontend.

There is no bundler to catch these, so they are asserted here instead.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1] / "gsid" / "web"


@pytest.fixture(scope="module")
def index_html() -> str:
    return (WEB / "index.html").read_text(encoding="utf-8")


def test_no_inline_script_in_index(index_html):
    """The CSP is script-src 'self', so an inline <script> silently never runs.

    The service-worker registration lived inline for the life of the file and
    was blocked on every load, which disabled the offline cache and the install
    prompt without any visible error.
    """
    inline = [m for m in re.findall(r"<script\b([^>]*)>", index_html)
              if "src=" not in m]
    assert inline == [], f"inline <script> will be blocked by the CSP: {inline}"


def test_every_script_is_precached_by_the_service_worker(index_html):
    """A script index.html loads but the worker does not precache is missing
    for a device that goes offline after its first load."""
    sw = (WEB / "sw.js").read_text(encoding="utf-8")
    shell = set(re.findall(r'"(/static/js/[^"]+)"', sw))
    loaded = re.findall(r'<script src="(/static/js/[^"]+)"', index_html)
    assert loaded, "expected index.html to load app scripts"
    assert [s for s in loaded if s not in shell] == []


def test_referenced_static_files_exist(index_html):
    """Catches a renamed or deleted asset, which the browser reports only as a
    404 in the console."""
    refs = re.findall(r'(?:src|href)="(/static/[^"]+)"', index_html)
    missing = [r for r in refs if not (WEB / r.lstrip("/")).exists()]
    assert missing == []


def test_severity_tokens_defined_in_both_themes():
    """Severity must resolve in light and dark; an undefined custom property
    renders as an unstyled element rather than failing loudly."""
    css = (WEB / "static" / "css" / "styles.css").read_text(encoding="utf-8")
    dark = css[css.index(":root {"):css.index('[data-theme="light"]')]
    light = css[css.index('[data-theme="light"]'):]
    light = light[:light.index("}")]
    for tok in ("--sev-critical", "--sev-high", "--sev-elevated",
                "--sev-medium", "--sev-moderate", "--sev-low", "--sev-info"):
        assert tok in dark, f"{tok} missing from the dark theme"
        assert tok in light, f"{tok} missing from the light theme"


def test_no_severity_tinted_badge_is_built_without_a_glyph():
    """Severity colour must never be a badge's only carrier.

    The kit's badge builders always emit a glyph, so the way this rule breaks is
    a hand-rolled `class: "badge " + <severity class>` somewhere in a view. That
    shipped 24 colour-only badges on the first pass of the redesign, so it is
    asserted rather than trusted.
    """
    views = (WEB / "static" / "js" / "views.js").read_text(encoding="utf-8")
    offenders = re.findall(r'class:\s*"badge\s*"\s*\+\s*[^,\n]*sev-', views)
    offenders += re.findall(r'class:\s*"badge\s+sev-[a-z]+"', views)
    assert offenders == [], (
        "build these through UI.severityBadge / urgencyBadge / movementBadge, "
        f"which carry a glyph: {offenders}")


def test_charts_expose_their_numbers_to_assistive_tech():
    """Every chart frame must emit a visually-hidden data table."""
    charts = (WEB / "static" / "js" / "charts.js").read_text(encoding="utf-8")
    assert "dataTableFallback" in charts
    # Each public chart routes through frame(), which attaches the table.
    for fn in ("trendChart", "barChart", "donutChart", "severityBars"):
        body_start = charts.index("function " + fn + "(")
        body = charts[body_start:body_start + 2600]
        assert "frame(" in body or "emptyState(" in body, fn
