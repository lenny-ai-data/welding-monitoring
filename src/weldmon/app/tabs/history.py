"""Onglet « Suivi & historique » : vue d'ensemble des 81 soudures et de leur verdict qualité.

La campagne la plus récente est affichée en premier ; dans une campagne, les essais sont triés par
numéro. Un clic sur une soudure affiche son détail ; « Ouvrir dans Monitoring process » la rejoue.
La sélection et le filtre sont gérés côté client (assets/history.js), le détail et la courbe côté
serveur (quelques kilo-octets, aucun calcul lourd).
"""

from dash import ALL, ClientsideFunction, Input, Output, State, callback, clientside_callback, dcc, html

from .. import data, theme
from ..components import VERDICTS, icon, point, section_header, verdict_badge

DEFAULT_RUN = "DoE3_19"
CAMPAIGNS = ["DoE3", "DoE2", "DoE1"]  # la plus récente d'abord
FILTERS = [("all", "Soudures contrôlées", "layout-grid"), *((k, lbl, ic) for k, (lbl, ic) in VERDICTS.items())]

EXPLANATIONS = [
    point(
        "Ce que montre cette page",
        "les 81 soudures du jeu de données, présentées comme le suivi d'une production : trois campagnes "
        "réalisées entre juin et juillet 2024, la plus récente en haut.",
    ),
    point(
        "Le verdict",
        "chaque soudure reçoit un verdict à partir des alarmes détectées par l'IA pendant le soudage (pics de "
        "plasma, rafales de projections) : OK jusqu'à 10 alarmes, OK avec warning jusqu'à 15, NOK au-delà. Un "
        "écart de vitesse soutenu rend la soudure NOK dans tous les cas.",
    ),
    point(
        "Filtrer et explorer",
        "les cartes du haut filtrent la grille ; un clic sur un essai (ou sur un point de la courbe) affiche son "
        "détail, et le bouton « Ouvrir dans Monitoring process » rejoue la soudure image par image.",
    ),
]


def runs_sorted() -> list[dict]:
    order = {s: i for i, s in enumerate(CAMPAIGNS)}
    return sorted(data.runs(), key=lambda r: (order[r["serie"]], r["point"]))


def chronological() -> list[dict]:
    return sorted(data.runs(), key=lambda r: r["recorded_at"])


def summary_cards() -> html.Div:
    runs = data.runs()
    cards = []
    for key, label, icon_name in FILTERS:
        n = len(runs) if key == "all" else sum(r["verdict"] == key for r in runs)
        share = "" if key == "all" else f" {round(100 * n / len(runs))} %"
        cards.append(
            html.Button(
                id={"type": "hist-filter", "index": key},
                n_clicks=0,
                type="button",
                className=f"hist-filter v-{key}" + (" is-on" if key == "all" else ""),
                **{"aria-pressed": "true" if key == "all" else "false"},
                children=[
                    html.Span(icon(icon_name, 20), className="hist-filter-icon"),
                    html.Span(
                        className="hist-filter-text",
                        children=[
                            html.Span(label, className="hist-filter-label"),
                            html.Span(
                                [str(n), html.Span(share, className="hist-filter-share")], className="hist-filter-n"
                            ),
                        ],
                    ),
                ],
            )
        )
    return html.Div(cards, className="hist-filters")


