# Modèle de segmentation

Fiche du U-Net qui segmente chaque image en cordon, panache de plasma et projections. Toutes les mesures vision
du projet en dépendent.

## Sommaire

1. [Résumé](#1-résumé)
2. [Données d'entraînement](#2-données-dentraînement)
3. [Entraînement](#3-entraînement)
4. [Post-traitement](#4-post-traitement)
5. [Évaluation](#5-évaluation)
6. [Utiliser le modèle](#6-utiliser-le-modèle)
7. [Performances](#7-performances)
8. [Réentraîner ou enrichir](#8-réentraîner-ou-enrichir)
9. [Limites](#9-limites)

## 1. Résumé

| | |
|---|---|
| Tâche | segmentation sémantique, 4 classes : fond (0), cordon (1), plasma (2), projections (3) |
| Architecture | U-Net, encodeur ResNet34 pré-entraîné ImageNet ([segmentation-models-pytorch](https://github.com/qubvel-org/segmentation_models.pytorch)), 24,4 M de paramètres |
| Entrée | image en niveaux de gris 512 × 512, `uint8`, normalisée par `(x / 255 - 0,45) / 0,25` |
| Sortie | logits `(N, 4, 512, 512)`, classe retenue par `argmax` |
| Poids | `models/unet.pt` (`state_dict` seul, 98 Mo) |
| Code | `pipeline/segmodel.py` (architecture, prétraitement, post-traitement), `05_train_seg.py`, `06_infer.py` |

## 2. Données d'entraînement

8 vidéos de la série DoE3 annotées par les auteurs du dataset avec SAM2, 164 frames réparties uniformément par
vidéo. Préparation par `04_labels.py` (voir [donnees.md](donnees.md)).

Le découpage se fait **par vidéo**, jamais par frame : deux frames voisines d'une même soudure sont presque
identiques, et les répartir entre entraînement et test gonflerait artificiellement les scores.

| Rôle | Vidéos | Frames |
|---|---|---|
| Entraînement | DoE3_9, DoE3_22, DoE3_24, DoE3_25, DoE3_26 | 820 |
| Validation (choix du meilleur epoch) | DoE3_16 | 164 |
| Évaluation finale (jamais vues) | DoE3_19, DoE3_23 | 328 |

Le découpage est défini dans `pipeline/common.py` (`TRAIN_RUNS`, `EVAL_RUNS`) et `05_train_seg.py` (`VAL_RUNS`).

## 3. Entraînement

`make train`, ou `cd pipeline && uv run --group pipeline python 05_train_seg.py`. Environ 15 min sur RTX 3090.

| Réglage | Valeur |
|---|---|
| Epochs, batch, taux d'apprentissage | 80, 8, 3e-4 |
| Optimiseur, planification | AdamW (weight decay 1e-4), OneCycle |
| Perte | entropie croisée + Dice multiclasse, pixels 255 ignorés |
| Précision | mixte (float16) |
| Graine | 42 |
| Checkpoint retenu | meilleur mIoU de validation (0,68, epoch 39) |

**Augmentations** (entraînement seulement) : petite rotation, translation et zoom, luminosité et contraste,
gamma aléatoire, flou léger. Elles sont volontairement fortes sur l'exposition et le cadrage, parce que les
séries DoE1 et DoE2 (non annotées) sont éclairées et cadrées différemment. **Pas de symétrie horizontale** : le
sens de soudage (de gauche à droite) est une information utile.

## 4. Post-traitement

`segmodel.suppress_static(labels)` travaille sur **toute la séquence d'une vidéo** (tableau `(N, H, W)`) et
supprime ce qui ne bouge pas :

- plasma présent au même pixel sur plus de 35 % des frames, projections sur plus de 8 % : ce sont des reflets ou
  des rayures, pas des phénomènes du procédé ;
- « cordon » déjà visible dans les toutes premières frames (2 % de la vidéo) : texture de la tôle prise pour une
  soudure, puisque le laser n'a encore rien soudé.

Ce post-traitement fait partie du modèle : il est appliqué à l'évaluation comme en production. Il corrige surtout
les faux positifs dus aux différences d'éclairage entre séries.

## 5. Évaluation

Sur les 2 vidéos d'évaluation, avec post-traitement (`models/metrics.json`, clé `eval`) :

| Métrique | U-Net | U-Net sans post-traitement | Baseline vision classique |
|---|---|---|---|
| IoU cordon | 0,93 | 0,93 | 0 (non accessible) |
| IoU plasma | 0,69 | 0,69 | 0,24 |
| IoU projections (au pixel) | 0,36 | 0,33 | 0,03 |
| Détection des projections : précision / rappel / F1 | 0,72 / 0,72 / 0,72 | 0,42 / 0,72 / 0,53 | 0,02 / 0,44 / 0,04 |
| Corrélation de l'aire du plasma (annotation / prédiction) | 0,89 | 0,89 | 0,67 |

**Lecture des métriques**

- L'IoU au pixel des projections reste basse parce que ce sont des objets de quelques pixels : un décalage d'un
  pixel suffit à la faire chuter. La métrique pertinente est la **détection** : une projection prédite est juste
  si elle recouvre une projection annotée, à 2 px près (`metrics.instance_matches`).
- La baseline (`baseline_cv.py`) soustrait la première image puis seuille : le plasma est l'objet le plus
  lumineux, les petites taches hors panache sont comptées comme projections. Son seuil est réglé sur les vidéos
  d'entraînement. Elle sert de référence honnête : ce qu'on obtient sans apprentissage.

Pour réévaluer les poids actuels sans réentraîner :

```bash
cd pipeline && uv run --group pipeline python 05_train_seg.py --eval-only
```

## 6. Utiliser le modèle

Le modèle se recharge en trois éléments, qui doivent toujours aller ensemble : l'architecture (`build_model`),
le prétraitement (`to_tensor`) et le post-traitement (`suppress_static`). Exemple sur une vidéo, en dehors du
pipeline :

```python
import sys

import cv2
import numpy as np
import torch

sys.path.insert(0, "pipeline")
from segmodel import load_model, suppress_static, to_tensor

device = "cuda" if torch.cuda.is_available() else "cpu"
model = load_model("models/unet.pt", device)

# Frames en niveaux de gris, redimensionnées en 512 x 512 (même méthode que l'entraînement)
cap, frames = cv2.VideoCapture("ma_video.avi"), []
while True:
    ok, img = cap.read()
    if not ok:
        break
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    frames.append(cv2.resize(gray, (512, 512), interpolation=cv2.INTER_AREA))
frames = np.stack(frames)

with torch.no_grad():
    labels = np.concatenate(
        [model(to_tensor(frames[i : i + 32]).to(device)).argmax(1).cpu().numpy() for i in range(0, len(frames), 32)]
    ).astype(np.uint8)
labels = suppress_static(labels)  # (N, 512, 512), valeurs 0 à 3
```

`segmodel.load_model` fonctionne sur CPU (lent, mais suffisant pour quelques vidéos). Seuls les scripts `05` et
`06` imposent CUDA (`DEVICE = "cuda"`).

Pour passer des cartes de labels aux mesures physiques, réutiliser `frame_features` de `06_infer.py` (mesures en
pixels), puis la chaîne de `07_signals.py` (étalonnage en mm, signaux, alarmes).

## 7. Performances

Mesuré sur RTX 3090 avec `make bench` (détail et projection vers la production : [production.md](production.md)).

| Configuration | Débit | Soudure type (700 images) |
|---|---|---|
| GPU, lots de 32, fp16, passe avant seule | 407 im/s | 1,7 s |
| GPU, lots de 32, fp16, chaîne de `06_infer` (prétraitement, argmax, retour CPU) | 300 im/s | 2,3 s |
| GPU, une image à la fois, fp16 (latence 3,7 ms) | 269 im/s | 2,6 s |
| GPU, lots de 32, fp32 | 259 im/s | 2,7 s |
| CPU, 12 threads, fp32 | 6 im/s | environ 2 min |

Mémoire GPU de pointe : 3,3 Go. Le post-traitement (`suppress_static`) est négligeable : 0,2 s par vidéo.

## 8. Réentraîner ou enrichir

**Réentraîner à l'identique** : `make train infer features export`, puis `make docker`. Sauvegarder
`models/unet.pt` avant : il est écrasé. Les métriques ressortiront très proches mais pas identiques (le calcul
GPU n'est pas déterministe au bit près).

**Ajouter des vidéos annotées** (par exemple quelques frames DoE1 / DoE2 pour réduire l'écart de domaine) :

1. Déposer les annotations dans `data/interim/Labels/training_labeled/<run>_C001H001S0001/` (ou
   `eval_ground_truth/`) au format du dataset : `frames/frame_NNNNN.png`, `final_masks/*.png` et
   `labels_final.csv` (colonnes listées dans `04_labels.COMMON`, plus `ignore`).
2. Ajouter le run à `TRAIN_RUNS` ou `EVAL_RUNS` dans `pipeline/common.py`.
3. Relancer `make labels train infer features export`.

Contrainte actuelle : chaque vidéo annotée doit compter **164 frames** réparties uniformément sur la vidéo. Ce
nombre est fixé dans `04_labels.py` (`N_LABELED`), `src/weldmon/app/data.py` (`N_SEG_FRAMES`) et
`assets/seg.js` (`N_FRAMES`). Une autre répartition demande d'adapter ces trois endroits et la reconstruction de
la correspondance frame annotée / frame vidéo (`04_labels.frame_mapping`).

**Changer d'architecture ou d'encodeur** : modifier `segmodel.build_model` (et `ENCODER`). Le reste du pipeline
ne dépend que de la sortie `(N, 4, H, W)`.

## 9. Limites

- **Domaine** : entraîné sur DoE3 seulement. Sur DoE1 et DoE2, les mesures restent exploitables grâce aux
  augmentations et au post-traitement, mais moins fiables.
- **Volume** : environ 1 000 frames annotées, issues de 6 soudures. Les scores sur 2 vidéos d'évaluation donnent
  un ordre de grandeur, pas un intervalle de confiance serré.
- **Pas de reprise d'entraînement** : `05_train_seg` repart toujours des poids ImageNet. Un affinage à partir de
  `unet.pt` demanderait une petite option dans `train()`.
- **Traçabilité** : `metrics.json` décrit le modèle, mais aucun hash des poids ni version des données n'est
  enregistré.
