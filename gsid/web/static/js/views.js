/* View renderers. Each returns a DOM node (may fetch its own data). */
(function () {
  "use strict";
  const API = window.GSID_API;
  const C = window.GSID_C;
  const h = C.h;
  const Views = {};

  const UI = window.GSID_UI;
  const CH = window.GSID_CHARTS;

  function head(title, sub, actions, eyebrow) {
    return h("div", { class: "page-head" }, [
      h("div", { class: "ph-main" }, [
        eyebrow ? h("div", { class: "ph-eyebrow" }, eyebrow) : null,
        h("h1", null, title),
        sub ? h("div", { class: "sub" }, sub) : null,
      ]),
      actions ? h("div", { class: "page-head-actions" }, actions) : null,
    ]);
  }

  /**
   * Render a view asynchronously.
   * `skel` picks the skeleton shape so the page does not jump when data lands.
   * A failure shows a retry rather than a dead end — one bad endpoint should
   * not cost the operator the whole page.
   */
  async function mount(node, builder, skel) {
    node.innerHTML = "";
    node.appendChild(UI.loadingState(skel || "line", 5));
    try {
      const content = await builder();
      node.innerHTML = "";
      node.appendChild(content);
    } catch (e) {
      node.innerHTML = "";
      node.appendChild(UI.errorState("Could not load this view: " + e.message,
        function () { mount(node, builder, skel); }));
    }
  }

  /**
   * Fill a panel from its own request, after the page has already painted.
   * Analytics panels need a 300-story fetch that would otherwise block the
   * alerts and map above them, which are what an operator opens this page for.
   */
  function lazyPanel(host, builder, skel) {
    host.appendChild(UI.loadingState(skel || "chart", 3));
    Promise.resolve().then(builder).then(function (node) {
      host.innerHTML = ""; host.appendChild(node);
    }).catch(function (e) {
      host.innerHTML = "";
      host.appendChild(UI.errorState("Panel unavailable: " + e.message,
        function () { host.innerHTML = ""; lazyPanel(host, builder, skel); }));
    });
  }

  /** Panel with the standard header strip. */
  function panel(title, action, body, cls) {
    return h("section", { class: "panel " + (cls || "") }, [
      h("div", { class: "panel-head" }, [
        h("h2", null, title),
        action || null,
      ]),
      body,
    ]);
  }
  function panelLink(text, href) { return h("a", { class: "panel-act", href: href }, text); }

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
      // Two light requests for the fold; the 300-story analytics set is fetched
      // afterwards by the row-3 panels so it cannot delay alerts or the map.
      const [brief, map] = await Promise.all([API.brief(), API.mapData()]);
      const p = brief.global_risk_pulse;
      const wrap = h("div", { class: "dash" });

      wrap.appendChild(head(
        "Executive Dashboard",
        p.posture.reason,
        [h("a", { class: "btn secondary", href: "#/brief" }, "Open Daily Brief"),
         h("a", { class: "btn", href: "#/alerts" }, "Critical Alerts")],
        "Global posture \u00b7 generated " + API.fmtTime(brief.generated_at)));

      // ---- Row 1: posture + metrics -----------------------------------
      const lvl = p.posture.level;
      const pct = POSTURE_PCT[lvl] != null ? POSTURE_PCT[lvl] : 55;
      const countries = Object.keys(map.country_risk || {});
      const severeCountries = countries.filter((c) =>
        ["Critical", "High"].indexOf((map.country_risk[c] || {}).impact) >= 0);
      const alertsCount = brief.critical_alerts.length;

      wrap.appendChild(h("div", { class: "dash-row1" }, [
        h("section", { class: "posture-card" }, [
          h("div", { class: "pc-gauge", style: "--pct:" + pct + "%" }, [
            h("div", { class: "pc-gauge-in" }, [
              h("span", { class: "pc-num num" }, String(pct)),
              h("span", { class: "pc-of" }, "INDEX"),
            ]),
          ]),
          h("div", { class: "pc-body" }, [
            h("div", { class: "pc-eyebrow" }, "Global risk posture"),
            h("div", { class: "pc-level lvl-" + slug(lvl) }, lvl),
            h("p", { class: "pc-reason" }, p.posture.reason),
          ]),
        ]),
        h("div", { class: "metric-row dash-metrics" }, [
          UI.metricCard({ label: "Critical alerts", value: alertsCount,
            severity: alertsCount ? "Critical" : null, href: "#/alerts",
            hint: alertsCount ? "requiring prompt action" : "none active" }),
          UI.metricCard({ label: "Active stories", value: brief.story_count,
            href: "#/stories", hint: "developments tracked" }),
          UI.metricCard({ label: "Countries tracked", value: countries.length,
            href: "#/map",
            hint: severeCountries.length + " at high or critical impact" }),
          UI.metricCard({ label: "Regions worsening", value: p.regions_deteriorating.length,
            severity: p.regions_deteriorating.length ? "High" : null, href: "#/regional",
            hint: p.regions_improving.length + " improving" }),
          // Filled in below from a real count, not estimated from this payload.
          (function () {
            const card = h("div", { class: "metric-card mc-pending" }, [
              h("div", { class: "mc-label" }, "New today"),
              h("div", { class: "mc-value-row" }, h("span", { class: "mc-value num" }, "\u2014")),
            ]);
            API.stories("new_today=1&limit=300").then(function (r) {
              const n = (r.stories || []).length;
              card.replaceWith(UI.metricCard({ label: "New today", value: n,
                href: "#/stories?new_today=1",
                hint: n ? "first seen in the last 24h" : "nothing new since yesterday" }));
            }).catch(function () {
              card.replaceWith(UI.metricCard({ label: "New today", value: null,
                hint: "count unavailable" }));
            });
            return card;
          })(),
        ]),
      ]));

      // ---- Row 2: threat map + critical alerts rail --------------------
      const mapHost = h("div", { class: "dash-map-host" });
      const mapPanel = panel("Global threat picture",
        panelLink("Open world view \u2192", "#/map"), mapHost, "flush dash-map");
      // The globe owns its own render + interaction; reuse it rather than
      // re-implementing, so click-through and rotation keep working.
      try {
        mapHost.appendChild(window.GSID_MAP.render(map,
          function (pt) { location.hash = "#/story/" + pt.id; },
          function (cc) { location.hash = "#/stories?country=" + cc; }));
      }
      catch (e) { mapHost.appendChild(UI.errorState("Map unavailable: " + e.message)); }

      const alertRail = panel("Critical alerts",
        panelLink("All \u2192", "#/alerts"),
        alertsCount
          ? h("ul", { class: "alert-rail" }, brief.critical_alerts.slice(0, 7).map(alertRailItem))
          : UI.emptyState("No developments currently meet the alert threshold."),
        "flush dash-alerts");

      wrap.appendChild(h("div", { class: "dash-row2" }, [mapPanel, alertRail]));

      // ---- Row 3: analytics (lazy) -------------------------------------
      const trendHost = h("div"), regionHost = h("div"), catHost = h("div");
      wrap.appendChild(h("div", { class: "dash-row3" }, [
        panel("Intelligence volume \u2014 14 days", null, trendHost),
        panel("Regional risk breakdown", panelLink("Regions \u2192", "#/regional"), regionHost),
        panel("Threat category distribution", panelLink("Stories \u2192", "#/stories"), catHost),
      ]));

      // One fetch feeds all three panels.
      const recent = API.stories("sort=recent&limit=300");
      lazyPanel(trendHost, async () => volumeTrend((await recent).stories), "chart");
      lazyPanel(regionHost, async () => regionSeverity((await recent).stories), "chart");
      lazyPanel(catHost, async () => categoryDonut((await recent).stories), "chart");

      // ---- Row 4: latest intelligence -----------------------------------
      const feedHost = h("div");
      wrap.appendChild(panel("Latest intelligence",
        panelLink("All stories \u2192", "#/stories"), feedHost, "flush"));
      lazyPanel(feedHost, async () => latestFeed((await recent).stories), "table");

      // ---- Row 5: emerging risks + executive summary --------------------
      wrap.appendChild(h("div", { class: "dash-row5" }, [
        panel("Emerging risks & regional watch", panelLink("Regional \u2192", "#/regional"),
          h("div", { class: "emerging" }, [
            movers("Deteriorating", p.regions_deteriorating, "High"),
            movers("Improving", p.regions_improving, "Low"),
            p.emerging_hotspots && p.emerging_hotspots.length
              ? h("div", { class: "em-block" }, [
                  h("div", { class: "em-title" }, "Emerging hotspots"),
                  h("div", { class: "em-tags" },
                    p.emerging_hotspots.map((r) => UI.tag(r, "#/regional"))),
                ])
              : null,
            (p.watch_next && p.watch_next.length)
              ? h("div", { class: "em-block" }, [
                  h("div", { class: "em-title" }, "Watch next 24\u201372h"),
                  h("ul", { class: "watch-list" }, p.watch_next.map((w) =>
                    h("li", null, h("a", { href: "#/story/" + w.id }, C.cleanHeadline(w.headline))))),
                ])
              : null,
          ])),
        panel("Executive summary", panelLink("Full brief \u2192", "#/brief"),
          h("div", null, [
            h("ol", { class: "exec-points" },
              (brief.executive_talking_points || []).map((t) => h("li", null, t))),
            h("div", { class: "exec-top" }, [
              h("div", { class: "et-title" }, "Top ranked developments"),
              h("ol", { class: "rank-list compact" },
                brief.executive_snapshot.slice(0, 3).map((st, i) => rankItem(st, i))),
            ]),
          ])),
      ]));

      return wrap;
    }, "metrics");
    return node;
  };

  // ---- dashboard parts ------------------------------------------------
  function slug(str) { return String(str || "").toLowerCase().replace(/[^a-z]/g, ""); }

  /** Ranked development row. Rebuilt on the kit's badges so the severity glyph
   *  and confidence language match every other surface. */
  function rankItem(s, i) {
    const d = DIR_META[s.trend] || DIR_META["Stable"];
    return h("li", { class: "rank-item", tabindex: "0", role: "link",
                     onclick: function () { location.hash = "#/story/" + s.id; },
                     onkeydown: function (e) {
                       if (e.key === "Enter" || e.key === " ") {
                         e.preventDefault(); location.hash = "#/story/" + s.id;
                       }
                     } }, [
      h("div", { class: "rank-num num" }, String(i + 1)),
      h("div", { class: "rank-body" }, [
        h("div", { class: "rank-head", title: C.cleanHeadline(s.headline) }, C.cleanHeadline(s.headline)),
        s.why ? h("p", { class: "rank-why" }, s.why) : null,
        h("div", { class: "rank-meta" }, [
          s.score != null ? h("span", { class: "score-pill mono" }, String(s.score) + "/100") : null,
          s.impact ? UI.severityBadge(s.impact) : null,
          s.category_name ? UI.tag(s.category_name) : null,
          s.direction ? h("span", { class: "dir " + d.cls },
            [h("span", { "aria-hidden": "true" }, d.sym + " "), s.direction]) : null,
        ].filter(Boolean)),
      ]),
    ]);
  }

  function alertRailItem(a) {
    return h("li", { class: "ar-item" }, [
      h("a", { class: "ar-link", href: "#/story/" + a.id }, [
        h("div", { class: "ar-top" }, [
          UI.severityBadge(a.impact, true),
          h("span", { class: "ar-time mono" }, API.relTime(a.event_time || a.first_seen)),
        ]),
        h("div", { class: "ar-head" }, C.cleanHeadline(a.headline)),
        h("div", { class: "ar-meta" }, [
          a.region_name ? h("span", null, a.region_name) : null,
          a.category_name ? h("span", null, a.category_name) : null,
          a.confidence ? h("span", null, a.confidence) : null,
        ].filter(Boolean)),
      ]),
    ]);
  }

  function movers(title, regions, severity) {
    if (!regions || !regions.length) return null;
    return h("div", { class: "em-block" }, [
      h("div", { class: "em-title" }, [
        UI.severityBadge(severity, true), title,
        h("span", { class: "em-count num" }, String(regions.length)),
      ]),
      h("div", { class: "em-tags" }, regions.map((r) => UI.tag(r, "#/regional"))),
    ]);
  }

  /** Stories first seen per day, last 14 days. Real counts, no interpolation. */
  function volumeTrend(stories) {
    const byDay = {};
    const today = new Date();
    const days = [];
    for (let i = 13; i >= 0; i--) {
      const d = new Date(today.getTime() - i * 86400000).toISOString().slice(0, 10);
      days.push(d); byDay[d] = 0;
    }
    (stories || []).forEach((s) => {
      const d = (s.first_seen || "").slice(0, 10);
      if (d in byDay) byDay[d]++;
    });
    const points = days.map((d) => ({ label: d, value: byDay[d] }));
    const total = points.reduce((n, x) => n + x.value, 0);
    if (!total) {
      return UI.emptyState("No developments were first seen in the last 14 days.");
    }
    // Week over week, from the same real counts.
    const last7 = points.slice(7).reduce((n, x) => n + x.value, 0);
    const prev7 = points.slice(0, 7).reduce((n, x) => n + x.value, 0);
    const delta = prev7 ? Math.round(((last7 - prev7) / prev7) * 100) : null;
    return h("div", { class: "vt" }, [
      h("div", { class: "vt-top" }, [
        h("span", { class: "vt-num num" }, String(last7)),
        h("span", { class: "vt-lab" }, "in the last 7 days"),
        delta === null ? null
          : h("span", { class: "vt-delta " + (delta > 0 ? "d-up" : delta < 0 ? "d-down" : "d-flat") },
              (delta > 0 ? "+" : "") + delta + "% vs prior 7"),
      ]),
      CH.trendChart(points, { label: "Developments first seen per day" }),
      h("div", { class: "vt-axis" }, [
        h("span", null, points[0].label.slice(5)),
        h("span", null, points[points.length - 1].label.slice(5)),
      ]),
    ]);
  }

  function regionSeverity(stories) {
    const by = {};
    (stories || []).forEach((s) => {
      const r = s.region_name || "Unattributed";
      by[r] = by[r] || { label: r, counts: { Critical: 0, High: 0, Moderate: 0, Low: 0 }, href: "#/regional" };
      if (s.impact in by[r].counts) by[r].counts[s.impact]++;
    });
    const groups = Object.keys(by).map((k) => by[k]).sort((a, b) =>
      (b.counts.Critical * 3 + b.counts.High) - (a.counts.Critical * 3 + a.counts.High));
    return CH.severityBars(groups.slice(0, 8), { label: "Impact by region" });
  }

  function categoryDonut(stories) {
    const by = {};
    (stories || []).forEach((s) => {
      const c = s.category_name || "Unclassified";
      by[c] = (by[c] || 0) + 1;
    });
    return CH.donutChart(
      Object.keys(by).map((k) => ({ label: k, value: by[k] })),
      { label: "Developments by category", centreLabel: "stories" });
  }

  function latestFeed(stories) {
    const rows = (stories || []).slice(0, 12);
    return UI.dataTable({
      dense: true,
      empty: "No developments have been ingested yet.",
      onRow: function (r) { location.hash = "#/story/" + r.id; },
      columns: [
        { key: "impact", label: "Sev", width: "58px", sort: false,
          sortValue: (r) => UI.sevMeta(r.impact).rank,
          render: (r) => UI.severityBadge(r.impact, true) },
        { key: "headline", label: "Development",
          render: (r) => h("span", { class: "lf-head" }, C.cleanHeadline(r.headline)) },
        { key: "location_text", label: "Location", width: "13%",
          render: (r) => r.location_text || r.region_name || "\u2014" },
        { key: "category_name", label: "Category", width: "15%",
          render: (r) => UI.tag(r.category_name) },
        { key: "confidence", label: "Confidence", width: "11%",
          render: (r) => UI.confidenceBadge(r.confidence) },
        { key: "event_time", label: "Detected", width: "11%", align: "right", mono: true,
          render: (r) => API.fmtTime(r.event_time || r.first_seen) },
      ],
      rows: rows,
    });
  }

  Views.brief = function () {
    const node = h("div");
    mount(node, async () => {
      // The advisory feed is a separate endpoint; a brief without the travel
      // picture is incomplete, but a travel outage must not cost the brief.
      const [brief, advisory] = await Promise.all([
        API.brief(),
        API.advisoryChanges(14).catch(() => null),
      ]);
      const wrap = h("div", { class: "brief-page" });
      wrap.appendChild(head("Daily Global Security Brief",
        "Generated " + API.fmtTime(brief.generated_at) + " \u00b7 times shown in " + API.state.tz,
        [h("button", { class: "btn secondary small",
            onclick: function () { window.print(); } }, "Print / PDF")],
        "Executive briefing"));

      // Sections collect into their own node so the index can be built from
      // them, then the two are laid out side by side at the end.
      const sections = h("div", { class: "brief-body" });

      // 1 snapshot
      sections.appendChild(sectionPanel("1 · Executive Snapshot (60-second read)",
        h("ul", { class: "clean" }, brief.executive_snapshot.map((s) =>
          h("li", null, [
            h("a", { href: "#/story/" + s.id }, h("strong", null, C.cleanHeadline(s.headline))),
            " — " + s.why + " ", h("em", null, "(" + s.direction + ")"),
          ])))));

      // 2 pulse
      const p = brief.global_risk_pulse;
      sections.appendChild(sectionPanel("2 · Global Risk Pulse", h("div", null, [
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
      sections.appendChild(sectionPanel("3 · Critical Alerts",
        brief.critical_alerts.length
          ? h("div", null, [
              h("ul", { class: "bs-list" }, brief.critical_alerts.slice(0, 8).map((a) =>
                h("li", null, [
                  UI.severityBadge(a.impact, true),
                  h("a", { href: "#/story/" + a.id }, C.cleanHeadline(a.headline)),
                  h("span", { class: "bs-where" },
                    (a.location_text || a.region_name || "\u2014") + " \u00b7 " + a.urgency),
                ]))),
              h("a", { class: "bs-more", href: "#/alerts" },
                "All " + brief.critical_alerts.length + " alerts with impact and actions \u2192"),
            ])
          : h("p", { class: "bs-none" }, "No developments currently meet the critical-alert threshold.")));

      // 4 regional
      sections.appendChild(sectionPanel("4 · Regional Security Watch",
        h("div", { class: "grid grid-2" }, brief.regional_watch.map((r) =>
          h("div", { class: "panel" }, [
            h("h3", null, r.region_name),
            r.no_material_change ? h("p", { class: "sd-reason" }, "No material change identified.")
              : h("ul", { class: "clean" }, r.stories.slice(0, 3).map((s) =>
                  h("li", null, h("a", { href: "#/story/" + s.id }, C.cleanHeadline(s.headline))))),
          ])))));

      // 5 regulations
      // Travel risk: government advisory movement over the last 14 days. Only
      // rendered when the feed answered and actually moved.
      if (advisory && (advisory.changes || []).length) {
        sections.appendChild(sectionPanel("4b \u00b7 Travel Risk Movement",
          h("div", null, [
            h("p", { class: "bs-note" },
              "Official advisory changes detected in the last " + advisory.days + " days."),
            h("ul", { class: "bs-list" }, advisory.changes.slice(0, 8).map((ch) =>
              h("li", null, [
                h("span", { class: "badge " + (ch.kind === "escalated" ? "sev-high" : ch.kind === "eased" ? "sev-low" : "sev-info") },
                  ch.kind),
                h("a", { href: "#/travel?country=" + (ch.country || "") },
                  ch.country_name || ch.country),
                h("span", { class: "bs-where" }, ch.label || ("Level " + ch.level)),
              ]))),
            h("a", { class: "bs-more", href: "#/travel" }, "Open Travel Risk \u2192"),
          ])));
      }

      sections.appendChild(sectionPanel("5 · Laws & Regulations Watch",
        h("div", { class: "grid grid-2" }, brief.regulations.map(regMini))));

      // 6 supply
      sections.appendChild(sectionPanel("6 · Supply-Chain Security Watch", storyMiniList(brief.supply_chain_watch)));
      // 7 cyber
      sections.appendChild(sectionPanel("7 · Cyber-Physical Watch", storyMiniList(brief.cyber_physical_watch)));

      // 8 outlook
      const o = brief.outlook;
      // The note belongs inside the section, not inserted after the fact
      // against the page root — that lookup broke as soon as sections moved
      // into their own container.
      sections.appendChild(sectionPanel("8 · 30/60/90-Day Outlook", h("div", null, [
        h("div", { class: "grid grid-3" }, [
          outlookCol("Confirmed", o.confirmed),
          outlookCol("Reasonably foreseeable", o.foreseeable),
          outlookCol("Speculative", o.speculative),
        ]),
        o.note ? h("p", { class: "bs-note" }, o.note) : null,
      ].filter(Boolean))));

      // 9 lesson
      const l = brief.todays_lesson;
      sections.appendChild(sectionPanel("9 · Today's Security Lesson", h("div", null, [
        h("h3", null, l.concept),
        h("p", null, l.plain_language),
        l.connected_story ? h("p", null, ["Connected development: ", h("a", { href: "#/story/" + l.connected_story.id }, C.cleanHeadline(l.connected_story.headline))]) : null,
        h("p", { class: "sd-reason" }, l.why_it_helps),
      ])));

      // 10 & 11 links
      sections.appendChild(sectionPanel("10 & 11 · Scenario & Knowledge Check",
        h("div", { class: "btn-row" }, [
          h("a", { class: "btn", href: "#/learn" }, "Open scenario exercise"),
          h("a", { class: "btn secondary", href: "#/learn" }, "Take today's quiz"),
        ])));

      // 12 talking points
      sections.appendChild(sectionPanel("12 · Executive Talking Points",
        h("ul", { class: "bs-points" }, brief.executive_talking_points.map((t) => h("li", null, t)))));

      // Restore the real appendChild and assemble: index rail beside the body.
      const index = h("nav", { class: "brief-index", "aria-label": "Brief sections" }, [
        h("div", { class: "bi-lab" }, "Contents"),
        h("ol", null, Array.from(sections.querySelectorAll(".brief-sec")).map(function (sec) {
          const t = sec.querySelector(".bs-head");
          const num = t.querySelector(".bs-num");
          return h("li", null, h("a", { href: "#" + sec.id, onclick: function (e) {
            // Plain anchors would rewrite the SPA hash and re-route the view.
            e.preventDefault();
            sec.scrollIntoView({ behavior: "smooth", block: "start" });
          } }, [
            num ? h("span", { class: "bi-num mono" }, num.textContent) : null,
            t.lastChild.textContent,
          ].filter(Boolean)));
        })),
      ]);
      wrap.appendChild(h("div", { class: "brief-layout" }, [sections, index]));
      return wrap;
    }, "line");
    return node;
  };

  /** Brief section. `n` is the printed number; `slugId` anchors the index. */
  function sectionPanel(title, body) {
    const id = "brief-" + slug(title).slice(0, 24);
    const m = /^(\d+(?:\s*&\s*\d+)?)\s*\u00b7\s*(.*)$/.exec(title);
    return h("section", { class: "brief-sec", id: id }, [
      h("h2", { class: "bs-head" }, [
        m ? h("span", { class: "bs-num mono" }, m[1]) : null,
        h("span", null, m ? m[2] : title),
      ].filter(Boolean)),
      h("div", { class: "bs-body" }, body),
    ]);
  }

  function storyMiniList(list) {
    if (!list || !list.length) {
      return h("p", { class: "bs-none" }, "No qualifying developments.");
    }
    return h("ul", { class: "bs-list" }, list.map((st) =>
      h("li", null, [
        UI.severityBadge(st.impact, true),
        h("a", { href: "#/story/" + st.id }, C.cleanHeadline(st.headline)),
        st.location_text || st.region_name
          ? h("span", { class: "bs-where" }, st.location_text || st.region_name) : null,
      ].filter(Boolean))));
  }
  function outlookCol(title, items) {
    return h("div", { class: "panel" }, [
      h("h3", null, title),
      items && items.length ? h("ul", { class: "clean" }, items.map((i) => h("li", null, [i.title.replace("[DEMO] ", ""), h("br"), h("span", { class: "sd-reason" }, (i.framework || "") + " · " + i.when)])))
        : h("p", { class: "sd-reason" }, "None recorded."),
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

      const all = data.alerts || [];
      const wrap = h("div");
      wrap.appendChild(head("Critical Alerts",
        "Developments meeting the prompt-action threshold: high or critical impact, near-term urgency, corroborated evidence, and a recent event.",
        null, "Requires action"));

      if (!all.length) {
        wrap.appendChild(UI.emptyState(
          "No developments currently meet the alert threshold. That is a deliberate outcome, not a gap \u2014 the gate is tuned against alert fatigue.",
          h("a", { class: "btn secondary", href: "#/stories?alerts_only=1" }, "Review recent high-impact stories")));
        return wrap;
      }

      // Counts by severity, from the alerts themselves.
      const bySev = { Critical: 0, High: 0, Moderate: 0, Low: 0 };
      all.forEach((a) => { if (a.impact in bySev) bySev[a.impact]++; });
      const immediate = all.filter((a) => a.urgency === "Immediate").length;
      wrap.appendChild(h("div", { class: "metric-row alerts-metrics" }, [
        UI.metricCard({ label: "Active alerts", value: all.length, severity: "Critical" }),
        UI.metricCard({ label: "Immediate urgency", value: immediate,
          severity: immediate ? "Critical" : null, hint: "act within hours" }),
        UI.metricCard({ label: "Critical impact", value: bySev.Critical,
          severity: bySev.Critical ? "Critical" : null }),
        UI.metricCard({ label: "High impact", value: bySev.High,
          severity: bySev.High ? "High" : null }),
      ]));

      // Filters operate on the alert set already in hand — alerting is a small,
      // bounded list, so there is nothing to gain from a round trip.
      const listHost = h("div", { class: "alert-cards" });
      let state = { impact: "", urgency: "", category: "", q: "" };

      function apply() {
        const rows = all.filter((a) =>
          (!state.impact || a.impact === state.impact) &&
          (!state.urgency || a.urgency === state.urgency) &&
          (!state.category || a.category === state.category) &&
          (!state.q || (a.headline || "").toLowerCase().indexOf(state.q.toLowerCase()) >= 0));
        listHost.innerHTML = "";
        if (!rows.length) {
          listHost.appendChild(UI.emptyState("No active alerts match these filters."));
          return;
        }
        rows.sort((a, b) => UI.sevMeta(b.impact).rank - UI.sevMeta(a.impact).rank);
        rows.forEach((a) => listHost.appendChild(alertCard(a)));
      }

      const cats = Array.from(new Set(all.map((a) => a.category)))
        .map((c) => ({ value: c, label: (all.find((a) => a.category === c) || {}).category_name || c }));
      wrap.appendChild(UI.filterBar([
        { type: "search", key: "q", label: "Filter alerts\u2026" },
        { type: "select", key: "impact", label: "Impact",
          options: [{ value: "", label: "Any impact" }, { value: "Critical", label: "Critical" }, { value: "High", label: "High" }] },
        { type: "select", key: "urgency", label: "Urgency",
          options: [{ value: "", label: "Any urgency" }, { value: "Immediate", label: "Immediate" }, { value: "24 Hours", label: "24 Hours" }] },
        { type: "select", key: "category", label: "Category",
          options: [{ value: "", label: "All categories" }].concat(cats) },
      ], function (v) { state = v; apply(); }));

      wrap.appendChild(listHost);
      apply();
      return wrap;
    }, "metrics");
    return node;
  };

  /**
   * Alert card. Carries the operational fields the alert record adds over a
   * story: who is affected, what to do, and when it was detected. Each block is
   * omitted when the record does not contain it.
   */
  function alertCard(a) {
    const al = a.alert || {};
    const impacts = [
      ["People", al.people_impact],
      ["Facilities", al.facility_impact],
      ["Operations", al.operational_impact],
    ].filter((x) => x[1]);

    return h("article", { class: "alert-card sev-edge-" + slug(a.impact || "") }, [
      h("div", { class: "ac-top" }, [
        UI.severityBadge(a.impact),
        a.urgency ? h("span", { class: "badge " + urgencyCls(a.urgency) }, a.urgency) : null,
        UI.confidenceBadge(a.confidence),
        a.category_name ? UI.tag(a.category_name) : null,
        h("span", { class: "ac-detected mono" },
          "detected " + API.relTime(al.created_at || a.first_seen)),
      ].filter(Boolean)),
      h("h3", { class: "ac-head" },
        h("a", { href: "#/story/" + a.id }, C.cleanHeadline(a.headline))),
      h("div", { class: "ac-where" }, [
        a.location_text || a.region_name || "Location not attributed",
        a.geo_scope ? h("span", { class: "ac-scope" }, a.geo_scope + " scope") : null,
      ].filter(Boolean)),
      impacts.length
        ? h("dl", { class: "ac-impacts" }, impacts.map(([k, v]) =>
            [h("dt", null, k), h("dd", null, v)])) : null,
      al.recommended_action
        ? h("div", { class: "ac-action" }, [
            h("div", { class: "ac-action-lab" }, "Recommended action"),
            h("p", null, al.recommended_action),
          ]) : null,
      h("div", { class: "ac-foot" }, [
        h("a", { class: "btn small", href: "#/story/" + a.id }, "Open intelligence record"),
        a.primary_country
          ? h("a", { class: "btn small secondary", href: "#/travel?country=" + a.primary_country }, "Travel risk")
          : null,
      ].filter(Boolean)),
    ].filter(Boolean));
  }
  function urgencyCls(v) {
    return v === "Immediate" ? "sev-critical" : v === "24 Hours" ? "sev-high"
         : v === "7 Days" ? "sev-moderate" : "sev-low";
  }

  // ============================ STORIES (list + filters) ============================
  Views.stories = function (params) {
    const node = h("div");
    const meta = API.state.meta;
    const filters = Object.assign({ sort: "score" }, params || {});
    // View mode is a workspace preference, not a route: an analyst who works in
    // the table should not be dropped back into cards on every navigation.
    let mode = API.LS.get("storyView", "cards");
    let savedOnly = false;

    const listWrap = h("div", { class: "story-list" });
    const countEl = h("span", { class: "fb-count" }, "");

    // Request handling below is unchanged: aborting the in-flight request and
    // guarding on a sequence number is what stops a fast second filter change
    // racing a stale response back over the newer one.
    let inflight = null;
    let requestSeq = 0;
    let lastRows = [];

    function draw(stories) {
      listWrap.innerHTML = "";
      let rows = stories;
      if (savedOnly) {
        const ids = new Set(API.savedLocal.all().map((x) => x.story_id));
        rows = rows.filter((r) => ids.has(r.id));
      }
      countEl.textContent = rows.length
        ? rows.length + (rows.length === 1 ? " development" : " developments")
        : "";
      if (!rows.length) {
        listWrap.appendChild(UI.emptyState(
          savedOnly ? "None of your saved intelligence matches these filters."
                    : "No developments match these filters. Try widening the region or lowering the impact threshold."));
        return;
      }
      if (mode === "table") {
        listWrap.className = "story-list is-table";
        listWrap.appendChild(storyTable(rows));
      } else {
        listWrap.className = "story-list is-cards";
        rows.forEach((st) => listWrap.appendChild(UI.intelligenceCard(st, {
          relTime: API.relTime,
          onOpen: function (x) { location.hash = "#/story/" + x.id; },
          footer: st.similar && st.similar.length
            ? h("div", { class: "ic-similar" },
                "+" + st.similar.length + " related report" + (st.similar.length > 1 ? "s" : ""))
            : null,
        })));
      }
    }

    async function refresh() {
      const seq = ++requestSeq;
      if (inflight) inflight.abort();
      const controller = new AbortController();
      inflight = controller;

      const qs = new URLSearchParams();
      Object.keys(filters).forEach((k) => {
        if (k === "since_days") return;          // translated below
        if (filters[k]) qs.set(k, filters[k]);
      });
      if (filters.since_days) {
        qs.set("since", new Date(Date.now() - Number(filters.since_days) * 86400000).toISOString());
      }
      qs.set("group", "1");  // collapse near-duplicate coverage into lead + similar

      if (!listWrap.childElementCount) listWrap.appendChild(UI.loadingState("table", 6));
      listWrap.classList.add("is-busy");
      listWrap.setAttribute("aria-busy", "true");

      let data;
      try {
        data = await API.stories(qs.toString(), { signal: controller.signal });
      } catch (err) {
        if (err.name === "AbortError") return;   // superseded by a newer filter
        if (seq !== requestSeq) return;
        listWrap.classList.remove("is-busy");
        listWrap.removeAttribute("aria-busy");
        listWrap.innerHTML = "";
        listWrap.appendChild(UI.errorState("Could not load stories: " + err.message, refresh));
        return;
      }
      if (seq !== requestSeq) return;            // a newer response already won

      listWrap.classList.remove("is-busy");
      listWrap.removeAttribute("aria-busy");
      lastRows = data.stories || [];
      draw(lastRows);
    }

    function storyTable(rows) {
      return UI.dataTable({
        dense: true,
        onRow: function (r) { location.hash = "#/story/" + r.id; },
        empty: "No developments match these filters.",
        columns: [
          { key: "impact", label: "Sev", width: "56px",
            sortValue: (r) => UI.sevMeta(r.impact).rank,
            render: (r) => UI.severityBadge(r.impact, true) },
          { key: "headline", label: "Development",
            render: (r) => h("div", { class: "st-head" }, [
              h("span", null, C.cleanHeadline(r.headline)),
              r.is_alert ? h("span", { class: "ic-alert-flag" }, "ALERT") : null,
            ].filter(Boolean)) },
          { key: "location_text", label: "Location", width: "12%",
            sortValue: (r) => r.location_text || r.region_name || "",
            render: (r) => r.location_text || r.region_name || "\u2014" },
          { key: "category_name", label: "Category", width: "14%",
            render: (r) => UI.tag(r.category_name) },
          { key: "urgency", label: "Urgency", width: "9%" },
          { key: "confidence", label: "Confidence", width: "10%",
            render: (r) => UI.confidenceBadge(r.confidence) },
          { key: "relevance_score", label: "Score", width: "62px", align: "right", mono: true },
          { key: "event_time", label: "Detected", width: "10%", align: "right", mono: true,
            sortValue: (r) => r.event_time || r.first_seen || "",
            render: (r) => API.relTime(r.event_time || r.first_seen) },
        ],
        rows: rows,
      });
    }

    // ---- filter bar ----
    function opts(list, allLabel) {
      return [{ value: "", label: allLabel }].concat(list);
    }
    const fields = [
      { type: "select", key: "category", label: "Category",
        value: filters.category || "",
        options: opts(meta.categories.map((c) => ({ value: c.id, label: c.name })), "All categories") },
      { type: "select", key: "region", label: "Region",
        value: filters.region || "",
        options: opts(meta.regions.filter((r) => r.id !== "global").map((r) => ({ value: r.id, label: r.name })), "All regions") },
      { type: "select", key: "country", label: "Country",
        value: filters.country || "",
        options: opts((meta.countries || []).map((c) => ({ value: c.code, label: c.name })), "All countries") },
      { type: "select", key: "impact", label: "Impact",
        value: filters.impact || "",
        options: opts(meta.scales.impact.slice().reverse().map((v) => ({ value: v, label: v })), "Any impact") },
      { type: "select", key: "confidence", label: "Confidence",
        value: filters.confidence || "",
        options: opts(meta.scales.confidence.slice().reverse().map((v) => ({ value: v, label: v })), "Any confidence") },
      { type: "select", key: "urgency", label: "Urgency",
        value: filters.urgency || "",
        options: opts(meta.scales.urgency.map((v) => ({ value: v, label: v })), "Any urgency") },
      // The API compares `since` as `last_updated >= ?` against an ISO
      // timestamp, so the control sends a date. Sending a day count instead
      // compares against the literal string and filters wrongly but silently.
      { type: "select", key: "since_days", label: "Date range",
        value: filters.since_days || "",
        options: [{ value: "", label: "Any date" }, { value: "1", label: "Last 24 hours" },
                  { value: "7", label: "Last 7 days" }, { value: "30", label: "Last 30 days" },
                  { value: "90", label: "Last 90 days" }] },
      { type: "select", key: "sort", label: "Sort",
        value: filters.sort || "score",
        options: [{ value: "score", label: "Sort: relevance" }, { value: "recent", label: "Sort: most recent" },
                  { value: "urgency", label: "Sort: urgency" }, { value: "watchlist", label: "Sort: watchlist exposure" }] },
      { type: "toggle", key: "alerts_only", label: "Alerts only", value: filters.alerts_only === "1" },
      { type: "toggle", key: "verified_only", label: "Verified only", value: filters.verified_only === "1" },
      { type: "toggle", key: "new_today", label: "New today", value: filters.new_today === "1" },
      { type: "toggle", key: "saved_only", label: "Saved", value: false },
    ];

    const viewToggle = h("div", { class: "view-toggle", role: "group", "aria-label": "Result view" },
      [["cards", "Cards"], ["table", "Table"]].map(([m, label]) =>
        h("button", {
          type: "button", class: "vt-btn" + (mode === m ? " is-on" : ""),
          "aria-pressed": String(mode === m),
          onclick: function (e) {
            mode = m; API.LS.set("storyView", m);
            e.currentTarget.parentElement.querySelectorAll(".vt-btn").forEach(function (b) {
              const on = b === e.currentTarget;
              b.classList.toggle("is-on", on);
              b.setAttribute("aria-pressed", String(on));
            });
            draw(lastRows);
          },
        }, label)));

    const bar = UI.filterBar(fields, function (v) {
      Object.keys(v).forEach(function (k) {
        if (k === "saved_only") { savedOnly = !!v[k]; return; }
        filters[k] = typeof v[k] === "boolean" ? (v[k] ? "1" : "") : v[k];
      });
      refresh();
    }, [countEl, viewToggle]);

    const wrap = h("div");
    wrap.appendChild(head("Stories",
      "Every ingested development, filterable across region, category, impact, confidence and date.",
      [h("a", { class: "btn secondary small", href: "/api/export/stories.csv" }, "Export CSV"),
       h("a", { class: "btn secondary small", href: "/api/export/stories.json" }, "Export JSON")],
      "Intelligence feed"));
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
        (() => { const rc = C.ratingChips(s); rc.classList.add("inferred"); return rc; })(),
        h("div", { class: "sd-reason" }, "Event: " + API.fmtTime(s.event_time) + " · First seen: " + API.fmtTime(s.first_seen) + " · Last verified: " + API.fmtTime(s.last_updated) + " · Status: " + (s.status || "—")),
      ]));

      // "Confirmed facts only" hides every generated section (.inferred) and
      // filters claims to sourced facts, so what remains is evidence.
      const factsBanner = h("div", { class: "facts-banner", hidden: true },
        "Confirmed facts only: interpretation, ratings and recommendations are "
        + "hidden. Showing sourced claims and citations.");
      const factsBtn = toolBtn("✓ Show only confirmed facts", (e) => {
        confirmedOnly = !confirmedOnly;
        wrap.classList.toggle("facts-only", confirmedOnly);
        const btn = e.currentTarget;
        btn.setAttribute("aria-pressed", String(confirmedOnly));
        btn.classList.toggle("active", confirmedOnly);
        factsBanner.hidden = !confirmedOnly;
        renderClaims();
      }, true);
      factsBtn.setAttribute("aria-pressed", "false");

      // toolbar
      wrap.appendChild(h("div", { class: "btn-row", style: "margin-bottom:1rem" }, [
        toolBtn(API.savedLocal.has(id) ? "★ Saved" : "☆ Save", (e) => {
          const nowSaved = API.savedLocal.toggle(id);
          e.target.textContent = nowSaved ? "★ Saved" : "☆ Save";
          C.toast(nowSaved ? "Saved to this browser." : "Removed.");
        }),
        toolBtn("⚔ Challenge this analysis", () => openChallenge(id)),
        factsBtn,
        exportMenu(s),
      ]));
      wrap.appendChild(factsBanner);

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
      if (a.background) left.appendChild(inferredSection("Background", h("p", null, a.background)));

      // Narrative comparison
      if ((s.narratives || []).length) {
        left.appendChild(inferredSection("Narrative comparison",
          h("div", { class: "grid grid-2" }, s.narratives.map((n) => h("div", { class: "narrative" }, [
            h("strong", null, n.label), h("p", { class: "sd-reason" }, "Who: " + (n.who || "—")),
            h("p", null, n.claim), h("p", { class: "sd-reason" }, "Evidence: " + n.evidence),
          ])))));
      } else {
        left.appendChild(inferredSection("Narrative comparison",
          h("p", { class: "sd-reason" }, "No materially different narrative captured. Use ‘Challenge this analysis’ to check for missing perspectives.")));
      }

      // Why global / why your work
      if (a.why_global) left.appendChild(inferredSection("Why it matters globally", h("p", null, a.why_global)));
      left.appendChild(inferredSection("Why this matters to your work",
        h("ul", { class: "clean" }, (a.why_your_work || []).map((w) => h("li", null, w)))));

      // Risk pathway
      if ((a.risk_pathway || []).length) {
        left.appendChild(inferredSection("Risk pathway",
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
      left.appendChild(inferredSection("Questions you should ask today",
        h("ul", { class: "clean" }, (a.questions || []).map((q) => h("li", null, q)))));

      // Recommended actions
      left.appendChild(inferredSection("Recommended actions",
        h("div", { class: "grid" }, (a.actions || []).map((ac) =>
          h("div", { class: "claim" }, [h("span", { class: "claim-type" }, ac.type), " ", ac.text])))));

      // Indicators — analytical content, so it belongs in the main column. In
      // the 320px rail this long list wrapped badly and made the rail outgrow
      // the main column, leaving a large void beside it on wide screens.
      left.appendChild(inferredSection("Indicators to monitor",
        h("ul", { class: "clean" }, (s.indicators || []).map((i) =>
          h("li", null, [i.text, " ", C.chip(i.direction, i.direction === "improvement" ? "sev-low" : i.direction === "deterioration" ? "sev-high" : "", "◍")])))));

      // ---- right column (at-a-glance metadata only) ----
      right.appendChild(h("div", { class: "panel inferred" }, [
        h("h2", null, "Relevance score"),
        h("div", { style: "display:flex;align-items:center;gap:.8rem;margin-bottom:.6rem" }, [C.scoreRing(s.relevance_score), h("span", { class: "sd-reason" }, "0–100 documented model. Each dimension is explained below.")]),
        C.scoreBars(s.scoring),
      ]));
      right.appendChild(h("div", { class: "panel inferred", style: "margin-top:1rem" }, [
        h("h2", null, "Rating rationale"), C.ratingRationale(s.scoring),
      ]));

      // Cross-government advisory consensus (Layer 2), advisory stories only
      const advPanel = C.advisoryConsensus(s.advisory);
      if (advPanel) { advPanel.style.marginTop = "1rem"; right.appendChild(advPanel); }

      // Potentially affected
      const pa = a.potentially_affected || {};
      right.appendChild(h("div", { class: "panel inferred", style: "margin-top:1rem" }, [
        h("h2", null, "Potentially affected"),
        affectedBlock("Countries", (pa.countries || s.countries || []).map((x) => (x || "").toUpperCase())),
        affectedBlock("Business functions", pa.business_functions || []),
        affectedBlock("Infrastructure", pa.infrastructure || []),
      ]));

      // regulation panel if present
      if (s.regulation) right.appendChild(regulationPanel(s.regulation));

      wrap.appendChild(h("div", { class: "detail-cols" }, [left, right]));

      // Reference/appendix material runs FULL WIDTH below the two columns.
      // Keeping these out of the narrow rail stops it outgrowing the main
      // column (which left a large void beside it) and gives citation URLs and
      // headlines room to breathe instead of wrapping in a ~440px gutter.
      const appendix = h("div", { class: "detail-appendix" });
      appendix.appendChild(h("div", { class: "panel", style: "margin-top:1rem" }, [
        h("h2", null, "Sources & transparency"),
        h("p", { class: "sd-reason" }, "Every claim links to its exact source. Tier 1 = primary/authoritative → Tier 4 = unverified signal."),
        h("div", { class: "cite-grid" }, (s.citations || []).map(citationEl)),
      ]));
      if (s.similar && s.similar.length) {
        appendix.appendChild(h("div", { class: "panel", style: "margin-top:1rem" }, [
          h("h2", null, "Similar coverage"),
          h("p", { class: "sd-reason" }, "Other tracked reports on a closely related event."),
          h("ul", { class: "clean cite-grid" }, s.similar.map((x) =>
            h("li", null, [
              h("a", { href: "#/story/" + x.id }, C.cleanHeadline(x.headline)),
              x.location_text ? h("span", { class: "sd-reason" }, " · " + x.location_text) : null,
            ]))),
        ]));
      }
      wrap.appendChild(appendix);
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
  // Generated/interpretive sections. "Show only confirmed facts" hides these
  // so the page shows sourced evidence only — previously the toggle filtered
  // the claim list but left every inference on screen, which made the mode
  // actively misleading.
  function inferredSection(title, body) {
    const el = detailSection(title, body);
    el.classList.add("inferred");
    return el;
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
      const risk = data.country_risk || {};
      const codes = Object.keys(risk);
      const nameOf = {};
      (API.state.meta.countries || []).forEach((c) => (nameOf[c.code] = c.name));

      wrap.appendChild(head("World / Region View",
        "Countries shaded by the worst impact recorded in the last 30 days; depth of shade is the volume of serious activity. Drag to turn the globe, click a country to filter its stories, or a marker to open the development.",
        null, "Geographic intelligence"));

      const bySev = { Critical: 0, High: 0, Moderate: 0, Low: 0 };
      codes.forEach((c) => { if (risk[c].impact in bySev) bySev[risk[c].impact]++; });
      wrap.appendChild(h("div", { class: "metric-row" }, [
        UI.metricCard({ label: "Countries with activity", value: codes.length }),
        UI.metricCard({ label: "At critical impact", value: bySev.Critical,
          severity: bySev.Critical ? "Critical" : null }),
        UI.metricCard({ label: "At high impact", value: bySev.High,
          severity: bySev.High ? "High" : null }),
        UI.metricCard({ label: "Plotted events", value: (data.points || []).length,
          hint: "developments carrying coordinates" }),
      ]));

      const mapHost = h("div", { class: "world-map-host" });
      try {
        mapHost.appendChild(window.GSID_MAP.render(data,
          (id) => (location.hash = "#/story/" + id),
          (iso) => (location.hash = "#/stories?country=" + iso)));
      } catch (e) {
        mapHost.appendChild(UI.errorState("The globe could not render: " + e.message));
      }

      // Drill-down rail beside the globe: world -> region -> country -> events.
      const counts = data.region_counts || {};
      const regions = API.state.meta.regions.filter((r) => r.id !== "global");
      const drill = panel("Drill down", null, h("div", { class: "drill" }, [
        h("div", { class: "drill-lab" }, "By region"),
        CH.barChart(regions.map((r) => ({
          label: r.name, value: counts[r.id] || 0, href: "#/stories?region=" + r.id,
        })).sort((a, b) => b.value - a.value),
          { label: "Developments by region", limit: 11,
            empty: "No regional activity recorded." }),
        h("div", { class: "drill-lab" }, "Most active countries"),
        CH.barChart(codes.map((c) => ({
          label: nameOf[c] || c.toUpperCase(),
          value: risk[c].total || risk[c].count || 0,
          severity: risk[c].impact,
          href: "#/stories?country=" + c,
        })).sort((a, b) => b.value - a.value),
          { label: "Developments by country", limit: 10,
            empty: "No country-level activity recorded." }),
      ]));

      wrap.appendChild(h("div", { class: "world-split" }, [
        panel("Global threat picture", panelLink("Regional detail \u2192", "#/regional"), mapHost, "flush"),
        drill,
      ]));
      return wrap;
    }, "metrics");
    return node;
  };

  // ============================ REGIONAL ============================
  Views.regional = function () {
    const node = h("div");
    mount(node, async () => {
      const data = await API.regional();
      const wrap = h("div");
      const regions = data.regions || [];
      wrap.appendChild(head("Regional Intelligence",
        "Per-region picture with the developments behind it. Regions with nothing material say so rather than being padded out.",
        [h("a", { class: "btn secondary small", href: "#/map" }, "World view")],
        "By region"));

      const active = regions.filter((r) => !r.no_material_change);
      wrap.appendChild(h("div", { class: "metric-row" }, [
        UI.metricCard({ label: "Regions covered", value: regions.length }),
        UI.metricCard({ label: "With material change", value: active.length,
          hint: (regions.length - active.length) + " quiet" }),
        UI.metricCard({ label: "Developments listed", value:
          regions.reduce((n, r) => n + (r.stories || []).length, 0) }),
      ]));

      wrap.appendChild(h("div", { class: "region-grid" }, regions.map((r) => {
        const rows = r.stories || [];
        const worst = rows.reduce((w, st) =>
          UI.sevMeta(st.impact).rank > UI.sevMeta(w).rank ? st.impact : w, "Informational");
        return h("section", { class: "panel flush region-card" }, [
          h("div", { class: "panel-head" }, [
            h("h2", null, r.region_name),
            h("div", { class: "rc-right" }, [
              rows.length ? UI.severityBadge(worst, true) : null,
              h("a", { class: "panel-act", href: "#/stories?region=" + r.region }, rows.length + " \u2192"),
            ].filter(Boolean)),
          ]),
          r.no_material_change || !rows.length
            ? h("p", { class: "rc-quiet" }, "No material change identified.")
            : h("ul", { class: "rc-list" }, rows.map((st) =>
                h("li", null, h("a", { href: "#/story/" + st.id }, [
                  UI.severityBadge(st.impact, true),
                  h("span", { class: "rc-head" }, C.cleanHeadline(st.headline)),
                  h("span", { class: "rc-when mono" }, API.relTime(st.event_time || st.first_seen)),
                ])))),
        ]);
      })));
      return wrap;
    }, "metrics");
    return node;
  };

  // ============================ REGULATORY ============================
  Views.regulatory = function () {
    const node = h("div");
    mount(node, async () => {
      const data = await API.regulations();
      const all = data.regulations || [];
      const wrap = h("div");
      wrap.appendChild(head("Regulatory Tracker",
        "Obligations that touch physical and converged security. Lifecycle status is explicit \u2014 a proposal is never presented as enacted law.",
        null, "Compliance horizon"));

      if (!all.length) {
        wrap.appendChild(UI.emptyState("No regulations are being tracked yet."));
        return wrap;
      }

      const byStatus = {};
      all.forEach((r) => (byStatus[r.status] = (byStatus[r.status] || 0) + 1));
      // Tiles are built from the status values actually present, not from a
      // guessed vocabulary. Hardcoding enforced/adopted/proposed showed two
      // zeroes while `enacted` and `effective` went uncounted — a tile reading
      // 0 for a status that simply is not used is worse than no tile.
      const statusOrder = Object.keys(byStatus).sort((a, b) => byStatus[b] - byStatus[a]);
      wrap.appendChild(h("div", { class: "metric-row" }, [
        UI.metricCard({ label: "Tracked instruments", value: all.length,
          hint: statusOrder.length + " lifecycle states in use" }),
      ].concat(statusOrder.slice(0, 4).map((k) => UI.metricCard({
        label: k, value: byStatus[k],
        hint: k === "proposed" ? "not law \u2014 monitor only" : null,
      })))));

      // Detail lives in an expandable row: the table is for scanning the estate,
      // and eight prose fields per instrument would make it unscannable.
      const listHost = h("div");
      let state = { q: "", status: "", jurisdiction: "" };
      function apply() {
        const rows = all.filter((r) =>
          (!state.status || r.status === state.status) &&
          (!state.jurisdiction || r.jurisdiction === state.jurisdiction) &&
          (!state.q || (r.title + " " + (r.framework || "")).toLowerCase()
            .indexOf(state.q.toLowerCase()) >= 0));
        listHost.innerHTML = "";
        listHost.appendChild(UI.dataTable({
          empty: "No tracked regulation matches these filters.",
          sort: { key: "effective_date", dir: "desc" },
          columns: [
            { key: "title", label: "Instrument",
              render: (r) => h("div", { class: "reg-title" }, [
                h("span", null, (r.title || "").replace("[DEMO] ", "")),
                r.framework ? h("span", { class: "reg-fw mono" }, r.framework) : null,
              ].filter(Boolean)) },
            { key: "jurisdiction", label: "Jurisdiction", width: "14%" },
            { key: "status", label: "Status", width: "11%",
              render: (r) => h("span", { class: "status-pill st-" + r.status }, r.status) },
            { key: "effective_date", label: "Effective", width: "10%", mono: true,
              render: (r) => r.effective_date || "\u2014" },
            { key: "_detail", label: "", width: "84px", align: "right", sort: false,
              render: (r) => h("button", {
                class: "btn small secondary",
                onclick: function (e) {
                  e.stopPropagation();
                  openRegulation(r);
                },
              }, "Detail") },
          ],
          rows: rows,
        }));
      }

      const juris = Array.from(new Set(all.map((r) => r.jurisdiction))).filter(Boolean)
        .map((j) => ({ value: j, label: j }));
      wrap.appendChild(UI.filterBar([
        { type: "search", key: "q", label: "Search instruments\u2026" },
        { type: "select", key: "status", label: "Status",
          options: [{ value: "", label: "Any status" }].concat(
            Object.keys(byStatus).map((k) => ({ value: k, label: k }))) },
        { type: "select", key: "jurisdiction", label: "Jurisdiction",
          options: [{ value: "", label: "All jurisdictions" }].concat(juris) },
      ], function (v) { state = v; apply(); }));

      wrap.appendChild(h("section", { class: "panel flush" }, listHost));
      apply();
      return wrap;
    }, "metrics");
    return node;
  };

  /** Full regulation record in the shared modal. */
  function openRegulation(r) {
    const body = h("div", null, [
      h("div", { class: "ic-meta" }, [
        h("span", { class: "status-pill st-" + r.status }, r.status),
        UI.tag(r.jurisdiction),
        r.framework ? UI.tag(r.framework) : null,
        r.effective_date ? h("span", { class: "ic-when mono" }, "Effective " + r.effective_date) : null,
      ].filter(Boolean)),
      h("dl", { class: "reg-grid" }, [
        rg("Affected", r.affected), rg("Obligations", r.obligations),
        rg("Reporting timelines", r.reporting), rg("Penalties / enforcement", r.penalties),
        rg("Practical implications", r.implications),
        rg("Recommended preparation", r.prep_steps),
      ]),
      h("div", { class: "btn-row" }, [
        r.source_url ? h("a", { class: "btn small secondary", href: r.source_url,
          target: "_blank", rel: "noopener noreferrer" }, "Original source") : null,
        r.story_id ? h("a", { class: "btn small secondary", href: "#/story/" + r.story_id }, "Related story") : null,
      ].filter(Boolean)),
    ]);
    const host = document.getElementById("modalHost");
    document.getElementById("modalTitle").textContent = (r.title || "").replace("[DEMO] ", "");
    const mb = document.getElementById("modalBody");
    mb.innerHTML = ""; mb.appendChild(body);
    host.hidden = false;
  }

  // ============================ SUPPLY / CYBER (category views) ============================
  Views.supply = categoryView(
    "Supply-Chain Watch", "supply_chain",
    "Disruption to ports, shipping lanes, borders, customs, freight and cargo security \u2014 the developments that move delivery dates and route risk.",
    "Logistics exposure",
    ["Ports & terminals", "Shipping lanes", "Air freight", "Rail & trucking",
     "Customs & borders", "Cargo crime", "Manufacturing", "Energy supply"]);
  Views.cyber = categoryView(
    "Cyber-Physical Intelligence", "cyber_physical",
    "Incidents where digital compromise has physical consequence: industrial control systems, utilities, data centres, building systems and connected infrastructure.",
    "Converged risk",
    ["Critical infrastructure", "Industrial control / OT", "Data centres",
     "Utilities & grid", "Transportation systems", "Telecommunications",
     "Physical security systems"]);

  /**
   * Shared builder for the single-category watch pages (Supply-Chain,
   * Cyber-Physical). They ask the same question of the same endpoint, so they
   * share one implementation: metrics, a location/severity table, a severity
   * breakdown, and the ranked feed.
   * `sectors` names the exposure this category maps to, which is the framing
   * those teams actually work in.
   */
  function categoryView(title, cat, sub, eyebrow, sectors) {
    return function () {
      const node = h("div");
      mount(node, async () => {
        const data = await API.stories("category=" + cat + "&limit=100");
        const rows = data.stories || [];
        const wrap = h("div");
        wrap.appendChild(head(title, sub, [
          h("a", { class: "btn secondary small", href: "#/stories?category=" + cat }, "Open in Stories"),
        ], eyebrow));

        if (!rows.length) {
          wrap.appendChild(UI.emptyState(
            "No developments have been classified into this category yet."));
          return wrap;
        }

        const bySev = { Critical: 0, High: 0, Moderate: 0, Low: 0 };
        rows.forEach((r) => { if (r.impact in bySev) bySev[r.impact]++; });
        const located = rows.filter((r) => r.lat != null && r.lon != null).length;
        const alerts = rows.filter((r) => r.is_alert).length;
        wrap.appendChild(h("div", { class: "metric-row" }, [
          UI.metricCard({ label: "Tracked developments", value: rows.length }),
          UI.metricCard({ label: "Critical impact", value: bySev.Critical,
            severity: bySev.Critical ? "Critical" : null }),
          UI.metricCard({ label: "Active alerts", value: alerts,
            severity: alerts ? "Critical" : null, href: "#/alerts" }),
          UI.metricCard({ label: "Geolocated", value: located,
            hint: "plotted on the world view", href: "#/map" }),
        ]));

        wrap.appendChild(h("div", { class: "cat-split" }, [
          panel("Severity by region", null, (function () {
            const by = {};
            rows.forEach((r) => {
              const k = r.region_name || "Unattributed";
              by[k] = by[k] || { label: k, counts: { Critical: 0, High: 0, Moderate: 0, Low: 0 } };
              if (r.impact in by[k].counts) by[k].counts[r.impact]++;
            });
            return CH.severityBars(Object.keys(by).map((k) => by[k]), { label: title + " by region" });
          })()),
          panel("Where it is happening", null, (function () {
            const by = {};
            rows.forEach((r) => {
              const k = r.location_text || r.region_name;
              if (!k) return;
              by[k] = by[k] || { label: k, value: 0, severity: null };
              by[k].value++;
              if (UI.sevMeta(r.impact).rank > UI.sevMeta(by[k].severity || "Informational").rank) {
                by[k].severity = r.impact;
              }
            });
            const items = Object.keys(by).map((k) => by[k]).sort((a, b) => b.value - a.value);
            return CH.barChart(items, { label: "Developments by location", limit: 9,
              empty: "None of these developments carry a location." });
          })()),
          sectors ? panel("Exposure this maps to", null,
            h("div", { class: "em-tags" }, sectors.map((x) => UI.tag(x)))) : null,
        ].filter(Boolean)));

        wrap.appendChild(panel("Ranked developments", panelLink("All \u2192", "#/stories?category=" + cat),
          UI.dataTable({
            dense: true,
            onRow: function (r) { location.hash = "#/story/" + r.id; },
            columns: [
              { key: "impact", label: "Sev", width: "56px",
                sortValue: (r) => UI.sevMeta(r.impact).rank,
                render: (r) => UI.severityBadge(r.impact, true) },
              { key: "headline", label: "Development",
                render: (r) => h("div", { class: "st-head" }, [
                  h("span", null, C.cleanHeadline(r.headline)),
                  r.is_alert ? h("span", { class: "ic-alert-flag" }, "ALERT") : null,
                ].filter(Boolean)) },
              { key: "location_text", label: "Location", width: "14%",
                sortValue: (r) => r.location_text || r.region_name || "",
                render: (r) => r.location_text || r.region_name || "\u2014" },
              { key: "urgency", label: "Urgency", width: "10%" },
              { key: "confidence", label: "Confidence", width: "11%",
                render: (r) => UI.confidenceBadge(r.confidence) },
              { key: "relevance_score", label: "Score", width: "60px", align: "right", mono: true },
              { key: "event_time", label: "Detected", width: "10%", align: "right", mono: true,
                sortValue: (r) => r.event_time || r.first_seen || "",
                render: (r) => API.relTime(r.event_time || r.first_seen) },
            ],
            rows: rows,
          }), "flush"));
        return wrap;
      }, "metrics");
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
    // Keep a handle on the score line so it updates as you answer — otherwise
    // it renders once and appears stuck at "0 / 0".
    const scoreEl = h("p", { class: "sd-reason" }, "");
    const paintScore = () => {
      scoreEl.textContent = "Local score: " + stats.correct + " / " + stats.asked
        + " correct. Difficulty adapts to your performance.";
    };
    paintScore();
    host.appendChild(scoreEl);
    data.questions.forEach((q) => {
      const qEl = h("div", { class: "quiz-q" }, [h("strong", null, q.question)]);
      const opts = q.options.map((o, i) => h("button", { class: "quiz-opt", onclick: async (e) => {
        const btns = qEl.querySelectorAll(".quiz-opt"); btns.forEach((b) => (b.disabled = true));
        const target = e.currentTarget;
        let res;
        try {
          res = await API.quizAnswer(q.id, i);
        } catch (err) {
          // Never fail silently — a dead-looking button is worse than an error.
          btns.forEach((b) => (b.disabled = false));
          qEl.appendChild(h("p", { class: "sd-reason" }, "Could not check that answer: " + err.message));
          return;
        }
        stats.asked++; if (res.correct) stats.correct++;
        API.LS.set("quizStats", stats);
        paintScore();
        btns[res.answer_index].classList.add("correct");
        if (!res.correct) target.classList.add("wrong");
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
      // 200 undifferentiated rows is not an audit trail you can actually use,
      // so filter by actor/action and free text. Filtering is client-side over
      // the fetched page — no extra endpoint, and it stays instant.
      const rows = audit.audit || [];
      const uniq = (key) => Array.from(new Set(rows.map((a) => a[key]).filter(Boolean))).sort();
      const state = { actor: "", action: "", q: "" };
      const tbody = h("dl", { class: "kv" });
      const count = h("span", { class: "sd-reason" }, "");

      function paintAudit() {
        const q = state.q.toLowerCase();
        const shown = rows.filter((a) =>
          (!state.actor || a.actor === state.actor)
          && (!state.action || a.action === state.action)
          && (!q || JSON.stringify(a).toLowerCase().includes(q)));
        tbody.innerHTML = "";
        if (!shown.length) {
          tbody.appendChild(h("p", { class: "sd-reason" }, "No entries match these filters."));
        }
        shown.forEach((a) => {
          tbody.appendChild(h("dt", { style: "font-family:var(--mono);font-size:.74rem" }, API.fmtTime(a.ts)));
          tbody.appendChild(h("dd", null, "[" + a.actor + "] " + a.action
            + (a.entity ? " · " + a.entity : "")
            + (a.detail ? " — " + C.truncate(a.detail, 80) : "")));
        });
        count.textContent = "Showing " + shown.length + " of " + rows.length + " entries.";
      }

      const pick = (label, key, options) => {
        const s = h("select", { onchange: (e) => { state[key] = e.target.value; paintAudit(); } },
          [h("option", { value: "" }, "All")].concat(options.map((o) => h("option", { value: o }, o))));
        return h("label", null, [label, s]);
      };

      wrap.appendChild(h("div", { class: "panel", style: "margin-top:1rem" }, [
        h("div", { class: "sc-top" }, [h("h2", null, "Audit log"), count]),
        h("div", { class: "filters" }, [
          pick("Actor", "actor", uniq("actor")),
          pick("Action", "action", uniq("action")),
          h("label", null, ["Contains", h("input", {
            type: "search", placeholder: "story id, detail…",
            oninput: (e) => { state.q = e.target.value; paintAudit(); } })]),
        ]),
        h("div", { style: "max-height:420px;overflow:auto" }, tbody),
      ]));
      paintAudit();
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
            const value = tokenInput.value.trim();
            // Submitting an empty box used to do nothing at all — no error, no
            // toast — so it read as a broken button.
            if (!value) {
              tokenInput.setAttribute("aria-invalid", "true");
              tokenInput.focus();
              C.toast("Enter a token first.");
              return;
            }
            tokenInput.removeAttribute("aria-invalid");
            API.state.token = value; API.LS.set("token", value);
            try {
              const chk = await API.req("/api/admin/check");
              if (chk.is_admin) {
                C.toast("Admin unlocked.");
                location.reload();                    // re-render with edit rights
              } else {
                // Say plainly that it did not work, rather than "saved".
                C.toast("That token was not accepted.");
                tokenInput.setAttribute("aria-invalid", "true");
              }
            } catch (e) { C.toast("Could not verify token: " + e.message); }
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

      // "What changed" feed — the payoff of advisory change-detection. Shown
      // on arrival so the first question ("what moved?") is answered without
      // having to pick a destination first. Loaded async; never blocks.
      const changeHost = h("div");
      wrap.appendChild(changeHost);
      API.advisoryChanges().then((d) => {
        changeHost.appendChild(C.advisoryChangeFeed(d, loadCountry));
      }).catch(() => {});

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

    // "Error" alone hides the distinction that actually matters: a feed that has
    // NEVER worked here needs a different fix from one that worked until today.
    // The same feed can also be healthy on one deployment and blocked on
    // another (datacenter IPs get refused), so say which state this is.
    function condition(f) {
      if (!f.enabled_by_default && f.status === "unknown") {
        return { label: "Disabled", note: "not polled by configuration" };
      }
      if (f.status === "ok") return { label: "OK", note: "" };
      if (!f.last_success) {
        return { label: "Never worked here",
                 note: "no successful fetch on this deployment" };
      }
      return { label: "Was working", note: "last succeeded " + API.relTime(f.last_success) };
    }

    const rows = feeds.map((f) => {
      const m = META[f.status] || META.unknown;
      const c = condition(f);
      const quarantined = (f.consecutive_failures || 0) >= 5;
      const last = f.last_success ? API.fmtTime(f.last_success) : "never";
      const detail = ["tier " + f.tier, f.source_type, c.note].filter(Boolean).join(" · ");
      return h("tr", null, [
        h("td", null, h("span", { class: "fh-dot " + m.cls, title: m.label }, [
          h("span", { "aria-hidden": "true" }, m.sym), " ",
          h("span", null, c.label),
        ])),
        h("td", null, [h("a", { href: f.url, target: "_blank", rel: "noopener noreferrer" }, f.name),
          h("div", { class: "sd-reason" }, detail + (f.error ? " · " + f.error : "")),
          quarantined ? h("div", { class: "sd-reason" },
            "⏸ paused after " + f.consecutive_failures
            + " failures; re-probed periodically") : null]),
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
      const regs = data.regulations || [];
      const total = data.stories.length + regs.length;
      const wrap = h("div");
      wrap.appendChild(head("Search results", '"' + q + '" · ' + total + " matches"));

      // Regulations lead: an exact framework match (e.g. "NIS2") is usually
      // what the searcher wanted, and the tracker used to be unsearchable.
      if (regs.length) {
        wrap.appendChild(h("p", { class: "section-title" },
          "Regulatory tracker (" + regs.length + ")"));
        wrap.appendChild(h("div", { class: "grid grid-2" }, regs.map(regMini)));
      }
      if (data.stories.length) {
        if (regs.length) wrap.appendChild(h("p", { class: "section-title" },
          "Developments (" + data.stories.length + ")"));
        wrap.appendChild(h("div", { class: "grid grid-2" },
          data.stories.map((s) => C.storyCard(s, openStory))));
      }
      if (!total) wrap.appendChild(C.empty("No matches. Try different keywords."));
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
