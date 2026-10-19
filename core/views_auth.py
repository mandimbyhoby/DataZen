"""Vue de connexion protégée contre la force brute.

``LoginView`` de Django n'offre aucun ralentissement : un script peut essayer
des milliers de mots de passe. Cette sous-classe compte les échecs via
:mod:`core.throttling` et renvoie un HTTP 429 tant que la fenêtre de blocage
n'est pas écoulée.
"""
from __future__ import annotations

from django.contrib.auth.views import LoginView
from django.utils.translation import gettext_lazy as _

from . import throttling


class ThrottledLoginView(LoginView):
    """Formulaire de connexion avec limitation des tentatives échouées."""

    template_name = "core/login.html"

    def post(self, request, *args, **kwargs):
        username = (request.POST.get("username") or "").strip()

        if throttling.is_locked_out(request, username):
            wait = throttling.remaining_seconds(request, username)
            minutes = max(1, (wait + 59) // 60)
            form = self.get_form()
            form.add_error(
                None,
                _(
                    "Trop de tentatives de connexion échouées. "
                    "Réessayez dans %(minutes)s minute(s)."
                )
                % {"minutes": minutes},
            )
            # 429 : le statut est explicite pour les clients HTTP et les
            # journaux, tout en réaffichant le formulaire à l'utilisateur.
            return self.render_to_response(self.get_context_data(form=form), status=429)

        response = super().post(request, *args, **kwargs)

        if request.user.is_authenticated:
            throttling.reset(request, username)
        elif response.status_code == 200:
            # 200 = le formulaire est réaffiché avec une erreur : identifiants
            # refusés. Un 302 signale une connexion réussie.
            throttling.register_failure(request, username)

        return response
