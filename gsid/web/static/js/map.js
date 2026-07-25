/* Lightweight schematic world map (equirectangular). Dots are projected from
   lat/lon; region bands are clickable. Not a survey-grade map — a fast
   situational overview. Each dot has an accessible title. */
(function () {
  "use strict";
  const C = window.GSID_C;
  const h = C.h;
  const SVGNS = "http://www.w3.org/2000/svg";

  function svg(tag, attrs, kids) {
    const el = document.createElementNS(SVGNS, tag);
    for (const k in (attrs || {})) el.setAttribute(k, attrs[k]);
    (kids || []).forEach((c) => el.appendChild(c));
    return el;
  }

  const W = 1000, H = 500;
  function proj(lat, lon) {
    return [((lon + 180) / 360) * W, ((90 - lat) / 180) * H];
  }

  // Very rough continent silhouettes (schematic, for orientation only).
  const CONTINENTS = [
    // North America
    "M120,90 L250,80 L300,150 L250,230 L200,250 L170,200 L120,150 Z",
    // South America
    "M270,270 L330,260 L340,360 L300,440 L270,400 L280,320 Z",
    // Europe
    "M470,90 L560,85 L560,150 L500,170 L470,140 Z",
    // Africa
    "M480,190 L580,180 L600,300 L540,400 L500,320 L480,250 Z",
    // Asia
    "M580,80 L820,70 L880,180 L780,240 L640,220 L580,150 Z",
    // Southeast Asia / Indonesia
    "M760,250 L860,250 L880,300 L780,300 Z",
    // Australia
    "M800,340 L900,335 L910,410 L820,420 Z",
  ];

  // Region clickable bands (approx bounding boxes in map coords).
  const REGION_BOXES = {
    north_america: [90, 60, 230, 200],
    latam_caribbean: [250, 250, 120, 200],
    europe: [455, 70, 130, 110],
    mena: [470, 175, 150, 120],
    subsaharan_africa: [480, 250, 140, 170],
    south_asia: [640, 190, 110, 90],
    central_asia: [610, 120, 130, 70],
    east_asia: [760, 100, 140, 120],
    southeast_asia: [740, 240, 150, 90],
    australia_pacific: [790, 330, 150, 110],
  };

  const IMPACT_COLOR = {
    Critical: "var(--sev-critical)", High: "var(--sev-high)",
    Moderate: "var(--sev-moderate)", Low: "var(--sev-low)",
  };

  function render(data, onPoint, onRegion) {
    const s = svg("svg", { viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": "World map of tracked developments" });
    s.appendChild(svg("rect", { x: 0, y: 0, width: W, height: H, fill: "var(--panel-2)", rx: 8 }));
    // graticule
    for (let x = 0; x <= W; x += 100) s.appendChild(svg("line", { x1: x, y1: 0, x2: x, y2: H, stroke: "var(--border)", "stroke-width": .4 }));
    for (let y = 0; y <= H; y += 50) s.appendChild(svg("line", { x1: 0, y1: y, x2: W, y2: y, stroke: "var(--border)", "stroke-width": .4 }));
    // continents
    CONTINENTS.forEach((d) => s.appendChild(svg("path", { d, class: "map-region" })));

    // clickable region bands (invisible but labelled)
    Object.entries(REGION_BOXES).forEach(([rid, box]) => {
      const [x, y, w, hh] = box;
      const g = svg("g", { style: "cursor:pointer" });
      const rect = svg("rect", { x, y, width: w, height: hh, fill: "transparent", stroke: "transparent" });
      rect.addEventListener("click", () => onRegion(rid));
      rect.addEventListener("mouseenter", () => rect.setAttribute("fill", "color-mix(in srgb, var(--accent) 12%, transparent)"));
      rect.addEventListener("mouseleave", () => rect.setAttribute("fill", "transparent"));
      const title = svg("title", {}); title.textContent = "Filter " + rid.replace(/_/g, " ");
      g.appendChild(rect); g.appendChild(title);
      s.appendChild(g);
    });

    // story dots
    (data.points || []).forEach((p) => {
      const [cx, cy] = proj(p.lat, p.lon);
      const g = svg("g", { class: "map-dot" });
      const c = svg("circle", { cx, cy, r: p.is_alert ? 8 : 6, fill: IMPACT_COLOR[p.impact] || "var(--sev-moderate)",
        "fill-opacity": .85, stroke: "var(--bg)", "stroke-width": 1.5 });
      if (p.is_alert) {
        const ring = svg("circle", { cx, cy, r: 8, fill: "none", stroke: IMPACT_COLOR[p.impact] || "var(--sev-critical)", "stroke-width": 1.5, "stroke-opacity": .6 });
        g.appendChild(ring);
      }
      const title = svg("title", {});
      title.textContent = (p.headline || "").replace("[DEMO] ", "") + " — " + p.impact + " impact, " + p.confidence + " confidence";
      c.addEventListener("click", () => onPoint(p.id));
      g.appendChild(c); g.appendChild(title);
      s.appendChild(g);
    });

    // legend
    const legend = h("div", { class: "sc-meta", style: "margin-top:.6rem" }, [
      C.chip("Critical", "sev-critical", "⬤"), C.chip("High", "sev-high", "◆"),
      C.chip("Moderate", "sev-moderate", "▲"), C.chip("Low", "sev-low", "■"),
      h("span", { class: "sd-reason" }, "Schematic overview — click a dot to open, or a region area to filter. " + (data.points || []).length + " geolocated developments."),
    ]);

    return h("div", { class: "map-wrap" }, [s, legend]);
  }

  window.GSID_MAP = { render };
})();
