"""Onglet « Analyses » : fenêtre de procédé à partir des 81 runs (3 séries Box-Behnken).

Les surfaces sont recalculées ici à partir des coefficients exportés (Python pur, sans numpy).
"""

import statistics

import dash_mantine_components as dmc
from dash import Input, Output, callback, dcc, html

from .. import data, theme
from ..components import point, section_header

# Constantes et textes -----------------------------------------------------------------------------
EXPLANATIONS = [
    point(
        "L'étude de sensibilité",
        "permet d'évaluer l'impact d'un paramètre sur les indicateurs cible à partir une matrice d'essais "
        "portant ici sur 4 paramètres (puissance, vitesse, défocalisation et PFO).",
    ),
    point(
        "La surface de réponse",
        "un modèle statistique prédit l'indicateur pour toute combinaison de deux paramètres (les deux autres au "
        "milieu de leur plage).",
    ),
    point(
        "Les effets standardisés",
        "quels paramètres ont un impact statistiquement démontré (barres violettes, au-delà du seuil p = 0,05) et "
        "lesquels se confondent avec le bruit de mesure (barres grises).",
    ),
    point(
        "La carte de contrôle",
        "ce que les paramètres n'expliquent pas, soudure après soudure dans l'ordre chronologique : un point hors "
        "des limites rouges signale un essai anormal ou une dérive à investiguer.",
    ),
]

GRID = 41
# Les 4 facteurs du plan Box-Behnken (clés de doe.json) : constantes pour que le module s'importe
# sans app_data/ (CI, tests unitaires), les callbacks étant déclarés à l'import.
FACTORS = ("P", "v", "f", "y")


# Calcul des modèles (Python pur, à partir des coefficients de doe.json) ---------------------------


def factor_value(run: dict, key: str) -> float:
    f = data.doe()["factors"][key]
    return (run[f["column"]] - f["center"]) / f["half_range"]


def predict(kpi: dict, coded: dict[str, float]) -> float:
    y = kpi["intercept"]
    for coef, term in zip(kpi["coefs"], data.doe()["terms"], strict=True):
        prod = 1.0
        for a in term:
            prod *= coded[a]
        y += coef * prod
    return y


def fmt(v: float, d: int = 2) -> str:
    return f"{v:.{d}f}".replace(".", ",")


# Mise en page -------------------------------------------------------------------------------------


def graph(graph_id: str, height: str) -> dcc.Graph:
    return dcc.Graph(id=graph_id, config={"displayModeBar": False, "responsive": True}, style={"height": height})


def layout() -> html.Div:
    d = data.doe()
    kpi_opts = [
        {"value": k, "label": v["label"] + (f" ({v['unit']})" if v["unit"] else "")} for k, v in d["kpis"].items()
    ]
    fac_opts = [{"value": k, "label": f"{v['label']} ({v['unit']})"} for k, v in d["factors"].items()]
    return html.Div(
        className="tab-body",
        children=[
            section_header(
                "Analyses",
                "Etude de sensibilité : quels paramètres influencent la qualité de soudure ?",
                EXPLANATIONS,
                aside=[
                    dmc.Select(
                        id="doe-kpi",
                        label="Indicateur",
                        data=kpi_opts,
                        value="weld_width_mm",
                        allowDeselect=False,
                        w=300,
                        size="sm",
                        className="select-accent",
                    ),
                    dmc.Select(
                        id="doe-x",
                        label="Axe horizontal",
                        data=fac_opts,
                        value="P",
                        allowDeselect=False,
                        w=240,
                        size="sm",
                        className="select-accent",
                    ),
                    dmc.Select(
                        id="doe-y",
                        label="Axe vertical",
                        data=fac_opts,
                        value="v",
                        allowDeselect=False,
                        w=240,
                        size="sm",
                        className="select-accent",
                    ),
                ],
            ),
            html.Div(
                className="doe-row doe-row-1",
                children=[
                    html.Div(
                        className="panel",
                        children=[
                            html.Div(
                                [
                                    html.H3(id="doe-surface-title", className="panel-title"),
                                    html.Div(id="doe-fit", className="fit-badges"),
                                ],
                                className="panel-head",
                            ),
                            graph("doe-surface", "420px"),
                        ],
                    ),
                    html.Div(
                        className="panel",
                        children=[
                            html.Div(
                                [
                                    html.H3("Effets standardisés", className="panel-title"),
                                    html.Span(
                                        "|t| de Student · violet : significatif (p < 0,05)", className="muted small"
                                    ),
                                ],
                                className="panel-head",
                            ),
                            graph("doe-pareto", "420px"),
                        ],
                    ),
                ],
            ),
            html.Div(
                className="doe-row doe-row-2",
                children=[
                    html.Div(
                        className="panel",
                        children=[
                            html.Div(
                                [
                                    html.H3("Carte de contrôle des résidus (I-MR)", className="panel-title"),
                                    html.Span("dans l'ordre réel de soudage", className="muted small"),
                                ],
                                className="panel-head",
                            ),
                            graph("doe-spc", "300px"),
                        ],
                    ),
                    html.Div(
                        className="main-effects",
                        children=[
                            html.Div(
                                className="panel effect-card",
                                children=[
                                    html.Div(
                                        [
                                            html.H3(f["label"], className="panel-title"),
                                            html.Span(f"effet principal · {f['unit']}", className="muted small"),
                                        ],
                                        className="panel-head",
                                    ),
                                    graph(f"doe-main-{key}", "122px"),
                                ],
                            )
                            for key, f in d["factors"].items()
                        ],
                    ),
                ],
            ),
        ],
    )


