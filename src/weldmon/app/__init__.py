"""Laser Welding Process Monitor : application Dash."""

import os

import dash_mantine_components as dmc
from dash import ALL, ClientsideFunction, Dash, Input, Output, State, clientside_callback, dcc, html

from . import security, theme
from .components import icon
from .tabs import about, doe, history, process, segmentation

TITLE = "Monitoring Soudage | Lenny Jacquinot"
CONTACT_URL = os.environ.get("WELDMON_CONTACT_URL", "https://www.linkedin.com/in/lenny-jacquinot-ai-engineer/")
DESCRIPTION = (
    "Monitoring de production d'une soudure laser : suivi qualité de 81 soudures réelles, relecture "
    "image par image avec segmentation IA du plasma, des projections et du cordon, et analyses statistiques."
)


SECTIONS = [
    # (clé, libellé, icône Lucide, constructeur)
    ("process", "Monitoring process", "activity", process.layout),
    ("suivi", "Suivi & historique", "layout-grid", history.layout),
    ("analyses", "Analyses", "chart-column", doe.layout),
    ("seg", "Segmentation IA", "scan-eye", segmentation.layout),
    ("about", "Méthode", "book-open", about.layout),
]
DEFAULT_SECTION = "process"
NAV_WIDTH = {"expanded": 240, "collapsed": 72}


def wordmark() -> html.Span:
    """Logo : version claire sur fond sombre et inversement (bascule en CSS)."""
    return html.Span(
        className="wordmark",
        children=[
            html.Img(src="/assets/brand/wordmark-dark.png", alt="Lenny Jacquinot", className="wordmark-on-dark"),
            html.Img(src="/assets/brand/wordmark-light.png", alt="Lenny Jacquinot", className="wordmark-on-light"),
        ],
    )


def theme_toggle(toggle_id: str) -> dmc.ColorSchemeToggle:
    return dmc.ColorSchemeToggle(
        id=toggle_id,
        size="lg",
        variant="subtle",
        color="gray",
        radius="md",
        lightIcon=icon("sun"),
        darkIcon=icon("moon"),
        **{"aria-label": "Basculer thème clair / sombre"},
    )


def header() -> dmc.AppShellHeader:
    """En-tête mobile uniquement : sur grand écran, tout est dans la barre latérale."""
    return dmc.AppShellHeader(
        className="header",
        hiddenFrom="sm",
        children=html.Div(
            className="header-inner",
            children=[
                dmc.Burger(id="nav-burger", opened=False, size="sm", **{"aria-label": "Ouvrir le menu"}),
                wordmark(),
                theme_toggle("color-scheme-mobile"),
            ],
        ),
    )


def tip(tip_id, label: str, child) -> dmc.Tooltip:
    """Infobulle à droite, active seulement quand la barre est repliée (icônes seules)."""
    return dmc.Tooltip(id=tip_id, label=label, position="right", withArrow=True, disabled=True, children=child)


def navbar() -> dmc.AppShellNavbar:
    return dmc.AppShellNavbar(
        className="navbar",
        children=[
            html.Div(
                className="nav-top",
                children=[
                    wordmark(),
                    html.Img(src="/assets/brand/mark.png", alt="Lenny Jacquinot", className="nav-mark"),
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
            html.Nav(
                className="nav-links",
                **{"aria-label": "Navigation principale"},
                children=[
                    tip(
                        {"type": "nav-tip", "index": key},
                        label,
                        dmc.NavLink(
                            id={"type": "nav", "index": key},
                            label=label,
                            leftSection=icon(icon_name, 18),
                            active=key == DEFAULT_SECTION,
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
                    dmc.Box(html.Div(theme_toggle("color-scheme"), className="nav-tools"), visibleFrom="sm"),
                    html.Div(
                        className="nav-contact nav-text",
                        children=[
                            html.Div(
                                [
                                    html.Img(src="/assets/brand/mark.png", alt="", className="nav-contact-mark"),
                                    html.Span("Le même suivi sur votre ligne ?"),
                                ],
                                className="nav-contact-title",
                            ),
                            html.P("Vision industrielle, IA embarquée, monitoring procédé et plans d'expériences."),
                        ],
                    ),
                    tip(
                        "contact-tip",
                        "Contacter l'auteur",
                        html.A(
                            [icon("mail", 16), html.Span("Contacter l'auteur", className="nav-text")],
                            href=CONTACT_URL,
                            className="btn-primary nav-cta",
                            target="_blank",
                            rel="noopener noreferrer",
                            **{"aria-label": "Contacter l'auteur"},
                        ),
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
                build(),
                id=f"section-{key}",
                className="section",
                style={} if key == DEFAULT_SECTION else {"display": "none"},
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
    app._favicon = "brand/mark.png"
    app.layout = dmc.MantineProvider(
        defaultColorScheme="dark",
        theme={
            "colors": {"brand": theme.BRAND_SHADES},
            "primaryColor": "brand",
            "primaryShade": {"light": 6, "dark": 5},
            "fontFamily": theme.FONT,
            "fontFamilyMonospace": "'JetBrains Mono', ui-monospace, monospace",
            "defaultRadius": "md",
            "headings": {"fontFamily": theme.FONT},
        },
        children=dmc.AppShell(
            id="app-shell",
            layout="alt",
            header={"height": {"base": 56, "sm": 0}},
            navbar={"width": NAV_WIDTH["expanded"], "breakpoint": "sm", "collapsed": {"mobile": True}},
            padding="md",
            children=[
                header(),
                navbar(),
                dmc.AppShellMain(className="main", children=html.Div(sections(), className="canvas", id="canvas")),
                dcc.Store(id="goto"),
            ],
        ),
    )
    security.install(app, app.csp_hashes())
    return app


# Navigation (côté client) : section affichée, lien actif, barre repliée / dépliée, menu mobile,
# bascule depuis le suivi vers le monitoring, vidéo mise en pause quand on quitte le monitoring.
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
    Input("goto", "data"),
    State("app-shell", "navbar"),
)
