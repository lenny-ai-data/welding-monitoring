# Performances et passage en production

Ce que coûte l'inférence aujourd'hui, et comment le projet se transposerait sur une vraie ligne de soudage. Les
mesures sont reproductibles avec `make bench` ; la projection vers la production est une proposition
d'architecture, pas un système testé.

## Sommaire

1. [Mesures](#1-mesures)
2. [Lecture des mesures](#2-lecture-des-mesures)
3. [Principe : un contrôle par soudure](#3-principe--un-contrôle-par-soudure)
4. [Architecture envisagée](#4-architecture-envisagée)
5. [Dimensionnement](#5-dimensionnement)
6. [Optimisations possibles](#6-optimisations-possibles)
7. [Points à valider avant un pilote](#7-points-à-valider-avant-un-pilote)

## 1. Mesures

Banc : NVIDIA RTX 3090 (24 Go), PyTorch 2.14, vidéo DoE3_19 (658 images de 1024 × 1024, traitées à 512 × 512).
Commande : `make bench` (ou `cd pipeline && uv run --group pipeline python bench_infer.py <run>`).

**Chaîne complète de l'étape `06_infer`, sur la vidéo entière**

| Poste | Temps | Débit |
|---|---|---|
| Décodage du fichier AVI et redimensionnement | 2,5 s | 266 im/s |
| U-Net (lots de 32, fp16, argmax et retour vers le CPU compris) | 2,2 s | 300 im/s |
| Post-traitement (`suppress_static`) | 0,2 s | 2 900 im/s |
| Mesures par frame | 0,6 s | 1 090 im/s |
| Encodage de la vidéo avec masques (pour la démo seulement) | 1,3 s | 490 im/s |

**Modèle seul (passe avant, sans argmax ni transfert)**

| Lot | fp16 | fp32 |
|---|---|---|
| 1 image (latence) | 269 im/s, 3,7 ms | 209 im/s, 4,8 ms |
| 8 images | 382 im/s | 250 im/s |
| 32 images | 407 im/s | 259 im/s |
| CPU, 12 threads, lot de 8 | | 5,8 im/s |

Mémoire GPU de pointe : **3,3 Go**.

**Sur les 81 vidéos** (journal de l'étape 06, `data/processed/infer.log`) : 59 830 images en 417 s, soit environ
5 s par vidéo (de 2,9 à 10,5 s selon la longueur), décodage exclu car exécuté en parallèle.

## 2. Lecture des mesures

- **Une soudure type** (110 ms filmées, environ 700 images) passe dans le modèle en **2,3 s**, et dans toute la
  chaîne de mesure (modèle, post-traitement, mesures) en **environ 3 s**. C'est ce qui permet d'envisager un
  contrôle à chaque soudure.
- **Le CPU seul n'est pas une option** : environ 2 minutes par soudure. Un GPU est nécessaire, mais modeste en
  mémoire (3,3 Go).
- **Un quart du temps du modèle est perdu autour de lui** : 407 im/s pour la passe avant seule, 300 im/s une fois
  le prétraitement (sur CPU) et le retour des résultats comptés. C'est le premier gain facile.
- **Le décodage AVI pèse autant que le modèle**, mais c'est un artefact du dataset : sur une ligne, les images
  arriveraient brutes de la caméra.
- **L'encodage de la vidéo avec masques** ne sert qu'à la démonstration ; en production, on ne l'appliquerait
  qu'aux soudures à archiver.

## 3. Principe : un contrôle par soudure

La caméra enregistre la soudure dans sa mémoire interne, puis transfère la séquence au poste de calcul, qui la
traite en entier et rend un verdict, en environ 3 s de calcul par soudure. C'est le même traitement que dans ce
projet, appliqué à une soudure à la fois : le code de mesure et de qualification se réutilise presque tel quel.

L'objectif visé est de savoir si la pièce est bonne avant qu'elle ne quitte le poste, et de garder une trace de
chaque soudure.

## 4. Architecture envisagée

| # | Brique | Rôle | Reprise de l'existant |
|---|---|---|---|
| 1 | Déclenchement et traçabilité | le signal d'allumage du laser (contrôleur laser ou automate) déclenche l'enregistrement ; l'identifiant de pièce est associé à la séquence | à construire |
| 2 | Acquisition | la caméra enregistre la soudure dans sa mémoire, puis la transfère au poste de calcul | à construire (SDK du constructeur) |
| 3 | Service d'inférence, au pied de la machine | segmentation, post-traitement, mesures, signaux, alarmes et verdict | `segmodel.py`, `frame_features` (06), `run_signals` (07), règles de verdict (09) |
| 4 | Décision | verdict transmis à l'automate (OPC UA par exemple) pour écarter une pièce NOK | à construire |
| 5 | Mesures réelles | puissance et vitesse lues sur le contrôleur laser et le robot, à la place des consignes | à construire |
| 6 | Stockage | signaux et indicateurs dans une base de séries temporelles ; vidéo 512 px de chaque soudure (environ 1 Mo) ; vidéo brute seulement pour les NOK et un échantillon | format des signaux repris de `ts/<run>.json` |
| 7 | Supervision | le dashboard, alimenté par la base au lieu des fichiers de `app_data/` | l'application ; seul `data.py` lit les données, c'est le point à remplacer |
| 8 | Suivi du modèle | version des poids, surveillance de dérive, boucle d'annotation et de réentraînement | `05_train_seg.py`, `metrics.py` ; registre et surveillance à construire |

**Suivi du modèle, en pratique**

- **Version** : chaque verdict enregistre la version du modèle et des règles qui l'ont produit.
- **Dérive** : surveiller ce qui signale un changement de conditions sans attendre une annotation, comme la
  luminosité moyenne des images, la distribution de l'aire du plasma, la part de détections rejetées par le
  post-traitement ou le taux de NOK.
- **Boucle d'amélioration** : annoter régulièrement quelques soudures (en priorité les NOK et les cas limites),
  réentraîner, puis comparer l'ancien et le nouveau modèle sur les mêmes soudures avant de basculer.

## 5. Dimensionnement

Ordres de grandeur pour un contrôle par soudure, à partir des mesures de la section 1 (soudure de 700 images). Hypothèse de
liaison caméra : **10 GbE**, standard sur ce niveau d'équipement.

| Grandeur | Valeur | Remarque |
|---|---|---|
| Volume brut d'une soudure | environ 700 Mo | 700 images de 1 Mo (1024 × 1024, 8 bits) |
| Transfert caméra vers poste de calcul | environ 0,7 s | 10 GbE, débit utile supposé d'environ 1 Go/s ; à vérifier sur la caméra retenue |
| Calcul par soudure | environ 3 s aujourd'hui, environ 2 s optimisé | modèle, post-traitement, mesures, signaux |
| Délai du verdict après la soudure | environ 4 s aujourd'hui, environ 3 s optimisé | transfert puis calcul, sans recouvrement |
| Capacité d'un GPU | environ 20 soudures par minute | au-delà, paralléliser ou optimiser (section 6) |
| Mémoire GPU | 3,3 Go mesurés | une carte de 8 Go suffit a priori ; débit à mesurer sur le matériel cible |
| Stockage courant | environ 1 Mo par soudure (vidéo 512 px) + quelques ko de signaux | 1 000 soudures par jour : environ 1 Go par jour |

Avec une liaison 10 GbE, le transfert pèse peu (moins d'une seconde) : **le calcul est le poste dominant**, et
c'est lui qu'il faut optimiser si le temps de cycle est court (section 6). Traiter les images au fil du transfert
plutôt qu'après permettrait de recouvrir les deux et de ramener le délai vers la seule durée du calcul.

## 6. Optimisations possibles

Aucune n'a été testée. Les gains sont des estimations à confirmer par `make bench`.

| Piste | Gain attendu | Contrepartie |
|---|---|---|
| Prétraitement et argmax sur le GPU, transferts en parallèle du calcul | jusqu'à 25 % (de 300 vers 400 im/s, écart mesuré) | aucune, simple travail de code |
| Compilation TensorRT en fp16 | gain significatif habituel sur ce type de réseau, à mesurer | chaîne de compilation à maintenir pour chaque version du modèle |
| Traiter 1 image sur N | coût divisé par N | sans risque pour le plasma et la vitesse, qui varient lentement ; à valider pour les projections, très brèves |
| Résolution d'entrée réduite (256 px) | environ 4 fois moins de calcul | réentraînement nécessaire, petites projections menacées |
| Encodeur plus léger | variable | réentraînement et réévaluation complets |

## 7. Points à valider avant un pilote

- **Lien entre verdict et qualité réelle** : le verdict actuel compte des anomalies de procédé (pics de plasma,
  rafales de projections, écarts de vitesse). Il n'a pas été confronté à des contrôles de la soudure elle-même
  (coupes, ressuage, essais destructifs). C'est la première validation à mener, sur des pièces contrôlées.
- **Seuils** : bornes du verdict et limites de vigilance ont été fixées sur 81 soudures d'une campagne de
  laboratoire. Elles sont à recalibrer sur la production, avec un taux de faux NOK accepté par le métier.
- **Changement de domaine** : nouvelle caméra, nouvelle optique, autre matériau ou autre éclairage. Prévoir
  l'annotation de quelques soudures par configuration et un réaffinage du modèle. L'écart déjà observé entre DoE3
  et DoE1 / DoE2 en donne un aperçu.
- **Matériel cible** : mesurer le débit réel sur le GPU et le lien caméra retenus, avec `make bench`.
- **Temps de cycle** : vérifier que transfert et calcul tiennent dans le temps entre deux soudures, ou prévoir un
  traitement décalé avec une file d'attente.
