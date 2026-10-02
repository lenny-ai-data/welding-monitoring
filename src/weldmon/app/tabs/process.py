"""Onglet « Monitoring process » : relecture d'une soudure synchronisée avec ses signaux de procédé.

Le serveur n'envoie qu'une fois par run les séries complètes et la mise en page des courbes ;
l'animation (lecture de video.currentTime, révélation progressive des courbes, KPI, alarmes,
timeline du lecteur) tourne côté client dans assets/process.js : aucun aller-retour serveur
pendant la lecture.
"""

import dash_mantine_components as dmc
from dash import ClientsideFunction, Input, Output, State, callback, clientside_callback, dcc, html

from .. import data, theme
from ..components import icon, point, section_header, verdict_badge

DEFAULT_RUN = "DoE3_19"

EXPLANATIONS = [
    point(
        "Ce que vous voyez",
        "une soudure laser réelle filmée par une caméra ultra-rapide (6 000 à 9 000 images par seconde). Une "
        "soudure complète dure moins de 0,15 seconde : elle est rejouée environ 200 fois plus lentement, avec "
        "les mesures que l'IA en extrait image par image.",
    ),
    point(
        "Tir laser",
        "indique d'un coup d'œil si le laser tire à l'instant affiché (« Tir en cours ») ou non (« À l'arrêt »).",
    ),
    point(
        "Intégrité",
        "compte les seuils franchis depuis l'allumage : pics de plasma, rafales de projections, écarts de "
        "vitesse. L'anneau va de 0 à 15 et suit les seuils du verdict : violet jusqu'à 10 (OK), doré jusqu'à 15 "
        "(OK avec warning), rouge au-delà ou dès un écart de vitesse (NOK).",
    ),
    point(
        "Puissance et vitesse",
        "consigne de puissance et vitesse d'avance mesurée à l'image. L'anneau de vitesse montre l'écart à la "
        "consigne : il vire au doré à l'approche de ±10 % et au rouge en cas d'alarme (±20 % pendant 5 ms).",
    ),
    point(
        "Les masques IA",
        "un modèle d'intelligence artificielle repère sur chaque image le cordon de soudure (violet), le panache "
        "de plasma (orange) — la vapeur de métal ionisée au-dessus du point de soudage — et les projections de "
        "métal fondu (magenta). Le bouton en haut à droite de la vidéo les masque.",
    ),
    point(
        "Les courbes",
        "en pointillés, les consignes et les seuils ; en violet, ce qui est mesuré à l'image. Les pics de plasma "
        "(▲), les rafales de projections (◆) et les écarts de vitesse (▼) sont marqués là où ils se produisent, "
        "et la timeline du lecteur les situe dans la soudure.",
    ),
    point(
        "Enchaîner",
        "activé, le lecteur passe automatiquement à la soudure suivante, dans l'ordre réel de production.",
    ),
    point(
        "Badge « hors domaine »",
        "le modèle a appris sur la campagne DoE3 ; DoE1 et DoE2 ont été filmées avec un éclairage et un cadrage "
        "différents. Les mesures y restent exploitables mais moins précises — c'est signalé, pas caché.",
    ),
]

KPIS = [
    # (clé, libellé, unité)
    ("power", "Puissance", "W"),
    ("speed", "Vitesse", "mm/s"),
]
CHARTS = ["plasma", "speed", "spatter", "weld"]
SHORT_LABELS = {
    "on": "Allumage laser",
    "off": "Extinction laser",
    "plasma_spike": "Pic de plasma",
    "spatter_burst": "Rafale de projections",
    "speed_deviation": "Écart de vitesse",
}


def event_labels() -> dict[str, str]:
    rules = data.meta()["calibration"]["alarm_rules"]
    return {
        "on": "Allumage laser",
        "off": "Extinction laser",
        "plasma_spike": f"Pic de plasma (> médiane + {rules['plasma_spike_sigma']:.0f}σ)",
        "spatter_burst": f"Rafale de projections (≥ {rules['spatter_burst_count']} visibles)",
        "speed_deviation": f"Écart de vitesse > {rules['speed_tolerance_pct']} % "
        f"(≥ {rules['speed_min_duration_ms']:.0f} ms)",
    }


def run_options() -> list[dict]:
    groups: dict[str, list] = {}
    for r in sorted(data.runs(), key=lambda r: ({"DoE3": 0, "DoE2": 1, "DoE1": 2}[r["serie"]], r["point"])):
        groups.setdefault(r["serie"], []).append(
            {
                "value": r["run_id"],
                "label": f"{r['serie']} · essai {r['point']} · {r['power_w']:.0f} W · {r['feedrate_mm_s']:.0f} mm/s",
            }
        )
    return [{"group": f"Campagne {g}", "items": items} for g, items in groups.items()]


