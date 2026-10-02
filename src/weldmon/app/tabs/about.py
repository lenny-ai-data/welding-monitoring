"""Onglet « Méthode & sources » : chaîne de traitement, statut de chaque signal, attribution."""

import dash_mantine_components as dmc
from dash import html

from .. import data
from ..components import point, section_header

EXPLANATIONS = [
    point(
        "Des données réelles",
        "ce démonstrateur rejoue une campagne d'essais publiée par l'Université de Skövde (Suède). Rien n'est "
        "inventé : une grandeur qui n'a pas été mesurée (la puissance laser) est affichée comme consigne.",
    ),
    point(
        "Tout est calculé en amont",
        "préparation des vidéos, entraînement du modèle, calcul des indicateurs et des modèles statistiques sont "
        "réalisés hors ligne sur GPU ; le site ne fait que restituer les résultats, ce qui le rend léger et sûr.",
    ),
    point(
        "Transposable à une ligne réelle",
        "le même principe s'applique en production : une caméra, un modèle embarqué près de la machine et un "
        "écran de supervision qui alerte en temps réel.",
    ),
]


PIPELINE = [
    ("Acquisition", "81 vidéos Photron 6 000–9 000 im/s, plan Box-Behnken 4 facteurs × 3 séries"),
    ("Annotation", "8 vidéos annotées (SAM2 + relecture humaine) : cordon, plasma, projections"),
    ("Modèle IA", "U-Net entraîné sur 6 vidéos, évalué sur 2 vidéos jamais vues"),
    ("Inférence", "59 830 frames segmentées, mesures géométriques par frame"),
    ("Signaux & KPI", "étalonnage px → mm, détection ON/OFF, vitesse, stabilité, alarmes"),
    ("Analyse DoE", "surfaces de réponse quadratiques, effets, cartes de contrôle"),
]

SIGNALS = [
    ("Vidéo haute vitesse", "Mesuré", "Caméra du dataset, transcodée en 512 px (une frame caméra = une frame vidéo)."),
    (
        "Puissance laser",
        "Consigne",
        "Valeur du plan d'expériences, appliquée entre l'allumage et l'extinction "
        "détectés à l'image. Aucun capteur de puissance n'est fourni.",
    ),
    ("Vitesse d'avance — consigne", "Consigne", "Valeur du plan d'expériences."),
    ("Vitesse d'avance — mesurée", "Mesuré (IA)", "Dérivée lissée de la position du front du cordon segmenté."),
    ("Plasma, projections, cordon", "Mesuré (IA)", "Segmentation U-Net de chaque frame, converties en mm / mm²."),
    (
        "Alarmes",
        "Calculé",
        "Pics de plasma > médiane + 3σ (robuste), rafales de projections (quantile 99 % "
        "du dataset), écart de vitesse > 20 % pendant au moins 5 ms.",
    ),
    ("Surfaces de réponse", "Modélisé", "Modèle quadratique complet + effet de série, ajusté sur les 81 runs."),
]

BADGE_COLOR = {"Mesuré": "teal", "Mesuré (IA)": "grape", "Consigne": "gray", "Calculé": "orange", "Modélisé": "indigo"}


