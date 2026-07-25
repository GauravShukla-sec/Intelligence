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

    // demo banner + mode badge
    const mode = API.state.meta.data_mode;
    const badge = document.getElementById("modeBadge");
    badge.textContent = "Mode: " + mode + " · AI: " + API.state.meta.ai_provider;
    badge.className = "mode-badge " + (mode === "demo" ? "demo" : mode === "live" ? "live" : "");
    // Only pure demo mode is "not current news". Hybrid/live serve real feeds.
    if (mode === "demo") {
      document.getElementById("demoBanner").hidden = false;
      document.body.classList.add("has-banner");
    }

    // alert badge
    try {
      const a = await API.alerts();
      const b = document.getElementById("alertBadge");
      if (a.alerts.length) { b.textContent = a.alerts.length; b.hidden = false; }
    } catch {}

    window.addEventListener("hashchange", render);
    render();
  }

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
      try {
        el.textContent = new Intl.DateTimeFormat("en-GB", { timeStyle: "medium", timeZone: API.state.tz }).format(new Date());
      } catch { el.textContent = new Date().toISOString().slice(11, 19) + "Z"; }
    }
    tick(); setInterval(tick, 1000);
  }

  // ---------- search ----------
  document.getElementById("searchForm").addEventListener("submit", (e) => {
    e.preventDefault();
    const q = document.getElementById("searchInput").value.trim();
    if (q) location.hash = "#/search?q=" + encodeURIComponent(q);
  });

  // ---------- nav toggle (mobile) ----------
  document.getElementById("menuToggle").addEventListener("click", (e) => {
    document.body.classList.toggle("nav-open");
    e.currentTarget.setAttribute("aria-expanded", document.body.classList.contains("nav-open"));
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
