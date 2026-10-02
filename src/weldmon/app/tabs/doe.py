"""Onglet « Analyses » : fenêtre de procédé à partir des 81 runs (3 séries Box-Behnken).

Les surfaces sont recalculées ici à partir des coefficients exportés (Python pur, sans numpy).
"""

import statistics

import dash_mantine_components as dmc
from dash import Input, Output, callback, dcc, html

from .. import data, theme
from ..components import point, section_header

EXPLANATIONS = [
    point(
        "Le plan d'expériences (DoE)",
        "plutôt que de tester toutes les combinaisons de réglages, on choisit un petit nombre d'essais bien "
        "répartis (plan Box-Behnken : 27 essais) pour étudier 4 réglages : la puissance du laser, la vitesse "
        "d'avance, la défocalisation (hauteur du point focal) et la translation PFO (inclinaison du faisceau). "
        "Le plan a été répété 3 fois : séries DoE1, DoE2 et DoE3, soit 81 soudures.",
    ),
    point(
        "Les indicateurs",
        "chaque soudure est résumée par des mesures issues de la vision IA : taille et stabilité du plasma, "
        "projections, largeur du cordon, écart de vitesse. Choisissez-en un dans la liste.",
    ),
    point(
        "La surface de réponse",
        "un modèle statistique prédit l'indicateur pour toute combinaison de deux réglages (les deux autres au "
        "milieu de leur plage). Violet foncé = valeurs élevées ; les points sont les essais réellement faits.",
    ),
    point(
        "Les effets standardisés",
        "quels réglages ont un impact statistiquement démontré (barres violettes, au-delà du seuil p = 0,05) et "
        "lesquels se confondent avec le bruit de mesure (barres grises).",
    ),
    point(
        "Les effets principaux",
        "comment l'indicateur varie en moyenne lorsqu'on change un seul réglage ; les barres d'erreur traduisent "
        "l'incertitude.",
    ),
    point(
        "La carte de contrôle",
        "ce que les réglages n'expliquent pas, soudure après soudure dans l'ordre chronologique : un point hors "
        "des limites rouges signale un essai anormal, à investiguer.",
    ),
    point(
        "L'énergie linéique",
        "puissance ÷ vitesse : l'énergie déposée par millimètre de soudure, repère classique des soudeurs.",
    ),
]

