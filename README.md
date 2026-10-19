# DataZen 🧹

**DataZen** est une application de nettoyage de données (*DataClean Pro*), construite avec
**Django**, **Pandas** et **Bootstrap**. Elle permet de téléverser des fichiers CSV ou Excel,
de les nettoyer et d'exporter les résultats.

## 🚀 Technologies

| Technologie | Rôle |
|-------------|------|
| Python 3    | Langage principal |
| Django      | Framework web |
| Pandas      | Manipulation et nettoyage des données |
| matplotlib  | Génération des graphiques statistiques (rendu serveur, PNG de repli) |
| seaborn     | Graphiques statistiques avancés (histogrammes, heatmap, boxplots) |
| React 18    | Rendu interactif des graphiques côté navigateur |
| Chart.js 4  | Moteur de dessin des graphiques interactifs |
| Vite 5      | Bundler du frontend React |
| openpyxl    | Lecture/écriture des fichiers Excel |
| Bootstrap 5 | Interface utilisateur |
| HTML + CSS  | Structure et styles |

## 🌍 Langues

L’interface propose un sélecteur avec drapeaux pour 23 langues : français, anglais,
espagnol, allemand, italien, portugais, néerlandais, arabe, chinois simplifié,
russe, japonais, coréen, turc, hindi, polonais, suédois, danois, finnois, tchèque,
roumain, vietnamien, thaï et indonésien. Le français reste la langue par défaut ;
l’arabe active une mise en page de droite à gauche.

Les catalogues sont générés sans GNU gettext :

```powershell
python tools\i18n_extract.py --out files\inventory.json
python tools\i18n_build.py --stats
python tools\i18n_build.py
```

Pour ajouter une traduction, compléter le module correspondant dans
`tools/translations/`, puis régénérer les catalogues `.po` et `.mo`.

L'extracteur unifie les trois familles d'appels sous un même contrat
`(msgid, pluriel, contexte)` : les formes contextuelles
(`{% translate "ou" context "séparateur" %}`, `pgettext`, `npgettext`) sont
écrites avec un `msgctxt` dans le `.po` et sous la clé `contexte\x04msgid` dans
le `.mo`, ce qui permet à `pgettext()` de les résoudre.

Les libellés produits en JavaScript (bascule de mot de passe, thème clair/sombre,
filtre de tableau, info-bulle de tri, confirmation de copie) ne sont pas scannés
par l'extracteur : ils sont exposés sur `<body>` via des attributs
`data-dz-msg-*` remplis par `{% translate %}` puis lus par le helper `dzMsg()`
de `static/js/main.js`.

## 📁 Structure du projet

```
DataZen/
├── manage.py                 # Utilitaire de commande Django
├── requirements.txt          # Dépendances Python
├── datazen/                  # Configuration du projet
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── core/                     # Application principale
│   ├── models.py             # Modèles (DataFile, CleaningRule, ActivityLog, ApiToken, Webhook, Profile)
│   ├── views.py              # Vues
│   ├── views_pro.py          # Vues du pack « pro » + API REST (jeton Bearer)
│   ├── forms.py              # Formulaires
│   ├── urls.py               # Routage
│   ├── admin.py              # Administration
│   ├── tests.py              # Tests (auth, asynchrone, règles, pack « pro »)
│   ├── migrations/           # Migrations de base de données
│   └── services/             # Logique métier
│       ├── cleaning.py       # Classe DataCleaner (moteur de nettoyage)
│       ├── pipeline.py       # Pipeline partagé (synchrone / asynchrone)
│       ├── charts.py         # Graphiques matplotlib / seaborn
│       ├── overview.py       # Agrégation du tableau de bord global
│       ├── comparison.py     # Comparaison avant / après nettoyage
│       ├── pdf.py            # Rapport PDF autonome (sans dépendance externe)
│       ├── api.py            # Jetons, webhooks et envois signés
│       ├── retention.py      # Politique de conservation / purge
│       ├── activity.py       # Journal d'activité
│       ├── search.py         # Recherche globale multi-sources (palette Ctrl+K)
│       └── async_runner.py   # Exécution en arrière-plan (threads)
├── templates/                # Templates HTML
│   └── core/
│       ├── base.html         # Layout Bootstrap
│       ├── index.html        # Page d'accueil
│       ├── login.html        # Connexion
│       ├── signup.html       # Inscription
│       ├── password_reset*.html  # Mot de passe oublié (4 étapes)
│       ├── profile.html      # Profil utilisateur (photo, bio)
│       ├── dataset_analysis.html # Analyse exploratoire (graphiques)
│       ├── dataset_comparison.html # Comparaison avant / après
│       ├── dashboard.html    # Tableau de bord global (pilotage)
│       ├── activity.html     # Journal d'activité
│       ├── api_tokens.html   # Jetons d'API
│       ├── webhooks.html     # Webhooks
│       ├── retention.html    # Politique de rétention
│       ├── shortcuts.html    # Raccourcis clavier
│       └── rules.html        # Règles personnalisées
├── frontend/                 # Application React (graphiques interactifs)
│   ├── package.json          # Dépendances npm (React, Chart.js, Vite)
│   ├── vite.config.js        # Build vers static/js/charts/
│   └── src/
│       ├── main.jsx          # Point d'entrée (montage sur [data-dz-charts])
│       ├── register.js       # Enregistrement des composants Chart.js
│       ├── App.jsx           # Chargement du JSON + répartition par type
│       ├── theme.js          # Palette, options Chart.js, HiDPI
│       ├── plugins.js        # Plugins (pistes, texte centré, moustaches)
│       ├── format.js         # Formatage localisé des nombres
│       └── charts/           # 7 composants de graphiques
├── static/                   # Fichiers statiques (CSS, JS)
│   ├── css/style.css         # Feuille de style unique
│   ├── img/                  # Affiches des vidéos de fond (générées)
│   │   ├── hero-poster.jpg   # Affiche de la page d'accueil
│   │   ├── login-poster.jpg  # Affiche de la page de connexion
│   │   ├── logo-datazen.png  # Logo (détouré, thème clair)
│   │   ├── logo-datazen-dark.png  # Logo éclairci pour le thème sombre
│   │   ├── favicon.ico       # Icône d'onglet multi-tailles (16/32/48/64)
│   │   └── favicon-180.png   # Icône Apple Touch (180 px, fond blanc)
│   ├── video/                # Vidéos de fond décoratives (générées)
│   └── js/charts/
│       └── datazen-charts.js # Bundle React compilé (généré)
├── design/                   # Sources de design (non servies, hors static/)
│   ├── logo-source.png       # Logo d'origine, intrant de make_logo_asset.py
│   └── mockup-reference.jpg  # Maquette de référence de la refonte
├── tools/                    # Outillage de développement
│   ├── i18n_extract.py       # Collecte des chaînes traduisibles
│   ├── i18n_build.py         # Génération des catalogues .po / .mo
│   ├── video_kit.py          # Encodeur ffmpeg partagé par les générateurs
│   ├── generate_hero_video.py  # Vidéo de fond du héros (MP4 / WebM + affiche)
│   ├── generate_login_video.py # Tableau de bord animé de la connexion
│   ├── make_logo_asset.py    # Détourage du logo source (clair + sombre)
│   ├── make_favicon.py       # Icône d'onglet dérivée de la marque
│   └── translations/         # Traductions hors code source
│       ├── ui_strings.py     # Libellés générés par JavaScript
│       ├── search_labels.py  # Libellés de la palette de recherche
│       └── …                 # Autres tables de traduction
└── media/                    # Fichiers téléversés
```

