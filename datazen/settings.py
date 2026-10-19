"""
Configuration Django du projet DataZen.

DataZen est une application de nettoyage de données (DataClean Pro).
"""
import os
import secrets
from pathlib import Path

# Chemins de base du projet
BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path):
    """Charge un fichier ``.env`` dans l'environnement, sans écraser l'existant.

    Les variables déjà présentes dans l'environnement du processus gagnent :
    un déploiement qui exporte ses secrets (systemd, Docker, CI) n'est jamais
    écrasé par un fichier laissé sur le disque. Le format accepté est celui de
    ``.env.example`` : ``CLE=valeur``, commentaires sur une ligne commençant
    par ``#``, guillemets simples ou doubles facultatifs autour de la valeur.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if name and name not in os.environ:
            os.environ[name] = value


# Chargé avant toute lecture de variable : `DJANGO_DEBUG`, la clé secrète et
# les identifiants de base de données proviennent de ce fichier en local.
_load_dotenv(BASE_DIR / ".env")


def _env_bool(name, default=False):
    """Lit un booléen d'environnement (``1``/``true``/``oui``/``yes``)."""
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "oui", "yes", "on"}


def _load_secret_key():
    """Clé de signature, lue dans l'environnement ou persistée en local.

    En production (``DJANGO_DEBUG`` désactivé), l'absence de
    ``DJANGO_SECRET_KEY`` interrompt le démarrage : une clé publique permettrait
    de forger des sessions et des jetons de réinitialisation de mot de passe.

    En développement, la clé est lue depuis ``var/dev_secret_key`` puis générée
    au premier démarrage. Elle doit rester stable : une clé régénérée à chaque
    redémarrage rend indéchiffrables toutes les sessions existantes, ce qui se
    manifeste par des messages « Session data corrupted » et des préférences
    (langue de l'interface, options de nettoyage) silencieusement perdues.
    """
    key = os.environ.get("DJANGO_SECRET_KEY", "").strip()
    if key:
        return key
    if not DEBUG:
        raise RuntimeError(
            "DJANGO_SECRET_KEY est obligatoire lorsque DEBUG est désactivé. "
            "Définissez-la dans l'environnement avant de démarrer le serveur."
        )
    # Développement : clé persistée localement, jamais versionnée.
    key_file = BASE_DIR / "var" / "dev_secret_key"
    try:
        key = key_file.read_text(encoding="utf-8").strip()
    except OSError:
        key = ""
    if not key:
        key = "django-insecure-dev-" + secrets.token_hex(32)
        key_file.parent.mkdir(parents=True, exist_ok=True)
        key_file.write_text(key, encoding="utf-8")
    return key


# Sécurité — la production doit définir DJANGO_DEBUG=0 et DJANGO_SECRET_KEY.
DEBUG = _env_bool("DJANGO_DEBUG", True)
SECRET_KEY = _load_secret_key()

# En développement, tout hôte local est accepté ; en production, la liste
# blanche est obligatoire pour éviter l'empoisonnement du cache et des liens
# de réinitialisation via l'en-tête Host.
_hosts = os.environ.get("DJANGO_ALLOWED_HOSTS", "").strip()
if _hosts:
    ALLOWED_HOSTS = [host.strip() for host in _hosts.split(",") if host.strip()]
else:
    ALLOWED_HOSTS = (
        ["*"] if DEBUG else ["localhost", "127.0.0.1", "[::1]"]
    )

# Applications installées
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Filtres de présentation (intcomma, naturaltime) pour les pages pro.
    "django.contrib.humanize",
    # Applications locales
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Doit rester juste après SecurityMiddleware : sert /static/ directement
    # depuis le processus WSGI, sans quoi les fichiers statiques renvoient 404
    # dès que DEBUG=False.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Toute l'application exige un compte connecté : seules les vues marquées
    # `login_not_required` (connexion, inscription, réinitialisation du mot de
    # passe, changement de langue) restent accessibles aux visiteurs anonymes.
    "django.contrib.auth.middleware.LoginRequiredMiddleware",
    # Doit rester après SessionMiddleware et AuthenticationMiddleware
    "core.middleware.LanguageMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "datazen.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.site_languages",
            ],
        },
    },
]

WSGI_APPLICATION = "datazen.wsgi.application"

