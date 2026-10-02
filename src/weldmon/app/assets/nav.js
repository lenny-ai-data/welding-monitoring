/* Navigation latérale : une section visible à la fois, lien profond via #ancre, barre repliable
 * (icônes seules, préférence mémorisée dans le navigateur), menu burger sur mobile. */
(function () {
  "use strict";

  const KEYS = ["process", "suivi", "analyses", "seg", "about"]; // même ordre que SECTIONS (app/__init__.py)
  const DEFAULT = "process"; // = DEFAULT_SECTION
  const WIDTH = { expanded: 240, collapsed: 72 }; // = NAV_WIDTH
  const STORAGE_KEY = "weldmon-nav-collapsed";
  let current = null;
  let collapsed = null;

  function fromHash() {
    const key = window.location.hash.replace("#", "");
    return KEYS.includes(key) ? key : DEFAULT;
  }

  function readCollapsed() {
    try {
      return window.localStorage.getItem(STORAGE_KEY) === "1";
    } catch (e) {
      return false; // stockage indisponible (navigation privée...) : barre dépliée
    }
  }

  function saveCollapsed(value) {
    try {
      window.localStorage.setItem(STORAGE_KEY, value ? "1" : "0");
    } catch (e) {
      /* préférence non mémorisée, sans conséquence */
    }
  }

  function go(key) {
    current = key;
    if (window.location.hash !== "#" + current) {
      window.history.replaceState(null, "", "#" + current);
    }
    window.scrollTo({ top: 0 });
  }

  // Soudure ouverte depuis le suivi : si elle est déjà chargée dans le lecteur, on la relance ici ;
  // sinon le chargement du run s'en charge (drapeau window.weldAutoplay).
  function playIfLoaded(run) {
    const v = document.getElementById("live-video");
    if (!v || !run || !window.weldAutoplay) return;
    if ((v.getAttribute("src") || "").indexOf("/" + run + "_") !== -1 || (v.getAttribute("src") || "").endsWith("/" + run + ".mp4")) {
      window.weldAutoplay = false;
      if (v.ended) v.currentTime = 0;
      v.play().catch(() => {});
    }
  }

  // Mise à l'échelle du canevas (voir .canvas / .sections dans style.css) : référence 1920 × 1080,
  // barre dépliée. La hauteur réservée suit le contenu (bandeau d'explications ouvert, changement de page).
  const DESIGN = { width: 1920 - WIDTH.expanded - 32, height: 1080 - 32 }; // hors marges de l'AppShell (16 px)
  let observer = null;
  function applyFit() {
    const root = document.documentElement;
    const canvas = document.getElementById("canvas");
    const content = canvas && canvas.firstElementChild;
    if (!canvas || !content) return;
    let fit = 1;
    let cx = 0;
    if (window.innerWidth >= 1200) {
      const nav = collapsed ? WIDTH.collapsed : WIDTH.expanded;
      fit = Math.min((window.innerHeight - 32) / DESIGN.height, (window.innerWidth - nav - 32) / DESIGN.width);
      cx = Math.max(0, (canvas.clientWidth - DESIGN.width * fit) / 2);
      root.style.setProperty("--canvas-h", Math.ceil(content.offsetHeight * fit) + "px");
    } else {
      root.style.removeProperty("--canvas-h");
    }
    root.style.setProperty("--fit", fit.toFixed(4));
    root.style.setProperty("--cx", cx.toFixed(1) + "px");
    if (!observer && window.ResizeObserver) {
      observer = new ResizeObserver(() => scheduleFit());
      observer.observe(content);
      observer.observe(canvas);
    }
  }
  let fitFrame = null;
  function scheduleFit() {
    if (fitFrame) window.cancelAnimationFrame(fitFrame);
    fitFrame = window.requestAnimationFrame(applyFit);
  }
  window.addEventListener("resize", scheduleFit);

  window.dash_clientside = Object.assign({}, window.dash_clientside, {
    nav: {
      route: function (_clicks, burgerOpened, _collapseClicks, goto, navbar) {
        const ctx = window.dash_clientside.callback_context;
        const trig = ctx && ctx.triggered_id;
        let opened = Boolean(burgerOpened);

        if (current === null) current = fromHash();
        if (collapsed === null) collapsed = readCollapsed();

        if (trig === "nav-collapse") {
          collapsed = !collapsed;
          saveCollapsed(collapsed);
        } else if (trig && typeof trig === "object" && trig.type === "nav") {
          go(trig.index);
          opened = false; // sur mobile, le menu se referme après un choix
        } else if (trig === "goto" && goto && KEYS.includes(goto.section)) {
          go(goto.section);
          playIfLoaded(goto.run);
        }

        // Quitter le monitoring met la vidéo en pause (pas de lecture invisible en arrière-plan).
        if (current !== "process") {
          const v = document.getElementById("live-video");
          if (v && !v.paused) v.pause();
        }

        scheduleFit();
        const styles = KEYS.map((k) => (k === current ? {} : { display: "none" }));
        const nav = Object.assign({}, navbar, {
          width: collapsed ? WIDTH.collapsed : WIDTH.expanded,
          collapsed: Object.assign({}, (navbar && navbar.collapsed) || {}, { mobile: !opened }),
        });
        // Les graphes Plotly suivent la nouvelle largeur du contenu.
        window.setTimeout(() => window.dispatchEvent(new Event("resize")), 280); // après la transition (240 ms)
        return [
          ...styles,
          KEYS.map((k) => k === current),
          KEYS.map(() => !collapsed),
          !collapsed,
          nav,
          collapsed ? "app-shell nav-collapsed" : "app-shell",
          opened,
        ];
      },
    },
  });
})();
