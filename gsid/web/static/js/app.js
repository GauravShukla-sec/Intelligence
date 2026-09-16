/* Router + app initialization. Hash-based, no build step. */
(function () {
  "use strict";
  const API = window.GSID_API;
  const C = window.GSID_C;
  const Views = window.GSID_VIEWS;

  const viewEl = document.getElementById("view");
  const navLinks = Array.from(document.querySelectorAll("[data-nav]"));

  // Route table: hash pattern -> view name + params parser.
  function parseHash() {
    const raw = (location.hash || "#/dashboard").slice(1); // "/story/abc?x=y"
    const [path, query] = raw.split("?");
    const parts = path.split("/").filter(Boolean); // ["story","abc"]
    const params = {};
    if (query) new URLSearchParams(query).forEach((v, k) => (params[k] = v));
    return { parts, params };
  }

  const ROUTES = {
    "": "dashboard",
    dashboard: "dashboard",
    brief: "brief",
    alerts: "alerts",
    stories: "stories",
    story: "story",
    map: "map",
    travel: "travel",
    regional: "regional",
    regulatory: "regulatory",
    supply: "supply",
    cyber: "cyber",
    saved: "saved",
    learn: "learn",
    transparency: "transparency",
    settings: "settings",
    search: "search",
  };

  function render() {
    const { parts, params } = parseHash();
    const key = parts[0] || "dashboard";
    const viewName = ROUTES[key] || "dashboard";
    if (key === "story" && parts[1]) params.id = parts[1];

    // active nav
    const navKey = ({ story: "stories", search: "stories" })[viewName] || viewName;
    navLinks.forEach((a) => a.classList.toggle("active", a.dataset.nav === navKey));

    // build view
    const builder = Views[viewName] || Views.dashboard;
    viewEl.innerHTML = "";
    try {
      viewEl.appendChild(builder(params));
    } catch (e) {
      viewEl.appendChild(C.empty("View error: " + e.message));
    }
    document.getElementById("main").focus();
    window.scrollTo(0, 0);
    document.body.classList.remove("nav-open");
  }

  // ---------- init ----------
  async function init() {
    applyTheme(API.state.theme);
    populateTz();
    startClock();

    try {
      API.state.meta = await API.meta();
    } catch (e) {
      viewEl.appendChild(C.empty("Could not reach the API: " + e.message));
      return;
    }

    // demo banner + system status
    const mode = API.state.meta.data_mode;
    document.getElementById("modeBadge").textContent =
      mode.toUpperCase() + " · " + API.state.meta.ai_provider;
    document.getElementById("sysDot").className =
      "sf-dot " + (mode === "demo" ? "demo" : "live");
    // The top-bar pill states what the pipeline is doing, not what page you are
    // on — the one piece of chrome that is about the system itself.
    const pill = document.getElementById("statusPill");
    const isDemo = mode === "demo";
    pill.classList.toggle("is-demo", isDemo);
    document.getElementById("statusText").textContent =
      isDemo ? "DEMO DATA" : "INTELLIGENCE ACTIVE";
    // Narrow screens show an abbreviation instead: the full label pushed the
    // pill past the right edge of a 375px viewport.
    document.getElementById("statusTextShort").textContent = isDemo ? "DEMO" : "LIVE";
    pill.title = isDemo
      ? "Illustrative scenarios — not current news"
      : "Live feeds ingesting · analyzer: " + API.state.meta.ai_provider;
    // Only pure demo mode is "not current news". Hybrid/live serve real feeds.
    if (mode === "demo") {
      document.getElementById("demoBanner").hidden = false;
      document.body.classList.add("has-banner");
    }

    // alert badge — count of UNSEEN critical alerts (clears once viewed)
    await refreshAlertBadge();

    window.addEventListener("hashchange", render);
    render();
  }

  // Badge shows how many critical alerts the visitor hasn't seen yet. The
  // Alerts view marks them seen and calls this again to clear the badge.
  async function refreshAlertBadge() {
    try {
      const a = await API.alerts();
      const b = document.getElementById("alertBadge");
      const n = API.alertsSeen.unseen(a.alerts).length;
      if (n) { b.textContent = String(n); b.hidden = false; }
      else { b.hidden = true; }
    } catch {}
  }
  API.refreshAlertBadge = refreshAlertBadge;

  // ---------- theme ----------
  function applyTheme(t) {
    document.documentElement.setAttribute("data-theme", t);
    API.state.theme = t; API.LS.set("theme", t);
  }
  document.getElementById("themeToggle").addEventListener("click", () => {
    applyTheme(API.state.theme === "dark" ? "light" : "dark");
  });

  // ---------- timezone ----------
  function populateTz() {
    const sel = document.getElementById("tzSelect");
    let zones = ["UTC", "America/New_York", "America/Chicago", "America/Los_Angeles",
      "America/Mexico_City", "America/Sao_Paulo", "Europe/London", "Europe/Paris",
      "Europe/Berlin", "Europe/Budapest", "Africa/Nairobi", "Asia/Dubai", "Asia/Kolkata",
      "Asia/Singapore", "Asia/Shanghai", "Asia/Tokyo", "Australia/Sydney"];
    if (!zones.includes(API.state.tz)) zones.unshift(API.state.tz);
    zones.forEach((z) => {
      const o = document.createElement("option");
      o.value = z; o.textContent = z; if (z === API.state.tz) o.selected = true;
      sel.appendChild(o);
    });
    sel.addEventListener("change", (e) => {
      API.state.tz = e.target.value; API.LS.set("tz", e.target.value);
      render();
    });
  }

  function startClock() {
    const el = document.getElementById("clock");
    function tick() {
      const now = new Date();
      try {
        const t = new Intl.DateTimeFormat("en-GB",
          { hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: API.state.tz }).format(now);
        // Zone abbreviation matters here: analysts read event times across
        // zones, and a bare clock invites the wrong assumption about which.
        const parts = new Intl.DateTimeFormat("en-GB",
          { timeZone: API.state.tz, timeZoneName: "short" }).formatToParts(now);
        const zone = (parts.find((x) => x.type === "timeZoneName") || {}).value || "";
        // Seconds are wrapped so the narrow layout can drop them without
        // losing the reading; the title always carries the full time and zone.
        const cut = t.lastIndexOf(":");
        el.textContent = "";
        el.appendChild(document.createTextNode(cut > 0 ? t.slice(0, cut) : t));
        if (cut > 0) {
          const sec = document.createElement("span");
          sec.className = "sec";
          sec.textContent = t.slice(cut);
          el.appendChild(sec);
        }
        el.title = t + " " + zone + " (" + API.state.tz + ")";
      } catch { el.textContent = now.toISOString().slice(11, 19); el.title = "UTC"; }
    }
    tick(); setInterval(tick, 1000);
  }

  // ---------- search ----------
  document.getElementById("searchForm").addEventListener("submit", (e) => {
    e.preventDefault();
    const q = document.getElementById("searchInput").value.trim();
    if (q) location.hash = "#/search?q=" + encodeURIComponent(q);
  });

  // ---------- nav toggle ----------
  // Two behaviours behind one control: on a wide screen it collapses the rail
  // to icons (and the choice persists, because an operator sets it once); on a
  // narrow one the rail is off-canvas, so it opens and closes instead.
  const NARROW = "(max-width: 1024px)";
  function isNarrow() { return window.matchMedia(NARROW).matches; }

  if (API.LS.get("navCollapsed") === "1") document.body.classList.add("nav-collapsed");

  document.getElementById("menuToggle").addEventListener("click", (e) => {
    if (isNarrow()) {
      document.body.classList.toggle("nav-open");
      e.currentTarget.setAttribute("aria-expanded", document.body.classList.contains("nav-open"));
    } else {
      const collapsed = document.body.classList.toggle("nav-collapsed");
      API.LS.set("navCollapsed", collapsed ? "1" : "0");
      e.currentTarget.setAttribute("aria-expanded", String(!collapsed));
    }
  });
  // Leaving narrow width must not strand the drawer class on a desktop layout.
  window.matchMedia(NARROW).addEventListener("change", () => {
    document.body.classList.remove("nav-open");
  });

  // ---------- modal close ----------
  document.getElementById("modalHost").addEventListener("click", (e) => {
    if (e.target.hasAttribute("data-close")) document.getElementById("modalHost").hidden = true;
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") document.getElementById("modalHost").hidden = true;
  });

  init();
})();