def campaign_block(serie: str) -> html.Div:
    rs = [r for r in runs_sorted() if r["serie"] == serie]
    dates = sorted(r["recorded_at"] for r in rs)
    counts = {k: sum(r["verdict"] == k for r in rs) for k in VERDICTS}
    span = f"du {dates[0][8:10]}/{dates[0][5:7]} au {dates[-1][8:10]}/{dates[-1][5:7]}/{dates[-1][2:4]}"
    return html.Div(
        className="campaign",
        children=[
            html.Div(
                className="campaign-head",
                children=[
                    html.Span([html.Strong(f"Campagne {serie}"), html.Span(f" · {span}", className="muted")]),
                    html.Span(
                        className="campaign-stats",
                        children=[
                            html.Span(f"{counts['ok']} OK · {counts['warn']} warning · {counts['nok']} NOK"),
                            html.Span(
                                [
                                    html.Span(className=f"bar-{k}", style={"flexGrow": counts[k]})
                                    for k in VERDICTS
                                    if counts[k]
                                ],
                                className="campaign-bar",
                                **{"aria-hidden": "true"},
                            ),
                        ],
                    ),
                ],
            ),
            html.Div(
                className="run-tiles",
                children=[
                    html.Button(
                        [
                            icon(VERDICTS[r["verdict"]][1], 13),
                            html.Span("Essai ", className="tile-prefix"),
                            str(r["point"]),
                        ],
                        id={"type": "hist-run", "index": r["run_id"]},
                        n_clicks=0,
                        type="button",
                        className=f"run-tile v-{r['verdict']}" + (" is-selected" if r["run_id"] == DEFAULT_RUN else ""),
                        title=f"{serie} · essai {r['point']} : {VERDICTS[r['verdict']][0]}",
                        **{"aria-label": f"{serie} essai {r['point']} : {VERDICTS[r['verdict']][0]}"},
                    )
                    for r in rs
                ],
            ),
        ],
    )


def layout() -> html.Div:
    return html.Div(
        className="tab-body",
        children=[
            section_header(
                "Suivi & historique",
                "Les 81 soudures du jeu de données suivies comme une production : verdict qualité de chaque "
                "soudure, campagne la plus récente en premier.",
                EXPLANATIONS,
            ),
            summary_cards(),
            html.Div(
                className="hist-grid",
                children=[
                    html.Div(
                        className="hist-main",
                        children=[
                            html.Div([campaign_block(s) for s in CAMPAIGNS], className="panel campaigns"),
                            html.Div(
                                className="panel",
                                children=[
                                    html.Div(
                                        className="panel-head",
                                        children=[
                                            html.H3(
                                                [
                                                    "Alarmes par soudure",
                                                    html.Span(" · dans l'ordre de production", className="muted"),
                                                ],
                                                className="panel-title",
                                            ),
                                            html.Span(
                                                "pics de plasma + rafales de projections", className="muted small"
                                            ),
                                        ],
                                    ),
                                    dcc.Graph(
                                        id="hist-trend",
                                        config={"displayModeBar": False, "responsive": True},
                                        style={"height": "250px"},
                                    ),
                                ],
                            ),
                        ],
                    ),
                    html.Aside(
                        className="panel hist-detail",
                        **{"aria-label": "Détail de la soudure sélectionnée"},
                        children=[
                            html.Div(id="hist-detail"),
                            html.Button(
                                [html.Span("Ouvrir dans Monitoring process"), icon("arrow-right", 16)],
                                id="hist-open",
                                n_clicks=0,
                                type="button",
                                className="btn-primary",
                            ),
                        ],
                    ),
                ],
            ),
            dcc.Store(id="hist-selected", data=DEFAULT_RUN),
            dcc.Store(id="hist-filter", data="all"),
        ],
    )


def fmt(v, nd=1, unit="") -> str:
    if v is None:
        return "-"
    return f"{v:.{nd}f}".replace(".", ",").replace("-", "−") + (f" {unit}" if unit else "")


