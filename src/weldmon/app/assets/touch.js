/* Tactile : rattrapage des touchers dont Safari iOS n'envoie pas le clic.
 *
 * Après un toucher, Safari iOS observe la page un court instant : si du contenu y apparaît, il croit avoir
 * ouvert un menu au survol et n'envoie pas le clic. Pendant une lecture (vidéo du monitoring, frames de la
 * segmentation), la page change en continu (courbes, HUD, curseurs) : le premier toucher d'un bouton
 * n'aboutit alors souvent à rien et seul le second clique. Les événements
 * pointer, eux, arrivent toujours : un toucher franc (sans glisser, ni appui long) non suivi d'un clic
 * natif dans DELAY_MS déclenche ce clic. Un clic natif tardif sur le même élément est alors ignoré,
 * pour ne jamais agir deux fois. Sans effet à la souris et au clavier.
 */
(function () {
  "use strict";

  // Constantes et état ----------------------------------------------------------------------------
  const TARGETS =
    'button, a[href], label, summary, video, [role="button"], [role="tab"], [role="switch"], [role="checkbox"], [role="radio"]';
  const DELAY_MS = 350; // attente du clic natif avant de le déclencher nous-mêmes
  const GUARD_MS = 800; // fenêtre où un clic natif tardif est ignoré
  const SLOP_PX = 10; // déplacement au-delà duquel le geste est un défilement
  const LONG_MS = 700; // appui long : menu contextuel, pas un clic

  let touch = null; // toucher en cours : { id, el, x, y, t }
  let pending = null; // clic attendu après un toucher : { el, timer }
  let guard = null; // clic déclenché par ce script : { el, until }

  function disabled(el) {
    return el.matches(":disabled") || el.getAttribute("aria-disabled") === "true";
  }

  // Suivi du toucher ------------------------------------------------------------------------------
  document.addEventListener(
    "pointerdown",
    (e) => {
      touch = null;
      if (e.pointerType !== "touch" || !e.isPrimary) return;
      const el = e.target.closest && e.target.closest(TARGETS);
      if (el && !disabled(el)) touch = { id: e.pointerId, el, x: e.clientX, y: e.clientY, t: e.timeStamp };
    },
    { capture: true, passive: true }
  );

  document.addEventListener(
    "pointermove",
    (e) => {
      if (touch && e.pointerId === touch.id && Math.hypot(e.clientX - touch.x, e.clientY - touch.y) > SLOP_PX) {
        touch = null;
      }
    },
    { capture: true, passive: true }
  );

  document.addEventListener("pointercancel", () => (touch = null), { capture: true, passive: true });

  document.addEventListener(
    "pointerup",
    (e) => {
      const t = touch;
      touch = null;
      if (!t || e.pointerId !== t.id || e.timeStamp - t.t > LONG_MS) return;
      if (pending) window.clearTimeout(pending.timer);
      const el = t.el;
      pending = {
        el,
        timer: window.setTimeout(() => {
          pending = null;
          if (!el.isConnected || disabled(el)) return;
          guard = { el, until: performance.now() + GUARD_MS };
          el.click();
        }, DELAY_MS),
      };
    },
    { capture: true, passive: true }
  );

  // Clic natif : il annule le rattrapage, ou il est ignoré s'il arrive après lui ------------------
  document.addEventListener(
    "click",
    (e) => {
      if (!e.isTrusted) return; // clic déclenché par ce script
      if (pending && pending.el.contains(e.target)) {
        window.clearTimeout(pending.timer);
        pending = null;
      } else if (guard && guard.el.contains(e.target) && performance.now() < guard.until) {
        guard = null;
        e.preventDefault();
        e.stopImmediatePropagation();
      }
    },
    true
  );
})();