# Base de données
#
# PostgreSQL est le moteur par défaut : SQLite verrouille la base en écriture
# et ne supporte donc pas plusieurs workers WSGI simultanés. Le moteur SQLite
# reste accessible avec `DJANGO_DB_ENGINE=sqlite` pour un démarrage sans
# dépendance externe (tests hors ligne, poste isolé).
_db_engine = os.environ.get("DJANGO_DB_ENGINE", "postgresql").strip().lower()

if _db_engine in {"sqlite", "sqlite3"}:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    # Connexions persistantes : évite de rouvrir une session TCP à chaque
    # requête. Doit rester inférieur au délai d'expiration des connexions
    # inactives du serveur PostgreSQL.
    _db_conn_max_age = int(os.environ.get("DJANGO_DB_CONN_MAX_AGE", "60"))

    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("DJANGO_DB_NAME", "datazen"),
            "USER": os.environ.get("DJANGO_DB_USER", "datazen"),
            "PASSWORD": os.environ.get("DJANGO_DB_PASSWORD", ""),
            "HOST": os.environ.get("DJANGO_DB_HOST", "127.0.0.1"),
            "PORT": os.environ.get("DJANGO_DB_PORT", "5432"),
            "CONN_MAX_AGE": _db_conn_max_age,
            # `prefer` chiffre la connexion si le serveur le propose ; les
            # hébergeurs gérés exigent `require`.
            "OPTIONS": {
                "sslmode": os.environ.get("DJANGO_DB_SSLMODE", "prefer"),
            },
            # Sans ce contrôle, une connexion persistante refermée par le
            # serveur (expiration d'inactivité, `pgbouncer`, redémarrage) est
            # réutilisée telle quelle et la requête échoue avec
            # « the connection is closed ». Le contrôle la remplace par une
            # connexion neuve. Inutile sans persistance, d'où la condition.
            "CONN_HEALTH_CHECKS": _db_conn_max_age > 0,
        }
    }

# Validation des mots de passe
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalisation
LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Europe/Paris"
USE_I18N = True
USE_TZ = True

# Dossier des catalogues de traduction (locale/<code>/LC_MESSAGES/django.po)
LOCALE_PATHS = [BASE_DIR / "locale"]

# Langues proposées dans le sélecteur.
# Langue principale en premier : sert de repli et de référence pour les .po.
SITE_LANGUAGES = [
    {"code": "fr", "name": "Français", "english": "French", "flag": "🇫🇷", "dir": "ltr"},
    {"code": "en", "name": "English", "english": "English", "flag": "🇬🇧", "dir": "ltr"},
    {"code": "es", "name": "Español", "english": "Spanish", "flag": "🇪🇸", "dir": "ltr"},
    {"code": "de", "name": "Deutsch", "english": "German", "flag": "🇩🇪", "dir": "ltr"},
    {"code": "it", "name": "Italiano", "english": "Italian", "flag": "🇮🇹", "dir": "ltr"},
    {"code": "pt", "name": "Português", "english": "Portuguese", "flag": "🇵🇹", "dir": "ltr"},
    {"code": "nl", "name": "Nederlands", "english": "Dutch", "flag": "🇳🇱", "dir": "ltr"},
    {"code": "ar", "name": "العربية", "english": "Arabic", "flag": "🇸🇦", "dir": "rtl"},
    {"code": "zh-hans", "name": "简体中文", "english": "Chinese (Simplified)", "flag": "🇨🇳", "dir": "ltr"},
    {"code": "ru", "name": "Русский", "english": "Russian", "flag": "🇷🇺", "dir": "ltr"},
    {"code": "ja", "name": "日本語", "english": "Japanese", "flag": "🇯🇵", "dir": "ltr"},
    {"code": "ko", "name": "한국어", "english": "Korean", "flag": "🇰🇷", "dir": "ltr"},
    {"code": "tr", "name": "Türkçe", "english": "Turkish", "flag": "🇹🇷", "dir": "ltr"},
    {"code": "hi", "name": "हिन्दी", "english": "Hindi", "flag": "🇮🇳", "dir": "ltr"},
    {"code": "pl", "name": "Polski", "english": "Polish", "flag": "🇵🇱", "dir": "ltr"},
    {"code": "sv", "name": "Svenska", "english": "Swedish", "flag": "🇸🇪", "dir": "ltr"},
    {"code": "da", "name": "Dansk", "english": "Danish", "flag": "🇩🇰", "dir": "ltr"},
    {"code": "fi", "name": "Suomi", "english": "Finnish", "flag": "🇫🇮", "dir": "ltr"},
    {"code": "cs", "name": "Čeština", "english": "Czech", "flag": "🇨🇿", "dir": "ltr"},
    {"code": "ro", "name": "Română", "english": "Romanian", "flag": "🇷🇴", "dir": "ltr"},
    {"code": "vi", "name": "Tiếng Việt", "english": "Vietnamese", "flag": "🇻🇳", "dir": "ltr"},
    {"code": "th", "name": "ไทย", "english": "Thai", "flag": "🇹🇭", "dir": "ltr"},
    {"code": "id", "name": "Bahasa Indonesia", "english": "Indonesian", "flag": "🇮🇩", "dir": "ltr"},
]

