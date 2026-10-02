# Laser Welding Process Monitor — orchestration du pipeline et de l'image
PY := uv run --group pipeline python
IMAGE ?= ghcr.io/lenny-ai-data/laser-welding-monitor
TAG ?= $(shell git describe --tags --always --dirty 2>/dev/null || echo dev)

.PHONY: help data labels train infer features export pipeline app test lint docker docker-run scan

help:  ## Affiche cette aide
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

data:  ## Extraction des archives, métadonnées, transcodage vidéo
	cd pipeline && $(PY) 01_extract.py && $(PY) 02_metadata.py && $(PY) 03_transcode.py

labels:  ## Normalisation des annotations (cartes de labels 512 px)
	cd pipeline && $(PY) 04_labels.py

train:  ## Entraînement + évaluation du modèle de segmentation (GPU)
	cd pipeline && $(PY) 05_train_seg.py

infer:  ## Inférence sur les 81 vidéos (features par frame + vidéos IA)
	cd pipeline && $(PY) 06_infer.py

features:  ## Signaux, KPI par run, modèles DoE
	cd pipeline && $(PY) 07_signals.py && $(PY) 08_doe.py

export:  ## Export des artefacts légers vers app_data/
	cd pipeline && $(PY) 09_export.py

pipeline: data labels train infer features export  ## Pipeline complet

app:  ## Lance l'app en local (http://127.0.0.1:8050)
	uv run python -m weldmon.app.main

test:  ## Tests unitaires
	uv run --group analysis pytest -q

lint:  ## Lint + format check
	uv run ruff check . && uv run ruff format --check .

docker:  ## Construit l'image
	docker build -t $(IMAGE):$(TAG) -t $(IMAGE):latest .

docker-run:  ## Lance l'image avec les options de durcissement
	docker run --rm -p 8050:8050 --read-only --tmpfs /tmp --cap-drop ALL \
		--security-opt no-new-privileges --memory 512m --cpus 1 $(IMAGE):latest

scan:  ## Scan de vulnérabilités (Trivy + pip-audit)
	docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:latest image \
		--severity CRITICAL,HIGH --exit-code 1 --ignore-unfixed $(IMAGE):latest
	uv export --frozen --no-dev --no-default-groups --no-emit-project --format requirements-txt > /tmp/weldmon-req.txt
	uvx pip-audit -r /tmp/weldmon-req.txt --strict --disable-pip --no-deps
