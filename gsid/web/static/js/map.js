/* Real world map (equirectangular / plate carrée). Country geometry is loaded
   from a bundled, slimmed Natural Earth 110m dataset and drawn as SVG paths;
   countries are shaded by their worst tracked impact (a risk choropleth), and
   individual geolocated developments are overlaid as clickable dots. The
   projection matches the dot projection exactly, so points sit on the map.
   Self-contained: no tiles, no external requests. */
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

  const W = 1000, H = 500;               // 2:1 == correct equirectangular aspect
  function proj(lat, lon) {
    return [((lon + 180) / 360) * W, ((90 - lat) / 180) * H];
  }

  const IMPACT_COLOR = {
    Critical: "var(--sev-critical)", High: "var(--sev-high)",
    Moderate: "var(--sev-moderate)", Low: "var(--sev-low)",
  };

  // Cache the geometry across view switches (fetched once per session).
  let _geo = null;
  function loadGeo() {
    if (!_geo) _geo = fetch("/static/data/world-countries.geo.json").then((r) => r.json());
    return _geo;
  }

  function pathFor(geom) {
    const polys = geom.type === "Polygon" ? [geom.coordinates] : geom.coordinates;
    let d = "";
    for (const poly of polys) {
      for (const ring of poly) {
        for (let i = 0; i < ring.length; i++) {
          const [x, y] = proj(ring[i][1], ring[i][0]);
          d += (i === 0 ? "M" : "L") + x.toFixed(1) + "," + y.toFixed(1);
        }
        d += "Z";
      }
    }
    return d;
  }

  function riskOpacity(count) {
    return Math.min(0.82, 0.3 + Math.min(count, 6) * 0.088);
  }

  function buildSvg(geo, data, onPoint, onCountry) {
    const risk = data.country_risk || {};
    const s = svg("svg", { viewBox: "0 0 " + W + " " + H, class: "world-map",
      role: "img", "aria-label": "World map of tracked developments by country" });
    // ocean + graticule
    s.appendChild(svg("rect", { x: 0, y: 0, width: W, height: H, class: "map-ocean", rx: 8 }));
    for (let x = 0; x <= W; x += 1000 / 12) s.appendChild(svg("line", { x1: x, y1: 0, x2: x, y2: H, class: "map-grat" }));
    for (let y = 0; y <= H; y += 500 / 6) s.appendChild(svg("line", { x1: 0, y1: y, x2: W, y2: y, class: "map-grat" }));

    // countries
    for (const f of geo.features) {
      const iso = (f.properties.iso || "");
      const r = iso && risk[iso];
      const path = svg("path", { d: pathFor(f.geometry), class: "map-country" });
      if (r) {
        // Inline style (not a presentation attribute) so it overrides the
        // .map-country class fill — SVG CSS rules beat fill="…" attributes.
        path.style.fill = IMPACT_COLOR[r.impact] || "var(--sev-moderate)";
        path.style.fillOpacity = riskOpacity(r.count).toFixed(2);
        path.classList.add("has-risk");
      }
      const title = svg("title", {});
      title.textContent = r
        ? `${f.properties.name} — ${r.count} development(s), worst impact ${r.impact}`
        : f.properties.name;
      path.appendChild(title);
      if (iso) {
        path.classList.add("clickable");
        path.addEventListener("click", () => onCountry(iso));
      }
      s.appendChild(path);
    }

    // geolocated developments (precise events; click opens the story)
    for (const p of (data.points || [])) {
      const [cx, cy] = proj(p.lat, p.lon);
      const g = svg("g", { class: "map-dot" });
      if (p.is_alert) {
        g.appendChild(svg("circle", { cx, cy, r: 9, fill: "none",
          stroke: IMPACT_COLOR[p.impact] || "var(--sev-critical)", "stroke-width": 1.4, "stroke-opacity": .55 }));
      }
      const c = svg("circle", { cx, cy, r: p.is_alert ? 5 : 4,
        fill: IMPACT_COLOR[p.impact] || "var(--sev-moderate)", "fill-opacity": .95,
        stroke: "var(--bg)", "stroke-width": 1.2, style: "cursor:pointer" });
      const title = svg("title", {});
      title.textContent = (p.headline || "").replace("[DEMO] ", "") + " — " + p.impact + " impact, " + p.confidence + " confidence";
      c.addEventListener("click", () => onPoint(p.id));
      g.appendChild(c); g.appendChild(title);
      s.appendChild(g);
    }
    return s;
  }

  function render(data, onPoint, onCountry) {
    const legend = h("div", { class: "sc-meta", style: "margin-top:.6rem" }, [
      C.chip("Critical", "sev-critical", "⬤"), C.chip("High", "sev-high", "◆"),
      C.chip("Moderate", "sev-moderate", "▲"), C.chip("Low", "sev-low", "■"),
      h("span", { class: "sd-reason" },
        "Countries shaded by worst tracked impact; dots are individual geolocated developments. "
        + "Click a country to filter its stories, or a dot to open it. "
        + (data.points || []).length + " geolocated · "
        + Object.keys(data.country_risk || {}).length + " countries with activity."),
    ]);
    const holder = h("div", { class: "map-canvas" }, C.loading());
    loadGeo().then((geo) => {
      holder.textContent = "";
      holder.appendChild(buildSvg(geo, data, onPoint, onCountry));
    }).catch(() => {
      holder.textContent = "";
      holder.appendChild(C.empty("Could not load map geometry."));
    });
    return h("div", { class: "map-wrap" }, [holder, legend]);
  }

  window.GSID_MAP = { render };
})();
