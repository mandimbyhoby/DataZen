# Revue de sécurité — DataZen

Audit statique du dépôt réalisé sur la totalité du code applicatif (vues, modèles,
formulaires, services, gabarits, réglages), avec priorité au code exposé à
l'utilisateur et aux intégrations sortantes.

Six vulnérabilités ont été retenues : **une critique, une élevée, trois moyennes
et une faible**. Toutes ont été corrigées et vérifiées par des tests.

## Tableau récapitulatif

| # | Gravité | Fichier | Lignes | Vulnérabilité | Confiance |
|---|---------|---------|--------|---------------|-----------|
| 1 | 🔴 CRITIQUE | `datazen/settings.py` | 12-14 | `SECRET_KEY` en clair, `DEBUG=True` et `ALLOWED_HOSTS=["*"]` en toutes circonstances | 9/10 |
| 2 | 🟠 ÉLEVÉE | `core/services/api.py` | 154-170 | SSRF : webhooks dirigeables vers la boucle locale, `169.254.169.254` et les plages RFC1918 | 9/10 |
| 3 | 🟡 MOYENNE | `core/services/async_runner.py` | 101 | Trace d'exécution Python complète persistée puis renvoyée à l'utilisateur | 9/10 |
| 4 | 🟡 MOYENNE | `datazen/settings.py` | — | Aucun durcissement du transport (redirection HTTPS, HSTS, cookies `Secure`, `nosniff`) | 9/10 |
| 5 | 🟡 MOYENNE | `core/views_pro.py` | 223-228 | Jeton d'API accepté via `?token=` : fuite dans les journaux, l'historique et `Referer` | 8/10 |
| 6 | ⚪ FAIBLE | `core/services/api.py` | 50-53 | Empreinte SHA-256 non keyée avec sel statique au lieu d'un HMAC | 8/10 |

## Détail des corrections

### 1. Réglages sensibles figés dans le code (CRITIQUE)

**Risque.** Une `SECRET_KEY` versionnée permet de forger des sessions et des
jetons de réinitialisation. `DEBUG=True` en production expose les traces
complètes et sert `/media/` sans contrôle d'accès.

**Correction.** `datazen/settings.py` lit désormais `DJANGO_DEBUG`,
`DJANGO_SECRET_KEY` et `DJANGO_ALLOWED_HOSTS`.

- En développement, une clé éphémère est tirée au démarrage
  (`django-insecure-dev-` + 32 octets aléatoires) : rien de secret n'est écrit
  sur le disque.
- En production (`DJANGO_DEBUG=0`), l'absence de `DJANGO_SECRET_KEY` provoque une
  `RuntimeError` immédiate : le serveur refuse de démarrer plutôt que de tourner
  avec une clé prévisible.
- `ALLOWED_HOSTS` vaut la valeur fournie, sinon `["*"]` en développement et une
  liste restreinte (`localhost`, `127.0.0.1`, `[::1]`) en production.

Comme `/media/` n'est monté que sous `DEBUG`, les fichiers téléversés ne sont
plus exposés en production.

### 2. Requêtes sortantes forgées — SSRF (ÉLEVÉE)