def detail(run: dict) -> list:
    q = data.meta()["quality"]
    n_ok, n_warn = q["verdict_ok_max_alarms"], q["verdict_warn_max_alarms"]
    # Barres sur l'échelle du verdict : 15 alarmes (limite NOK) pour les pics et rafales, un seul écart
    # de vitesse suffit à rendre la soudure NOK.
    alarms = [
        ("Pics de plasma", run["n_plasma_spike"], n_warn, "warn"),
        ("Rafales de projections", run["n_spatter_burst"], n_warn, "warn"),
        ("Écarts de vitesse", run["n_speed_deviation"], 1, "nok"),
    ]
    speed_err = run["speed_error_pct"]
    rule = (
        "écart de vitesse soutenu"
        if run["n_speed_deviation"]
        else f"{run['n_alarms']} alarmes (OK ≤ {n_ok}, warning ≤ {n_warn})"
    )
    return [
        html.Div("Soudure sélectionnée", className="muted small"),
        html.Div(f"{run['serie']} · essai {run['point']}", className="detail-title"),
        verdict_badge(run["verdict"]),
        html.Div(
            f"{run['exec_rank']}ᵉ soudure de la campagne · {run['recorded_at'][8:10]}/{run['recorded_at'][5:7]}/"
            f"{run['recorded_at'][2:4]} {run['recorded_at'][11:16]}",
            className="muted small",
        ),
        html.Div(f"Verdict : {rule}", className="muted small"),
        html.Div(
            className="detail-params",
            children=[
                html.Div([html.Span(k, className="muted"), html.Strong(v)])
                for k, v in [
                    ("Puissance", f"{run['power_w']:,.0f} W".replace(",", "\u00a0")),
                    ("Vitesse", f"{run['feedrate_mm_s']:.0f} mm/s"),
                    ("Défocalisation", fmt(run["defocus_mm"], 1, "mm")),
                    ("PFO Y", f"{run['pfo_y_mm']:.0f} mm"),
                ]
            ],
        ),
        html.H4(["Alarmes", html.Span(f" · {run['n_alarms'] + run['n_speed_deviation']} au total", className="muted")]),
        html.Div(
            className="detail-alarms",
            children=[
                html.Div(
                    [
                        html.Span(label, className="muted"),
                        html.Span(
                            html.Span(className=f"fill-{tone}", style={"width": f"{100 * min(n / scale, 1):.0f}%"}),
                            className="detail-bar",
                            title=f"{n} sur {scale}",
                        ),
                        html.Strong(str(n)),
                    ]
                )
                for label, n, scale, tone in alarms
            ],
        ),
        html.H4("Mesures vision"),
        html.Dl(
            className="detail-measures",
            children=[
                item
                for k, v in [
                    (
                        "Vitesse mesurée",
                        fmt(run["speed_measured_mm_s"], 1, "mm/s")
                        + (f" ({'+' if speed_err >= 0 else ''}{fmt(speed_err, 1)} %)" if speed_err is not None else ""),
                    ),
                    ("Plasma moyen", fmt(run["plasma_mean_mm2"], 1, "mm²")),
                    ("Largeur du cordon", fmt(run["weld_width_mm"], 2, "mm")),
                    ("Longueur soudée", fmt(run["seam_length_mm"], 1, "mm")),
                ]
                for item in (html.Dt(k), html.Dd(v))
            ],
        ),
    ]


