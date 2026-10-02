"""Composants d'interface partagés : icônes, en-tête de section et bandeau d'explications."""

import dash_mantine_components as dmc
from dash import html


def icon(name: str, size: int = 18) -> html.Span:
    """Icône Lucide servie localement (assets/icons/<name>.svg), colorée par currentColor."""
    return html.Span(
        className=f"icon icon-{name}",
        style={"width": f"{size}px", "height": f"{size}px"},
        **{"aria-hidden": "true"},
    )


def section_header(title: str, subtitle: str, explanations: list) -> html.Div:
    """Titre de section + accroche + bandeau « Infos et explications » replié par défaut."""
    return html.Div(
        className="section-header",
        children=[
            html.H1(title, className="section-title"),
            html.P(subtitle, className="section-subtitle"),
            dmc.Accordion(
                value=None,
                variant="separated",
                radius="md",
                chevronPosition="right",
                className="info-accordion",
                children=[
                    dmc.AccordionItem(
                        value="info",
                        children=[
                            dmc.AccordionControl("Infos et explications", icon=icon("info", 16)),
                            dmc.AccordionPanel(html.Div(explanations, className="info-body")),
                        ],
                    )
                ],
            ),
        ],
    )


def point(title: str, text: str) -> html.P:
    """Paragraphe explicatif avec un intitulé en gras."""
    return html.P([html.Strong(title + " — "), text])
