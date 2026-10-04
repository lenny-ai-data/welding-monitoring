/* Monitoring process : lecteur vidéo, synchronisation vidéo <-> signaux, entièrement côté client.
 *
 * La vidéo web contient une frame par frame caméra (30 im/s) : l'index de frame procédé est
 * floor(currentTime * 30). Une boucle autonome (100 ms) révèle les signaux jusqu'à cet index, en
 * mettant à jour directement les courbes (Plotly) et les cartes (DOM), sans passer par Dash : Dash ne
 * sert qu'à charger une soudure. La timeline du lecteur est animée à chaque image par requestAnimationFrame.
 */
(function () {
  "use strict";

  // État, constantes et utilitaires ---------------------------------------------------------------
  const state = {
    key: null, run: null, videoRun: null, idx: -1, chartsIdx: -1, nextCharts: 0, logKey: null,
    advancing: false, resume: null, swap: null, rate: 1, p: null,
  };
  const KPIS = ["integrity", "power", "speed"]; // cartes kpi-<clé> de tabs/process.py, dans l'ordre de kpis()
  const TICK_MS = 100; // pas de la boucle de relecture
  const CHART_SHARE = 3; // les courbes n'occupent au plus qu'un tiers du temps (cadence adaptée à la machine)
  const HOLD_MS = 3; // une alarme reste affichée 3 ms de procédé
  const nf = (v, d) =>
    v === null || v === undefined || Number.isNaN(v)
      ? "-"
      : Number(v)
          .toLocaleString("fr-FR", { minimumFractionDigits: d, maximumFractionDigits: d })
          .replace(/\u202f/g, "\u00a0"); // espace fine absente de la police Sora

  // Graphes des courbes, dans l'ordre de figures() (tabs/process.py, CHARTS).
  const CHART_IDS = ["live-plasma", "live-speed", "live-spatter", "live-weld"];
  const el = (type, props) => ({ type, namespace: "dash_html_components", props });
  const video = () => document.getElementById("live-video");
  const byId = (id) => document.getElementById(id);

  // Couleur des anneaux ---------------------------------------------------------------------------
  // Violet, puis doré entre 60 et 100 % de la limite, rouge au-delà d'un seuil d'alarme.
  function hex(h) {
    return [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
  }
  function mix(a, b, k) {
    const A = hex(a);
    const B = hex(b);
    return "rgb(" + A.map((v, i) => Math.round(v + (B[i] - v) * k)).join(", ") + ")";
  }
  function ringColor(c, r, alarm) {
    if (alarm) return c.alarm;
    return mix(c.ring, c.gold, Math.min(Math.max((r - 0.6) / 0.4, 0), 1));
  }
  const ring = (r, color) => ({ "--p": Math.round(Math.min(Math.max(r, 0), 1) * 1000) / 10, "--c": color });

  // Lecteur ---------------------------------------------------------------------------------------
  // Lecture / pause, recherche dans la timeline (souris, tactile, clavier).
  function togglePlay() {
    const v = video();
    if (!v) return;
    if (v.paused || v.ended) {
      if (v.ended) v.currentTime = 0;
      v.play().catch(() => {});
    } else {
      v.pause();
    }
  }

  function seekTo(fraction) {
    const v = video();
    if (!v || !v.duration) return;
    v.currentTime = Math.min(Math.max(fraction, 0), 0.9999) * v.duration;
  }

  let dragging = false;
  function seekFromPointer(e) {
    const track = document.getElementById("vp-track");
    if (!track) return;
    const box = track.getBoundingClientRect();
    seekTo((e.clientX - box.left) / box.width);
  }

  // Vitesse de lecture : ½×, 1×, 2× (bouton unique, compact).
  const RATES = [0.5, 1, 2];
  function cycleRate(btn) {
    state.rate = RATES[(RATES.indexOf(state.rate) + 1) % RATES.length];
    const v = video();
    if (v) v.playbackRate = state.rate;
    const label = (state.rate === 0.5 ? "½" : String(state.rate)) + "×";
    btn.textContent = label;
    btn.setAttribute("aria-label", "Vitesse de lecture : " + label);
  }

  document.addEventListener("click", (e) => {
    if (e.target.closest("#vp-play") || e.target.closest("#live-video")) togglePlay();
    const rate = e.target.closest("#vp-rate");
    if (rate) cycleRate(rate);
  });
  document.addEventListener("pointerdown", (e) => {
    if (!e.target.closest("#vp-track")) return;
    dragging = true;
    seekFromPointer(e);
  });
  document.addEventListener("pointermove", (e) => dragging && seekFromPointer(e));
  document.addEventListener("pointerup", () => (dragging = false));
  document.addEventListener("keydown", (e) => {
    if (!e.target || e.target.id !== "vp-track") return;
    const v = video();
    if (!v || !v.duration) return;
    const f = v.currentTime / v.duration;
    const moves = { ArrowLeft: f - 0.02, ArrowRight: f + 0.02, Home: 0, End: 1 };
    if (e.key in moves) {
      seekTo(moves[e.key]);
      e.preventDefault();
    } else if (e.key === " " || e.key === "Enter") {
      togglePlay();
      e.preventDefault();
    }
  });

  // Changement de source sans à-coup --------------------------------------------------------------
  // Basculer les masques recharge la vidéo, qui repart de 0 le temps de se repositionner : la frame
  // courante reste affichée (canevas vp-freeze) et le rendu est gelé jusqu'à ce que la nouvelle source
  // montre la même image. Cartes, courbes et timeline ne bougent donc pas.
  const SWAP_MAX_MS = 5000; // garde-fou : source qui ne charge pas

  function startSwap(v) {
    const freeze = byId("vp-freeze");
    if (!state.swap && freeze && v.readyState >= 2 && v.videoWidth) {
      freeze.width = v.videoWidth;
      freeze.height = v.videoHeight;
      freeze.getContext("2d").drawImage(v, 0, 0);
      freeze.classList.add("is-on");
    }
    if (state.swap) window.clearTimeout(state.swap.timer);
    state.swap = { seek: false, timer: window.setTimeout(endSwap, SWAP_MAX_MS) };
  }

  function endSwap() {
    if (!state.swap) return;
    window.clearTimeout(state.swap.timer);
    state.swap = null;
    const freeze = byId("vp-freeze");
    if (freeze) freeze.classList.remove("is-on");
  }

  // Fin du changement une fois la nouvelle image affichée (et non seulement décodée).
  function endSwapAfterFrame(v) {
    let done = false;
    const once = () => {
      if (done) return;
      done = true;
      endSwap();
    };
    if (v.requestVideoFrameCallback) v.requestVideoFrameCallback(once);
    window.setTimeout(once, 150);
  }

  // Synchronisation de la vidéo -------------------------------------------------------------------
  // Reprise de la position après changement de source (vidéo brute <-> masques IA) ou de run.
  document.addEventListener(
    "loadedmetadata",
    (e) => {
      const v = e.target;
      if (!v || v.id !== "live-video") return;
      v.playbackRate = state.rate;
      if (state.resume) {
        if (state.resume.t > 0) {
          if (state.swap) state.swap.seek = true;
          v.currentTime = Math.min(state.resume.t, v.duration - 0.01);
        }
        if (state.resume.play) v.play().catch(() => {});
        state.resume = null;
      }
    },
    true
  );
  ["loadeddata", "seeked", "error"].forEach((type) =>
    document.addEventListener(
      type,
      (e) => {
        const v = e.target;
        if (!v || v.id !== "live-video" || !state.swap) return;
        if (type === "error") endSwap();
        else if (type === "seeked" || !state.swap.seek) endSwapAfterFrame(v);
      },
      true
    )
  );

  // Timeline animée à chaque image (éléments sans sortie Dash : aucun conflit de rendu).
  function animate() {
    const v = video();
    const track = document.getElementById("vp-track");
    if (v && track && !state.swap) {
      const f = v.duration ? v.currentTime / v.duration : 0;
      const pct = (100 * Math.min(f, 1)).toFixed(2) + "%";
      const prog = document.getElementById("vp-progress");
      const head = document.getElementById("vp-head");
      const time = document.getElementById("vp-time");
      const play = document.getElementById("vp-play");
      if (prog) prog.style.width = pct;
      if (head) head.style.left = pct;
      track.setAttribute("aria-valuenow", Math.round(100 * f));
      if (time && state.p) {
        const p = state.p;
        const idx = Math.max(0, Math.min(p.n - 1, Math.floor(v.currentTime * p.playback_fps + 1e-3)));
        const txt = nf(p.ts.t_ms[idx], 1) + " / " + nf(p.duration, 1) + " ms";
        if (time.textContent !== txt) time.textContent = txt;
      }
      if (play) play.classList.toggle("is-playing", !v.paused && !v.ended);
    }
    window.requestAnimationFrame(animate);
  }
  window.requestAnimationFrame(animate);

  // Statut, cartes et courbes ---------------------------------------------------------------------
  function activeAlarms(p, idx) {
    const hold = Math.round((p.fps * HOLD_MS) / 1000);
    return p.events.filter((e) => e.start <= idx && idx <= e.end + hold && !["on", "off"].includes(e.type));
  }

  // Tir laser : uniquement « Tir en cours » ou « À l'arrêt ».
  function laserAt(p, idx) {
    const on = p.events.find((e) => e.type === "on");
    if (p.ts.on[idx]) {
      const since = on ? p.ts.t_ms[idx] - on.t_ms : null;
      return ["status-card is-firing", "Tir en cours", since != null ? "depuis " + nf(since, 1) + " ms" : ""];
    }
    const before = !on || idx < on.start;
    return ["status-card is-standby", "À l'arrêt", before ? "en attente d'allumage" : "soudure terminée"];
  }

  function kpis(p, idx, alarms) {
    const ts = p.ts;
    const c = p.colors;
    const L = p.limits;
    const on = Boolean(ts.on[idx]);
    const speed = ts.speed_mm_s[idx];
    const dev = speed != null ? (100 * (speed - p.setpoint.speed)) / p.setpoint.speed : null;
    const speedAlarm = alarms.some((e) => e.type === "speed_deviation");
    const rSpeed = dev != null ? Math.abs(dev) / L.speed_warn_pct : 0;

    // Intégrité : seuils franchis depuis l'allumage ; couleur selon les seuils du verdict.
    const past = p.events.filter((e) => e.start <= idx);
    const n = (type) => past.filter((e) => e.type === type).length;
    const plasma = n("plasma_spike");
    const bursts = n("spatter_burst");
    const speedDev = n("speed_deviation");
    const alarmsCount = plasma + bursts;
    const total = alarmsCount + speedDev;
    const integrityColor =
      speedDev || alarmsCount > L.warn_max ? c.alarm : alarmsCount > L.ok_max ? c.gold : c.ring;
    return [
      [String(total), plasma + " plasma · " + bursts + " projections · " + speedDev + " vitesse", ring(total / L.warn_max, integrityColor)],
      [on ? nf(p.setpoint.power, 0) : "0", on ? "consigne" : "laser coupé", ring(on ? 1 : 0, c.ring)],
      [
        speed != null ? nf(speed, 0) : "-",
        dev != null ? (dev >= 0 ? "+" : "−") + nf(Math.abs(dev), 0) + " % / consigne" : on ? "mesure en cours" : "à l'arrêt",
        ring(rSpeed, ringColor(c, rSpeed, speedAlarm)),
      ],
    ];
  }

  function figures(p, idx) {
    const ts = p.ts;
    const c = p.colors;
    const end = idx + 1;
    const x = ts.t_ms.slice(0, end);
    const cut = (s) => s.slice(0, end);
    const past = p.events.filter((e) => e.start <= idx);
    const tNow = ts.t_ms[idx];

    // Marqueurs d'événement : symbole sur la courbe + trait vertical (forme + couleur, jamais la couleur seule).
    function marks(type, series, color, symbol, name) {
      const ev = past.filter((e) => e.type === type);
      const shapes = ev.map((e) => ({
        type: "line", xref: "x", yref: "paper", x0: ts.t_ms[e.start], x1: ts.t_ms[e.start], y0: 0, y1: 1,
        layer: "below", line: { color, width: 1, dash: "dot" },
      }));
      const trace = ev.length
        ? {
            x: ev.map((e) => ts.t_ms[e.start]), y: ev.map((e) => series[e.start]), type: "scatter", mode: "markers",
            name, marker: { color, size: 10, symbol, line: { width: 1.5, color: c.surface } },
            hovertemplate: name + "<extra></extra>",
          }
        : null;
      return { shapes, trace };
    }
    const cursor = {
      type: "line", xref: "x", yref: "paper", x0: tNow, x1: tNow, y0: 0, y1: 1,
      line: { color: c.cursor, width: 1 }, opacity: 0.45,
    };
    function fig(key, traces, m) {
      const lay = p.layouts[key];
      const extra = m ? m.shapes : [];
      return {
        data: m && m.trace ? traces.concat([m.trace]) : traces,
        layout: Object.assign({}, lay, { shapes: lay.shapes.concat(extra, [cursor]) }),
      };
    }
    const line = (y, name, fmt, extra) =>
      Object.assign(
        { x, y, type: "scatter", mode: "lines", name, line: { color: c.line, width: 2 }, hovertemplate: fmt },
        extra || {}
      );

    return [
      fig(
        "plasma",
        [
          line(cut(ts.plasma_mm2), "image", "%{y:.1f} mm²", { line: { color: c.line_raw, width: 1 } }),
          line(cut(ts.plasma_smooth_mm2), "moyenne 2 ms", "%{y:.1f} mm² (moy.)"),
        ],
        marks("plasma_spike", ts.plasma_mm2, c.alarm, "triangle-up", "Pic de plasma")
      ),
      fig(
        "speed",
        [line(cut(ts.speed_mm_s), "mesurée", "%{y:.0f} mm/s", { connectgaps: false })],
        marks("speed_deviation", ts.speed_mm_s, c.alarm, "triangle-down", "Écart de vitesse")
      ),
      fig(
        "spatter",
        [
          line(cut(ts.spatter_n), "projections", "%{y} visibles", {
            line: { color: c.line, width: 1.4, shape: "hv" }, fill: "tozeroy", fillcolor: c.fill,
          }),
        ],
        marks("spatter_burst", ts.spatter_n, c.gold, "diamond", "Rafale de projections")
      ),
      fig("weld", [line(cut(ts.weld_length_mm), "cordon", "%{y:.1f} mm", { fill: "tozeroy", fillcolor: c.fill })]),
    ];
  }

  // Écriture directe dans la page ------------------------------------------------------------------
  // Les éléments ciblés sont créés par Dash (tabs/process.py) ; leur contenu n'est ensuite modifié que
  // par cette boucle, jamais par un callback Dash.
  function chartsReady() {
    if (!window.Plotly) return null;
    const gds = CHART_IDS.map((id) => document.querySelector("#" + id + " .js-plotly-plot"));
    return gds.every((g) => g && g._fullLayout) ? gds : null;
  }

  function node(tag, className, text) {
    const e = document.createElement(tag);
    if (className) e.className = className;
    if (text != null) e.textContent = text;
    return e;
  }

  function setText(id, text) {
    const e = byId(id);
    if (e && e.textContent !== text) e.textContent = text;
  }

  function setRing(id, style) {
    const e = byId(id);
    if (!e) return;
    e.style.setProperty("--p", String(style["--p"]));
    e.style.setProperty("--c", style["--c"]);
  }

  // Journal d'événements, du plus récent au plus ancien.
  function eventNodes(p, idx) {
    const icons = { on: "◉", off: "○", plasma_spike: "▲", spatter_burst: "◆", speed_deviation: "▼" };
    return p.events
      .filter((e) => e.start <= idx)
      .reverse()
      .slice(0, 60)
      .map((e) => {
        const li = node("li", "event event-" + e.type);
        li.append(
          node("span", "event-time", nf(e.t_ms, 2) + " ms"),
          node("span", "event-icon", icons[e.type] || "•"),
          node("span", "event-label", e.label)
        );
        return li;
      });
  }

  // Boucle de relecture ------------------------------------------------------------------------------
  // Un minuteur Dash (dcc.Interval) faisait passer chaque pas par toute la mécanique de Dash sur la page :
  // c'était l'essentiel du coût, même en pause. La boucle ne fait rien tant que l'image ne change pas.
  // Les cartes suivent chaque pas ; les courbes, plus coûteuses, sont espacées selon leur coût mesuré :
  // tous les pas sur une machine rapide, moins souvent sur une machine lente, qui reste ainsi réactive.
  function render(force) {
    const p = state.p;
    const v = video();
    if (!p || !v || state.swap) return; // changement de source : l'image et les cartes restent figées

    // Lecture auto : à la fin de la vidéo, on passe à la soudure suivante.
    const prodMode = byId("prod-mode");
    if (prodMode && prodMode.checked && v.ended && !state.advancing) {
      state.advancing = true;
      window.dash_clientside.set_props("run-select", { value: p.next });
      return;
    }

    const idx = Math.max(0, Math.min(p.n - 1, Math.floor(v.currentTime * p.playback_fps + 1e-3)));
    const moved = force || idx !== state.idx;
    if (!moved && state.chartsIdx === idx) return;
    const gds = chartsReady();
    if (!gds) return; // Plotly pas encore chargé : nouvel essai au pas suivant

    const now = performance.now();
    if (force || (state.chartsIdx !== idx && now >= state.nextCharts)) {
      const figs = figures(p, idx);
      gds.forEach((g, i) => window.Plotly.react(g, figs[i].data, figs[i].layout));
      const cost = performance.now() - now;
      state.chartsIdx = idx;
      state.nextCharts = now + Math.max(0, CHART_SHARE * cost - TICK_MS);
    }
    if (!moved) return;
    state.idx = idx;

    const hud = byId("live-hud");
    if (hud) {
      hud.replaceChildren(
        node("span", null, "t = " + nf(p.ts.t_ms[idx], 2) + " ms"),
        node("span", null, "image " + (idx + 1) + " / " + p.n),
        node("span", null, "×1/" + p.slowmo)
      );
    }
    const [cardClass, laserText, laserDetail] = laserAt(p, idx);
    const card = byId("laser-card");
    if (card && card.className !== cardClass) card.className = cardClass;
    setText("laser-text", laserText);
    setText("laser-detail", laserDetail);
    kpis(p, idx, activeAlarms(p, idx)).forEach(([num, sub, ringStyle], i) => {
      setText("kpi-" + KPIS[i], num);
      setText("kpi-" + KPIS[i] + "-sub", sub);
      setRing("ring-" + KPIS[i], ringStyle);
    });

    // Journal : reconstruit seulement quand un événement apparaît ou disparaît (retour en arrière).
    const shown = p.events.filter((e) => e.start <= idx).length;
    const logKey = state.key + "|" + shown;
    if (force || state.logKey !== logKey) {
      state.logKey = logKey;
      const log = byId("events-log");
      if (log) log.replaceChildren(...eventNodes(p, idx));
      setText("events-count", shown + " / " + p.events.length);
    }
  }

  window.setInterval(() => {
    try {
      render(false);
    } catch (err) {
      console.error(err);
    }
  }, TICK_MS);

  // Fonctions appelées par Dash : ClientsideFunction("weld", ...) dans tabs/process.py ------------
  window.dash_clientside = Object.assign({}, window.dash_clientside, {
    weld: {
      videoSource: function (p, source, prodMode) {
        const keep = [window.dash_clientside.no_update, window.dash_clientside.no_update];
        if (!p) return keep;
        const v = video();
        const src = "/media/videos/" + p.run_id + (source === "raw" ? "" : "_ia") + ".mp4";
        if (v && v.getAttribute("src") === src) return keep; // même vidéo (changement de thème) : rien à recharger
        const sameRun = state.videoRun === p.run_id;
        state.videoRun = p.run_id;
        const autoplay = Boolean(window.weldAutoplay);
        window.weldAutoplay = false;
        if (v && sameRun) {
          // Pendant un changement en cours, la vidéo n'est pas encore repositionnée : reprise inchangée.
          if (!(state.swap && state.resume)) state.resume = { t: v.currentTime, play: !v.paused };
          startSwap(v);
        } else if (v) {
          endSwap();
          state.resume = { t: 0, play: Boolean(prodMode) || autoplay || (v.currentTime > 0 && !v.paused) };
        }
        return [src, "/media/posters/" + p.run_id + ".jpg"];
      },

      toggleMasks: function (_n, source) {
        const next = source === "raw" ? "ia" : "raw";
        const on = next === "ia";
        return [next, on ? "true" : "false", "mask-toggle" + (on ? "" : " is-off"), "mask-legend" + (on ? "" : " is-hidden")];
      },

      // Repères de la timeline : phase laser ON et événements, positionnés en part de la vidéo.
      marks: function (p) {
        if (!p) return [[], {}];
        const pos = (i) => ((100 * i) / p.n).toFixed(2) + "%";
        const on = p.events.find((e) => e.type === "on");
        const off = p.events.find((e) => e.type === "off");
        const style = on ? { left: pos(on.start), width: ((100 * ((off ? off.start : p.n) - on.start)) / p.n).toFixed(2) + "%" } : { display: "none" };
        const marks = p.events
          .filter((e) => !["on", "off"].includes(e.type))
          .map((e) => el("Span", { className: "vp-mark m-" + e.type, style: { left: pos(e.start) }, title: e.short + " · " + nf(e.t_ms, 1) + " ms" }));
        return [marks, style];
      },

      // Réception des données d'une soudure (au chargement d'un run ou d'un thème) : rendu complet.
      receive: function (p) {
        if (p && state.run !== p.run_id) state.advancing = false;
        state.p = p || null;
        state.key = p ? p.run_id + "|" + p.colors.line : null;
        state.run = p ? p.run_id : null;
        window.setTimeout(() => render(true), 0); // après la mise à jour de la page par Dash
        return state.key;
      },
    },
  });
})();
