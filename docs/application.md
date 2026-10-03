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
7. [Thème et mise en page](#7-thème-et-mise-en-page)
8. [Faire évoluer l'application](#8-faire-évoluer-lapplication)

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
| `security.py` | en-têtes HTTP (CSP, HSTS...), routes `/media/<fichier>`, `/overlay/<run>/<k>.jpg`, `/healthz` |
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
3. **Navigation** : l'ancre de l'URL (`#process`, `#suivi`...) détermine la section affichée ; un lien direct
   ouvre donc la bonne page. Le store `goto` permet à un onglet d'en ouvrir un autre (« Ouvrir dans Monitoring
   process » depuis le suivi).
4. **Thème** : la bascule clair / sombre est gérée par Mantine. Les callbacks qui produisent des figures Plotly
   prennent `Input("color-scheme", "computedColorScheme")` pour se redessiner avec les bonnes couleurs.

## 4. Onglets

| Onglet | Module | Callbacks serveur | Callbacks client |
|---|---|---|---|
| Monitoring process | `tabs/process.py` | `load_run` : charge le run choisi dans le store `live-data` (séries, événements, limites, mises en page des courbes) | `weld.videoSource`, `weld.toggleMasks`, `weld.marks`, `weld.tick` |
| Suivi & historique | `tabs/history.py` | `update` : détail de la soudure sélectionnée et courbe des alarmes | `history.select`, `history.filter`, `history.open` |
| Analyses | `tabs/doe.py` | `update` : surface de réponse, effets, effets principaux, carte I-MR | aucun |
| Segmentation IA | `tabs/segmentation.py` | `load_seg` : courbes d'aires et d'IoU de la vidéo choisie | `seg.render`, `seg.togglePlay`, `seg.advance` |
| Méthode | `tabs/about.py` | aucun (page statique construite depuis `meta.json` et `seg_metrics.json`) | aucun |

**Monitoring process, en détail.** C'est l'onglet le plus dense.

- `load_run` envoie tout ce qu'il faut pour rejouer la soudure : `live_payload()` assemble les séries de
  `ts/<run>.json`, les événements avec leurs libellés, les limites (seuil de plasma, vigilance vitesse,
  instabilité, bornes du verdict) et les mises en page des 4 courbes (`chart_layouts()`).
- `weld.tick` est appelé toutes les 100 ms (`dcc.Interval` `live-tick`). Il lit la position de la vidéo, en
  déduit l'index de frame (`floor(currentTime * 30)`) et révèle les courbes, les cartes, l'anneau d'intégrité et
  le journal jusqu'à cet index. Si rien n'a changé (pause), il ne renvoie rien.
- La timeline du lecteur (progression, tête de lecture) est animée à chaque image par `requestAnimationFrame`,
  hors callback Dash.
- « Lecture auto » (`prod-mode`) enchaîne les soudures dans l'ordre réel de production (`data.next_run`).

**Segmentation IA.** Les images comparées (annotation, prédiction ou désaccords) sont composées à la demande par
la route `/overlay` de `security.py` à partir de `app_data/media/seg/`, puis mises en cache. Le changement de
frame ne déclenche aucun callback serveur : `seg.render` calcule simplement l'URL de l'image.

## 5. Logique côté client

Chaque fichier JS enregistre un espace de noms dans `window.dash_clientside`, appelé depuis Python par
`ClientsideFunction("<espace>", "<fonction>")`.

| Fichier | Espace | Rôle |
|---|---|---|
| `nav.js` | `nav` | section visible, lien actif, barre repliée (préférence mémorisée dans le navigateur), menu mobile |
| `process.js` | `weld` | lecteur vidéo, synchronisation vidéo et signaux, cartes, journal d'événements |
| `history.js` | `history` | sélection d'une soudure, filtre par verdict, ouverture dans le monitoring |
| `seg.js` | `seg` | URL des images composées, curseur temporel, lecture automatique des frames |

Une fonction clientside renvoie ses sorties **dans l'ordre exact des `Output` déclarés en Python**, et
`window.dash_clientside.no_update` pour une sortie inchangée.

## 6. Contrats entre Python et JavaScript

Valeurs dupliquées des deux côtés : toute modification doit être reportée à l'identique, sinon l'app casse sans
erreur explicite.

| Python | JavaScript | Objet |
|---|---|---|
| `SECTIONS`, `DEFAULT_SECTION`, `NAV_WIDTH` (`__init__.py`) | `KEYS`, `DEFAULT`, `WIDTH` (`nav.js`) | clés et ordre des sections, largeur de la barre |
| sorties de `weld.tick` (`tabs/process.py`) | `KPIS`, `N_OUTPUTS` (`process.js`) | nombre et ordre des sorties du tick |
| `FILTERS` (`tabs/history.py`) | `VERDICTS` (`history.js`) | ordre des filtres |
| `N_SEG_FRAMES` (`data.py`) | `N_FRAMES` (`seg.js`) | 164 frames par vidéo annotée |
| noms de fichiers de `app_data/media/` | URL construites dans `process.js` et `seg.js` | à garder conformes à `MEDIA_RE` (`security.py`) |

Les couleurs de classes (cordon, plasma, projections) sont aussi définies à trois endroits qui doivent rester
cohérents : `theme.TOKENS`, `security.OVERLAY_COLORS` (images composées) et `pipeline/06_infer.OVERLAY` (vidéos
IA, en BGR).

## 7. Thème et mise en page

- **Couleurs** : un violet unique (`#8C18CC`) et ses nuances pour l'interface et les courbes de procédé. Le doré
  signale la vigilance, le rouge l'alarme ; un statut n'est jamais porté par la couleur seule (toujours une icône
  et un libellé). Les classes de segmentation gardent leurs couleurs propres dans tous les graphiques et vidéos.
- **Deux sources de couleurs** : les variables CSS de `style.css` (interface) et `theme.TOKENS` (figures Plotly,
  qui ne lisent pas le CSS). Une modification de palette se fait aux deux endroits.
- **Plein écran** : chaque page tient sans défilement en 1920 × 1080. Les proportions sont pilotées par la
  largeur (contenu plafonné à 1648 px) ; en fenêtre plus petite, la page garde ses proportions et défile. Si une
  mise à l'échelle devenait nécessaire, utiliser `transform` et non la propriété CSS `zoom`, qui casse le survol
  des graphiques Plotly.

## 8. Faire évoluer l'application

**Lancer en local** : `make app` (port 8050, variable `PORT`). L'app cherche ses données dans `app_data/` à la
racine du dépôt, ou dans le dossier indiqué par `WELDMON_DATA`.

**Ajouter un onglet**

1. Créer `tabs/<nom>.py` avec une fonction `layout()` qui commence par `components.section_header(...)`.
2. L'ajouter à `SECTIONS` dans `__init__.py` (clé, libellé, icône Lucide, constructeur).
3. Ajouter la clé à `KEYS` dans `nav.js`, à la même position.
4. Si l'icône est nouvelle : déposer le SVG Lucide dans `assets/icons/` et déclarer la classe `.icon-<nom>` dans
   `style.css`.
5. Ajouter un test de rendu dans `tests/test_app.py`.

**Ajouter un indicateur à un onglet** : le calculer dans le pipeline (`07_signals.py` pour un signal ou un KPI),
l'exporter (`09_export.py`), puis le lire via `data.py`. Ne jamais ajouter de calcul numpy / pandas dans l'app.

**Ajouter une route ou un média** : passer par `security.py`, avec une expression régulière ou une liste blanche
stricte, et un test de rejet des chemins invalides.

**Tests** : `make test`. Les tests de `tests/test_app.py` vérifient les en-têtes de sécurité, les routes, la
liste blanche et le rendu de chaque onglet ; ils sont sautés si `app_data/` est absent.
