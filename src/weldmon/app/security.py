"""Durcissement HTTP : en-têtes de sécurité, routes statiques contrôlées, santé.

- /media/<fichier>  : vidéos, posters, frames et cartes de labels précalculés (requêtes Range gérées
                      par Werkzeug), noms de fichiers en liste blanche ;
- /healthz          : sonde de vie pour l'orchestrateur.
"""

import os
import re

from flask import Flask, Response, abort, request, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix

from . import data

# Listes blanches et constantes --------------------------------------------------------------------
MEDIA_RE = re.compile(
    r"^(videos/DoE[123]_\d{1,2}(_ia)?\.mp4"
    r"|posters/DoE[123]_\d{1,2}\.jpg"
    r"|seg/DoE[123]_\d{1,2}/(frames/\d{3}\.webp|(gt|pred)/\d{3}\.png))$"
)
MEDIA_MAX_AGE = 7 * 24 * 3600


# En-têtes et routes -------------------------------------------------------------------------------


def csp(script_hashes: list[str]) -> str:
    scripts = " ".join(script_hashes)  # Dash fournit déjà les hash entre apostrophes
    return "; ".join(
        [
            "default-src 'self'",
            f"script-src 'self' {scripts}",
            # Mantine (variables CSS) et Plotly injectent des styles en ligne.
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data: blob:",
            "media-src 'self'",
            "font-src 'self'",
            "connect-src 'self'",
            "worker-src 'self' blob:",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        ]
    )


def install(app, script_hashes: list[str]) -> None:
    server: Flask = app.server
    if os.environ.get("WELDMON_TRUST_PROXY", "1") == "1":
        # Derrière un reverse proxy (Caddy, Traefik, Cloud Run...) : schéma et IP réels.
        server.wsgi_app = ProxyFix(server.wsgi_app, x_for=1, x_proto=1, x_host=1)
    policy = csp(script_hashes)

    @server.after_request
    def headers(resp: Response) -> Response:
        resp.headers["Content-Security-Policy"] = policy
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        resp.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()"
        )
        resp.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        if request.is_secure:
            # COOP et HSTS n'ont d'effet qu'en HTTPS (en HTTP le navigateur ignore COOP et le signale).
            resp.headers["Cross-Origin-Opener-Policy"] = "same-origin"
            resp.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return resp

    @server.before_request
    def strict_prefixes():
        # Sans cela, un chemin mal formé sous /media tomberait sur la route « attrape-tout » de Dash
        # (page d'accueil) au lieu d'un 404 net.
        if request.path.startswith("/media/") and request.endpoint != "media":
            abort(404)

    @server.route("/healthz")
    def healthz():
        return Response("ok", mimetype="text/plain", headers={"Cache-Control": "no-store"})

    @server.route("/media/<path:filename>")
    def media(filename: str):
        if not MEDIA_RE.match(filename):
            abort(404)
        return send_from_directory(data.MEDIA_DIR, filename, max_age=MEDIA_MAX_AGE, conditional=True)
