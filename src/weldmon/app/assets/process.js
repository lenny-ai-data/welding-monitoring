/* Monitoring process : lecteur vidéo, synchronisation vidéo <-> signaux, entièrement côté client.
 *
 * La vidéo web contient une frame par frame caméra (30 im/s) : l'index de frame procédé est
 * floor(currentTime * 30). À chaque tick (100 ms), on révèle les signaux jusqu'à cet index ;
 * si rien n'a changé (pause), on ne renvoie rien pour éviter tout rendu inutile. La timeline du
 * lecteur (progression, tête de lecture, temps) est animée à chaque image par requestAnimationFrame.
 */
(function () {
  "use strict";

  const state = { key: null, run: null, videoRun: null, idx: -1, advancing: false, resume: null, rate: 1, p: null };
  const KPIS = ["integrity", "power", "speed"]; // même ordre que les sorties du tick (tabs/process.py)
  const N_OUTPUTS = 4 + 1 + 3 + 3 * KPIS.length + 3;
  const HOLD_MS = 3; // une alarme reste affichée 3 ms de procédé
  const nf = (v, d) =>
    v === null || v === undefined || Number.isNaN(v)
      ? "-"
      : Number(v)
          .toLocaleString("fr-FR", { minimumFractionDigits: d, maximumFractionDigits: d })
          .replace(/\u202f/g, "\u00a0"); // espace fine absente de la police Sora

  const el = (type, props) => ({ type, namespace: "dash_html_components", props });
  const video = () => document.getElementById("live-video");
  const noUpdates = () => Array(N_OUTPUTS).fill(window.dash_clientside.no_update);

  // Couleur d'anneau : violet, puis doré entre 60 et 100 % de la limite, rouge au-delà d'un seuil d'alarme.
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

  // ---------------------------------------------------------------------------------------------
  // Lecteur : lecture / pause, recherche dans la timeline (souris, tactile, clavier).
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

  // Reprise de la position après changement de source (vidéo brute <-> masques IA) ou de run.
  document.addEventListener(
    "loadedmetadata",
    (e) => {
      const v = e.target;
      if (!v || v.id !== "live-video") return;
      v.playbackRate = state.rate;
      if (state.resume) {
        if (state.resume.t > 0) v.currentTime = Math.min(state.resume.t, v.duration - 0.01);
        if (state.resume.play) v.play().catch(() => {});
        state.resume = null;
      }
    },
    true
  );

  // Timeline animée à chaque image (éléments sans sortie Dash : aucun conflit de rendu).
  function animate() {
    const v = video();
    const track = document.getElementById("vp-track");
    if (v && track) {
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

  // ---------------------------------------------------------------------------------------------
  // Statut, KPI, courbes.
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

  function eventItems(p, idx) {
    const icons = { on: "◉", off: "○", plasma_spike: "▲", spatter_burst: "◆", speed_deviation: "▼" };
    return p.events
      .filter((e) => e.start <= idx)
      .reverse()
      .slice(0, 60)
      .map((e) =>
        el("Li", {
          className: "event event-" + e.type,
          children: [
            el("Span", { className: "event-time", children: nf(e.t_ms, 2) + " ms" }),
            el("Span", { className: "event-icon", children: icons[e.type] || "•" }),
            el("Span", { className: "event-label", children: e.label }),
          ],
        })
      );
  }

  window.dash_clientside = Object.assign({}, window.dash_clientside, {
    weld: {
      videoSource: function (p, source, prodMode) {
        if (!p) return [window.dash_clientside.no_update, window.dash_clientside.no_update];
        const v = video();
        const sameRun = state.videoRun === p.run_id;
        state.videoRun = p.run_id;
        const autoplay = Boolean(window.weldAutoplay);
        window.weldAutoplay = false;
        if (v) {
          state.resume = sameRun
            ? { t: v.currentTime, play: !v.paused }
            : { t: 0, play: Boolean(prodMode) || autoplay || (v.currentTime > 0 && !v.paused) };
        }
        const suffix = source === "raw" ? "" : "_ia";
        return ["/media/videos/" + p.run_id + suffix + ".mp4", "/media/posters/" + p.run_id + ".jpg"];
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

      tick: function (_n, p, prodMode) {
        const v = video();
        if (!p || !v) return noUpdates();
        state.p = p;
        const ctx = window.dash_clientside.callback_context;
        // Clé stable du payload (run + thème) : évite de redessiner quand rien n'a changé.
        const key = p.run_id + "|" + p.colors.line;
        const newPayload = state.key !== key;
        if (state.run !== p.run_id) state.advancing = false;
        state.key = key;
        state.run = p.run_id;

        // Enchaîner : à la fin de la vidéo, on passe à la soudure suivante.
        if (prodMode && v.ended && !state.advancing) {
          state.advancing = true;
          const out = noUpdates();
          out[N_OUTPUTS - 1] = p.next;
          return out;
        }

        const idx = Math.max(0, Math.min(p.n - 1, Math.floor(v.currentTime * p.playback_fps + 1e-3)));
        const triggeredByData = ctx && ctx.triggered && ctx.triggered.some((t) => t.prop_id.startsWith("live-data"));
        if (idx === state.idx && !newPayload && !triggeredByData) return noUpdates();
        state.idx = idx;

        const alarms = activeAlarms(p, idx);
        const shown = p.events.filter((e) => e.start <= idx).length;
        const hud = [
          el("Span", { children: "t = " + nf(p.ts.t_ms[idx], 2) + " ms" }),
          el("Span", { children: "image " + (idx + 1) + " / " + p.n }),
          el("Span", { children: "×1/" + p.slowmo }),
        ];
        return [
          ...figures(p, idx),
          hud,
          ...laserAt(p, idx),
          ...kpis(p, idx, alarms).flat(),
          eventItems(p, idx),
          shown + " / " + p.events.length,
          window.dash_clientside.no_update,
        ];
      },
    },
  });
})();
