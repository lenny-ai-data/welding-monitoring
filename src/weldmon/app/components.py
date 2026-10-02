"""Composants d'interface partagés : icônes, en-tête de section, explications, verdicts."""

import dash_mantine_components as dmc
from dash import html

# Verdict qualité d'une soudure : libellé + icône (jamais la couleur seule).
VERDICTS = {
    "ok": ("OK", "circle-check"),
    "warn": ("OK avec warning", "triangle-alert"),
    "nok": ("NOK", "circle-x"),
}


def icon(name: str, size: int = 18) -> html.Span:
    """Icône Lucide servie localement (assets/icons/<name>.svg), colorée par currentColor."""
    return html.Span(
        className=f"icon icon-{name}",
        style={"width": f"{size}px", "height": f"{size}px"},
        **{"aria-hidden": "true"},
    )


def verdict_badge(verdict: str, prefix: str = "") -> html.Span:
    label, icon_name = VERDICTS[verdict]
    return html.Span([icon(icon_name, 15), prefix + label], className=f"verdict-badge v-{verdict}")


def section_header(title: str, subtitle: str, explanations: list, crumb=None, aside=None) -> html.Div:
    """Titre de section (+ fil d'Ariane et éléments à droite) + bandeau « Infos et explications » replié."""
    return html.Div(
        className="section-header",
        children=[
            html.Div(
                className="section-head-row",
                children=[
                    html.Div(
                        className="section-head-text",
                        children=([html.Div(crumb, className="crumb")] if crumb else [])
                        + [html.H1(title, className="section-title"), html.P(subtitle, className="section-subtitle")],
                    ),
                    html.Div(aside, className="section-aside") if aside else None,
                ],
            ),
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