# Figures : surface de réponse, effets standardisés, effets principaux, carte I-MR -----------------


def surface_fig(kpi_key: str, fx: str, fy: str, scheme) -> dict:
    d, t = data.doe(), theme.tokens(scheme)
    kpi, factors = d["kpis"][kpi_key], d["factors"]
    grid = [-1 + 2 * i / (GRID - 1) for i in range(GRID)]

    def real(key, c):
        return factors[key]["center"] + c * factors[key]["half_range"]

    z = []
    for cy in grid:
        row = []
        for cx in grid:
            coded = {k: 0.0 for k in factors}
            coded[fx], coded[fy] = cx, cy
            row.append(predict(kpi, coded))
        z.append(row)
    unit = kpi["unit"]

    others = [k for k in factors if k not in (fx, fy)]
    pts = [r for r in data.runs() if r.get(kpi_key) is not None and all(abs(factor_value(r, o)) < 1e-6 for o in others)]
    traces = [
        {
            "type": "contour",
            "x": [real(fx, c) for c in grid],
            "y": [real(fy, c) for c in grid],
            "z": z,
            "colorscale": theme.pale_plasma(scheme),
            "contours": {"coloring": "heatmap", "showlabels": False},
            "line": {"width": 0.5, "color": t["surface"]},
            "ncontours": 14,
            "colorbar": {
                "title": {"text": unit, "side": "right"},
                "thickness": 10,
                "outlinewidth": 0,
                "tickfont": {"color": t["text2"], "size": 10},
            },
            "hovertemplate": (
                f"{factors[fx]['label']} %{{x:.3~f}} {factors[fx]['unit']}<br>"
                f"{factors[fy]['label']} %{{y:.3~f}} {factors[fy]['unit']}<br>"
                f"prédit : %{{z:.3~f}} {unit}<extra></extra>"
            ),
        },
        {
            "type": "scatter",
            "mode": "markers",
            "x": [r[factors[fx]["column"]] for r in pts],
            "y": [r[factors[fy]["column"]] for r in pts],
            "marker": {"size": 9, "color": t["surface"], "line": {"width": 2, "color": t["text"]}},
            "customdata": [[r["run_id"], r[kpi_key]] for r in pts],
            "hovertemplate": f"%{{customdata[0]}}<br>mesuré : %{{customdata[1]:.3~f}} {unit}<extra></extra>",
        },
    ]
    layout = theme.base_layout(
        scheme, showlegend=False, hovermode="closest", margin={"l": 64, "r": 10, "t": 6, "b": 44}
    )
    layout["xaxis"] = theme.axis(t, title={"text": f"{factors[fx]['label']} ({factors[fx]['unit']})"}, showgrid=False)
    layout["yaxis"] = theme.axis(t, title={"text": f"{factors[fy]['label']} ({factors[fy]['unit']})"}, showgrid=False)
    return {"data": traces, "layout": layout}


def pretty_term(term: str) -> str:
    names = {k: v["label"] for k, v in data.doe()["factors"].items()}
    if term.startswith("série"):
        return term.replace("série", "Série")
    if term.endswith("²"):
        return names[term[:-1]] + "²"
    return " × ".join(names[p] for p in term.split("·"))


