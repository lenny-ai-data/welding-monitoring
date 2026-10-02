/* Onglet segmentation : URL des images composées + curseur temporel, sans aller-retour serveur. */
(function () {
  "use strict";

  const N_FRAMES = 164;
  const nf = (v, d) => Number(v).toLocaleString("fr-FR", { minimumFractionDigits: d, maximumFractionDigits: d });

  function url(run, k, src, cls, alpha) {
    const q = new URLSearchParams({ src, cls, a: String(alpha) });
    return "/overlay/" + encodeURIComponent(run) + "/" + k + ".jpg?" + q.toString();
  }

  function withCursor(fig, x, color) {
    if (!fig) return window.dash_clientside.no_update;
    const cursor = { type: "line", xref: "x", yref: "paper", x0: x, x1: x, y0: 0, y1: 1, line: { color, width: 1 } };
    return { data: fig.data, layout: Object.assign({}, fig.layout, { shapes: [cursor] }) };
  }

  window.dash_clientside = Object.assign({}, window.dash_clientside, {
    seg: {
      render: function (run, view, k, classes, alpha, figs) {
        const cls = (classes || []).join("") || "none";
        const show = cls === "none" ? "none" : null;
        k = Math.max(0, Math.min(N_FRAMES - 1, k | 0));
        let a, b, capA, capB;
        if (view === "compare") {
          a = url(run, k, show || "gt", cls === "none" ? "wps" : cls, alpha);
          b = url(run, k, show || "pred", cls === "none" ? "wps" : cls, alpha);
          capA = "Annotation (SAM2 + relecture humaine)";
          capB = "Prédiction du modèle U-Net";
        } else {
          const src = show || view;
          a = url(run, k, src, cls === "none" ? "wps" : cls, alpha);
          b = "";
          capA = {
            gt: "Annotation (SAM2 + relecture humaine)",
            pred: "Prédiction du modèle U-Net",
            diff: "Pixels où annotation et modèle divergent",
          }[view];
          capB = "";
        }
        const t = figs ? figs.t_ms[k] : null;
        const label = figs ? "t = " + nf(t, 2) + " ms · frame " + (figs.frames[k] + 1) : "";
        return [
          a, b, capA, capB,
          view === "compare" ? {} : { display: "none" },
          label,
          figs ? withCursor(figs.areas, t, figs.muted) : window.dash_clientside.no_update,
          figs ? withCursor(figs.iou, t, figs.muted) : window.dash_clientside.no_update,
        ];
      },

      togglePlay: function (_n, disabled) {
        return disabled ? [false, "Pause"] : [true, "Lecture"];
      },

      advance: function (_n, k) {
        return ((k | 0) + 1) % N_FRAMES;
      },
    },
  });
})();
