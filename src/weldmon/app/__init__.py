"""Laser Welding Process Monitor — application Dash."""

import os

import dash_mantine_components as dmc
from dash import ALL, ClientsideFunction, Dash, Input, Output, State, clientside_callback, html

from . import security
from .components import icon
from .tabs import about, doe, live, segmentation

TITLE = "Weld Process Monitor — Lenny Jacquinot"
CONTACT_URL = os.environ.get("WELDMON_CONTACT_URL", "https://www.linkedin.com/in/lenny-jacquinot-ai-engineer/")
DESCRIPTION = (
    "Monitoring de soudage laser rejoué en temps réel : vidéo haute vitesse, segmentation IA "
    "du plasma, des projections et du cordon, et analyse de plan d'expériences."
)


SECTIONS = [
    # (clé, libellé, icône Lucide, constructeur)
    ("live", "Monitoring live", "activity", live.layout),
    ("seg", "Segmentation IA", "scan-eye", segmentation.layout),
    ("doe", "Analyse DoE", "chart-scatter", doe.layout),
    ("about", "Méthode & sources", "book-open", about.layout),
]
NAV_WIDTH = {"expanded": 240, "collapsed": 72}


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
                            # Sur mobile, la barre latérale est masquée : le logo reste visible ici.
                            dmc.Box(html.Span(className="brand-mark", **{"aria-hidden": "true"}), hiddenFrom="sm"),
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


def tip(tip_id, label: str, child) -> dmc.Tooltip:
    """Infobulle à droite, active seulement quand la barre est repliée (icônes seules)."""
    return dmc.Tooltip(id=tip_id, label=label, position="right", withArrow=True, disabled=True, children=child)


def navbar() -> dmc.AppShellNavbar:
    return dmc.AppShellNavbar(
        className="navbar",
        children=[
            # Logo seul : le nom et la baseline sont dans l'en-tête, alignés sur le contenu.
            html.Div(className="nav-top", children=html.Span(className="brand-mark", **{"aria-hidden": "true"})),
            html.Nav(
                className="nav-links",
                children=[
                    tip(
                        {"type": "nav-tip", "index": key},
                        label,
                        dmc.NavLink(
                            id={"type": "nav", "index": key},
                            label=label,
                            leftSection=icon(icon_name, 18),
                            active=key == "live",
                            variant="light",
                            className="nav-link",
                            n_clicks=0,
                        ),
                    )
                    for key, label, icon_name, _ in SECTIONS
                ],
            ),
            html.Div(
                className="nav-bottom",
                children=[
                    html.Div(
                        className="nav-contact nav-text",
                        children=[
                            html.Div("Le même suivi sur votre ligne ?", className="nav-contact-title"),
                            html.P(
                                "Vision industrielle, IA embarquée, monitoring procédé et plans d'expériences : "
                                "du prototype au déploiement sur site."
                            ),
                        ],
                    ),
                    tip(
                        "contact-tip",
                        "Contacter l'auteur",
                        html.A(
                            [icon("mail", 16), html.Span("Contacter l'auteur", className="nav-text")],
                            href=CONTACT_URL,
                            className="cta-button nav-cta",
                            target="_blank",
                            rel="noopener noreferrer",
                            **{"aria-label": "Contacter l'auteur"},
                        ),
                    ),
                    dmc.ActionIcon(
                        id="nav-collapse",
                        variant="subtle",
                        color="gray",
                        size="lg",
                        visibleFrom="sm",
                        className="nav-collapse",
                        n_clicks=0,
                        children=[icon("panel-left-close", 18), icon("panel-left-open", 18)],
                        **{"aria-label": "Replier / déplier le menu"},
                    ),
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
            layout="alt",  # barre latérale pleine hauteur : l'en-tête s'aligne sur le contenu
            header={"height": 64},
            navbar={"width": NAV_WIDTH["expanded"], "breakpoint": "sm", "collapsed": {"mobile": True}},
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


# Navigation (côté client) : section affichée, lien actif, barre repliée / dépliée, menu mobile,
# vidéo mise en pause quand on quitte le monitoring.
clientside_callback(
    ClientsideFunction("nav", "route"),
    *[Output(f"section-{key}", "style") for key, *_ in SECTIONS],
    Output({"type": "nav", "index": ALL}, "active"),
    Output({"type": "nav-tip", "index": ALL}, "disabled"),
    Output("contact-tip", "disabled"),
    Output("app-shell", "navbar"),
    Output("app-shell", "className"),
    Output("nav-burger", "opened"),
    Input({"type": "nav", "index": ALL}, "n_clicks"),
    Input("nav-burger", "opened"),
    Input("nav-collapse", "n_clicks"),
    State("app-shell", "navbar"),
)