def pareto_fig(kpi_key: str, scheme) -> dict:
    d, t = data.doe(), theme.tokens(scheme)
    kpi = d["kpis"][kpi_key]

    eff = sorted(kpi["effects"], key=lambda e: abs(e["t"]))[-12:]
    sig = [e["p"] < 0.05 for e in eff]
    traces = [
        {
            "type": "bar",
            "orientation": "h",
            "x": [abs(e["t"]) for e in eff],
            "y": [pretty_term(e["term"]) for e in eff],
            "marker": {"color": [t["line"] if s else t["bar_muted"] for s in sig], "cornerradius": 4},
            "customdata": [[e["coef"], e["p"]] for e in eff],
            "hovertemplate": "%{y}<br>|t| = %{x:.2f} · coef %{customdata[0]:.4~f} · p = %{customdata[1]:.3f}"
            "<extra></extra>",
        }
    ]
    layout = theme.base_layout(
        scheme, showlegend=False, hovermode="closest", bargap=0.4, margin={"l": 12, "r": 16, "t": 20, "b": 24}
    )
    layout["xaxis"] = theme.axis(t, rangemode="tozero", nticks=5)
    layout["yaxis"] = theme.axis(t, showgrid=False, automargin=True, tickfont={"size": 11.5, "color": t["text2"]})
    layout["shapes"] = [
        {
            "type": "line",
            "x0": kpi["t_crit"],
            "x1": kpi["t_crit"],
            "yref": "paper",
            "y0": 0,
            "y1": 1,
            "line": {"color": t["muted"], "width": 1, "dash": "dash"},
        }
    ]
    layout["annotations"] = [
        {
            "x": kpi["t_crit"],
            "y": 1,
            "yref": "paper",
            "text": "p = 0,05",
            "showarrow": False,
            "xanchor": "left",
            "yanchor": "bottom",
            "xshift": 3,
            "font": {"size": 10, "color": t["text2"]},
        }
    ]
    return {"data": traces, "layout": layout}


def main_effects(kpi_key: str, scheme) -> dict[str, dict]:
    """Une petite figure par réglage, sur une échelle verticale commune pour comparer les effets."""
    d, t = data.doe(), theme.tokens(scheme)
    factors, unit = d["factors"], d["kpis"][kpi_key]["unit"]
    runs = [r for r in data.runs() if r.get(kpi_key) is not None]
    stats = {}
    for key, f in factors.items():
        levels = sorted({r[f["column"]] for r in runs})
        means, errs = [], []
        for lv in levels:
            vals = [r[kpi_key] for r in runs if r[f["column"]] == lv]
            means.append(statistics.mean(vals))
            errs.append(statistics.stdev(vals) / len(vals) ** 0.5 if len(vals) > 1 else 0)
        stats[key] = (levels, means, errs)
    lo = min(m - e for _, ms, es in stats.values() for m, e in zip(ms, es, strict=True))
    hi = max(m + e for _, ms, es in stats.values() for m, e in zip(ms, es, strict=True))
    pad = 0.12 * (hi - lo or 1)
    figs = {}
    for key, f in factors.items():
        levels, means, errs = stats[key]
        trace = {
            "type": "scatter",
            "mode": "lines+markers",
            "x": [f"{lv:g}".replace(".", ",").replace("-", "−") for lv in levels],
            "y": means,
            "line": {"color": t["line"], "width": 2},
            "marker": {"size": 8, "color": t["line"], "line": {"width": 2, "color": t["surface"]}},
            "error_y": {"type": "data", "array": errs, "color": t["muted"], "thickness": 1, "width": 4},
            "hovertemplate": f"{f['label']} %{{x}} {f['unit']}<br>moyenne %{{y:.3~f}} {unit}<extra></extra>",
        }
        layout = theme.base_layout(
            scheme, showlegend=False, hovermode="closest", margin={"l": 40, "r": 10, "t": 4, "b": 22}
        )
        layout["xaxis"] = theme.xaxis(t, type="category")
        layout["yaxis"] = theme.axis(t, range=[lo - pad, hi + pad], nticks=3)
        figs[key] = {"data": [trace], "layout": layout}
    return figs


