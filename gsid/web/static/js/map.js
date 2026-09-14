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

  // Orthographic globe. A flat plate-carrée map is a picture of the world; a
  // globe you can turn is the world — and for a desk whose whole subject is
  // where things are happening, that difference is the point.
  const W = 900, H = 900;
  const R = 366, CX = W / 2, CY = H / 2;
  const RAD = Math.PI / 180;

  // Rotation state: lambda0 = spin (lon), phi0 = tilt (lat).
  const view = { lam: -10 * RAD, phi: 12 * RAD };

  function proj(lat, lon) {
    const phi = lat * RAD, lam = lon * RAD - view.lam;
    const cosPhi = Math.cos(phi), sinPhi = Math.sin(phi);
    const cosLam = Math.cos(lam), sinLam = Math.sin(lam);
    const cosPhi0 = Math.cos(view.phi), sinPhi0 = Math.sin(view.phi);
    // cos of angular distance from the view centre: negative == far side.
    const cosc = sinPhi0 * sinPhi + cosPhi0 * cosPhi * cosLam;
    return [
      CX + R * cosPhi * sinLam,
      CY - R * (cosPhi0 * sinPhi - sinPhi0 * cosPhi * cosLam),
      cosc,
    ];
  }

  function visible(lat, lon) { return proj(lat, lon)[2] >= 0; }

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

  // Points on the far side of the globe project onto the near hemisphere
  // mirrored, so they must be dropped rather than drawn. Each ring therefore
  // becomes one or more visible segments instead of a single closed loop.
  function pathFor(geom) {
    const polys = geom.type === "Polygon" ? [geom.coordinates] : geom.coordinates;
    let d = "";
    for (const poly of polys) {
      for (const ring of poly) {
        let open = false;
        for (let i = 0; i < ring.length; i++) {
          const [x, y, c] = proj(ring[i][1], ring[i][0]);
          if (c < 0) {                 // crossed the horizon — end this segment
            if (open) { d += "Z"; open = false; }
            continue;
          }
          d += (open ? "L" : "M") + x.toFixed(1) + "," + y.toFixed(1);
          open = true;
        }
        if (open) d += "Z";
      }
    }
    return d;
  }

  // Meridians and parallels give the sphere its depth; without them a filled
  // circle of countries reads as a sticker rather than a globe.
  function graticulePath(step) {
    let d = "";
    for (let lon = -180; lon <= 180; lon += step) {
      let open = false;
      for (let lat = -90; lat <= 90; lat += 3) {
        const [x, y, c] = proj(lat, lon);
        if (c < 0) { open = false; continue; }
        d += (open ? "L" : "M") + x.toFixed(1) + "," + y.toFixed(1);
        open = true;
      }
    }
    for (let lat = -60; lat <= 60; lat += step) {
      let open = false;
      for (let lon = -180; lon <= 180; lon += 3) {
        const [x, y, c] = proj(lat, lon);
        if (c < 0) { open = false; continue; }
        d += (open ? "L" : "M") + x.toFixed(1) + "," + y.toFixed(1);
        open = true;
      }
    }
    return d;
  }

  function riskOpacity(count) {
    // On a flat map a high floor kept every shaded country legible. On a globe
    // that made the whole sphere one colour, because "worst impact ever seen"
    // is Critical for most countries. Volume now carries the weight: a country
    // with one report reads faintly, a hotspot reads solid.
    const n = Math.max(1, count);
    return Math.min(0.92, 0.18 + Math.log(n + 1) / Math.log(40) * 0.74);
  }

  function buildSvg(geo, data, onPoint, onCountry) {
    const risk = data.country_risk || {};
    const s = svg("svg", { viewBox: "0 0 " + W + " " + H, class: "world-map",
      role: "img", "aria-label": "World map of tracked developments by country" });
    // Sphere: a soft limb gradient reads as curvature, so the disc looks like a
    // body in space rather than a filled circle.
    const defs = svg("defs", {});
    defs.innerHTML =
      '<radialGradient id="globeShade" cx="38%" cy="32%" r="78%">' +
      '<stop offset="0%" stop-color="var(--panel-3)"/>' +
      '<stop offset="62%" stop-color="var(--panel-2)"/>' +
      '<stop offset="100%" stop-color="var(--bg-2)"/>' +
      '</radialGradient>' +
      '<radialGradient id="globeGlow" cx="50%" cy="50%" r="50%">' +
      '<stop offset="86%" stop-color="var(--accent)" stop-opacity="0"/>' +
      '<stop offset="100%" stop-color="var(--accent)" stop-opacity="0.22"/>' +
      '</radialGradient>';
    s.appendChild(defs);
    s.appendChild(svg("circle", { cx: CX, cy: CY, r: R, class: "globe-sphere",
                                  fill: "url(#globeShade)" }));
    const grat = svg("path", { class: "map-grat", d: graticulePath(30) });
    s.appendChild(grat);

    // Redraw on rotation reuses these nodes — rebuilding 177 paths per frame
    // would allocate constantly and drop frames while dragging.
    const countryPaths = [];
    const dotNodes = [];

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
      const label = r
        ? `${f.properties.name} — ${r.count} tracked development${r.count > 1 ? "s" : ""}, worst impact ${r.impact}`
        : f.properties.name;
      const title = svg("title", {});
      title.textContent = label;
      path.appendChild(title);

      // Only countries that actually have tracked activity are interactive.
      // Clicking an inert country just opened an empty filter, and making all
      // 177 focusable would bury the keyboard user in meaningless tab stops.
      if (iso && r) {
        path.classList.add("clickable");
        path.setAttribute("role", "button");
        path.setAttribute("tabindex", "0");
        path.setAttribute("aria-label", label);
        const open = () => onCountry(iso);
        path.addEventListener("click", open);
        path.addEventListener("keydown", (e) => {
          if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); }
        });
      } else {
        // Decorative landmass: announced via the map's own label, not per-shape.
        path.setAttribute("aria-hidden", "true");
      }
      countryPaths.push([path, f.geometry]);
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
      const label = (p.headline || "").replace("[DEMO] ", "")
        + " — " + p.impact + " impact, " + p.confidence + " confidence";
      const title = svg("title", {});
      title.textContent = label;
      c.setAttribute("role", "button");
      c.setAttribute("tabindex", "0");
      c.setAttribute("aria-label", label);
      const open = () => onPoint(p.id);
      c.addEventListener("click", open);
      c.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); }
      });
      g.appendChild(c); g.appendChild(title);
      dotNodes.push([g, p]);
      s.appendChild(g);
    }

    // Reproject everything for the current rotation. Dots on the far side are
    // hidden rather than moved, otherwise they would surface on the wrong
    // continent.
    function redraw() {
      // Update the graticule in place. Re-appending it moved the node to the
      // end of the SVG, which in paint order put it ON TOP of every country and
      // swallowed their clicks.
      grat.setAttribute("d", graticulePath(30));
      for (const [path, geom] of countryPaths) path.setAttribute("d", pathFor(geom));
      for (const [g, p] of dotNodes) {
        const [x, y, c] = proj(p.lat, p.lon);
        if (c < 0) { g.setAttribute("visibility", "hidden"); continue; }
        g.removeAttribute("visibility");
        g.querySelectorAll("circle").forEach((el) => {
          el.setAttribute("cx", x.toFixed(1));
          el.setAttribute("cy", y.toFixed(1));
        });
      }
    }
    attachRotation(s, redraw);
    redraw();
    return s;
  }

  // Drag to spin. Pointer events cover mouse, trackpad and touch in one path;
  // setPointerCapture keeps the gesture alive when the cursor leaves the disc.
  function attachRotation(node, redraw) {
    // `pending` is the gap between pressing and actually dragging. Capturing the
    // pointer on pointerdown redirects the following pointerup — and the click
    // the browser synthesises from it — to the capturing element, so every
    // country click was being swallowed by the globe. Capture only once the
    // pointer has genuinely moved, so a press-and-release stays a click.
    let pending = false, dragging = false, lastX = 0, lastY = 0, raf = 0;
    let downX = 0, downY = 0, pointerId = null;
    const DRAG_THRESHOLD = 4;          // px of travel before it counts as a drag
    const MAX_TILT = 78 * RAD;

    function schedule() {
      if (raf) return;
      raf = requestAnimationFrame(() => { raf = 0; redraw(); });
    }
    node.addEventListener("pointerdown", (e) => {
      pending = true; dragging = false;
      downX = lastX = e.clientX; downY = lastY = e.clientY;
      pointerId = e.pointerId;
    });
    node.addEventListener("pointermove", (e) => {
      if (pending && !dragging) {
        if (Math.hypot(e.clientX - downX, e.clientY - downY) < DRAG_THRESHOLD) return;
        dragging = true;
        try { node.setPointerCapture(pointerId); } catch { /* pointer already gone */ }
        node.classList.add("grabbing");
      }
      if (!dragging) return;
      const box = node.getBoundingClientRect();
      // Scale by rendered size so a drag moves the same arc at any zoom.
      const k = (Math.PI / Math.max(box.width, 1)) * 1.1;
      view.lam -= (e.clientX - lastX) * k;
      view.phi = Math.max(-MAX_TILT, Math.min(MAX_TILT, view.phi + (e.clientY - lastY) * k));
      lastX = e.clientX; lastY = e.clientY;
      schedule();
    });
    const stop = (e) => {
      const wasDragging = dragging;
      pending = false; dragging = false;
      node.classList.remove("grabbing");
      if (wasDragging && e.pointerId !== undefined
          && node.hasPointerCapture?.(e.pointerId)) {
        node.releasePointerCapture(e.pointerId);
      }
      pointerId = null;
    };
    node.addEventListener("pointerup", stop);
    node.addEventListener("pointercancel", stop);

    // Keyboard parity: the globe is a control, so arrows must turn it.
    node.setAttribute("tabindex", "0");
    node.addEventListener("keydown", (e) => {
      const step = 6 * RAD;
      if (e.key === "ArrowLeft") view.lam -= step;
      else if (e.key === "ArrowRight") view.lam += step;
      else if (e.key === "ArrowUp") view.phi = Math.min(MAX_TILT, view.phi + step);
      else if (e.key === "ArrowDown") view.phi = Math.max(-MAX_TILT, view.phi - step);
      else return;
      e.preventDefault();
      schedule();
    });
  }

  function countryTextAlternative(geo, data, onCountry) {
    const risk = data.country_risk || {};
    const names = {};
    for (const f of geo.features) {
      if (f.properties.iso) names[f.properties.iso] = f.properties.name;
    }
    const order = { Critical: 0, High: 1, Moderate: 2, Low: 3 };
    const entries = Object.entries(risk)
      .filter(([iso]) => names[iso])
      .sort((a, b) => (order[a[1].impact] ?? 9) - (order[b[1].impact] ?? 9)
                      || b[1].count - a[1].count);
    if (!entries.length) return h("div");

    const list = h("ul", { class: "map-country-list" }, entries.map(([iso, r]) =>
      h("li", null, h("button", { class: "linklike", onclick: () => onCountry(iso) },
        `${names[iso]} — ${r.impact}, ${r.count} development${r.count > 1 ? "s" : ""}`))));
    const details = h("details", { class: "map-alt" }, [
      h("summary", null, `Countries with tracked activity (${entries.length})`),
      list,
    ]);
    return details;
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
      // Equivalent non-visual route to the same information. A choropleth is
      // not usable with a screen reader however well each shape is labelled.
      holder.appendChild(countryTextAlternative(geo, data, onCountry));
    }).catch(() => {
      holder.textContent = "";
      holder.appendChild(C.empty("Could not load map geometry."));
    });
    return h("div", { class: "map-wrap" }, [holder, legend]);
  }

  window.GSID_MAP = { render };
})();
