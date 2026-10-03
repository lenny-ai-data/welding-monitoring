"""Onglet « Segmentation IA » : annotations SAM2 relues vs prédictions du U-Net, frame par frame.

Les images sont composées par la route /overlay (paramètres en liste blanche, cache) ; le
changement de frame ne déclenche aucun callback serveur (URL calculée côté client).
"""

import dash_mantine_components as dmc
from dash import ClientsideFunction, Input, Output, State, callback, clientside_callback, dcc, html

from .. import data, theme
from ..components import point, section_header

# Constantes et textes -----------------------------------------------------------------------------
EXPLANATIONS = [
    point(
        "La segmentation",
        "consiste à attribuer chaque pixel d'une image à une catégorie. Ici trois : le cordon de soudure "
        ", le panache de plasma et les projections de métal fondu.",
    ),
    point(
        "Le modèle IA",
        "un réseau de neurones (U-Net) a appris sur 6 de ces vidéos, puis a été testé sur les 2 qu'il n'avait "
        "jamais vues : ce sont elles qui mesurent ses performances réelles.",
    ),
    point(
        "Prédiction / Désaccords",
        "à gauche l'annotation humaine, délimitée par des experts. C'est la « vérité terrain » qui sert de référence. "
        "A droite, au choix, la prédiction du modèle ou, en rouge, les zones où les deux divergent.",
    ),
    point(
        "L'IoU (Intersection over Union)",
        "mesure le recouvrement entre la zone tracée par l'humain et celle trouvée par IA. "
        "Les projections, qui ne font que quelques pixels, sont les plus difficiles à délimiter.",
    ),
]

# Teinte moyenne de chaque classe (lisible dans les deux thèmes).
CHIP_COLORS = {"weld": "#9550d8", "plasma": "#dd6a1e", "spatter": "#d2448c"}
CLASSES = [("w", "weld", "Cordon"), ("p", "plasma", "Plasma"), ("s", "spatter", "Projections")]


# Composants ---------------------------------------------------------------------------------------


def run_options() -> list[dict]:
    out = []
    for split, title in (("eval", "Évaluation (jamais vues à l'entraînement)"), ("train", "Entraînement")):
        items = []
        for run_id, info in data.seg()["runs"].items():
            if info["split"] != split:
                continue
            r = data.runs_by_id()[run_id]
            items.append(
                {
                    "value": run_id,
                    "label": f"{run_id.replace('_', ' · essai ')} · "
                    f"{r['power_w']:.0f} W · {r['feedrate_mm_s']:.0f} mm/s",
                }
            )
        out.append({"group": title, "items": items})
    return out


def metric(label: str, value: str, sub: str = "") -> dmc.Paper:
    return dmc.Paper(
        className="kpi",
        children=[
            html.Div(label, className="kpi-label"),
            html.Div(value, className="kpi-value"),
            html.Div(sub, className="kpi-sub"),
        ],
    )


def pct(v: float | None) -> str:
    return "-" if v is None else f"{100 * v:.0f} %".replace(".", ",")