def kpi_card(key: str, label: str, unit: str) -> html.Div:
    return html.Div(
        className="kpi-card",
        children=[
            html.Div(id=f"ring-{key}", className="ring", style={"--p": 0}, **{"aria-hidden": "true"}),
            html.Div(
                className="kpi-body",
                children=[
                    html.Div(label, className="kpi-label"),
                    html.Div(
                        [html.Span("—", id=f"kpi-{key}", className="kpi-num"), html.Span(unit, className="kpi-unit")],
                        className="kpi-value",
                    ),
                    html.Div("", id=f"kpi-{key}-sub", className="kpi-sub"),
                ],
            ),
        ],
    )


def laser_card() -> html.Div:
    """Tir laser : seulement « Tir en cours » ou « À l'arrêt »."""
    return html.Div(
        id="laser-card",
        className="status-card is-standby",
        **{"role": "status", "aria-live": "polite"},
        children=[
            html.Div("Tir laser", className="status-label"),
            html.Div(
                className="status-main",
                children=[
                    html.Span(className="status-dot", **{"aria-hidden": "true"}),
                    html.Span("À l'arrêt", id="laser-text", className="status-text"),
                ],
            ),
            html.Div("", id="laser-detail", className="status-detail"),
        ],
    )


def integrity_card() -> html.Div:
    """Intégrité : seuils franchis depuis l'allumage, anneau de 0 à 15 qui suit les seuils du verdict."""
    return html.Div(
        className="kpi-card integrity-card",
        children=[
            html.Div(
                className="integrity-top",
                children=[
                    html.Div(id="ring-integrity", className="ring", style={"--p": 0}, **{"aria-hidden": "true"}),
                    html.Div(
                        className="kpi-body",
                        children=[
                            html.Div("Intégrité", className="kpi-label"),
                            html.Div(
                                [
                                    html.Span("0", id="kpi-integrity", className="kpi-num"),
                                    html.Span("seuils franchis", className="kpi-unit"),
                                ],
                                className="kpi-value",
                            ),
                        ],
                    ),
                ],
            ),
            html.Div("", id="kpi-integrity-sub", className="kpi-sub"),
        ],
    )


def chart_panel(key: str, title, legend=None) -> html.Div:
    return html.Div(
        className=f"panel chart-panel chart-{key}",
        children=[
            html.Div([html.H3(title, className="panel-title"), legend], className="panel-head"),
            dcc.Graph(
                id=f"live-{key}",
                className="graph-fill",
                config={"displayModeBar": False, "responsive": True},
                style={"height": "100%"},
            ),
        ],
    )


def legend_item(cls: str, label: str) -> html.Span:
    return html.Span([html.Span(className=f"lg {cls}"), label], className="legend-item")


def player() -> html.Div:
    return html.Div(
        className="panel video-card",
        children=[
            html.Div(
                className="player",
                children=[
                    html.Video(
                        id="live-video",
                        controls=False,
                        muted=True,
                        playsInline=True,
                        preload="auto",
                        className="video",
                    ),
                    html.Div(id="live-hud", className="hud"),
                    html.Button(
                        icon("layers", 16),
                        id="mask-toggle",
                        n_clicks=0,
                        type="button",
                        className="mask-toggle",
                        title="Masques IA",
                        **{"aria-label": "Masques IA", "aria-pressed": "true"},
                    ),
                    html.Div(
                        id="mask-legend",
                        className="mask-legend",
                        children=[
                            html.Span([html.Span(className="sw sw-weld"), "Cordon"]),
                            html.Span([html.Span(className="sw sw-plasma"), "Plasma"]),
                            html.Span([html.Span(className="sw sw-spatter"), "Projections"]),
                        ],
                    ),
                ],
            ),
            html.Div(
                className="transport",
                children=[
                    html.Button(
                        [icon("play", 16), icon("pause", 16)],
                        id="vp-play",
                        type="button",
                        className="vp-play",
                        **{"aria-label": "Lecture / pause"},
                    ),
                    html.Div(
                        id="vp-track",
                        className="vp-track",
                        tabIndex=0,
                        **{
                            "role": "slider",
                            "aria-label": "Position dans la soudure",
                            "aria-valuemin": 0,
                            "aria-valuemax": 100,
                            "aria-valuenow": 0,
                        },
                        children=[
                            html.Div(className="vp-rail"),
                            html.Div(id="vp-on", className="vp-on"),
                            html.Div(id="vp-progress", className="vp-progress"),
                            html.Div(id="vp-marks", className="vp-marks"),
                            html.Div(id="vp-head", className="vp-head"),
                        ],
                    ),
                    html.Span("0,00 ms", id="vp-time", className="vp-time"),
                    html.Button(
                        "1×",
                        id="vp-rate",
                        type="button",
                        className="vp-rate",
                        title="Vitesse de lecture",
                        **{"aria-label": "Vitesse de lecture : 1×"},
                    ),
                ],
            ),
        ],
    )