def layout() -> html.Div:
    m = data.meta()
    cal, ds, seg = m["calibration"], m["dataset"], data.seg()
    return html.Div(
        className="tab-body about",
        children=[
            section_header(
                "Méthode & sources",
                "Comment ce démonstrateur a été construit, ce qui est mesuré ou modélisé, et d'où viennent les données.",
                EXPLANATIONS,
            ),
            dmc.Paper(
                className="panel",
                children=[
                    html.H3("Chaîne de traitement", className="panel-title"),
                    html.Ol(
                        className="pipeline",
                        children=[
                            html.Li([html.Span(str(i), className="step-n"), html.Strong(title), html.Span(desc)])
                            for i, (title, desc) in enumerate(PIPELINE, start=1)
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
                                    html.H3("Ce qui est mesuré, reconstruit ou modélisé", className="panel-title"),
                                    dmc.Table(
                                        highlightOnHover=True,
                                        children=[
                                            html.Thead(
                                                html.Tr(
                                                    [
                                                        html.Th("Signal", style={"width": "26%"}),
                                                        html.Th("Statut", style={"width": "120px"}),
                                                        html.Th("Origine"),
                                                    ]
                                                )
                                            ),
                                            html.Tbody(
                                                [
                                                    html.Tr(
                                                        [
                                                            html.Td(name),
                                                            html.Td(
                                                                dmc.Badge(
                                                                    status,
                                                                    variant="light",
                                                                    size="sm",
                                                                    className="badge-full",
                                                                    color=BADGE_COLOR[status],
                                                                )
                                                            ),
                                                            html.Td(desc, className="small"),
                                                        ]
                                                    )
                                                    for name, status, desc in SIGNALS
                                                ]
                                            ),
                                        ],
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
                                    html.H3("Étalonnage", className="panel-title"),
                                    html.P(
                                        "Aucune mire n'est fournie : l'échelle est déduite du procédé lui-même. Pour chaque "
                                        "série (le cadrage change d'une série à l'autre), facteur = médiane, sur les runs, du "
                                        "rapport entre la vitesse de consigne et la vitesse du front du cordon à l'image."
                                    ),
                                    dmc.Table(
                                        children=[
                                            html.Thead(
                                                html.Tr(
                                                    [
                                                        html.Th("Série"),
                                                        html.Th("µm / pixel (1024 px)"),
                                                        html.Th("Champ"),
                                                        html.Th("Dispersion"),
                                                    ]
                                                )
                                            ),
                                            html.Tbody(
                                                [
                                                    html.Tr(
                                                        [
                                                            html.Td(serie),
                                                            html.Td(
                                                                f"{1000 * c['mm_per_px_1024']:.1f}".replace(".", ","),
                                                                className="num",
                                                            ),
                                                            html.Td(
                                                                f"{c['field_of_view_mm']:.1f} mm".replace(".", ","),
                                                                className="num",
                                                            ),
                                                            html.Td(
                                                                f"{100 * c['cv']:.1f} %".replace(".", ","),
                                                                className="num",
                                                            ),
                                                        ]
                                                    )
                                                    for serie, c in cal["series"].items()
                                                ]
                                            ),
                                        ]
                                    ),
                                    html.P(
                                        "Les écarts run par run entre vitesse mesurée et consigne sont donc de vraies "
                                        "mesures, à un facteur d'échelle commun près par série.",
                                        className="muted small",
                                    ),
                                ],
                            ),
                            dmc.Paper(
                                className="panel",
                                mt="md",
                                children=[
                                    html.H3("Modèle de segmentation", className="panel-title"),
                                    html.P(
                                        f"U-Net, encodeur {seg['model']['encoder']} pré-entraîné ImageNet, "
                                        f"{str(seg['model']['params_m']).replace('.', ',')} M paramètres, perte Dice + entropie croisée. "
                                        "Découpage par vidéo pour éviter toute fuite entre frames voisines. "
                                        "Le modèle tourne hors ligne (GPU) : l'application ne sert que les résultats."
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
                    html.H3("Données & licence", className="panel-title"),
                    html.P(
                        [
                            html.Em(ds["title"]),
                            f" — {ds['authors']}, {ds['institution']}, {ds['year']}. DOI ",
                            html.A(ds["doi"], href=ds["url"], target="_blank", rel="noopener noreferrer"),
                            ". Licence ",
                            html.A(ds["license"], href=ds["license_url"], target="_blank", rel="noopener noreferrer"),
                            " : usage non commercial, attribution requise.",
                        ]
                    ),
                    html.P(["Modifications : ", ds["changes"]], className="muted small"),
                ],
            ),
        ],
    )