def trend_figure(selected: str, flt: str, scheme) -> dict:
    t, vc = theme.tokens(scheme), theme.verdict_colors(scheme)
    q = data.meta()["quality"]
    runs = chronological()
    x = list(range(1, len(runs) + 1))
    shown = [flt == "all" or r["verdict"] == flt for r in runs]
    traces = [
        {
            "type": "scatter",
            "mode": "markers",
            "x": x,
            "y": [r["n_alarms"] for r in runs],
            "customdata": [r["run_id"] for r in runs],
            "text": [f"{r['serie']} · essai {r['point']} : {VERDICTS[r['verdict']][0]}" for r in runs],
            "hovertemplate": "%{text}<br>%{y} alarmes<extra></extra>",
            "marker": {
                "size": [13 if r["run_id"] == selected else 9 for r in runs],
                "color": [vc[r["verdict"]] for r in runs],
                "opacity": [1 if s else 0.2 for s in shown],
                "symbol": [{"ok": "circle", "warn": "triangle-up", "nok": "x"}[r["verdict"]] for r in runs],
                "line": {
                    "width": [2.5 if r["run_id"] == selected else 1 for r in runs],
                    "color": [t["line"] if r["run_id"] == selected else t["surface"] for r in runs],
                },
            },
        }
    ]
    ymax = max(r["n_alarms"] for r in runs) + 3
    shapes, annotations = [], []
    for y, color, label in [
        (q["verdict_ok_max_alarms"] + 0.5, vc["warn"], "warning au-delà de 10"),
        (q["verdict_warn_max_alarms"] + 0.5, vc["nok"], "NOK au-delà de 15"),
    ]:
        shapes.append(
            {
                "type": "line",
                "xref": "paper",
                "x0": 0,
                "x1": 1,
                "y0": y,
                "y1": y,
                "layer": "below",
                "line": {"color": color, "width": 1, "dash": "dash"},
            }
        )
        annotations.append(
            {
                "text": label,
                "xref": "paper",
                "x": 1,
                "y": y,
                "xanchor": "right",
                "yanchor": "bottom",
                "showarrow": False,
                "font": {"size": 10, "color": color},
            }
        )
    # Séparateurs et libellés de campagne.
    start = 0
    for serie in ["DoE1", "DoE2", "DoE3"]:
        n = sum(r["serie"] == serie for r in runs)
        if start:
            shapes.append(
                {
                    "type": "line",
                    "x0": start + 0.5,
                    "x1": start + 0.5,
                    "yref": "paper",
                    "y0": 0,
                    "y1": 1,
                    "layer": "below",
                    "line": {"color": t["axis"], "width": 1},
                }
            )
        annotations.append(
            {
                "text": serie,
                "x": start + 1,
                "y": 1,
                "yref": "paper",
                "xanchor": "left",
                "yanchor": "top",
                "showarrow": False,
                "font": {"size": 10, "color": t["muted"]},
            }
        )
        start += n
    layout = theme.base_layout(
        scheme,
        showlegend=False,
        hovermode="closest",
        margin={"l": 36, "r": 8, "t": 8, "b": 24},
        shapes=shapes,
        annotations=annotations,
    )
    layout["xaxis"] = theme.axis(
        t, range=[0, len(runs) + 1], showgrid=False, showticklabels=False, ticks="", fixedrange=True
    )
    layout["yaxis"] = theme.axis(t, range=[0, ymax], nticks=4, ticks="", showline=False, fixedrange=True)
    return {"data": traces, "layout": layout}


@callback(
    Output("hist-detail", "children"),
    Output("hist-trend", "figure"),
    Input("hist-selected", "data"),
    Input("hist-filter", "data"),
    Input("color-scheme", "computedColorScheme"),
)
def update(selected, flt, scheme):
    run_id = data.valid_run(selected) or DEFAULT_RUN
    flt = flt if flt in ("all", *VERDICTS) else "all"
    return detail(data.runs_by_id()[run_id]), trend_figure(run_id, flt, scheme)


# Sélection d'un essai (tuile ou point de la courbe) et filtre : côté client.
clientside_callback(
    ClientsideFunction("history", "select"),
    Output("hist-selected", "data"),
    Output({"type": "hist-run", "index": ALL}, "className"),
    Input({"type": "hist-run", "index": ALL}, "n_clicks"),
    Input("hist-trend", "clickData"),
    Input("hist-filter", "data"),
    State("hist-selected", "data"),
    State({"type": "hist-run", "index": ALL}, "className"),
)

clientside_callback(
    ClientsideFunction("history", "filter"),
    Output("hist-filter", "data"),
    Output({"type": "hist-filter", "index": ALL}, "className"),
    Output({"type": "hist-filter", "index": ALL}, "aria-pressed"),
    Input({"type": "hist-filter", "index": ALL}, "n_clicks"),
    State("hist-filter", "data"),
    State({"type": "hist-filter", "index": ALL}, "className"),
    prevent_initial_call=True,
)

# Ouvrir la soudure sélectionnée dans le monitoring process (run + navigation).
clientside_callback(
    ClientsideFunction("history", "open"),
    Output("run-select", "value", allow_duplicate=True),
    Output("goto", "data", allow_duplicate=True),
    Input("hist-open", "n_clicks"),
    State("hist-selected", "data"),
    prevent_initial_call=True,
)