def metrics_block() -> html.Div:
    s = data.seg()
    ev, base = s["eval"], s["baseline"]
    sd = ev["spatter_detection"]
    rows = [
        ("mIoU (3 classes)", pct(ev["miou"]), "-"),
        ("IoU cordon", pct(ev["iou"]["weld"]), "non mesurable"),
        ("IoU plasma", pct(ev["iou"]["plasma"]), pct(base["iou"]["plasma"])),
        ("IoU projections", pct(ev["iou"]["spatter"]), pct(base["iou"]["spatter"])),
        ("F1 détection des projections", pct(sd["f1"]), pct(base["spatter_detection"]["f1"])),
        (
            "Corrélation aire plasma (frame à frame)",
            f"{ev['plasma_area_corr']:.2f}".replace(".", ","),
            f"{base['plasma_area_corr']:.2f}".replace(".", ","),
        ),
    ]
    return html.Div(
        [
            dmc.Paper(
                className="panel seg-table",
                children=[
                    html.H3("Modèle U-Net vs vision classique par seuillage", className="panel-title"),
                    dmc.Table(
                        striped=False,
                        highlightOnHover=True,
                        verticalSpacing=4,
                        fz="sm",
                        children=[
                            html.Thead(
                                html.Tr(
                                    [
                                        html.Th("Métrique"),
                                        html.Th("U-Net", className="num"),
                                        html.Th("Baseline seuillage", className="num"),
                                    ]
                                )
                            ),
                            html.Tbody(
                                [
                                    html.Tr(
                                        [html.Td(a), html.Td(b, className="num strong"), html.Td(c, className="num")]
                                    )
                                    for a, b, c in rows
                                ]
                            ),
                        ],
                    ),
                    html.P(
                        className="muted small pre-line",
                        children=(
                            f"U-Net {s['model']['encoder']}, {str(s['model']['params_m']).replace('.', ',')} M paramètres, "
                            f"entraîné sur {len(s['model']['train_runs'])} vidéos.\nBaseline : soustraction de la "
                            f"première image et seuil à {base['threshold']} niveaux de gris, sans détection du cordon."
                        ),
                    ),
                ],
            ),
        ]
    )


# Mise en page -------------------------------------------------------------------------------------


