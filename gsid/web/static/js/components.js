/* Reusable DOM builders. Severity is shown with label + icon, never colour alone. */
(function () {
  "use strict";
  const API = window.GSID_API;

  // Tiny hyperscript helper.
  function h(tag, attrs, children) {
    const el = document.createElement(tag);
    if (attrs) {
      for (const k in attrs) {
        if (k === "class") el.className = attrs[k];
        else if (k === "html") el.innerHTML = attrs[k];
        else if (k === "text") el.textContent = attrs[k];
        else if (k.startsWith("on") && typeof attrs[k] === "function") el.addEventListener(k.slice(2), attrs[k]);
        else if (k === "dataset") Object.assign(el.dataset, attrs[k]);
        else if (attrs[k] !== null && attrs[k] !== undefined && attrs[k] !== false) el.setAttribute(k, attrs[k]);
      }
    }
    appendChildren(el, children);
    return el;
  }

  function appendChildren(el, children) {
    (Array.isArray(children) ? children : [children]).forEach((c) => {
      if (c === null || c === undefined || c === false) return;
      if (Array.isArray(c)) { appendChildren(el, c); return; } // flatten nested arrays
      el.appendChild(typeof c === "string" || typeof c === "number" ? document.createTextNode(String(c)) : c);
    });
  }

  const IMPACT_ICON = { Critical: "⬤", High: "◆", Moderate: "▲", Low: "■" };
  const IMPACT_CLASS = { Critical: "sev-critical", High: "sev-high", Moderate: "sev-moderate", Low: "sev-low" };
  const TREND_ICON = { "Improving": "↓", "Stable": "→", "Deteriorating": "↑", "Rapidly Deteriorating": "⇈" };
  const URGENCY_ICON = { "Immediate": "⏱", "24 Hours": "◔", "7 Days": "◑", "Long-Term": "◕" };
  const CONF_ICON = { Confirmed: "✓✓", High: "✓", Moderate: "≈", Low: "?", Unverified: "!" };

  function chip(text, cls, icon) {
    const kids = [];
    if (icon) kids.push(h("span", { class: "ico", "aria-hidden": "true" }, icon));
    kids.push(h("span", null, text));
    return h("span", { class: "chip " + (cls || "") }, kids);
  }

  function impactChip(v) { return chip("Impact: " + v, IMPACT_CLASS[v] || "", IMPACT_ICON[v] || "•"); }
  function confChip(v) { return chip(v, "conf-" + v, CONF_ICON[v] || ""); }
  function urgencyChip(v) { return chip(v, urgencyCls(v), URGENCY_ICON[v] || ""); }
  function trendChip(v) {
    const cls = v === "Improving" ? "trend-down" : v === "Rapidly Deteriorating" ? "trend-rapid" : v.includes("Deterior") ? "trend-up" : "";
    return chip(v, cls, TREND_ICON[v] || "→");
  }
  function urgencyCls(v) { return v === "Immediate" ? "sev-critical" : v === "24 Hours" ? "sev-high" : v === "7 Days" ? "sev-moderate" : "sev-low"; }

  function ratingChips(s) {
    return h("div", { class: "detail-ratings" }, [
      impactChip(s.impact),
      urgencyChip(s.urgency),
      confChip(s.confidence),
      trendChip(s.trend),
      chip("Scope: " + s.geo_scope, "", "◍"),
      chip("Likelihood: " + s.likelihood, "", "⋔"),
      chip("Velocity: " + s.velocity, "", "➤"),
    ]);
  }

  function scoreRing(score) {
    const ring = h("div", { class: "score-ring", title: "Relevance score " + score + "/100", "aria-label": "Relevance score " + score + " of 100" }, h("span", null, String(score)));
    ring.style.setProperty("--v", score);
    return ring;
  }

  function isNewToday(s) {
    const ts = s.event_time || s.first_seen;
    if (!ts) return false;
    const t = new Date(String(ts).replace(" ", "T"));
    if (isNaN(t)) return false;
    return (Date.now() - t.getTime()) < 24 * 3600 * 1000;
  }

  function storyCard(s, onOpen) {
    const meta = h("div", { class: "sc-meta" }, [
      isNewToday(s) ? chip("New today", "sev-new", "✦") : null,
      chip(s.category_name, "", "▦"),
      chip(s.region_name, "", "◍"),
      impactChip(s.impact),
      confChip(s.confidence),
      s.is_alert ? chip("Alert", "sev-critical", "▲") : null,
    ]);
    const card = h("article", { class: "story-card", tabindex: "0", role: "button", "aria-label": s.headline,
      onclick: () => onOpen(s.id),
      onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onOpen(s.id); } } }, [
      h("div", { class: "sc-top" }, [
        h("h3", null, cleanHeadline(s.headline)),
        scoreRing(s.relevance_score),
      ]),
      meta,
      h("p", { class: "sc-sum" }, truncate(s.summary || "", 180)),
      h("div", { class: "sc-foot" }, [
        h("span", null, [s.is_demo ? h("span", { class: "demo-tag" }, "demo") : "", " " + (s.location_text || s.region_name)]),
        h("span", { title: "Last updated " + API.fmtTime(s.last_updated) }, "Updated " + API.relTime(s.last_updated)),
      ]),
    ]);
    return card;
  }

  function scoreBars(scoring) {
    if (!scoring || !scoring.relevance) return h("p", { class: "empty" }, "No score breakdown available.");
    const dims = scoring.relevance.dimensions || [];
    const wrap = h("div", null, dims.map((d) => {
      const pct = d.max ? Math.round((d.points / d.max) * 100) : 0;
      const bar = h("div", { class: "bar" }, h("i", null, ""));
      bar.querySelector("i").style.width = pct + "%";
      return h("div", { class: "score-dim" }, [
        h("div", { class: "sd-top" }, [h("span", null, d.label), h("span", null, d.points + " / " + d.max)]),
        bar,
        h("div", { class: "sd-reason" }, d.rationale),
      ]);
    }));
    wrap.appendChild(h("p", { class: "section-title" }, "Total relevance: " + scoring.relevance.total + " / " + scoring.relevance.max));
    return wrap;
  }

  function ratingRationale(scoring) {
    if (!scoring || !scoring.ratings) return null;
    const r = scoring.ratings;
    const rows = Object.keys(r).map((k) => h("div", { class: "score-dim" }, [
      h("div", { class: "sd-top" }, [h("strong", null, k.replace("_", " ")), h("span", null, r[k].value)]),
      h("div", { class: "sd-reason" }, r[k].reason),
    ]));
    return h("div", null, rows);
  }

  function cleanHeadline(t) { return (t || "").replace("[DEMO] ", ""); }
  function truncate(t, n) { t = t || ""; return t.length > n ? t.slice(0, n).trim() + "…" : t; }

  function loading() {
    const tpl = document.getElementById("tpl-loading");
    return tpl.content.cloneNode(true);
  }
  function empty(msg) { return h("div", { class: "empty" }, msg || "Nothing to show."); }

  function toast(msg) {
    const t = document.getElementById("toast");
    t.textContent = msg; t.hidden = false;
    clearTimeout(t._t); t._t = setTimeout(() => (t.hidden = true), 3200);
  }

  window.GSID_C = {
    h, chip, impactChip, confChip, urgencyChip, trendChip, ratingChips, scoreRing,
    storyCard, scoreBars, ratingRationale, cleanHeadline, truncate, loading, empty, toast,
    IMPACT_ICON,
  };
})();
