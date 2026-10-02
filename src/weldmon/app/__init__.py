"""Laser Welding Process Monitor — application Dash."""

import dash_mantine_components as dmc
from dash import ALL, ClientsideFunction, Dash, Input, Output, State, clientside_callback, html

from . import data, security
from .components import icon
from .tabs import about, doe, live, segmentation

TITLE = "Weld Process Monitor — Lenny Jacquinot"
DESCRIPTION = (
    "Monitoring de soudage laser rejoué en temps réel : vidéo haute vitesse, segmentation IA "
    "du plasma, des projections et du cordon, et analyse de plan d'expériences."
)


SECTIONS = [
    # (clé, libellé, icône Lucide, constructeur)
    ("live", "Monitoring live", "activity", live.layout),
    ("seg", "Vidéo & masques IA", "scan-eye", segmentation.layout),
    ("doe", "Analyse DoE", "chart-scatter", doe.layout),
    ("about", "Méthode & sources", "book-open", about.layout),
]


def header() -> dmc.AppShellHeader:
    return dmc.AppShellHeader(
        className="header",
        children=[
            html.Div(
                className="header-inner",
                children=[
                    html.Div(
                        className="brand",
                        children=[
                            dmc.Burger(
                                id="nav-burger",
                                opened=False,
                                size="sm",
                                hiddenFrom="sm",
                                **{"aria-label": "Ouvrir le menu"},
                            ),
                            html.Span(className="brand-mark", **{"aria-hidden": "true"}),
                            html.Div(
                                [
                                    html.Div("Weld Process Monitor", className="brand-title"),
                                    html.Div("Lenny Jacquinot · IA & Data pour l'industrie", className="brand-sub"),
                                ]
                            ),
                        ],
                    ),
                    html.Div(
                        className="header-right",
                        children=[
                            html.Span("● REPLAY · données réelles", className="pill-live"),
                            dmc.ColorSchemeToggle(
                                id="color-scheme",
                                size="lg",
                                variant="default",
                                radius="md",
                                lightIcon=icon("sun"),
                                darkIcon=icon("moon"),
                                **{"aria-label": "Basculer thème clair / sombre"},
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


def navbar() -> dmc.AppShellNavbar:
    ds = data.meta()["dataset"]
    return dmc.AppShellNavbar(
        className="navbar",
        children=[
            html.Nav(
                className="nav-links",
                children=[
                    dmc.NavLink(
                        id={"type": "nav", "index": key},
                        label=label,
                        leftSection=icon(icon_name, 18),
                        active=key == "live",
                        variant="light",
                        className="nav-link",
                        n_clicks=0,
                    )
                    for key, label, icon_name, _ in SECTIONS
                ],
            ),
            html.Div(
                className="nav-footer",
                children=[
                    html.Div("Données", className="kpi-label"),
                    html.A(f"{ds['institution']} · Zenodo", href=ds["url"], target="_blank", rel="noopener noreferrer"),
                    html.Div(f"Licence {ds['license']}", className="muted"),
                ],
            ),
        ],
    )


def sections() -> html.Div:
    return html.Div(
        className="sections",
        children=[
            html.Section(
                build(), id=f"section-{key}", className="section", style={} if key == "live" else {"display": "none"}
            )
            for key, _, _, build in SECTIONS
        ],
    )


def create_app() -> Dash:
    app = Dash(
        __name__,
        title=TITLE,
        update_title=None,
        serve_locally=True,
        compress=False,  # compression déléguée au reverse proxy
        enable_mcp=False,  # Dash 4 : jamais d'endpoint MCP exposé publiquement
        meta_tags=[
            {"name": "viewport", "content": "width=device-width, initial-scale=1"},
            {"name": "description", "content": DESCRIPTION},
            {"name": "robots", "content": "index, follow"},
        ],
    )
    app.layout = dmc.MantineProvider(
        defaultColorScheme="dark",
        theme={
            "primaryColor": "grape",
            "fontFamily": "Inter, system-ui, sans-serif",
            "fontFamilyMonospace": "'JetBrains Mono', ui-monospace, monospace",
            "defaultRadius": "md",
            "headings": {"fontFamily": "Inter, system-ui, sans-serif"},
        },
        children=dmc.AppShell(
            id="app-shell",
            header={"height": 64},
            navbar={"width": 236, "breakpoint": "sm", "collapsed": {"mobile": True}},
            padding="md",
            children=[
                header(),
                navbar(),
                dmc.AppShellMain(className="main", children=[sections()]),
            ],
        ),
    )
    security.install(app, app.csp_hashes())
    return app


# Navigation (côté client) : section affichée, lien actif, menu mobile replié, vidéo mise en pause
# quand on quitte le monitoring.
clientside_callback(
    ClientsideFunction("nav", "route"),
    *[Output(f"section-{key}", "style") for key, *_ in SECTIONS],
    Output({"type": "nav", "index": ALL}, "active"),
    Output("app-shell", "navbar"),
    Output("nav-burger", "opened"),
    Input({"type": "nav", "index": ALL}, "n_clicks"),
    Input("nav-burger", "opened"),
    State("app-shell", "navbar"),
)
