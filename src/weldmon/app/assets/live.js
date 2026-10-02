/* Monitoring live : synchronisation vidéo <-> signaux, entièrement côté client.
 *
 * La vidéo web contient une frame par frame caméra (30 im/s) : l'index de frame procédé est
 * floor(currentTime * 30). À chaque tick (100 ms), on révèle les signaux jusqu'à cet index ;
 * si rien n'a changé (pause), on ne renvoie rien pour éviter tout rendu inutile.
 */
(function () {
  "use strict";

  const state = { key: null, run: null, videoRun: null, idx: -1, advancing: false, resume: null, rate: 1 };
  const N_OUTPUTS = 17;
  const nf = (v, d) =>
    v === null || v === undefined || Number.isNaN(v)
      ? "—"
      : Number(v).toLocaleString("fr-FR", { minimumFractionDigits: d, maximumFractionDigits: d });

  const el = (type, props) => ({ type, namespace: "dash_html_components", props });

  function video() {
    return document.getElementById("live-video");
  }

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

  function noUpdates() {
    return Array(N_OUTPUTS).fill(window.dash_clientside.no_update);
  }

  function statusAt(p, idx) {
    if (!p.ts.on[idx]) {
      return { cls: "status-off", icon: "○", text: "Laser OFF", sub: "laser éteint" };
    }
    const hold = Math.round(p.fps * 0.003); // une alarme reste affichée 3 ms
    const active = p.events.filter(
      (e) => e.start <= idx && idx <= e.end + hold && !["on", "off"].includes(e.type)
    );
    if (active.length) {
      const e = active[active.length - 1];
      const serious = e.type !== "spatter_burst";
      return {
        cls: serious ? "status-serious" : "status-warning",
        icon: "▲",
        text: "Alarme",
        sub: e.label,
      };
    }
    return { cls: "status-good", icon: "●", text: "Nominal", sub: "dans les limites" };
  }

  function figure(p, idx) {
    const ts = p.ts;
    const end = idx + 1;
    const x = ts.t_ms.slice(0, end);
    const c = p.colors;
    const line = (color, width, extra) => Object.assign({ color, width }, extra || {});
    const traces = [
      {
        x, y: ts.power_cmd_w.slice(0, end), yaxis: "y", type: "scatter", mode: "lines",
        name: "Puissance (consigne)", line: line(c.setpoint, 2, { shape: "hv" }),
        fill: "tozeroy", fillcolor: "rgba(140,134,152,0.10)", hovertemplate: "%{y:.0f} W",
      },
      {
        x, y: ts.feed_cmd_mm_s.slice(0, end), yaxis: "y2", type: "scatter", mode: "lines",
        name: "Vitesse (consigne)", line: line(c.setpoint, 1.5, { shape: "hv", dash: "dash" }),
        hovertemplate: "%{y:.0f} mm/s",
      },
      {
        x, y: ts.speed_mm_s.slice(0, end), yaxis: "y2", type: "scatter", mode: "lines",
        name: "Vitesse (mesurée)", line: line(c.weld, 2), connectgaps: false,
        hovertemplate: "%{y:.0f} mm/s",
      },
      {
        x, y: ts.plasma_mm2.slice(0, end), yaxis: "y3", type: "scatter", mode: "lines",
        name: "Plasma (frame)", line: line(c.plasma, 1), opacity: 0.4, hovertemplate: "%{y:.2f} mm²",
      },
      {
        x, y: ts.plasma_smooth_mm2.slice(0, end), yaxis: "y3", type: "scatter", mode: "lines",
        name: "Plasma (moy. 2 ms)", line: line(c.plasma, 2.2), hovertemplate: "%{y:.2f} mm² (moy.)",
      },
      {
        x, y: ts.spatter_n.slice(0, end), yaxis: "y4", type: "scatter", mode: "lines",
        name: "Projections", line: line(c.spatter, 1.2, { shape: "hv" }), fill: "tozeroy",
        fillcolor: c.spatter + "33", hovertemplate: "%{y} visibles",
      },
      {
        x, y: ts.weld_length_mm.slice(0, end), yaxis: "y5", type: "scatter", mode: "lines",
        name: "Cordon", line: line(c.weld, 2), hovertemplate: "%{y:.1f} mm",
      },
    ];

    // Marqueurs d'alarme (statut + forme, jamais la couleur seule).
    const past = p.events.filter((e) => e.start <= idx);
    const marker = (type, axis, series, color, symbol, name) => {
      const ev = past.filter((e) => e.type === type);
      if (!ev.length) return null;
      return {
        x: ev.map((e) => ts.t_ms[e.start]), y: ev.map((e) => series[e.start]), yaxis: axis,
        type: "scatter", mode: "markers", name,
        marker: { color, size: 9, symbol, line: { width: 1.5, color: "rgba(0,0,0,0.35)" } },
        hovertemplate: name + "<extra></extra>",
      };
    };
    [
      marker("plasma_spike", "y3", ts.plasma_mm2, c.serious, "triangle-up", "Pic de plasma"),
      marker("spatter_burst", "y4", ts.spatter_n, c.warning, "diamond", "Rafale de projections"),
      marker("speed_deviation", "y2", ts.speed_mm_s, c.serious, "triangle-down", "Écart de vitesse"),
    ].forEach((m) => m && traces.push(m));

    const cursor = {
      type: "line", xref: "x", yref: "paper", x0: ts.t_ms[idx], x1: ts.t_ms[idx], y0: 0, y1: 1,
      line: { color: c.muted, width: 1 },
    };
    const layout = Object.assign({}, p.layout, { shapes: p.layout.shapes.concat([cursor]) });
    return { data: traces, layout };
  }

  function eventItems(p, idx) {
    return p.events
      .filter((e) => e.start <= idx)
      .reverse()
      .slice(0, 60)
      .map((e) =>
        el("Li", {
          className: "event event-" + e.type,
          children: [
            el("Span", { className: "event-time", children: nf(e.t_ms, 2) + " ms" }),
            el("Span", { className: "event-icon", children: e.type === "on" ? "◉" : e.type === "off" ? "○" : "▲" }),
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
        if (v) {
          state.resume = sameRun
            ? { t: v.currentTime, play: !v.paused }
            : { t: 0, play: Boolean(prodMode) || (v.currentTime > 0 && !v.paused) };
        }
        const suffix = source === "ia" ? "_ia" : "";
        return ["/media/videos/" + p.run_id + suffix + ".mp4", "/media/posters/" + p.run_id + ".jpg"];
      },

      setRate: function (rate) {
        state.rate = parseFloat(rate) || 1;
        const v = video();
        if (v) v.playbackRate = state.rate;
        return window.dash_clientside.no_update;
      },

      tick: function (_n, p, prodMode) {
        const v = video();
        if (!p || !v) return noUpdates();
        const ctx = window.dash_clientside.callback_context;
        // Clé stable du payload (run + thème) : évite de redessiner quand rien n'a changé.
        const key = p.run_id + "|" + p.layout.font.color;
        const newPayload = state.key !== key;
        if (state.run !== p.run_id) state.advancing = false;
        state.key = key;
        state.run = p.run_id;

        // Mode ligne de production : à la fin de la vidéo, on passe au run suivant.
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

        const ts = p.ts;
        const st = statusAt(p, idx);
        const on = Boolean(ts.on[idx]);
        const speed = ts.speed_mm_s[idx];
        const dev = speed != null ? (100 * (speed - p.setpoint.speed)) / p.setpoint.speed : null;
        const cv = ts.plasma_cv[idx];
        const bursts = p.events.filter((e) => e.type === "spatter_burst" && e.start <= idx).length;
        const shown = p.events.filter((e) => e.start <= idx).length;

        const hud = [
          el("Span", { className: "hud-live", children: "● REPLAY" }),
          el("Span", { children: "t = " + nf(ts.t_ms[idx], 2) + " ms" }),
          el("Span", { children: "frame " + (idx + 1) + " / " + p.n }),
          el("Span", { children: "ralenti ×1/" + p.slowmo + " · " + nf(p.fps, 0) + " im/s" }),
        ];

        return [
          figure(p, idx),
          hud,
          on ? nf(p.setpoint.power, 0) + " W" : "0 W",
          on ? "consigne · laser ON" : "consigne · laser OFF",
          speed != null ? nf(speed, 0) + " mm/s" : "—",
          "consigne " + nf(p.setpoint.speed, 0) + (dev != null ? " · " + (dev >= 0 ? "+" : "") + nf(dev, 0) + " %" : ""),
          on ? nf(ts.plasma_mm2[idx], 2) + " mm²" : "—",
          p.threshold ? "seuil " + nf(p.threshold, 1) + " mm²" : "",
          cv != null ? nf(100 * cv, 0) + " %" : "—",
          "CV plasma · 5 ms",
          String(ts.spatter_n[idx]),
          "visibles · " + bursts + (bursts > 1 ? " rafales" : " rafale"),
          el("Span", { className: "status " + st.cls, children: st.icon + " " + st.text }),
          st.sub,
          eventItems(p, idx),
          shown + " / " + p.events.length + " événements",
          window.dash_clientside.no_update,
        ];
      },
    },
  });
})();
