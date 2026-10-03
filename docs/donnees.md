# Dictionnaire des données

Tous les fichiers produits par le pipeline, du brut jusqu'aux artefacts de l'application. Pour chacun : le script
qui le produit, son format et son contenu.

Conventions valables partout :

- **`run_id`** : identifiant d'une soudure, `DoE<série>_<point>` (par exemple `DoE3_19`). 3 séries de 27 points,
  81 runs.
- **Frame** : une image de la caméra. Les index de frame partent de 0, dans l'ordre de la vidéo source.
- **Pixels** : sauf mention contraire, les mesures en pixels sont exprimées à la résolution de travail
  **512 × 512** (les vidéos source font 1024 × 1024).
- **Classes de segmentation** : 0 fond, 1 cordon (`weld`), 2 plasma, 3 projections (`spatter`), 255 ignoré.

## Sommaire

1. [Données brutes](#1-données-brutes-data)
2. [Données intermédiaires](#2-données-intermédiaires-datainterim)
3. [Données traitées](#3-données-traitées-dataprocessed)
4. [Modèle](#4-modèle-models)
5. [Artefacts de l'application](#5-artefacts-de-lapplication-app_data)

## 1. Données brutes (`data/`)

Téléchargées depuis [Zenodo](https://doi.org/10.5281/zenodo.22282527), jamais modifiées.

| Fichier | Contenu |
|---|---|
| `high_speed_camera_videos.zip` | 81 vidéos `.avi` (Photron FASTCAM Nova S9, 1024 × 1024, mono 8 bits, codec msmpeg4v3) et leurs fichiers `.cihx` (métadonnées caméra en XML) |
| `Labels.zip` | annotations de 8 vidéos DoE3 produites avec SAM2 : frames extraites, masques par instance, CSV d'instances, tables de correspondance des frames |
| `Laser_Welding_Dataset_Metadata.xlsx` | une feuille par série (`DOE1`, `DOE2`, `DOE3`) : les 27 points du plan Box-Behnken et un bloc « Execution order » donnant l'ordre de soudage |

## 2. Données intermédiaires (`data/interim/`)

Produit par `01_extract.py`. C'est le contenu exact des deux archives, sans transformation : on peut supprimer ce
dossier et le recréer à tout moment.

```
data/interim/
├── high_speed_camera_videos/DOE{1,2,3}/<run>_C001H001S0001/<run>_C001H001S0001.{avi,cihx}
└── Labels/
    ├── training_labeled/<run>_C001H001S0001/     DoE3_9, 16, 22, 24, 25, 26
    └── eval_ground_truth/<run>_C001H001S0001/    DoE3_19, 23
        ├── frames/frame_NNNNN.png                164 frames annotées (1024 px)
        ├── final_masks/*.png                     un masque binaire par instance
        └── labels_final.csv                      une ligne par instance (classe, boîte, aire...)
```

## 3. Données traitées (`data/processed/`)

### `runs.parquet` : les 81 runs

Produit par `02_metadata.py`. Une ligne par run.

| Colonne | Unité | Description |
|---|---|---|
| `run_id`, `serie`, `point` | | identifiant, série (`DoE1` à `DoE3`), numéro du point d'essai (1 à 27) |
| `power_w` | W | consigne de puissance laser |
| `feedrate_mm_s` | mm/s | consigne de vitesse d'avance |
| `defocus_mm` | mm | défocalisation |
| `pfo_y_mm` | mm | translation de la tête scanner (PFO) en Y |
| `inclination_deg` | ° | angle d'inclinaison du faisceau, qui découle directement de `pfo_y_mm` (une valeur par niveau) : ce n'est pas un facteur indépendant |
| `exec_rank` | | rang de soudage dans la série (1 = première soudure réalisée) |
| `n_frames`, `fps` | -, im/s | nombre de frames et cadence d'enregistrement, 6 000 ou 9 000 (lus dans le `.cihx`) |
| `shutter_ns` | ns | temps d'exposition |
| `recorded_at` | | horodatage de l'enregistrement |
| `camera` | | modèle de caméra |
| `duration_ms` | ms | durée de la vidéo |
| `line_energy_j_mm` | J/mm | énergie linéique, puissance / vitesse |
| `is_center` | | vrai pour les points centraux du plan (répétitions) |

### `labels/<run>/` : annotations normalisées

Produit par `04_labels.py`, pour les 8 vidéos annotées. Les annotations SAM2 (instances, schémas CSV variables)
sont fusionnées en une carte sémantique par frame, avec la priorité projections > plasma > cordon. La classe
`dynamic_other` du dataset est marquée 255 (ignorée à l'entraînement et à l'évaluation).

| Fichier | Contenu |
|---|---|
| `frames/NNN.png` | frame annotée, niveaux de gris 512 px (NNN = 000 à 163) |
| `masks/NNN.png` | carte de labels 512 px (valeurs 0, 1, 2, 3, 255) |

### `labeled_frames.parquet` : index des frames annotées

Produit par `04_labels.py`. 1 312 lignes (8 vidéos × 164 frames).

| Colonne | Description |
|---|---|
| `run_id`, `gt_index` | vidéo et rang de la frame annotée (0 à 163) |
| `video_frame` | index de la frame correspondante dans la vidéo source (reconstruit puis vérifié contre les tables du dataset) |
| `split` | `train` ou `eval` |
| `px_weld`, `px_plasma`, `px_spatter` | nombre de pixels de chaque classe dans le masque |

### `label_instances.parquet` : instances annotées

Produit par `04_labels.py`. 3 162 lignes, une par objet annoté. Colonnes reprises du CSV SAM2, sur un schéma
commun : `frame_file`, `frame_index`, `label`, `track_id`, `area`, `bbox_x`, `bbox_y`, `bbox_w`, `bbox_h`,
`cx_geo`, `cy_geo` (coordonnées en pixels 1024), plus `mask_file`, `run_id` et `video_frame`.

### `frame_features.parquet` : mesures vision par frame

Produit par `06_infer.py`. 59 830 lignes, une par frame des 81 vidéos. Mesures en pixels 512, calculées sur la
segmentation après post-traitement. Les colonnes du plasma et du cordon sont vides quand la classe est absente.

| Colonne | Description |
|---|---|
| `run_id`, `frame` | run et index de frame |
| `mean_gray` | niveau de gris moyen de l'image |
| `plasma_px` | aire du panache de plasma (px) |
| `plasma_cx`, `plasma_cy` | centre de gravité du panache |
| `plasma_top`, `plasma_h`, `plasma_w` | ligne la plus haute, hauteur et largeur de la boîte englobante |
| `plasma_gray` | niveau de gris moyen dans le panache |
| `spatter_n`, `spatter_px` | nombre de projections (composantes connexes d'au moins 4 px) et aire totale |
| `weld_px` | aire du cordon |
| `weld_x0`, `weld_x1` | colonnes de début et de fin du cordon ; `weld_x1` est le **front**, qui suit le laser |
| `weld_width_px` | largeur moyenne du cordon sur les colonnes couvertes |

### `preds/<run>/NNN.png` : prédictions aux frames annotées

Produit par `06_infer.py`, pour les 8 vidéos annotées : carte de labels prédite (même format que `masks/`), aux
mêmes frames que l'annotation. Sert à la comparaison annotation / IA dans l'app.

### `ts/<run>.json` : signaux temporels

Produit par `07_signals.py`. Un fichier par run, **un point par frame** (par exemple 640 points à 6 000 im/s
pour une vidéo de 106 ms). Copié tel quel dans `app_data/ts/` par `09_export.py`. Valeur `null` quand la mesure
n'est pas disponible (laser éteint, bord de filtre).

| Champ | Unité | Statut | Description |
|---|---|---|---|
| `t_ms` | ms | axe | temps depuis le début de la vidéo |
| `on` | 0/1 | calculé | laser allumé, détecté à l'image |
| `power_cmd_w` | W | consigne | puissance du plan quand `on` vaut 1, 0 sinon |
| `feed_cmd_mm_s` | mm/s | consigne | vitesse du plan quand `on` vaut 1, 0 sinon |
| `speed_mm_s` | mm/s | mesuré | vitesse d'avance : pente glissante (20 ms) de la position du front |
| `plasma_mm2` | mm² | mesuré | aire du panache |
| `plasma_smooth_mm2` | mm² | mesuré | même aire, moyenne glissante causale sur 2 ms |
| `plasma_threshold_mm2` | mm² | calculé | **scalaire** : seuil de pic de plasma propre au run |
| `plasma_cv` | | calculé | instabilité : coefficient de variation glissant (5 ms) de l'aire du plasma |
| `plasma_height_mm` | mm | mesuré | hauteur du panache |
| `spatter_n` | | mesuré | nombre de projections visibles |
| `weld_length_mm` | mm | mesuré | longueur de cordon déjà soudée |
| `events` | | calculé | liste d'événements, voir ci-dessous |

Chaque événement est un objet `{type, start, end, t_ms}` : `start` et `end` sont des index de frame, `t_ms`
l'instant de début. Types : `on` (allumage), `off` (extinction), `plasma_spike` (pic de plasma),
`spatter_burst` (rafale de projections), `speed_deviation` (écart de vitesse soutenu).

### `run_kpis.parquet` : indicateurs par run

Produit par `07_signals.py`. Une ligne par run. Les moyennes sont calculées en **régime établi** : phase laser
allumé, sans les 15 % du début ni les 5 % de la fin.

| Colonne | Unité | Description |
|---|---|---|
| `laser_on_ms`, `laser_off_ms`, `weld_duration_ms` | ms | allumage, extinction, durée de tir |
| `speed_measured_mm_s` | mm/s | vitesse de régime (pente de Theil-Sen du front) |
| `speed_error_pct` | % | écart de la vitesse mesurée à la consigne |
| `front_fit_r2` | | qualité de l'ajustement linéaire du front |
| `seam_length_mm` | mm | longueur finale du cordon |
| `plasma_mean_mm2`, `plasma_cv`, `plasma_height_mm` | mm², -, mm | aire moyenne, instabilité, hauteur du panache |
| `spatter_mean`, `spatter_px_mean` | -, mm² | nombre moyen de projections visibles par frame, aire totale moyenne des projections par frame |
| `weld_width_mm` | mm | largeur du cordon après extinction |
| `n_plasma_spike`, `n_spatter_burst`, `n_speed_deviation` | | nombre d'alarmes de chaque type |
| `mm_per_px_run` | mm/px | échelle estimée sur ce run seul (contrôle de l'étalonnage) |

### `calibration.json` : étalonnage et règles d'alarme

Produit par `07_signals.py`.

- `series.<série>` : `mm_per_px_512` (échelle retenue, médiane des runs dont l'ajustement du front a un R² > 0,95),
  `mm_per_px_1024`, `field_of_view_mm`, `runs_used` / `runs`, `cv` (dispersion entre runs).
- `spatter_burst_threshold` : nombre de projections simultanées qui définit une rafale.
- `alarm_rules` : `plasma_spike_sigma`, `spatter_burst_count`, `speed_tolerance_pct`, `speed_min_duration_ms`.

### `doe.json` : modèles de surface de réponse

Produit par `08_doe.py`. Un modèle quadratique complet (4 facteurs codés de -1 à +1, interactions, carrés) plus
un effet de série, par indicateur.

- `factors.<clé>` : pour P, v, f, y, la colonne source, le centre, la demi-étendue, le libellé et l'unité.
- `terms` : liste ordonnée des termes du modèle (`["P"]`, `["P","P"]`, `["P","v"]`...).
- `kpis.<indicateur>` : `r2`, `r2_adj`, `rmse`, `dof`, `t_crit`, `intercept` (moyenné sur les séries),
  `coefs` (dans l'ordre de `terms`), `effects` (coefficient, t et p de chaque terme, séries comprises),
  `fitted` (valeur ajustée par run, pour la carte de contrôle des résidus).

Indicateurs modélisés : `plasma_mean_mm2`, `plasma_cv`, `plasma_height_mm`, `spatter_mean`, `weld_width_mm`,
`speed_error_pct`.

### Journaux

`transcode.log`, `infer.log` (dans `processed/`) et `extract.log` (dans `interim/`) : sorties console des
étapes correspondantes, utiles pour vérifier un passage complet.

## 4. Modèle (`models/`)

Produit par `05_train_seg.py`.

| Fichier | Contenu |
|---|---|
| `unet.pt` | poids du U-Net (`state_dict` PyTorch seul, 98 Mo), à recharger avec `segmodel.load_model` |
| `history.csv` | par epoch : perte d'entraînement et mIoU de validation |
| `metrics.json` | description du modèle, évaluation finale avec et sans post-traitement, par vidéo, et baseline |
| `train.log`, `eval.log` | sorties console |

Voir [modele.md](modele.md).

## 5. Artefacts de l'application (`app_data/`)

Produits par `03_transcode.py` (vidéos brutes, posters), `06_infer.py` (vidéos IA) et `09_export.py` (le reste).
L'application ne lit rien d'autre. Format JSON pour que l'image n'embarque ni numpy ni pandas.

```
app_data/
├── meta.json             étalonnage, règles d'alarme, limites de vigilance, modèle, attribution du dataset
├── runs.json             81 runs : facteurs, caméra, KPI, verdict
├── doe.json              copie de data/processed/doe.json
├── seg_metrics.json      métriques du modèle et comparaison frame par frame
├── ts/<run>.json         copie de data/processed/ts/
└── media/
    ├── videos/<run>.mp4       vidéo web (H.264, 512 px, 30 im/s : une frame caméra par frame vidéo)
    ├── videos/<run>_ia.mp4    même vidéo avec les masques IA incrustés
    ├── posters/<run>.jpg      image d'attente du lecteur (frame à 35 % de la vidéo brute)
    └── seg/<run>/             8 vidéos annotées
        ├── frames/NNN.webp    frame annotée
        ├── gt/NNN.png         annotation (carte de labels)
        └── pred/NNN.png       prédiction (carte de labels)
```

Une frame vidéo par frame caméra : l'index de frame se retrouve exactement par `floor(currentTime * 30)` dans le
navigateur. C'est ce qui permet la synchronisation vidéo / courbes sans serveur.

### `runs.json`

Liste de 81 objets triés par série puis ordre de soudage. Contient toutes les colonnes de `runs.parquet` (sauf
`camera`) et de `run_kpis.parquet`, plus :

| Champ | Description |
|---|---|
| `split` | `train`, `eval` ou `null` selon le rôle de la vidéo pour le modèle |
| `slowmo` | facteur de ralenti à la lecture (fps caméra / 30) |
| `in_domain` | vrai pour DoE3, seule série vue à l'entraînement |
| `n_alarms` | pics de plasma + rafales de projections |
| `verdict` | `ok`, `warn` ou `nok` |

### `meta.json`

| Clé | Contenu |
|---|---|
| `generated_at` | date de l'export |
| `calibration` | copie de `calibration.json` |
| `model` | description du modèle (depuis `metrics.json`) |
| `dataset` | titre, auteurs, DOI, licence et modifications apportées (attribution CC BY) |
| `playback_fps`, `camera` | cadence de lecture, description de la caméra |
| `quality` | bornes du verdict, vigilance vitesse, limite d'instabilité calculée et son quantile |

### `seg_metrics.json`

Contenu de `models/metrics.json`, plus `runs.<run>` : pour chaque vidéo annotée, son rôle (`split`) et, par
frame (`frames`), l'index vidéo, l'instant, les pixels de chaque classe dans l'annotation et la prédiction, et
l'IoU par classe.
