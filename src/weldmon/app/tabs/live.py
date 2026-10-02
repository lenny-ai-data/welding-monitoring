"""Onglet « Monitoring live » : replay d'un run synchronisé avec ses signaux de procédé.

Le serveur n'envoie qu'une fois par run les séries complètes et la mise en page ; l'animation
(lecture de video.currentTime, révélation progressive des courbes, KPI, alarmes) tourne côté
client dans assets/live.js : aucun aller-retour serveur pendant la lecture.
"""

import dash_mantine_components as dmc
from dash import ClientsideFunction, Input, Output, State, callback, clientside_callback, dcc, html

from .. import data, theme

# Pistes du graphe live : (clé, titre, unité, part de hauteur)
TRACKS = [
    ("power", "Puissance laser — consigne", "W", 0.14),
    ("speed", "Vitesse d'avance — consigne vs mesurée (vision)", "mm/s", 0.21),
    ("plasma", "Aire du panache de plasma (IA)", "mm²", 0.25),
    ("spatter", "Projections visibles (IA)", "nb", 0.20),
    ("weld", "Longueur de cordon (IA)", "mm", 0.20),
]
GAP = 0.045


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
    for r in data.runs():
        tag = " · annoté" if r["split"] else ""
        groups.setdefault(r["serie"], []).append(
            {
                "value": r["run_id"],
                "label": f"#{r['exec_rank']:02d} · essai {r['point']} — {r['power_w']:.0f} W · "
                f"{r['feedrate_mm_s']:.0f} mm/s{tag}",
            }
        )
    return [{"group": f"Série {g} (ordre d'exécution)", "items": items} for g, items in groups.items()]


def kpi_card(key: str, label: str) -> dmc.Paper:
    return dmc.Paper(
        className="kpi",
        children=[
            html.Div(label, className="kpi-label"),
            html.Div("—", id=f"kpi-{key}", className="kpi-value"),
            html.Div("", id=f"kpi-{key}-sub", className="kpi-sub"),
        ],
    )


