/* Service-worker registration (offline + installable).
 *
 * This lived as an inline <script> in index.html, where the app's own
 * Content-Security-Policy (script-src 'self') blocked it on every load — so the
 * offline cache and install prompt had never once worked in production. An
 * external file is same-origin and therefore allowed.
 *
 * Progressive: if the browser lacks support, or registration fails, the app
 * behaves exactly as before.
 */
if ("serviceWorker" in navigator) {
      window.addEventListener("load", function () {
        navigator.serviceWorker.register("/sw.js").then(function (reg) {
          // A new version is waiting: activate it so the next load is current.
          if (reg.waiting) reg.waiting.postMessage("skipWaiting");
          reg.addEventListener("updatefound", function () {
            var sw = reg.installing;
            if (!sw) return;
            sw.addEventListener("statechange", function () {
              if (sw.state === "installed" && navigator.serviceWorker.controller) {
                sw.postMessage("skipWaiting");
              }
            });
          });
        }).catch(function () { /* offline support is optional */ });
      });
    }
