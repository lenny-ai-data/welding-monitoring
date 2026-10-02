# Laser Welding Process Monitor

Dashboard de démonstration (Dash / Plotly) de **monitoring de production** d'un procédé de soudage laser :
suivi qualité de 81 soudures réelles, puis relecture de chacune image par image avec ses signaux de procédé. Il
s'appuie sur des vidéos haute vitesse réelles, sur un modèle de segmentation entraîné pour l'occasion (cordon,
plasma, projections) et sur l'analyse statistique du plan d'expériences Box-Behnken de la campagne.

> Projet personnel de [Lenny Jacquinot](https://www.linkedin.com/in/lenny-jacquinot-ai-engineer/), IA & Data pour l'industrie.

| Onglet | Contenu |
|---|---|
| **Suivi & historique** | Verdict qualité de chaque soudure (OK / OK avec warning / NOK, d'après ses alarmes), campagne la plus récente en premier, filtres par verdict, courbe des alarmes dans l'ordre de production, détail d'une soudure et ouverture dans le monitoring. |
| **Monitoring process** | Relecture d'une soudure (ralentie ×200) : lecteur avec lecture / pause et timeline des événements, cartes tir laser, intégrité (seuils franchis, anneau qui suit les seuils du verdict), puissance et vitesse, journal d'événements, courbes plasma / vitesse (bande ±10 %) / projections / cordon, enchaînement des soudures dans l'ordre réel. Tient sans défilement en plein écran 1920 × 1080. |
| **Segmentation IA** | Annotation humaine à gauche, prédiction du U-Net ou carte des désaccords à droite, image par image. Métriques sur les vidéos d'évaluation, comparaison avec une baseline de vision classique. |
| **Analyses** | Surfaces de réponse quadratiques, effets standardisés, effets principaux, carte de contrôle I-MR des résidus — à réévaluer au fil de la production. |
| **Méthode & sources** | Chaîne de traitement, modèle de segmentation, statut de chaque signal (mesuré / consigne / calculé / modélisé), licence. |

Navigation par barre latérale repliable (icônes seules), liens directs `#suivi`, `#process`, `#seg`, `#analyses`,
`#about`, et un bandeau « Infos et explications » dans chaque section pour un public non spécialiste.

**Verdict d'une soudure** : OK jusqu'à 10 alarmes (pics de plasma + rafales de projections), OK avec warning
jusqu'à 15, NOK au-delà ou dès qu'un écart de vitesse soutenu (±20 % pendant 5 ms) est détecté. Limites de
vigilance des indicateurs : vitesse ±10 % de la consigne, instabilité au 90ᵉ centile des 81 soudures.

## Ce que l'on montre — et ce que l'on ne prétend pas

Le dataset ne contient **aucun log capteur** : puissance et vitesse sont des consignes constantes par run. Le
dashboard les affiche comme telles, entre l'allumage et l'extinction du laser, eux-mêmes détectés à l'image.
Toutes les autres courbes sont **mesurées par vision** :

- **Vitesse d'avance mesurée** : pente glissante de la position du front du cordon.
- **Échelle px → mm** : déduite du procédé lui-même, un facteur par série car le cadrage change.
- **Panache de plasma, projections et largeur de cordon** : issus de la segmentation de chaque frame.

Résultats principaux :

- **Évaluation sur 2 vidéos jamais vues** : IoU cordon 0,93, IoU plasma 0,68, F1 de détection des
  projections 0,70. La baseline par seuillage atteint 0,24 d'IoU plasma et 0,04 de F1 projections.
- **Vitesse mesurée à l'image** : elle retrouve la consigne avec un écart moyen proche de 0 % (σ ≈ 3,5 %).
- **Largeur du cordon** (R² = 0,84) : pilotée par la puissance et la vitesse, comme attendu physiquement.
- **Projections et stabilité du plasma** : l'effet de série domine, d'où l'intérêt d'un suivi en ligne.

## Architecture

```
data/          dataset Zenodo brut + intermédiaires (non versionné, ~11 Go)
pipeline/      traitements hors ligne (GPU) — jamais embarqués dans l'image
  01_extract → 02_metadata → 03_transcode → 04_labels → 05_train_seg → 06_infer
  → 07_signals → 08_doe → 09_export
models/        poids du U-Net + métriques (non versionné)
app_data/      artefacts légers générés pour l'app (~170 Mo, non versionné, copié dans l'image)
src/weldmon/app/
  __init__.py  create_app() — mise en page, thème
  security.py  en-têtes HTTP, routes /media, /overlay, /healthz
  data.py      accès lecture seule aux artefacts, liste blanche des runs
  theme.py     jetons clair / sombre, violet de l'interface, couleurs de classes validées (daltonisme, contraste)
  tabs/        history (suivi), process, segmentation, doe (analyses), about
  assets/      CSS, logique client (process.js, history.js, seg.js, nav.js), polices Sora / JetBrains Mono et logo auto-hébergés
```

Principe : **tout est précalculé**. Le serveur ne sert que la mise en page et des fichiers statiques. Le
replay temps réel tourne dans le navigateur, via des callbacks clientside qui lisent `video.currentTime`.
Résultat : une charge serveur quasi nulle, une image légère, une surface d'attaque minimale.

## Données

*High-Speed Laser Beam Welding Video Dataset with Weld, Plasma, and Spatter Annotations*. Auteurs :
A. Darwish, M. Persson, A. Andersson Lassila, D. Lönn, S. Ericson, K. Salomonsson (University of Skövde), 2026.
DOI [10.5281/zenodo.22282527](https://doi.org/10.5281/zenodo.22282527), licence
[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) : usage non commercial, attribution requise.

Pour reproduire, télécharger les trois fichiers du dépôt Zenodo dans `data/`.

## Reproduire

```bash
uv sync --all-groups      # app + pipeline (torch, GPU CUDA) + dev
make pipeline             # données -> modèle -> signaux -> app_data/   (~45 min sur RTX 3090)
make test lint
make app                  # http://127.0.0.1:8050
```

`make help` liste toutes les cibles. Les groupes de dépendances sont `analysis` (léger, utilisé en CI),
`ml` (torch) et `pipeline` (les deux).

## Image Docker & sécurité

```bash
make docker               # image ghcr.io/lenny-ai-data/laser-welding-monitor
make docker-run           # lancement durci en local
make scan                 # Trivy (CRITICAL/HIGH) + pip-audit
```

- **Image**
  - Multi-stage, base `python:3.12-slim` épinglée par digest.
  - Dépendances figées par `uv.lock`, sans torch, pandas ni numpy au runtime.
  - Utilisateur non-root (UID 10001), `HEALTHCHECK` sur `/healthz`.
  - Compatible `--read-only`, `--cap-drop ALL`, `no-new-privileges`.
- **Application**
  - Aucun upload ni champ libre.
  - Runs et frames validés par liste blanche. Les médias passent par une route dédiée (regex) qui gère les
    requêtes Range ; les chemins inconnus renvoient 404.
  - Dash en mode production, endpoint MCP de Dash 4 désactivé explicitement.
- **En-têtes HTTP**
  - CSP stricte : `script-src 'self'` + hash, `frame-ancestors 'none'`, sans `unsafe-eval`.
  - `nosniff`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, COOP/CORP.
  - HSTS derrière HTTPS.
- **Vie privée**
  - Aucun appel tiers : polices, scripts et médias sont servis localement.
  - Ni cookie ni traceur, d'où un RGPD simple.
- **Déploiement** : `compose.yaml` et `deploy/Caddyfile` (TLS automatique, compression, cache des médias).
  Prévoir un rate limiting au niveau du proxy ou d'un CDN.

```bash
DOMAIN=demo.mondomaine.fr docker compose up -d
```

Variables d'environnement : `PORT` (8050), `WEB_CONCURRENCY` (2), `GUNICORN_THREADS` (4),
`FORWARDED_ALLOW_IPS`, `WELDMON_TRUST_PROXY` (1), `WELDMON_CONTACT_URL`.
