"""Onglet « Méthode & sources » : chaîne de traitement, statut de chaque signal, attribution."""

import dash_mantine_components as dmc
from dash import html

from .. import data
from ..components import point, section_header

# Textes -------------------------------------------------------------------------------------------
EXPLANATIONS = [
    point(
        "Des données réelles",
        "ce démonstrateur rejoue une campagne d'essais publiée par l'Université de Skövde (Suède).",
    ),
    point(
        "Tout est calculé en amont",
        "préparation des vidéos, entraînement du modèle, calcul des indicateurs et des modèles statistiques sont "
        "réalisés hors ligne sur GPU. Le site affiche seulement les résultats, sans calcul lourd à la volée.",
    ),
    point(
        "Transposable à une ligne réelle",
        "le même principe s'applique en production : une caméra, un modèle embarqué près de la machine et un "
        "écran de supervision qui alerte en temps réel.",
    ),
]


PIPELINE = [
    ("Acquisition", "81 vidéos Photron 6 000 à 9 000 im/s, plan Box-Behnken 4 facteurs × 3 séries"),
    ("Annotation", "8 vidéos annotées (SAM2 + relecture humaine) : cordon, plasma, projections"),
    ("Modèle IA", "U-Net entraîné sur 6 vidéos (dont 1 de validation), évalué sur 2 vidéos jamais vues"),
    ("Inférence", "59 830 frames segmentées, mesures géométriques par frame"),
    ("Signaux & KPI", "conversion pixels en mm, détection ON/OFF, vitesse, stabilité, alarmes"),
    ("Suivi & analyses", "verdict par soudure, surfaces de réponse, effets, cartes de contrôle"),
]

SIGNALS = [
    ("Vidéo haute vitesse", "Mesuré", "Caméra du dataset, transcodée en 512 px (une frame caméra = une frame vidéo)."),
    (
        "Puissance laser",
        "Consigne",
        "Valeur du plan d'expériences, appliquée entre l'allumage et l'extinction "
        "détectés à l'image. Aucun capteur de puissance n'est fourni.",
    ),
    ("Vitesse d'avance (consigne)", "Consigne", "Valeur du plan d'expériences."),
    ("Vitesse d'avance (mesurée)", "Mesuré (IA)", "Dérivée lissée de la position du front du cordon segmenté."),
    ("Plasma, projections, cordon", "Mesuré (IA)", "Segmentation U-Net de chaque frame, converties en mm / mm²."),
    (
        "Alarmes",
        "Calculé",
        "Pics de plasma > médiane + 3σ (robuste), rafales de projections (quantile 99 % "
        "du dataset), écart de vitesse > 20 % pendant au moins 5 ms.",
    ),
    (
        "Verdict d'une soudure",
        "Calculé",
        "OK jusqu'à 10 alarmes, OK avec warning jusqu'à 15, NOK au-delà ou dès un écart de vitesse soutenu.",
    ),
    ("Surfaces de réponse", "Modélisé", "Modèle quadratique complet + effet de série, ajusté sur les 81 runs."),
]

BADGE_CLASS = {
    "Mesuré": "mesure",
    "Mesuré (IA)": "ia",
    "Consigne": "consigne",
    "Calculé": "calcule",
    "Modélisé": "modelise",
}


# Panneaux -----------------------------------------------------------------------------------------


def pct(v: float) -> str:
    return f"{100 * v:.0f} %"


def model_panel() -> html.Div:
    seg = data.seg()
    model, ev = seg["model"], seg["eval"]
    rows = [
        ("Architecture", f"U-Net, encodeur {model['encoder']} pré-entraîné ImageNet"),
        ("Taille", f"{str(model['params_m']).replace('.', ',')} M paramètres"),
        ("Entrée", f"image {model['input']}"),
        ("Apprentissage", f"{len(model['train_runs'])} vidéos annotées, perte Dice + entropie croisée"),
        ("Validation", ", ".join(model["val_runs"]).replace("_", " · essai ")),
        ("Évaluation", ", ".join(model["eval_runs"]).replace("_", " · essai ") + " (jamais vues)"),
        (
            "Recouvrement (IoU)",
            f"cordon {pct(ev['iou']['weld'])} · plasma {pct(ev['iou']['plasma'])} · "
            f"projections {pct(ev['iou']['spatter'])}",
        ),
        (
            "Projections détectées",
            f"{pct(ev['spatter_detection']['recall'])} (F1 {pct(ev['spatter_detection']['f1'])})",
        ),
    ]
    return html.Div(
        className="panel",
        children=[
            html.H3("Modèle de segmentation", className="panel-title"),
            html.P(
                "Un réseau de neurones repère, sur chaque image, le cordon, le plasma et les projections. Découpage "
                "par vidéo pour éviter toute fuite entre images voisines. Le modèle tourne hors ligne (GPU), "
                "l'application ne sert que les résultats."
            ),
            html.Dl([item for k, v in rows for item in (html.Dt(k), html.Dd(v))], className="params-grid model-grid"),
        ],
    )


def signals_panel() -> html.Div:
    return html.Div(
        className="panel",
        children=[
            html.H3("Ce qui est mesuré, calculé ou modélisé", className="panel-title"),
            dmc.Table(
                highlightOnHover=True,
                verticalSpacing=6,
                children=[
                    html.Thead(
                        html.Tr(
                            [
                                html.Th("Signal", style={"width": "28%"}),
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
                                    html.Td(html.Span(status, className=f"status-badge sb-{BADGE_CLASS[status]}")),
                                    html.Td(desc, className="small"),
                                ]
                            )
                            for name, status, desc in SIGNALS
                        ]
                    ),
                ],
            ),
        ],
    )


# Mise en page -------------------------------------------------------------------------------------


def layout() -> html.Div:
    ds = data.meta()["dataset"]
    return html.Div(
        className="tab-body about",
        children=[
            section_header(
                "Méthode & sources",
                "Comment ce démonstrateur a été construit, ce qui est mesuré ou modélisé, et d'où viennent les données.",
                EXPLANATIONS,
                opened=True,
            ),
            html.Div(
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
            html.Div([model_panel(), signals_panel()], className="about-grid"),
            html.Div(
                className="panel",
                children=[
                    html.H3("Données & licence", className="panel-title"),
                    html.P(
                        [
                            html.Em(ds["title"]),
                            f", {ds['authors']}, {ds['institution']}, {ds['year']}. DOI ",
                            html.A(ds["doi"], href=ds["url"], target="_blank", rel="noopener noreferrer"),
                            ". Licence ",
                            html.A(ds["license"], href=ds["license_url"], target="_blank", rel="noopener noreferrer"),
                            ".",
                        ]
                    ),
                    html.P(["Modifications : ", ds["changes"]], className="muted small"),
                    html.P(
                        "Démonstrateur réalisé à titre personnel, sans usage commercial des données.",
                        className="muted small",
                    ),
                ],
            ),
        ],
    )
