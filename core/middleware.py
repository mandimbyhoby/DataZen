"""Middleware de langue propre à DataZen.

Remplace ``LocaleMiddleware`` : la langue n'est pas déduite de l'en-tête
``Accept-Language`` mais d'un choix explicite de l'utilisateur. Sans cela, un
visiteur dont le navigateur est en anglais verrait le sélecteur afficher « EN »
alors qu'il n'a jamais rien choisi.

Ordre de priorité :

1. la session (choix effectué dans le sélecteur pendant cette visite) ;
2. le cookie (choix mémorisé au-delà de la session) ;
3. la langue du profil (choix fait sur un autre appareil) ;
4. ``LANGUAGE_CODE`` (langue par défaut de l'application, le français).

Ce middleware doit être placé après ``SessionMiddleware`` et
``AuthenticationMiddleware`` (il lit ``request.user``).
"""
from django.conf import settings
from django.utils import translation


class LanguageMiddleware:
    """Active la langue choisie pour chaque requête."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        language = self._resolve(request)
        previous = translation.get_language()
        translation.activate(language)
        request.LANGUAGE_CODE = language
        try:
            response = self.get_response(request)
        finally:
            # Ne pas laisser la langue de la requête déteindre sur la suite du
            # processus (tests, tâches de fond, traitements différés).
            translation.activate(previous)

        # Répercute le choix sur le cookie afin qu'il survive à la session.
        if request.session.get("django_language"):
            response.set_cookie(
                settings.LANGUAGE_COOKIE_NAME,
                language,
                max_age=settings.LANGUAGE_COOKIE_AGE,
                path=settings.LANGUAGE_COOKIE_PATH,
                domain=settings.LANGUAGE_COOKIE_DOMAIN,
                secure=settings.LANGUAGE_COOKIE_SECURE,
                httponly=settings.LANGUAGE_COOKIE_HTTPONLY,
                samesite=settings.LANGUAGE_COOKIE_SAMESITE,
            )
        return response

    @staticmethod
    def _resolve(request):
        """Retourne le code de langue à activer."""
        allowed = {lang["code"].lower() for lang in settings.SITE_LANGUAGES}
        candidate = request.session.get("django_language") or request.COOKIES.get(
            settings.LANGUAGE_COOKIE_NAME
        )

        if not candidate:
            user = getattr(request, "user", None)
            if user is not None and user.is_authenticated:
                profile = getattr(user, "profile", None)
                if profile is not None:
                    candidate = profile.language

        if candidate:
            candidate = str(candidate).lower().replace("_", "-")
            if candidate in allowed:
                return candidate

        return settings.LANGUAGE_CODE
