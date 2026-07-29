/* View renderers. Each returns a DOM node (may fetch its own data). */
(function () {
  "use strict";
  const API = window.GSID_API;
  const C = window.GSID_C;
  const h = C.h;
  const Views = {};

  function head(title, sub, actions) {
    return h("div", { class: "page-head" }, [
      h("div", null, [h("h1", null, title), sub ? h("div", { class: "sub" }, sub) : null]),
      actions ? h("div", { class: "btn-row" }, actions) : null,
    ]);
  }

  async function mount(node, builder) {
    node.appendChild(C.loading());
    try {
      const content = await builder();
      node.innerHTML = "";
      node.appendChild(content);
    } catch (e) {
      node.innerHTML = "";
      node.appendChild(h("div", { class: "empty" }, "Could not load: " + e.message));
    }
  }

  // ============================ DASHBOARD ============================
  const POSTURE_PCT = { Low: 22, Guarded: 42, Elevated: 62, High: 80, Severe: 94, Critical: 96 };
  const DIR_META = {
    "Rapidly Deteriorating": { sym: "▼▼", cls: "dir-bad" },
    "Deteriorating": { sym: "▼", cls: "dir-bad" },
    "Stable": { sym: "▬", cls: "dir-flat" },
    "Improving": { sym: "▲", cls: "dir-good" },
  };

  Views.dashboard = function () {
    const node = h("div");
    mount(node, async () => {
      const brief = await API.brief();
      const p = brief.global_risk_pulse;
      const alertsCount = brief.critical_alerts.length;
      const deter = p.regions_deteriorating.length;
      const wrap = h("div");

      wrap.appendChild(head("Executive Dashboard",
        "Generated " + API.fmtTime(brief.generated_at) + " · " + brief.story_count + " developments tracked",
        [h("a", { class: "btn secondary", href: "#/brief" }, "Open full Daily Brief")]));

      // ---- Hero: risk posture + KPI tiles ----
      const lvl = p.posture.level;
      const pct = POSTURE_PCT[lvl] != null ? POSTURE_PCT[lvl] : 55;
      const hero = h("section", { class: "hero-posture panel" }, [
        h("div", { class: "hp-gauge" }, [
          h("div", { class: "hp-ring", style: "--pct:" + pct + "%" }, [
            h("div", { class: "hp-ring-inner" }, [
              h("span", { class: "hp-pct num" }, pct + ""),
              h("span", { class: "hp-of" }, "index"),
            ]),
          ]),
        ]),
        h("div", { class: "hp-body" }, [
          h("div", { class: "hp-eyebrow" }, "Global risk posture"),
          h("div", { class: "hp-level" }, [
            h("span", { class: "hp-dot lvl-" + slug(lvl) }, ""),
            h("span", null, lvl),
          ]),
          h("p", { class: "hp-reason" }, p.posture.reason),
          h("div", { class: "kpi-row" }, [
            kpi(brief.story_count, "Tracked", "◔", "", "#/stories"),
            kpi(alertsCount, "Critical alerts", "▲", alertsCount ? "sev-critical" : "sev-info", "#/alerts"),
            kpi(deter, "Regions worsening", "▼", deter ? "sev-high" : "sev-info", "#/regional"),
            kpi(p.regions_improving.length, "Regions improving", "▲", p.regions_improving.length ? "sev-low" : "sev-info", "#/regional"),
          ]),
        ]),
      ]);
      wrap.appendChild(hero);

      // ---- Main split: top developments | side rail ----
      const split = h("div", { class: "dash-split" });

      // Top developments (ranked)
      const devs = h("section", { class: "panel" }, [
        h("div", { class: "sc-top" }, [
          h("h2", null, "Top developments"),
          h("a", { class: "sd-reason", href: "#/stories" }, "All stories →"),
        ]),
        h("ol", { class: "rank-list" }, brief.executive_snapshot.map((s, i) => rankItem(s, i))),
      ]);
      split.appendChild(devs);

      // Side rail: movers + watch-next
      const rail = h("div", { class: "dash-rail" }, [
        moversCard(p),
        h("section", { class: "panel" }, [
          h("h2", null, "Watch next 24–72h"),
          (p.watch_next && p.watch_next.length)
            ? h("ul", { class: "watch-list" }, p.watch_next.map((w) =>
                h("li", null, h("a", { href: "#/story/" + w.id }, C.cleanHeadline(w.headline)))))
            : h("p", { class: "empty" }, "Nothing flagged for the next 24–72h."),
        ]),
      ]);
      split.appendChild(rail);
      wrap.appendChild(split);

      // ---- Pulse cards ----
      wrap.appendChild(h("p", { class: "section-title" }, "Focus areas"));
      wrap.appendChild(h("div", { class: "grid grid-3" }, [
        pulseCard("Top regulatory", p.top_regulatory, "§"),
        pulseCard("Top supply-chain", p.top_supply_chain, "⚓"),
        pulseCard("Top employee-safety", p.top_employee_safety, "⚑"),
      ]));

      return wrap;
    });
    return node;
  };

  function slug(s) { return String(s || "").toLowerCase().replace(/[^a-z]/g, ""); }

  function kpi(num, label, sym, cls, href) {
    const kids = [
      h("div", { class: "kpi-num num " + (cls || "") }, [
        h("span", { class: "kpi-ico", "aria-hidden": "true" }, sym), String(num),
      ]),
      h("div", { class: "kpi-lbl" }, label),
    ];
    // A tile with a target is a real link (keyboard-accessible, shows what's
    // behind the number); otherwise it's a plain stat.
    return href
      ? h("a", { class: "kpi kpi-link", href, "aria-label": label + ": " + num }, kids)
      : h("div", { class: "kpi" }, kids);
  }

  function rankItem(s, i) {
    const d = DIR_META[s.trend] || DIR_META["Stable"];
    return h("li", { class: "rank-item", onclick: () => go("#/story/" + s.id), tabindex: "0",
                     onkeydown: (e) => { if (e.key === "Enter") go("#/story/" + s.id); } }, [
      h("div", { class: "rank-num num" }, String(i + 1)),
      h("div", { class: "rank-body" }, [
        h("div", { class: "rank-head", title: C.cleanHeadline(s.headline) }, C.cleanHeadline(s.headline)),
        h("p", { class: "rank-why" }, s.why),
        h("div", { class: "rank-meta" }, [
          s.score != null ? h("span", { class: "score-pill" }, [h("b", { class: "num" }, String(s.score)), "/100"]) : null,
          s.impact ? C.impactChip ? C.impactChip(s.impact) : C.chip(s.impact, sevCls(s.impact), "●") : null,
          s.category_name ? h("span", { class: "meta-tag" }, s.category_name) : null,
          h("span", { class: "dir " + d.cls }, [h("span", { "aria-hidden": "true" }, d.sym + " "), s.direction]),
        ]),
      ]),
    ]);
  }

  function sevCls(v) {
    return { Critical: "sev-critical", High: "sev-high", Moderate: "sev-moderate", Low: "sev-low" }[v] || "sev-info";
  }

  function moversCard(p) {
    const row = (label, names, cls, sym) => h("div", { class: "mover-row" }, [
      h("div", { class: "mover-head" }, [
        h("span", { class: "mover-ico " + cls, "aria-hidden": "true" }, sym),
        h("span", null, label),
        h("span", { class: "mover-count num" }, String(names.length)),
      ]),
      names.length ? h("div", { class: "tag-list" }, names.slice(0, 6).map((n) => h("span", { class: "region-tag" }, n)))
                   : h("p", { class: "sd-reason" }, "No material change identified."),
    ]);
    return h("section", { class: "panel" }, [
      h("h2", null, "Regional movers"),
      row("Deteriorating", p.regions_deteriorating, "sev-high", "▼"),
      row("Improving", p.regions_improving, "sev-low", "▲"),
    ]);
  }

  function pulseCard(title, item, ico) {
    return h("div", { class: "panel pulse-card" }, [
      h("div", { class: "pulse-ico", "aria-hidden": "true" }, ico || "•"),
      h("div", null, [
        h("div", { class: "pulse-title" }, title),
        item ? h("a", { class: "pulse-link", href: "#/story/" + item.id }, C.cleanHeadline(item.headline))
             : h("p", { class: "empty" }, "No material item identified."),
      ]),
    ]);
  }

  // ============================ DAILY BRIEF ============================
  Views.brief = function () {
    const node = h("div");
    mount(node, async () => {
      const brief = await API.brief();
      const wrap = h("div");
      wrap.appendChild(head("Daily Global Security Brief",
        "Generated " + API.fmtTime(brief.generated_at) + " (UTC internal, shown in " + API.state.tz + ")"));

      // 1 snapshot
      wrap.appendChild(sectionPanel("1 · Executive Snapshot (60-second read)",
        h("ul", { class: "clean" }, brief.executive_snapshot.map((s) =>
          h("li", null, [
            h("a", { href: "#/story/" + s.id }, h("strong", null, C.cleanHeadline(s.headline))),
            " — " + s.why + " ", h("em", null, "(" + s.direction + ")"),
          ])))));

      // 2 pulse
      const p = brief.global_risk_pulse;
      wrap.appendChild(sectionPanel("2 · Global Risk Pulse", h("div", null, [
        h("div", { class: "posture posture-" + p.posture.level }, [
          C.chip("Posture: " + p.posture.level, p.posture.level === "Elevated" ? "sev-critical" : p.posture.level === "Guarded" ? "sev-high" : "sev-low", "◧"),
          h("div", { class: "meter" }, h("i")),
        ]),
        h("p", { class: "sd-reason" }, p.posture.reason),
        h("div", { class: "kv", style: "margin-top:.6rem" }, [
          h("dt", null, "Deteriorating"), h("dd", null, p.regions_deteriorating.join(", ") || "None"),
          h("dt", null, "Improving"), h("dd", null, p.regions_improving.join(", ") || "None"),
          h("dt", null, "Emerging hotspots"), h("dd", null, p.emerging_hotspots.join(", ") || "None"),
        ]),
      ])));

      // 3 alerts
      wrap.appendChild(sectionPanel("3 · Critical Alerts",
        brief.critical_alerts.length ? h("div", { class: "grid" }, brief.critical_alerts.map(alertRow))
          : h("p", { class: "empty" }, "No developments currently meet the critical-alert threshold.")));

      // 4 regional
      wrap.appendChild(sectionPanel("4 · Regional Security Watch",
        h("div", { class: "grid grid-2" }, brief.regional_watch.map((r) =>
          h("div", { class: "panel" }, [
            h("h3", null, r.region_name),
            r.no_material_change ? h("p", { class: "sd-reason" }, "No material change identified.")
              : h("ul", { class: "clean" }, r.stories.slice(0, 3).map((s) =>
                  h("li", null, h("a", { href: "#/story/" + s.id }, C.cleanHeadline(s.headline))))),
          ])))));

      // 5 regulations
      wrap.appendChild(sectionPanel("5 · Laws & Regulations Watch",
        h("div", { class: "grid grid-2" }, brief.regulations.map(regMini))));

      // 6 supply
      wrap.appendChild(sectionPanel("6 · Supply-Chain Security Watch", storyMiniList(brief.supply_chain_watch)));
      // 7 cyber
      wrap.appendChild(sectionPanel("7 · Cyber-Physical Watch", storyMiniList(brief.cyber_physical_watch)));

      // 8 outlook
      const o = brief.outlook;
      wrap.appendChild(sectionPanel("8 · 30/60/90-Day Outlook", h("div", { class: "grid grid-3" }, [
        outlookCol("Confirmed", o.confirmed), outlookCol("Reasonably foreseeable", o.foreseeable), outlookCol("Speculative", o.speculative),
      ])));
      wrap.querySelector(".grid-3").insertAdjacentElement("afterend", h("p", { class: "sd-reason" }, o.note));

      // 9 lesson
      const l = brief.todays_lesson;
      wrap.appendChild(sectionPanel("9 · Today's Security Lesson", h("div", null, [
        h("h3", null, l.concept),
        h("p", null, l.plain_language),
        l.connected_story ? h("p", null, ["Connected development: ", h("a", { href: "#/story/" + l.connected_story.id }, C.cleanHeadline(l.connected_story.headline))]) : null,
        h("p", { class: "sd-reason" }, l.why_it_helps),
      ])));

      // 10 & 11 links
      wrap.appendChild(sectionPanel("10 & 11 · Scenario & Knowledge Check",
        h("div", { class: "btn-row" }, [
          h("a", { class: "btn", href: "#/learn" }, "Open scenario exercise"),
          h("a", { class: "btn secondary", href: "#/learn" }, "Take today's quiz"),
        ])));

      // 12 talking points
      wrap.appendChild(sectionPanel("12 · Executive Talking Points",
        h("ul", { class: "clean" }, brief.executive_talking_points.map((t) => h("li", null, t)))));

      return wrap;
    });
    return node;
  };

  function sectionPanel(title, body) {
    return h("section", { class: "panel", style: "margin-bottom:1rem" }, [h("h2", null, title), body]);
  }
  function storyMiniList(list) {
    if (!list || !list.length) return h("p", { class: "empty" }, "No qualifying developments.");
    return h("ul", { class: "clean" }, list.map((s) =>
      h("li", null, [h("a", { href: "#/story/" + s.id }, C.cleanHeadline(s.headline)), " ", C.impactChip(s.impact)])));
  }
  function outlookCol(title, items) {
    return h("div", { class: "panel" }, [
      h("h3", null, title),
      items && items.length ? h("ul", { class: "clean" }, items.map((i) => h("li", null, [i.title.replace("[DEMO] ", ""), h("br"), h("span", { class: "sd-reason" }, (i.framework || "") + " · " + i.when)])))
        : h("p", { class: "sd-reason" }, "None recorded."),
    ]);
  }
  function alertRow(a) {
    const al = a.alert || {};
    return h("div", { class: "panel alert-row", style: "border-left:3px solid var(--sev-critical);cursor:pointer",
                      role: "button", tabindex: "0", "aria-label": C.cleanHeadline(a.headline),
                      onclick: () => go("#/story/" + a.id),
                      onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go("#/story/" + a.id); } } }, [
      h("div", { class: "sc-top" }, [h("h3", null, h("a", { href: "#/story/" + a.id }, C.cleanHeadline(a.headline))), C.confChip(a.confidence)]),
      h("div", { class: "sc-meta" }, [C.chip(a.location_text || a.region_name, "", "◍"), C.impactChip(a.impact), C.urgencyChip(a.urgency)]),
      h("div", { class: "kv", style: "margin-top:.5rem" }, [
        h("dt", null, "People"), h("dd", null, al.people_impact || "—"),
        h("dt", null, "Facilities"), h("dd", null, al.facility_impact || "—"),
        h("dt", null, "Operations"), h("dd", null, al.operational_impact || "—"),
        h("dt", null, "Event time"), h("dd", null, API.fmtTime(a.event_time)),
        h("dt", null, "Last verified"), h("dd", null, API.fmtTime(a.last_updated)),
        h("dt", null, "Recommended"), h("dd", null, al.recommended_action || "—"),
      ]),
    ]);
  }
  function regMini(r) {
    return h("div", { class: "panel" }, [
      h("div", { class: "sc-top" }, [h("h3", null, r.title.replace("[DEMO] ", "")), h("span", { class: "status-pill st-" + r.status }, r.status)]),
      h("div", { class: "sd-reason" }, r.jurisdiction + " · " + (r.framework || "")),
      h("a", { class: "btn small secondary", href: "#/regulatory" }, "View in tracker"),
    ]);
  }

  // ============================ ALERTS ============================
  Views.alerts = function () {
    const node = h("div");
    mount(node, async () => {
      const data = await API.alerts();
      // Viewing the list marks these alerts seen and clears the nav badge.
      API.alertsSeen.markSeen(data.alerts);
      if (API.refreshAlertBadge) API.refreshAlertBadge();
      const wrap = h("div");
      wrap.appendChild(head("Critical Alerts", "Only developments meeting the prompt-action threshold appear here. Newest first."));
      wrap.appendChild(data.alerts.length ? h("div", { class: "grid" }, data.alerts.map(alertRow))
        : C.empty("No active critical alerts. This is intentional — the desk avoids alert fatigue."));
      return wrap;
    });
    return node;
  };

  // ============================ STORIES (list + filters) ============================
  Views.stories = function (params) {
    const node = h("div");
    const meta = API.state.meta;
    const filters = Object.assign({ sort: "score" }, params || {});
    const listWrap = h("div", { class: "grid grid-2" });

    function sel(name, label, opts, includeAll) {
      const s = h("select", { name, onchange: (e) => { filters[name] = e.target.value; refresh(); } });
      if (includeAll) s.appendChild(h("option", { value: "" }, "All"));
      opts.forEach((o) => s.appendChild(h("option", { value: o.value, selected: filters[name] === o.value ? "selected" : null }, o.label)));
      return h("label", null, [label, s]);
    }

    async function refresh() {
      listWrap.innerHTML = "";
      listWrap.appendChild(C.loading());
      const qs = new URLSearchParams();
      Object.keys(filters).forEach((k) => { if (filters[k]) qs.set(k, filters[k]); });
      const data = await API.stories(qs.toString());
      listWrap.innerHTML = "";
      if (!data.stories.length) { listWrap.appendChild(C.empty("No stories match these filters.")); return; }
      data.stories.forEach((s) => listWrap.appendChild(C.storyCard(s, openStory)));
    }

    const bar = h("div", { class: "filters" }, [
      sel("category", "Category", meta.categories.map((c) => ({ value: c.id, label: c.name })), true),
      sel("region", "Region", meta.regions.filter(r => r.id !== "global").map((r) => ({ value: r.id, label: r.name })), true),
      sel("impact", "Impact", meta.scales.impact.map((v) => ({ value: v, label: v })), true),
      sel("urgency", "Urgency", meta.scales.urgency.map((v) => ({ value: v, label: v })), true),
      sel("confidence", "Confidence", meta.scales.confidence.map((v) => ({ value: v, label: v })), true),
      sel("trend", "Trend", meta.scales.trend.map((v) => ({ value: v, label: v })), true),
      sel("sort", "Sort", [{ value: "score", label: "Relevance" }, { value: "recent", label: "Most recent" }, { value: "urgency", label: "Urgency" }]),
      h("label", null, ["New today", h("input", { type: "checkbox", checked: filters.new_today === "1" ? "checked" : null, onchange: (e) => { filters.new_today = e.target.checked ? "1" : ""; refresh(); } })]),
      h("label", null, ["Verified only", h("input", { type: "checkbox", onchange: (e) => { filters.verified_only = e.target.checked ? "1" : ""; refresh(); } })]),
      h("label", null, ["Alerts only", h("input", { type: "checkbox", onchange: (e) => { filters.alerts_only = e.target.checked ? "1" : ""; refresh(); } })]),
    ]);

    const wrap = h("div");
    wrap.appendChild(head("Stories", "Filter, sort and open any development for the full intelligence template.",
      [h("a", { class: "btn secondary small", href: "/api/export/stories.csv" }, "Export CSV"),
       h("a", { class: "btn secondary small", href: "/api/export/stories.json" }, "Export JSON")]));
    wrap.appendChild(bar);
    wrap.appendChild(listWrap);
    node.appendChild(wrap);
    refresh();
    return node;
  };

  // ============================ STORY DETAIL ============================
  Views.story = function (params) {
    const id = params.id;
    const node = h("div");
    mount(node, async () => {
      const s = await API.story(id);
      const a = s.analysis || {};
      let confirmedOnly = false;

      const wrap = h("div");
      const backBtn = h("a", { class: "btn secondary small", href: "#/stories" }, "← Stories");
      wrap.appendChild(h("div", { class: "btn-row", style: "margin-bottom:.6rem" }, [backBtn]));

      // header
      wrap.appendChild(h("div", { class: "detail-head" }, [
        h("div", { class: "sc-meta" }, [C.chip(s.category_name, "", "▦"), C.chip(s.region_name, "", "◍"),
          C.chip(s.location_text || "—", "", "⚑"), s.is_demo ? h("span", { class: "demo-tag" }, "demo data") : null,
          s.is_alert ? C.chip("Critical alert", "sev-critical", "▲") : null]),
        h("h1", null, C.cleanHeadline(s.headline)),
        C.ratingChips(s),
        h("div", { class: "sd-reason" }, "Event: " + API.fmtTime(s.event_time) + " · First seen: " + API.fmtTime(s.first_seen) + " · Last verified: " + API.fmtTime(s.last_updated) + " · Status: " + (s.status || "—")),
      ]));

      // toolbar
      wrap.appendChild(h("div", { class: "btn-row", style: "margin-bottom:1rem" }, [
        toolBtn(API.savedLocal.has(id) ? "★ Saved" : "☆ Save", (e) => {
          const nowSaved = API.savedLocal.toggle(id);
          e.target.textContent = nowSaved ? "★ Saved" : "☆ Save";
          C.toast(nowSaved ? "Saved to this browser." : "Removed.");
        }),
        toolBtn("⚔ Challenge this analysis", () => openChallenge(id)),
        toolBtn("✓ Show only confirmed facts", (e) => { confirmedOnly = !confirmedOnly; e.target.classList.toggle("btn"); e.target.classList.toggle("secondary"); renderClaims(); }, true),
        exportMenu(s),
      ]));

      // two columns
      const left = h("div");
      const right = h("div");

      // What happened
      left.appendChild(detailSection("What happened", h("p", null, a.what_happened || s.summary)));

      // Verified facts + claims
      const claimsHost = h("div");
      left.appendChild(detailSection("Verified facts", h("ul", { class: "clean" }, (a.verified_facts || []).map((f) => h("li", null, f)))));
      const claimsSection = detailSection("Claims, uncertainties & provenance", claimsHost);
      left.appendChild(claimsSection);
      function renderClaims() {
        claimsHost.innerHTML = "";
        const items = (s.claims || []).filter((c) => !confirmedOnly || c.claim_type === "fact" || c.corroboration === "primary");
        if (!items.length) { claimsHost.appendChild(C.empty(confirmedOnly ? "No confirmed-fact claims to show." : "No claims recorded.")); }
        items.forEach((c) => claimsHost.appendChild(claimEl(c)));
        (a.claims_uncertainties || []).filter(() => !confirmedOnly).forEach((u) =>
          claimsHost.appendChild(h("p", { class: "sd-reason" }, "• " + u)));
      }
      renderClaims();

      // Background
      if (a.background) left.appendChild(detailSection("Background", h("p", null, a.background)));

      // Narrative comparison
      if ((s.narratives || []).length) {
        left.appendChild(detailSection("Narrative comparison",
          h("div", { class: "grid grid-2" }, s.narratives.map((n) => h("div", { class: "narrative" }, [
            h("strong", null, n.label), h("p", { class: "sd-reason" }, "Who: " + (n.who || "—")),
            h("p", null, n.claim), h("p", { class: "sd-reason" }, "Evidence: " + n.evidence),
          ])))));
      } else {
        left.appendChild(detailSection("Narrative comparison",
          h("p", { class: "sd-reason" }, "No materially different narrative captured. Use ‘Challenge this analysis’ to check for missing perspectives.")));
      }

      // Why global / why your work
      if (a.why_global) left.appendChild(detailSection("Why it matters globally", h("p", null, a.why_global)));
      left.appendChild(detailSection("Why this matters to your work",
        h("ul", { class: "clean" }, (a.why_your_work || []).map((w) => h("li", null, w)))));

      // Risk pathway
      if ((a.risk_pathway || []).length) {
        left.appendChild(detailSection("Risk pathway",
          h("p", { class: "sc-sum" }, a.risk_pathway.join("  →  "))));
      }

      // Timeline
      if ((s.events || []).length) {
        left.appendChild(detailSection("Timeline",
          h("div", { class: "timeline" }, s.events.map((e) => h("div", { class: "tl-item" }, [
            h("time", null, API.fmtTime(e.occurred)), h("div", null, h("strong", null, e.title)),
            e.detail ? h("div", { class: "sd-reason" }, e.detail) : null,
          ])))));
      }

      // Questions
      left.appendChild(detailSection("Questions you should ask today",
        h("ul", { class: "clean" }, (a.questions || []).map((q) => h("li", null, q)))));

      // Recommended actions
      left.appendChild(detailSection("Recommended actions",
        h("div", { class: "grid" }, (a.actions || []).map((ac) =>
          h("div", { class: "claim" }, [h("span", { class: "claim-type" }, ac.type), " ", ac.text])))));

      // ---- right column ----
      right.appendChild(h("div", { class: "panel" }, [
        h("h2", null, "Relevance score"),
        h("div", { style: "display:flex;align-items:center;gap:.8rem;margin-bottom:.6rem" }, [C.scoreRing(s.relevance_score), h("span", { class: "sd-reason" }, "0–100 documented model. Each dimension is explained below.")]),
        C.scoreBars(s.scoring),
      ]));
      right.appendChild(h("div", { class: "panel", style: "margin-top:1rem" }, [
        h("h2", null, "Rating rationale"), C.ratingRationale(s.scoring),
      ]));

      // Cross-government advisory consensus (Layer 2), advisory stories only
      const advPanel = C.advisoryConsensus(s.advisory);
      if (advPanel) { advPanel.style.marginTop = "1rem"; right.appendChild(advPanel); }

      // Potentially affected
      const pa = a.potentially_affected || {};
      right.appendChild(h("div", { class: "panel", style: "margin-top:1rem" }, [
        h("h2", null, "Potentially affected"),
        affectedBlock("Countries", (pa.countries || s.countries || []).map((x) => (x || "").toUpperCase())),
        affectedBlock("Business functions", pa.business_functions || []),
        affectedBlock("Infrastructure", pa.infrastructure || []),
      ]));

      // Indicators
      right.appendChild(h("div", { class: "panel", style: "margin-top:1rem" }, [
        h("h2", null, "Indicators to monitor"),
        h("ul", { class: "clean" }, (s.indicators || []).map((i) =>
          h("li", null, [i.text, " ", C.chip(i.direction, i.direction === "improvement" ? "sev-low" : i.direction === "deterioration" ? "sev-high" : "", "◍")]))),
      ]));

      // Sources / transparency
      right.appendChild(h("div", { class: "panel", style: "margin-top:1rem" }, [
        h("h2", null, "Sources & transparency"),
        h("p", { class: "sd-reason" }, "Every claim links to its exact source. Tier 1 = primary/authoritative → Tier 4 = unverified signal."),
        h("div", null, (s.citations || []).map(citationEl)),
      ]));

      // regulation panel if present
      if (s.regulation) right.appendChild(regulationPanel(s.regulation));

      wrap.appendChild(h("div", { class: "detail-cols" }, [left, right]));
      return wrap;
    });
    return node;

    function toolBtn(label, fn, secondary) {
      return h("button", { class: "btn " + (secondary ? "secondary" : "secondary") + " small", onclick: fn }, label);
    }
  }

  function detailSection(title, body) {
    return h("section", { class: "detail-section" }, [h("h3", null, title), body]);
  }
  function claimEl(c) {
    return h("div", { class: "claim" }, [
      h("div", null, [h("span", { class: "claim-type ct-" + c.claim_type }, (c.claim_type || "").replace("_", " ")),
        " ", c.corroboration ? C.chip("corroboration: " + c.corroboration, "", "⛓") : ""]),
      h("p", { style: "margin:.3rem 0 0" }, c.text),
      h("div", { class: "sd-reason" }, "Attributed to: " + (c.attributed_to || "—") +
        (c.source_name ? " · Source: " + c.source_name + " (Tier " + c.source_tier + ")" : "")),
    ]);
  }
  function citationEl(c) {
    return h("div", { class: "citation" }, [
      h("div", { class: "cite-top" }, [
        h("span", { class: "tier-badge tier-" + c.source_tier }, "T" + c.source_tier),
        h("strong", null, c.source_name || "Source"),
        c.is_primary ? C.chip("primary", "sev-low", "◆") : null,
        c.is_circular ? C.chip("circular", "sev-high", "⟳") : null,
      ]),
      h("a", { href: c.url, target: "_blank", rel: "noopener noreferrer" }, C.truncate(c.title || c.url, 90)),
      h("div", { class: "sd-reason" }, "Published: " + API.fmtTime(c.published_at) + " · Accessed: " + API.fmtTime(c.accessed_at) +
        (c.source_country ? " · " + c.source_country.toUpperCase() : "") + (c.orig_language && c.orig_language !== "en" ? " · orig " + c.orig_language : "")),
      c.ownership ? h("div", { class: "sd-reason" }, "Ownership: " + c.ownership) : null,
    ]);
  }
  function affectedBlock(title, items) {
    return h("div", { style: "margin-bottom:.5rem" }, [
      h("div", { class: "section-title", style: "margin:.3rem 0" }, title),
      items && items.length ? h("div", { class: "tag-list" }, items.map((i) => h("span", { class: "tag" }, i)))
        : h("span", { class: "sd-reason" }, "To be confirmed."),
    ]);
  }
  function regulationPanel(r) {
    return h("div", { class: "panel", style: "margin-top:1rem" }, [
      h("div", { class: "sc-top" }, [h("h2", null, "Regulatory detail"), h("span", { class: "status-pill st-" + r.status }, r.status)]),
      h("dl", { class: "reg-grid" }, [
        rg("Jurisdiction", r.jurisdiction), rg("Framework", r.framework), rg("Effective", r.effective_date),
        rg("Obligations", r.obligations), rg("Reporting", r.reporting), rg("Penalties", r.penalties),
        rg("Prep steps", r.prep_steps),
      ]),
      r.source_url ? h("a", { href: r.source_url, target: "_blank", rel: "noopener noreferrer", class: "btn small secondary" }, "Original source") : null,
    ]);
  }
  function rg(k, v) { return [h("dt", null, k), h("dd", null, v || "—")]; }

  function exportMenu(s) {
    const kinds = [
      ["risk_register", "Risk-register entry"], ["corrective_action", "Corrective action"],
      ["executive_summary", "Executive summary"], ["travel_note", "Travel-security note"],
      ["email_leadership", "Email to leadership"], ["risk_register_csv", "Risk register CSV"],
      ["story_json", "Full JSON"],
    ];
    const sel = h("select", { class: "btn secondary small", "aria-label": "Export this development",
      onchange: async (e) => {
        const kind = e.target.value; e.target.selectedIndex = 0;
        if (!kind) return;
        if (kind === "risk_register_csv" || kind === "story_json") {
          window.open("/api/stories/" + encodeURIComponent(s.id) + "/export?kind=" + kind, "_blank");
          return;
        }
        try {
          const res = await API.exportStory(s.id, kind);
          openModal("Export · " + kind.replace("_", " "),
            h("pre", null, typeof res === "string" ? res : JSON.stringify(res, null, 2)));
        } catch (err) { C.toast(err.message); }
      } });
    sel.appendChild(h("option", { value: "" }, "⇩ Export as…"));
    kinds.forEach((k) => sel.appendChild(h("option", { value: k[0] }, k[1])));
    return sel;
  }

  async function openChallenge(id) {
    openModal("Challenge this analysis", C.loading());
    try {
      const data = await API.challenge(id);
      const body = h("div", null, [
        h("p", { class: "sd-reason" }, "Automated red-team across missing perspectives, contradictions, weak assumptions, staleness, over/understated risk, geographic bias, source concentration and circular reporting. Advisory only — human review still applies."),
        h("div", null, data.findings.map((f) => h("div", { class: "finding " + f.severity }, [
          h("div", { class: "f-dim" }, f.dimension + " · " + f.severity),
          h("div", null, f.finding),
        ]))),
      ]);
      setModalBody(body);
    } catch (e) { setModalBody(C.empty(e.message)); }
  }

  // ============================ MAP ============================
  Views.map = function () {
    const node = h("div");
    mount(node, async () => {
      const data = await API.mapData();
      const wrap = h("div");
      wrap.appendChild(head("World / Region View", "Countries are shaded by risk. Click a country to filter its stories, or a marker to open the development."));
      wrap.appendChild(window.GSID_MAP.render(data,
        (id) => go("#/story/" + id),
        (iso) => go("#/stories?country=" + iso)));
      // region summary
      const counts = data.region_counts || {};
      wrap.appendChild(h("div", { class: "grid grid-4", style: "margin-top:1rem" },
        API.state.meta.regions.filter(r => r.id !== "global").map((r) =>
          h("a", { class: "stat", href: "#/stories?region=" + r.id, style: "text-decoration:none" }, [
            h("div", { class: "num" }, String(counts[r.id] || 0)), h("div", { class: "lbl" }, r.name)]))));
      return wrap;
    });
    return node;
  };

  // ============================ REGIONAL ============================
  Views.regional = function () {
    const node = h("div");
    mount(node, async () => {
      const data = await API.regional();
      const wrap = h("div");
      wrap.appendChild(head("Regional Security Watch", "‘No material change identified’ is shown where appropriate — sections are not padded."));
      wrap.appendChild(h("div", { class: "grid grid-2" }, data.regions.map((r) =>
        h("section", { class: "panel" }, [
          h("div", { class: "sc-top" }, [h("h2", null, r.region_name), C.chip(r.stories.length + " items", "", "▦")]),
          r.no_material_change ? h("p", { class: "sd-reason" }, "No material change identified.")
            : h("div", { class: "grid" }, r.stories.map((s) => C.storyCard(s, openStory))),
        ]))));
      return wrap;
    });
    return node;
  };

  // ============================ REGULATORY ============================
  Views.regulatory = function () {
    const node = h("div");
    mount(node, async () => {
      const data = await API.regulations();
      const wrap = h("div");
      wrap.appendChild(head("Regulatory Tracker", "Lifecycle status is explicit — a proposal is never shown as enacted law."));
      wrap.appendChild(h("div", { class: "grid" }, data.regulations.map((r) =>
        h("article", { class: "reg-card" }, [
          h("div", { class: "sc-top" }, [h("h2", null, r.title.replace("[DEMO] ", "")), h("span", { class: "status-pill st-" + r.status }, r.status)]),
          h("div", { class: "sc-meta" }, [C.chip(r.jurisdiction, "", "§"), r.framework ? C.chip(r.framework, "", "▦") : null,
            r.effective_date ? C.chip("Effective: " + r.effective_date, "", "◔") : null]),
          h("dl", { class: "reg-grid" }, [
            rg("Affected", r.affected), rg("Obligations", r.obligations), rg("Reporting timelines", r.reporting),
            rg("Penalties / enforcement", r.penalties), rg("Practical implications", r.implications),
            rg("Recommended preparation", r.prep_steps),
          ]),
          h("div", { class: "btn-row" }, [
            r.source_url ? h("a", { class: "btn small secondary", href: r.source_url, target: "_blank", rel: "noopener noreferrer" }, "Original source") : null,
            r.story_id ? h("a", { class: "btn small secondary", href: "#/story/" + r.story_id }, "Related story") : null,
          ]),
        ]))));
      return wrap;
    });
    return node;
  };

  // ============================ SUPPLY / CYBER (category views) ============================
  Views.supply = categoryView("Supply-Chain Security Watch", "supply_chain", "Ports, borders, shipping routes, cargo crime, customs, strikes, CTPAT-relevant developments.");
  Views.cyber = categoryView("Cyber-Physical Watch", "cyber_physical", "Incidents that could affect factories, buildings, physical-security systems, ICS/OT, and continuity.");

  function categoryView(title, cat, sub) {
    return function () {
      const node = h("div");
      mount(node, async () => {
        const data = await API.stories("category=" + cat + "&limit=50");
        const wrap = h("div");
        wrap.appendChild(head(title, sub));
        wrap.appendChild(data.stories.length ? h("div", { class: "grid grid-2" }, data.stories.map((s) => C.storyCard(s, openStory)))
          : C.empty("No qualifying developments."));
        return wrap;
      });
      return node;
    };
  }

  // ============================ SAVED ============================
  Views.saved = function () {
    const node = h("div");
    async function refresh(target) {
      target.innerHTML = ""; target.appendChild(C.loading());
      const items = API.savedLocal.all();
      // Fetch each saved story on demand (tolerate ones that no longer exist).
      const stories = await Promise.all(items.map((it) =>
        API.story(it.story_id).catch(() => null)));
      target.innerHTML = "";
      const live = stories.filter(Boolean);
      if (!live.length) { target.appendChild(C.empty("No saved stories yet. Open a story and click ☆ Save.")); return; }
      live.forEach((story) => {
        const card = C.storyCard(story, openStory);
        card.appendChild(h("button", { class: "btn small secondary", onclick: (e) => {
          e.stopPropagation(); API.savedLocal.remove(story.id); refresh(target);
        } }, "Remove"));
        target.appendChild(card);
      });
    }
    const wrap = h("div");
    wrap.appendChild(head("Saved Stories", "Saved to this browser — private to you, no account needed."));
    const list = h("div", { class: "grid grid-2" });
    wrap.appendChild(list);
    node.appendChild(wrap);
    refresh(list);
    return node;
  };

  // ============================ LEARN (quiz + scenario) ============================
  Views.learn = function () {
    const node = h("div");
    mount(node, async () => {
      const wrap = h("div");
      wrap.appendChild(head("Learn & Exercise", "Interactive scenario + daily knowledge check. Performance is tracked locally to adapt difficulty."));

      // Scenario
      const scenList = await API.scenarios();
      const scenHost = h("div", { class: "panel" });
      wrap.appendChild(scenHost);
      if (scenList.scenarios.length) {
        renderScenario(scenHost, scenList.scenarios);
      } else scenHost.appendChild(C.empty("No scenario available."));

      // Quiz
      const quizHost = h("div", { class: "panel", style: "margin-top:1rem" });
      wrap.appendChild(quizHost);
      renderQuiz(quizHost);

      return wrap;
    });
    return node;
  };

  async function renderScenario(host, list, currentId) {
    // Rotate to a fresh scenario, avoiding an immediate repeat when possible.
    let pool = list;
    if (currentId && list.length > 1) pool = list.filter((s) => s.id !== currentId);
    const pick = pool[Math.floor(Math.random() * pool.length)];
    host.innerHTML = "";
    host.appendChild(C.loading());
    const sc = await API.scenario(pick.id);
    host.innerHTML = "";
    host.appendChild(h("div", { class: "sc-top" }, [
      h("h2", null, "10 · Interactive Scenario"),
      list.length > 1
        ? h("button", { class: "btn secondary small", onclick: () => renderScenario(host, list, sc.id) }, "New scenario")
        : null,
    ]));
    host.appendChild(h("h3", null, sc.title));
    host.appendChild(h("p", null, sc.prompt));
    const analysisHost = h("div");
    sc.options.forEach((opt, i) => {
      host.appendChild(h("button", { class: "scenario-opt", onclick: () => {
        analysisHost.innerHTML = "";
        analysisHost.appendChild(h("div", { class: "scenario-analysis" }, [
          h("strong", null, "You chose: " + opt.text),
          h("p", null, [h("strong", null, "Strengths: "), opt.strengths]),
          h("p", null, [h("strong", null, "Risks / blind spots: "), opt.blindspots]),
          h("p", null, [h("strong", null, "Better next steps: "), opt.better]),
          h("p", { class: "sd-reason" }, "Principle: " + sc.principle),
        ]));
      } }, (i + 1) + ". " + opt.text));
    });
    host.appendChild(analysisHost);
    if (sc.story_id) host.appendChild(h("a", { class: "btn small secondary", href: "#/story/" + sc.story_id }, "See related development"));
  }

  async function renderQuiz(host) {
    host.innerHTML = "";
    host.appendChild(C.loading());
    const level = API.state.quizStats.correct > 4 ? 3 : API.state.quizStats.correct > 2 ? 2 : "";
    const data = await API.quiz(level);
    host.innerHTML = "";
    host.appendChild(h("h2", null, "11 · Quick Knowledge Check"));
    const stats = API.state.quizStats;
    host.appendChild(h("p", { class: "sd-reason" }, "Local score: " + stats.correct + " / " + stats.asked + " correct. Difficulty adapts to your performance."));
    data.questions.forEach((q) => {
      const qEl = h("div", { class: "quiz-q" }, [h("strong", null, q.question)]);
      const opts = q.options.map((o, i) => h("button", { class: "quiz-opt", onclick: async (e) => {
        const btns = qEl.querySelectorAll(".quiz-opt"); btns.forEach((b) => (b.disabled = true));
        const res = await API.quizAnswer(q.id, i);
        stats.asked++; if (res.correct) stats.correct++;
        API.LS.set("quizStats", stats);
        btns[res.answer_index].classList.add("correct");
        if (!res.correct) e.target.classList.add("wrong");
        qEl.appendChild(h("p", { class: "sd-reason" }, (res.correct ? "✓ Correct. " : "✗ Not quite. ") + res.explanation));
      } }, o));
      opts.forEach((o) => qEl.appendChild(o));
      host.appendChild(qEl);
    });
    host.appendChild(h("button", { class: "btn secondary small", onclick: () => renderQuiz(host) }, "New questions"));
  }

  // ============================ TRANSPARENCY / AUDIT ============================
  Views.transparency = function () {
    const node = h("div");
    mount(node, async () => {
      const audit = await API.audit();
      const wrap = h("div");
      wrap.appendChild(head("Transparency & Audit", "How this desk sources, verifies and scores — plus an audit trail of automated analysis and manual changes."));
      wrap.appendChild(h("div", { class: "grid grid-2" }, [
        h("div", { class: "panel" }, [h("h2", null, "Source tiers"),
          h("dl", { class: "kv" }, Object.entries(API.state.meta.source_tiers).flatMap(([k, v]) => [h("dt", null, "Tier " + k), h("dd", null, v)]))]),
        h("div", { class: "panel" }, [h("h2", null, "Confidence model"),
          h("ul", { class: "clean" }, [
            h("li", null, "Confirmed — primary evidence + multiple reliable sources."),
            h("li", null, "High — strongly corroborated, minor details unresolved."),
            h("li", null, "Moderate — credible reporting, important details uncertain."),
            h("li", null, "Low — limited or conflicting evidence."),
            h("li", null, "Unverified — single-source / social / unsupported."),
          ])]),
      ]));
      wrap.appendChild(h("div", { class: "panel", style: "margin-top:1rem" }, [
        h("h2", null, "Relevance scoring model (0–100)"),
        h("p", { class: "sd-reason" }, "People safety 20 · Facilities 15 · Operational 15 · Supply-chain 15 · Regulatory 15 · Geopolitical 10 · Cyber-physical 5 · Reputational 5. Each story explains every point awarded."),
      ]));
      wrap.appendChild(h("div", { class: "panel", style: "margin-top:1rem" }, [
        h("h2", null, "Audit log (latest 200)"),
        h("div", { style: "max-height:420px;overflow:auto" }, h("dl", { class: "kv" },
          audit.audit.flatMap((a) => [
            h("dt", { style: "font-family:var(--mono);font-size:.74rem" }, API.fmtTime(a.ts)),
            h("dd", null, "[" + a.actor + "] " + a.action + (a.entity ? " · " + a.entity : "") + (a.detail ? " — " + C.truncate(a.detail, 80) : "")),
          ]))),
      ]));
      return wrap;
    });
    return node;
  };

  // ============================ SETTINGS ============================
  Views.settings = function () {
    const node = h("div");
    mount(node, async () => {
      const [prefs, meta] = await Promise.all([API.preferences(), Promise.resolve(API.state.meta)]);
      const readonly = !!(meta.public_readonly && !meta.is_admin);
      const wrap = h("div");
      wrap.appendChild(head("Watchlist & Settings",
        readonly ? "Public read-only view. Sign in as admin to change the shared watchlist and settings."
                 : "Personalize the desk. Changes are saved to the server."));

      if (readonly) {
        wrap.appendChild(h("div", { class: "ro-banner" }, [
          h("span", { class: "ro-ico", "aria-hidden": "true" }, "🔒"),
          h("span", null, "This is a public deployment. You can browse everything and refresh the data, "
            + "but the shared watchlist and settings are locked. Your saved stories and quiz progress "
            + "are private to this browser."),
        ]));
      }

      const draft = JSON.parse(JSON.stringify(prefs));

      function listEditor(key, label, placeholder) {
        const host = h("div", { class: "tag-list" });
        function paint() {
          host.innerHTML = "";
          (draft[key] || []).forEach((v, idx) => host.appendChild(h("span", { class: "tag" },
            readonly ? [v] : [v,
            h("button", { "aria-label": "Remove " + v, onclick: () => { draft[key].splice(idx, 1); paint(); } }, "✕")])));
        }
        paint();
        if (readonly) {
          return h("div", { class: "panel" }, [h("h2", null, label),
            (draft[key] || []).length ? host : h("p", { class: "sd-reason" }, "None configured.")]);
        }
        const input = h("input", { placeholder, onkeydown: (e) => {
          if (e.key === "Enter") { e.preventDefault(); const v = e.target.value.trim(); if (v) { draft[key] = draft[key] || []; draft[key].push(v); e.target.value = ""; paint(); } }
        } });
        return h("div", { class: "panel" }, [h("h2", null, label), host, input, h("div", { class: "sd-reason" }, "Type and press Enter to add.")]);
      }

      wrap.appendChild(h("div", { class: "grid grid-2" }, [
        listEditor("countries", "Countries of operation", "e.g. us, de, in"),
        listEditor("topics", "Priority topics", "e.g. cargo theft"),
        listEditor("sites", "Corporate sites", "e.g. Frankfurt DC"),
        listEditor("suppliers", "Supplier locations", "e.g. Shenzhen supplier"),
        listEditor("routes", "Ports & shipping routes", "e.g. Asia–Europe"),
        listEditor("travel_destinations", "Employee-travel destinations", "e.g. Nairobi"),
        listEditor("industries", "Industries", "e.g. manufacturing"),
        listEditor("regulations", "Regulations to track", "e.g. NIS2"),
      ]));

      // scalar prefs
      const dis = readonly ? { disabled: "disabled" } : null;
      const risk = h("select", dis, ["low", "moderate", "high"].map((v) => h("option", { value: v, selected: draft.risk_tolerance === v ? "selected" : null }, v)));
      risk.onchange = (e) => (draft.risk_tolerance = e.target.value);
      const length = h("select", dis, ["brief", "standard", "detailed"].map((v) => h("option", { value: v, selected: draft.briefing_length === v ? "selected" : null }, v)));
      length.onchange = (e) => (draft.briefing_length = e.target.value);
      const tz = h("input", Object.assign({ value: draft.timezone || API.state.tz }, dis));
      tz.onchange = (e) => (draft.timezone = e.target.value);
      const rtime = h("input", Object.assign({ type: "time", value: draft.report_time || "07:00" }, dis));
      rtime.onchange = (e) => (draft.report_time = e.target.value);

      wrap.appendChild(h("div", { class: "panel", style: "margin-top:1rem" }, [
        h("h2", null, "Preferences"),
        h("div", { class: "grid grid-4" }, [
          h("label", null, ["Risk tolerance", risk]),
          h("label", null, ["Briefing length", length]),
          h("label", null, ["Timezone", tz]),
          h("label", null, ["Preferred report time", rtime]),
        ]),
      ]));

      // access / admin + refresh
      const tokenInput = h("input", { type: "password", value: API.state.token,
        placeholder: meta.public_readonly ? "Admin token" : "Access token (if auth enabled)" });
      const adminState = h("span", { class: "sd-reason" },
        meta.is_admin ? "✓ Admin unlocked — you can edit settings." :
        meta.public_readonly ? "Viewer (read-only). Enter the admin token to unlock editing." : "");
      wrap.appendChild(h("div", { class: "panel", style: "margin-top:1rem" }, [
        h("h2", null, meta.public_readonly ? "Admin access & data" : "Access & live data"),
        h("p", { class: "sd-reason" }, "Data mode: " + meta.data_mode + " · AI: " + meta.ai_provider
          + " · Mode: " + (meta.public_readonly ? "public read-only" : "full control")),
        h("label", null, [meta.public_readonly ? "Admin token" : "Access token", tokenInput]),
        adminState,
        h("div", { class: "btn-row", style: "margin-top:.6rem" }, [
          h("button", { class: "btn secondary", onclick: async () => {
            API.state.token = tokenInput.value; API.LS.set("token", tokenInput.value);
            try {
              const chk = await API.req("/api/admin/check");
              C.toast(chk.is_admin ? "Admin unlocked." : "Token saved (not admin).");
              if (chk.is_admin) location.reload();           // re-render with edit rights
            } catch (e) { C.toast("Saved token."); }
          } }, meta.public_readonly ? "Unlock admin" : "Save token"),
          (!meta.public_readonly || meta.public_allow_refresh || meta.is_admin)
            ? h("button", { class: "btn secondary", onclick: async (e) => {
                e.target.disabled = true; e.target.textContent = "Refreshing…";
                try { const r = await API.ingest(); C.toast("Refreshed: " + r.stories_saved + " stories from " + r.feeds_polled + " feeds."); }
                catch (err) { C.toast(err.message); }
                e.target.disabled = false; e.target.textContent = "↻ Refresh data now";
              } }, "↻ Refresh data now")
            : null,
        ]),
        h("p", { class: "sd-reason" }, meta.data_mode === "demo"
          ? "Live refresh requires GSID_DATA_MODE=live or hybrid."
          : "Refresh pulls the latest items from all configured feeds."),
      ]));

      // ---- Feed health indicator ----
      const healthHost = h("div");
      async function loadHealth() {
        healthHost.innerHTML = "";
        healthHost.appendChild(C.loading());
        try {
          const data = await API.feedHealth();
          healthHost.innerHTML = "";
          healthHost.appendChild(renderFeedHealth(data));
        } catch (e) {
          healthHost.innerHTML = "";
          healthHost.appendChild(C.empty("Could not load feed health: " + e.message));
        }
      }
      wrap.appendChild(h("div", { class: "panel", style: "margin-top:1rem" }, [
        h("div", { class: "sc-top" }, [
          h("h2", null, "Source feed health"),
          h("button", { class: "btn small secondary", onclick: loadHealth }, "↻ Refresh"),
        ]),
        h("p", { class: "sd-reason" }, "Status of each ingestion feed at the last poll. Updates every time ingestion runs."),
        healthHost,
      ]));
      loadHealth();

      if (!readonly) {
        wrap.appendChild(h("div", { class: "btn-row", style: "margin-top:1rem" }, [
          h("button", { class: "btn", onclick: async () => {
            try { await API.savePreferences(draft); C.toast("Preferences saved."); } catch (e) { C.toast(e.message); } } }, "Save all preferences"),
        ]));
      }
      return wrap;
    });
    return node;
  };

  // ============================ TRAVEL RISK ============================
  Views.travel = function (params) {
    const node = h("div");
    const meta = API.state.meta;
    const briefHost = h("div");
    const trip = { country: null, origin: "" };  // destination + traveller nationality

    async function run() {
      if (!trip.country) return;
      const q = "#/travel?country=" + trip.country + (trip.origin ? "&origin=" + trip.origin : "");
      window.location.hash = q;  // shareable
      briefHost.innerHTML = "";
      briefHost.appendChild(C.loading());
      try {
        const tb = await API.travel(trip.country, trip.origin);
        briefHost.innerHTML = "";
        briefHost.appendChild(renderTravelBrief(tb));
      } catch (e) {
        briefHost.innerHTML = "";
        briefHost.appendChild(C.empty("Could not load: " + e.message));
      }
    }
    function loadCountry(code) { trip.country = code; run(); }

    mount(node, async () => {
      const prefs = await API.preferences();
      const wrap = h("div");
      wrap.appendChild(head("Travel Risk",
        "Pick a destination for the official advisory and what your travellers should watch for. "
        + "Add a traveller nationality to lead with the matching government's advice."));

      // destination picker
      const select = h("select", { "aria-label": "Destination country" },
        [h("option", { value: "" }, "— Select destination —")]
          .concat((meta.countries || []).map((c) => h("option", { value: c.code }, c.name))));
      select.onchange = (e) => { if (e.target.value) loadCountry(e.target.value); };

      // traveller nationality picker (optional)
      const originSel = h("select", { "aria-label": "Traveller nationality" },
        [h("option", { value: "" }, "Any / show UK + US")]
          .concat((meta.countries || []).map((c) => h("option", { value: c.code }, c.name))));
      originSel.onchange = (e) => { trip.origin = e.target.value; run(); };

      wrap.appendChild(h("div", { class: "filters" }, [
        h("label", null, ["Destination", select]),
        h("label", null, ["Traveller nationality (optional)", originSel]),
        h("span", { class: "sd-reason" }, "The risk picture is destination-based; nationality only decides whose advisory leads and entry/visa context."),
      ]));

      // saved travel destinations as quick chips
      const saved = (prefs.travel_destinations || []);
      if (saved.length) {
        wrap.appendChild(h("div", { class: "tag-list", style: "margin-bottom:.8rem" },
          [h("span", { class: "sd-reason", style: "margin-right:.3rem" }, "Your watchlist:")].concat(
            saved.map((d) => {
              const code = resolveClientCountry(d, meta.countries);
              return h("button", { class: "btn small secondary", onclick: () => code && loadCountry(code) },
                "✈ " + d);
            }))));
      }

      wrap.appendChild(briefHost);
      // deep link ?country=&origin=
      if (params && params.origin) { trip.origin = params.origin; originSel.value = params.origin; }
      if (params && params.country) { select.value = params.country; loadCountry(params.country); }
      return wrap;
    });
    return node;

    function renderTravelBrief(tb) {
      const wrap = h("div");
      // header banner with highest impact
      wrap.appendChild(h("div", { class: "panel", style: "margin-bottom:1rem" }, [
        h("div", { class: "sc-top" }, [
          h("h2", null, "✈ " + tb.country_name),
          // Lead with the authoritative government advisory level; fall back to
          // the developments-impact heuristic only when no advisory exists.
          C.advisoryLevelChip(tb.advisory_consensus, tb.advisory_consensus_label)
            || C.impactChip(tb.highest_impact),
        ]),
        h("div", { class: "sd-reason" }, "Region: " + tb.region_name +
          " · " + tb.advisories.length + " official advisory record(s) · " +
          tb.related.length + " related development(s)"),
        h("div", { class: "btn-row", style: "margin-top:.6rem" },
          tb.official_links.map((l) => h("a", { class: "btn small", href: l.url, target: "_blank", rel: "noopener noreferrer" }, "Official: " + l.name))),
      ]));

      // traveller context (nationality-dependent)
      const tv = tb.traveller || {};
      wrap.appendChild(h("div", { class: "panel", style: "margin-bottom:1rem" }, [
        h("h2", null, tv.origin ? ("Traveller context — " + tv.origin_name) : "Traveller context"),
        h("p", null, tv.note),
        tv.entry_note ? h("p", { class: "sd-reason" }, "Entry & visa: " + tv.entry_note) : null,
      ]));

      // cross-government advisory consensus (Layer 2) — worst-case + divergence
      (tb.advisories || []).forEach((a) => {
        const panel = C.advisoryConsensus(a.advisory);
        if (panel) wrap.appendChild(panel);
      });

      // official advisory records
      if (tb.advisories.length) {
        wrap.appendChild(h("div", { class: "panel", style: "margin-bottom:1rem" }, [
          h("h2", null, "Government travel advisory"),
          h("div", null, tb.advisories.map((a) => h("div", { class: "citation" }, [
            h("div", null, h("strong", null, C.cleanHeadline(a.headline))),
            a.summary ? h("p", { class: "sd-reason" }, "Latest change: " + a.summary) : null,
            h("div", null, (a.citations || []).map((c) =>
              h("div", null, h("a", { href: c.url, target: "_blank", rel: "noopener noreferrer" },
                (c.source_name || "source") + " → full advisory")))),
            h("a", { class: "btn small secondary", href: "#/story/" + a.id }, "Open in desk"),
          ]))),
        ]));
      } else {
        wrap.appendChild(h("div", { class: "panel", style: "margin-bottom:1rem" }, [
          h("h2", null, "Government travel advisory"),
          h("p", { class: "sd-reason" }, "No advisory update has been ingested for this destination recently. Use the official links above for the current, authoritative advisory."),
        ]));
      }

      // what to look out for
      wrap.appendChild(h("div", { class: "panel", style: "margin-bottom:1rem" }, [
        h("h2", null, "What to look out for"),
        tb.watch_items.length ? h("ul", { class: "clean" }, tb.watch_items.map((w) => h("li", null, w)))
          : h("p", { class: "sd-reason" }, "No specific indicators flagged from current developments. Baseline travel precautions apply."),
      ]));

      // recommended actions
      if (tb.recommended_actions && tb.recommended_actions.length) {
        wrap.appendChild(h("div", { class: "panel", style: "margin-bottom:1rem" }, [
          h("h2", null, "Recommended actions for travellers / security"),
          h("div", { class: "grid" }, tb.recommended_actions.map((a) =>
            h("div", { class: "claim" }, [h("span", { class: "claim-type" }, a.type), " ", a.text]))),
        ]));
      }

      // related developments
      wrap.appendChild(h("div", { class: "panel" }, [
        h("h2", null, "Relevant developments in / near " + tb.country_name),
        tb.related.length ? h("div", { class: "grid grid-2" }, tb.related.map((s) => C.storyCard(s, openStory)))
          : h("p", { class: "sd-reason" }, "No material developments currently tracked for this destination."),
      ]));

      return wrap;
    }
  };

  function renderFeedHealth(data) {
    const feeds = data.feeds || [];
    // Accessible status meta: symbol + label + class (never colour alone).
    const META = {
      ok: { sym: "●", label: "OK", cls: "fh-ok" },
      empty: { sym: "▲", label: "No items", cls: "fh-empty" },
      error: { sym: "✕", label: "Error", cls: "fh-error" },
      unknown: { sym: "○", label: "Not polled", cls: "fh-unknown" },
    };
    const okCount = feeds.filter((f) => f.status === "ok").length;
    const problems = feeds.filter((f) => f.status === "error" || f.status === "empty").length;

    const rows = feeds.map((f) => {
      const m = META[f.status] || META.unknown;
      const last = f.last_success ? API.fmtTime(f.last_success) : "—";
      return h("tr", null, [
        h("td", null, h("span", { class: "fh-dot " + m.cls, title: m.label }, [
          h("span", { "aria-hidden": "true" }, m.sym), " ",
          h("span", null, m.label),
        ])),
        h("td", null, [h("a", { href: f.url, target: "_blank", rel: "noopener noreferrer" }, f.name),
          h("div", { class: "sd-reason" }, "tier " + f.tier + " · " + f.source_type +
            (f.error ? " · " + f.error : ""))]),
        h("td", { class: "num" }, String(f.last_count)),
        h("td", { class: "sd-reason" }, last),
      ]);
    });

    const wrap = h("div");
    wrap.appendChild(h("p", { class: "sd-reason" },
      okCount + " healthy · " + problems + " with issues · " + feeds.length + " total"));
    wrap.appendChild(h("table", { class: "fh-table" }, [
      h("thead", null, h("tr", null, [
        h("th", null, "Status"), h("th", null, "Feed"),
        h("th", { class: "num" }, "Items"), h("th", null, "Last success"),
      ])),
      h("tbody", null, rows),
    ]));
    return wrap;
  }

  function resolveClientCountry(text, countries) {
    if (!text) return null;
    const t = String(text).trim().toLowerCase();
    const hit = (countries || []).find((c) => c.name.toLowerCase() === t || c.code === t);
    return hit ? hit.code : null;
  }

  // ============================ SEARCH ============================
  Views.search = function (params) {
    const node = h("div");
    const q = params.q || "";
    mount(node, async () => {
      const data = await API.search(q);
      const wrap = h("div");
      wrap.appendChild(head("Search results", '"' + q + '" · ' + data.stories.length + " matches"));
      wrap.appendChild(data.stories.length ? h("div", { class: "grid grid-2" }, data.stories.map((s) => C.storyCard(s, openStory)))
        : C.empty("No matches. Try different keywords."));
      return wrap;
    });
    return node;
  };

  // ---------- shared helpers exposed to router ----------
  function openStory(id) { go("#/story/" + id); }
  function go(hash) { window.location.hash = hash; }

  // modal helpers
  function openModal(title, bodyNode) {
    document.getElementById("modalTitle").textContent = title;
    setModalBody(bodyNode);
    const host = document.getElementById("modalHost");
    host.hidden = false;
  }
  function setModalBody(bodyNode) {
    const b = document.getElementById("modalBody");
    b.innerHTML = ""; b.appendChild(bodyNode);
  }

  window.GSID_VIEWS = Views;
  window.GSID_NAV = { go, openModal };
})();
