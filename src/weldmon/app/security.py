"""Durcissement HTTP : en-têtes de sécurité, routes statiques contrôlées, santé.

- /media/<fichier>  : vidéos et images précalculées (requêtes Range gérées par Werkzeug) ;
- /overlay/...      : composition frame + masques pour l'onglet segmentation (paramètres en
                      liste blanche, résultat mis en cache) ;
- /healthz          : sonde de vie pour l'orchestrateur.
"""

import io
import os
import re
from functools import lru_cache

from flask import Flask, Response, abort, request, send_from_directory
from PIL import Image, ImageChops, ImageFilter
from werkzeug.middleware.proxy_fix import ProxyFix

from . import data

# Listes blanches et constantes --------------------------------------------------------------------
MEDIA_RE = re.compile(r"^(videos/DoE[123]_\d{1,2}(_ia)?\.mp4|posters/DoE[123]_\d{1,2}\.jpg)$")
MEDIA_MAX_AGE = 7 * 24 * 3600

# Couleurs d'incrustation (identiques aux vidéos IA) et désaccord GT/IA.
OVERLAY_COLORS = {1: (149, 80, 216), 2: (221, 106, 30), 3: (210, 68, 140)}
DISAGREE = (208, 59, 59)
CLASS_KEYS = {"w": 1, "p": 2, "s": 3}


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
        # Sans cela, un chemin mal formé sous /media ou /overlay tomberait sur la route
        # « attrape-tout » de Dash (page d'accueil) au lieu d'un 404 net.
        if request.path.startswith(("/media/", "/overlay/")) and request.endpoint not in ("media", "overlay"):
            abort(404)

    @server.route("/healthz")
    def healthz():
        return Response("ok", mimetype="text/plain", headers={"Cache-Control": "no-store"})

    @server.route("/media/<path:filename>")
    def media(filename: str):
        if not MEDIA_RE.match(filename):
            abort(404)
        return send_from_directory(data.MEDIA_DIR, filename, max_age=MEDIA_MAX_AGE, conditional=True)

    @server.route("/overlay/<run_id>/<int:k>.jpg")
    def overlay(run_id: str, k: int):
        run_id = data.valid_run(run_id)
        source = request.args.get("src", "gt")
        classes = request.args.get("cls", "wps")
        try:
            alpha = int(request.args.get("a", "55"))
        except ValueError:
            abort(400)
        if (
            run_id not in data.labeled_runs()
            or not 0 <= k < data.N_SEG_FRAMES
            or source not in ("gt", "pred", "diff", "none")
            or not 0 <= alpha <= 100
            or not set(classes) <= set(CLASS_KEYS)
            or len(classes) > 3
        ):
            abort(404)
        try:
            body = compose(run_id, k, source, "".join(sorted(set(classes))), alpha)
        except FileNotFoundError:
            abort(404)
        return Response(body, mimetype="image/jpeg", headers={"Cache-Control": f"public, max-age={MEDIA_MAX_AGE}"})


# Composition des images de l'onglet segmentation --------------------------------------------------


def _class_mask(labels: Image.Image, cid: int) -> Image.Image:
    return labels.point(lambda v, c=cid: 255 if v == c else 0)


@lru_cache(maxsize=1024)
def compose(run_id: str, k: int, source: str, classes: str, alpha: int) -> bytes:
    root = data.MEDIA_DIR / "seg" / run_id
    base = Image.open(root / "frames" / f"{k:03d}.webp").convert("RGB")
    if source == "diff":
        gt = Image.open(root / "gt" / f"{k:03d}.png").convert("L")
        pred = Image.open(root / "pred" / f"{k:03d}.png").convert("L")
        # Désaccord : les deux cartes diffèrent ET l'une d'elles porte une classe cochée.
        checked = {CLASS_KEYS[key] for key in classes}
        lut = [255 if v in checked else 0 for v in range(256)]
        differ = ImageChops.difference(gt, pred).point(lambda v: 255 if v else 0)
        relevant = ImageChops.lighter(gt.point(lut), pred.point(lut))
        mask = ImageChops.multiply(differ, relevant)
        _paint(base, mask, DISAGREE, alpha)
    elif source != "none":
        labels = Image.open(root / source / f"{k:03d}.png").convert("L")
        for key in "wps":
            if key in classes:
                cid = CLASS_KEYS[key]
                _paint(base, _class_mask(labels, cid), OVERLAY_COLORS[cid], alpha)
    out = io.BytesIO()
    base.save(out, "JPEG", quality=85)
    return out.getvalue()


def _paint(base: Image.Image, mask: Image.Image, color: tuple, alpha: int) -> None:
    """Remplissage semi-transparent + contour plein (les petites projections restent visibles)."""
    if not mask.getbbox():
        return
    solid = Image.new("RGB", base.size, color)
    base.paste(Image.blend(base, solid, alpha / 100), mask=mask)
    edges = mask.filter(ImageFilter.FIND_EDGES)
    base.paste(solid, mask=edges)
