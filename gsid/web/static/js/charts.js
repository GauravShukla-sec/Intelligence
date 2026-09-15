/* Hand-drawn SVG charts.
 *
 * No charting library: the app has no build step and its CSP is
 * script-src 'self', so nothing can be pulled from a CDN or bundled from npm
 * without changing how the app is deployed. These four cover every analytical
 * panel in the product.
 *
 * Shared rules, so the set reads as one system:
 *   - colours come from CSS custom properties, so charts retheme automatically;
 *   - every chart is labelled and exposes its numbers as a table to screen
 *     readers, because a chart that only exists visually is not evidence;
 *   - no chart renders without data. An empty series returns an empty state,
 *     not an axis with nothing on it, which reads as "zero" rather than "none";
 *   - viewBox + preserveAspectRatio, so they scale without a resize listener.
 */
(function () {
  "use strict";
  const C = window.GSID_C;
  const UI = window.GSID_UI;
  const h = C.h;
  const NS = "http://www.w3.org/2000/svg";

  function svg(tag, attrs) {
    const el = document.createElementNS(NS, tag);
    for (const k in attrs) {
      if (attrs[k] === null || attrs[k] === undefined) continue;
      el.setAttribute(k, attrs[k]);
    }
    return el;
  }

  /** Screen-reader equivalent: the same numbers as a real table. */
  function dataTableFallback(caption, pairs) {
    return h("table", { class: "sr-only" }, [
      h("caption", null, caption),
      h("tbody", null, pairs.map(([k, v]) =>
        h("tr", null, [h("th", { scope: "row" }, String(k)), h("td", null, String(v))]))),
    ]);
  }

  function frame(cls, node, caption, pairs) {
    return h("figure", { class: "chart " + (cls || "") }, [
      node,
      dataTableFallback(caption, pairs),
    ]);
  }

  // ---------------------------------------------------------------------
  // Sparkline / area trend
  // ---------------------------------------------------------------------
  /**
   * @param {array} points [{label, value}]
   * A trend needs at least two observations; one point is a reading, not a
   * trend, and drawing it as a flat line asserts stability that was never
   * measured.
   */
  function trendChart(points, o) {
    o = o || {};
    if (!points || points.length < 2) {
      return UI.emptyState(o.empty || "Not enough history yet to plot a trend.");
    }
    const W = 100, H = o.height || 32, pad = 2;
    const vals = points.map((p) => p.value);
    const min = Math.min.apply(null, vals);
    const max = Math.max.apply(null, vals);
    const span = max - min || 1;
    const x = (i) => pad + (i * (W - pad * 2)) / (points.length - 1);
    const y = (v) => H - pad - ((v - min) / span) * (H - pad * 2);

    const line = points.map((p, i) => (i ? "L" : "M") + x(i).toFixed(2) + " " + y(p.value).toFixed(2)).join(" ");
    const area = line + " L" + x(points.length - 1).toFixed(2) + " " + H + " L" + x(0).toFixed(2) + " " + H + " Z";

    const g = svg("svg", {
      viewBox: "0 0 " + W + " " + H, preserveAspectRatio: "none",
      class: "spark", role: "img", "aria-label": o.label || "Trend",
    });
    const gid = "sparkfill-" + Math.random().toString(36).slice(2, 8);
    const defs = svg("defs");
    const grad = svg("linearGradient", { id: gid, x1: "0", y1: "0", x2: "0", y2: "1" });
    grad.appendChild(svg("stop", { offset: "0%", "stop-color": "currentColor", "stop-opacity": ".28" }));
    grad.appendChild(svg("stop", { offset: "100%", "stop-color": "currentColor", "stop-opacity": "0" }));
    defs.appendChild(grad); g.appendChild(defs);
    g.appendChild(svg("path", { d: area, fill: "url(#" + gid + ")", stroke: "none" }));
    g.appendChild(svg("path", {
      d: line, fill: "none", stroke: "currentColor", "stroke-width": "1.4",
      "vector-effect": "non-scaling-stroke", "stroke-linejoin": "round", "stroke-linecap": "round",
    }));
    // Mark the latest reading: it is the number the panel's headline quotes.
    g.appendChild(svg("circle", {
      cx: x(points.length - 1), cy: y(vals[vals.length - 1]), r: "1.6",
      fill: "currentColor", "vector-effect": "non-scaling-stroke",
    }));

    return frame("chart-spark", g, o.label || "Trend",
      points.map((p) => [p.label, p.value]));
  }

  // ---------------------------------------------------------------------
  // Horizontal bars — ranked categories
  // ---------------------------------------------------------------------
  /**
   * @param {array} items [{label, value, severity?, href?}]
   * Bars are proportional to the largest value, and the value is printed as
   * well as drawn, so the reader never has to estimate from length.
   */
  function barChart(items, o) {
    o = o || {};
    if (!items || !items.length) return UI.emptyState(o.empty || "No data in this period.");
    const max = Math.max.apply(null, items.map((i) => i.value)) || 1;
    const rows = items.slice(0, o.limit || 8).map((it) => {
      const pct = Math.max(1.5, (it.value / max) * 100);
      const sev = it.severity ? UI.sevMeta(it.severity).cls : "";
      const bar = h("div", { class: "bc-track" }, [
        h("div", { class: "bc-fill " + sev, style: "width:" + pct.toFixed(1) + "%" }),
      ]);
      const label = it.href
        ? h("a", { class: "bc-label", href: it.href }, it.label)
        : h("span", { class: "bc-label" }, it.label);
      return h("div", { class: "bc-row" }, [
        label, bar, h("span", { class: "bc-val num" }, String(it.value)),
      ]);
    });
    return frame("chart-bars", h("div", { class: "bc" }, rows),
      o.label || "Breakdown", items.map((i) => [i.label, i.value]));
  }

  // ---------------------------------------------------------------------
  // Donut — distribution across a small set of categories
  // ---------------------------------------------------------------------
  /**
   * @param {array} slices [{label, value, severity?}]
   * Capped at six slices plus "Other": beyond that the arcs are too small to
   * compare and the legend does the work anyway.
   */
  function donutChart(slices, o) {
    o = o || {};
    const clean = (slices || []).filter((s) => s.value > 0);
    if (!clean.length) return UI.emptyState(o.empty || "Nothing recorded in this period.");

    let use = clean.slice().sort((a, b) => b.value - a.value);
    if (use.length > 7) {
      const rest = use.slice(6).reduce((n, s) => n + s.value, 0);
      use = use.slice(0, 6).concat([{ label: "Other", value: rest }]);
    }
    const total = use.reduce((n, s) => n + s.value, 0);
    const R = 42, SW = 13, CIRC = 2 * Math.PI * R;

    const g = svg("svg", {
      viewBox: "0 0 110 110", class: "donut", role: "img",
      "aria-label": (o.label || "Distribution") + ": " + total + " total",
    });
    g.appendChild(svg("circle", {
      cx: 55, cy: 55, r: R, fill: "none", "stroke-width": SW, class: "donut-track",
    }));
    let offset = 0;
    use.forEach((s, i) => {
      const frac = s.value / total;
      const arc = svg("circle", {
        cx: 55, cy: 55, r: R, fill: "none", "stroke-width": SW,
        "stroke-dasharray": (frac * CIRC).toFixed(2) + " " + CIRC,
        "stroke-dashoffset": (-offset * CIRC).toFixed(2),
        transform: "rotate(-90 55 55)",
        class: "donut-arc " + (s.severity ? UI.sevMeta(s.severity).cls : "cat-" + (i % 7)),
      });
      arc.appendChild(svg("title", {})).textContent = s.label + ": " + s.value;
      g.appendChild(arc);
      offset += frac;
    });

    const centre = h("div", { class: "donut-centre" }, [
      h("span", { class: "dc-num num" }, String(total)),
      h("span", { class: "dc-lab" }, o.centreLabel || "total"),
    ]);
    const legend = h("ul", { class: "donut-legend" }, use.map((s, i) =>
      h("li", null, [
        h("span", {
          class: "dl-swatch " + (s.severity ? UI.sevMeta(s.severity).cls : "cat-" + (i % 7)),
          "aria-hidden": "true",
        }),
        h("span", { class: "dl-lab" }, s.label),
        h("span", { class: "dl-val num" }, String(s.value)),
      ])));

    return frame("chart-donut",
      h("div", { class: "donut-wrap" }, [h("div", { class: "donut-hold" }, [g, centre]), legend]),
      o.label || "Distribution", use.map((s) => [s.label, s.value]));
  }

  // ---------------------------------------------------------------------
  // Stacked severity bar — composition per group
  // ---------------------------------------------------------------------
  /**
   * @param {array} groups [{label, counts:{Critical,High,Moderate,Low}, href?}]
   * Segment order is fixed worst-first so bars are comparable across rows at a
   * glance; that only works if the order never varies.
   */
  function severityBars(groups, o) {
    o = o || {};
    const ORDER = ["Critical", "High", "Moderate", "Low"];
    const use = (groups || []).filter((g) =>
      ORDER.some((k) => (g.counts && g.counts[k]) > 0));
    if (!use.length) return UI.emptyState(o.empty || "No scored developments in this period.");

    const max = Math.max.apply(null, use.map((g) =>
      ORDER.reduce((n, k) => n + (g.counts[k] || 0), 0))) || 1;

    const rows = use.map((grp) => {
      const total = ORDER.reduce((n, k) => n + (grp.counts[k] || 0), 0);
      const segs = ORDER.filter((k) => grp.counts[k] > 0).map((k) =>
        h("div", {
          class: "sb-seg " + UI.sevMeta(k).cls,
          style: "flex:" + grp.counts[k],
          title: k + ": " + grp.counts[k],
        }));
      const label = grp.href
        ? h("a", { class: "sb-label", href: grp.href }, grp.label)
        : h("span", { class: "sb-label" }, grp.label);
      return h("div", { class: "sb-row" }, [
        label,
        h("div", { class: "sb-track", style: "width:" + ((total / max) * 100).toFixed(1) + "%" }, segs),
        h("span", { class: "sb-val num" }, String(total)),
      ]);
    });

    const key = h("div", { class: "sb-key" }, ORDER.map((k) =>
      h("span", { class: "sb-key-item" }, [
        h("span", { class: "dl-swatch " + UI.sevMeta(k).cls, "aria-hidden": "true" }),
        h("span", null, k),
      ])));

    const pairs = [];
    use.forEach((g) => ORDER.forEach((k) => {
      if (g.counts[k]) pairs.push([g.label + " — " + k, g.counts[k]]);
    }));
    return frame("chart-sevbars",
      h("div", { class: "sb" }, [h("div", { class: "sb-rows" }, rows), key]),
      o.label || "Severity by group", pairs);
  }

  window.GSID_CHARTS = { trendChart, barChart, donutChart, severityBars };
})();