def layout() -> html.Div:
    runs = data.labeled_runs()
    default = "DoE3_19" if "DoE3_19" in runs else runs[0]
    return html.Div(
        className="tab-body",
        children=[
            section_header(
                "Segmentation par IA",
                "Evaluation du modèle de segmentation des éléments d'une soudure : son évaluation passe par une comparaison avec une segmentation manuelle réalisée par des experts.",
                EXPLANATIONS,
            ),
            html.Div(
                className="seg-grid",
                children=[
                    html.Div(
                        className="seg-left",
                        children=[
                            dmc.Paper(
                                className="panel",
                                children=[
                                    html.Div(
                                        className="seg-toolbar",
                                        children=[
                                            dmc.Select(
                                                id="seg-run",
                                                data=run_options(),
                                                value=default,
                                                allowDeselect=False,
                                                w=330,
                                                **{"aria-label": "Vidéo annotée"},
                                            ),
                                            dmc.ChipGroup(
                                                id="seg-classes",
                                                multiple=True,
                                                value=["w", "p", "s"],
                                                children=html.Div(
                                                    [
                                                        dmc.Chip(
                                                            label,
                                                            value=key,
                                                            size="xs",
                                                            variant="light",
                                                            color=CHIP_COLORS[name],
                                                        )
                                                        for key, name, label in CLASSES
                                                    ],
                                                    className="seg-chips",
                                                ),
                                            ),
                                            dmc.SegmentedControl(
                                                id="seg-view",
                                                value="pred",
                                                size="xs",
                                                data=[
                                                    {"value": "pred", "label": "Prédiction"},
                                                    {"value": "diff", "label": "Désaccords"},
                                                ],
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        id="seg-images",
                                        className="seg-images",
                                        children=[
                                            html.Figure(
                                                className="seg-fig",
                                                children=[
                                                    html.Img(id="seg-img-a", alt="Frame annotée"),
                                                    html.Figcaption(id="seg-cap-a"),
                                                ],
                                            ),
                                            html.Figure(
                                                id="seg-fig-b",
                                                className="seg-fig",
                                                children=[
                                                    html.Img(id="seg-img-b", alt="Prédiction du modèle ou désaccords"),
                                                    html.Figcaption(id="seg-cap-b"),
                                                ],
                                            ),
                                            html.Div(
                                                className="seg-opacity",
                                                children=[
                                                    html.Span("Opacité"),
                                                    dmc.Slider(
                                                        id="seg-alpha",
                                                        min=10,
                                                        max=90,
                                                        step=5,
                                                        value=55,
                                                        size="xs",
                                                        w=110,
                                                        label=None,
                                                        **{"aria-label": "Opacité des masques"},
                                                    ),
                                                ],
                                            ),
                                        ],
                                    ),
                                    dmc.Group(
                                        gap="sm",
                                        mt="sm",
                                        wrap="nowrap",
                                        children=[
                                            dmc.Button("Lecture", id="seg-play", size="xs", variant="light", w=90),
                                            html.Div(
                                                style={"flex": 1},
                                                children=[
                                                    dmc.Slider(
                                                        id="seg-k",
                                                        min=0,
                                                        max=data.N_SEG_FRAMES - 1,
                                                        step=1,
                                                        value=default_frame(default),
                                                        label=None,
                                                        size="sm",
                                                        updatemode="drag",
                                                    ),
                                                ],
                                            ),
                                            html.Span(
                                                id="seg-k-label", className="mono muted", style={"minWidth": "150px"}
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            metrics_block(),
                        ],
                    ),
                    html.Div(
                        className="seg-right",
                        children=[
                            dmc.Paper(
                                className="panel",
                                children=[
                                    html.H3("Aire par classe : annotation vs IA", className="panel-title"),
                                    dcc.Graph(
                                        id="seg-areas",
                                        config={"displayModeBar": False, "responsive": True},
                                        style={"height": "440px"},
                                    ),
                                ],
                            ),
                            dmc.Paper(
                                className="panel seg-iou-panel",
                                children=[
                                    html.H3("IoU par image (modèle vs annotation)", className="panel-title"),
                                    dcc.Graph(
                                        id="seg-iou",
                                        className="graph-fill",
                                        config={"displayModeBar": False, "responsive": True},
                                        style={"height": "100%"},
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
            dcc.Store(id="seg-figs"),
            dcc.Interval(id="seg-tick", interval=120, disabled=True),
        ],
    )


# Courbes d'aires et d'IoU -------------------------------------------------------------------------


def rolling_mean(values: list, window: int) -> list:
    """Moyenne glissante centrée qui ignore les valeurs absentes (classe absente des deux cartes)."""
    half, out = window // 2, []
    for i in range(len(values)):
        chunk = [v for v in values[max(0, i - half) : i + half + 1] if v is not None]
        out.append(sum(chunk) / len(chunk) if len(chunk) >= 3 else None)
    return out


def default_frame(run_id: str) -> int:
    """Frame de départ parlante : plasma et projections visibles simultanément dans l'annotation."""
    frames = data.seg()["runs"][run_id]["frames"]
    return max(frames, key=lambda f: (f["gt"]["spatter"] > 0) * 1e6 + f["gt"]["plasma"])["k"]


def area_figs(run_id: str, scheme: str | None) -> dict:
    t = theme.tokens(scheme)
    frames = data.seg()["runs"][run_id]["frames"]
    scale2 = data.meta()["calibration"]["series"][run_id.split("_")[0]]["mm_per_px_512"] ** 2
    x = [f["t_ms"] for f in frames]
    traces, n = [], len(CLASSES)
    layout = theme.base_layout(
        scheme,
        margin={"l": 52, "r": 12, "t": 36, "b": 40},
        showlegend=True,
        hovermode="x unified",
        hoversubplots="axis",
        legend={
            "orientation": "h",
            "y": 1.0,
            "yanchor": "bottom",
            "x": 1,
            "xanchor": "right",
            "font": {"color": t["text2"]},
        },
    )
    layout["xaxis"] = theme.xaxis(t, title={"text": "Temps de procédé (ms)"}, anchor=f"y{n}")
    annotations = []
    for i, (_, name, label) in enumerate(CLASSES, start=1):
        top = 0.93 - 0.93 * (i - 1) / n
        domain = [top - 0.93 / n + 0.07, top - 0.03]
        axis_name = "yaxis" if i == 1 else f"yaxis{i}"
        layout[axis_name] = theme.axis(
            t, domain=domain, anchor="x", nticks=3, title={"text": "mm²", "standoff": 2}, fixedrange=True
        )
        annotations.append(
            {
                "text": label,
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
        yref = "y" if i == 1 else f"y{i}"
        traces.append(
            {
                "x": x,
                "y": [f["gt"][name] * scale2 for f in frames],
                "yaxis": yref,
                "type": "scatter",
                "mode": "lines",
                "name": "Annotation",
                "legendgroup": "gt",
                "showlegend": i == 1,
                "line": {"color": t["setpoint"], "width": 1.5, "dash": "dot"},
                "hovertemplate": f"{label} annoté : %{{y:.2f}} mm²<extra></extra>",
            }
        )
        traces.append(
            {
                "x": x,
                "y": [f["pred"][name] * scale2 for f in frames],
                "yaxis": yref,
                "type": "scatter",
                "mode": "lines",
                "name": f"IA · {label.lower()}",
                "line": {"color": t[name], "width": 2},
                "hovertemplate": f"{label} IA : %{{y:.2f}} mm²<extra></extra>",
            }
        )
    layout["annotations"] = annotations

    iou_layout = theme.base_layout(
        scheme,
        margin={"l": 52, "r": 12, "t": 28, "b": 40},
        showlegend=True,
        hovermode="x unified",
        legend={"orientation": "h", "y": 1.02, "yanchor": "bottom", "x": 0, "font": {"color": t["text2"]}},
    )
    iou_layout["xaxis"] = theme.xaxis(t, title={"text": "Temps de procédé (ms)"})
    iou_layout["yaxis"] = theme.axis(t, range=[0, 1.05], tickformat=".0%", nticks=4, fixedrange=True)
    # Moyenne glissante sur 9 frames annotées (~36 frames caméra) : l'IoU d'objets minuscules
    # (projections) varie trop d'une frame à l'autre pour être lisible brute.
    iou_traces = [
        {
            "x": x,
            "y": rolling_mean([f["iou"][name] for f in frames], 9),
            "type": "scatter",
            "mode": "lines",
            "name": label,
            "connectgaps": False,
            "line": {"color": t[name], "width": 2},
            "hovertemplate": f"{label} : %{{y:.0%}}<extra></extra>",
        }
        for _, name, label in CLASSES
    ]
    return {
        "areas": {"data": traces, "layout": layout},
        "iou": {"data": iou_traces, "layout": iou_layout},
        "t_ms": x,
        "frames": [f["frame"] for f in frames],
        "muted": t["muted"],
    }


# Callbacks : courbes côté serveur, images et curseur côté client (assets/seg.js) ------------------


@callback(Output("seg-figs", "data"), Input("seg-run", "value"), Input("color-scheme", "computedColorScheme"))
def load_seg(run_id, scheme):
    if run_id not in data.labeled_runs():
        run_id = data.labeled_runs()[0]
    return area_figs(run_id, scheme)


clientside_callback(
    ClientsideFunction("seg", "render"),
    Output("seg-img-a", "src"),
    Output("seg-img-b", "src"),
    Output("seg-cap-a", "children"),
    Output("seg-cap-b", "children"),
    Output("seg-fig-b", "style"),
    Output("seg-k-label", "children"),
    Output("seg-areas", "figure"),
    Output("seg-iou", "figure"),
    Input("seg-run", "value"),
    Input("seg-view", "value"),
    Input("seg-k", "value"),
    Input("seg-classes", "value"),
    Input("seg-alpha", "value"),
    Input("seg-figs", "data"),
)

clientside_callback(
    ClientsideFunction("seg", "togglePlay"),
    Output("seg-tick", "disabled"),
    Output("seg-play", "children"),
    Input("seg-play", "n_clicks"),
    State("seg-tick", "disabled"),
    prevent_initial_call=True,
)

clientside_callback(
    ClientsideFunction("seg", "advance"),
    Output("seg-k", "value"),
    Input("seg-tick", "n_intervals"),
    State("seg-k", "value"),
    prevent_initial_call=True,
)