def layout() -> html.Div:
    first = data.runs()[0]["run_id"]
    default = "DoE3_19" if data.valid_run("DoE3_19") else first
    return html.Div(
        className="tab-body",
        children=[
            dmc.Grid(
                gutter="md",
                children=[
                    dmc.GridCol(
                        span={"base": 12, "lg": 5},
                        children=[
                            dmc.Paper(
                                className="panel",
                                children=[
                                    dmc.Group(
                                        justify="space-between",
                                        align="flex-end",
                                        wrap="wrap",
                                        gap="sm",
                                        children=[
                                            dmc.Select(
                                                id="run-select",
                                                label="Run",
                                                data=run_options(),
                                                value=default,
                                                searchable=True,
                                                allowDeselect=False,
                                                w="100%",
                                                maw=380,
                                                maxDropdownHeight=380,
                                                comboboxProps={"withinPortal": True},
                                            ),
                                            dmc.Switch(
                                                id="prod-mode",
                                                label="Ligne de production",
                                                checked=False,
                                                description="Enchaîne les runs dans l'ordre réel",
                                                size="sm",
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        className="video-wrap",
                                        children=[
                                            html.Video(
                                                id="live-video",
                                                controls=True,
                                                muted=True,
                                                playsInline=True,
                                                preload="auto",
                                                className="video",
                                            ),
                                            html.Div(id="live-hud", className="hud"),
                                        ],
                                    ),
                                    dmc.Group(
                                        justify="space-between",
                                        wrap="wrap",
                                        gap="sm",
                                        mt="sm",
                                        children=[
                                            dmc.SegmentedControl(
                                                id="video-source",
                                                value="raw",
                                                size="xs",
                                                data=[
                                                    {"value": "raw", "label": "Vidéo brute"},
                                                    {"value": "ia", "label": "Masques IA"},
                                                ],
                                            ),
                                            dmc.SegmentedControl(
                                                id="video-rate",
                                                value="1",
                                                size="xs",
                                                data=[
                                                    {"value": v, "label": f"{lab}×"}
                                                    for v, lab in [("0.25", "¼"), ("0.5", "½"), ("1", "1"), ("2", "2")]
                                                ],
                                            ),
                                        ],
                                    ),
                                    html.Div(id="run-params", className="params"),
                                ],
                            ),
                        ],
                    ),
                    dmc.GridCol(
                        span={"base": 12, "lg": 7},
                        children=[
                            html.Div(
                                className="kpi-row",
                                children=[
                                    kpi_card("power", "Puissance"),
                                    kpi_card("speed", "Vitesse"),
                                    kpi_card("plasma", "Plasma"),
                                    kpi_card("stab", "Instabilité"),
                                    kpi_card("spatter", "Projections"),
                                    kpi_card("status", "Statut"),
                                ],
                            ),
                            dmc.Paper(
                                className="panel",
                                mt="md",
                                children=[
                                    dcc.Graph(
                                        id="live-graph",
                                        config={"displayModeBar": False, "responsive": True},
                                        style={"height": "640px"},
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
            dmc.Paper(
                className="panel",
                mt="md",
                children=[
                    dmc.Group(
                        justify="space-between",
                        children=[
                            html.H3("Journal d'événements", className="panel-title"),
                            html.Span(id="events-count", className="muted"),
                        ],
                    ),
                    html.Ul(id="events-log", className="events"),
                ],
            ),
            dcc.Store(id="live-data"),
            dcc.Store(id="live-sink"),
            dcc.Interval(id="live-tick", interval=100),
        ],
    )


def _range(values, floor=1.0, pad=1.12) -> list[float]:
    vals = [v for v in values if v is not None]
    return [0, max(floor, max(vals, default=floor) * pad)]


def live_payload(run_id: str, scheme: str | None) -> dict:
    """Séries complètes + mise en page : le client les révèle au fil de la lecture."""
    run = data.runs_by_id()[run_id]
    ts = data.timeseries(run_id)
    t = theme.tokens(scheme)

    threshold = ts["plasma_threshold_mm2"]  # seuil d'alarme « pic de plasma » (médiane + 3σ robuste)

    labels = event_labels()
    duration = ts["t_ms"][-1]
    ranges = {
        "power": [0, 4500],
        "speed": _range(ts["speed_mm_s"] + [run["feedrate_mm_s"]], 50, 1.25),
        "plasma": _range(ts["plasma_mm2"] + ([threshold] if threshold else []), 1, 1.08),
        "spatter": _range(ts["spatter_n"], 3, 1.15),
        "weld": _range(ts["weld_length_mm"], 5, 1.1),
    }

    layout = theme.base_layout(
        scheme,
        margin={"l": 58, "r": 14, "t": 26, "b": 40},
        showlegend=False,
        hovermode="x unified",
        hoversubplots="axis",
        uirevision=run_id,
    )
    layout["xaxis"] = theme.axis(
        t,
        range=[0, duration],
        title={"text": "Temps de procédé (ms)"},
        anchor=f"y{len(TRACKS)}",
        showspikes=True,
        spikemode="across",
        spikethickness=1,
        spikecolor=t["muted"],
        spikedash="solid",
    )
    annotations, shapes = [], []
    top = 1.0
    for i, (key, title, unit, share) in enumerate(TRACKS, start=1):
        height = share * (1 - GAP * (len(TRACKS) - 1))
        domain = [max(0.0, top - height), top]
        name = "yaxis" if i == 1 else f"yaxis{i}"
        layout[name] = theme.axis(
            t,
            domain=domain,
            range=ranges[key],
            anchor="x",
            title={"text": unit, "standoff": 4},
            nticks=4,
            fixedrange=True,
        )
        annotations.append(
            {
                "text": title,
                "xref": "paper",
                "yref": "paper",
                "x": 0,
                "y": domain[1],
                "xanchor": "left",
                "yanchor": "bottom",
                "showarrow": False,
                "font": {"size": 11, "color": t["text2"]},
            }
        )
        if key == "plasma" and threshold:
            shapes.append(
                {
                    "type": "line",
                    "xref": "x",
                    "yref": f"y{i}",
                    "x0": 0,
                    "x1": duration,
                    "y0": threshold,
                    "y1": threshold,
                    "layer": "below",
                    "line": {"color": theme.STATUS["serious"], "width": 1, "dash": "dash"},
                }
            )
            annotations.append(
                {
                    "text": "seuil d'alarme",
                    "xref": "paper",
                    "x": 1,
                    "yref": f"y{i}",
                    "y": threshold,
                    "xanchor": "right",
                    "yanchor": "bottom",
                    "showarrow": False,
                    "font": {"size": 10, "color": theme.STATUS["serious"]},
                }
            )
        top = domain[0] - GAP
    layout["annotations"] = annotations
    layout["shapes"] = shapes

    return {
        "run_id": run_id,
        "next": data.next_run(run_id),
        "fps": run["fps"],
        "playback_fps": data.meta()["playback_fps"],
        "slowmo": run["slowmo"],
        "n": len(ts["t_ms"]),
        "duration": duration,
        "setpoint": {"power": run["power_w"], "speed": run["feedrate_mm_s"]},
        "threshold": threshold,
        "colors": {k: t[k] for k in ("weld", "plasma", "spatter", "setpoint", "muted")}
        | {"serious": theme.STATUS["serious"], "warning": theme.STATUS["warning"]},
        "ts": {
            k: ts[k]
            for k in (
                "t_ms",
                "on",
                "power_cmd_w",
                "feed_cmd_mm_s",
                "speed_mm_s",
                "plasma_mm2",
                "plasma_smooth_mm2",
                "plasma_cv",
                "spatter_n",
                "weld_length_mm",
            )
        },
        "events": [e | {"label": labels[e["type"]]} for e in ts["events"]],
        "layout": layout,
    }


def params_table(run: dict) -> html.Div:
    rows = [
        ("Puissance", f"{run['power_w']:.0f} W"),
        ("Vitesse d'avance", f"{run['feedrate_mm_s']:.0f} mm/s"),
        ("Énergie linéique", f"{run['line_energy_j_mm']:.1f} J/mm".replace(".", ",")),
        ("Défocalisation", f"{run['defocus_mm']:+.1f} mm".replace(".", ",")),
        ("PFO Y", f"{run['pfo_y_mm']:.0f} mm · {run['inclination_deg']:.1f}°".replace(".", ",")),
        ("Caméra", f"{run['fps']} im/s · {run['n_frames']} frames · {run['duration_ms']:.0f} ms"),
        ("Enregistré le", run["recorded_at"][:16].replace("T", " à ")),
    ]
    badge = []
    if not run["in_domain"]:
        badge.append(
            dmc.Tooltip(
                label="Le modèle IA a été entraîné sur la série DoE3 uniquement. Cette série a un éclairage "
                "et un cadrage différents : les mesures vision y sont moins fiables.",
                multiline=True,
                w=280,
                withArrow=True,
                children=dmc.Badge("Hors domaine d'entraînement", variant="outline", color="orange", size="sm"),
            )
        )
    if run.get("front_fit_r2") is not None and run["front_fit_r2"] < 0.9:
        badge.append(
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
        badge += [
            dmc.Badge(
                "Annoté · " + ("évaluation" if run["split"] == "eval" else "entraînement"),
                variant="light",
                color="grape",
                size="sm",
            )
        ]
    return html.Div(
        [
            dmc.Group(
                [
                    html.Span(
                        f"{run['serie']} · essai {run['point']} · run #{run['exec_rank']} de la série",
                        className="params-title",
                    )
                ]
                + badge,
                gap="xs",
            ),
            html.Dl([item for k, v in rows for item in (html.Dt(k), html.Dd(v))], className="params-grid"),
        ]
    )


@callback(
    Output("live-data", "data"),
    Output("run-params", "children"),
    Input("run-select", "value"),
    Input("color-scheme", "computedColorScheme"),
)
def load_run(run_id, scheme):
    run_id = data.valid_run(run_id) or data.runs()[0]["run_id"]
    return live_payload(run_id, scheme), params_table(data.runs_by_id()[run_id])


clientside_callback(
    ClientsideFunction("weld", "videoSource"),
    Output("live-video", "src"),
    Output("live-video", "poster"),
    Input("live-data", "data"),
    Input("video-source", "value"),
    State("prod-mode", "checked"),
)

clientside_callback(
    ClientsideFunction("weld", "setRate"),
    Output("live-sink", "data"),
    Input("video-rate", "value"),
)

clientside_callback(
    ClientsideFunction("weld", "tick"),
    Output("live-graph", "figure"),
    Output("live-hud", "children"),
    Output("kpi-power", "children"),
    Output("kpi-power-sub", "children"),
    Output("kpi-speed", "children"),
    Output("kpi-speed-sub", "children"),
    Output("kpi-plasma", "children"),
    Output("kpi-plasma-sub", "children"),
    Output("kpi-stab", "children"),
    Output("kpi-stab-sub", "children"),
    Output("kpi-spatter", "children"),
    Output("kpi-spatter-sub", "children"),
    Output("kpi-status", "children"),
    Output("kpi-status-sub", "children"),
    Output("events-log", "children"),
    Output("events-count", "children"),
    Output("run-select", "value"),
    Input("live-tick", "n_intervals"),
    Input("live-data", "data"),
    State("prod-mode", "checked"),
)
