/* Suivi & historique : sélection d'une soudure, filtre par verdict et ouverture dans le monitoring. */
(function () {
  "use strict";

  // Constantes et utilitaires ---------------------------------------------------------------------
  const VERDICTS = ["all", "ok", "warn", "nok"]; // même ordre que FILTERS (tabs/history.py)

  // Classe d'une tuile : verdict (repris de la classe existante) + sélection + filtre.
  function tileClass(current, selected, flt) {
    const verdict = (current.match(/\bv-(ok|warn|nok)\b/) || [null, "ok"])[1];
    let cls = "run-tile v-" + verdict;
    if (selected) cls += " is-selected";
    if (flt !== "all" && flt !== verdict) cls += " is-dim";
    return cls;
  }

  // Fonctions appelées par Dash : ClientsideFunction("history", ...) dans tabs/history.py ---------
  window.dash_clientside = Object.assign({}, window.dash_clientside, {
    history: {
      select: function (_clicks, clickData, flt, selected, classes) {
        const ctx = window.dash_clientside.callback_context;
        const trig = ctx && ctx.triggered_id;
        let sel = selected;
        if (trig && typeof trig === "object" && trig.type === "hist-run") {
          sel = trig.index;
        } else if (trig === "hist-trend" && clickData && clickData.points && clickData.points.length) {
          sel = clickData.points[0].customdata || sel;
        }
        const ids = (ctx.inputs_list[0] || []).map((i) => i.id.index);
        return [sel, classes.map((c, i) => tileClass(c || "", ids[i] === sel, flt || "all"))];
      },

      filter: function (_clicks, current, classes) {
        const ctx = window.dash_clientside.callback_context;
        const trig = ctx && ctx.triggered_id;
        if (!trig || typeof trig !== "object") {
          const nu = window.dash_clientside.no_update;
          return [nu, nu, nu];
        }
        // Recliquer sur le filtre actif revient à « toutes ».
        const flt = trig.index === current && trig.index !== "all" ? "all" : trig.index;
        return [
          flt,
          VERDICTS.map((k, i) => (classes[i] || "").replace(/\s*is-on\b/, "") + (k === flt ? " is-on" : "")),
          VERDICTS.map((k) => (k === flt ? "true" : "false")),
        ];
      },

      open: function (_n, selected) {
        if (!selected) return [window.dash_clientside.no_update, window.dash_clientside.no_update];
        window.weldAutoplay = true; // la soudure ouverte démarre aussitôt dans le lecteur
        return [selected, { section: "process", run: selected, at: Date.now() }];
      },
    },
  });
})();
