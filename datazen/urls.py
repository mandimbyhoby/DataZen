"""Routage URL principal du projet DataZen."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth.decorators import login_not_required
from django.templatetags.static import static as static_url
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("admin/", admin.site.urls),
    # Les navigateurs demandent /favicon.ico même quand un <link rel="icon">
    # est déclaré : on renvoie l'icône statique au lieu d'un 404. La route est
    # publique, sinon LoginRequiredMiddleware redirige vers la connexion.
    path(
        "favicon.ico",
        login_not_required(
            RedirectView.as_view(url=static_url("img/favicon.ico"), permanent=True)
        ),
        name="favicon",
    ),
    path("", include("core.urls")),
]

# Servir les fichiers médias en mode développement
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
