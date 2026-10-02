# Laser Welding Process Monitor

Dashboard de démonstration (Dash / Plotly) qui rejoue *comme en temps réel* le monitoring d'un procédé de
soudage laser à partir de vidéos haute vitesse, d'un modèle de segmentation (cordon / plasma / projections)
et d'un plan d'expériences Box-Behnken.

> Projet personnel de [Lenny Jacquinot](https://www.linkedin.com/in/lenny-jacquinot-ai-engineer/), IA & Data pour l'industrie.

## Données

*High-Speed Laser Beam Welding Video Dataset with Weld, Plasma, and Spatter Annotations* —
A. Darwish, M. Persson, A. Andersson Lassila, D. Lönn, S. Ericson, K. Salomonsson (University of Skövde), 2026.
DOI [10.5281/zenodo.22282527](https://doi.org/10.5281/zenodo.22282527) — licence
[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/).

Les données brutes (~11 Go) ne sont pas versionnées : télécharger les trois fichiers du dépôt Zenodo dans `data/`.

## Démarrage rapide

```bash
uv sync --all-groups      # dépendances (app + pipeline + dev)
make pipeline             # données -> modèle -> signaux -> app_data/
make app                  # http://127.0.0.1:8050
make docker docker-run    # image de production
```

`make help` liste toutes les cibles.
