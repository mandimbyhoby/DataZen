"""
Configuration Django du projet DataZen.

DataZen est une application de nettoyage de données (DataClean Pro).
"""
import os
from pathlib import Path

# Chemins de base du projet
BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(name, default=False):
    """Lit un booléen d'environnement (``1``/``true``/``oui``/``yes``)."""
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "oui", "yes", "on"}


def _load_secret_key():
    """Clé de signature, lue dans l'environnement ou générée hors production.

    En production (``DJANGO_DEBUG`` désactivé), l'absence de
    ``DJANGO_SECRET_KEY`` interrompt le démarrage : une clé publique permettrait
    de forger des sessions et des jetons de réinitialisation de mot de passe.
    """
    key = os.environ.get("DJANGO_SECRET_KEY", "").strip()
    if key:
        return key
    if not DEBUG:
        raise RuntimeError(
            "DJANGO_SECRET_KEY est obligatoire lorsque DEBUG est désactivé. "
            "Définissez-la dans l'environnement avant de démarrer le serveur."
        )
    # Développement : clé éphémère, régénérée à chaque démarrage.
    return "django-insecure-dev-" + __import__("secrets").token_hex(32)


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
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
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

# Fichiers médias (fichiers téléversés par les utilisateurs)
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Authentification : redirections par défaut
LOGIN_URL = "core:login"
LOGIN_REDIRECT_URL = "core:index"
LOGOUT_REDIRECT_URL = "core:index"

# Taille maximale de téléversement (20 Mo)
DATA_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024

# E-mail : en développement, les messages sont affichés dans la console du
# serveur. Pour un envoi réel, remplacer par un backend SMTP et renseigner
# EMAIL_HOST / EMAIL_PORT / EMAIL_HOST_USER / EMAIL_HOST_PASSWORD.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = "DataZen <no-reply@datazen.local>"

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