## 🛠️ Installation

1. **Créer un environnement virtuel** (depuis le dossier `DataZen`) :

   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

2. **Installer les dépendances** :

   ```powershell
   pip install -r requirements.txt
   ```

3. **Fournir un PostgreSQL** — le moteur par défaut. Copiez `.env.example` vers
   `.env` et renseignez `DJANGO_DB_PASSWORD` (voir
   [Base de données](#2-base-de-données)). Sans serveur PostgreSQL,
   `DJANGO_DB_ENGINE=sqlite` permet de travailler sur `db.sqlite3`.

4. **Appliquer les migrations** :

   ```powershell
   python manage.py migrate
   ```

5. **Créer un super-utilisateur** (pour accéder à l'administration) :

   ```powershell
   python manage.py createsuperuser
   ```

6. **Lancer le serveur de développement** :

   ```powershell
   python manage.py runserver
   ```

   Ouvrez ensuite <http://127.0.0.1:8000/>.

   La clé de signature est générée au premier démarrage dans `var/dev_secret_key`
   (ignoré par Git) puis réutilisée. Cette persistance est indispensable : une
   clé qui changerait à chaque redémarrage rendrait indéchiffrables les sessions
   en cours, avec des messages « Session data corrupted » et la perte des
   préférences (langue de l'interface, options de nettoyage). Pour la définir
   vous-même, renseignez la variable d'environnement `DJANGO_SECRET_KEY`.

   7. **Compiler les graphiques interactifs** (facultatif — le bundle est déjà
      versionné dans `static/js/charts/`) :

      ```powershell
      cd frontend
      npm install
      npm run build
      ```

      Le bundle est écrit dans `static/js/charts/datazen-charts.js`. Après un
      rebuild, incrémentez la chaîne de version `?v=…` du `<script>` dans
      `templates/core/base.html` pour invalider le cache navigateur.

   8. **Régénérer les vidéos de fond** (facultatif — les fichiers de
      `static/video/` sont versionnés) :

      ```powershell
      python tools\generate_hero_video.py
      python tools\generate_login_video.py
      python tools\generate_login_video.py --preview 3
      ```

      Les scripts dessinent une animation de 10 s (240 images à 24 i/s) avec
      numpy et Pillow, puis l'encodent en MP4 (H.264) et WebM (VP9) via le
      binaire ffmpeg fourni par `imageio-ffmpeg` : aucun ffmpeg système n'est
      requis. `tools/video_kit.py` mutualise l'encodage et le flou gaussien.

      - `generate_hero_video.py` → `static/video/hero.mp4`, `hero.webm` et
        l'affiche `static/img/hero-poster.jpg` (halos, trame de points,
        histogramme balayé par un faisceau).
      - `generate_login_video.py` → `static/video/login.mp4`, `login.webm` et
        l'affiche `static/img/login-poster.jpg` (tableau de bord animé :
        histogramme qui respire, anneau de répartition, graphique en courbes
        avec aire remplie et curseur, nuage de points).

      Les affiches servent de `poster` et de repli `prefers-reduced-motion`.
      L'option `--preview N` exporte des images PNG dans `files/_*_preview/`
      pour contrôler le rendu sans encoder.

   ## ✨ Fonctionnalités

- **Import** de fichiers CSV / Excel (`.csv`, `.xlsx`, `.xls`).
- **Détection** des problèmes : doublons exacts/potentiels, valeurs manquantes,
  valeurs « Inconnu », emails/dates/téléphones invalides.
- **Nettoyage** configurable : déduplication, normalisation (casse, emails,
  téléphones, dates, montants), remplissage des valeurs manquantes.
- **Score de qualité** sur 100 (complétude, validité, unicité, cohérence,
  conformité) avec explication détaillée.
- **Dashboard Data Quality** : indicateurs, dimensions, qualité par colonne,
  statistiques descriptives.
- **Profilage avancé** : pour chaque colonne, type détecté, complétude, valeurs
  uniques, mode, min/max, moyenne, médiane, écart-type, **variance**,
  **asymétrie**, **aplatissement** (kurtosis), quartiles Q1/Q3 et valeurs
  aberrantes (méthode IQR). Le rapport Markdown/HTML reprend ce profilage dans
  une section « 🔬 Profilage statistique » avec lecture interprétative
  (distribution la plus asymétrique, la plus pointue, colonnes les plus
  touchées par les valeurs aberrantes).
- **Anomalies structurelles** : détection des colonnes vides, constantes,
  quasi constantes, à identifiant non unique ou à type hétérogène — signalées
  avec leur sévérité, jamais modifiées automatiquement.
- **Opérations de nettoyage traduites à l'affichage** : le pipeline mémorise
  des codes stables (`core/services/operations.py`) et non du texte déjà
  traduit, si bien que la liste des opérations, l'explication du score, le
  journal des modifications et le rapport suivent la langue active de
  l'interface même si le nettoyage a été lancé dans une autre langue. Les
  sessions enregistrées avant l'introduction des codes (texte déjà traduit)
  sont reconnues puis retraduites à l'affichage, au lieu de rester figées.
- **Revue manuelle** des doublons potentiels (jamais supprimés automatiquement).
- **Traçabilité** : journal des modifications (change log) et rapport de
  nettoyage.
- **Consultation du rapport** directement dans le navigateur (Markdown → HTML)
  et export HTML autonome.
- **Export** des données nettoyées en CSV ou Excel (conversion à la volée).
- **Tableau de bord d'accueil** : statistiques globales et filtre par statut.
- **Interface soignée** : thème de marque indigo → violet → cyan, héros animé,
  cartes de statistiques, navigation translucide, animations d'apparition
  respectant `prefers-reduced-motion`, et **mode sombre** persistant.
- **Recherche/tri** dans les tableaux.
- **Comptes utilisateurs** : inscription, connexion, déconnexion et
  **réinitialisation du mot de passe** (« Mot de passe oublié ? » sur la page de
  connexion). Chaque utilisateur ne voit que ses propres fichiers (les
  super-utilisateurs voient tout).
- **Accès protégé** : l'application entière exige un compte connecté
  (`LoginRequiredMiddleware`). Seules les pages d'authentification (connexion,
  inscription, réinitialisation du mot de passe) et le changement de langue
  restent accessibles aux visiteurs anonymes ; tout le reste redirige vers
  `/accounts/login/?next=…`. Aucun fichier ne peut être téléversé ni nettoyé
  sans être connecté à son propre compte.
- **Traitement asynchrone** : le nettoyage s'exécute en arrière-plan (thread)
  avec une barre de progression interrogée en JSON, sans bloquer la requête.
- **Règles de nettoyage personnalisées** : création de règles réutilisables
  (déduplication, espaces, casse, emails, téléphones, dates, montants,
  remplissage, anonymisation), activables/désactivables et applicables à un
  nettoyage. Les règles appliquées apparaissent dans le journal des
  modifications avec le préfixe `[Règle]`.
- **Profil utilisateur** : page `/profile/` permettant de modifier son prénom,
  son nom, son adresse email et sa présentation, et de **téléverser une photo
  de profil** (JPEG, PNG, WebP ou GIF, 5 Mo maximum) avec aperçu immédiat avant
  envoi. L'avatar apparaît dans la barre de navigation ; en l'absence de photo,
  un **avatar par défaut** (`static/img/avatar-default.svg`) est affiché. La
  photo peut être supprimée à tout moment. Un profil est créé automatiquement à
  l'inscription.
- **Sélecteur d'avatar façon Facebook** : sur la page de profil, l'avatar
  lui-même est un bouton — un clic ouvre le sélecteur de fichiers de l'appareil
  (ordinateur ou téléphone). Une icône **appareil photo** dans le coin inférieur
  droit de l'avatar ouvre une fenêtre modale qui active la webcam
  (`getUserMedia`), affiche un aperçu en direct et capture une image carrée
  centrée. Dans les deux cas, l'aperçu se met à jour immédiatement et une barre
  « Enregistrer / Annuler » permet de confirmer ou de revenir à la photo
  précédente. La capture webcam nécessite un contexte sécurisé (HTTPS ou
  `localhost`) ; à défaut, un message explicatif s'affiche et le choix d'un
  fichier reste disponible.
- **Profil enrichi** :
  - *Informations professionnelles* : intitulé de poste, organisation, lieu et
    site web (validé comme URL).
  - *Préférences* : thème (système / clair / sombre, appliqué dès la connexion),
    format de date (`JJ/MM/AAAA`, `MM/JJ/AAAA`, `AAAA-MM-JJ`), notifications par
    e-mail et visibilité du profil.
  - *Jauge de complétion* : pourcentage calculé sur 9 critères, avec la liste des
    éléments manquants.
  - *Activité récente* : 5 derniers fichiers importés et 5 dernières règles
    créées.
  - *Sécurité et données* : changement de mot de passe en ligne
    (`/profile/password/`, la session reste active) et **export JSON** de toutes
    ses données (`/profile/export/`).
  - *Zone de danger* : suppression définitive du compte
    (`/profile/delete/`), protégée par la saisie du nom d'utilisateur et
    interdite aux super-utilisateurs.
  - *Profil public* : page `/u/<nom_utilisateur>/` accessible uniquement si
    l'utilisateur a activé « Profil public ».
- **Navigation réservée au staff** : le lien « Administration » (barre de
  navigation et pied de page) n'apparaît que pour les comptes `is_staff`.

## 🏢 Pack « pro »

Cinq familles de fonctionnalités rapprochent DataZen d'un outil de production.

### 📊 Pilotage — tableau de bord global (`/dashboard/`)

`core/services/overview.py` agrège **tous** les fichiers visibles à partir des
indicateurs figés en base (`metrics`, `quality_after`, `rows_count`…) : aucun
fichier n'est relu au moment de l'affichage, la page reste donc instantanée même
avec des milliers de lignes.

- KPI globaux : fichiers, nettoyés, en attente, erreurs, archivés, lignes,
  colonnes, problèmes, corrections ;
- score moyen, meilleur / moins bon score, catégorie qualitative ;
- distribution par tranche de qualité et répartition des problèmes
  (doublons, doublons potentiels, « Inconnu », aberrantes, erreurs, manquants) ;
- dimensions qualité les plus faibles, classement des fichiers à traiter ;
- **sparkline** des scores et **frise chronologique** sur 12 semaines.

### 🛡️ Confiance — comparaison avant/après et rapport PDF

- `/datasets/<id>/comparison/` : `core/services/comparison.py` met en regard les
  indicateurs *avant* et *après* nettoyage (lignes, colonnes, problèmes,
  dimensions, score) avec deltas signés et colorés ;
- `/datasets/<id>/report/pdf/` : `core/services/pdf.py` produit un rapport PDF
  autonome (synthèse, comparaison, graphiques, journal) — **sans dépendance
  externe**, le PDF est écrit à la main (`%PDF`, table xref). L'activité
  `REPORT` est journalisée.

### ⚡ Productivité — recherche globale, historique, raccourcis

- **Palette de commandes `Ctrl+K`** (alias `⌘K`) : recherche instantanée
  (`/search/`, `views_pro.global_search`) alimentée par
  `core/services/search.py`, qui agrège **six sources** en une seule requête :
  fichiers, règles de nettoyage, pages de l'interface, journal d'activité,
  jetons d'API et webhooks. Chaque résultat porte un libellé de famille, une
  infobulle contextuelle et la portion de texte trouvée, mise en évidence
  dans la palette ;
- **Tout est indexé, pas seulement les noms** : un fichier est trouvable par
  une de ses colonnes (noms figés dans `DataFile.metrics["columns"]` au
  nettoyage), une règle par son opération ou sa colonne cible, une page par
  son URL ou ses mots-clés anglais (`dashboard`, `rgpd`, `webhook`…), un
  webhook par son URL ;
- **Comparaison insensible à la casse et aux accents** : « regles » trouve
  « Règles de nettoyage ». Le repliage se fait en Python
  (`unicodedata.normalize("NFKD")`), car le `LIKE` de SQLite ne sait pas
  replier les accents ; les requêtes sont donc bornées (`SCAN_LIMIT`) avant
  filtrage ;
- **Classement déterministe** : score de pertinence (exact 100, préfixe 85,
  début de mot 70, sous-chaîne 50), puis priorité de famille, longueur et
  libellé. Chaque famille est plafonnée (`PER_TYPE`) pour qu'aucune ne sature
  la palette, et l'ensemble est tronqué à `MAX_RESULTS` ;
- `/activity/` : journal d'activité filtrable par action avec statistiques
  (`ActivityLog` : upload, nettoyage, export, rapport, graphiques, règles,
  archivage, suppression, connexion, API, jetons) ;
- `/shortcuts/` : aide-mémoire des raccourcis clavier.

### 🔌 Intégration — API REST, jetons, webhooks

- **API REST en lecture** (`/api/`), authentifiée par **jeton Bearer**
  (`Authorization: Bearer dz_…` ou `?token=`) :
  `GET /api/` (index), `/api/datasets/`, `/api/datasets/<id>/`,
  `/api/datasets/<id>/changelog/`, `/api/datasets/<id>/download/`,
  `/api/stats/`. Réponses JSON stables (`401 invalid_token`, `404 not_found`,
  `409 no_cleaned_data`) ;
- `/api/tokens/` : création (le jeton en clair n'est affiché **qu'une fois**,
  seul un hachage salé SHA-256 est stocké), expiration, compteur d'appels et
  révocabilité ;
- `/api/webhooks/` : notification HTTP POST signée (`X-DataZen-Signature`,
  HMAC-SHA256) à chaque événement (`cleaning_done`, `cleaning_error`, `upload`,
  `delete`), avec bouton **Tester** et suivi du dernier statut. L'envoi est
  asynchrone (thread) et n'affecte jamais le traitement.

### 🗄️ Rétention — gouvernance des données (`/retention/`)

`core/services/retention.py` applique la politique définie dans le profil :
durée de conservation (`Profile.retention_days`, `0` = illimité, défaut 180 j)
et purge automatique facultative. Les fichiers devenus périmés sont **archivés**
ou **purgés** au choix, avec aperçu des fichiers concernés avant action.
L'archivage exempte un fichier de la règle.

## 📈 Visualisation des données (matplotlib + seaborn + React)

Le traitement statistique des données nettoyées s'appuie sur **matplotlib** et
**seaborn** (`core/services/charts.py`). Les figures sont rendues côté serveur
avec le backend **Agg** (aucun affichage graphique requis) puis servies en PNG.

Depuis la version « full HD », les mêmes graphiques sont **rejoués côté
navigateur** par une application **React + Chart.js** (`frontend/`) : les PNG
servent de repli (JavaScript désactivé, réseau indisponible) tandis que les
versions interactives offrent infobulles, animations et rendu HiDPI.

### Graphiques disponibles

| Slug | Graphique | Bibliothèque | Composant React |
|------|-----------|--------------|-----------------|
| `score` | Jauge du score de qualité global (sur 100) | matplotlib | `ScoreGauge` |
| `dimensions` | Contribution des 5 dimensions pondérées du score | matplotlib | `HorizontalBars` |
| `missing` | Taux de remplissage par colonne | matplotlib | `HorizontalBars` |
| `problems` | Volume des anomalies restantes par catégorie | matplotlib | `VerticalBars` |
| `histograms` | Histogrammes des colonnes numériques | seaborn `histplot` | `Histograms` |
| `boxplots` | Dispersion et valeurs extrêmes (boîtes à moustaches) | seaborn `boxplot` | `BoxPlots` |
| `correlation` | Matrice de corrélation de Pearson | seaborn `heatmap` | `CorrelationHeatmap` |
| `categories` | Top 8 des valeurs les plus fréquentes | matplotlib | `CategoryPanels` |
| `outliers` | Nombre de valeurs aberrantes (méthode IQR) par colonne | matplotlib | `HorizontalBars` |
| `moments` | Asymétrie et aplatissement (moments centrés) des colonnes numériques | matplotlib | `DistributionMoments` |
| `structural` | Anomalies structurelles par type (colonnes vides, constantes…) | matplotlib | `HorizontalBars` |

### Où les retrouver

- **Page du fichier** (`/datasets/<id>/`) : section « 📈 Visualisations
  statistiques » avec les 4 graphiques de synthèse.
- **Analyse exploratoire** (`/datasets/<id>/analysis/`) : page dédiée présentant
  un tableau de bord KPI (score, lignes, colonnes, doublons, valeurs inconnues,
  erreurs et valeurs aberrantes), l'ensemble des graphiques disponibles et les
  colonnes numériques détectées.
- **Rapport HTML** (`/datasets/<id>/report/html/`) : les graphiques sont
  **embarqués en base64** (`data:image/png;base64,…`) afin que le document
  exporté reste totalement autonome, même hors ligne.

### Graphiques interactifs (React + Chart.js)

- **Endpoint JSON** : `/datasets/<id>/chart-data/` renvoie l'ensemble des
  graphiques sous forme de données brutes (`{language, direction, separators,
  charts: [{slug, title, description, kind, data}]}`), avec
  `Cache-Control: private, max-age=3600` et `Vary: Cookie`.
- **Montage** : chaque `.dz-chart-frame` porte `data-dz-charts`,
  `data-dz-chart="<slug>"` et `data-dz-chart-data-url`. `main.jsx` monte un
  composant React par cadre et ajoute la classe `dz-chart-live`, ce qui masque
  le PNG de repli en CSS.
- **Repli gracieux** : si le `fetch` échoue ou si JavaScript est désactivé, la
  classe n'est jamais ajoutée et l'image PNG reste affichée.
- **HiDPI** : `devicePixelRatio: Math.max(2, window.devicePixelRatio || 1)` dans
  `theme.js` — les canvas sont rendus au minimum en 2×, donc nets sur écrans
  Retina et en plein écran.
- **Thème** : `App.jsx` observe l'attribut `data-bs-theme` sur `<html>` et
  redessine les graphiques lors du basculement clair/sombre.
- **Localisation** : les libellés viennent du serveur (déjà traduits) et les
  nombres sont formatés côté client avec les séparateurs renvoyés par l'API
  (`format.js`), ce qui garantit la cohérence avec les PNG.
- **Enregistrement Chart.js** : `register.js` doit être importé **avant** tout
  composant de graphique (c'est le premier import de `main.jsx`), sinon
  `react-chartjs-2` échoue avec `"arc" is not a registered element`.

### Points techniques

- **Rendu « full HD »** : les figures sont dimensionnées en pouces puis
  multipliées par la résolution (`DPI = 200`, `FULL_WIDTH = 9.6` in ≈ 1920 px,
  `HALF_WIDTH = 4.8` in). Les images restent nettes une fois réduites dans une
  carte ou un rapport, et s'affichent en pleine largeur (`width: 100%`).
- **Habillage** : palette de marque DataZen, cadres supérieur et droit retirés,
  grilles discrètes tracées **sous** les données (`_soft_grid`), titres alignés
  à gauche, étiquettes de valeur sur les barres, pistes claires pour les jauges
  (`_hbar_track`) et courbe de densité superposée aux histogrammes.
- **Endpoint PNG** : `/datasets/<id>/chart/<slug>.png` renvoie l'image avec
  `Cache-Control: private, max-age=3600`, ce qui allège la page et met les
  graphiques en cache côté navigateur.
- **Thème `auto`** : le thème de l'interface est stocké dans `localStorage` et
  donc invisible côté serveur. Les graphiques sont générés par défaut avec un
  fond **transparent** et un texte gris neutre, ce qui les rend lisibles en mode
  clair comme en mode sombre. Le paramètre `?theme=light|dark` permet de forcer
  un thème.
- **Détection des colonnes** : `numeric_columns()` et `categorical_columns()`
  s'appuient sur le profilage de `dashboard.py` et gèrent les formats français
  (`1 299,90 €`, espaces insécables, virgule décimale).
- **Robustesse** : les graphiques s'adaptent aux jeux de données vides, aux
  colonnes entièrement vides ou sans valeur numérique exploitable — la jauge de
  score reste toujours disponible.
- **Langue** : titres, axes, libellés et valeurs numériques des graphiques
  suivent la langue active (séparateur décimal localisé, formatage des nombres
  via `number_format`). Les URL d'images portent `?lang=<code>` afin que le
  cache navigateur ne serve pas une image dans une autre langue. Les libellés
  arabes sont façonnés et réordonnancés (`arabic-reshaper` + `python-bidi`) et
  une chaîne de polices de repli couvre les glyphes CJK, thaï et devanagari.

## 🧪 Tests

```powershell
python manage.py test core
```

Sur PostgreSQL, la suite crée une base `test_datazen` puis la détruit à la fin.
La destruction peut échouer avec `database "test_datazen" is being accessed by
other users` : un fil d'arrière-plan garde brièvement une session ouverte. Les
tests sont tous passés — seul le nettoyage râle. Pour l'éviter, conservez la
base de test entre deux exécutions (elle est aussi bien plus rapide) :

```powershell
python manage.py test core --keepdb
```

Si une base `test_datazen` reste orpheline, supprimez-la :

```powershell
docker exec datazen-postgres psql -U datazen -d postgres -c "DROP DATABASE IF EXISTS test_datazen;"
```

La suite couvre l'authentification, la réinitialisation du mot de passe,
l'isolation des données par propriétaire, les règles personnalisées, le
traitement asynchrone, le pipeline de nettoyage, le profil utilisateur
(accès, mise à jour, téléversement et suppression de la photo, avatar par défaut,
validations, informations professionnelles, préférences, complétion, changement
de mot de passe, export JSON, suppression de compte et profil public) et les
graphiques matplotlib/seaborn (signature PNG, disponibilité des 11 graphiques,
jeux de données vides ou sans colonne numérique, endpoint PNG, page d'analyse,
contrôle d'accès et embarquement des graphiques dans le rapport HTML), la
détection des anomalies structurelles (`StructuralAnomalyTests`) et le profilage
statistique restitué dans le rapport (`PipelineTests`).

Le pack « pro » est couvert par les classes `OverviewServiceTests`,
`DashboardTests`, `ComparisonTests`, `PdfReportTests`, `ProductivityPageTests`,
`GlobalSearchServiceTests`, `ApiAccessTests`, `ApiTokenManagementTests`,
`WebhookTests`, `RetentionTests` et `ActivityJournalTests` : agrégation
multi-fichiers, KPI globaux et frise chronologique, comparaison avant/après,
génération du PDF, recherche globale, journal d'activité, authentification par
jeton (401/404/200), gestion des jetons et des webhooks, politique de rétention
et traçabilité des actions.

`GlobalSearchServiceTests` verrouille la recherche globale : repliage des
accents, barème de pertinence (exact, préfixe, début de mot, sous-chaîne),
position du surlignage dans le texte d'origine, recherche d'un fichier par une
de ses colonnes, d'une règle par son opération ou sa colonne cible, d'une page
par un mot-clé anglais, d'une activité par son message, d'un jeton et d'un
webhook par leur nom ou leur URL, plafonnement par famille et au global, tri par
score décroissant, contrat de la palette et absence de fuite entre comptes.

Trois classes verrouillent l'internationalisation : `JsUiStringsTests` vérifie
que les libellés générés par JavaScript sont exposés sur `<body>` et traduits
dans les 23 langues, `ContextTranslationTests` vérifie que les chaînes
contextuelles (séparateur « ou » des pages d'authentification) sont bien
résolues par `pgettext`, dans les catalogues `.po` comme dans les `.mo`, et
`KeyNameTranslationTests` couvre les noms de touches des raccourcis.

Deux classes verrouillent les vidéos de fond décoratives : `HeroVideoTests`
(page d'accueil) et `LoginVideoTests` (page de connexion) vérifient que la vidéo
et son affiche existent, que le MP4 est un vrai conteneur ISO BMFF, que le
gabarit embarque les deux sources avec `muted`, `loop`, `playsinline` et
`aria-hidden`, et que la feuille de style prévoit l'overlay, le mode sombre et
le repli `prefers-reduced-motion`. `LoginVideoTests` s'assure en plus que les
autres pages d'authentification restent sobres et que la carte de connexion
adopte le verre dépoli (`backdrop-filter`) avec un repli opaque.

Deux classes verrouillent l'identité visuelle : `NavbarDesignTests` vérifie que
la barre de navigation reste collante (`position: sticky` non écrasée, garde
`overflow-x: clip`), que le verre teinté, le liseré dégradé et l'ombre colorée
au défilement sont bien déclarés, et que le soulignement dégradé épargne les
menus déroulants ; `LogoAssetTests` vérifie que les deux variantes du logo
existent en PNG transparent, que la barre et le pied de page les affichent, que
le thème sombre bascule sur la variante éclaircie et que l'effet de survol de la
marque est conservé. `FaviconTests` complète l'identité : `tools/make_favicon.py`
isole le glyphe gauche du logo et produit un `.ico` multi-tailles plus une icône
Apple Touch, déclarés dans le gabarit de base ; la route `/favicon.ico` renvoie
l'icône statique au lieu d'un 404, et reste publique malgré
`LoginRequiredMiddleware`.

`LocaleNumberRenderingTests` protège un piège de localisation : en français,
Django écrit `92,2` au lieu de `92.2`. Injecté tel quel dans
`style="width: …%"` ou dans `cx="…"`, le nombre est rejeté par le navigateur —
les barres de progression restent vides et le tracé du score disparaît. Les
gabarits appliquent donc `|unlocalize` sur toute valeur numérique destinée au
CSS ou au SVG, et le test balaie les pages concernées en français.

`DesignSystemTests` verrouille la refonte issue du modèle : échelle de rayons
généreuse (`--dz-radius-lg` à `1.5rem`, `--dz-radius-xl` à `2rem`, alignée sur
les jetons Bootstrap), ombres à deux couches (contact net + halo large), jetons
de rythme vertical (`--dz-section-gap`, `--dz-section-gap-sm`), héros plus haut
et titres plus grands, cartes et fonctionnalités plus aérées, variante
`.dz-panel-xl`, et surcharge des ombres en thème sombre. Il vérifie aussi que la
vitrine utilise `.dz-section` / `.dz-section-head` / `.dz-panel-xl`, que les
pages internes troquent `container py-4` contre `.dz-page` avec `.dz-page-head`
et `.dz-block`, et que le cache-buster de `style.css` a bien été incrémenté.

`KeyNameTranslationTests` couvre les noms de touches affichés dans les balises
`<kbd>` : « Entrée » et « Échap » apparaissaient en clair dans `shortcuts.html`
et dans l'aide de la palette Ctrl+K, invisibles pour l'extracteur et donc figés
en français. Ils passent par `{% translate %}` et par le catalogue
`tools/translations/key_names.py`, qui fournit le libellé de chaque touche dans
les 22 langues cibles ; le test balaie plusieurs langues sur la page des
raccourcis et vérifie que le catalogue reste complet.

`FrenchSourceTranslationTests` verrouille le cas inverse : le français est la
langue source de DataZen, donc son catalogue reste vide et `gettext` renvoie le
msgid tel quel. C'est correct tant que le msgid est écrit en français, mais le
contrôle de cohérence, le tableau de bord et les exports déclaraient leurs
messages directement en anglais — ils s'affichaient donc en anglais dans une
interface française. `tools/translations/french_source.py` ne contient que ces
msgids à source anglaise ; le test vérifie que le bloc « Contrôle de
cohérence » suit la langue active, que les explications du score et les types
de correction aussi, et qu'aucune entrée du catalogue n'est identique à son
msgid (une telle entrée serait inutile).

Le même fichier de tests verrouille les **formes plurielles**. Les catalogues
ne déclaraient souvent que le singulier d'un msgid pluriel ; `tools/i18n_build.py`
n'écrivait alors que `msgstr[0]` dans le `.mo`, et `gettext` retombait sur le
msgid — donc sur le français — dès que la langue demandait une autre forme
(« 10 valides » restait français en anglais). `plural_count()` et
`plural_value()` complètent désormais chaque entrée jusqu'au nombre de formes
déclaré par la langue (réplication de la dernière forme, troncature si le
catalogue en fournit trop). Le test balaie les 23 langues sur plusieurs valeurs
de `n` et vérifie qu'aucune ne retombe sur le français.

La suite compte 300 tests ; l'exécution complète dure environ 10 minutes.

## 🎨 Charte graphique

Le design est centralisé dans `static/css/style.css`, organisé en 18 sections
numérotées. Toute la palette, les ombres et les rayons sont exposés en variables
CSS (`--dz-*`) : changer la couleur de marque se fait en modifiant
`--dz-brand-500` et `--dz-gradient`.

| Élément | Classe | Rôle |
| --- | --- | --- |
| Barre de navigation | `.dz-navbar` | Verre teinté (reflet de marque + liseré dégradé), ombre colorée au défilement |
| Logo | `.dz-logo-img` | Image de marque détourée, variante éclaircie en thème sombre |
| Héros | `.dz-hero` | Titre principal avec halo lumineux |
| Vidéo du héros | `.dz-hero-video` | Animation de fond décorative (MP4 / WebM) |
| Vidéo d'authentification | `.dz-auth-video` | Tableau de bord animé en fond de la page de connexion |
| Enveloppe d'auth | `.dz-auth-shell` | Cadre plein écran qui porte la vidéo et centre la carte |
| Carte de connexion | `.dz-auth-shell .dz-auth-card` | Verre dépoli (`backdrop-filter`) posé sur la vidéo |
| Statistique | `.dz-stat` | Compteur du bandeau d'accueil |
| Fonctionnalité | `.dz-feature` | Carte avec icône dégradée |
| Panneau | `.dz-panel` | Surface de travail neutre |
| Panneau large | `.dz-panel-xl` | Variante à très grand rayon pour les blocs de premier plan |
| Section | `.dz-section` | Bloc de vitrine portant le rythme vertical du modèle |
| En-tête de section | `.dz-section-head` | Titre + sous-titre centrés, avec respiration propre |
| Page interne | `.dz-page` | Enveloppe applicative (remplace `container py-4`) |
| En-tête de page | `.dz-page-head` | Titre + actions d'une page interne |
| Bloc de contenu | `.dz-block` | Espacement vertical d'un bloc applicatif |
| Grille | `.dz-grid` | Gouttières alignées sur le rythme des sections |
| Carte accentuée | `.dz-card-accent` | Liseré dégradé en haut |
| Zone de dépôt | `.dz-dropzone` | Cible de téléversement |
| Carte d'auth | `.dz-auth-card` | Connexion / inscription / reset |
| Avatar | `.dz-avatar` | Pastille ronde (photo ou avatar par défaut) |
| Aperçu d'avatar | `.dz-avatar-preview` | Grand aperçu cliquable sur la page de profil |
| Sélecteur d'avatar | `.dz-avatar-picker` | Avatar + bouton appareil photo superposé |
| Bouton appareil photo | `.dz-avatar-camera` | Ouvre la capture webcam |
| Scène webcam | `.dz-camera-stage` | Aperçu vidéo dans la fenêtre modale |

Les animations d'apparition s'activent avec l'attribut `data-dz-reveal`
(et `data-dz-delay="1..4"` pour la cascade).

## 📱 Adaptabilité (responsive)

L'application est **mobile-first** : la section 17 de `style.css` regroupe toutes
les adaptations. Les points de rupture suivent la grille Bootstrap 5.3, donc les
classes `col-*` et les règles personnalisées basculent aux mêmes largeurs.

| Largeur | Cible | Adaptations principales |
| --- | --- | --- |
| ≤ 1199 px | Petits portables | Grilles resserrées |
| ≤ 991,98 px | Tablettes | Menu de navigation replié en panneau plein écran, tableaux défilants |
| ≤ 767,98 px | Téléphones | Héros compact, boutons pleine largeur, champs à 16 px (anti-zoom iOS), cartes de stats sur 2 colonnes |
| ≤ 575,98 px | Petits téléphones | Barres d'action empilées, typographie réduite |
| ≤ 399,98 px | Très petits écrans | Marges et titres minimaux |

Points clés :

- **Aucun débordement horizontal** de 320 px à 1440 px (`overflow-x: hidden` +
  `overflow-wrap: anywhere` sur les tableaux, cartes et fils d'Ariane).
- **Champs de formulaire à 16 px** sous 768 px : évite le zoom automatique de
  Safari sur les champs de saisie.
- **Cibles tactiles de 44 px** minimum sur les écrans sans survol
  (`@media (hover: none)`), avec neutralisation des effets de survol.
- **Menu mobile** : le panneau se ferme automatiquement au clic sur un lien et au
  retour en mode bureau (`static/js/main.js`).
- **Tableaux larges** : défilement horizontal tactile dans `.table-responsive`
  plutôt que compression des colonnes.
- **Impression** : navigation, pied de page et boutons masqués, ombres aplaties.

Les hauteurs de barres de progression et les largeurs minimales de filtres sont
gérées par des classes utilitaires (`.dz-progress-*`, `.dz-filter-*`) et non par
des styles en ligne, afin qu'elles puissent s'adapter.

## ✉️ Envoi d'e-mails

Le projet utilise le *console backend* en développement : les messages
(réinitialisation de mot de passe) sont affichés **dans le terminal** où tourne
`runserver`, avec le lien cliquable. Aucun serveur SMTP n'est requis.

En production, la réinitialisation de mot de passe n'a de sens que si les
messages partent réellement. Il suffit de définir `DJANGO_EMAIL_HOST` : le
réglage bascule alors automatiquement sur un envoi SMTP.

```bash
DJANGO_EMAIL_HOST=smtp.example.com
DJANGO_EMAIL_PORT=587
DJANGO_EMAIL_USER=no-reply@example.com
DJANGO_EMAIL_PASSWORD=...
DJANGO_DEFAULT_FROM_EMAIL="DataZen <no-reply@example.com>"
```

Le port 587 active STARTTLS, le port 465 active SSL implicite. Les deux
comportements restent surchargeables avec `DJANGO_EMAIL_TLS` et
`DJANGO_EMAIL_SSL`.

## 🚀 Mise en production

`runserver` est un serveur de développement : mono-processus, sans service des
fichiers statiques dès que `DEBUG=False`. Le projet est livré avec
**waitress** (serveur WSGI compatible Windows) et **WhiteNoise** (service des
fichiers statiques depuis le processus applicatif).

### 1. Variables d'environnement

Copiez `.env.example` et renseignez au minimum :

| Variable | Rôle |
| --- | --- |
| `DJANGO_DEBUG` | `0` en production (obligatoire) |
| `DJANGO_SECRET_KEY` | Clé secrète longue et aléatoire (obligatoire) |
| `DJANGO_ALLOWED_HOSTS` | Hôtes autorisés, séparés par des virgules |
| `DJANGO_HTTPS` | `1` si le site est servi en HTTPS |
| `DJANGO_EMAIL_HOST` | Serveur SMTP pour les e-mails réels |
| `DJANGO_DB_PASSWORD` | Mot de passe PostgreSQL (obligatoire) |

Sans `DJANGO_SECRET_KEY` et avec `DJANGO_DEBUG=0`, l'application refuse de
démarrer : c'est volontaire, une clé de développement ne doit jamais servir en
production.

Générer une clé :

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

### 2. Base de données

L'application utilise **PostgreSQL par défaut** (`psycopg` 3). SQLite verrouille
la base en écriture et ne supporte pas plusieurs workers WSGI simultanés ; il
n'est conservé que comme repli pour un poste isolé.

| Variable | Défaut | Rôle |
| --- | --- | --- |
| `DJANGO_DB_ENGINE` | `postgresql` | `sqlite` bascule sur `db.sqlite3` |
| `DJANGO_DB_NAME` | `datazen` | Nom de la base |
| `DJANGO_DB_USER` | `datazen` | Utilisateur |
| `DJANGO_DB_PASSWORD` | — | Mot de passe |
| `DJANGO_DB_HOST` | `127.0.0.1` | Hôte |
| `DJANGO_DB_PORT` | `5432` | Port |
| `DJANGO_DB_SSLMODE` | `prefer` | `require` chez les hébergeurs gérés |
| `DJANGO_DB_CONN_MAX_AGE` | `60` | Connexions persistantes, en secondes |

Créer la base et l'utilisateur :

```sql
CREATE ROLE datazen LOGIN PASSWORD '...';
CREATE DATABASE datazen OWNER datazen;
```

Pour un PostgreSQL local immédiat, Docker fournit l'équivalent :

```bash
docker run -d --name datazen-postgres --restart unless-stopped \
  -e POSTGRES_DB=datazen -e POSTGRES_USER=datazen -e POSTGRES_PASSWORD=... \
  -p 127.0.0.1:5432:5432 -v datazen_pgdata:/var/lib/postgresql/data \
  postgres:16-alpine
```

`DJANGO_DB_CONN_MAX_AGE` doit rester **inférieur** au délai d'inactivité du
serveur (sinon une connexion recyclée peut être coupée côté serveur). Pour
repartir d'une base propre : `python manage.py migrate`.

### 3. Préparation

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py check --deploy
```

`check --deploy` doit répondre **« no issues »**. Les avertissements de sécurité
(HSTS, cookies `Secure`, redirection SSL) sont tous pilotés par `DJANGO_HTTPS`
et `DJANGO_DEBUG`.

> ⚠️ **`collectstatic` est obligatoire avant chaque démarrage.** En production,
> l'application utilise `CompressedManifestStaticFilesStorage`, qui lit
> `staticfiles/staticfiles.json` pour résoudre chaque URL statique. Sans ce
> fichier, toute page lève `ValueError: Missing staticfiles manifest entry`.
> Relancez donc `collectstatic` après **chaque** modification de CSS, JS ou
> image. Les pages d'erreur (404/403/500) ne dépendent pas du manifeste : elles
> s'affichent même si l'étape a été oubliée.

### 4. Lancement

```bash
waitress-serve --listen=0.0.0.0:8000 --threads=8 datazen.wsgi:application
```

Sous Linux, `gunicorn --workers 3 --bind 0.0.0.0:8000 datazen.wsgi:application`
fonctionne également.

### 5. Reverse proxy

Placez nginx (ou IIS) devant waitress pour terminer le TLS. Deux points
d'attention :

- transmettre `X-Forwarded-Proto` et définir `SECURE_PROXY_SSL_HEADER` (déjà
  configuré) pour que Django sache que la requête est en HTTPS ;
- ne pas laisser nginx servir `/static/` : WhiteNoise s'en charge, ce qui évite
  d'oublier un `collectstatic` après un déploiement.

Après un déploiement, vérifiez le démarrage avec :

```bash
python manage.py check --deploy          # doit afficher « no issues »
python -c "import urllib.request as u; print(u.urlopen('https://votre-domaine/').status)"
```

Le test décisif est la première visite : si vous voyez
`Missing staticfiles manifest entry`, c'est que `collectstatic` n'a pas été
relancé sur le serveur.

### 6. Limites connues

- **Cache local** : la limitation des tentatives de connexion s'appuie sur
  `LocMemCache`, propre à chaque processus. Avec plusieurs workers, configurez
  Redis ou Memcached pour que le blocage soit partagé.
- **Fichiers médias** : `media/` est servi par Django uniquement en
  développement. En production, laissez le reverse proxy servir `/media/`, ou
  stockez les fichiers sur un service objet.

## 📝 Licence

Projet en cours de développement — usage interne.