# Consommé par LocaleMiddleware pour savoir quelles langues accepter.
LANGUAGES = [(lang["code"], lang["name"]) for lang in SITE_LANGUAGES]

# Langues écrites de droite à gauche
RTL_LANGUAGES = [lang["code"] for lang in SITE_LANGUAGES if lang["dir"] == "rtl"]

# Fichiers statiques (CSS, JavaScript, images)
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# WhiteNoise sert /static/ en production. Le stockage « manifest » ajoute une
# empreinte au nom de chaque fichier et permet un cache navigateur d'un an ;
# il exige d'avoir lancé `collectstatic` au préalable. En développement, le
# stockage simple évite d'imposer cette étape à chaque modification de CSS.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}

# Fichiers médias (fichiers téléversés par les utilisateurs)
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Authentification : redirections par défaut
LOGIN_URL = "core:login"
LOGIN_REDIRECT_URL = "core:index"
LOGOUT_REDIRECT_URL = "core:index"

# Anti-force brute sur la connexion (voir core/throttling.py).
# Le compteur utilise le cache : LocMemCache convient à un déploiement
# mono-processus ; au-delà, configurer un cache partagé (Redis/Memcached).
LOGIN_THROTTLE_MAX_PER_USER = int(os.environ.get("DJANGO_LOGIN_MAX_PER_USER", "5"))
LOGIN_THROTTLE_MAX_PER_IP = int(os.environ.get("DJANGO_LOGIN_MAX_PER_IP", "20"))
LOGIN_THROTTLE_WINDOW = int(os.environ.get("DJANGO_LOGIN_WINDOW", "900"))

# Taille maximale de téléversement (20 Mo)
DATA_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024

# E-mail : sans configuration, les messages sont affichés dans la console du
# serveur — pratique en développement, mais la réinitialisation de mot de passe
# reste alors sans effet pour un utilisateur réel. Renseigner DJANGO_EMAIL_HOST
# bascule automatiquement sur un envoi SMTP.
EMAIL_HOST = os.environ.get("DJANGO_EMAIL_HOST", "").strip()
if EMAIL_HOST:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_PORT = int(os.environ.get("DJANGO_EMAIL_PORT", "587"))
    EMAIL_HOST_USER = os.environ.get("DJANGO_EMAIL_USER", "").strip()
    EMAIL_HOST_PASSWORD = os.environ.get("DJANGO_EMAIL_PASSWORD", "")
    # 587 (STARTTLS) et 25 utilisent TLS ; 465 utilise SSL implicite.
    EMAIL_USE_TLS = _env_bool("DJANGO_EMAIL_TLS", EMAIL_PORT != 465)
    EMAIL_USE_SSL = _env_bool("DJANGO_EMAIL_SSL", EMAIL_PORT == 465)
    EMAIL_TIMEOUT = int(os.environ.get("DJANGO_EMAIL_TIMEOUT", "15"))
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

DEFAULT_FROM_EMAIL = os.environ.get(
    "DJANGO_DEFAULT_FROM_EMAIL", "DataZen <no-reply@datazen.local>"
)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Durcissement du transport (constat d'audit) : les cookies de session et de
# jeton CSRF ne doivent jamais transiter en clair. Les redirections HTTPS et
# HSTS ne sont activées qu'hors développement, sinon `runserver` en HTTP local
# bouclerait. `DJANGO_HTTPS=1` force leur activation derrière un proxy TLS.
HTTPS_ENFORCED = _env_bool("DJANGO_HTTPS", not DEBUG)

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

SESSION_COOKIE_SECURE = HTTPS_ENFORCED
CSRF_COOKIE_SECURE = HTTPS_ENFORCED
SECURE_SSL_REDIRECT = HTTPS_ENFORCED
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

if HTTPS_ENFORCED:
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