def spc_fig(kpi_key: str, scheme) -> dict:
    d, t = data.doe(), theme.tokens(scheme)
    kpi = d["kpis"][kpi_key]
    runs = sorted([r for r in data.runs() if r["run_id"] in kpi["fitted"]], key=lambda r: r["recorded_at"])
    resid = [r[kpi_key] - kpi["fitted"][r["run_id"]] for r in runs]
    mr = [abs(b - a) for a, b in zip(resid, resid[1:], strict=False)]
    center = statistics.mean(resid)
    width = 2.66 * statistics.mean(mr)
    ucl, lcl = center + width, center - width
    out = [not lcl <= v <= ucl for v in resid]
    x = list(range(1, len(runs) + 1))
    traces = [
        {
            "type": "scatter",
            "mode": "lines+markers",
            "x": x,
            "y": resid,
            "line": {"color": t["line"], "width": 1.5},
            "marker": {"size": 5, "color": t["line"]},
            "customdata": [[r["run_id"], r[kpi_key]] for r in runs],
            "hovertemplate": "%{customdata[0]}<br>résidu %{y:.3~f}<br>mesuré %{customdata[1]:.3~f}<extra></extra>",
        },
        {
            "type": "scatter",
            "mode": "markers",
            "x": [xi for xi, o in zip(x, out, strict=True) if o],
            "y": [v for v, o in zip(resid, out, strict=True) if o],
            "name": "Hors limites",
            "marker": {
                "size": 11,
                "symbol": "triangle-up",
                "color": t["alarm"],
                "line": {"width": 1.5, "color": t["surface"]},
            },
            "hoverinfo": "skip",
        },
    ]
    shapes = [
        {
            "type": "line",
            "xref": "paper",
            "x0": 0,
            "x1": 1,
            "y0": y,
            "y1": y,
            "layer": "below",
            "line": {"color": c, "width": 1, "dash": dash},
        }
        for y, c, dash in [
            (center, t["muted"], "solid"),
            (ucl, t["alarm"], "dash"),
            (lcl, t["alarm"], "dash"),
        ]
    ]
    # Séparateurs de séries (DoE1 | DoE2 | DoE3).
    annotations = [
        {
            "xref": "paper",
            "x": 1,
            "y": y,
            "text": lab,
            "showarrow": False,
            "xanchor": "right",
            "yanchor": "bottom",
            "font": {"size": 10, "color": t["text2"]},
        }
        for y, lab in [(ucl, "LSC"), (lcl, "LIC")]
    ]
    for i in range(1, len(runs)):
        if runs[i]["serie"] != runs[i - 1]["serie"]:
            shapes.append(
                {
                    "type": "line",
                    "x0": i + 0.5,
                    "x1": i + 0.5,
                    "yref": "paper",
                    "y0": 0,
                    "y1": 1,
                    "line": {"color": t["axis"], "width": 1},
                }
            )
    for serie in ("DoE1", "DoE2", "DoE3"):
        idx = [i + 1 for i, r in enumerate(runs) if r["serie"] == serie]
        if idx:
            annotations.append(
                {
                    "x": (idx[0] + idx[-1]) / 2,
                    "yref": "paper",
                    "y": 1,
                    "text": serie,
                    "showarrow": False,
                    "yanchor": "bottom",
                    "font": {"size": 10, "color": t["text2"]},
                }
            )
    layout = theme.base_layout(
        scheme,
        showlegend=False,
        hovermode="closest",
        margin={"l": 52, "r": 12, "t": 20, "b": 26},
        shapes=shapes,
        annotations=annotations,
    )
    layout["xaxis"] = theme.xaxis(t, nticks=9)
    layout["yaxis"] = theme.axis(t, title={"text": f"résidu ({kpi['unit']})" if kpi["unit"] else "résidu"}, nticks=5)
    return {"data": traces, "layout": layout}


# Callback -----------------------------------------------------------------------------------------


@callback(
    Output("doe-surface", "figure"),
    Output("doe-pareto", "figure"),
    *[Output(f"doe-main-{k}", "figure") for k in FACTORS],
    Output("doe-spc", "figure"),
    Output("doe-fit", "children"),
    Output("doe-surface-title", "children"),
    Input("doe-kpi", "value"),
    Input("doe-x", "value"),
    Input("doe-y", "value"),
    Input("color-scheme", "computedColorScheme"),
)
def update(kpi_key, fx, fy, scheme):
    d = data.doe()
    if kpi_key not in d["kpis"]:
        kpi_key = next(iter(d["kpis"]))
    if fx not in d["factors"]:
        fx = "P"
    if fy not in d["factors"] or fy == fx:
        fy = next(k for k in d["factors"] if k != fx)
    kpi = d["kpis"][kpi_key]
    badges = [
        dmc.Badge(f"R² = {fmt(kpi['r2'])}", variant="light"),
        dmc.Badge(f"R² ajusté = {fmt(kpi['r2_adj'])}", variant="light", color="gray"),
        dmc.Badge(f"{kpi['n']} runs · {kpi['dof']} ddl", variant="light", color="gray"),
    ]
    title = f"Surface de réponse : {kpi['label'].lower()}"
    return (
        surface_fig(kpi_key, fx, fy, scheme),
        pareto_fig(kpi_key, scheme),
        *(main_effects(kpi_key, scheme)[k] for k in FACTORS),
        spc_fig(kpi_key, scheme),
        badges,
        title,
    )
