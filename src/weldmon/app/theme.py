"""Jetons de couleur (clair / sombre) et mise en page Plotly commune.

Les couleurs de classes suivent la gamme « plasma » (violet -> orange -> magenta) et ont été
validées pour la séparation daltonisme / contraste sur chaque surface (validateur dataviz, toutes
paires) : la couleur suit l'entité (cordon, plasma, projections) dans tous les graphiques et vidéos.
"""

TOKENS = {
    "light": {
        "surface": "#ffffff",
        "page": "#f6f5fa",
        "text": "#16131f",
        "text2": "#5b5768",
        "muted": "#8a8698",
        "grid": "#ebe9f1",
        "axis": "#d9d6e2",
        "setpoint": "#5b5768",
        "band": "rgba(212, 98, 10, 0.10)",
        "weld": "#7e03a8",
        "plasma": "#d4620a",
        "spatter": "#c23f86",
    },
    "dark": {
        "surface": "#17141f",
        "page": "#0f0d16",
        "text": "#f4f2fa",
        "text2": "#b9b4c8",
        "muted": "#85809a",
        "grid": "#262231",
        "axis": "#34303f",
        "setpoint": "#b9b4c8",
        "band": "rgba(221, 106, 30, 0.14)",
        "weld": "#9550d8",
        "plasma": "#dd6a1e",
        "spatter": "#d2448c",
    },
}

# Statuts : échelle fixe, jamais réutilisée pour une série, toujours accompagnée d'un libellé.
STATUS = {"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b"}

# Échelle continue des surfaces de réponse : Plasma (séquentielle perceptuelle, monotone).
PLASMA_SCALE = [
    [0.0, "#0d0887"],
    [0.111, "#46039f"],
    [0.222, "#7201a8"],
    [0.333, "#9c179e"],
    [0.444, "#bd3786"],
    [0.556, "#d8576b"],
    [0.667, "#ed7953"],
    [0.778, "#fb9f3a"],
    [0.889, "#fdca26"],
    [1.0, "#f0f921"],
]

FONT = "Inter, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"


def tokens(scheme: str | None) -> dict:
    return TOKENS["light" if scheme == "light" else "dark"]


def axis(t: dict, **kw) -> dict:
    return {
        "gridcolor": t["grid"],
        "linecolor": t["axis"],
        "zerolinecolor": t["grid"],
        "tickcolor": t["axis"],
        "showline": True,
        "ticks": "outside",
        "ticklen": 4,
        "tickfont": {"size": 11, "color": t["text2"]},
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
