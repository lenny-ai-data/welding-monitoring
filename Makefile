# Laser Welding Process Monitor : orchestration du pipeline et de l'image
# Variables ----------------------------------------------------------------------------------------
PY := uv run --group pipeline python
IMAGE ?= ghcr.io/lenny-ai-data/welding-monitoring
# Trivy épinglé par digest (outil de sécurité : jamais de tag flottant).
TRIVY := aquasec/trivy:0.75.0@sha256:af6acf9a6b85dfe389a1941505c0ce9efef52a4719635e1a962f022a3d855daa
TAG ?= $(shell git describe --tags --always --dirty 2>/dev/null || echo dev)
# Architectures de l'image publiée : serveurs x86 et ARM (Ampere, Graviton...). L'ARM se construit sous
# émulation QEMU sur une machine x86 (paquet qemu-user-static).
PLATFORMS ?= linux/amd64,linux/arm64
# Adresse de l'app mesurée par bench-ui (lancée par make app ou make docker-run).
URL ?= http://127.0.0.1:8050

.PHONY: help data labels train infer features export pipeline bench app bench-ui test lint docker docker-multi docker-run push scan

# Aide ---------------------------------------------------------------------------------------------
help:  ## Affiche cette aide
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

# Pipeline de données (dans l'ordre ; train, infer et bench demandent un GPU CUDA) -----------------
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

bench:  ## Mesure des temps d'inférence sur une vidéo (GPU)
	cd pipeline && $(PY) bench_infer.py

# Développement ------------------------------------------------------------------------------------
app:  ## Lance l'app en local (http://127.0.0.1:8050)
	uv run python -m weldmon.app.main

bench-ui:  ## Mesure du rendu dans le navigateur (app lancée sur URL ; Chromium de Playwright requis)
	uv run --with playwright python tests/bench_ui.py $(URL)

test:  ## Tests unitaires
	uv run --group analysis pytest -q

lint:  ## Lint + format check
	uv run ruff check . && uv run ruff format --check .

# Image Docker et sécurité -------------------------------------------------------------------------
docker:  ## Construit l'image pour l'architecture de cette machine
	docker build -t $(IMAGE):$(TAG) -t $(IMAGE):latest .

docker-multi:  ## Construit l'image pour toutes les architectures de PLATFORMS (amd64 + arm64)
	docker buildx build --platform $(PLATFORMS) -t $(IMAGE):$(TAG) -t $(IMAGE):latest --load .

docker-run:  ## Lance l'image avec les options de durcissement
	docker run --rm -p 8050:8050 --read-only --tmpfs /tmp --cap-drop ALL \
		--security-opt no-new-privileges --memory 512m --cpus 1 $(IMAGE):latest

push:  ## Pousse l'image (toutes ses architectures) sur le registre ; version taguée et arbre propre exigés
	@case "$(TAG)" in v*-g*|*dirty*|dev) echo "Version $(TAG) non publiable : tagger un commit propre (git tag vX.Y.Z)"; exit 1;; esac
	docker push $(IMAGE):$(TAG)
	docker push $(IMAGE):latest

scan:  ## Scan de vulnérabilités (Trivy + pip-audit)
	docker run --rm -v /var/run/docker.sock:/var/run/docker.sock $(TRIVY) image \
		--scanners vuln,secret --severity CRITICAL,HIGH --exit-code 1 --ignore-unfixed $(IMAGE):latest
	uv export --frozen --no-dev --no-default-groups --no-emit-project --format requirements-txt > /tmp/weldmon-req.txt
	uvx pip-audit -r /tmp/weldmon-req.txt --strict --disable-pip --no-deps
