/* GSID command-centre UI kit.
 *
 * Presentation primitives shared by every view: metric tiles, severity badges,
 * data tables, filter bars, skeletons, empty and error states, plus a small set
 * of hand-drawn SVG charts.
 *
 * Charts are hand-drawn on purpose. The app has no build step and its CSP is
 * script-src 'self', so no charting library can be loaded from a CDN or bundled
 * from npm without changing the deployment. Four chart types cover every panel
 * this product actually needs, and they inherit the CSS custom properties, so
 * they retheme with the rest of the interface for free.
 *
 * Nothing here fetches. Views pass in data that came from the API; a component
 * that renders no data renders an empty state, never a placeholder value.
 */
(function () {
  "use strict";
  const C = window.GSID_C;
  const h = C.h;

  // ---------------------------------------------------------------------
  // Severity
  // ---------------------------------------------------------------------
  // The glyph is load-bearing, not decoration: it is what carries severity for
  // a colour-blind reader and in greyscale print. Never render one without it.
  const SEV = {
    Critical:      { cls: "sev-critical",  glyph: "◉", rank: 5 },
    High:          { cls: "sev-high",      glyph: "◆", rank: 4 },
    Elevated:      { cls: "sev-elevated",  glyph: "▲", rank: 3 },
    Medium:        { cls: "sev-medium",    glyph: "△", rank: 2 },
    Moderate:      { cls: "sev-moderate",  glyph: "△", rank: 2 },
    Low:           { cls: "sev-low",       glyph: "■", rank: 1 },
    Informational: { cls: "sev-info",      glyph: "□", rank: 0 },
  };
  function sevMeta(level) { return SEV[level] || SEV.Informational; }

  /** Severity badge. `compact` drops the word and keeps the glyph + title. */
  function severityBadge(level, compact) {
    const m = sevMeta(level);
    return h("span", {
      class: "badge " + m.cls + (compact ? " badge-compact" : ""),
      title: "Severity: " + (level || "Informational"),
    }, [
      h("span", { class: "badge-glyph", "aria-hidden": "true" }, m.glyph),
      compact ? h("span", { class: "sr-only" }, level || "Informational")
              : h("span", null, level || "Informational"),
    ]);
  }

  function confidenceBadge(level) {
    if (!level) return null;
    return h("span", { class: "badge conf-" + level, title: "Source confidence: " + level }, [
      h("span", { class: "badge-glyph", "aria-hidden": "true" },
        ({ Confirmed: "✓✓", High: "✓", Moderate: "≈", Low: "?", Unverified: "!" })[level] || ""),
      h("span", null, level),
    ]);
  }

  /**
   * Urgency badge. Borrows the severity palette because urgency and impact are
   * read together, but carries its own glyph — a badge tinted with a severity
   * colour and no glyph breaks the rule that colour is never the sole carrier,
   * which is exactly how 24 of these shipped colour-only on first pass.
   */
  const URGENCY = {
    "Immediate":  { cls: "sev-critical", glyph: "\u25D4" },
    "24 Hours":   { cls: "sev-high",     glyph: "\u25D1" },
    "7 Days":     { cls: "sev-moderate", glyph: "\u25D5" },
    "Long-Term":  { cls: "sev-info",     glyph: "\u25CB" },
  };
  function urgencyBadge(level) {
    if (!level) return null;
    const m = URGENCY[level] || URGENCY["Long-Term"];
    return h("span", { class: "badge " + m.cls, title: "Urgency: " + level }, [
      h("span", { class: "badge-glyph", "aria-hidden": "true" }, m.glyph),
      h("span", null, level),
    ]);
  }

  /** Advisory movement badge (escalated / eased / revised). */
  const MOVE = {
    escalated: { cls: "sev-high", glyph: "\u25B2" },
    eased:     { cls: "sev-low",  glyph: "\u25BC" },
    revised:   { cls: "sev-info", glyph: "\u25C7" },
  };
  function movementBadge(kind) {
    const m = MOVE[kind] || MOVE.revised;
    return h("span", { class: "badge " + m.cls, title: "Advisory " + kind }, [
      h("span", { class: "badge-glyph", "aria-hidden": "true" }, m.glyph),
      h("span", null, kind),
    ]);
  }

  function sourceBadge(name, tier) {
    if (!name) return null;
    return h("span", {
      class: "badge badge-quiet",
      title: tier ? name + " · tier " + tier + " source" : name,
    }, C.truncate(name, 28));
  }

  /** Neutral label pill — category, region, country. Carries no severity. */
  function tag(text, href) {
    if (!text) return null;
    return href ? h("a", { class: "tag", href: href }, text) : h("span", { class: "tag" }, text);
  }

  // ---------------------------------------------------------------------
  // Metric tile
  // ---------------------------------------------------------------------
  /**
   * @param {object} o value, label, delta (signed number|null), deltaLabel,
   *   severity, href, hint.
   * Delta is rendered only when a real previous-period number exists. A tile
   * with no comparison shows no arrow rather than implying a flat trend.
   */
  function metricCard(o) {
    const kids = [
      h("div", { class: "mc-label" }, o.label),
      h("div", { class: "mc-value-row" }, [
        h("span", { class: "mc-value num" + (o.severity ? " " + sevMeta(o.severity).cls : "") },
          o.value === null || o.value === undefined ? "—" : String(o.value)),
        o.unit ? h("span", { class: "mc-unit" }, o.unit) : null,
      ]),
    ];
    if (o.delta !== null && o.delta !== undefined && !Number.isNaN(o.delta)) {
      const dir = o.delta > 0 ? "up" : o.delta < 0 ? "down" : "flat";
      kids.push(h("div", { class: "mc-delta d-" + dir + (o.deltaGood ? " good" : "") }, [
        h("span", { "aria-hidden": "true" }, dir === "up" ? "▲" : dir === "down" ? "▼" : "–"),
        h("span", null, (o.delta > 0 ? "+" : "") + o.delta + (o.deltaLabel ? " " + o.deltaLabel : "")),
      ]));
    } else if (o.hint) {
      kids.push(h("div", { class: "mc-hint" }, o.hint));
    }
    const cls = "metric-card" + (o.href ? " is-link" : "");
    return o.href ? h("a", { class: cls, href: o.href }, kids) : h("div", { class: cls }, kids);
  }

  // ---------------------------------------------------------------------
  // States
  // ---------------------------------------------------------------------
  /** Skeleton block. Shapes match the content they stand in for, so the layout
   *  does not jump when data lands (and CLS stays near zero). */
  function skeleton(kind, n) {
    const rows = [];
    const count = n || 3;
    if (kind === "table") {
      for (let i = 0; i < count; i++) rows.push(h("div", { class: "sk-row" }));
      return h("div", { class: "sk sk-table", "aria-hidden": "true" }, rows);
    }
    if (kind === "metrics") {
      for (let i = 0; i < count; i++) rows.push(h("div", { class: "sk-metric" }));
      return h("div", { class: "sk sk-metrics", "aria-hidden": "true" }, rows);
    }
    if (kind === "chart") return h("div", { class: "sk sk-chart", "aria-hidden": "true" });
    if (kind === "map") return h("div", { class: "sk sk-map", "aria-hidden": "true" });
    for (let i = 0; i < count; i++) rows.push(h("div", { class: "sk-line" }));
    return h("div", { class: "sk", "aria-hidden": "true" }, rows);
  }

  function loadingState(kind, n, label) {
    return h("div", { class: "state-wrap", role: "status", "aria-live": "polite" }, [
      h("span", { class: "sr-only" }, label || "Loading intelligence…"),
      skeleton(kind, n),
    ]);
  }

  /** Empty state. `msg` should say what is absent and why, not just "no data". */
  function emptyState(msg, action) {
    return h("div", { class: "state-empty" }, [
      h("div", { class: "se-mark", "aria-hidden": "true" }, "◌"),
      h("p", null, msg || "No intelligence matches the current filters."),
      action || null,
    ]);
  }

  /** Error state. Keeps the rest of the page alive and offers a retry. */
  function errorState(msg, onRetry) {
    return h("div", { class: "state-error", role: "alert" }, [
      h("div", { class: "se-mark", "aria-hidden": "true" }, "⚠"),
      h("p", null, msg || "This panel could not load."),
      onRetry ? h("button", { class: "btn secondary", onclick: onRetry }, "Retry") : null,
    ]);
  }

  // ---------------------------------------------------------------------
  // Data table
  // ---------------------------------------------------------------------
  /**
   * Compact sortable table.
   * @param {object} o
   *   columns: [{key,label,render?,sort?,align?,width?,mono?}]
   *   rows:    array of records
   *   onRow:   optional click handler -> makes rows activatable
   *   empty:   message when rows is empty
   *   sort:    {key, dir} initial sort
   * Sorting is client-side over the rows handed in; it never refetches, so it
   * cannot disagree with what the server ranked.
   */
  function dataTable(o) {
    const cols = o.columns || [];
    let sort = o.sort ? Object.assign({}, o.sort) : null;
    const host = h("div", { class: "table-wrap" });

    function compare(a, b, key) {
      const col = cols.find((c) => c.key === key) || {};
      const va = col.sortValue ? col.sortValue(a) : a[key];
      const vb = col.sortValue ? col.sortValue(b) : b[key];
      if (va === vb) return 0;
      if (va === null || va === undefined) return 1;   // blanks sort last, both ways
      if (vb === null || vb === undefined) return -1;
      return typeof va === "number" && typeof vb === "number"
        ? va - vb : String(va).localeCompare(String(vb));
    }

    function draw() {
      host.innerHTML = "";
      if (!o.rows || !o.rows.length) {
        host.appendChild(emptyState(o.empty));
        return;
      }
      const rows = sort
        ? o.rows.slice().sort((a, b) => compare(a, b, sort.key) * (sort.dir === "desc" ? -1 : 1))
        : o.rows;

      const thead = h("thead", null, h("tr", null, cols.map((c) => {
        if (c.sort === false) {
          return h("th", { class: c.align ? "ta-" + c.align : null, style: c.width ? "width:" + c.width : null }, c.label);
        }
        const active = sort && sort.key === c.key;
        return h("th", {
          class: (c.align ? "ta-" + c.align + " " : "") + "th-sort" + (active ? " is-sorted" : ""),
          style: c.width ? "width:" + c.width : null,
          "aria-sort": active ? (sort.dir === "desc" ? "descending" : "ascending") : "none",
        }, h("button", {
          type: "button",
          onclick: function () {
            sort = active && sort.dir === "asc" ? { key: c.key, dir: "desc" } : { key: c.key, dir: "asc" };
            draw();
          },
        }, [c.label, h("span", { class: "th-arrow", "aria-hidden": "true" },
          active ? (sort.dir === "desc" ? "▼" : "▲") : "◇")]));
      })));

      const tbody = h("tbody", null, rows.map((r) => {
        const tr = h("tr", o.onRow ? {
          class: "is-clickable", tabindex: "0", role: "link",
          onclick: function () { o.onRow(r); },
          onkeydown: function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); o.onRow(r); } },
        } : null, cols.map((c) => h("td", {
          class: (c.align ? "ta-" + c.align + " " : "") + (c.mono ? "mono" : ""),
        }, c.render ? c.render(r) : (r[c.key] === null || r[c.key] === undefined ? "—" : String(r[c.key])))));
        return tr;
      }));

      host.appendChild(h("table", { class: "dtable" + (o.dense ? " dense" : "") }, [thead, tbody]));
    }
    draw();
    return host;
  }

  // ---------------------------------------------------------------------
  // Filter bar
  // ---------------------------------------------------------------------
  /**
   * @param {array} fields [{type:'select'|'search'|'toggle', key, label, options, value}]
   * @param {function} onChange called with the full value map on every change.
   */
  function filterBar(fields, onChange, extra) {
    const values = {};
    fields.forEach((f) => (values[f.key] = f.value === undefined ? "" : f.value));
    function fire() { onChange(Object.assign({}, values)); }

    const controls = fields.map((f) => {
      if (f.type === "search") {
        const input = h("input", {
          type: "search", value: values[f.key], placeholder: f.label,
          "aria-label": f.label,
          oninput: function (e) {
            values[f.key] = e.target.value;
            clearTimeout(input._t);
            // Debounced: typing a country name should not fire six renders.
            input._t = setTimeout(fire, 220);
          },
        });
        return h("div", { class: "fb-field fb-search" }, input);
      }
      if (f.type === "toggle") {
        return h("button", {
          type: "button",
          class: "fb-toggle" + (values[f.key] ? " is-on" : ""),
          "aria-pressed": String(!!values[f.key]),
          onclick: function (e) {
            values[f.key] = !values[f.key];
            e.currentTarget.classList.toggle("is-on", values[f.key]);
            e.currentTarget.setAttribute("aria-pressed", String(!!values[f.key]));
            fire();
          },
        }, f.label);
      }
      return h("div", { class: "fb-field" }, [
        h("label", { class: "sr-only", for: "fb-" + f.key }, f.label),
        h("select", {
          id: "fb-" + f.key,
          onchange: function (e) { values[f.key] = e.target.value; fire(); },
        }, (f.options || []).map((opt) => {
          const val = typeof opt === "string" ? opt : opt.value;
          const lab = typeof opt === "string" ? opt : opt.label;
          return h("option", { value: val, selected: val === values[f.key] ? "selected" : null }, lab);
        })),
      ]);
    });

    return h("div", { class: "filter-bar" }, [
      h("div", { class: "fb-controls" }, controls),
      extra ? h("div", { class: "fb-extra" }, extra) : null,
    ]);
  }

  // ---------------------------------------------------------------------
  // Intelligence card
  // ---------------------------------------------------------------------
  /**
   * Scannable story card. Field order is fixed across every surface so a
   * reader's eye learns one layout: severity, then headline, then where, then
   * what kind, then how well evidenced, then when.
   * Optional fields are omitted rather than shown blank — an empty "Impact:"
   * row reads as "no impact" instead of "not assessed".
   */
  function intelligenceCard(s, opts) {
    opts = opts || {};
    const href = "#/story/" + s.id;
    const when = s.event_time || s.first_seen;
    const kids = [
      h("div", { class: "ic-top" }, [
        severityBadge(s.impact),
        s.urgency ? h("span", { class: "ic-urgency" }, s.urgency) : null,
        s.is_alert ? h("span", { class: "ic-alert-flag", title: "Active critical alert" }, "ALERT") : null,
        h("span", { class: "ic-when mono" }, opts.relTime ? opts.relTime(when) : ""),
      ].filter(Boolean)),
      h("h3", { class: "ic-head" }, h("a", { href: href }, cleanish(s.headline))),
      s.summary ? h("p", { class: "ic-sum" }, truncateAt(s.summary, 190)) : null,
      h("div", { class: "ic-meta" }, [
        (s.location_text || s.region_name) ? h("span", { class: "ic-loc" }, [
          h("span", { "aria-hidden": "true" }, "\u25CE "), s.location_text || s.region_name,
        ]) : null,
        s.category_name ? tag(s.category_name) : null,
        confidenceBadge(s.confidence),
        s.relevance_score != null
          ? h("span", { class: "ic-score mono", title: "Relevance score" }, s.relevance_score + "/100")
          : null,
      ].filter(Boolean)),
      opts.footer || null,
    ];
    const el = h("article", { class: "intel-card" }, kids.filter(Boolean));
    if (opts.onOpen) {
      el.classList.add("is-clickable");
      el.tabIndex = 0;
      el.setAttribute("role", "link");
      el.addEventListener("click", function (e) {
        if (e.target.closest("a,button")) return;   // let real links win
        opts.onOpen(s);
      });
      el.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); opts.onOpen(s); }
      });
    }
    return el;
  }
  function cleanish(t) { return String(t || "").replace("[DEMO] ", ""); }
  function truncateAt(t, n) {
    t = String(t || "");
    return t.length > n ? t.slice(0, n).trim() + "\u2026" : t;
  }

  window.GSID_UI = {
    SEV, sevMeta, severityBadge, confidenceBadge, urgencyBadge, movementBadge,
    sourceBadge, tag,
    metricCard, intelligenceCard, skeleton, loadingState, emptyState, errorState,
    dataTable, filterBar,
  };
})();
