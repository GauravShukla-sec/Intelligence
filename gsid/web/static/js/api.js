/* API client + shared state + small utilities. No framework, no build step. */
(function () {
  "use strict";

  const API = {};

  // --- persisted client state (localStorage) ---
  const LS = {
    get(k, def) { try { return JSON.parse(localStorage.getItem("gsid:" + k)) ?? def; } catch { return def; } },
    set(k, v) { try { localStorage.setItem("gsid:" + k, JSON.stringify(v)); } catch {} },
  };
  API.LS = LS;

  API.state = {
    meta: null,
    tz: LS.get("tz", Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"),
    theme: LS.get("theme", "dark"),
    quizStats: LS.get("quizStats", { asked: 0, correct: 0 }),
    token: LS.get("token", ""),
  };

  async function req(path, opts) {
    opts = opts || {};
    const headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
    if (API.state.token) headers["X-GSID-Token"] = API.state.token;
    const res = await fetch(path, Object.assign({}, opts, { headers }));
    if (res.status === 429) throw new Error("Rate limited — please wait a moment.");
    if (res.status === 401) throw new Error("Unauthorized — set an access token in Settings.");
    const ct = res.headers.get("content-type") || "";
    if (!res.ok) {
      let msg = "Request failed (" + res.status + ")";
      if (ct.includes("json")) { try { msg = (await res.json()).error || msg; } catch {} }
      throw new Error(msg);
    }
    if (ct.includes("application/json")) return res.json();
    return res.text();
  }
  API.req = req;

  API.get = (p) => req(p);
  API.meta = () => req("/api/meta");
  API.stories = (qs, opts) => req("/api/stories" + (qs ? "?" + qs : ""), opts);
  API.story = (id) => req("/api/stories/" + encodeURIComponent(id));
  API.challenge = (id) => req("/api/stories/" + encodeURIComponent(id) + "/challenge");
  API.brief = () => req("/api/brief");
  API.alerts = () => req("/api/alerts");

  // Per-visitor "seen" tracking for the Critical Alerts badge (localStorage).
  // An alert's signature includes last_updated, so a re-fired/updated alert
  // becomes unseen again.
  API.alertsSeen = {
    KEY: "seen_alerts",
    sig(a) { return (a.id || "") + "|" + (a.last_updated || ""); },
    _set() { return new Set(LS.get(this.KEY, [])); },
    markSeen(alerts) {
      const s = this._set();
      (alerts || []).forEach((a) => s.add(this.sig(a)));
      LS.set(this.KEY, Array.from(s));
    },
    unseen(alerts) {
      const s = this._set();
      return (alerts || []).filter((a) => !s.has(this.sig(a)));
    },
  };
  API.regional = () => req("/api/regional");
  API.advisoryChanges = (days) => req("/api/advisory-changes" + (days ? "?days=" + days : ""));
  API.regulations = () => req("/api/regulations");
  API.mapData = () => req("/api/map");
  API.search = (q) => req("/api/search?q=" + encodeURIComponent(q));
  API.travel = (country, origin) => req("/api/travel?country=" + encodeURIComponent(country)
    + (origin ? "&origin=" + encodeURIComponent(origin) : ""));
  API.feedHealth = () => req("/api/feeds/health");
  API.preferences = () => req("/api/preferences");
  API.savePreferences = (obj) => req("/api/preferences", { method: "PUT", body: JSON.stringify(obj) });
  // Saved stories are per-visitor and live in THIS browser (localStorage), so
  // the public/read-only deployment works with no login and no shared state.
  API.savedLocal = {
    all() { return LS.get("saved", []); },
    has(id) { return this.all().some((x) => x.story_id === id); },
    add(id, note) {
      const a = this.all();
      if (!a.some((x) => x.story_id === id)) {
        a.unshift({ story_id: id, note: note || "", saved_at: new Date().toISOString() });
        LS.set("saved", a);
      }
    },
    remove(id) { LS.set("saved", this.all().filter((x) => x.story_id !== id)); },
    toggle(id) { this.has(id) ? this.remove(id) : this.add(id); return this.has(id); },
  };
  API.quiz = (level) => req("/api/quiz" + (level ? "?level=" + level : ""));
  API.quizAnswer = (qid, idx) => req("/api/quiz/answer", { method: "POST", body: JSON.stringify({ question_id: qid, choice_index: idx }) });
  API.scenario = (id) => req("/api/scenario/" + encodeURIComponent(id));
  API.scenarios = () => req("/api/scenarios");
  API.exportStory = (id, kind) => req("/api/stories/" + encodeURIComponent(id) + "/export?kind=" + kind, { method: "POST" });
  API.audit = () => req("/api/audit");
  API.ingest = () => req("/api/ingest", { method: "POST" });

  // --- time helpers (UTC internal -> selected tz display) ---
  API.fmtTime = function (iso, tz) {
    if (!iso) return "—";
    tz = tz || API.state.tz;
    try {
      const d = new Date(iso);
      return new Intl.DateTimeFormat("en-GB", {
        dateStyle: "medium", timeStyle: "short", timeZone: tz,
      }).format(d);
    } catch { return iso; }
  };
  API.relTime = function (iso) {
    if (!iso) return "";
    const d = new Date(iso), now = new Date();
    const s = (now - d) / 1000;
    if (s < 60) return "just now";
    if (s < 3600) return Math.floor(s / 60) + "m ago";
    if (s < 86400) return Math.floor(s / 3600) + "h ago";
    return Math.floor(s / 86400) + "d ago";
  };

  window.GSID_API = API;
})();