**Risque.** L'URL d'un webhook était appelée telle quelle. Un utilisateur pouvait
viser `http://127.0.0.1:…`, `http://169.254.169.254/latest/meta-data/` (métadonnées
d'instance cloud) ou toute adresse RFC1918, puis lire le code de retour HTTP comme
oracle.

**Correction.** `core/services/api.py` introduit `validate_webhook_url(url, resolve)` :

- schémas `http`/`https` uniquement (pas de `file:`, `gopher:`, `ftp:`) ;
- refus des identifiants intégrés (`https://user:pass@…`) et des ports invalides ;
- refus de `localhost` et de toute IP littérale interne (boucle locale,
  link-local, privée, multicast, réservée, non spécifiée) via `ipaddress` ;
- avec `resolve=True`, résolution DNS puis contrôle de **chaque** adresse obtenue.

`_post()` valide une seconde fois avec `resolve=True` juste avant l'appel, ce qui
neutralise le rebinding DNS, et un `_NoRedirectHandler` refuse toute redirection.
`Webhook.clean()`, `Webhook.save()` et `WebhookForm.clean_url()` valident l'URL
dès la saisie (`resolve=False`, pour ne pas rejeter un hôte légitime non résoluble
depuis le serveur).

### 3. Trace d'exécution renvoyée à l'utilisateur (MOYENNE)

**Risque.** `async_runner.py` persistait `traceback.format_exc()` et l'affichait :
chemins absolus, versions de bibliothèques et structure interne du projet.

**Correction.** Le module `core/errors.py` centralise la présentation des erreurs.
`user_error(exc, context)` journalise l'exception complète côté serveur
(`logger.exception`) et ne renvoie qu'une ligne, débarrassée des chemins absolus
et tronquée à 180 caractères. `async_runner` enregistre un message court assorti
d'une référence (`uuid4` sur 8 caractères) qui permet de retrouver la trace dans
les journaux. Les six messages d'erreur de `core/views.py` et celui du PDF dans
`core/views_pro.py` passent par ce même entonnoir.

### 4. Transport non durci (MOYENNE)

**Correction.** Bloc de durcissement dans `datazen/settings.py` :
`SESSION_COOKIE_HTTPONLY`, `SameSite=Lax` sur les cookies de session et CSRF,
`SECURE_CONTENT_TYPE_NOSNIFF`, `SECURE_REFERRER_POLICY="same-origin"`,
`X_FRAME_OPTIONS="DENY"`. Quand `DJANGO_HTTPS` est actif : `SESSION_COOKIE_SECURE`,
`CSRF_COOKIE_SECURE`, `SECURE_SSL_REDIRECT`, `SECURE_PROXY_SSL_HEADER` et HSTS un an
avec `includeSubDomains` et `preload`. Le drapeau suit `DEBUG` par défaut et reste
donc inactif en développement local.

### 5. Jeton d'API en paramètre d'URL (MOYENNE)

**Risque.** `?token=…` fait fuiter un secret durable dans les journaux d'accès, les
proxys, l'historique du navigateur et l'en-tête `Referer`.

**Correction.** `_bearer_token()` ne lit plus que l'en-tête
`Authorization: Bearer …` et renvoie `None` sinon, ce qui produit un `401` avec
`WWW-Authenticate: Bearer`. Le test correspondant a été inversé pour verrouiller
ce comportement.

### 6. Empreinte de jeton non keyée (FAIBLE)

**Risque.** `sha256("datazen:" + jeton)` repose sur un sel public et statique :
une table de correspondance précalculée reste réutilisable d'une installation à
l'autre.

**Correction.** `hash_token()` calcule un HMAC-SHA256 dont la clé dérive de
`SECRET_KEY`. `legacy_token_hash()` conserve l'ancienne empreinte pour la
compatibilité : `resolve_token()` essaie le nouveau condensé, puis l'ancien, et
réécrit la ligne au format actuel dès qu'un jeton hérité est reconnu. Aucun jeton
existant n'est invalidé.

## Catégories vérifiées et jugées saines

Injection SQL/ORM, injection de commandes, désérialisation non sûre, protection
CSRF, contrôle d'accès et IDOR, redirection ouverte, traversée de répertoire,
injection de gabarit. Le rendu `|safe` du rapport HTML est légitime : il est
précédé d'un `html.escape()` dans `core/services/markdown.py`.

## Vérification

- `core/tests.py::SecurityHardeningTests` couvre les six corrections : refus des
  URL internes et malformées, acceptation des URL publiques, contrôle DNS, refus
  du formulaire et de la vue webhooks, nettoyage des messages d'erreur, HMAC
  distinct de l'ancienne empreinte, résolution puis migration d'un jeton hérité,
  rejet du jeton en paramètre d'URL.
- Suites ciblées `SecurityHardeningTests`, `WebhookTests`, `ApiAccessTests` et
  `ApiTokenManagementTests` : 38 tests, OK.
- Suite complète : lancée après l'ensemble des correctifs.

## Note sur les réglages de production

Le durcissement s'active par variables d'environnement :

```text
DJANGO_DEBUG=0
DJANGO_SECRET_KEY=<chaîne aléatoire longue et secrète>
DJANGO_ALLOWED_HOSTS=datazen.exemple.com
DJANGO_HTTPS=1
```

Sans `DJANGO_SECRET_KEY` alors que `DJANGO_DEBUG=0`, l'application refuse de
démarrer : c'est intentionnel.
