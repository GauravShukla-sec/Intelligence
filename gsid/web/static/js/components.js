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

  // Advisory levels reuse the severity palette: 4→critical … 1→low.
  const ADV_SEV = { 4: "sev-critical", 3: "sev-high", 2: "sev-moderate", 1: "sev-low" };
  const ADV_ICON = { 4: "⛔", 3: "⚠", 2: "◑", 1: "■" };

  function advisoryLevelChip(level, label) {
    if (!level) return null;
    return chip("Advisory: Level " + level + (label ? " · " + label : ""),
      ADV_SEV[level] || "", ADV_ICON[level] || "•");
  }

  function advisoryConsensus(adv) {
    if (!adv || !adv.consensus) return null;
    const govChips = (adv.sources || []).map((s) =>
      chip((s.gov_name || (s.gov || "").toUpperCase()) + " · L" + s.level,
        ADV_SEV[s.level] || "", ADV_ICON[s.level] || "•"));
    return h("div", { class: "panel", style: "margin-bottom:1rem" }, [
      h("div", { class: "sc-top" }, [
        h("h2", null, "Cross-government advisory level"),
        chip("Consensus: Level " + adv.consensus, ADV_SEV[adv.consensus] || "",
          ADV_ICON[adv.consensus] || "•"),
      ]),
      h("p", { class: "sd-reason" },
        "Worst-case across governments that rate this destination — a stricter "
        + "advisory is never hidden behind a milder one. "
        + adv.consensus_label + "."),
      h("div", { class: "detail-ratings" }, govChips),
      adv.diverges ? h("p", { class: "sd-reason" },
        chip("Governments differ", "sev-high", "⚠"),
        " Assessments span levels " + adv.lowest + "–" + adv.consensus
        + "; treat the range as a signal and check the leading government for your travellers.")
        : null,
    ]);
  }

  // "What changed" feed for government travel advice (change-detection).
  const CHG_META = {
    escalated:   { label: "Escalated",    cls: "sev-critical",  ico: "↑" },
    deescalated: { label: "Eased",        cls: "sev-low",       ico: "↓" },
    revised:     { label: "Revised",      cls: "sev-moderate",  ico: "≈" },
    new:         { label: "Now tracked",  cls: "sev-info",      ico: "+" },
  };

  function advisoryChangeFeed(data, onCountry) {
    const c = (data && data.counts) || {};
    const rows = (data && data.changes) || [];
    const summary = h("div", { class: "detail-ratings" }, [
      chip(c.escalated + " escalated", c.escalated ? "sev-critical" : "sev-info", "↑"),
      chip(c.deescalated + " eased", c.deescalated ? "sev-low" : "sev-info", "↓"),
      chip(c.revised + " revised", c.revised ? "sev-moderate" : "sev-info", "≈"),
      chip(c.new + " newly tracked", "sev-info", "+"),
    ]);
    const body = rows.length
      ? h("div", null, rows.map((r) => {
          const m = CHG_META[r.kind] || CHG_META.revised;
          const move = r.kind === "escalated" || r.kind === "deescalated"
            ? ("Level " + r.prev_level + " → Level " + r.level)
            : ("Level " + r.level);
          return h("div", { class: "citation" }, [
            h("div", { class: "sc-top" }, [
              h("strong", null, r.country_name),
              chip(m.label, m.cls, m.ico),
            ]),
            h("div", { class: "sd-reason" }, [
              move + " · " + (r.level_label || "") + " · " + (r.source_name || ""),
            ]),
            h("div", { class: "sc-meta" }, [
              h("span", { class: "sd-reason" }, "Detected " + API.relTime(r.changed_at)),
              onCountry
                ? h("button", { class: "btn small secondary", onclick: () => onCountry(r.country) },
                    "Open " + r.country_name)
                : null,
            ]),
          ]);
        }))
      : h("p", { class: "sd-reason" },
          "No advisory level changes detected in the last " + (data.days || 14)
          + " days. Baseline advice for " + (c.new || 0)
          + " destinations is being tracked; a change here means a government "
          + "actually moved or rewrote its advice.");

    return h("div", { class: "panel", style: "margin-bottom:1rem" }, [
      h("div", { class: "sc-top" }, [
        h("h2", null, "What changed in government travel advice"),
        h("span", { class: "sd-reason" }, "Last " + (data.days || 14) + " days"),
      ]),
      summary,
      body,
    ]);
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
    storyCard, scoreBars, ratingRationale, advisoryConsensus, advisoryLevelChip,
    advisoryChangeFeed, cleanHeadline, truncate, loading, empty, toast,
    IMPACT_ICON,
  };
})();
