/* Onglet segmentation : images composées dans le navigateur (frame + masques), curseur temporel, lecture.
 *
 * Les frames et les cartes de labels sont des fichiers statiques (app_data/media/seg/) : le serveur ne
 * calcule rien. La lecture ne passe à la frame suivante qu'une fois la frame courante dessinée, et charge
 * les suivantes d'avance : sur un réseau lent elle ralentit au lieu de geler.
 */
(function () {
  "use strict";

  // Constantes et utilitaires ---------------------------------------------------------------------
  const N_FRAMES = 164; // = data.N_SEG_FRAMES
  const SIZE = 512; // résolution des frames et des cartes de labels
  const PREFETCH = 6; // frames chargées d'avance
  const CACHE_MAX = 80; // images décodées gardées en mémoire (environ 50 Mo au plus)
  const CLASS_IDS = { w: 1, p: 2, s: 3 };
  const DIFF = 4; // indice de couleur des désaccords (palette envoyée par tabs/segmentation.py)
  const nf = (v, d) => Number(v).toLocaleString("fr-FR", { minimumFractionDigits: d, maximumFractionDigits: d });

  // Demande en cours (token) et dernière demande entièrement dessinée.
  const state = { token: 0, drawn: -1 };

  function fileUrl(run, kind, k) {
    const name = String(k).padStart(3, "0") + (kind === "frames" ? ".webp" : ".png");
    return "/media/seg/" + encodeURIComponent(run) + "/" + kind + "/" + name;
  }

  function withCursor(fig, x, color) {
    if (!fig) return window.dash_clientside.no_update;
    const cursor = { type: "line", xref: "x", yref: "paper", x0: x, x1: x, y0: 0, y1: 1, line: { color, width: 1 } };
    return { data: fig.data, layout: Object.assign({}, fig.layout, { shapes: [cursor] }) };
  }

  // Chargement des images, avec un cache borné (les plus anciennes sont oubliées) -----------------
  const cache = new Map(); // url -> Promise<Uint8ClampedArray> (RGBA pour une frame, R pour une carte)

  function load(url, labels) {
    if (cache.has(url)) {
      const hit = cache.get(url);
      cache.delete(url); // remis en fin de file : récemment utilisé
      cache.set(url, hit);
      return hit;
    }
    const promise = new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement("canvas");
        canvas.width = SIZE;
        canvas.height = SIZE;
        const ctx = canvas.getContext("2d", { willReadFrequently: true });
        ctx.drawImage(img, 0, 0, SIZE, SIZE);
        const rgba = ctx.getImageData(0, 0, SIZE, SIZE).data;
        if (!labels) return resolve(rgba);
        const ids = new Uint8Array(SIZE * SIZE); // carte de labels : un octet par pixel (canal rouge)
        for (let i = 0; i < ids.length; i++) ids[i] = rgba[4 * i];
        resolve(ids);
      };
      img.onerror = () => {
        cache.delete(url);
        reject(new Error("image indisponible : " + url));
      };
      img.src = url;
    });
    cache.set(url, promise);
    while (cache.size > CACHE_MAX) cache.delete(cache.keys().next().value);
    return promise;
  }

  function prefetch(run, k) {
    for (let j = 1; j <= PREFETCH; j++) {
      const n = (k + j) % N_FRAMES;
      load(fileUrl(run, "frames", n), false).catch(() => {});
      load(fileUrl(run, "gt", n), true).catch(() => {});
      load(fileUrl(run, "pred", n), true).catch(() => {});
    }
  }

  // Composition : remplissage semi-transparent + contour plein, comme les vidéos IA ----------------
  // cls : indice de couleur par pixel (0 = rien), calculé selon la vue.
  function paint(canvasId, base, cls, palette, alpha) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const out = new ImageData(new Uint8ClampedArray(base), SIZE, SIZE);
    const px = out.data;
    for (let i = 0; i < cls.length; i++) {
      const c = cls[i];
      if (!c) continue;
      const x = i % SIZE;
      const edge =
        (x > 0 && cls[i - 1] !== c) ||
        (x < SIZE - 1 && cls[i + 1] !== c) ||
        (i >= SIZE && cls[i - SIZE] !== c) ||
        (i < cls.length - SIZE && cls[i + SIZE] !== c);
      const col = palette[c];
      const a = edge ? 1 : alpha;
      const o = 4 * i;
      px[o] = px[o] + (col[0] - px[o]) * a;
      px[o + 1] = px[o + 1] + (col[1] - px[o + 1]) * a;
      px[o + 2] = px[o + 2] + (col[2] - px[o + 2]) * a;
    }
    canvas.getContext("2d").putImageData(out, 0, 0);
  }

  // Classes cochées d'une carte de labels.
  function classMap(ids, checked) {
    const cls = new Uint8Array(ids.length);
    for (let i = 0; i < ids.length; i++) if (checked[ids[i]]) cls[i] = ids[i];
    return cls;
  }

  // Désaccords : les deux cartes diffèrent ET l'une d'elles porte une classe cochée.
  function diffMap(gt, pred, checked) {
    const cls = new Uint8Array(gt.length);
    for (let i = 0; i < gt.length; i++) {
      if (gt[i] !== pred[i] && (checked[gt[i]] || checked[pred[i]])) cls[i] = DIFF;
    }
    return cls;
  }

  async function draw(token, run, k, view, keys, alpha, palette) {
    const [frame, gt, pred] = await Promise.all([
      load(fileUrl(run, "frames", k), false),
      load(fileUrl(run, "gt", k), true),
      load(fileUrl(run, "pred", k), true),
    ]);
    if (token !== state.token) return; // une demande plus récente est arrivée entre-temps
    // Aucune classe cochée : frames seules à gauche, désaccords sur toutes les classes à droite.
    const checked = {};
    (keys.length ? keys : ["w", "p", "s"]).forEach((key) => (checked[CLASS_IDS[key]] = true));
    const none = new Uint8Array(gt.length);
    paint("seg-img-a", frame, keys.length ? classMap(gt, checked) : none, palette, alpha);
    const right = view === "diff" ? diffMap(gt, pred, checked) : keys.length ? classMap(pred, checked) : none;
    paint("seg-img-b", frame, right, palette, alpha);
    state.drawn = token;
    prefetch(run, k);
  }

  // Fonctions appelées par Dash : ClientsideFunction("seg", ...) dans tabs/segmentation.py --------
  window.dash_clientside = Object.assign({}, window.dash_clientside, {
    seg: {
      render: function (run, view, k, classes, alpha, figs) {
        k = Math.max(0, Math.min(N_FRAMES - 1, k | 0));
        if (figs && run) {
          state.token += 1;
          draw(state.token, run, k, view, classes || [], (alpha || 55) / 100, figs.overlay).catch(() => {});
        }
        // À gauche l'annotation ; à droite la prédiction ou la carte des désaccords.
        const capA = "Annotation (SAM2 + relecture humaine)";
        const capB =
          view === "diff" ? "Désaccords : pixels où annotation et modèle divergent" : "Prédiction du modèle U-Net";
        const t = figs ? figs.t_ms[k] : null;
        const label = figs ? "t = " + nf(t, 2) + " ms · frame " + (figs.frames[k] + 1) : "";
        return [
          capA,
          capB,
          {},
          label,
          figs ? withCursor(figs.areas, t, figs.muted) : window.dash_clientside.no_update,
          figs ? withCursor(figs.iou, t, figs.muted) : window.dash_clientside.no_update,
        ];
      },

      togglePlay: function (_n, disabled) {
        return disabled ? [false, "Pause"] : [true, "Lecture"];
      },

      // Frame suivante seulement quand la précédente est affichée : la lecture suit le réseau.
      advance: function (_n, k) {
        if (state.drawn !== state.token) return window.dash_clientside.no_update;
        return ((k | 0) + 1) % N_FRAMES;
      },
    },
  });
})();
