# syntax=docker/dockerfile:1.7
# Weld Process Monitor — image de production (app Dash + artefacts précalculés).
# Le pipeline (torch, données brutes, modèle) n'est jamais embarqué : seuls src/ et app_data/ le sont.

ARG PYTHON_IMAGE=python:3.12-alpine@sha256:0687a6bc9716edc2a6ee0fbfb0f87e7ee358b262b67c9215de91bc9b2d38ba71
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.11.23@sha256:d0a0a753ab981624b49c97abc98821c1c09f4ca69d1ef5cee69c501be3d88479

FROM ${UV_IMAGE} AS uv

# --- Build : environnement virtuel figé par uv.lock (dépendances runtime uniquement) ------------
FROM ${PYTHON_IMAGE} AS build
COPY --from=uv /uv /usr/local/bin/uv
# Pas de bytecode précompilé : -50 Mo, coût négligeable au démarrage (preload gunicorn).
ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /build
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-default-groups --no-install-project
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-default-groups --no-editable
# Élagage de ce qui ne sert jamais en production : source maps, bundles de debug,
# extensions Jupyter, jeux de données d'exemple de plotly.express.
RUN cd /opt/venv/lib/python3.12/site-packages \
 && find . -name '*.map' -delete \
 && find . -name '*.dev.js' -delete \
 && find . -type d -name '__pycache__' -prune -exec rm -rf {} + \
 && rm -rf plotly/labextension plotly/package_data/widgetbundle.js plotly/package_data/datasets \
           dash/labextension dash/nbextension

# --- Runtime : Alpine, non-root, aucun outil de build, fichiers applicatifs en lecture seule ----
FROM ${PYTHON_IMAGE} AS runtime
LABEL org.opencontainers.image.title="Weld Process Monitor" \
      org.opencontainers.image.description="Monitoring de soudage laser rejoué : vidéo haute vitesse, segmentation IA, DoE" \
      org.opencontainers.image.authors="Lenny Jacquinot" \
      org.opencontainers.image.source="https://github.com/lenny-ai-data/laser-welding-monitor" \
      org.opencontainers.image.licenses="Code: propriétaire ; données dérivées du dataset Zenodo 10.5281/zenodo.22282527 (CC BY-NC 4.0)"

RUN addgroup -S -g 10001 app \
 && adduser -S -D -H -u 10001 -G app -h /nonexistent -s /sbin/nologin app \
 && rm -rf /root/.cache /usr/local/lib/python3.12/ensurepip /usr/local/lib/python3.12/idlelib \
           /usr/local/lib/python3.12/tkinter /usr/local/lib/python3.12/turtledemo /usr/local/bin/idle* /usr/local/bin/pydoc* \
           /usr/local/lib/python3.12/site-packages/pip* /usr/local/bin/pip*

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WELDMON_DATA=/app/app_data \
    PORT=8050

COPY --from=build /opt/venv /opt/venv
COPY gunicorn.conf.py /app/gunicorn.conf.py
COPY app_data /app/app_data

WORKDIR /app
USER 10001:10001
EXPOSE 8050
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen(f\"http://127.0.0.1:{os.environ.get('PORT', '8050')}/healthz\", timeout=4)"]
CMD ["gunicorn", "--config", "/app/gunicorn.conf.py", "weldmon.app.main:server"]
