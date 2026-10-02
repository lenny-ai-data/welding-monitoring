"""Laser Welding Process Monitor — application Dash."""

import dash_mantine_components as dmc
from dash import Dash, html

from . import data, security
from .tabs import about, doe, live, segmentation

TITLE = "Weld Process Monitor — Lenny Jacquinot"
DESCRIPTION = (
    "Monitoring de soudage laser rejoué en temps réel : vidéo haute vitesse, segmentation IA "
    "du plasma, des projections et du cordon, et analyse de plan d'expériences."
)


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
                            html.A(
                                "Dataset Zenodo",
                                href=data.meta()["dataset"]["url"],
                                target="_blank",
                                rel="noopener noreferrer",
                                className="header-link",
                            ),
                            dmc.ColorSchemeToggle(
                                id="color-scheme",
                                size="lg",
                                variant="default",
                                radius="md",
                                lightIcon=html.Span(className="icon icon-sun"),
                                darkIcon=html.Span(className="icon icon-moon"),
                                **{"aria-label": "Basculer thème clair / sombre"},
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


def tabs() -> dmc.Tabs:
    items = [
        ("live", "Monitoring live", live.layout),
        ("seg", "Vidéo & masques IA", segmentation.layout),
        ("doe", "Analyse DoE", doe.layout),
        ("about", "Méthode & sources", about.layout),
    ]
    return dmc.Tabs(
        value="live",
        variant="pills",
        radius="md",
        keepMounted=True,
        className="tabs",
        children=[
            dmc.TabsList([dmc.TabsTab(label, value=key) for key, label, _ in items], className="tabs-list"),
            *[dmc.TabsPanel(build(), value=key) for key, _, build in items],
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
            header={"height": 64},
            padding="md",
            children=[
                header(),
                dmc.AppShellMain(className="main", children=[tabs()]),
            ],
        ),
    )
    security.install(app, app.csp_hashes())
    return app