GRID = 41


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
                "Quels réglages de la machine influencent la qualité ? Modèles statistiques ajustés sur les 81 "
                "soudures, à réévaluer au fil de la production.",
                EXPLANATIONS,
            ),
            dmc.Paper(
                className="panel",
                children=[
                    dmc.Group(
                        align="flex-end",
                        wrap="wrap",
                        gap="md",
                        children=[
                            dmc.Select(
                                id="doe-kpi",
                                label="Indicateur",
                                data=kpi_opts,
                                value="weld_width_mm",
                                allowDeselect=False,
                                w=320,
                            ),
                            dmc.Select(
                                id="doe-x", label="Axe horizontal", data=fac_opts, value="P", allowDeselect=False, w=230
                            ),
                            dmc.Select(
                                id="doe-y", label="Axe vertical", data=fac_opts, value="v", allowDeselect=False, w=230
                            ),
                            html.Div(id="doe-fit", className="fit-badges"),
                        ],
                    ),
                ],
            ),
            dmc.Grid(
                gutter="md",
                mt="xs",
                children=[
                    dmc.GridCol(
                        span={"base": 12, "lg": 7},
                        children=[
                            dmc.Paper(
                                className="panel",
                                children=[
                                    html.H3(id="doe-surface-title", className="panel-title"),
                                    dcc.Graph(
                                        id="doe-surface",
                                        config={"displayModeBar": False, "responsive": True},
                                        style={"height": "440px"},
                                    ),
                                    html.P(
                                        "Surface du modèle quadratique (moyenne des 3 séries), autres facteurs au centre "
                                        "du domaine. Points : essais réalisés à ces réglages (valeur mesurée au survol).",
                                        className="muted small",
                                    ),
                                ],
                            ),
                        ],
                    ),
                    dmc.GridCol(
                        span={"base": 12, "lg": 5},
                        children=[
                            dmc.Paper(
                                className="panel",
                                children=[
                                    html.H3("Effets standardisés (|t| de Student)", className="panel-title"),
                                    dcc.Graph(
                                        id="doe-pareto",
                                        config={"displayModeBar": False, "responsive": True},
                                        style={"height": "440px"},
                                    ),
                                    html.P(
                                        "« Série » est un facteur de bloc : il absorbe les écarts entre campagnes "
                                        "(réglages machine, mais aussi éclairage et cadrage différents, alors que le "
                                        "modèle IA n'a été entraîné que sur DoE3). Le traiter ainsi évite de biaiser "
                                        "les effets des quatre facteurs du plan.",
                                        className="muted small",
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
                    html.H3("Effets principaux (moyenne par niveau, 81 runs)", className="panel-title"),
                    dcc.Graph(
                        id="doe-main", config={"displayModeBar": False, "responsive": True}, style={"height": "250px"}
                    ),
                ],
            ),
            dmc.Grid(
                gutter="md",
                mt="xs",
                children=[
                    dmc.GridCol(
                        span={"base": 12, "lg": 7},
                        children=[
                            dmc.Paper(
                                className="panel",
                                children=[
                                    html.H3(
                                        "Carte de contrôle des résidus (I-MR), dans l'ordre réel de soudage",
                                        className="panel-title",
                                    ),
                                    dcc.Graph(
                                        id="doe-spc",
                                        config={"displayModeBar": False, "responsive": True},
                                        style={"height": "300px"},
                                    ),
                                    html.P(
                                        "Résidu = mesure − prédiction du modèle : ce qui reste une fois l'effet des "
                                        "réglages retiré, c'est-à-dire la variabilité propre du procédé. Limites à "
                                        "±2,66 × étendue mobile moyenne.",
                                        className="muted small",
                                    ),
                                ],
                            ),
                        ],
                    ),
                    dmc.GridCol(
                        span={"base": 12, "lg": 5},
                        children=[
                            dmc.Paper(
                                className="panel",
                                children=[
                                    html.H3("Énergie linéique vs indicateur", className="panel-title"),
                                    dcc.Graph(
                                        id="doe-energy",
                                        config={"displayModeBar": False, "responsive": True},
                                        style={"height": "300px"},
                                    ),
                                    html.P(
                                        "E = P / v (J/mm). Chaque point est un run ; survol pour le détail.",
                                        className="muted small",
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


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
            "colorscale": theme.VIOLET_SCALE,
            "contours": {"coloring": "heatmap", "showlabels": False},
            "line": {"width": 0.5, "color": "rgba(255,255,255,0.35)"},
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
        scheme, showlegend=False, hovermode="closest", margin={"l": 64, "r": 10, "t": 10, "b": 48}
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
            "marker": {"color": [t["line"] if s else t["muted"] for s in sig], "cornerradius": 3},
            "customdata": [[e["coef"], e["p"]] for e in eff],
            "hovertemplate": "%{y}<br>|t| = %{x:.2f} · coef %{customdata[0]:.4~f} · p = %{customdata[1]:.3f}"
            "<extra></extra>",
        }
    ]
    layout = theme.base_layout(
        scheme, showlegend=False, hovermode="closest", bargap=0.35, margin={"l": 12, "r": 16, "t": 24, "b": 44}
    )
    layout["xaxis"] = theme.axis(t, title={"text": "|t| (violet : significatif, p < 0,05)"}, rangemode="tozero")
    layout["yaxis"] = theme.axis(t, showgrid=False, ticks="", automargin=True)
    layout["shapes"] = [
        {
            "type": "line",
            "x0": kpi["t_crit"],
            "x1": kpi["t_crit"],
            "yref": "paper",
            "y0": 0,
            "y1": 1,
            "line": {"color": t["text2"], "width": 1, "dash": "dot"},
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


def main_effects_fig(kpi_key: str, scheme) -> dict:
    d, t = data.doe(), theme.tokens(scheme)
    factors, unit = d["factors"], d["kpis"][kpi_key]["unit"]
    runs = [r for r in data.runs() if r.get(kpi_key) is not None]
    traces, layout = (
        [],
        theme.base_layout(scheme, showlegend=False, hovermode="closest", margin={"l": 52, "r": 10, "t": 26, "b": 44}),
    )
    n = len(factors)
    all_y = []
    for i, f in enumerate(factors.values(), start=1):
        levels = sorted({r[f["column"]] for r in runs})
        means, errs = [], []
        for lv in levels:
            vals = [r[kpi_key] for r in runs if r[f["column"]] == lv]
            means.append(statistics.mean(vals))
            errs.append(statistics.stdev(vals) / len(vals) ** 0.5 if len(vals) > 1 else 0)
        all_y += [m + e for m, e in zip(means, errs, strict=True)] + [m - e for m, e in zip(means, errs, strict=True)]
        xa, ya = ("x", "y") if i == 1 else (f"x{i}", f"y{i}")
        traces.append(
            {
                "type": "scatter",
                "mode": "lines+markers",
                "x": levels,
                "y": means,
                "xaxis": xa,
                "yaxis": ya,
                "line": {"color": t["line"], "width": 2},
                "marker": {"size": 8, "color": t["line"], "line": {"width": 2, "color": t["surface"]}},
                "error_y": {"type": "data", "array": errs, "color": t["muted"], "thickness": 1, "width": 4},
                "hovertemplate": f"{f['label']} %{{x}} {f['unit']}<br>moyenne %{{y:.3~f}} {unit}<extra></extra>",
            }
        )
        dom = [(i - 1) / n + 0.04, i / n - 0.02]
        layout["xaxis" if i == 1 else f"xaxis{i}"] = theme.axis(
            t, domain=dom, anchor=ya, tickvals=levels, title={"text": f"{f['label']} ({f['unit']})"}
        )
    lo, hi = min(all_y), max(all_y)
    pad = 0.1 * (hi - lo or 1)
    for i in range(1, n + 1):
        layout["yaxis" if i == 1 else f"yaxis{i}"] = theme.axis(
            t,
            anchor="x" if i == 1 else f"x{i}",
            range=[lo - pad, hi + pad],
            showticklabels=i == 1,
            matches=None if i == 1 else "y",
            title={"text": unit if i == 1 else ""},
            nticks=4,
        )
    return {"data": traces, "layout": layout}


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
            "line": {"color": t["weld"], "width": 1.5},
            "marker": {"size": 6, "color": t["weld"]},
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
                "color": theme.STATUS["critical"],
                "line": {"width": 2, "color": t["surface"]},
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
            "line": {"color": c, "width": 1, "dash": dash},
        }
        for y, c, dash in [
            (center, t["text2"], "solid"),
            (ucl, theme.STATUS["critical"], "dash"),
            (lcl, theme.STATUS["critical"], "dash"),
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
        margin={"l": 52, "r": 12, "t": 22, "b": 40},
        shapes=shapes,
        annotations=annotations,
    )
    layout["xaxis"] = theme.axis(t, title={"text": "Run (ordre chronologique de la campagne)"})
    layout["yaxis"] = theme.axis(t, title={"text": f"résidu ({kpi['unit']})" if kpi["unit"] else "résidu"})
    return {"data": traces, "layout": layout}


def energy_fig(kpi_key: str, scheme) -> dict:
    d, t = data.doe(), theme.tokens(scheme)
    kpi = d["kpis"][kpi_key]
    runs = [r for r in data.runs() if r.get(kpi_key) is not None]
    traces = [
        {
            "type": "scatter",
            "mode": "markers",
            "x": [r["line_energy_j_mm"] for r in runs],
            "y": [r[kpi_key] for r in runs],
            "marker": {"size": 8, "color": t["line"], "opacity": 0.85, "line": {"width": 1, "color": t["surface"]}},
            "customdata": [[r["run_id"], r["power_w"], r["feedrate_mm_s"]] for r in runs],
            "hovertemplate": "%{customdata[0]} · %{customdata[1]:.0f} W · %{customdata[2]:.0f} mm/s<br>"
            "E = %{x:.1f} J/mm<br>%{y:.3~f}<extra></extra>",
        }
    ]
    layout = theme.base_layout(
        scheme, showlegend=False, hovermode="closest", margin={"l": 52, "r": 12, "t": 10, "b": 44}
    )
    layout["xaxis"] = theme.axis(t, title={"text": "Énergie linéique (J/mm)"})
    layout["yaxis"] = theme.axis(t, title={"text": kpi["unit"] or kpi["label"]})
    return {"data": traces, "layout": layout}


@callback(
    Output("doe-surface", "figure"),
    Output("doe-pareto", "figure"),
    Output("doe-main", "figure"),
    Output("doe-spc", "figure"),
    Output("doe-energy", "figure"),
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
        dmc.Badge(f"R² = {fmt(kpi['r2'])}", variant="light", color="grape"),
        dmc.Badge(f"R² ajusté = {fmt(kpi['r2_adj'])}", variant="light", color="gray"),
        dmc.Badge(f"{kpi['n']} runs · {kpi['dof']} ddl", variant="light", color="gray"),
    ]
    significant = [pretty_term(e["term"]) for e in sorted(kpi["effects"], key=lambda e: -abs(e["t"])) if e["p"] < 0.05]
    badges.append(
        html.Span(
            "Effets significatifs : " + (", ".join(significant) if significant else "aucun (p < 0,05)"),
            className="muted small",
        )
    )
    title = f"Surface de réponse — {kpi['label']}"
    return (
        surface_fig(kpi_key, fx, fy, scheme),
        pareto_fig(kpi_key, scheme),
        main_effects_fig(kpi_key, scheme),
        spc_fig(kpi_key, scheme),
        energy_fig(kpi_key, scheme),
        badges,
        title,
    )
