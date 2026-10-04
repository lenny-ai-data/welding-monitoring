# Application

Architecture de l'application Dash (`src/weldmon/app/`), conventions de code et points de vigilance pour la faire
évoluer.

## Sommaire

1. [Principes](#1-principes)
2. [Organisation du code](#2-organisation-du-code)
3. [Cycle de vie d'une page](#3-cycle-de-vie-dune-page)
4. [Onglets](#4-onglets)
5. [Logique côté client](#5-logique-côté-client)
6. [Contrats entre Python et JavaScript](#6-contrats-entre-python-et-javascript)
7. [Performances du rendu](#7-performances-du-rendu)

## 1. Principes

- **Tout est précalculé.** L'app lit `app_data/` (JSON, vidéos, images) et ne fait aucun calcul lourd : ni
  numpy, ni pandas, ni modèle. Les surfaces de réponse sont recalculées en Python pur à partir des coefficients
  exportés.
- **La relecture tourne dans le navigateur.** Le serveur envoie une fois les séries complètes d'une soudure ; les
  courbes, cartes et alarmes avancent ensuite côté client en lisant `video.currentTime`. Aucun aller-retour
  serveur pendant la lecture.
- **Rien n'est construit à partir d'une saisie brute.** Tout identifiant venu du navigateur (run, frame, options
  d'affichage) passe par une liste blanche avant de toucher au disque.
- **Aucune ressource tierce.** Polices, icônes, scripts et médias sont servis par l'app elle-même. La CSP
  interdit les scripts en ligne : toute logique client vit dans `assets/*.js`.

## 2. Organisation du code

| Fichier | Rôle |
|---|---|
| `__init__.py` | `create_app()` : coque Mantine (barre latérale, en-tête mobile), liste des sections, thème, installation de la sécurité, callback de navigation |
| `main.py` | point d'entrée : `python -m weldmon.app.main` en local, `weldmon.app.main:server` pour gunicorn ; préchauffe le registre des composants Dash avant le fork des workers |
| `data.py` | accès en lecture seule à `app_data/` (lectures mises en cache), liste blanche des runs (`valid_run`) |
| `security.py` | en-têtes HTTP (CSP, HSTS...), routes `/media/<fichier>` (liste blanche des noms de fichiers) et `/healthz` |
| `components.py` | composants partagés : icône Lucide, badge de verdict, en-tête de section avec bandeau d'explications |
| `theme.py` | couleurs (clair / sombre), échelles, gabarits d'axes et de mise en page Plotly |
| `tabs/*.py` | un module par onglet : constantes, `layout()`, fonctions de figures, callbacks |
| `assets/*.js` | logique côté client, une fonction par callback clientside |
| `assets/style.css` | styles, organisés par section (coque, barre latérale, puis un bloc par onglet) |

Dash charge automatiquement tout le contenu de `assets/` (CSS et JS) dans l'ordre alphabétique.

## 3. Cycle de vie d'une page

1. **Import** : `create_app()` importe les modules d'onglets. Leurs callbacks sont déclarés à l'import
   (décorateur `dash.callback`), donc **un module d'onglet doit pouvoir s'importer sans `app_data/`** (CI). Les
   données ne sont lues que dans les fonctions, jamais au niveau du module.
2. **Rendu** : les 5 sections sont construites une seule fois et toutes présentes dans le DOM ; une seule est
   visible. Changer d'onglet ne fait que basculer leur `display` (callback `nav.route`), ce qui rend la
   navigation instantanée et conserve l'état de chaque onglet.
   **Les graphes d'un onglet ne sont calculés qu'à sa première ouverture** : `nav.route` renseigne alors le store
   `{"type": "seen", "index": <section>}`, entrée des callbacks serveur des onglets Suivi, Analyses et
   Segmentation, qui ne font rien tant qu'il est vide. Le premier affichage ne paie que le monitoring.
3. **Navigation** : l'ancre de l'URL (`#process`, `#suivi`...) détermine la section affichée ; un lien direct
   ouvre donc la bonne page. Le store `goto` permet à un onglet d'en ouvrir un autre (« Ouvrir dans Monitoring
   process » depuis le suivi).
4. **Thème** : la bascule clair / sombre est gérée par Mantine. Les callbacks qui produisent des figures Plotly
   prennent `Input("color-scheme", "computedColorScheme")` pour se redessiner avec les bonnes couleurs.

## 4. Onglets

| Onglet | Module | Callbacks serveur | Callbacks client |
|---|---|---|---|
| Monitoring process | `tabs/process.py` | `load_run` : charge le run choisi dans le store `live-data` (séries, événements, limites, mises en page des courbes) | `weld.videoSource`, `weld.toggleMasks`, `weld.marks`, `weld.receive` ; relecture par une boucle JavaScript hors Dash |
| Suivi & historique | `tabs/history.py` | `update` : détail de la soudure sélectionnée et courbe des alarmes | `history.select`, `history.filter`, `history.open` |
| Analyses | `tabs/doe.py` | `update` : surface de réponse, effets, effets principaux, carte I-MR | aucun |
| Segmentation IA | `tabs/segmentation.py` | `load_seg` : courbes d'aires et d'IoU de la vidéo choisie | `seg.render`, `seg.togglePlay`, `seg.advance` |
| Méthode | `tabs/about.py` | aucun (page statique construite depuis `meta.json` et `seg_metrics.json`) | aucun |

**Monitoring process, en détail.** C'est l'onglet le plus dense.

- `load_run` envoie tout ce qu'il faut pour rejouer la soudure : `live_payload()` assemble les séries de
  `ts/<run>.json`, les événements avec leurs libellés, les limites (seuil de plasma, vigilance vitesse,
  instabilité, bornes du verdict) et les mises en page des 4 courbes (`chart_layouts()`).
- `weld.receive` garde ces données côté navigateur. Une **boucle JavaScript autonome** (`render`, toutes les
  100 ms) lit la position de la vidéo, en déduit l'index de frame (`floor(currentTime * 30)`) et révèle jusqu'à
  cet index les courbes (appel direct à `Plotly.react`), les cartes, l'anneau d'intégrité et le journal (écriture
  directe dans les éléments créés par Dash). Si l'image n'a pas changé (pause), elle ne fait rien.
- **Pourquoi hors de Dash** : avec un minuteur `dcc.Interval`, chaque pas faisait passer toute la mécanique de
  Dash sur la page, ce qui saturait un ordinateur modeste même en pause. Les éléments mis à jour par la boucle
  (`live-hud`, `laser-card`, `kpi-*`, `ring-*`, `events-log`, courbes `live-*`) ne doivent donc être la sortie
  d'aucun callback Dash.
- **Cadence adaptative** : la boucle mesure le coût du dessin des courbes et les espace pour qu'elles occupent au
  plus un tiers du temps (`CHART_SHARE`). Sur une machine rapide, elles suivent chaque pas ; sur une machine
  lente, elles avancent par pas plus grands et la page reste réactive.
- La timeline du lecteur (progression, tête de lecture) est animée à chaque image par `requestAnimationFrame`,
  hors callback Dash.
- « Lecture auto » (`prod-mode`) enchaîne les soudures dans l'ordre réel de production (`data.next_run`) : en fin
  de vidéo, la boucle change la soudure choisie par `dash_clientside.set_props("run-select", ...)`.

**Segmentation IA.** Les images comparées (annotation, prédiction ou désaccords) sont composées **dans le
navigateur** par `assets/seg.js`, à partir de fichiers statiques : la frame (`frames/NNN.webp`) et les deux cartes
de labels (`gt/NNN.png`, `pred/NNN.png`) de `app_data/media/seg/<run>/`. Le serveur ne calcule rien, et les
fichiers se mettent en cache. Pendant la lecture, la frame suivante n'est demandée qu'une fois la frame courante
dessinée, et les 6 suivantes sont chargées d'avance : sur un réseau lent, la lecture ralentit au lieu de geler.

## 5. Logique côté client

Chaque fichier JS enregistre un espace de noms dans `window.dash_clientside`, appelé depuis Python par
`ClientsideFunction("<espace>", "<fonction>")`.

| Fichier | Espace | Rôle |
|---|---|---|
| `nav.js` | `nav` | section visible, lien actif, barre repliée (préférence mémorisée dans le navigateur), menu mobile |
| `process.js` | `weld` | lecteur vidéo, synchronisation vidéo et signaux, cartes, journal d'événements |
| `history.js` | `history` | sélection d'une soudure, filtre par verdict, ouverture dans le monitoring |
| `seg.js` | `seg` | composition des images (frame + masques), curseur temporel, lecture et préchargement des frames |

Une fonction clientside renvoie ses sorties **dans l'ordre exact des `Output` déclarés en Python**, et
`window.dash_clientside.no_update` pour une sortie inchangée.

## 6. Contrats entre Python et JavaScript

Valeurs dupliquées des deux côtés : toute modification doit être reportée à l'identique, sinon l'app casse sans
erreur explicite.

| Python | JavaScript | Objet |
|---|---|---|
| `SECTIONS`, `DEFAULT_SECTION`, `NAV_WIDTH` (`__init__.py`) | `KEYS`, `DEFAULT`, `WIDTH` (`nav.js`) | clés et ordre des sections, largeur de la barre |
| `KPIS`, `CHARTS` et identifiants des cartes et courbes (`tabs/process.py`) | `KPIS`, `CHART_IDS` (`process.js`) | éléments mis à jour par la boucle de relecture |
| `FILTERS` (`tabs/history.py`) | `VERDICTS` (`history.js`) | ordre des filtres |
| `N_SEG_FRAMES` (`data.py`) | `N_FRAMES` (`seg.js`) | 164 frames par vidéo annotée |
| noms de fichiers de `app_data/media/` | URL construites dans `process.js` et `seg.js` | à garder conformes à `MEDIA_RE` (`security.py`) |

Les couleurs de classes (cordon, plasma, projections) sont aussi définies à trois endroits qui doivent rester
cohérents : `theme.TOKENS`, `segmentation.OVERLAY_COLORS` (images composées dans le navigateur) et `pipeline/06_infer.OVERLAY` (vidéos
IA, en BGR).

## 7. Performances du rendu

Le serveur ne calcule presque rien : ce qui compte pour la fluidité, c'est le travail du **navigateur**. Deux
séries d'optimisations ont été menées, mesurées avant et après dans les mêmes conditions.

### Lecture de l'onglet Segmentation (v0.5.3)

**Symptôme** : en ligne, les images ne défilaient pas pendant la lecture ; seule la pause les faisait apparaître.
En local, aucun problème.

**Cause** : chaque image était composée par le serveur (frame et masques peints par Pillow, route `/overlay`). En
ligne, une image arrivait en environ 180 ms, alors que la lecture passait à la frame suivante toutes les 120 ms
en demandant deux nouvelles images. Le navigateur abandonnait chaque chargement avant la fin pour lancer le
suivant : rien ne s'affichait jamais, et le serveur composait en pure perte les images abandonnées.

**Correction** : composition dans le navigateur à partir des fichiers statiques de `app_data/media/seg/`, lecture
qui attend que la frame courante soit dessinée et préchargement des 6 suivantes (voir la section 4).

| | Avant | Après |
|---|---|---|
| Calcul serveur par image | environ 70 ms sur une petite instance Render (4 ms en local) | aucun |
| Données par frame | environ 96 Ko (deux JPEG) | environ 36 Ko (frame et deux cartes), mises en cache |
| Lecture avec 200 ms de latence réseau | gelée | 6,6 frames/s (8,3 au plus), image toujours synchrone avec le curseur |
| Fidélité des images | référence | écart moyen inférieur à 2 niveaux sur 255 avec l'ancienne composition |

### Monitoring et chargement de la page (v0.5.4)

**Diagnostic** (profil CPU pendant la relecture, processeur ralenti) : 44 % du temps dans le moteur de Dash, 20 %
dans le dessin Plotly. Un minuteur Dash (`dcc.Interval`) déclenchait toutes les 100 ms un callback qui faisait
transiter les quatre figures complètes par Dash. Le coût venait du passage par Dash lui-même, sur une page de
plusieurs centaines de composants. Appelé directement, `Plotly.react` ne coûte qu'environ 5 ms par graphe.

**Corrections** :

1. Relecture sortie de la boucle Dash : une boucle JavaScript autonome met à jour directement les courbes et les
   cartes, avec une cadence des courbes adaptée au coût mesuré (section 4).
2. Graphes des onglets Suivi, Analyses et Segmentation calculés à leur première ouverture, et non au chargement
   de la page (section 3).

| Mesure | Processeur | v0.5.3 | v0.5.4 |
|---|---|---|---|
| Relecture | normal | occupé 83 % | **pratiquement 0 %** (aucune tâche longue) |
| Relecture | ralenti 4 fois | occupé 93 %, gels jusqu'à 458 ms | **occupé 39 %, gels de moins de 90 ms** |
| Vidéo en pause | ralenti 4 fois | occupé 61 % | **0 %** |
| Calcul au chargement | normal | 3,6 s | **0,7 s** |
| Calcul au chargement | ralenti 4 fois | 12,6 s | **7,8 s** |
