/* Navigation latérale : une section visible à la fois, lien profond via #ancre, menu mobile. */
(function () {
  "use strict";

  const KEYS = ["live", "seg", "doe", "about"]; // même ordre que SECTIONS (app/__init__.py)
  let current = null;

  function fromHash() {
    const key = window.location.hash.replace("#", "");
    return KEYS.includes(key) ? key : "live";
  }

  window.dash_clientside = Object.assign({}, window.dash_clientside, {
    nav: {
      route: function (_clicks, burgerOpened, navbar) {
        const ctx = window.dash_clientside.callback_context;
        const trig = ctx && ctx.triggered_id;
        let opened = Boolean(burgerOpened);

        if (current === null) current = fromHash();
        if (trig && typeof trig === "object" && trig.type === "nav") {
          current = trig.index;
          opened = false; // sur mobile, le menu se referme après un choix
          if (window.location.hash !== "#" + current) {
            window.history.replaceState(null, "", "#" + current);
          }
          window.scrollTo({ top: 0 });
        }

        // Quitter le monitoring met la vidéo en pause (pas de lecture invisible en arrière-plan).
        if (current !== "live") {
          const v = document.getElementById("live-video");
          if (v && !v.paused) v.pause();
        }

        const styles = KEYS.map((k) => (k === current ? {} : { display: "none" }));
        const nav = Object.assign({}, navbar, {
          collapsed: Object.assign({}, (navbar && navbar.collapsed) || {}, { mobile: !opened }),
        });
        return [...styles, KEYS.map((k) => k === current), nav, opened];
      },
    },
  });
})();
