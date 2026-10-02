"""Jetons de couleur (clair / sombre) et mise en page Plotly commune.

Identité visuelle : un violet unique (#8C18CC) et ses nuances. Les courbes de procédé sont
monochromes violettes ; la couleur chaude est réservée aux limites et alarmes (doré = vigilance,
rouge = alarme). Les classes de segmentation (cordon, plasma, projections) gardent leurs couleurs
catégorielles, validées pour la séparation daltonisme / contraste sur chaque surface (validateur
dataviz) : la couleur suit l'entité dans tous les graphiques et vidéos.
"""

BRAND = "#8c18cc"

# Nuances du violet de marque (Mantine attend 10 tons, du plus clair au plus foncé).
BRAND_SHADES = [
    "#f6ecfc",
    "#ead6fb",
    "#d4acf4",
    "#bd80ee",
    "#a95ae8",
    "#9c3fe3",
    "#8c18cc",
    "#7612ad",
    "#600e8d",
    "#4a0a6d",
]

TOKENS = {
    "light": {
        "surface": "#ffffff",
        "page": "#f5f3f9",
        "text": "#1a1430",
        "text2": "#5d566f",
        "muted": "#6b6480",
        "grid": "#ece8f3",
        "axis": "#ddd7e8",
        "line": "#7a16b5",
        "line_raw": "rgba(122, 22, 181, 0.35)",
        "fill": "rgba(122, 22, 181, 0.10)",
        "band": "rgba(122, 22, 181, 0.07)",
        "band_edge": "rgba(122, 22, 181, 0.32)",
        "cursor": "#1a1430",
        "ring": "#8c18cc",
        "gold": "#b07c07",
        "alarm": "#c8323c",
        "setpoint": "#5d566f",
        "weld": "#7e03a8",
        "plasma": "#d4620a",
        "spatter": "#c23f86",
    },
    "dark": {
        "surface": "#1a1526",
        "page": "#100d18",
        "text": "#ece8f7",
        "text2": "#b3abc9",
        "muted": "#8e86a6",
        "grid": "rgba(236, 232, 247, 0.07)",
        "axis": "#2c2440",
        "line": "#b07cf0",
        "line_raw": "rgba(176, 124, 240, 0.35)",
        "fill": "rgba(176, 124, 240, 0.12)",
        "band": "rgba(176, 124, 240, 0.09)",
        "band_edge": "rgba(176, 124, 240, 0.35)",
        "cursor": "#ece8f7",
        "ring": "#a35bf0",
        "gold": "#e7b84a",
        "alarm": "#f07070",
        "setpoint": "#b3abc9",
        "weld": "#9550d8",
        "plasma": "#dd6a1e",
        "spatter": "#d2448c",
    },
}

# Statuts : échelle fixe, jamais réutilisée pour une série, toujours accompagnée d'une icône et d'un libellé.
STATUS = {"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b"}

# Verdict qualité d'une soudure (suivi & historique) : vert / doré / rouge + icône.
VERDICT = {
    "light": {"ok": "#16803c", "warn": "#a36f00", "nok": "#c8323c"},
    "dark": {"ok": "#4cc47e", "warn": "#e7b84a", "nok": "#f07070"},
}

# Échelle séquentielle des surfaces de réponse : une seule teinte, du clair au foncé.
VIOLET_SCALE = [
    [0.0, "#f6ecfc"],
    [0.2, "#d4acf4"],
    [0.4, "#a95ae8"],
    [0.6, "#8c18cc"],
    [0.8, "#600e8d"],
    [1.0, "#2e0546"],
]

FONT = "Sora, system-ui, -apple-system, 'Segoe UI', sans-serif"


def tokens(scheme: str | None) -> dict:
    return TOKENS["light" if scheme == "light" else "dark"]


def verdict_colors(scheme: str | None) -> dict:
    return VERDICT["light" if scheme == "light" else "dark"]


def axis(t: dict, **kw) -> dict:
    return {
        "gridcolor": t["grid"],
        "linecolor": t["axis"],
        "zerolinecolor": t["grid"],
        "tickcolor": t["axis"],
        "showline": True,
        "ticks": "outside",
        "ticklen": 4,
        "tickfont": {"size": 11, "color": t["muted"]},
        "title": {"font": {"size": 12, "color": t["text2"]}},
        **kw,
    }


def base_layout(scheme: str | None, **kw) -> dict:
    t = tokens(scheme)
    layout = {
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": {"family": FONT, "size": 12, "color": t["text"]},
        "margin": {"l": 56, "r": 16, "t": 28, "b": 40},
        "hoverlabel": {
            "bgcolor": t["surface"],
            "bordercolor": t["axis"],
            "font": {"family": FONT, "color": t["text"], "size": 12},
        },
        "legend": {"orientation": "h", "y": 1.02, "yanchor": "bottom", "x": 0, "font": {"color": t["text2"]}},
        "xaxis": axis(t),
        "yaxis": axis(t),
        "hovermode": "x unified",
        "separators": ", ",
    }
    layout.update(kw)
    return layout
