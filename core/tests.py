"""Tests de l'application DataZen (authentification, asynchrone, règles)."""
import json
import re
from datetime import timedelta
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import User
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import pgettext

from . import views
from .errors import user_error
from .forms import CleaningOptionsForm, WebhookForm
from .models import ActivityLog, ApiToken, CleaningRule, DataFile, Profile, Webhook
from .services import activity as activity_service
from .services import api as api_service
from .services.api import (
    WebhookUrlError,
    hash_token,
    legacy_token_hash,
    validate_webhook_url,
)
from .services import overview as overview_service
from .services import retention as retention_service
from .services import search as search_service
from .services.dashboard import build_dashboard
from .services.pipeline import run_cleaning
from .services.reader import read_dataframe
from .services.validation import build_detection

CSV_CONTENT = (
    "id;nom;email;telephone;ville\n"
    "1;  alice ;Alice@Example.COM;06 12 34 56 78;paris\n"
    "2;Bob;bob@example.com;0612345679;Lyon\n"
    "3;alice;alice@example.com;0612345678;Paris\n"
    "4;;inconnu;;\n"
)


def make_upload(name="clients.csv", content=CSV_CONTENT):
    return SimpleUploadedFile(name, content.encode("utf-8"), content_type="text/csv")


class AuthTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            "alice", "alice@example.com", "MotDePasse!2024"
        )

    def _login(self):
        self.client.force_login(self.user)

    def test_upload_file_picker_uses_selected_language(self):
        self._login()
        session = self.client.session
        session["django_language"] = "en"
        session.save()

        response = self.client.get(reverse("core:index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'for="id_file"')
        self.assertContains(response, 'class="dz-file-input"')
        self.assertContains(response, "Choose file")
        self.assertContains(response, "No file selected")
        self.assertContains(response, 'aria-live="polite"')

    def test_upload_file_picker_renders_in_french(self):
        self._login()
        response = self.client.get(reverse("core:index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Parcourir…")
        self.assertContains(response, "Aucun fichier sélectionné")

    def test_signup_creates_and_logs_in_user(self):
        response = self.client.post(
            reverse("core:signup"),
            {
                "username": "bob",
                "email": "bob@example.com",
                "password1": "MotDePasse!2024",
                "password2": "MotDePasse!2024",
            },
        )
        self.assertRedirects(response, reverse("core:index"))
        self.assertTrue(User.objects.filter(username="bob").exists())
        self.assertIn("_auth_user_id", self.client.session)

    def test_login_page_renders(self):
        response = self.client.get(reverse("core:login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Connexion")

    def test_upload_success_message_uses_selected_language(self):
        self._login()
        session = self.client.session
        session["django_language"] = "en"
        session.save()

        response = self.client.post(reverse("core:index"), {"file": make_upload()})

        self.assertRedirects(
            response,
            reverse("core:dataset_detail", args=[DataFile.objects.get().pk]),
        )
        message = list(response.wsgi_request._messages)[0]
        self.assertEqual(str(message), "File uploaded successfully.")

    def test_upload_assigns_the_logged_in_account_as_owner(self):
        self._login()
        response = self.client.post(reverse("core:index"), {"file": make_upload()})

        data_file = DataFile.objects.get()
        self.assertRedirects(response, reverse("core:dataset_detail", args=[data_file.pk]))
        self.assertEqual(data_file.owner, self.user)
        self.assertEqual(
            self.client.get(reverse("core:dataset_detail", args=[data_file.pk])).status_code,
            200,
        )

    def test_anonymous_cannot_upload(self):
        response = self.client.post(reverse("core:index"), {"file": make_upload()})

        self.assertRedirects(
            response, f"{reverse('core:login')}?next={reverse('core:index')}"
        )
        self.assertFalse(DataFile.objects.exists())

    def test_anonymous_cannot_open_a_dataset(self):
        data_file = DataFile.objects.create(
            owner=self.user, file=make_upload(), original_name="clients.csv"
        )
        url = reverse("core:dataset_detail", args=[data_file.pk])

        response = self.client.get(url)

        self.assertRedirects(response, f"{reverse('core:login')}?next={url}")

    def test_anonymous_cannot_start_cleaning(self):
        data_file = DataFile.objects.create(
            owner=self.user, file=make_upload(), original_name="clients.csv"
        )
        url = reverse("core:dataset_detail", args=[data_file.pk])

        with mock.patch.object(views, "start_cleaning") as start:
            response = self.client.post(url, {"trim_whitespace": "on"})

        self.assertRedirects(response, f"{reverse('core:login')}?next={url}")
        start.assert_not_called()
        data_file.refresh_from_db()
        self.assertFalse(data_file.cleaned_file)

    def test_upload_rejects_unsupported_extension(self):
        self._login()
        response = self.client.post(
            reverse("core:index"), {"file": make_upload(name="data.txt")}
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Choisissez un fichier CSV ou Excel")
        self.assertEqual(DataFile.objects.count(), 0)


class LoginRequiredPolicyTests(TestCase):
    """Toute l'application exige un compte : seules les pages d'authentification
    restent accessibles aux visiteurs anonymes."""

    PUBLIC_PAGES = (
        "core:login",
        "core:signup",
        "core:password_reset",
        "core:password_reset_done",
        "core:password_reset_complete",
    )

    PROTECTED_PAGES = (
        "core:index",
        "core:profile",
        "core:rules_list",
    )

    def test_public_pages_are_reachable_anonymously(self):
        for name in self.PUBLIC_PAGES:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_protected_pages_redirect_to_login(self):
        for name in self.PROTECTED_PAGES:
            with self.subTest(name=name):
                url = reverse(name)
                response = self.client.get(url)
                self.assertRedirects(response, f"{reverse('core:login')}?next={url}")

    def test_language_switch_is_reachable_anonymously(self):
        response = self.client.post(
            reverse("core:set_language"), {"language": "en", "next": "/"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/")

    def test_anonymous_visitor_owns_no_file(self):
        """Aucun fichier nettoyé ne peut exister sans compte propriétaire."""
        self.assertFalse(DataFile.objects.filter(owner__isnull=True).exists())


class CleaningOptionsTranslationTests(TestCase):
    def test_duplicate_review_notice_is_translated_in_english(self):
        from django.template import Context, Template
        from django.utils import translation

        template = Template(
            "{% load i18n %}{% blocktranslate trimmed count counter=count %}"
            "{{ counter }} doublon potentiel détecté. Ces lignes ne sont "
            "<strong>jamais</strong> supprimées automatiquement : elles nécessitent "
            "votre décision.{% plural %}{{ counter }} doublons potentiels détectés. "
            "Ces lignes ne sont <strong>jamais</strong> supprimées automatiquement : "
            "elles nécessitent votre décision.{% endblocktranslate %}"
        )
        with translation.override("en"):
            rendered = template.render(Context({"count": 0}))

        self.assertIn("0 potential duplicates detected", rendered)
        self.assertIn("<strong>never</strong>", rendered)
        self.assertIn("your decision is required", rendered)

        with translation.override("es"):
            rendered = template.render(Context({"count": 0}))
        self.assertIn("posibles duplicados", rendered)
        self.assertIn("<strong>nunca</strong>", rendered)
        self.assertIn("requieren su decisión", rendered)

    def test_cleaning_options_render_in_english(self):
        from django.utils import translation

        with translation.override("en"):
            form = CleaningOptionsForm(columns=["email"])
            self.assertEqual(
                str(form.fields["remove_duplicates"].label),
                "Remove duplicates (confirmation required)",
            )
            self.assertEqual(
                str(form.fields["dedupe_column"].help_text),
                "Choose a unique column (e.g. email) to merge variants of the same record (Alice / alice). Leave blank to remove only 100% identical rows.",
            )
            self.assertEqual(
                str(form.fields["anonymize"].label),
                "Anonymize sensitive data (names, emails, phone numbers)",
            )

    def test_cleaning_options_translation_keys_cover_form(self):
        from tools.translations.cleaning_options import CLEANING_OPTIONS_TRANSLATIONS

        french_form = CleaningOptionsForm(columns=["email", "name"])
        source_texts = {
            str(text)
            for field in french_form.fields.values()
            for text in (field.label, field.help_text, field.widget.attrs.get("placeholder", ""))
            if text
        }
        source_texts.discard("code_postal:^\\d{5}$\nreference:^[A-Z]{2}-\\d+$")
        for code, translations in CLEANING_OPTIONS_TRANSLATIONS.items():
            self.assertTrue(
                source_texts.issubset(translations),
                f"Missing cleaning option translations for {code}: {source_texts - translations.keys()}",
            )

    def test_cleaning_options_render_in_spanish(self):
        from django.utils import translation

        with translation.override("es"):
            form = CleaningOptionsForm()
            self.assertEqual(
                str(form.fields["remove_duplicates"].label),
                "Eliminar duplicados (se requiere confirmación)",
            )
            self.assertEqual(
                str(form.fields["dedupe_column"].label),
                "Columna clave para la deduplicación",
            )


class AdminLinkVisibilityTests(TestCase):
    """Le lien « Administration » ne doit apparaître que pour le staff."""

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get(reverse("core:index"))
        self.assertRedirects(
            response, f"{reverse('core:login')}?next={reverse('core:index')}"
        )

    def test_regular_user_does_not_see_admin_link(self):
        User.objects.create_user("alice", "alice@example.com", "MotDePasse!2024")
        self.client.login(username="alice", password="MotDePasse!2024")
        response = self.client.get(reverse("core:index"))
        self.assertNotContains(response, reverse("admin:index"))

    def test_staff_user_sees_admin_link(self):
        User.objects.create_user(
            "bob", "bob@example.com", "MotDePasse!2024", is_staff=True
        )
        self.client.login(username="bob", password="MotDePasse!2024")
        response = self.client.get(reverse("core:index"))
        self.assertContains(response, reverse("admin:index"))


class ProfileTests(TestCase):
    """Page de profil : accès, mise à jour et photo de profil."""

    def setUp(self):
        self.user = User.objects.create_user(
            "alice", "alice@example.com", "MotDePasse!2024"
        )
        self.url = reverse("core:profile")

    @staticmethod
    def make_image(name="avatar.png", size=(64, 64), fmt="PNG"):
        """Génère une vraie image en mémoire (Pillow est requis par ImageField)."""
        from io import BytesIO

        from PIL import Image

        buffer = BytesIO()
        Image.new("RGB", size, (79, 70, 229)).save(buffer, format=fmt)
        content_type = f"image/{fmt.lower()}"
        return SimpleUploadedFile(name, buffer.getvalue(), content_type=content_type)

    @staticmethod
    def make_heavy_image(name="big.png", size=(2000, 2000)):
        """Image réelle et volumineuse (> 5 Mo) : bruit aléatoire incompressible."""
        import os
        from io import BytesIO

        from PIL import Image

        width, height = size
        raw = os.urandom(width * height * 3)
        buffer = BytesIO()
        Image.frombytes("RGB", size, raw).save(buffer, format="PNG")
        return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")

    def test_profile_requires_login(self):
        response = self.client.get(self.url)
        self.assertRedirects(
            response, f"{reverse('core:login')}?next={self.url}"
        )

    def test_profile_is_created_automatically_on_signup(self):
        self.assertTrue(Profile.objects.filter(user=self.user).exists())

    def test_profile_page_renders(self):
        self.client.login(username="alice", password="MotDePasse!2024")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mon profil")
        self.assertContains(response, "alice@example.com")

    def test_profile_update_saves_identity_and_bio(self):
        self.client.login(username="alice", password="MotDePasse!2024")
        response = self.client.post(
            self.url,
            {
                "first_name": "Alice",
                "last_name": "Martin",
                "email": "alice.martin@example.com",
                "bio": "Analyste de données.",
            },
        )
        self.assertRedirects(response, self.url)

        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Alice")
        self.assertEqual(self.user.last_name, "Martin")
        self.assertEqual(self.user.email, "alice.martin@example.com")
        self.assertEqual(self.user.profile.bio, "Analyste de données.")

    def test_profile_success_message_uses_selected_language(self):
        self.client.login(username="alice", password="MotDePasse!2024")
        session = self.client.session
        session["django_language"] = "en"
        session.save()

        response = self.client.post(self.url, {"first_name": "Alice"}, follow=True)

        self.assertRedirects(response, self.url)
        self.assertIn(
            "Your profile has been updated.",
            [str(message) for message in response.context["messages"]],
        )

    def test_avatar_upload_succeeds(self):
        self.client.login(username="alice", password="MotDePasse!2024")
        response = self.client.post(
            self.url,
            {"first_name": "", "last_name": "", "email": "", "bio": "", "avatar": self.make_image()},
        )
        self.assertRedirects(response, self.url)

        profile = Profile.objects.get(user=self.user)
        self.assertTrue(profile.avatar)
        self.assertTrue(profile.avatar.name.startswith(f"avatars/{self.user.pk}/"))
        self.assertTrue(profile.avatar.name.endswith(".png"))

    def test_avatar_rejects_non_image_file(self):
        self.client.login(username="alice", password="MotDePasse!2024")
        response = self.client.post(
            self.url,
            {
                "first_name": "",
                "last_name": "",
                "email": "",
                "bio": "",
                "avatar": SimpleUploadedFile(
                    "notes.txt", b"pas une image", content_type="text/plain"
                ),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "image valide")
        self.assertFalse(Profile.objects.get(user=self.user).avatar)

    def test_avatar_rejects_oversized_file(self):
        self.client.login(username="alice", password="MotDePasse!2024")
        # Image réelle mais volumineuse : dépasse la limite de 5 Mo.
        big = self.make_heavy_image()
        self.assertGreater(big.size, 5 * 1024 * 1024)

        response = self.client.post(
            self.url,
            {"first_name": "", "last_name": "", "email": "", "bio": "", "avatar": big},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ne doit pas dépasser 5 Mo")
        self.assertFalse(Profile.objects.get(user=self.user).avatar)

    def test_avatar_delete_removes_file(self):
        self.client.login(username="alice", password="MotDePasse!2024")
        self.client.post(
            self.url,
            {"first_name": "", "last_name": "", "email": "", "bio": "", "avatar": self.make_image()},
        )
        profile = Profile.objects.get(user=self.user)
        self.assertTrue(profile.avatar)

        response = self.client.post(reverse("core:profile_avatar_delete"))
        self.assertRedirects(response, self.url)

        profile.refresh_from_db()
        self.assertFalse(profile.avatar)

    def test_avatar_delete_requires_post(self):
        self.client.login(username="alice", password="MotDePasse!2024")
        response = self.client.get(reverse("core:profile_avatar_delete"))
        self.assertEqual(response.status_code, 405)

    def test_avatar_rejects_unsupported_mime_type(self):
        """Une image valide mais d'un type non autorisé est refusée."""
        self.client.login(username="alice", password="MotDePasse!2024")
        image = self.make_image(name="avatar.bmp", fmt="BMP")
        image.content_type = "image/bmp"

        response = self.client.post(
            self.url,
            {"first_name": "", "last_name": "", "email": "", "bio": "", "avatar": image},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Format non pris en charge")
        self.assertFalse(Profile.objects.get(user=self.user).avatar)

    def test_profile_page_shows_default_avatar_without_photo(self):
        """Sans photo, l'avatar par défaut est affiché (comportement Facebook)."""
        self.client.login(username="alice", password="MotDePasse!2024")
        response = self.client.get(self.url)
        self.assertContains(response, "avatar-default.svg")
        self.assertContains(response, "avatar-camera")

    def test_profile_page_shows_uploaded_avatar(self):
        self.client.login(username="alice", password="MotDePasse!2024")
        self.client.post(
            self.url,
            {"first_name": "", "last_name": "", "email": "", "bio": "", "avatar": self.make_image()},
        )
        profile = Profile.objects.get(user=self.user)
        response = self.client.get(self.url)
        self.assertContains(response, profile.avatar.url)
        self.assertNotContains(response, "avatar-default.svg")

    def test_navbar_shows_default_avatar_without_photo(self):
        self.client.login(username="alice", password="MotDePasse!2024")
        response = self.client.get(reverse("core:index"))
        self.assertContains(response, "avatar-default.svg")

    def test_public_profile_shows_default_avatar_without_photo(self):
        profile = Profile.objects.get(user=self.user)
        profile.public_profile = True
        profile.save()
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:profile_public", args=["alice"]))
        self.assertContains(response, "avatar-default.svg")

    def test_initials_fall_back_to_username(self):
        profile = Profile.objects.get(user=self.user)
        self.assertEqual(profile.initials, "AL")

    def test_initials_use_full_name_when_available(self):
        self.user.first_name = "Alice"
        self.user.last_name = "Martin"
        self.user.save()
        self.assertEqual(Profile.objects.get(user=self.user).initials, "AM")

    def test_profile_update_saves_professional_fields(self):
        self.client.login(username="alice", password="MotDePasse!2024")
        response = self.client.post(
            self.url,
            {
                "first_name": "Alice",
                "last_name": "Martin",
                "email": "alice@example.com",
                "bio": "",
                "job_title": "Analyste",
                "organisation": "DataZen",
                "location": "Antananarivo",
                "website": "https://example.com",
            },
        )
        self.assertRedirects(response, self.url)

        profile = Profile.objects.get(user=self.user)
        self.assertEqual(profile.job_title, "Analyste")
        self.assertEqual(profile.organisation, "DataZen")
        self.assertEqual(profile.location, "Antananarivo")
        self.assertEqual(profile.website, "https://example.com")

    def test_profile_update_saves_preferences(self):
        self.client.login(username="alice", password="MotDePasse!2024")
        response = self.client.post(
            self.url,
            {
                "first_name": "",
                "last_name": "",
                "email": "",
                "bio": "",
                "theme_preference": "dark",
                "date_format": "Y-m-d",
                "email_notifications": "on",
                "public_profile": "on",
            },
        )
        self.assertRedirects(response, self.url)

        profile = Profile.objects.get(user=self.user)
        self.assertEqual(profile.theme_preference, "dark")
        self.assertEqual(profile.date_format, "Y-m-d")
        self.assertTrue(profile.email_notifications)
        self.assertTrue(profile.public_profile)

    def test_profile_rejects_invalid_website(self):
        self.client.login(username="alice", password="MotDePasse!2024")
        response = self.client.post(
            self.url,
            {
                "first_name": "",
                "last_name": "",
                "email": "",
                "bio": "",
                "website": "pas-une-url",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Profile.objects.get(user=self.user).website, "")

    def test_completion_grows_with_filled_fields(self):
        profile = Profile.objects.get(user=self.user)
        self.assertEqual(profile.completion["percent"], 11)  # email seul renseigné
        self.assertIn("Photo de profil", profile.completion["missing"])

        self.user.first_name = "Alice"
        self.user.last_name = "Martin"
        self.user.save()
        profile.refresh_from_db()
        self.assertEqual(profile.completion["percent"], 33)

    def test_completion_is_full_when_everything_is_set(self):
        self.user.first_name = "Alice"
        self.user.last_name = "Martin"
        self.user.save()
        profile = Profile.objects.get(user=self.user)
        profile.bio = "Présentation."
        profile.job_title = "Analyste"
        profile.organisation = "DataZen"
        profile.location = "Antananarivo"
        profile.website = "https://example.com"
        profile.avatar = "avatars/1/test.png"
        profile.save()

        self.assertEqual(profile.completion["percent"], 100)
        self.assertEqual(profile.completion["missing"], [])

    def test_display_name_prefers_full_name(self):
        profile = Profile.objects.get(user=self.user)
        self.assertEqual(profile.display_name, "alice")

        self.user.first_name = "Alice"
        self.user.last_name = "Martin"
        self.user.save()
        self.assertEqual(Profile.objects.get(user=self.user).display_name, "Alice Martin")

    def test_password_change_page_renders(self):
        self.client.login(username="alice", password="MotDePasse!2024")
        response = self.client.get(reverse("core:profile_password"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Changer mon mot de passe")

    def test_password_change_updates_password(self):
        self.client.login(username="alice", password="MotDePasse!2024")
        response = self.client.post(
            reverse("core:profile_password"),
            {
                "old_password": "MotDePasse!2024",
                "new_password1": "NouveauMotDePasse!2025",
                "new_password2": "NouveauMotDePasse!2025",
            },
        )
        self.assertRedirects(response, self.url)

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NouveauMotDePasse!2025"))

    def test_password_change_rejects_wrong_current_password(self):
        self.client.login(username="alice", password="MotDePasse!2024")
        response = self.client.post(
            reverse("core:profile_password"),
            {
                "old_password": "MauvaisMotDePasse!2024",
                "new_password1": "NouveauMotDePasse!2025",
                "new_password2": "NouveauMotDePasse!2025",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("MotDePasse!2024"))

    def test_password_change_requires_login(self):
        response = self.client.get(reverse("core:profile_password"))
        self.assertEqual(response.status_code, 302)

    def test_profile_export_returns_json(self):
        self.client.login(username="alice", password="MotDePasse!2024")
        response = self.client.get(reverse("core:profile_export"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertIn("attachment", response["Content-Disposition"])

        payload = json.loads(response.content)
        self.assertEqual(payload["compte"]["nom_utilisateur"], "alice")
        self.assertIn("profil", payload)
        self.assertIn("fichiers", payload)
        self.assertIn("regles", payload)

    def test_profile_export_requires_login(self):
        response = self.client.get(reverse("core:profile_export"))
        self.assertEqual(response.status_code, 302)

    def test_profile_export_includes_file_dimensions(self):
        """L'export lit les dimensions réelles du fichier, sans erreur."""
        self.client.login(username="alice", password="MotDePasse!2024")
        DataFile.objects.create(
            owner=self.user,
            file=make_upload(),
            original_name="clients.csv",
        )
        response = self.client.get(reverse("core:profile_export"))
        self.assertEqual(response.status_code, 200)

        payload = json.loads(response.content)
        self.assertEqual(len(payload["fichiers"]), 1)
        entry = payload["fichiers"][0]
        self.assertEqual(entry["nom"], "clients.csv")
        self.assertIsInstance(entry["lignes"], int)
        self.assertIsInstance(entry["colonnes"], int)
        self.assertGreater(entry["lignes"], 0)
        self.assertGreater(entry["colonnes"], 0)

    def test_account_delete_requires_username_confirmation(self):
        self.client.login(username="alice", password="MotDePasse!2024")
        response = self.client.post(reverse("core:profile_delete"), {"confirmation": "mauvais"})
        self.assertRedirects(response, self.url)
        self.assertTrue(User.objects.filter(username="alice").exists())

    def test_account_delete_removes_user(self):
        self.client.login(username="alice", password="MotDePasse!2024")
        response = self.client.post(reverse("core:profile_delete"), {"confirmation": "alice"})
        # Le compte supprimé, la session devient anonyme : l'accueil exige une
        # connexion et redirige donc vers la page de connexion.
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("core:index"))
        self.assertFalse(User.objects.filter(username="alice").exists())

    def test_account_delete_requires_post(self):
        self.client.login(username="alice", password="MotDePasse!2024")
        response = self.client.get(reverse("core:profile_delete"))
        self.assertEqual(response.status_code, 405)

    def test_superuser_cannot_delete_own_account(self):
        admin = User.objects.create_superuser("root", "root@example.com", "MotDePasse!2024")
        self.client.login(username="root", password="MotDePasse!2024")
        response = self.client.post(reverse("core:profile_delete"), {"confirmation": "root"})
        self.assertRedirects(response, self.url)
        self.assertTrue(User.objects.filter(username=admin.username).exists())

    def test_public_profile_hidden_by_default(self):
        other = User.objects.create_user("bob", "bob@example.com", "MotDePasse!2024")
        self.client.login(username="bob", password="MotDePasse!2024")
        response = self.client.get(reverse("core:profile_public", args=["alice"]))
        self.assertRedirects(response, reverse("core:index"))
        self.assertTrue(other.is_authenticated)

    def test_public_profile_visible_when_enabled(self):
        profile = Profile.objects.get(user=self.user)
        profile.public_profile = True
        profile.job_title = "Analyste"
        profile.save()

        self.client.force_login(self.user)
        response = self.client.get(reverse("core:profile_public", args=["alice"]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "alice")
        self.assertContains(response, "Analyste")

    def test_own_profile_visible_even_when_private(self):
        self.client.login(username="alice", password="MotDePasse!2024")
        response = self.client.get(reverse("core:profile_public", args=["alice"]))
        self.assertEqual(response.status_code, 200)

    def test_public_profile_unknown_user_returns_404(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:profile_public", args=["inconnu"]))
        self.assertEqual(response.status_code, 404)

    def test_profile_page_shows_completion_and_activity(self):
        self.client.login(username="alice", password="MotDePasse!2024")
        response = self.client.get(self.url)
        self.assertContains(response, "Complétion du profil")
        self.assertContains(response, "Activité récente")
        self.assertContains(response, "Zone de danger")
        self.assertContains(response, "Exporter mes données")


class PasswordResetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            "alice", "alice@example.com", "AncienMotDePasse!2024"
        )

    def _reset_urls(self, mail):
        """Extrait le lien de réinitialisation du message envoyé."""
        body = mail.body
        path = body.split("http://testserver")[1].split()[0]
        return path

    def test_login_page_links_to_reset(self):
        response = self.client.get(reverse("core:login"))
        self.assertContains(response, reverse("core:password_reset"))
        self.assertContains(response, "Mot de passe oublié")

    def test_reset_pages_render(self):
        for name in (
            "core:password_reset",
            "core:password_reset_done",
            "core:password_reset_complete",
        ):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_full_reset_flow_changes_password(self):
        response = self.client.post(
            reverse("core:password_reset"), {"email": "alice@example.com"}
        )
        self.assertRedirects(response, reverse("core:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)

        path = self._reset_urls(mail.outbox[0])

        # Django redirige une première fois vers l'URL avec le token « set-password ».
        response = self.client.get(path)
        self.assertEqual(response.status_code, 302)
        response = self.client.get(response.url)
        self.assertTrue(response.context["validlink"])

        response = self.client.post(
            response.request["PATH_INFO"],
            {"new_password1": "NouveauMotDePasse!2025", "new_password2": "NouveauMotDePasse!2025"},
        )
        self.assertRedirects(response, reverse("core:password_reset_complete"))

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NouveauMotDePasse!2025"))

    def test_unknown_email_does_not_leak(self):
        response = self.client.post(
            reverse("core:password_reset"), {"email": "inconnu@example.com"}
        )
        self.assertRedirects(response, reverse("core:password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)


class PasswordToggleTests(TestCase):
    """Le bouton « œil » est injecté côté client par static/js/main.js."""

    TEMPLATES = ("core:login", "core:signup", "core:password_reset")

    def test_pages_load_the_toggle_script(self):
        for name in self.TEMPLATES:
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "js/main.js")

    def test_toggle_script_targets_password_fields(self):
        source = (
            Path(__file__).resolve().parent.parent
            / "static"
            / "js"
            / "main.js"
        ).read_text(encoding="utf-8")
        self.assertIn("initPasswordToggles", source)
        self.assertIn('input[type="password"]', source)
        self.assertIn("password-toggle-btn", source)


class OwnershipTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", password="MotDePasse!2024")
        self.bob = User.objects.create_user("bob", password="MotDePasse!2024")

    def _upload(self, user):
        self.client.force_login(user)
        return self.client.post(reverse("core:index"), {"file": make_upload()})

    def test_upload_assigns_owner(self):
        self._upload(self.alice)
        data_file = DataFile.objects.get()
        self.assertEqual(data_file.owner, self.alice)

    def test_index_only_lists_own_files(self):
        self._upload(self.alice)
        self.client.force_login(self.bob)
        response = self.client.get(reverse("core:index"))
        self.assertEqual(response.context["global_stats"]["total"], 0)

    def test_cannot_open_other_users_file(self):
        self._upload(self.alice)
        data_file = DataFile.objects.get()
        self.client.force_login(self.bob)
        response = self.client.get(
            reverse("core:dataset_detail", args=[data_file.pk])
        )
        self.assertRedirects(response, reverse("core:index"))

    def test_delete_dataset_success_message_uses_active_language(self):
        data_file = DataFile.objects.create(
            owner=self.alice,
            file=make_upload(name="clients.csv"),
            original_name="donnees_clients_a_nettoyer.csv",
        )
        self.client.force_login(self.alice)
        session = self.client.session
        session["django_language"] = "en"
        session.save()

        response = self.client.post(reverse("core:delete_dataset", args=[data_file.pk]))

        self.assertRedirects(response, reverse("core:index"))
        message = list(response.wsgi_request._messages)[0]
        self.assertEqual(
            str(message),
            "File ‘donnees_clients_a_nettoyer.csv’ deleted.",
        )
        self.assertFalse(DataFile.objects.filter(pk=data_file.pk).exists())

    def test_superuser_sees_all_files(self):
        self._upload(self.alice)
        admin = User.objects.create_superuser(
            "root", "root@example.com", "MotDePasse!2024"
        )
        self.client.force_login(admin)
        response = self.client.get(reverse("core:index"))
        self.assertEqual(response.context["global_stats"]["total"], 1)

    def test_old_cleaned_files_are_archived_and_remain_accessible(self):
        data_file = DataFile.objects.create(
            owner=self.alice,
            file=make_upload(),
            original_name="archive.csv",
            status=DataFile.Status.CLEANED,
            cleaned_at=timezone.now() - timedelta(days=31),
        )

        self.client.force_login(self.alice)
        recent_response = self.client.get(reverse("core:index"))
        data_file.refresh_from_db()

        self.assertEqual(data_file.archived_at, data_file.cleaned_at)
        self.assertNotContains(recent_response, "archive.csv")
        self.assertEqual(recent_response.context["global_stats"]["total"], 0)

        archive_response = self.client.get(f"{reverse('core:index')}?archive=1")
        self.assertContains(archive_response, "archive.csv")
        self.assertEqual(archive_response.context["recent_files"][0].pk, data_file.pk)
        self.assertTrue(data_file.file.storage.exists(data_file.file.name))

    def test_recent_cleaned_files_are_not_archived_early(self):
        data_file = DataFile.objects.create(
            owner=self.alice,
            file=make_upload(),
            original_name="recent.csv",
            status=DataFile.Status.CLEANED,
            cleaned_at=timezone.now() - timedelta(days=29),
        )

        self.client.force_login(self.alice)
        response = self.client.get(reverse("core:index"))
        data_file.refresh_from_db()

        self.assertIsNone(data_file.archived_at)
        self.assertContains(response, "recent.csv")
        self.assertEqual(response.context["global_stats"]["total"], 1)

    def test_archived_files_remain_private_to_their_owner(self):
        DataFile.objects.create(
            owner=self.alice,
            file=make_upload(),
            original_name="private-archive.csv",
            status=DataFile.Status.CLEANED,
            cleaned_at=timezone.now() - timedelta(days=31),
        )

        self.client.force_login(self.bob)
        response = self.client.get(f"{reverse('core:index')}?archive=1")

        self.assertNotContains(response, "private-archive.csv")
        self.assertEqual(response.context["archived_count"], 0)

    def test_user_can_manually_archive_and_restore_file(self):
        data_file = DataFile.objects.create(
            owner=self.alice,
            file=make_upload(),
            original_name="manual.csv",
            status=DataFile.Status.CLEANED,
            cleaned_at=timezone.now() - timedelta(days=1),
        )
        self.client.force_login(self.alice)

        recent_response = self.client.get(reverse("core:index"))
        self.assertContains(recent_response, "Archiver")
        archive_response = self.client.post(
            reverse("core:archive_dataset", args=[data_file.pk])
        )
        data_file.refresh_from_db()
        self.assertRedirects(archive_response, f"{reverse('core:index')}?archive=1")
        self.assertIsNotNone(data_file.archived_at)
        archive_page = self.client.get(f"{reverse('core:index')}?archive=1")
        self.assertContains(archive_page, "manual.csv")
        self.assertContains(archive_page, "Restaurer")

        restore_response = self.client.post(
            reverse("core:restore_dataset", args=[data_file.pk])
        )
        data_file.refresh_from_db()
        self.assertRedirects(restore_response, reverse("core:index"))
        self.assertIsNone(data_file.archived_at)
        self.assertTrue(data_file.archive_exempt_from_auto)

    def test_other_user_cannot_manually_archive_file(self):
        data_file = DataFile.objects.create(
            owner=self.alice,
            file=make_upload(),
            original_name="protected.csv",
            status=DataFile.Status.CLEANED,
        )
        self.client.force_login(self.bob)

        self.client.post(reverse("core:archive_dataset", args=[data_file.pk]))

        data_file.refresh_from_db()
        self.assertIsNone(data_file.archived_at)

    def test_delete_confirmation_follows_selected_language(self):
        DataFile.objects.create(
            owner=self.alice,
            file=make_upload(),
            original_name="report.csv",
            status=DataFile.Status.CLEANED,
        )
        session = self.client.session
        session["django_language"] = "en"
        session.save()
        self.client.force_login(self.alice)

        response = self.client.get(reverse("core:index"))

        self.assertContains(response, "Delete “")
        self.assertContains(response, "report.csv” permanently?")
        self.assertContains(response, 'aria-label="Delete report.csv"')


class CleaningRuleTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="MotDePasse!2024")
        self.client.force_login(self.user)

    def test_create_rule(self):
        response = self.client.post(
            reverse("core:rules_list"),
            {
                "name": "Emails minuscules",
                "operation": "normalize_emails",
                "column": "email",
                "value": "",
                "is_active": "on",
            },
        )
        self.assertRedirects(response, reverse("core:rules_list"))
        rule = CleaningRule.objects.get()
        self.assertEqual(rule.owner, self.user)

    def test_toggle_and_delete_rule(self):
        rule = CleaningRule.objects.create(
            owner=self.user, name="R", operation="trim_whitespace"
        )
        self.client.post(reverse("core:rule_toggle", args=[rule.pk]))
        rule.refresh_from_db()
        self.assertFalse(rule.is_active)

        self.client.post(reverse("core:rule_delete", args=[rule.pk]))
        self.assertFalse(CleaningRule.objects.exists())

    def test_toggle_message_is_translated(self):
        """Le message d'état d'une règle suit la langue de l'interface."""
        rule = CleaningRule.objects.create(
            owner=self.user, name="R", operation="trim_whitespace"
        )
        for language, enabled, disabled in (
            ("fr", "Règle « R » activée.", "Règle « R » désactivée."),
            ("en", "Rule “R” enabled.", "Rule “R” disabled."),
        ):
            session = self.client.session
            session["django_language"] = language
            session.save()
            response = self.client.post(
                reverse("core:rule_toggle", args=[rule.pk]), follow=True
            )
            rule.refresh_from_db()
            expected = enabled if rule.is_active else disabled
            messages = [str(message) for message in response.context["messages"]]
            self.assertIn(expected, messages)

    def test_apply_rules_in_pipeline(self):
        """Une règle personnalisée est bien appliquée par le moteur."""
        data_file = DataFile.objects.create(
            owner=self.user,
            file=make_upload(),
            original_name="clients.csv",
        )
        operations, _ = run_cleaning(
            data_file,
            {"trim_whitespace": True},
            rules=[{"operation": "normalize_emails", "column": "email", "value": ""}],
        )
        self.assertTrue(any("[Règle]" in op for op in operations))
        self.assertTrue(data_file.cleaned_file)


class AsyncCleaningTests(TransactionTestCase):
    """Le nettoyage s'exécute dans un thread : il faut des données réellement
    commitées (TransactionTestCase) pour que la connexion du thread les voie."""

    def setUp(self):
        self.user = User.objects.create_user("alice", password="MotDePasse!2024")
        self.client.force_login(self.user)
        self.data_file = DataFile.objects.create(
            owner=self.user,
            file=make_upload(),
            original_name="clients.csv",
        )

    def test_post_starts_background_cleaning(self):
        # La vue doit bien déclencher le nettoyage asynchrone. On intercepte
        # l'appel pour vérifier les arguments, mais on ne démarre pas le thread
        # pendant la requête : sur la base SQLite en mémoire partagée des tests,
        # la connexion du thread entrerait en conflit de verrou avec celle de la
        # requête et l'échec serait intermittent. On le lance donc après la
        # réponse, ce qui reste déterministe.
        calls = []
        real_start = views.start_cleaning

        def capture(*args, **kwargs):
            calls.append((args, kwargs))
            return None

        with mock.patch.object(views, "start_cleaning", capture):
            response = self.client.post(
                reverse("core:dataset_detail", args=[self.data_file.pk]),
                {
                    "trim_whitespace": "on",
                    "normalize_case": "on",
                    "normalize_emails": "on",
                    "normalize_phones": "on",
                    "normalize_dates": "on",
                    "normalize_salaries": "on",
                },
            )

        self.assertRedirects(
            response, reverse("core:dataset_detail", args=[self.data_file.pk])
        )
        self.assertEqual(len(calls), 1)
        args, kwargs = calls[0]
        self.assertEqual(args[0], self.data_file.pk)
        self.assertTrue(kwargs["rules"] == [] or kwargs["rules"] is None)
        self.assertEqual(kwargs["language"], "fr-fr")

        thread = real_start(*args, **kwargs)
        thread.join(timeout=60)
        self.assertFalse(thread.is_alive())

        self.data_file.refresh_from_db()
        self.assertEqual(
            self.data_file.status,
            DataFile.Status.CLEANED,
            msg=f"Le nettoyage a échoué : {self.data_file.error_message}",
        )
        self.assertEqual(self.data_file.progress, 100)
        self.assertTrue(self.data_file.cleaned_file)
        self.assertTrue(self.data_file.report_file)

    def test_status_endpoint(self):
        response = self.client.get(
            reverse("core:cleaning_status", args=[self.data_file.pk])
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("status", payload)
        self.assertIn("progress", payload)

    def test_status_endpoint_denies_other_user(self):
        other = User.objects.create_user("bob", password="MotDePasse!2024")
        self.client.force_login(other)
        response = self.client.get(
            reverse("core:cleaning_status", args=[self.data_file.pk])
        )
        self.assertEqual(response.status_code, 404)


class PipelineTests(TestCase):
    def test_operations_follow_active_language(self):
        """Les résumés d'opérations utilisent la langue active."""
        data_file = DataFile.objects.create(
            file=make_upload(), original_name="clients.csv"
        )
        with translation.override("en"):
            operations, _ = run_cleaning(
                data_file,
                {"normalize_case": True, "anonymize": True},
                rules=[{"operation": "trim_whitespace"}],
            )
        self.assertIn("Category normalization (", operations[1])
        self.assertTrue(any("Anonymize sensitive data" in op for op in operations))
        self.assertIn("[Rule] Remove extra whitespace", operations[-1])
        self.assertFalse(any("Normalisation" in op or "Règle" in op for op in operations))

    def test_dedupe_on_key_column(self):
        """La colonne clé choisie dans le formulaire est bien utilisée."""
        data_file = DataFile.objects.create(
            file=make_upload(), original_name="clients.csv"
        )
        operations, _ = run_cleaning(
            data_file,
            {
                "remove_duplicates": True,
                "dedupe_column": "email",
                "dedupe_ignore_case": True,
            },
        )
        self.assertTrue(any("« email »" in op for op in operations))
        cleaned = read_dataframe(data_file.cleaned_file.path)
        self.assertEqual(len(cleaned), 3)

    def test_run_cleaning_produces_artifacts(self):
        data_file = DataFile.objects.create(
            file=make_upload(), original_name="clients.csv"
        )
        progress_values = []
        operations, _ = run_cleaning(
            data_file,
            {
                "trim_whitespace": True,
                "normalize_case": True,
                "normalize_emails": True,
                "remove_duplicates": True,
                "dedupe_ignore_case": True,
            },
            progress=lambda p, m="": progress_values.append(p),
        )
        self.assertTrue(operations)
        self.assertEqual(progress_values[-1], 100)
        self.assertTrue(Path(data_file.cleaned_file.path).exists())
        self.assertTrue(Path(data_file.report_file.path).exists())


class ValidationIssueDetailTests(TestCase):
    def test_dashboard_lists_invalid_values_with_source_rows(self):
        import pandas as pd

        df = pd.DataFrame(
            {
                "email": ["not-an-email", "person@example.com"],
                "telephone": ["bad-phone", "0612345678"],
                "date_inscription": ["32/13/2025", "2025-01-01"],
                "montant_achat": ["bad-amount", "12.50"],
            },
            index=[0, 1],
        )

        dashboard = build_dashboard(df, detection=build_detection(df))
        issue_item = next(item for item in dashboard["to_verify"] if item.get("issues"))

        self.assertEqual(len(issue_item["issues"]), 4)
        self.assertEqual(
            [(issue["row"], issue["column"]) for issue in issue_item["issues"]],
            [
                (1, "date_inscription"),
                (1, "email"),
                (1, "montant_achat"),
                (1, "telephone"),
            ],
        )
        self.assertEqual(
            {issue["reason"] for issue in issue_item["issues"]},
            {"Email invalide", "Téléphone non standard", "Date invalide", "Valeur numérique invalide"},
        )
        self.assertIn("4 erreur(s)", issue_item["text"])

    def test_dashboard_dynamic_labels_use_selected_language(self):
        import pandas as pd
        from django.utils import translation

        df = pd.DataFrame(
            {"email": ["bad", "person@example.com"], "montant": ["invalid", "2"]}
        )
        with translation.override("en"):
            dashboard = build_dashboard(df, detection=build_detection(df))

        labels = {item["label"] for item in dashboard["indicators"]}
        self.assertIn("Remaining errors", labels)
        self.assertIn("2 error(s) could not be corrected automatically.", [item["text"] for item in dashboard["to_verify"]])
        self.assertEqual(dashboard["dimensions"][0]["name"], "completeness")
        self.assertIn(dashboard["columns_quality"][0]["type"], {"email", "numerical"})

    def test_issue_detail_table_is_rendered_without_changing_data(self):
        import pandas as pd

        df = pd.DataFrame(
            {"email": ["not-an-email"], "telephone": ["bad-phone"]},
            index=[0],
        )
        dashboard = build_dashboard(df, detection=build_detection(df))
        from django.template.loader import render_to_string

        html = render_to_string(
            "core/validation_issues.html",
            {"verification_items": dashboard["to_verify"], "dashboard": dashboard},
        )

        self.assertIn("Afficher les détails des anomalies", html)
        self.assertIn("<th scope=\"col\">Ligne</th>", html)
        self.assertIn("not-an-email", html)
        self.assertIn("bad-phone", html)
        self.assertIn(">Email invalide</td>", html)
        self.assertIn(">Téléphone non standard</td>", html)
        self.assertEqual(df.iloc[0]["email"], "not-an-email")

    def test_issue_detail_table_uses_selected_language(self):
        import pandas as pd
        from django.template.loader import render_to_string
        from django.utils import translation

        df = pd.DataFrame({"email": ["not-an-email"]}, index=[0])
        with translation.override("en"):
            dashboard = build_dashboard(df, detection=build_detection(df))
            html = render_to_string(
                "core/validation_issues.html",
                {"verification_items": dashboard["to_verify"], "dashboard": dashboard},
            )

        self.assertIn("Show anomaly details", html)
        self.assertIn("<th scope=\"col\">Row</th>", html)
        self.assertIn(">Invalid email</td>", html)
        self.assertIn("1 error(s) could not be corrected automatically.", html)


class ChartTests(TestCase):
    """Graphiques statistiques (matplotlib + seaborn)."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="chartuser", password="MotDePasse!123"
        )
        self.client.login(username="chartuser", password="MotDePasse!123")

    @staticmethod
    def sample_df():
        import pandas as pd

        return pd.DataFrame(
            {
                "nom": ["A", "B", "C", "D", "E", "F", "G", "H"],
                "age": [25, 30, 35, 40, 45, 200, 28, 33],
                "salaire": [2000, 2500, 3000, 3500, 4000, 4500, 2200, 2800],
                "ville": [
                    "Paris", "Lyon", "Paris", "Nice",
                    "Lyon", "Paris", "Nice", "Lyon",
                ],
            }
        )

    def test_build_charts_returns_valid_png(self):
        """Chaque graphique produit est un PNG valide (signature + taille)."""
        from .services.charts import build_charts

        charts = build_charts(self.sample_df())
        self.assertTrue(charts)
        for chart in charts:
            self.assertTrue(chart["png"].startswith(b"\x89PNG"))
            self.assertGreater(len(chart["png"]), 1000)
            self.assertTrue(chart["title"])

    def test_all_expected_charts_available(self):
        """Le catalogue expose les graphiques attendus pour un jeu complet."""
        from .services.charts import available_charts
        from .services.dashboard import build_dashboard

        df = self.sample_df()
        slugs = available_charts(df, build_dashboard(df))
        for expected in (
            "score",
            "dimensions",
            "missing",
            "problems",
            "histograms",
            "boxplots",
            "correlation",
            "categories",
            "outliers",
        ):
            self.assertIn(expected, slugs)

    def test_empty_dataframe_does_not_crash(self):
        """Un DataFrame vide ne produit que la jauge de score."""
        import pandas as pd

        from .services.charts import available_charts, build_charts

        df = pd.DataFrame({"a": [], "b": []})
        self.assertEqual(available_charts(df), ["score"])
        self.assertEqual([c["slug"] for c in build_charts(df)], ["score"])

    def test_nan_only_dataframe_does_not_crash(self):
        """Un DataFrame ne contenant que des NaN ne plante pas."""
        import pandas as pd

        from .services.charts import available_charts, build_charts

        df = pd.DataFrame({"n": [None, None, None], "m": [float("nan")] * 3})
        self.assertEqual(available_charts(df), ["score"])
        self.assertEqual([c["slug"] for c in build_charts(df)], ["score"])

    def test_no_numeric_column_skips_numeric_charts(self):
        """Sans colonne numérique, les graphiques numériques sont omis."""
        import pandas as pd

        from .services.charts import available_charts

        df = pd.DataFrame({"x": ["a", "b", "c"], "y": ["d", "e", "f"]})
        slugs = available_charts(df)
        for absent in ("histograms", "boxplots", "correlation", "outliers"):
            self.assertNotIn(absent, slugs)

    def test_unknown_values_are_ignored(self):
        """Les valeurs « Inconnu » ne sont pas traitées comme numériques."""
        import pandas as pd

        from .services.charts import available_charts

        df = pd.DataFrame({"q": ["Inconnu", "Inconnu", "Inconnu"]})
        self.assertNotIn("histograms", available_charts(df))

    def test_chart_png_unknown_slug_returns_none(self):
        """Un slug inconnu renvoie ``None`` au lieu de lever une exception."""
        from .services.charts import chart_png

        self.assertIsNone(chart_png(self.sample_df(), {}, "inexistant"))

    def test_charts_as_data_uris(self):
        """Les images du rapport HTML sont encodées en URI ``data:``."""
        from .services.charts import charts_as_data_uris

        charts = charts_as_data_uris(self.sample_df())
        self.assertTrue(charts)
        for chart in charts:
            self.assertTrue(chart["data_uri"].startswith("data:image/png;base64,"))

    def test_chart_endpoint_returns_png(self):
        """L'endpoint de graphique renvoie bien une image PNG."""
        data_file = DataFile.objects.create(
            file=make_upload(), original_name="clients.csv", owner=self.user
        )
        run_cleaning(data_file, {"trim_whitespace": True})
        response = self.client.get(
            reverse("core:dataset_chart", args=[data_file.pk, "score"])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertTrue(response.content.startswith(b"\x89PNG"))

    def test_chart_endpoint_unknown_slug_redirects(self):
        """Un slug inconnu redirige vers la page du dataset."""
        data_file = DataFile.objects.create(
            file=make_upload(), original_name="clients.csv", owner=self.user
        )
        run_cleaning(data_file, {"trim_whitespace": True})
        response = self.client.get(
            reverse("core:dataset_chart", args=[data_file.pk, "inexistant"])
        )
        self.assertEqual(response.status_code, 302)

    def test_chart_endpoint_requires_cleaned_file(self):
        """Sans fichier nettoyé, l'endpoint redirige au lieu de planter."""
        data_file = DataFile.objects.create(
            file=make_upload(), original_name="clients.csv", owner=self.user
        )
        response = self.client.get(
            reverse("core:dataset_chart", args=[data_file.pk, "score"])
        )
        self.assertEqual(response.status_code, 302)

    def test_analysis_page_renders_charts(self):
        """La page d'analyse exploratoire liste les graphiques disponibles."""
        data_file = DataFile.objects.create(
            file=make_upload(), original_name="clients.csv", owner=self.user
        )
        run_cleaning(data_file, {"trim_whitespace": True})
        response = self.client.get(
            reverse("core:dataset_analysis", args=[data_file.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Analyse exploratoire")
        self.assertContains(response, "matplotlib")
        self.assertContains(response, "seaborn")
        self.assertContains(response, "dz-kpi-dashboard")
        self.assertContains(response, "Doublons exacts")
        self.assertContains(response, "Valeurs aberrantes")
        self.assertEqual(len(response.context["dashboard"]["indicators"]), 6)
        self.assertIn("charts", response.context)
        self.assertTrue(response.context["charts"])
        self.assertEqual(
            response.context["charts"][0]["slug"], "score"
        )

    def test_analysis_page_without_cleaning_redirects(self):
        """Sans nettoyage préalable, la page d'analyse redirige."""
        data_file = DataFile.objects.create(
            file=make_upload(), original_name="clients.csv", owner=self.user
        )
        response = self.client.get(
            reverse("core:dataset_analysis", args=[data_file.pk])
        )
        self.assertEqual(response.status_code, 302)

    def test_analysis_page_denied_for_other_user(self):
        """Un autre utilisateur n'accède pas à l'analyse d'un dataset privé."""
        data_file = DataFile.objects.create(
            file=make_upload(), original_name="clients.csv", owner=self.user
        )
        run_cleaning(data_file, {"trim_whitespace": True})
        User.objects.create_user(username="intrus", password="MotDePasse!123")
        self.client.logout()
        self.client.login(username="intrus", password="MotDePasse!123")
        response = self.client.get(
            reverse("core:dataset_analysis", args=[data_file.pk])
        )
        self.assertEqual(response.status_code, 302)

    def test_report_html_embeds_charts(self):
        """Le rapport HTML téléchargeable embarque les graphiques."""
        data_file = DataFile.objects.create(
            file=make_upload(), original_name="clients.csv", owner=self.user
        )
        run_cleaning(data_file, {"trim_whitespace": True})
        response = self.client.get(
            reverse("core:download_report_html", args=[data_file.pk])
        )
        self.assertEqual(response.status_code, 200)
        content = b"".join(response.streaming_content).decode("utf-8")
        self.assertIn("Visualisations statistiques", content)
        self.assertIn("data:image/png;base64,", content)

    def test_dataset_detail_shows_chart_section(self):
        """La page du dataset affiche la section de visualisations."""
        data_file = DataFile.objects.create(
            file=make_upload(), original_name="clients.csv", owner=self.user
        )
        run_cleaning(data_file, {"trim_whitespace": True})
        response = self.client.get(
            reverse("core:dataset_detail", args=[data_file.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Visualisations statistiques")
        self.assertContains(response, "Analyse exploratoire")

    # ------------------------------------------------------------------
    # Traduction des visualisations statistiques
    # ------------------------------------------------------------------
    def _set_language(self, code):
        """Active une langue pour les requêtes suivantes du client de test."""
        session = self.client.session
        session["django_language"] = code
        session.save()

    def test_chart_labels_are_translated(self):
        """Les libellés des graphiques suivent la langue active."""
        from django.utils import translation
        from django.utils.translation import gettext

        with translation.override("fr"):
            french = gettext("Score global de qualité")
        with translation.override("en"):
            english = gettext("Score global de qualité")
        self.assertEqual(french, "Score global de qualité")
        self.assertEqual(english, "Overall quality score")

    def test_chart_labels_cover_all_site_languages(self):
        """Chaque langue du site traduit tous les libellés de graphique."""
        from django.conf import settings
        from django.utils import translation
        from django.utils.translation import gettext

        keys = (
            "Score global de qualité",
            "Score de la dimension",
            "Taux de complétude (%)",
            "Nombre d'occurrences",
            "Répartition des problèmes restants",
            "Effectif",
            "Distributions des colonnes numériques",
            "Boîtes à moustaches des colonnes numériques",
            "Matrice de corrélation (Pearson)",
            "Valeurs les plus fréquentes",
            "Nombre de valeurs aberrantes",
            "Valeurs aberrantes par colonne (méthode IQR)",
                        "Premier quartile",
                        "Troisième quartile",
                        "valeur(s) extrême(s)",
                    )
        for language in settings.SITE_LANGUAGES:
            code = language["code"]
            if code == "fr":
                continue
            with translation.override(code):
                for key in keys:
                    self.assertNotEqual(
                        gettext(key),
                        key,
                        f"{code} : « {key} » n'est pas traduit",
                    )

    def test_chart_numbers_use_language_decimal_separator(self):
        """Les valeurs affichées utilisent le séparateur décimal local."""
        from django.utils import translation

        from .services.charts import _num

        with translation.override("fr"):
            self.assertEqual(_num(95.5), "95,5")
        with translation.override("en"):
            self.assertEqual(_num(95.5), "95.5")

    def test_chart_png_differs_between_languages(self):
        """Le PNG rendu dépend de la langue (titres traduits)."""
        from django.utils import translation

        from .services.charts import chart_png
        from .services.dashboard import build_dashboard

        df = self.sample_df()
        dashboard = build_dashboard(df)
        with translation.override("fr"):
            french = chart_png(df, dashboard, "score")
        with translation.override("en"):
            english = chart_png(df, dashboard, "score")
        self.assertTrue(french.startswith(b"\x89PNG"))
        self.assertTrue(english.startswith(b"\x89PNG"))
        self.assertNotEqual(french, english)

    def test_chart_catalog_titles_are_translated(self):
        """Le catalogue des graphiques expose des titres traduits."""
        from django.utils import translation

        from .services.charts import chart_catalog

        df = self.sample_df()
        with translation.override("en"):
            titles = {c["slug"]: str(c["title"]) for c in chart_catalog(df)}
        self.assertEqual(titles["score"], "Overall score")
        self.assertEqual(titles["boxplots"], "Box plots")

    def test_chart_endpoint_varies_by_language(self):
        """L'endpoint PNG déclare ``Vary: Cookie`` (langue en session)."""
        data_file = DataFile.objects.create(
            file=make_upload(), original_name="clients.csv", owner=self.user
        )
        run_cleaning(data_file, {"trim_whitespace": True})
        response = self.client.get(
            reverse("core:dataset_chart", args=[data_file.pk, "score"])
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Cookie", response["Vary"])

    def test_chart_endpoint_renders_in_active_language(self):
        """Le PNG servi change lorsque l'utilisateur change de langue."""
        data_file = DataFile.objects.create(
            file=make_upload(), original_name="clients.csv", owner=self.user
        )
        run_cleaning(data_file, {"trim_whitespace": True})
        url = reverse("core:dataset_chart", args=[data_file.pk, "score"])

        self._set_language("fr")
        french = self.client.get(url).content
        self._set_language("en")
        english = self.client.get(url).content
        self.assertNotEqual(french, english)

    def test_report_html_headings_are_translated(self):
        """Les titres de la section graphiques du rapport HTML sont traduits."""
        data_file = DataFile.objects.create(
            file=make_upload(), original_name="clients.csv", owner=self.user
        )
        run_cleaning(data_file, {"trim_whitespace": True})
        url = reverse("core:download_report_html", args=[data_file.pk])

        self._set_language("en")
        response = self.client.get(url)
        content = b"".join(response.streaming_content).decode("utf-8")
        self.assertIn("Statistical visualisations", content)
        self.assertIn('<html lang="en">', content)
        self.assertNotIn("Visualisations statistiques", content)

    def test_analysis_page_chart_links_carry_language(self):
        """Les images de la page d'analyse portent la langue active."""
        data_file = DataFile.objects.create(
            file=make_upload(), original_name="clients.csv", owner=self.user
        )
        run_cleaning(data_file, {"trim_whitespace": True})
        self._set_language("en")
        response = self.client.get(
            reverse("core:dataset_analysis", args=[data_file.pk])
        )
        self.assertContains(response, "?lang=en")

    def test_request_language_does_not_leak_after_response(self):
        """La langue activée pour une requête est restaurée ensuite.

        Sans cette restauration, la langue choisie par un utilisateur
        déteindrait sur le reste du processus (tests suivants, tâches de fond).
        """
        data_file = DataFile.objects.create(
            file=make_upload(), original_name="clients.csv", owner=self.user
        )
        run_cleaning(data_file, {"trim_whitespace": True})
        self._set_language("en")

        with translation.override("fr"):
            self.client.get(reverse("core:dataset_detail", args=[data_file.pk]))
            self.assertEqual(translation.get_language(), "fr")

        # ------------------------------------------------------------------
        # Données JSON des graphiques interactifs (React + Chart.js)
        # ------------------------------------------------------------------
        def test_chart_data_endpoint_returns_json(self):
            """L'endpoint JSON renvoie tous les graphiques du jeu de données."""
            data_file = DataFile.objects.create(
                file=make_upload(), original_name="clients.csv", owner=self.user
            )
            run_cleaning(data_file, {"trim_whitespace": True})
            response = self.client.get(
                reverse("core:dataset_chart_data", args=[data_file.pk])
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "application/json")
            self.assertIn("Cookie", response["Vary"])

            payload = response.json()
            self.assertIn(payload["direction"], ("ltr", "rtl"))
            self.assertIn("decimal", payload["separators"])
            self.assertIn("thousand", payload["separators"])

            slugs = [chart["slug"] for chart in payload["charts"]]
            self.assertEqual(slugs[0], "score")
            for expected in (
                "score",
                "dimensions",
                "missing",
                "problems",
                "histograms",
                "boxplots",
                "correlation",
                "categories",
                "outliers",
            ):
                self.assertIn(expected, slugs)

            kinds = {chart["slug"]: chart["kind"] for chart in payload["charts"]}
            self.assertEqual(kinds["score"], "gauge")
            self.assertEqual(kinds["dimensions"], "hbar")
            self.assertEqual(kinds["problems"], "vbar")
            self.assertEqual(kinds["histograms"], "histograms")
            self.assertEqual(kinds["boxplots"], "boxplots")
            self.assertEqual(kinds["correlation"], "heatmap")
            self.assertEqual(kinds["categories"], "categories")

        def test_chart_data_endpoint_is_translated(self):
            """Les titres et libellés du JSON suivent la langue active."""
            data_file = DataFile.objects.create(
                file=make_upload(), original_name="clients.csv", owner=self.user
            )
            run_cleaning(data_file, {"trim_whitespace": True})
            url = reverse("core:dataset_chart_data", args=[data_file.pk])

            self._set_language("en")
            english = self.client.get(url).json()
            self.assertEqual(english["language"], "en")
            titles = {chart["slug"]: chart["title"] for chart in english["charts"]}
            self.assertEqual(titles["score"], "Overall score")

            self._set_language("fr")
            french = self.client.get(url).json()
            self.assertEqual(french["language"], "fr")
            titles = {chart["slug"]: chart["title"] for chart in french["charts"]}
            self.assertEqual(titles["score"], "Score global de qualité")

        def test_chart_data_endpoint_marks_rtl_languages(self):
            """Une langue RTL est signalée pour que le navigateur aligne le texte."""
            data_file = DataFile.objects.create(
                file=make_upload(), original_name="clients.csv", owner=self.user
            )
            run_cleaning(data_file, {"trim_whitespace": True})
            self._set_language("ar")
            payload = self.client.get(
                reverse("core:dataset_chart_data", args=[data_file.pk])
            ).json()
            self.assertEqual(payload["direction"], "rtl")

        def test_chart_data_endpoint_requires_cleaned_file(self):
            """Sans fichier nettoyé, l'endpoint JSON répond 409."""
            data_file = DataFile.objects.create(
                file=make_upload(), original_name="clients.csv", owner=self.user
            )
            response = self.client.get(
                reverse("core:dataset_chart_data", args=[data_file.pk])
            )
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json(), {"error": "no_cleaned_data"})

        def test_chart_data_endpoint_hides_other_users_files(self):
            """Un dataset privé d'un autre utilisateur répond 404."""
            data_file = DataFile.objects.create(
                file=make_upload(), original_name="clients.csv", owner=self.user
            )
            run_cleaning(data_file, {"trim_whitespace": True})
            User.objects.create_user("intrus2", "intrus2@example.com", "MotDePasse!2024")
            self.client.logout()
            self.client.login(username="intrus2", password="MotDePasse!2024")
            response = self.client.get(
                reverse("core:dataset_chart_data", args=[data_file.pk])
            )
            self.assertEqual(response.status_code, 404)

        def test_chart_data_payload_is_json_serializable(self):
            """Le payload est sérialisable tel quel (aucun type numpy)."""
            import json

            from django.utils import translation

            from .services.charts import chart_data
            from .services.dashboard import build_dashboard

            df = self.sample_df()
            for code in ("fr", "en", "ar", "zh-hans"):
                with translation.override(code):
                    payload = chart_data(df, build_dashboard(df))
                    json.dumps(payload)

        def test_chart_data_boxplot_stats_are_consistent(self):
            """Les statistiques des boîtes à moustaches respectent l'ordre IQR."""
            from django.utils import translation

            from .services.charts import chart_data
            from .services.dashboard import build_dashboard

            df = self.sample_df()
            with translation.override("fr"):
                payload = chart_data(df, build_dashboard(df))
            boxplots = next(c for c in payload["charts"] if c["slug"] == "boxplots")
            self.assertTrue(boxplots["data"]["items"])
            for item in boxplots["data"]["items"]:
                self.assertLessEqual(item["min"], item["q1"])
                self.assertLessEqual(item["q1"], item["median"])
                self.assertLessEqual(item["median"], item["q3"])
                self.assertLessEqual(item["q3"], item["max"])
            self.assertIn("q1", boxplots["data"]["labels"])

        def test_analysis_page_exposes_chart_data_url(self):
            """La page d'analyse fournit l'URL JSON aux composants React."""
            data_file = DataFile.objects.create(
                file=make_upload(), original_name="clients.csv", owner=self.user
            )
            run_cleaning(data_file, {"trim_whitespace": True})
            response = self.client.get(
                reverse("core:dataset_analysis", args=[data_file.pk])
            )
            self.assertContains(response, "data-dz-charts")
            self.assertContains(
                response,
                reverse("core:dataset_chart_data", args=[data_file.pk]),
            )


# --- Fonctionnalités « pro » : pilotage, confiance, productivité, API -----

PRO_USER_PASSWORD = "MotDePasse!2024"


def make_cleaned_file(user, name="clients.csv", options=None):
    """Crée un fichier déjà nettoyé, avec ses indicateurs et ses artefacts."""
    data_file = DataFile.objects.create(
        file=make_upload(name), original_name=name, owner=user
    )
    run_cleaning(data_file, options or {"trim_whitespace": True})
    data_file.refresh_from_db()
    return data_file


class OverviewServiceTests(TestCase):
    """Agrégation multi-fichiers : le tableau de bord ne relit aucun fichier."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="prouser", password=PRO_USER_PASSWORD
        )

    def test_build_overview_aggregates_frozen_indicators(self):
        first = make_cleaned_file(self.user, "a.csv")
        second = make_cleaned_file(self.user, "b.csv")
        DataFile.objects.filter(pk=first.pk).update(
            quality_after=92.0, metrics={"duplicates": 2, "missing": 3}
        )
        DataFile.objects.filter(pk=second.pk).update(
            quality_after=82.0, metrics={"duplicates": 1, "missing": 1}
        )

        overview = overview_service.build_overview(
            DataFile.objects.filter(owner=self.user)
        )

        self.assertEqual(overview["totals"]["files"], 2)
        self.assertEqual(overview["totals"]["cleaned"], 2)
        self.assertEqual(overview["average_score"], 87.0)
        self.assertEqual(len(overview["timeline"]), 12)
        problems = {item["key"]: item["value"] for item in overview["problems"]}
        self.assertEqual(problems["duplicates"], 3)
        self.assertEqual(problems["missing"], 4)

    def test_archived_files_are_excluded_from_the_totals(self):
        data_file = make_cleaned_file(self.user, "archived.csv")
        data_file.archived_at = timezone.now()
        data_file.save(update_fields=["archived_at"])

        overview = overview_service.build_overview(
            DataFile.objects.filter(owner=self.user)
        )

        self.assertEqual(overview["totals"]["files"], 0)
        self.assertEqual(overview["totals"]["archived"], 1)

    def test_timeline_heights_are_relative_to_the_peak(self):
        timeline = [{"count": 2}, {"count": 1}, {"count": 0}]
        heights = [
            bucket["height"] for bucket in overview_service.timeline_heights(timeline)
        ]
        self.assertEqual(heights, [100, 50, 0])

    def test_score_sparkline_ignores_buckets_without_score(self):
        timeline = [
            {"label": "01/01", "count": 0, "score": None},
            {"label": "08/01", "count": 1, "score": 90.0},
        ]
        points = overview_service.score_sparkline(timeline)
        self.assertEqual(len(points), 1)
        self.assertEqual(points[0]["score"], 90.0)
        self.assertAlmostEqual(points[0]["y"], 10.0, places=2)

    def test_aggregate_stats_sums_rows_and_scores(self):
        make_cleaned_file(self.user, "c.csv")
        stats = overview_service.aggregate_stats(
            DataFile.objects.filter(owner=self.user)
        )
        self.assertEqual(stats["files"], 1)
        self.assertGreaterEqual(stats["rows"], 1)
        self.assertIsNotNone(stats["average"])


class DashboardTests(TestCase):
    """Pilotage : tableau de bord global multi-fichiers."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="proboard", password=PRO_USER_PASSWORD
        )
        self.client.force_login(self.user)
        self.data_file = make_cleaned_file(self.user)

    def test_dashboard_renders_global_kpi_and_timeline(self):
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="dz-global-kpi"')
        self.assertContains(response, 'id="dz-timeline"')
        self.assertContains(response, "dz-timeline__svg")
        self.assertEqual(response.context["totals"]["files"], 1)
        self.assertEqual(response.context["aggregate"]["files"], 1)
        self.assertTrue(response.context["sparkline"])

    def test_dashboard_only_counts_the_connected_user_files(self):
        other = User.objects.create_user(
            username="proboard2", password=PRO_USER_PASSWORD
        )
        make_cleaned_file(other, "autre.csv")

        response = self.client.get(reverse("core:dashboard"))

        self.assertEqual(response.context["totals"]["files"], 1)

    def test_dashboard_requires_a_valid_json_timeline(self):
        response = self.client.get(reverse("core:dashboard"))
        timeline = json.loads(response.context["timeline_json"])
        self.assertEqual(len(timeline), 12)


class LocaleNumberRenderingTests(TestCase):
    """Les nombres injectés dans du CSS ou du SVG restent au format machine.

    En français, Django localise les flottants (``92.2`` devient ``92,2``).
    Injecté tel quel dans ``style="width: …%"`` ou dans ``cx="…"``, le nombre
    est rejeté par le navigateur : les barres de progression restent vides et
    le tracé du score disparaît. Les gabarits appliquent donc ``|unlocalize``.
    """

    # Un nombre localisé : virgule décimale, jamais un séparateur de milliers.
    LOCALIZED = re.compile(r'(?:style="[^"]*?|points="|cx="|cy="|aria-valuenow=")-?\d+,\d+')

    def setUp(self):
        self.user = User.objects.create_user(username="localenumbers")
        self.client.force_login(self.user)
        self.data_file = make_cleaned_file(
            self.user,
            options={
                "trim_whitespace": True,
                "normalize_case": True,
                "normalize_emails": True,
            },
        )
        session = self.client.session
        session["django_language"] = "fr"
        session.save()

    def _pages(self):
        return [
            reverse("core:dashboard"),
            reverse("core:index"),
            reverse("core:profile"),
            reverse("core:dataset_detail", args=[self.data_file.pk]),
            reverse("core:dataset_comparison", args=[self.data_file.pk]),
        ]

    def test_french_pages_never_emit_localized_numbers_in_css_or_svg(self):
        for url in self._pages():
            with self.subTest(url=url):
                html = self.client.get(url).content.decode("utf-8")
                self.assertIsNone(
                    self.LOCALIZED.search(html),
                    f"{url} contient un nombre localisé dans du CSS/SVG",
                )

    def test_french_dashboard_still_renders_the_sparkline(self):
        html = self.client.get(reverse("core:dashboard")).content.decode("utf-8")
        points = re.search(r'points="([^"]+)"', html)
        self.assertIsNotNone(points, "le tracé du score est absent")
        for pair in points.group(1).split():
            x, y = pair.split(",")
            float(x)
            float(y)

    def test_french_progress_bars_keep_a_machine_readable_width(self):
        html = self.client.get(reverse("core:dashboard")).content.decode("utf-8")
        widths = re.findall(r'style="width: ([^%"]+)%"', html)
        self.assertTrue(widths, "aucune barre de progression rendue")
        for width in widths:
            float(width)


class ComparisonTests(TestCase):
    """Confiance : comparaison avant / après du nettoyage."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="procompare", password=PRO_USER_PASSWORD
        )
        self.client.force_login(self.user)
        self.data_file = make_cleaned_file(
            self.user,
            options={
                "trim_whitespace": True,
                "normalize_case": True,
                "normalize_emails": True,
            },
        )

    def test_comparison_page_exposes_before_and_after(self):
        response = self.client.get(
            reverse("core:dataset_comparison", args=[self.data_file.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="dz-compare-kpi"')
        comparison = response.context["comparison"]
        self.assertIsNotNone(comparison["before"]["score"])
        self.assertIsNotNone(comparison["after"]["score"])
        self.assertTrue(comparison["columns"])
        self.assertIn("has_changes", comparison)

    def test_comparison_requires_a_cleaned_file(self):
        data_file = DataFile.objects.create(
            owner=self.user, file=make_upload(), original_name="brut.csv"
        )
        response = self.client.get(
            reverse("core:dataset_comparison", args=[data_file.pk])
        )
        self.assertRedirects(
            response, reverse("core:dataset_detail", args=[data_file.pk])
        )

    def test_comparison_is_denied_for_another_user(self):
        other = User.objects.create_user(
            username="procompare2", password=PRO_USER_PASSWORD
        )
        self.client.force_login(other)

        response = self.client.get(
            reverse("core:dataset_comparison", args=[self.data_file.pk])
        )

        self.assertRedirects(response, reverse("core:index"))


class PdfReportTests(TestCase):
    """Confiance : rapport PDF autonome (graphiques inclus)."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="propdf", password=PRO_USER_PASSWORD
        )
        self.client.force_login(self.user)
        self.data_file = make_cleaned_file(self.user)

    def test_pdf_report_is_generated_and_traced(self):
        response = self.client.get(
            reverse("core:download_pdf_report", args=[self.data_file.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("application/pdf"))
        self.assertIn("attachment", response["Content-Disposition"])
        payload = b"".join(response.streaming_content)
        response.close()
        self.assertTrue(payload.startswith(b"%PDF"))
        self.assertGreater(len(payload), 5000)
        self.assertTrue(
            ActivityLog.objects.filter(
                owner=self.user, action=ActivityLog.Action.REPORT
            ).exists()
        )

    def test_pdf_report_requires_a_cleaned_file(self):
        data_file = DataFile.objects.create(
            owner=self.user, file=make_upload(), original_name="brut.csv"
        )
        response = self.client.get(
            reverse("core:download_pdf_report", args=[data_file.pk])
        )
        self.assertRedirects(
            response, reverse("core:dataset_detail", args=[data_file.pk])
        )

    def test_pdf_report_is_denied_for_another_user(self):
        other = User.objects.create_user(
            username="propdf2", password=PRO_USER_PASSWORD
        )
        self.client.force_login(other)

        response = self.client.get(
            reverse("core:download_pdf_report", args=[self.data_file.pk])
        )

        self.assertRedirects(response, reverse("core:index"))


class ProductivityPageTests(TestCase):
    """Productivité : recherche globale (Ctrl+K), journal, aide-mémoire."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="prosearch", password=PRO_USER_PASSWORD
        )
        self.client.force_login(self.user)
        self.data_file = make_cleaned_file(self.user)

    def test_global_search_returns_matching_dataset(self):
        response = self.client.get(reverse("core:global_search"), {"q": "clients"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["type"], "dataset")
        self.assertEqual(
            payload["results"][0]["url"],
            reverse("core:dataset_detail", args=[self.data_file.pk]),
        )

    def test_global_search_returns_interface_pages(self):
        payload = self.client.get(
            reverse("core:global_search"), {"q": "Règles"}
        ).json()
        self.assertTrue(any(item["type"] == "page" for item in payload["results"]))

    def test_global_search_without_query_returns_nothing(self):
        payload = self.client.get(reverse("core:global_search")).json()
        self.assertEqual(payload["count"], 0)
        self.assertEqual(payload["results"], [])

    def test_global_search_never_leaks_another_users_file(self):
        other = User.objects.create_user(
            username="prosearch2", password=PRO_USER_PASSWORD
        )
        make_cleaned_file(other, "confidentiel.csv")

        payload = self.client.get(
            reverse("core:global_search"), {"q": "confidentiel"}
        ).json()

        self.assertEqual(payload["count"], 0)

    def test_activity_page_lists_entries_and_filters(self):
        activity_service.record(
            self.user, ActivityLog.Action.UPLOAD, "Téléversement de test"
        )
        activity_service.record(self.user, ActivityLog.Action.DELETE, "Suppression")

        response = self.client.get(reverse("core:activity"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="dz-activity-kpi"')
        self.assertContains(response, 'id="dz-action-filter"')
        self.assertEqual(response.context["stats"]["total"], 2)

        filtered = self.client.get(reverse("core:activity"), {"action": "delete"})
        self.assertEqual(filtered.context["selected_action"], "delete")
        self.assertEqual(len(filtered.context["activities"]), 1)
        self.assertEqual(filtered.context["activities"][0].action, "delete")

    def test_activity_page_ignores_an_unknown_action_filter(self):
        activity_service.record(self.user, ActivityLog.Action.UPLOAD, "un")

        response = self.client.get(reverse("core:activity"), {"action": "pirate"})

        self.assertEqual(response.context["selected_action"], "pirate")
        self.assertEqual(len(response.context["activities"]), 1)

    def test_shortcuts_page_exposes_workspace_counts(self):
        api_service.create_token(self.user, "Exemple")

        response = self.client.get(reverse("core:shortcuts"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="dz-shortcuts-kpi"')
        self.assertEqual(response.context["files_count"], 1)
        self.assertEqual(response.context["tokens_count"], 1)


class GlobalSearchServiceTests(TestCase):
    """Recherche globale : sources multiples, accents et pertinence."""

    def setUp(self):
        self.user = User.objects.create_user(username="searchsvc")
        self.client.force_login(self.user)

    def _search(self, query):
        return search_service.search(self.user, query)

    def test_fold_ignores_case_and_accents(self):
        self.assertEqual(search_service.fold("Règles"), "regles")
        self.assertEqual(search_service.fold("ACTIVITÉ"), "activite")

    def test_match_scores_exact_prefix_word_and_substring(self):
        self.assertEqual(search_service.match("Règles", "regles")[0], 100)
        self.assertEqual(search_service.match("Règles de nettoyage", "regles")[0], 85)
        self.assertEqual(search_service.match("Mes règles", "regles")[0], 70)
        self.assertEqual(search_service.match("Mesregles", "regles")[0], 50)
        self.assertEqual(search_service.match("Règles", "absent")[0], 0)

    def test_match_returns_span_in_the_original_text(self):
        score, start, end = search_service.match("Règles de nettoyage", "regles")

        self.assertEqual(score, 85)
        self.assertEqual("Règles de nettoyage"[start:end], "Règles")

    def test_accent_insensitive_query_finds_a_page(self):
        payload = self._search("regles")

        self.assertTrue(
            any(item["label"] == "Règles de nettoyage" for item in payload["results"])
        )

    def test_page_is_found_by_an_english_keyword(self):
        payload = self._search("dashboard")

        self.assertTrue(any(item["type"] == "page" for item in payload["results"]))

    def test_page_found_by_keyword_does_not_highlight_the_label(self):
        payload = self._search("dashboard")
        page = next(item for item in payload["results"] if item["type"] == "page")

        self.assertEqual(page["highlight"], "")

    def test_dataset_is_found_by_a_column_name(self):
        make_cleaned_file(self.user, "clients.csv")

        payload = self._search("telephone")

        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["type"], "dataset")
        self.assertIn("colonne", payload["results"][0]["hint"])

    def test_dataset_found_by_column_does_not_highlight_the_filename(self):
        make_cleaned_file(self.user, "clients.csv")

        payload = self._search("telephone")

        self.assertEqual(payload["results"][0]["highlight"], "")

    def test_dataset_highlight_follows_accents(self):
        make_cleaned_file(self.user, "données_ventes.csv")

        payload = self._search("donnees")

        self.assertEqual(payload["results"][0]["highlight"], "données")

    def test_rule_is_found_by_its_operation(self):
        CleaningRule.objects.create(
            owner=self.user,
            name="Ma règle",
            operation=CleaningRule.Operation.NORMALIZE_EMAILS,
        )

        payload = self._search("emails")

        self.assertTrue(any(item["type"] == "rule" for item in payload["results"]))

    def test_rule_is_found_by_its_target_column(self):
        CleaningRule.objects.create(
            owner=self.user,
            name="Ma règle",
            operation=CleaningRule.Operation.TRIM_WHITESPACE,
            column="ville",
        )

        payload = self._search("ville")

        self.assertTrue(any(item["type"] == "rule" for item in payload["results"]))

    def test_activity_is_found_by_its_message(self):
        activity_service.record(
            self.user, ActivityLog.Action.UPLOAD, "Téléversement du rapport annuel"
        )

        payload = self._search("rapport")

        self.assertTrue(any(item["type"] == "activity" for item in payload["results"]))

    def test_token_is_found_by_its_name(self):
        api_service.create_token(self.user, "Jeton production")

        payload = self._search("production")

        self.assertTrue(any(item["type"] == "token" for item in payload["results"]))

    def test_webhook_is_found_by_its_name_and_url(self):
        Webhook.objects.create(
            owner=self.user,
            name="Alerte Slack",
            url="https://hooks.slack.com/services/xyz",
            event=Webhook.Event.CLEANING_DONE,
        )

        by_name = self._search("slack")
        by_url = self._search("hooks.slack.com")

        self.assertTrue(any(item["type"] == "webhook" for item in by_name["results"]))
        self.assertTrue(any(item["type"] == "webhook" for item in by_url["results"]))

    def test_results_are_sorted_by_relevance(self):
        CleaningRule.objects.create(
            owner=self.user,
            name="Doublons",
            operation=CleaningRule.Operation.REMOVE_DUPLICATES,
        )
        make_cleaned_file(self.user, "doublons_2026.csv")

        payload = self._search("doublons")

        self.assertEqual(payload["results"][0]["label"], "Doublons")
        self.assertEqual(payload["results"][0]["score"], 100)
        scores = [item["score"] for item in payload["results"]]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_each_family_is_capped(self):
        for index in range(search_service.PER_TYPE + 3):
            make_cleaned_file(self.user, f"rapport_{index}.csv")

        payload = self._search("rapport")
        datasets = [item for item in payload["results"] if item["type"] == "dataset"]

        self.assertEqual(len(datasets), search_service.PER_TYPE)

    def test_results_never_exceed_the_global_cap(self):
        for index in range(search_service.MAX_RESULTS + 5):
            make_cleaned_file(self.user, f"mesure_{index}.csv")

        payload = self._search("mesure")

        self.assertLessEqual(payload["count"], search_service.MAX_RESULTS)

    def test_search_never_leaks_another_users_data(self):
        other = User.objects.create_user(username="searchsvc2")
        make_cleaned_file(other, "confidentiel.csv")
        CleaningRule.objects.create(
            owner=other,
            name="Règle confidentielle",
            operation=CleaningRule.Operation.TRIM_WHITESPACE,
        )
        api_service.create_token(other, "Jeton confidentiel")
        Webhook.objects.create(
            owner=other,
            name="Webhook confidentiel",
            url="https://example.com/confidentiel",
            event=Webhook.Event.UPLOAD,
        )
        activity_service.record(other, ActivityLog.Action.UPLOAD, "Confidentiel")

        payload = self._search("confidentiel")

        self.assertEqual(payload["count"], 0)

    def test_blank_query_returns_nothing(self):
        make_cleaned_file(self.user, "clients.csv")

        for query in ("", "   ", None):
            with self.subTest(query=query):
                payload = self._search(query)
                self.assertEqual(payload["count"], 0)
                self.assertEqual(payload["results"], [])

    def test_every_result_exposes_the_palette_contract(self):
        make_cleaned_file(self.user, "clients.csv")

        payload = self._search("clients")

        self.assertTrue(payload["results"])
        for item in payload["results"]:
            with self.subTest(label=item["label"]):
                self.assertEqual(
                    set(item),
                    {
                        "type",
                        "type_label",
                        "icon",
                        "label",
                        "hint",
                        "url",
                        "score",
                        "highlight",
                    },
                )
                self.assertTrue(item["type_label"])
                self.assertTrue(item["url"].startswith("/"))


class ApiAccessTests(TestCase):
    """Intégration : API REST en lecture, authentifiée par jeton porteur."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="proapi", password=PRO_USER_PASSWORD
        )
        self.client.force_login(self.user)
        self.data_file = make_cleaned_file(self.user)
        self.token, self.clear = api_service.create_token(self.user, "Test")
        self.client.logout()

    def test_api_rejects_a_missing_token(self):
        response = self.client.get(reverse("core:api_datasets"))
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "invalid_token")
        self.assertEqual(response["WWW-Authenticate"], "Bearer")

    def test_api_rejects_an_unknown_token(self):
        response = self.client.get(
            reverse("core:api_datasets"),
            HTTP_AUTHORIZATION="Bearer dz_00000000_inconnu",
        )
        self.assertEqual(response.status_code, 401)

    def test_api_accepts_a_bearer_token_and_counts_calls(self):
        response = self.client.get(
            reverse("core:api_datasets"),
            HTTP_AUTHORIZATION=f"Bearer {self.clear}",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertTrue(payload["results"][0]["urls"]["detail"])

        self.token.refresh_from_db()
        self.assertEqual(self.token.call_count, 1)
        self.assertIsNotNone(self.token.last_used_at)
        self.assertTrue(
            ActivityLog.objects.filter(
                owner=self.user, action=ActivityLog.Action.API
            ).exists()
        )

    def test_api_rejects_a_token_in_the_query_string(self):
        """Un jeton en URL fuite dans les journaux : il n'est plus accepté."""
        response = self.client.get(
            f"{reverse('core:api_datasets')}?token={self.clear}"
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response["WWW-Authenticate"], "Bearer")

    def test_api_rejects_a_revoked_token(self):
        api_service.revoke_token(self.token)

        response = self.client.get(
            reverse("core:api_datasets"),
            HTTP_AUTHORIZATION=f"Bearer {self.clear}",
        )

        self.assertEqual(response.status_code, 401)

    def test_api_rejects_an_expired_token(self):
        self.token.expires_at = timezone.now() - timedelta(minutes=1)
        self.token.save(update_fields=["expires_at"])

        response = self.client.get(
            reverse("core:api_datasets"),
            HTTP_AUTHORIZATION=f"Bearer {self.clear}",
        )

        self.assertEqual(response.status_code, 401)

    def authorization(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.clear}"}

    def test_api_index_describes_the_endpoints(self):
        response = self.client.get(reverse("core:api_index"), **self.authorization())
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["application"], "DataZen")
        self.assertEqual(payload["user"], "proapi")
        self.assertEqual(
            set(payload["endpoints"]),
            {"datasets", "dataset", "stats", "changelog", "download"},
        )

    def test_api_stats_returns_account_aggregates(self):
        response = self.client.get(reverse("core:api_stats"), **self.authorization())
        payload = response.json()
        self.assertEqual(payload["files"], 1)
        self.assertGreaterEqual(payload["rows"], 1)
        self.assertIsNotNone(payload["average_score"])

    def test_api_dataset_detail_returns_metrics_and_changelog(self):
        response = self.client.get(
            reverse("core:api_dataset_detail", args=[self.data_file.pk]),
            **self.authorization(),
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["name"], "clients.csv")
        self.assertEqual(payload["status"], DataFile.Status.CLEANED)
        self.assertIn("change_log", payload)
        self.assertTrue(payload["metrics"])
        self.assertFalse(payload["archived"])

    def test_api_changelog_returns_the_traced_rows(self):
        response = self.client.get(
            reverse("core:api_dataset_changelog", args=[self.data_file.pk]),
            **self.authorization(),
        )
        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["dataset"], "clients.csv")
        self.assertGreaterEqual(payload["count"], 1)

    def test_api_dataset_download_returns_json_records(self):
        response = self.client.get(
            reverse("core:api_dataset_download", args=[self.data_file.pk]),
            **self.authorization(),
        )
        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(payload["count"], 1)
        self.assertIn("email", payload["results"][0])

    def test_api_dataset_download_reports_missing_cleaned_data(self):
        data_file = DataFile.objects.create(
            owner=self.user, file=make_upload(), original_name="brut.csv"
        )
        response = self.client.get(
            reverse("core:api_dataset_download", args=[data_file.pk]),
            **self.authorization(),
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "no_cleaned_data")

    def test_api_never_exposes_another_users_dataset(self):
        other = User.objects.create_user(
            username="proapi2", password=PRO_USER_PASSWORD
        )
        secret = make_cleaned_file(other, "secret.csv")

        for name in (
            "core:api_dataset_detail",
            "core:api_dataset_changelog",
            "core:api_dataset_download",
        ):
            with self.subTest(name=name):
                response = self.client.get(
                    reverse(name, args=[secret.pk]), **self.authorization()
                )
                self.assertEqual(response.status_code, 404)

        listing = self.client.get(
            reverse("core:api_datasets"), **self.authorization()
        ).json()
        self.assertEqual(listing["count"], 1)


class ApiTokenManagementTests(TestCase):
    """Intégration : jetons d'API créés et révoqués depuis l'interface."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="protoken", password=PRO_USER_PASSWORD
        )
        self.client.force_login(self.user)

    def test_token_creation_reveals_the_secret_once(self):
        response = self.client.post(
            reverse("core:api_tokens"), {"name": "Intégration Power BI"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="dz-api-kpi"')
        clear = response.context["new_token"]["clear"]
        self.assertTrue(clear.startswith("dz_"))

        token = ApiToken.objects.get(owner=self.user, name="Intégration Power BI")
        self.assertNotIn(clear, token.key_hash)
        self.assertEqual(api_service.resolve_token(clear), token)
        self.assertTrue(
            ActivityLog.objects.filter(
                owner=self.user, action=ActivityLog.Action.TOKEN_CREATE
            ).exists()
        )

    def test_token_revocation_disables_the_token(self):
        token, clear = api_service.create_token(self.user, "CI")

        response = self.client.post(
            reverse("core:api_token_revoke", args=[token.pk])
        )

        self.assertRedirects(response, reverse("core:api_tokens"))
        token.refresh_from_db()
        self.assertFalse(token.is_active)
        self.assertIsNone(api_service.resolve_token(clear))
        self.assertTrue(
            ActivityLog.objects.filter(
                owner=self.user, action=ActivityLog.Action.TOKEN_REVOKE
            ).exists()
        )

    def test_token_revocation_is_denied_for_another_user(self):
        other = User.objects.create_user(
            username="protoken2", password=PRO_USER_PASSWORD
        )
        token, _ = api_service.create_token(other, "Autre")

        response = self.client.post(
            reverse("core:api_token_revoke", args=[token.pk])
        )

        self.assertRedirects(response, reverse("core:api_tokens"))
        token.refresh_from_db()
        self.assertTrue(token.is_active)


class WebhookTests(TestCase):
    """Intégration : notifications sortantes (webhooks)."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="prohook", password=PRO_USER_PASSWORD
        )
        self.client.force_login(self.user)
        self.hook = Webhook.objects.create(
            owner=self.user,
            name="Slack",
            url="https://hooks.exemple.test/datazen",
            event=Webhook.Event.CLEANING_DONE,
        )

    def test_webhook_page_exposes_the_subscriptions(self):
        response = self.client.get(reverse("core:webhooks"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="dz-hook-kpi"')
        self.assertEqual(response.context["stats"]["total"], 1)

    def test_webhook_creation_generates_a_signature_secret(self):
        response = self.client.post(
            reverse("core:webhooks"),
            {
                "name": "CRM",
                "url": "https://crm.exemple.test/hook",
                "event": Webhook.Event.UPLOAD,
                "is_active": "on",
            },
        )
        self.assertRedirects(response, reverse("core:webhooks"))
        hook = Webhook.objects.get(name="CRM")
        self.assertEqual(hook.owner, self.user)
        self.assertTrue(hook.is_active)
        self.assertTrue(hook.secret)

    def test_webhook_toggle_switches_the_state(self):
        response = self.client.post(
            reverse("core:webhook_toggle", args=[self.hook.pk])
        )
        self.assertRedirects(response, reverse("core:webhooks"))
        self.hook.refresh_from_db()
        self.assertFalse(self.hook.is_active)

    def test_webhook_deletion_removes_the_subscription(self):
        response = self.client.post(
            reverse("core:webhook_delete", args=[self.hook.pk])
        )
        self.assertRedirects(response, reverse("core:webhooks"))
        self.assertFalse(Webhook.objects.filter(pk=self.hook.pk).exists())

    def test_webhook_test_records_the_http_status(self):
        with mock.patch.object(api_service, "_post", return_value=200):
            response = self.client.post(
                reverse("core:webhook_test", args=[self.hook.pk])
            )
        self.assertRedirects(response, reverse("core:webhooks"))
        self.hook.refresh_from_db()
        self.assertEqual(self.hook.last_status, 200)
        self.assertIsNotNone(self.hook.last_triggered_at)

    def test_webhook_test_records_a_failure(self):
        with mock.patch.object(api_service, "_post", return_value=503):
            self.client.post(reverse("core:webhook_test", args=[self.hook.pk]))
        self.hook.refresh_from_db()
        self.assertEqual(self.hook.last_status, 503)

    def test_webhook_actions_are_denied_for_another_user(self):
        other = User.objects.create_user(
            username="prohook2", password=PRO_USER_PASSWORD
        )
        self.client.force_login(other)

        self.client.post(reverse("core:webhook_delete", args=[self.hook.pk]))
        self.client.post(reverse("core:webhook_toggle", args=[self.hook.pk]))

        self.assertTrue(Webhook.objects.filter(pk=self.hook.pk).exists())
        self.hook.refresh_from_db()
        self.assertTrue(self.hook.is_active)

    def test_trigger_only_queues_the_subscribed_event(self):
        Webhook.objects.create(
            owner=self.user,
            name="Erreur",
            url="https://hooks.exemple.test/erreur",
            event=Webhook.Event.CLEANING_ERROR,
        )

        with mock.patch("core.services.api.threading") as fake_threading:
            count = api_service.trigger(self.user, Webhook.Event.CLEANING_DONE)

        self.assertEqual(count, 1)
        fake_threading.Thread.assert_called_once()
        fake_threading.Thread.return_value.start.assert_called_once()

    def test_webhook_stats_count_active_and_failing_hooks(self):
        self.hook.last_status = 503
        self.hook.save(update_fields=["last_status"])

        stats = api_service.webhook_stats(self.user)

        self.assertEqual(stats, {"total": 1, "active": 1, "failing": 1})


class RetentionTests(TestCase):
    """Rétention : archivage automatique et purge explicite des fichiers."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="proretention", password=PRO_USER_PASSWORD
        )
        self.client.force_login(self.user)
        self.data_file = make_cleaned_file(self.user)
        self.profile = self.user.profile
        self.profile.retention_days = 30
        self.profile.save(update_fields=["retention_days"])

    def backdate(self, days=40, **extra):
        """Vieillit artificiellement le fichier nettoyé (les tests ne dorment pas)."""
        moment = timezone.now() - timedelta(days=days)
        values = {"cleaned_at": moment, "updated_at": moment}
        values.update(extra)
        DataFile.objects.filter(pk=self.data_file.pk).update(**values)
        self.data_file.refresh_from_db()

    def test_expired_files_detects_a_backdated_file(self):
        self.backdate()
        self.assertIn(self.data_file, retention_service.expired_files(self.user))

    def test_recent_file_is_not_expired(self):
        self.backdate(days=1)
        self.assertNotIn(self.data_file, retention_service.expired_files(self.user))

    def test_unlimited_retention_disables_expiry(self):
        self.profile.retention_days = 0
        self.profile.save(update_fields=["retention_days"])
        self.backdate()

        self.assertEqual(retention_service.retention_days(self.user), 0)
        self.assertFalse(retention_service.expired_files(self.user).exists())

    def test_exempted_file_is_never_expired(self):
        self.backdate(archive_exempt_from_auto=True)
        self.assertFalse(retention_service.expired_files(self.user).exists())

    def test_retention_page_lists_expired_files(self):
        self.backdate()

        response = self.client.get(reverse("core:retention"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="dz-retention-kpi"')
        self.assertContains(response, "clients.csv")
        self.assertEqual(response.context["expired_count"], 1)
        self.assertEqual(response.context["days"], 30)

    def test_retention_purge_deletes_expired_files(self):
        self.backdate()
        pk = self.data_file.pk

        response = self.client.post(reverse("core:retention_purge"))

        self.assertRedirects(response, reverse("core:retention"))
        self.assertFalse(DataFile.objects.filter(pk=pk).exists())
        self.assertTrue(
            ActivityLog.objects.filter(
                owner=self.user, action=ActivityLog.Action.DELETE
            ).exists()
        )

    def test_retention_purge_keeps_a_recent_file(self):
        response = self.client.post(reverse("core:retention_purge"))

        self.assertRedirects(response, reverse("core:retention"))
        self.assertTrue(DataFile.objects.filter(pk=self.data_file.pk).exists())

    def test_activity_cleanup_view_purges_old_entries(self):
        entry = activity_service.record(
            self.user, ActivityLog.Action.UPLOAD, "Ancienne entrée"
        )
        ActivityLog.objects.filter(pk=entry.pk).update(
            created_at=timezone.now() - timedelta(days=400)
        )
        activity_service.record(self.user, ActivityLog.Action.CLEAN, "Récente")

        response = self.client.post(reverse("core:retention_cleanup_activity"))

        self.assertRedirects(response, reverse("core:activity"))
        self.assertFalse(ActivityLog.objects.filter(pk=entry.pk).exists())
        self.assertEqual(ActivityLog.objects.filter(owner=self.user).count(), 1)

    def test_auto_archive_flags_a_file_older_than_the_archive_delay(self):
        self.backdate()

        views._auto_archive(self.user)

        self.data_file.refresh_from_db()
        self.assertIsNotNone(self.data_file.archived_at)

    def test_index_applies_the_retention_policy_when_enabled(self):
        self.profile.auto_purge = True
        self.profile.save(update_fields=["auto_purge"])
        self.backdate()
        pk = self.data_file.pk

        response = self.client.get(reverse("core:index"))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(DataFile.objects.filter(pk=pk).exists())


class ActivityJournalTests(TestCase):
    """Chaque action métier laisse une trace horodatée dans le journal."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="projournal", password=PRO_USER_PASSWORD
        )
        self.client.force_login(self.user)

    def actions(self):
        return list(
            ActivityLog.objects.filter(owner=self.user).values_list(
                "action", flat=True
            )
        )

    def test_upload_records_an_activity(self):
        response = self.client.post(reverse("core:index"), {"file": make_upload()})
        self.assertEqual(response.status_code, 302)
        self.assertIn(ActivityLog.Action.UPLOAD, self.actions())

    def test_cleaning_launch_records_an_activity(self):
        data_file = DataFile.objects.create(
            owner=self.user, file=make_upload(), original_name="clients.csv"
        )
        with mock.patch.object(views, "start_cleaning", lambda *a, **k: None):
            response = self.client.post(
                reverse("core:dataset_detail", args=[data_file.pk]),
                {"trim_whitespace": "on"},
            )
        self.assertEqual(response.status_code, 302)
        self.assertIn(ActivityLog.Action.CLEAN, self.actions())

    def test_download_records_an_activity(self):
        data_file = make_cleaned_file(self.user)

        response = self.client.get(
            reverse("core:download_cleaned", args=[data_file.pk])
        )
        b"".join(response.streaming_content)
        response.close()

        self.assertEqual(response.status_code, 200)
        self.assertIn(ActivityLog.Action.DOWNLOAD, self.actions())

    def test_archive_and_restore_record_activities(self):
        data_file = make_cleaned_file(self.user)

        self.client.post(reverse("core:archive_dataset", args=[data_file.pk]))
        data_file.refresh_from_db()
        self.assertIsNotNone(data_file.archived_at)

        self.client.post(reverse("core:restore_dataset", args=[data_file.pk]))
        data_file.refresh_from_db()
        self.assertIsNone(data_file.archived_at)

        actions = self.actions()
        self.assertIn(ActivityLog.Action.ARCHIVE, actions)
        self.assertIn(ActivityLog.Action.RESTORE, actions)

    def test_deletion_records_an_activity(self):
        data_file = make_cleaned_file(self.user)

        self.client.post(reverse("core:delete_dataset", args=[data_file.pk]))

        self.assertFalse(DataFile.objects.filter(pk=data_file.pk).exists())
        self.assertIn(ActivityLog.Action.DELETE, self.actions())

    def test_rule_creation_and_deletion_record_activities(self):
        response = self.client.post(
            reverse("core:rules_list"),
            {
                "name": "Espaces superflus",
                "operation": CleaningRule.Operation.TRIM_WHITESPACE,
                "column": "",
                "value": "",
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        rule = CleaningRule.objects.get(name="Espaces superflus")

        self.client.post(reverse("core:rule_delete", args=[rule.pk]))

        actions = self.actions()
        self.assertIn(ActivityLog.Action.RULE_CREATE, actions)
        self.assertIn(ActivityLog.Action.RULE_DELETE, actions)


class JsUiStringsTests(TestCase):
    """Les libellés générés par main.js passent par les attributs data-dz-msg-*.

    Le JavaScript n'est pas analysé par tools/i18n_build.py : les chaînes sont
    donc publiées par base.html et lues par la fonction dzMsg() de main.js.
    """

    EXPECTED_FR = {
        "dz-msg-show": "Afficher",
        "dz-msg-hide": "Masquer",
        "dz-msg-show-password": "Afficher le mot de passe",
        "dz-msg-hide-password": "Masquer le mot de passe",
        "dz-msg-theme-light": "Activer le thème clair",
        "dz-msg-theme-dark": "Activer le thème sombre",
        "dz-msg-filter-rows": "🔍 Filtrer les lignes…",
        "dz-msg-filter-rows-label": "Filtrer les lignes du tableau",
        "dz-msg-sort-hint": "Cliquer pour trier",
        "dz-msg-copied": "✓ Copié",
    }

    def render(self, language):
        session = self.client.session
        session["django_language"] = language
        session.save()
        return self.client.get(reverse("core:login")).content.decode("utf-8")

    def test_french_labels_are_exposed_on_the_body_element(self):
        html = self.render("fr")

        for attribute, value in self.EXPECTED_FR.items():
            self.assertIn(f'{attribute}="{value}"', html)

    def test_english_labels_replace_the_french_ones(self):
        html = self.render("en")

        self.assertIn('dz-msg-theme-dark="Switch to dark theme"', html)
        self.assertIn('dz-msg-sort-hint="Click to sort"', html)
        self.assertIn('dz-msg-copied="✓ Copied"', html)
        self.assertIn('dz-msg-filter-rows-label="Filter table rows"', html)
        self.assertNotIn("Cliquer pour trier", html)

    def test_every_language_translates_the_labels(self):
        french_values = set(self.EXPECTED_FR.values())

        for code in ("es", "de", "it", "ja", "ar", "zh-hans"):
            html = self.render(code)
            for attribute in self.EXPECTED_FR:
                match = re.search(rf'{attribute}="([^"]*)"', html)
                self.assertIsNotNone(match, f"{attribute} absent en {code}")
                self.assertNotIn(
                    match.group(1),
                    french_values,
                    f"{attribute} non traduit en {code}",
                )

    def test_main_js_delegates_to_the_exposed_labels(self):
        source = (
            Path(__file__).resolve().parent.parent / "static" / "js" / "main.js"
        ).read_text(encoding="utf-8")

        self.assertIn("function dzMsg(", source)
        # Les littéraux français subsistent comme repli, mais uniquement en
        # second argument de dzMsg() : plus aucune affectation directe.
        for literal in (
            '"Cliquer pour trier"',
            '"🔍 Filtrer les lignes…"',
            '"Filtrer les lignes du tableau"',
            '"Activer le thème clair"',
            '"Activer le thème sombre"',
        ):
            for line in source.splitlines():
                if literal in line:
                    self.assertIn(
                        "dzMsg(",
                        line,
                        f"{literal} n'est pas lu via dzMsg()",
                    )


class ContextTranslationTests(TestCase):
    """Les libellés contextuels (msgctxt) sont résolus par pgettext.

    tools/i18n_build.py écrit les entrées contextuelles sous la clé
    "contexte\x04msgid" du .mo : sans cela, {% translate "ou" context
    "séparateur" %} resterait en français dans les 22 autres langues.
    """

    MSGID = "ou"
    CONTEXT = "séparateur"
    TRANSLATIONS = {
        "en": "or",
        "es": "o",
        "de": "oder",
        "it": "o",
        "ja": "または",
        "ar": "أو",
        "zh-hans": "或",
    }

    DIVIDER = '<div class="dz-auth-divider">%s</div>'

    def render(self, view_name, language):
        session = self.client.session
        session["django_language"] = language
        session.save()
        return self.client.get(reverse(view_name)).content.decode("utf-8")

    def test_separator_is_translated_on_every_auth_page(self):
        for view_name in ("core:login", "core:signup", "core:password_reset"):
            for code, expected in self.TRANSLATIONS.items():
                html = self.render(view_name, code)
                self.assertIn(
                    self.DIVIDER % expected,
                    html,
                    f"separateur non traduit en {code} sur {view_name}",
                )

    def test_french_keeps_the_source_string(self):
        html = self.render("core:login", "fr")

        self.assertIn(self.DIVIDER % self.MSGID, html)

    def test_catalog_exposes_the_contextual_key(self):
        from django.utils.translation import override

        from tools.translations.separators import CONTEXT, MSGID, SEPARATOR_TRANSLATIONS

        self.assertEqual(CONTEXT, self.CONTEXT)
        self.assertEqual(MSGID, self.MSGID)

        for code, expected in self.TRANSLATIONS.items():
            key = f"{self.CONTEXT}\x04{self.MSGID}"
            self.assertEqual(SEPARATOR_TRANSLATIONS[code][key], expected)
            with override(code):
                self.assertEqual(pgettext(self.CONTEXT, self.MSGID), expected)

    def test_po_catalog_declares_the_context(self):
        root = Path(__file__).resolve().parent.parent / "locale"

        for code in self.TRANSLATIONS:
            folder = code.replace("-", "_")
            source = (root / folder / "LC_MESSAGES" / "django.po").read_text(
                encoding="utf-8"
            )
            self.assertIn(f'msgctxt "{self.CONTEXT}"', source)
            self.assertNotIn('msgid_plural "ou"', source)


class NavbarDesignTests(TestCase):
    """La barre de navigation adopte un verre teinté « premium ».

    Le rendu est purement CSS : les tests verrouillent les variables et les
    règles clés pour éviter une régression silencieuse du design.
    """

    def setUp(self):
        self.root = Path(__file__).resolve().parent.parent / "static"
        self.css = (self.root / "css" / "style.css").read_text(encoding="utf-8")

    def test_navbar_uses_the_tinted_glass_variables(self):
        self.assertIn("--dz-navbar-bg:", self.css)
        self.assertIn("--dz-navbar-bg-scrolled:", self.css)
        self.assertIn("--dz-navbar-sheen:", self.css)
        self.assertIn("--dz-navbar-hairline:", self.css)
        self.assertIn("--dz-navbar-shadow:", self.css)

        block = self.css[self.css.index(".dz-navbar {") : self.css.index(".dz-navbar.is-scrolled")]
        self.assertIn("background-color: var(--dz-navbar-bg)", block)
        self.assertIn("background-image: var(--dz-navbar-sheen)", block)
        self.assertIn("backdrop-filter: saturate(180%) blur(16px)", block)

    def test_navbar_is_more_opaque_than_before(self):
        self.assertIn("--dz-navbar-bg: rgba(255, 255, 255, 0.90)", self.css)
        self.assertIn("--dz-navbar-bg-scrolled: rgba(255, 255, 255, 0.97)", self.css)
        self.assertIn("--dz-navbar-bg: rgba(13, 15, 20, 0.90)", self.css)
        self.assertIn("--dz-navbar-bg-scrolled: rgba(13, 15, 20, 0.97)", self.css)

    def test_navbar_has_a_gradient_hairline_and_coloured_shadow(self):
        self.assertIn(".dz-navbar::after", self.css)
        self.assertIn("background: var(--dz-navbar-hairline)", self.css)
        self.assertIn("box-shadow: var(--dz-navbar-shadow)", self.css)

    def test_nav_links_get_a_gradient_underline(self):
        self.assertIn(".dz-navbar .nav-link:not(.dropdown-toggle)::after", self.css)
        self.assertIn("background: var(--dz-gradient)", self.css)
        self.assertIn("transform: scaleX(0)", self.css)
        self.assertIn("transform: scaleX(1)", self.css)

    def test_dark_theme_lightens_the_active_link(self):
        self.assertIn('[data-bs-theme="dark"] .dz-navbar .nav-link.active', self.css)
        self.assertIn("color: #a5b4fc", self.css)

    def test_mobile_panel_reuses_the_navbar_sheen(self):
        mobile = self.css[self.css.index("17.2 Barre de navigation") :]
        self.assertIn("background-color: var(--dz-navbar-bg-scrolled)", mobile)
        self.assertIn("background-image: var(--dz-navbar-sheen)", mobile)
        self.assertIn(".dz-navbar .nav-link::after", mobile)

    def test_horizontal_overflow_guard_keeps_sticky_working(self):
        # `overflow-x: hidden` sur <body> crée un conteneur de défilement qui
        # annule le `position: sticky` de la barre : on bascule sur `clip`.
        self.assertIn("@supports (overflow-x: clip)", self.css)
        guard = self.css[self.css.index("17.1 Garde-fous généraux") :]
        self.assertIn("overflow-x: clip", guard)
        # La barre ne doit pas redéfinir `position`, sinon `.sticky-top` saute.
        block = self.css[
            self.css.index(".dz-navbar {") : self.css.index("/* Liseré dégradé")
        ]
        self.assertNotIn("position:", block)


class LogoAssetTests(TestCase):
    """Le logo de marque est une image dérivée du fichier source fourni.

    `tools/make_logo_asset.py` détoure le PNG d'origine (fond blanc) et produit
    deux variantes : la version d'origine et une version éclaircie pour le
    thème sombre. Les tests verrouillent les fichiers et leur branchement.
    """

    LIGHT = "img/logo-datazen.png"
    DARK = "img/logo-datazen-dark.png"

    def setUp(self):
        self.root = Path(__file__).resolve().parent.parent / "static"
        self.css = (self.root / "css" / "style.css").read_text(encoding="utf-8")
        self.user = User.objects.create_user(username="logoviewer")
        self.client.force_login(self.user)

    def test_logo_assets_exist_and_are_transparent_pngs(self):
        for relative in (self.LIGHT, self.DARK):
            asset = self.root / relative
            self.assertTrue(asset.is_file(), f"{relative} manquant")
            self.assertGreater(asset.stat().st_size, 1024, f"{relative} tronqué")
            # Signature PNG puis chunk IHDR : couleur 6 = RGBA.
            head = asset.read_bytes()[:26]
            self.assertEqual(head[:8], b"\x89PNG\r\n\x1a\n")
            self.assertEqual(head[25], 6, f"{relative} doit être en RGBA")

    def test_navbar_and_footer_render_the_logo_image(self):
        response = self.client.get(reverse("core:index"))
        self.assertContains(response, "img/logo-datazen.png")
        self.assertContains(response, "img/logo-datazen-dark.png")
        self.assertContains(response, 'class="dz-logo-img dz-logo-img--light"')
        self.assertContains(response, 'class="dz-logo-img dz-logo-img--dark"')
        # L'ancienne pastille emoji ne doit plus apparaître.
        self.assertNotContains(response, "dz-logo-mark")

    def test_dark_variant_is_swapped_by_the_theme(self):
        self.assertIn(".dz-logo-img--dark {\n    display: none;", self.css)
        self.assertIn('[data-bs-theme="dark"] .dz-logo-img--light', self.css)
        self.assertIn('[data-bs-theme="dark"] .dz-logo-img--dark', self.css)

    def test_logo_keeps_the_brand_hover_lift(self):
        self.assertIn(".dz-navbar .navbar-brand:hover .dz-logo-img", self.css)
        self.assertIn("transform: translateY(-1px) scale(1.03)", self.css)


class FaviconTests(TestCase):
    """L'onglet du navigateur porte la marque DataZen.

    `tools/make_favicon.py` isole le glyphe gauche du logo et produit un .ico
    multi-tailles plus une icône Apple. Les tests verrouillent les fichiers,
    leur branchement dans le gabarit et la route /favicon.ico.
    """

    ICO = "img/favicon.ico"
    APPLE = "img/favicon-180.png"

    def setUp(self):
        self.root = Path(__file__).resolve().parent.parent / "static"
        self.user = User.objects.create_user(username="faviconviewer")
        self.client.force_login(self.user)

    def test_favicon_assets_exist(self):
        ico = self.root / self.ICO
        apple = self.root / self.APPLE
        self.assertTrue(ico.is_file(), f"{self.ICO} manquant")
        self.assertTrue(apple.is_file(), f"{self.APPLE} manquant")
        self.assertGreater(ico.stat().st_size, 1024, f"{self.ICO} tronqué")
        self.assertGreater(apple.stat().st_size, 1024, f"{self.APPLE} tronqué")
        # Signature ICO : 0x00 0x00 0x01 0x00 puis le nombre d'images.
        head = ico.read_bytes()[:6]
        self.assertEqual(head[:4], b"\x00\x00\x01\x00")
        self.assertGreaterEqual(int.from_bytes(head[4:6], "little"), 4)
        # L'icône Apple est un PNG carré de 180 px.
        self.assertEqual(apple.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(apple.read_bytes()[16:24], (180).to_bytes(4, "big") * 2)

    def test_base_template_declares_the_icons(self):
        response = self.client.get(reverse("core:index"))
        self.assertContains(response, 'rel="icon"')
        self.assertContains(response, "img/favicon.ico")
        self.assertContains(response, 'rel="apple-touch-icon"')
        self.assertContains(response, "img/favicon-180.png")

    def test_favicon_route_redirects_to_the_static_icon(self):
        response = self.client.get("/favicon.ico")
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], "/static/img/favicon.ico")


class DesignSystemTests(TestCase):
    """Le design system reprend les rayons, le rythme et les ombres du modèle.

    Le rendu est purement CSS : les tests verrouillent les jetons et les règles
    clés pour éviter une régression silencieuse de la refonte.
    """

    def setUp(self):
        self.root = Path(__file__).resolve().parent.parent / "static"
        self.css = (self.root / "css" / "style.css").read_text(encoding="utf-8")
        self.user = User.objects.create_user(username="designviewer")
        self.client.force_login(self.user)

    def test_radius_scale_is_generous(self):
        self.assertIn("--dz-radius-sm: 0.625rem;", self.css)
        self.assertIn("--dz-radius: 1rem;", self.css)
        self.assertIn("--dz-radius-lg: 1.5rem;", self.css)
        self.assertIn("--dz-radius-xl: 2rem;", self.css)
        self.assertIn("--dz-radius-2xl: 2.5rem;", self.css)
        # Bootstrap doit suivre la même échelle, sinon les composants natifs
        # (modales, menus, alertes) jurent avec les cartes maison.
        self.assertIn("--bs-border-radius: 1rem;", self.css)
        self.assertIn("--bs-border-radius-lg: 1.5rem;", self.css)

    def test_shadows_use_two_layers(self):
        # Une ombre de contact nette + un halo large, plutôt qu'une ombre unique.
        for token in ("--dz-shadow-sm:", "--dz-shadow:", "--dz-shadow-lg:"):
            start = self.css.index(token)
            block = self.css[start : self.css.index(";", start)]
            self.assertEqual(
                block.count("rgba("), 2, f"{token} doit superposer deux ombres"
            )
        self.assertIn("--dz-ring:", self.css)

    def test_vertical_rhythm_tokens_exist(self):
        self.assertIn("--dz-section-gap: clamp(", self.css)
        self.assertIn("--dz-section-gap-sm: clamp(", self.css)
        self.assertIn(".dz-section {", self.css)
        self.assertIn("margin-bottom: var(--dz-section-gap);", self.css)
        self.assertIn(".dz-section-head {", self.css)
        self.assertIn("margin-bottom: var(--dz-section-gap-sm);", self.css)

    def test_hero_is_taller_and_its_title_larger(self):
        hero = self.css[self.css.index(".dz-hero {") : self.css.index(".dz-hero::before")]
        self.assertIn("clamp(4rem, 2.5rem + 7vw, 7.5rem)", hero)
        h1 = self.css[self.css.index(".dz-hero h1 {") : self.css.index(".dz-hero .dz-hero-lead")]
        self.assertIn("clamp(2.4rem, 1.4rem + 4.2vw, 4.25rem)", h1)
        self.assertIn("letter-spacing: -0.035em", h1)

    def test_section_titles_scale_up(self):
        title = self.css[
            self.css.index(".dz-section-title {") : self.css.index(".dz-section-subtitle {")
        ]
        self.assertIn("clamp(1.75rem, 1.3rem + 1.8vw, 2.75rem)", title)
        self.assertIn("font-weight: 800", title)

    def test_cards_and_features_are_roomier(self):
        feature = self.css[
            self.css.index(".dz-feature {") : self.css.index(".dz-feature:hover")
        ]
        self.assertIn("padding: 2.25rem 1.75rem", feature)
        self.assertIn("border-radius: var(--dz-radius-lg)", feature)
        icon = self.css[
            self.css.index(".dz-feature .dz-feature-icon {") : self.css.index(".dz-feature h5")
        ]
        self.assertIn("width: 3.75rem", icon)
        self.assertIn("height: 3.75rem", icon)

    def test_wide_panel_variant_exists(self):
        self.assertIn(".dz-panel-xl {", self.css)
        block = self.css[self.css.index(".dz-panel-xl {") :]
        self.assertIn("border-radius: var(--dz-radius-xl)", block[:200])
        self.assertIn("box-shadow: var(--dz-shadow)", block[:200])

    def test_dark_theme_overrides_the_new_shadows(self):
        dark = self.css[self.css.index('[data-bs-theme="dark"] {') :]
        self.assertIn("--dz-ring: 0 0 0 1px rgba(255, 255, 255, 0.06);", dark[:4000])

    def test_landing_page_uses_the_section_rhythm(self):
        response = self.client.get(reverse("core:index"))
        self.assertContains(response, "dz-section-head")
        self.assertContains(response, "dz-section")
        self.assertContains(response, "dz-panel-xl")

    def test_stylesheet_cache_buster_was_bumped(self):
        base = (
            Path(__file__).resolve().parent.parent / "templates" / "core" / "base.html"
        ).read_text(encoding="utf-8")
        self.assertIn("css/style.css' %}?v=20261018-auth", base)

    def test_inner_pages_use_the_section_rhythm(self):
        # Les gabarits applicatifs troquent l'espacement serré de Bootstrap
        # contre le rythme aéré du modèle.
        for name in ("dashboard", "rules_list", "activity", "retention", "profile"):
            response = self.client.get(reverse(f"core:{name}"))
            self.assertEqual(response.status_code, 200, name)
            html = response.content.decode()
            self.assertIn("dz-page", html, name)
            self.assertNotIn("container py-4", html, name)

    def test_rhythm_helpers_are_defined(self):
        for selector in (".dz-page {", ".dz-page-head {", ".dz-block {", ".dz-grid {"):
            self.assertIn(selector, self.css, selector)
        block = self.css[self.css.index(".dz-block {") : self.css.index(".dz-grid {")]
        self.assertIn("margin-bottom: var(--dz-section-gap-sm);", block)
        self.assertIn(".dz-block:last-child", block)

    def test_design_sources_stay_out_of_the_served_tree(self):
        # Les intrants de build et la maquette de référence ne doivent pas être
        # exposés publiquement : ils vivent dans design/, pas dans static/.
        root = Path(__file__).resolve().parent.parent
        self.assertTrue((root / "design" / "logo-source.png").is_file())
        self.assertTrue((root / "design" / "mockup-reference.jpg").is_file())
        served = root / "static" / "img"
        for name in ("logo-source.png", "mockup-reference.jpg"):
            self.assertFalse((served / name).exists(), f"{name} ne doit pas être servi")
        # Chaque fichier de static/img doit être référencé quelque part.
        sources = []
        for pattern in ("templates/**/*.html", "static/css/*.css", "static/js/*.js"):
            for path in root.glob(pattern):
                sources.append(path.read_text(encoding="utf-8"))
        blob = "\n".join(sources)
        for asset in sorted(served.iterdir()):
            self.assertIn(asset.name, blob, f"{asset.name} n'est référencé nulle part")


class HeroVideoTests(TestCase):
    """La page d'accueil illustre son héros avec une vidéo de fond décorative.

    Les fichiers sont produits par tools/generate_hero_video.py : les tests
    vérifient qu'ils sont présents, lisibles et correctement branchés.
    """

    WEBM = "video/hero.webm"
    MP4 = "video/hero.mp4"
    POSTER = "img/hero-poster.jpg"

    def setUp(self):
        self.root = Path(__file__).resolve().parent.parent / "static"
        self.user = User.objects.create_user(
            username="heroviewer", password="MotDePasse!2026"
        )
        self.client.force_login(self.user)

    def test_video_and_poster_assets_exist(self):
        for relative in (self.WEBM, self.MP4, self.POSTER):
            asset = self.root / relative
            self.assertTrue(asset.is_file(), f"{relative} manquant")
            self.assertGreater(
                asset.stat().st_size, 1024, f"{relative} est vide ou tronqué"
            )

    def test_mp4_starts_with_an_iso_base_media_box(self):
        head = (self.root / self.MP4).read_bytes()[:12]

        self.assertEqual(head[4:8], b"ftyp")
        self.assertIn(head[8:12], (b"isom", b"mp42", b"avc1"))

    def test_poster_is_a_jpeg(self):
        head = (self.root / self.POSTER).read_bytes()[:3]

        self.assertEqual(head, b"\xff\xd8\xff")

    def test_home_page_embeds_the_decorative_video(self):
        html = self.client.get(reverse("core:index")).content.decode("utf-8")

        self.assertIn("dz-hero-video", html)
        self.assertIn("<video", html)
        self.assertIn('poster="/static/img/hero-poster.jpg"', html)
        for attribute in ("muted", "loop", "playsinline", "autoplay"):
            self.assertIn(attribute, html)
        self.assertIn('/static/video/hero.webm', html)
        self.assertIn('/static/video/hero.mp4', html)

    def test_video_is_hidden_from_assistive_technologies(self):
        html = self.client.get(reverse("core:index")).content.decode("utf-8")
        block = html[html.index("dz-hero-video") : html.index("dz-hero-lead")]

        self.assertIn('aria-hidden="true"', block)
        self.assertIn('tabindex="-1"', block)

    def test_stylesheet_ships_the_hero_video_rules(self):
        css = (self.root / "css" / "style.css").read_text(encoding="utf-8")

        self.assertIn(".dz-hero-video__media", css)
        self.assertIn(".dz-hero-video__overlay", css)
        self.assertIn("--dz-hero-video-overlay", css)
        # Accessibilité : la vidéo est coupée si l'utilisateur réduit les animations.
        self.assertIn("prefers-reduced-motion: reduce", css)
        self.assertIn('.dz-hero-video', css.split("@media print")[1])


class LoginVideoTests(TestCase):
    """La page de connexion s'illustre d'une vidéo de fond décorative.

    Les fichiers sont produits par tools/generate_login_video.py : les tests
    vérifient qu'ils sont présents, lisibles et correctement branchés.
    """

    WEBM = "video/login.webm"
    MP4 = "video/login.mp4"
    POSTER = "img/login-poster.jpg"

    def setUp(self):
        self.root = Path(__file__).resolve().parent.parent / "static"

    def test_video_and_poster_assets_exist(self):
        for relative in (self.WEBM, self.MP4, self.POSTER):
            asset = self.root / relative
            self.assertTrue(asset.is_file(), f"{relative} manquant")
            self.assertGreater(
                asset.stat().st_size, 1024, f"{relative} est vide ou tronqué"
            )

    def test_mp4_starts_with_an_iso_base_media_box(self):
        head = (self.root / self.MP4).read_bytes()[:12]

        self.assertEqual(head[4:8], b"ftyp")
        self.assertIn(head[8:12], (b"isom", b"mp42", b"avc1"))

    def test_poster_is_a_jpeg(self):
        head = (self.root / self.POSTER).read_bytes()[:3]

        self.assertEqual(head, b"\xff\xd8\xff")

    def test_login_page_embeds_the_decorative_video(self):
        html = self.client.get(reverse("core:login")).content.decode("utf-8")

        self.assertIn("dz-auth-video", html)
        self.assertIn("<video", html)
        self.assertIn('poster="/static/img/login-poster.jpg"', html)
        for attribute in ("muted", "loop", "playsinline", "autoplay"):
            self.assertIn(attribute, html)
        self.assertIn("/static/video/login.webm", html)
        self.assertIn("/static/video/login.mp4", html)

    def test_video_is_hidden_from_assistive_technologies(self):
        html = self.client.get(reverse("core:login")).content.decode("utf-8")
        block = html[html.index("dz-auth-video") : html.index("dz-auth-card")]

        self.assertIn('aria-hidden="true"', block)
        self.assertIn('tabindex="-1"', block)

    def test_stylesheet_ships_the_auth_video_rules(self):
        css = (self.root / "css" / "style.css").read_text(encoding="utf-8")

        self.assertIn(".dz-auth-video__media", css)
        self.assertIn(".dz-auth-video__overlay", css)
        self.assertIn("--dz-auth-video-overlay", css)
        # Accessibilité : la vidéo est coupée si l'utilisateur réduit les animations.
        self.assertIn("prefers-reduced-motion: reduce", css)
        self.assertIn(".dz-auth-video", css.split("@media print")[1])

    def test_login_card_uses_frosted_glass(self):
        """La carte de connexion est en verre dépoli, avec un repli lisible."""
        css = (self.root / "css" / "style.css").read_text(encoding="utf-8")

        self.assertIn(".dz-auth-shell .dz-auth-card", css)
        self.assertIn("backdrop-filter: blur(var(--dz-auth-card-blur))", css)
        self.assertIn("--dz-auth-card-bg", css)
        # Sans `backdrop-filter`, la carte redevient opaque pour rester lisible.
        self.assertIn("@supports not", css)
        self.assertIn("--dz-auth-card-bg: rgba(22, 24, 31, 0.58)", css)

    def test_other_auth_pages_keep_their_layout(self):
        """Seule la connexion porte la vidéo : les autres pages restent sobres."""
        for name in ("core:signup", "core:password_reset"):
            html = self.client.get(reverse(name)).content.decode("utf-8")

            self.assertIn("container dz-auth", html)
            self.assertNotIn("dz-auth-video", html)
            self.assertNotIn("dz-auth-shell", html)


class SecurityHardeningTests(TestCase):
    """Durcissement : SSRF, entonnoir des erreurs et hachage des jetons."""

    def setUp(self):
        self.user = User.objects.create_user(username="prosecure")

    def test_webhook_urls_pointing_inside_are_refused(self):
        for url in (
            "http://127.0.0.1:8000/hook",
            "http://localhost/hook",
            "http://169.254.169.254/latest/meta-data/",
            "http://10.0.0.5/hook",
            "http://192.168.1.10/hook",
            "http://172.16.4.4/hook",
            "http://[::1]:9000/hook",
            "http://0.0.0.0/hook",
        ):
            with self.subTest(url=url):
                with self.assertRaises(WebhookUrlError):
                    validate_webhook_url(url, resolve=False)

    def test_webhook_urls_with_the_wrong_shape_are_refused(self):
        for url in (
            "file:///etc/passwd",
            "gopher://127.0.0.1:6379/_INFO",
            "ftp://example.com/hook",
            "https://user:secret@example.com/hook",
            "http://example.com:99999999/hook",
            "",
        ):
            with self.subTest(url=url):
                with self.assertRaises(WebhookUrlError):
                    validate_webhook_url(url, resolve=False)

    def test_public_webhook_urls_are_accepted(self):
        for url in (
            "https://hooks.slack.com/services/xyz",
            "https://hooks.exemple.test/datazen",
            "http://93.184.216.34/webhook",
        ):
            with self.subTest(url=url):
                self.assertEqual(validate_webhook_url(url, resolve=False), url)

    def test_dns_resolution_rejects_an_internal_target(self):
        with self.assertRaises(WebhookUrlError):
            validate_webhook_url("http://169.254.169.254/", resolve=True)

    def test_webhook_form_refuses_an_internal_url(self):
        form = WebhookForm(
            data={
                "name": "Interne",
                "url": "http://127.0.0.1:8000/hook",
                "event": Webhook.Event.CLEANING_DONE,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("url", form.errors)

    def test_webhook_view_refuses_an_internal_url(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("core:webhooks"),
            {
                "name": "Interne",
                "url": "http://169.254.169.254/latest/meta-data/",
                "event": Webhook.Event.CLEANING_DONE,
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Webhook.objects.filter(name="Interne").exists())

    def test_webhook_save_refuses_an_internal_url(self):
        hook = Webhook(
            owner=self.user,
            name="Interne",
            url="http://10.0.0.5/hook",
            event=Webhook.Event.CLEANING_DONE,
        )
        with self.assertRaises(ValidationError):
            hook.save()

    def test_user_error_hides_absolute_paths(self):
        try:
            open("C:/Users/inconnu/dossier/absent.csv", encoding="utf-8")
        except OSError as exc:
            message = user_error(exc, "lecture du fichier")
        self.assertNotIn("C:/", message)
        self.assertNotIn("Users", message)
        self.assertIn("absent.csv", message)

    def test_user_error_keeps_a_single_short_line(self):
        message = user_error(ValueError("ligne" + chr(10) + "suite"), "test")
        self.assertNotIn(chr(10), message)
        self.assertLessEqual(len(user_error(ValueError("x" * 900), "test")), 181)

    def test_token_digest_is_keyed_and_differs_from_the_legacy_one(self):
        clear = api_service.generate_token()[0]
        self.assertNotEqual(hash_token(clear), legacy_token_hash(clear))
        self.assertEqual(len(hash_token(clear)), 64)
        self.assertEqual(hash_token(clear), hash_token(clear))

    def test_a_legacy_token_still_resolves_then_is_migrated(self):
        clear = api_service.generate_token()[0]
        token = ApiToken.objects.create(
            owner=self.user,
            name="Herite",
            key_hash=legacy_token_hash(clear),
            prefix=clear[:10],
        )
        self.assertEqual(api_service.resolve_token(clear), token)
        token.refresh_from_db()
        self.assertEqual(token.key_hash, hash_token(clear))

    def test_an_unknown_token_does_not_resolve(self):
        self.assertIsNone(api_service.resolve_token(api_service.generate_token()[0]))

    def test_api_rejects_a_token_in_the_query_string(self):
        token, clear = api_service.create_token(self.user, "URL")
        self.client.logout()
        response = self.client.get(f"{reverse('core:api_datasets')}?token={clear}")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response["WWW-Authenticate"], "Bearer")
        token.refresh_from_db()
        self.assertEqual(token.call_count, 0)