def layout() -> html.Div:
    default = DEFAULT_RUN if data.valid_run(DEFAULT_RUN) else data.runs()[0]["run_id"]
    return html.Div(
        className="tab-body",
        children=[
            section_header(
                "Monitoring process",
                "Relecture d'une soudure réelle filmée à 6 000 images/s et ralentie 200 fois, avec ses signaux de "
                "procédé et l'analyse de l'IA image par image.",
                EXPLANATIONS,
                crumb=[
                    html.Button(
                        "Suivi & historique", id="crumb-suivi", n_clicks=0, type="button", className="crumb-link"
                    ),
                    html.Span(" / "),
                    html.Span(id="proc-crumb-run"),
                ],
                aside=[
                    html.Div(id="proc-verdict"),
                    dmc.Select(
                        id="run-select",
                        data=run_options(),
                        value=default,
                        searchable=True,
                        allowDeselect=False,
                        w=330,
                        maxDropdownHeight=380,
                        comboboxProps={"withinPortal": True},
                        **{"aria-label": "Soudure à rejouer"},
                    ),
                    dmc.Switch(id="prod-mode", label="Enchaîner", checked=True, size="sm"),
                ],
            ),
            html.Div(
                className="proc-grid",
                children=[
                    html.Div(
                        className="proc-left",
                        children=[player(), html.Div(id="run-params", className="panel params")],
                    ),
                    html.Div(
                        className="proc-right",
                        children=[
                            html.Div(
                                className="proc-top",
                                children=[
                                    html.Div(
                                        [laser_card(), integrity_card(), *(kpi_card(*k) for k in KPIS)],
                                        className="kpi-grid",
                                    ),
                                    html.Div(
                                        className="panel events-panel",
                                        children=[
                                            html.Div(
                                                [
                                                    html.H3("Journal d'événements", className="panel-title"),
                                                    html.Span(id="events-count", className="muted small"),
                                                ],
                                                className="panel-head",
                                            ),
                                            html.Ul(id="events-log", className="events"),
                                        ],
                                    ),
                                ],
                            ),
                            chart_panel(
                                "plasma",
                                ["Panache de plasma", html.Span(" · mm²", className="muted")],
                                html.Span(
                                    [
                                        legend_item("lg-line", "moyenne 2 ms"),
                                        legend_item("lg-raw", "image par image"),
                                        legend_item("lg-alarm", "seuil d'alarme"),
                                        html.Span(
                                            [html.Span("▲", className="lg-sym alarm"), "pic"], className="legend-item"
                                        ),
                                    ],
                                    className="legend",
                                ),
                            ),
                            html.Div(
                                className="chart-row",
                                children=[
                                    chart_panel("speed", ["Vitesse", html.Span(" · mm/s", className="muted")]),
                                    chart_panel(
                                        "spatter", ["Projections", html.Span(" · visibles", className="muted")]
                                    ),
                                    chart_panel("weld", ["Cordon soudé", html.Span(" · mm", className="muted")]),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
            dcc.Store(id="live-data"),
            dcc.Store(id="video-source", data="ia"),
            dcc.Interval(id="live-tick", interval=100),
        ],
    )


def _max(values, floor: float) -> float:
    return max([v for v in values if v is not None] + [floor])


def chart_layouts(run: dict, ts: dict, scheme) -> dict:
    t = theme.tokens(scheme)
    duration = ts["t_ms"][-1]
    threshold = ts["plasma_threshold_mm2"]
    burst = data.meta()["calibration"]["alarm_rules"]["spatter_burst_count"]
    sp = run["feedrate_mm_s"]
    speeds = [v for v in ts["speed_mm_s"] if v is not None] or [sp]

    def layout(key: str, y_range, nticks: int, shapes=(), annotations=(), x_title=None) -> dict:
        lay = theme.base_layout(
            scheme,
            margin={"l": 40, "r": 10, "t": 6, "b": 34 if x_title else 22},
            showlegend=False,
            hovermode="x unified",
            uirevision=run["run_id"] + key,
            shapes=list(shapes),
            annotations=list(annotations),
        )
        lay["xaxis"] = theme.xaxis(t, range=[0, duration], nticks=7, fixedrange=True)
        if x_title:
            lay["xaxis"]["title"] |= {"text": x_title, "standoff": 6}
        lay["yaxis"] = theme.axis(t, range=y_range, nticks=nticks, showline=False, ticks="", fixedrange=True)
        return lay

    def hline(y, color, dash="dash"):
        return {
            "type": "line",
            "xref": "paper",
            "x0": 0,
            "x1": 1,
            "y0": y,
            "y1": y,
            "layer": "below",
            "line": {"color": color, "width": 1.2, "dash": dash},
        }

    def label(y, text, color, anchor="bottom"):
        return {
            "text": text,
            "xref": "paper",
            "x": 1,
            "y": y,
            "xanchor": "right",
            "yanchor": anchor,
            "showarrow": False,
            "font": {"size": 10, "color": color},
        }

    lo = min(0.75 * sp, min(speeds) * 0.95)
    hi = max(1.25 * sp, max(speeds) * 1.05)
    return {
        "plasma": layout(
            "plasma",
            [0, 1.1 * _max(ts["plasma_mm2"] + [threshold or 0], 1)],
            6,
            [hline(threshold, t["alarm"])] if threshold else [],
            [label(threshold, "seuil d'alarme", t["alarm"])] if threshold else [],
            x_title="Temps de procédé (ms)",
        ),
        "speed": layout(
            "speed",
            [lo, hi],
            4,
            [
                {
                    "type": "rect",
                    "xref": "paper",
                    "x0": 0,
                    "x1": 1,
                    "y0": 0.9 * sp,
                    "y1": 1.1 * sp,
                    "layer": "below",
                    "fillcolor": t["band"],
                    "line": {"color": t["band_edge"], "width": 1, "dash": "dot"},
                },
                hline(sp, t["muted"]),
            ],
            [label(1.1 * sp, "+10 %", t["muted"]), label(0.9 * sp, "−10 %", t["muted"], "top")],
        ),
        "spatter": layout(
            "spatter",
            [0, max(burst + 1, _max(ts["spatter_n"], 0) + 0.5)],
            4,
            [hline(burst, t["gold"])],
            [label(burst, "seuil de rafale", t["gold"])],
        ),
        "weld": layout("weld", [0, 1.1 * _max(ts["weld_length_mm"], 5)], 4),
    }


def live_payload(run_id: str, scheme: str | None) -> dict:
    """Séries complètes + mises en page : le client les révèle au fil de la lecture."""
    run = data.runs_by_id()[run_id]
    ts = data.timeseries(run_id)
    t = theme.tokens(scheme)
    rules = data.meta()["calibration"]["alarm_rules"]
    quality = data.meta()["quality"]
    labels = event_labels()
    return {
        "run_id": run_id,
        "next": data.next_run(run_id),
        "fps": run["fps"],
        "playback_fps": data.meta()["playback_fps"],
        "slowmo": run["slowmo"],
        "n": len(ts["t_ms"]),
        "duration": ts["t_ms"][-1],
        "setpoint": {"power": run["power_w"], "speed": run["feedrate_mm_s"]},
        "limits": {
            "plasma": ts["plasma_threshold_mm2"],
            "speed_warn_pct": quality["speed_warn_pct"],
            "stab": quality["stability_limit_cv"],
            "burst": rules["spatter_burst_count"],
            "ok_max": quality["verdict_ok_max_alarms"],
            "warn_max": quality["verdict_warn_max_alarms"],
        },
        "colors": {k: t[k] for k in ("line", "line_raw", "fill", "cursor", "ring", "gold", "alarm", "surface")},
        "ts": {
            k: ts[k]
            for k in (
                "t_ms",
                "on",
                "speed_mm_s",
                "plasma_mm2",
                "plasma_smooth_mm2",
                "plasma_cv",
                "spatter_n",
                "weld_length_mm",
            )
        },
        "events": [e | {"label": labels[e["type"]], "short": SHORT_LABELS[e["type"]]} for e in ts["events"]],
        "layouts": chart_layouts(run, ts, scheme),
    }


def fmt(v: float, nd: int = 1) -> str:
    return f"{v:,.{nd}f}".replace(",", " ").replace(".", ",").replace("-", "−")


def params_table(run: dict) -> list:
    rows = [
        ("Puissance", f"{fmt(run['power_w'], 0)} W"),
        ("Vitesse d'avance", f"{run['feedrate_mm_s']:.0f} mm/s"),
        ("Énergie linéique", f"{fmt(run['line_energy_j_mm'])} J/mm"),
        ("Défocalisation", f"{'+' if run['defocus_mm'] > 0 else ''}{fmt(run['defocus_mm'])} mm"),
        ("PFO Y", f"{run['pfo_y_mm']:.0f} mm · {fmt(run['inclination_deg'])}°"),
        ("Caméra", f"{fmt(run['fps'], 0)} im/s · {run['duration_ms']:.0f} ms"),
        (
            "Enregistré le",
            f"{run['recorded_at'][8:10]}/{run['recorded_at'][5:7]}/{run['recorded_at'][:4]} "
            f"à {run['recorded_at'][11:16]}",
        ),
    ]
    badges = []
    if not run["in_domain"]:
        badges.append(
            dmc.Tooltip(
                label="Le modèle IA a été entraîné sur la campagne DoE3 uniquement. Cette campagne a un éclairage "
                "et un cadrage différents : les mesures vision y sont moins fiables.",
                multiline=True,
                w=280,
                withArrow=True,
                children=dmc.Badge("Hors domaine d'entraînement", variant="outline", color="yellow", size="sm"),
            )
        )
    if run.get("front_fit_r2") is not None and run["front_fit_r2"] < 0.9:
        badges.append(
            dmc.Tooltip(
                label="La position du front du cordon est mal suivie sur ce run (ajustement R² < 0,9) : "
                "la vitesse mesurée y est indicative.",
                multiline=True,
                w=280,
                withArrow=True,
                children=dmc.Badge("Suivi du front dégradé", variant="outline", color="yellow", size="sm"),
            )
        )
    if run["split"]:
        badges.append(
            dmc.Badge(
                "Annoté · " + ("évaluation" if run["split"] == "eval" else "entraînement"), variant="light", size="sm"
            )
        )
    return [
        html.Div(
            [
                html.H3(
                    f"{run['serie']} · essai {run['point']} · {run['exec_rank']}ᵉ soudure de la campagne",
                    className="panel-title",
                ),
                *badges,
            ],
            className="params-head",
        ),
        html.Dl([item for k, v in rows for item in (html.Dt(k), html.Dd(v))], className="params-grid"),
    ]


@callback(
    Output("live-data", "data"),
    Output("run-params", "children"),
    Output("proc-verdict", "children"),
    Output("proc-crumb-run", "children"),
    Input("run-select", "value"),
    Input("color-scheme", "computedColorScheme"),
)
def load_run(run_id, scheme):
    run_id = data.valid_run(run_id) or data.runs()[0]["run_id"]
    run = data.runs_by_id()[run_id]
    return (
        live_payload(run_id, scheme),
        params_table(run),
        verdict_badge(run["verdict"], "Soudure "),
        f"{run['serie']} · essai {run['point']}",
    )


clientside_callback(
    ClientsideFunction("weld", "videoSource"),
    Output("live-video", "src"),
    Output("live-video", "poster"),
    Input("live-data", "data"),
    Input("video-source", "data"),
    State("prod-mode", "checked"),
)

clientside_callback(
    ClientsideFunction("weld", "toggleMasks"),
    Output("video-source", "data"),
    Output("mask-toggle", "aria-pressed"),
    Output("mask-toggle", "className"),
    Output("mask-legend", "className"),
    Input("mask-toggle", "n_clicks"),
    State("video-source", "data"),
    prevent_initial_call=True,
)

clientside_callback(
    ClientsideFunction("weld", "marks"),
    Output("vp-marks", "children"),
    Output("vp-on", "style"),
    Input("live-data", "data"),
)

clientside_callback(
    ClientsideFunction("weld", "tick"),
    *[Output(f"live-{k}", "figure") for k in CHARTS],
    Output("live-hud", "children"),
    Output("laser-card", "className"),
    Output("laser-text", "children"),
    Output("laser-detail", "children"),
    *[
        o
        for k in ["integrity", *(k for k, *_ in KPIS)]
        for o in (Output(f"kpi-{k}", "children"), Output(f"kpi-{k}-sub", "children"), Output(f"ring-{k}", "style"))
    ],
    Output("events-log", "children"),
    Output("events-count", "children"),
    Output("run-select", "value"),
    Input("live-tick", "n_intervals"),
    Input("live-data", "data"),
    State("prod-mode", "checked"),
)
