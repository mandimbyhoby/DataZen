"""Tests de l'application DataZen (authentification, asynchrone, règles)."""
import json
import re
from datetime import timedelta
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import AnonymousUser, User
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import pgettext

from . import views
from .errors import user_error
from .forms import BatchCleaningForm, CleaningOptionsForm, ShareForm, WebhookForm
from .models import (
    ActivityLog,
    ApiToken,
    CleaningRule,
    CleaningSchedule,
    DataFile,
    DatasetShare,
    DatasetVersion,
    Profile,
    Webhook,
)
from .services import activity as activity_service
from .services import api as api_service
from .services import batch as batch_service
from .services import permissions as permissions_service
from .services import schedules as schedule_service
from .services import versions as version_service
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
from .services.operations import (
    CORRECTION_TYPE_MESSAGES,
    correction_type_label,
    render_correction_types,
    render_operations,
    render_score_explanations,
)
from .services.pipeline import preview_cleaning, run_cleaning
from .services.reader import read_dataframe
from .services.validation import build_detection, verify_consistency

CSV_CONTENT = (
    "id;nom;email;telephone;ville\n"
    "1;  alice ;Alice@Example.COM;06 12 34 56 78;paris\n"
    "2;Bob;bob@example.com;0612345679;Lyon\n"
    "3;alice;alice@example.com;0612345678;Paris\n"
    "4;;inconnu;;\n"
)

# Colonne vide, colonne constante, colonne à type hétérogène + deux colonnes numériques.
MIXED_CSV_CONTENT = (
    "vide;constante;mixte;age;salaire\n"
    + "".join(
        f";x;{value};{10 + index * 10};{2000 + index * 100}\n"
        for index, value in enumerate(
            ["1", "2", "3", "a", "b", "c", "4", "5", "6", "d", "e", "f"]
        )
    )
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
        self.assertIn("rule_normalize_emails", [code for code, _ in operations])
        self.assertTrue(any("[Règle]" in op for op in render_operations(operations)))
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
            rendered = render_operations(operations)
        self.assertIn("Category normalization (", rendered[1])
        self.assertTrue(any("Anonymize sensitive data" in op for op in rendered))
        self.assertIn("[Rule] Remove extra whitespace", rendered[-1])
        self.assertFalse(any("Normalisation" in op or "Règle" in op for op in rendered))

    def test_operations_follow_the_language_active_at_display_time(self):
        """La liste reste traduisible après coup : elle suit la langue affichée.

        Le nettoyage est lancé en français, puis la même liste est rendue en
        anglais et en allemand : c'est le bug d'origine (texte figé dans la
        langue du nettoyage) qui est vérifié ici.
        """
        data_file = DataFile.objects.create(
            file=make_upload(), original_name="clients.csv"
        )
        with translation.override("fr"):
            operations, _ = run_cleaning(
                data_file,
                {"normalize_case": True, "anonymize": True},
                rules=[{"operation": "trim_whitespace"}],
            )
            french = render_operations(operations)
        self.assertTrue(any("Normalisation" in op for op in french))

        with translation.override("en"):
            english = render_operations(operations)
        with translation.override("de"):
            german = render_operations(operations)

        self.assertIn("Category normalization (", english[1])
        self.assertTrue(any("Anonymize sensitive data" in op for op in english))
        self.assertIn("[Rule] Remove extra whitespace", english[-1])
        self.assertFalse(any("Normalisation" in op or "Règle" in op for op in english))
        self.assertTrue(any("Kategorien vereinheitlichen" in op for op in german))
        self.assertFalse(any("Normalisation" in op for op in german))

    def test_operations_are_stored_as_codes_not_translated_text(self):
        """Le pipeline mémorise des codes : aucune traduction n'est figée."""
        data_file = DataFile.objects.create(
            file=make_upload(), original_name="clients.csv"
        )
        operations, _ = run_cleaning(data_file, {"trim_whitespace": True})
        self.assertTrue(operations)
        for entry in operations:
            self.assertIsInstance(entry, tuple)
            code, params = entry
            self.assertIsInstance(code, str)
            self.assertIsInstance(params, dict)

    def test_render_operations_keeps_legacy_strings(self):
        """Les sessions enregistrées avant les codes restent affichables."""
        legacy = ["Normalisation de la casse (noms, libellés, villes)"]
        self.assertEqual(render_operations(legacy), legacy)
        self.assertEqual(render_operations(None), [])
        self.assertEqual(render_operations([("code_inconnu", {})]), ["code_inconnu"])

    def test_render_operations_recovers_legacy_text_in_another_language(self):
        """Un libellé figé autrefois est retrouvé puis rendu dans la langue active.

        Les sessions enregistrées avant l'introduction des codes contiennent du
        texte déjà traduit. Il doit être reconnu pour suivre la langue de
        l'interface au lieu de rester figé dans la langue du nettoyage.
        """
        legacy = [
            "Normalisation de la casse (noms, libellés, villes)",
            "Normalisation des téléphones (0 corrigé(s))",
            "Suppression des doublons sur « Email » (2 supprimé(s))",
        ]
        with translation.override("zh-hans"):
            rendered = render_operations(legacy)

        self.assertEqual(
            rendered,
            [
                "统一大小写（姓名、标签、城市）",
                "规范电话号码（已修正 0 项）",
                "按“Email”列删除重复项（已删除 2 项）",
            ],
        )

    def test_render_operations_leaves_unknown_text_untouched(self):
        """Un texte irrécupérable n'est ni inventé ni perdu."""
        with translation.override("en"):
            rendered = render_operations(["Ancienne opération brute"])
        self.assertEqual(rendered, ["Ancienne opération brute"])

    def test_correction_type_labels_are_translated(self):
        """Les codes du journal ne sont jamais affichés bruts."""
        codes = ["doublon", "casse", "catégorie", "anonymisation", "email"]
        with translation.override("fr"):
            french = render_correction_types(codes)
        with translation.override("en"):
            english = render_correction_types(codes)

        self.assertEqual(
            french, ["Doublon", "Casse", "Catégorie", "Anonymisation", "Courriel"]
        )
        self.assertEqual(
            english, ["Duplicate", "Case", "Category", "Anonymization", "Email"]
        )
        self.assertEqual(render_correction_types(["code_inconnu"]), ["code_inconnu"])
        self.assertEqual(render_correction_types(None), [])

    def test_correction_type_labels_cover_the_change_log_vocabulary(self):
        """Chaque code produit par le moteur possède un libellé traduit."""
        expected = {
            "doublon": "Duplicate",
            "casse": "Case",
            "catégorie": "Category",
            "anonymisation": "Anonymization",
            "inconnu": "Unknown value",
            "téléphone": "Phone",
            "anomalie": "Anomaly",
            "date": "Date",
            "email": "Email",
            "Email invalide": "Invalid email",
            "Email placeholder": "Placeholder email",
            "Email manquant": "Missing email",
            "numérique": "Numeric",
        }
        self.assertEqual(set(CORRECTION_TYPE_MESSAGES), set(expected))
        with translation.override("en"):
            for code, label in expected.items():
                self.assertEqual(correction_type_label(code), label)

    def test_detail_page_operations_follow_the_interface_language(self):
        """Bout en bout : nettoyage en français, page affichée en anglais.

        Les opérations sont mémorisées en session sous forme de codes ; la page
        doit donc les afficher dans la langue active de l'interface, même si le
        nettoyage a été lancé dans une autre langue.
        """
        user = User.objects.create_user(username="ops-lang")
        self.client.force_login(user)
        data_file = DataFile.objects.create(
            file=make_upload(), original_name="clients.csv", owner=user
        )
        with translation.override("fr"):
            operations, _ = run_cleaning(
                data_file, {"normalize_case": True, "trim_whitespace": True}
            )
        session = self.client.session
        session[f"operations_{data_file.pk}"] = operations
        session["django_language"] = "en"
        session.save()

        response = self.client.get(reverse("core:dataset_detail", args=[data_file.pk]))

        self.assertEqual(response.status_code, 200)
        rendered = response.context["operations"]
        self.assertTrue(any("Case normalization" in op for op in rendered))
        self.assertTrue(any("Remove extra whitespace" in op for op in rendered))
        self.assertFalse(any("Normalisation" in op for op in rendered))
        self.assertContains(response, "Case normalization")

    def test_detail_page_operations_accept_legacy_session_strings(self):
        """Une session ancienne (chaînes déjà traduites) reste affichable."""
        user = User.objects.create_user(username="ops-legacy")
        self.client.force_login(user)
        data_file = DataFile.objects.create(
            file=make_upload(), original_name="clients.csv", owner=user
        )
        run_cleaning(data_file, {"trim_whitespace": True})
        session = self.client.session
        session[f"operations_{data_file.pk}"] = ["Ancienne opération brute"]
        session.save()

        response = self.client.get(reverse("core:dataset_detail", args=[data_file.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["operations"], ["Ancienne opération brute"])
        self.assertContains(response, "Ancienne opération brute")

    def test_score_explanations_are_stored_as_codes_not_translated_text(self):
        """Le score mémorise des codes : aucune traduction n'est figée."""
        data_file = DataFile.objects.create(
            file=make_upload(), original_name="clients.csv"
        )
        run_cleaning(data_file, {"trim_whitespace": True})
        report = Path(data_file.report_file.path).read_text(encoding="utf-8")

        self.assertIn("### 🔎 Explication du score", report)
        for entry in self._score_explanations():
            self.assertIsInstance(entry, dict)
            self.assertIn("code", entry)
            self.assertNotIn("text", entry)

    def _score_explanations(self):
        """Explications brutes du score, telles que produites par le moteur."""
        import pandas as pd

        from .services.validation import build_detection, compute_quality_score

        frame = pd.DataFrame(
            {
                "client_id": [1, 2, 2, 4],
                "email": ["a@b.fr", "mauvais", "mauvais", None],
                "ville": ["Paris", "paris ", "PARIS", "Lyon"],
            }
        )
        return compute_quality_score(frame, build_detection(frame))["explanations"]

    def test_score_explanations_follow_the_language_active_at_display_time(self):
        """Les explications restent traduisibles : elles suivent la langue affichée.

        Le même jeu d'explications est rendu en français, en anglais et en
        allemand : c'est le bug d'origine (texte figé dans la langue du calcul)
        qui est vérifié ici.
        """
        explanations = self._score_explanations()

        with translation.override("fr"):
            french = [item["text"] for item in self._rendered(explanations)]
        with translation.override("en"):
            english = [item["text"] for item in self._rendered(explanations)]
        with translation.override("de"):
            german = [item["text"] for item in self._rendered(explanations)]

        self.assertTrue(any("valeur(s) manquante(s)" in text for text in french))
        self.assertTrue(any("missing value(s)" in text for text in english))
        self.assertTrue(any("fehlende(r) Wert(e)" in text for text in german))

        for text in english + german:
            self.assertNotIn("valeur(s)", text)
            self.assertNotIn("Aucun ", text)

    @staticmethod
    def _rendered(explanations):
        from .services.operations import render_score_explanations

        return render_score_explanations(explanations)

    def test_score_explanations_are_rendered_in_french_by_default(self):
        """Le français est la langue source : il ne doit jamais rester en anglais."""
        with translation.override("fr"):
            rendered = self._rendered(self._score_explanations())

        self.assertTrue(rendered)
        joined = " ".join(item["text"] for item in rendered)
        for english in (
            "value(s)",
            "duplicate(s)",
            "No exact",
            "No potential",
            "No missing",
            "All filled",
            "standardized",
            "Data is ",
        ):
            self.assertNotIn(english, joined, f"anglais résiduel : {english}")
        self.assertTrue(any("Aucun doublon" in item["text"] for item in rendered))

    def test_render_score_explanations_keeps_legacy_entries(self):
        """Les scores calculés avant les codes restent affichables."""
        from .services.operations import render_score_explanations

        legacy = [{"type": "ok", "text": "Explication déjà rendue"}]
        self.assertEqual(render_score_explanations(legacy), legacy)
        self.assertEqual(render_score_explanations(None), [])
        self.assertEqual(render_score_explanations(["texte brut"]), [])
        self.assertEqual(render_score_explanations([{"code": "inconnu"}]), [])

    def test_render_score_explanations_recovers_legacy_text(self):
        """Une explication figée autrefois est retrouvée puis retraduite.

        Les scores calculés avant l'introduction des codes contiennent du texte
        déjà traduit (anglais pour les plus anciens, français ensuite). Il doit
        être reconnu pour suivre la langue affichée.
        """
        from .services.operations import render_score_explanations

        legacy = [
            {"type": "warn", "text": "1 unknown value(s) (data unavailable)"},
            {"type": "warn", "text": "1 valeur(s) manquante(s)"},
            {"type": "warn", "text": "3 valeur(s) non standard"},
        ]
        with translation.override("zh-hans"):
            rendered = render_score_explanations(legacy)

        self.assertEqual(
            [item["text"] for item in rendered],
            [
                "1 个未知值（数据不可用）",
                "1 个缺失值",
                "3 个非标准值",
            ],
        )
        self.assertEqual([item["type"] for item in rendered], ["warn", "warn", "warn"])

    def test_every_score_explanation_code_has_a_translation(self):
        """Chaque code produit par le moteur possède un message traduit."""
        from .services.operations import SCORE_EXPLANATION_MESSAGES

        expected = {
            "unknown_values",
            "missing_values",
            "no_missing_or_unknown",
            "invalid_values",
            "all_valid",
            "exact_duplicates",
            "no_exact_duplicates",
            "potential_duplicates",
            "no_potential_duplicates",
            "inconsistent_values",
            "consistent",
            "non_standard_values",
            "formats_standardized",
        }
        self.assertEqual(set(SCORE_EXPLANATION_MESSAGES), expected)
        with translation.override("en"):
            for code, message in SCORE_EXPLANATION_MESSAGES.items():
                translated = str(message)
                self.assertTrue(translated, code)
                self.assertNotIn("valeur(s) ", translated)

    def test_detail_page_score_explanations_follow_the_interface_language(self):
        """Bout en bout : nettoyage en français, page affichée en anglais.

        Les explications sont mémorisées en session sous forme de codes ; la
        page doit donc les afficher dans la langue active de l'interface, même
        si le nettoyage a été lancé dans une autre langue.
        """
        user = User.objects.create_user(username="score-lang")
        self.client.force_login(user)
        data_file = DataFile.objects.create(
            file=make_upload(), original_name="clients.csv", owner=user
        )
        with translation.override("fr"):
            run_cleaning(data_file, {"trim_whitespace": True})

        session = self.client.session
        session["django_language"] = "en"
        session.save()

        response = self.client.get(reverse("core:dataset_detail", args=[data_file.pk]))

        self.assertEqual(response.status_code, 200)
        texts = [
            item["text"]
            for item in response.context["quality_after"]["explanations"]
        ]
        self.assertTrue(texts)
        self.assertFalse(any("valeur(s)" in text for text in texts))
        self.assertContains(response, "No exact duplicates")

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
        self.assertIn("remove_duplicates_column", [code for code, _ in operations])
        self.assertTrue(any("« email »" in op for op in render_operations(operations)))
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

    def test_report_includes_the_statistical_profiling_section(self):
        """Le rapport Markdown expose le profilage statistique par colonne."""
        data_file = DataFile.objects.create(
            file=make_upload(), original_name="clients.csv"
        )
        run_cleaning(data_file, {"trim_whitespace": True})
        report = Path(data_file.report_file.path).read_text(encoding="utf-8")

        self.assertIn("## 🔬 Profilage statistique", report)
        for header in (
            "| Colonne |",
            "| Variance |",
            "| Asymétrie |",
            "| Aplatissement |",
            "| Valeurs aberrantes |",
        ):
            self.assertIn(header, report)

    def test_report_profiling_section_is_translated(self):
        """La section de profilage suit la langue active."""
        import pandas as pd

        from .services.report import build_report
        from .services.validation import profile_dataframe

        frame = pd.DataFrame({"age": [10, 20, 30, 40, 50]})
        with translation.override("en"):
            report = build_report(
                "clients.csv",
                [],
                {"rows": 5, "columns": 1, "duplicates": 0, "missing": 0},
                {"rows": 5, "columns": 1, "duplicates": 0, "missing": 0},
                profile=profile_dataframe(frame),
            )

        self.assertIn("## 🔬 Statistical profiling", report)
        self.assertIn("| Skewness |", report)
        self.assertIn("| Kurtosis |", report)
        self.assertNotIn("Profilage statistique", report)

    def test_report_profiling_section_is_omitted_without_profile(self):
        """Sans profilage fourni, la section n'apparaît pas."""
        from .services.report import build_report

        report = build_report(
            "clients.csv",
            [],
            {"rows": 5, "columns": 1, "duplicates": 0, "missing": 0},
            {"rows": 5, "columns": 1, "duplicates": 0, "missing": 0},
        )

        self.assertNotIn("Profilage statistique", report)

    def test_report_profiling_section_reads_the_distributions(self):
        """Les colonnes les plus asymétriques et les outliers sont commentés."""
        import pandas as pd

        from .services.report import build_report
        from .services.validation import profile_dataframe

        frame = pd.DataFrame(
            {
                "age": [10, 20, 30, 40, 50, 60, 70, 80, 90, 1000],
                "salaire": [2000, 2100, 2200, 2300, 2400, 2500, 2600, 2700, 2800, 2900],
            }
        )
        report = build_report(
            "clients.csv",
            [],
            {"rows": 10, "columns": 2, "duplicates": 0, "missing": 0},
            {"rows": 10, "columns": 2, "duplicates": 0, "missing": 0},
            profile=profile_dataframe(frame),
        )

        self.assertIn("Distribution la plus asymétrique : « age »", report)
        self.assertIn("Distribution la plus concentrée/pointue : « age »", report)
        self.assertIn("1 valeur(s) aberrante(s) détectée(s)", report)
        self.assertIn("« age » (1)", report)

    def test_report_profiling_section_skips_non_numeric_columns(self):
        """Sans colonne numérique, seul le tableau est produit."""
        import pandas as pd

        from .services.report import build_report
        from .services.validation import profile_dataframe

        frame = pd.DataFrame({"ville": ["Paris", "Lyon", "Nice"]})
        report = build_report(
            "clients.csv",
            [],
            {"rows": 3, "columns": 1, "duplicates": 0, "missing": 0},
            {"rows": 3, "columns": 1, "duplicates": 0, "missing": 0},
            profile=profile_dataframe(frame),
        )

        self.assertIn("## 🔬 Profilage statistique", report)
        self.assertIn("| ville |", report)
        self.assertNotIn("Distribution la plus asymétrique", report)
        self.assertNotIn("valeur(s) aberrante(s) détectée(s)", report)


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

    def test_profile_dataframe_includes_rich_numeric_statistics(self):
        import pandas as pd

        df = pd.DataFrame({"age": [10, 20, 30, 40, 50]})
        dashboard = build_dashboard(df, detection=build_detection(df))
        profile = dashboard["profile"][0]

        self.assertEqual(profile["colonne"], "age")
        self.assertEqual(profile["type"], "numérique")
        self.assertEqual(profile["min"], "10")
        self.assertEqual(profile["max"], "50")
        self.assertEqual(profile["moyenne"], "30.00")
        self.assertEqual(profile["mediane"], "30")
        self.assertNotIn(profile["ecart_type"], {"—", ""})
        self.assertNotIn(profile["variance"], {"—", ""})
        self.assertNotIn(profile["asymetrie"], {"—", ""})
        self.assertNotIn(profile["aplatissement"], {"—", ""})
        self.assertEqual(profile["q1"], "20")
        self.assertEqual(profile["q3"], "40")

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


class StructuralAnomalyTests(TestCase):
    """Détection des anomalies structurelles (forme des colonnes).

    Complète la détection ligne à ligne : une colonne vide, constante ou à
    type hétérogène fausse silencieusement les analyses sans produire la
    moindre erreur de format.
    """

    @staticmethod
    def sample_df():
        import pandas as pd

        return pd.DataFrame(
            {
                "vide": [None] * 12,
                "constante": ["x"] * 12,
                "mixte": ["1", "2", "3", "a", "b", "c", "4", "5", "6", "d", "e", "f"],
                "num": list(range(12)),
            }
        )

    def test_detects_every_structural_anomaly_type(self):
        """Chaque famille d'anomalie structurelle est détectée."""
        from .services.validation import detect_structural_anomalies

        anomalies = detect_structural_anomalies(self.sample_df())
        found = {(a["colonne"], a["type"]) for a in anomalies}

        self.assertIn(("vide", "vide"), found)
        self.assertIn(("constante", "constante"), found)
        self.assertIn(("mixte", "type_mixte"), found)
        self.assertNotIn(("num", "constante"), found)

    def test_anomalies_are_sorted_by_severity_then_column(self):
        """Le tri place les sévérités hautes en tête, puis l'ordre alphabétique."""
        from .services.validation import detect_structural_anomalies

        anomalies = detect_structural_anomalies(self.sample_df())
        order = {"haute": 0, "moyenne": 1, "faible": 2}
        keys = [(order[a["severite"]], a["colonne"]) for a in anomalies]

        self.assertEqual(keys, sorted(keys))
        self.assertEqual(anomalies[0]["severite"], "haute")

    def test_quasi_constant_and_duplicate_identifier_are_detected(self):
        """Une modalité écrasante et un identifiant dupliqué sont signalés."""
        import pandas as pd

        from .services.validation import detect_structural_anomalies

        df = pd.DataFrame(
            {
                "statut": ["actif"] * 19 + ["inactif"],
                "client_id": [1, 2, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19],
            }
        )
        found = {(a["colonne"], a["type"]) for a in detect_structural_anomalies(df)}

        self.assertIn(("statut", "quasi_constante"), found)
        self.assertIn(("client_id", "identifiant_non_unique"), found)

    def test_missing_and_unknown_values_are_ignored(self):
        """Les valeurs manquantes et « Inconnu » ne créent pas de faux positifs."""
        import pandas as pd

        from .services.validation import detect_structural_anomalies

        df = pd.DataFrame({"a": ["Inconnu"] * 5, "b": [None, None, None, None, None]})
        anomalies = detect_structural_anomalies(df)

        # Les deux colonnes sont vides de contenu réel : une seule anomalie
        # « vide » chacune, jamais « constante ».
        self.assertEqual({a["type"] for a in anomalies}, {"vide"})

    def test_detection_never_raises(self):
        """Un DataFrame vide ou sans ligne ne lève jamais."""
        import pandas as pd

        from .services.validation import detect_structural_anomalies

        self.assertEqual(detect_structural_anomalies(pd.DataFrame()), [])
        self.assertEqual(
            {a["type"] for a in detect_structural_anomalies(pd.DataFrame({"a": [], "b": []}))},
            {"vide"},
        )

    def test_detection_is_registered_in_build_detection(self):
        """``build_detection`` expose la clé ``structural``."""
        detection = build_detection(self.sample_df())

        self.assertIn("structural", detection)
        self.assertEqual(len(detection["structural"]), 3)

    def test_dashboard_exposes_translated_structural_rows(self):
        """Le tableau de bord fournit des lignes prêtes à afficher."""
        dashboard = build_dashboard(self.sample_df())

        self.assertEqual(dashboard["structural_count"], 3)
        self.assertEqual(len(dashboard["structural_anomalies"]), 3)

        rows = {row["colonne"]: row for row in dashboard["structural_anomalies"]}
        self.assertEqual(rows["vide"]["type"], "Colonne vide")
        self.assertEqual(rows["vide"]["severite"], "haute")
        self.assertEqual(rows["vide"]["classe"], "danger")
        self.assertEqual(rows["constante"]["type"], "Colonne constante")
        self.assertEqual(rows["mixte"]["type"], "Type hétérogène")
        self.assertEqual(rows["mixte"]["severite"], "moyenne")
        self.assertEqual(rows["mixte"]["classe"], "warning")

    def test_dashboard_structural_rows_follow_the_active_language(self):
        """Les libellés structurels suivent la langue active."""
        with translation.override("en"):
            dashboard = build_dashboard(self.sample_df())

        rows = {row["colonne"]: row for row in dashboard["structural_anomalies"]}
        self.assertEqual(rows["vide"]["type"], "Empty column")
        self.assertEqual(rows["vide"]["severite"], "high")
        self.assertEqual(rows["mixte"]["type"], "Mixed type")
        self.assertEqual(rows["mixte"]["severite"], "medium")

    def test_anomaly_type_labels_are_translated_in_every_language(self):
        """Chaque langue du site traduit les types d'anomalies structurelles."""
        from django.conf import settings

        from .services.validation import STRUCTURAL_ANOMALY_LABELS

        sources = {
            "vide": "Colonne vide",
            "constante": "Colonne constante",
            "identifiant_non_unique": "Identifiant non unique",
            "quasi_constante": "Colonne quasi constante",
            "type_mixte": "Type hétérogène",
        }
        self.assertEqual(set(STRUCTURAL_ANOMALY_LABELS), set(sources))

        for language in settings.SITE_LANGUAGES:
            code = language["code"]
            if code == "fr":
                continue
            with translation.override(code):
                for key, source in sources.items():
                    translated = str(STRUCTURAL_ANOMALY_LABELS[key])
                    self.assertTrue(translated.strip(), f"{code} : « {key} » vide")
                    self.assertNotEqual(
                        translated,
                        source,
                        f"{code} : « {source} » n'est pas traduit",
                    )

    def test_unknown_anomaly_code_falls_back_to_the_code(self):
        """Un code inconnu n'échoue pas : il est renvoyé tel quel."""
        from .services.validation import structural_anomaly_label

        self.assertEqual(str(structural_anomaly_label("inconnu")), "inconnu")

    def test_dashboard_reports_structural_anomalies_in_to_verify(self):
        """Les anomalies structurelles alimentent la liste « à vérifier »."""
        dashboard = build_dashboard(self.sample_df())

        item = next(
            item
            for item in dashboard["to_verify"]
            if "structurelle" in item["text"]
        )
        self.assertEqual(len(item["items"]), 3)
        self.assertEqual(
            {entry["column"] for entry in item["items"]},
            {"vide", "constante", "mixte"},
        )

    def test_dashboard_problems_include_structural_anomalies(self):
        """La répartition des problèmes compte les anomalies structurelles."""
        dashboard = build_dashboard(self.sample_df())

        entry = next(
            p for p in dashboard["problems"] if p["label"] == "Anomalies structurelles"
        )
        self.assertEqual(entry["value"], 3)
        self.assertGreater(entry["width"], 0)

    def test_structural_section_is_rendered_on_the_detail_page(self):
        """La page du dataset affiche le tableau des anomalies structurelles."""
        user = User.objects.create_user(username="structural")
        self.client.force_login(user)
        data_file = DataFile.objects.create(
            file=make_upload("mixte.csv", MIXED_CSV_CONTENT),
            original_name="mixte.csv",
            owner=user,
        )
        run_cleaning(data_file, {"trim_whitespace": True})

        response = self.client.get(
            reverse("core:dataset_detail", args=[data_file.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["dashboard"]["structural_count"], 3)
        self.assertContains(response, "Anomalies structurelles")
        self.assertContains(response, "Sévérité")
        self.assertContains(response, "Colonne vide")
        self.assertContains(response, "Type hétérogène")
        self.assertContains(
            response,
            "Anomalies signalées uniquement — jamais modifiées automatiquement.",
        )

    def test_structural_section_shows_an_empty_state(self):
        """Sans anomalie, la page affiche un état vide explicite."""
        user = User.objects.create_user(username="structural2")
        self.client.force_login(user)
        data_file = DataFile.objects.create(
            file=make_upload(), original_name="clients.csv", owner=user
        )
        run_cleaning(data_file, {"trim_whitespace": True})

        response = self.client.get(
            reverse("core:dataset_detail", args=[data_file.pk])
        )

        self.assertEqual(response.context["dashboard"]["structural_count"], 0)
        self.assertContains(response, "Aucune anomalie structurelle détectée.")


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
            "moments",
        ):
            self.assertIn(expected, slugs)

    def test_structural_chart_requires_structural_anomalies(self):
        """Le graphique structurel n'apparaît qu'en présence d'anomalies."""
        import pandas as pd

        from .services.charts import available_charts
        from .services.dashboard import build_dashboard

        clean = self.sample_df()
        self.assertNotIn("structural", available_charts(clean, build_dashboard(clean)))

        df = pd.DataFrame(
            {
                "vide": [None] * 12,
                "constante": ["x"] * 12,
                "mixte": ["1", "2", "3", "a", "b", "c", "4", "5", "6", "d", "e", "f"],
                "num": list(range(12)),
            }
        )
        slugs = available_charts(df, build_dashboard(df))
        self.assertIn("structural", slugs)
        self.assertIn("moments", slugs)

    def test_new_charts_render_valid_png(self):
        """Les graphiques « moments » et « structurel » produisent un PNG."""
        import pandas as pd

        from .services.charts import chart_png
        from .services.dashboard import build_dashboard

        df = pd.DataFrame(
            {
                "vide": [None] * 12,
                "constante": ["x"] * 12,
                "mixte": ["1", "2", "3", "a", "b", "c", "4", "5", "6", "d", "e", "f"],
                "num": list(range(12)),
            }
        )
        dashboard = build_dashboard(df)
        for slug in ("moments", "structural"):
            with self.subTest(slug=slug):
                png = chart_png(df, dashboard, slug)
                self.assertIsNotNone(png)
                self.assertTrue(png.startswith(b"\x89PNG"))
                self.assertGreater(len(png), 1000)

    def test_moments_chart_reuses_the_profiling_statistics(self):
        """Le graphique des moments reprend les valeurs du profilage."""
        from .services.charts import chart_data
        from .services.dashboard import build_dashboard
        from .services.validation import profile_dataframe

        df = self.sample_df()
        payload = chart_data(df, build_dashboard(df))
        moments = next(c for c in payload["charts"] if c["slug"] == "moments")

        self.assertEqual(moments["kind"], "moments")
        self.assertEqual(moments["data"]["labels"]["skewness"], "Asymétrie")
        self.assertEqual(moments["data"]["labels"]["kurtosis"], "Aplatissement")

        expected = {
            row["colonne"]: row
            for row in profile_dataframe(df)
            if row["type"] == "numérique"
        }
        self.assertTrue(moments["data"]["items"])
        for item in moments["data"]["items"]:
            row = expected[item["label"]]
            self.assertAlmostEqual(item["skewness"], float(row["asymetrie"]), places=2)
            self.assertAlmostEqual(
                item["kurtosis"], float(row["aplatissement"]), places=2
            )

    def test_structural_chart_groups_anomalies_by_translated_type(self):
        """Le graphique structurel compte les anomalies par type traduit."""
        import pandas as pd

        from .services.charts import chart_data
        from .services.dashboard import build_dashboard

        df = pd.DataFrame(
            {
                "vide": [None] * 12,
                "constante": ["x"] * 12,
                "mixte": ["1", "2", "3", "a", "b", "c", "4", "5", "6", "d", "e", "f"],
                "num": list(range(12)),
            }
        )
        payload = chart_data(df, build_dashboard(df))
        structural = next(c for c in payload["charts"] if c["slug"] == "structural")

        self.assertEqual(structural["kind"], "hbar")
        labels = {item["label"]: item["value"] for item in structural["data"]["items"]}
        self.assertEqual(labels["Colonne vide"], 1)
        self.assertEqual(labels["Colonne constante"], 1)
        self.assertEqual(labels["Type hétérogène"], 1)

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
        self.assertContains(response, "Anomalies structurelles")
        self.assertEqual(len(response.context["dashboard"]["indicators"]), 7)
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
            "Forme des distributions",
            "Asymétrie et aplatissement (moments centrés) des colonnes numériques.",
            "Valeur du moment centré",
            "Anomalies structurelles",
            "Anomalies structurelles par type",
            "Nombre de colonnes concernées",
            "Colonnes vides, constantes, quasi constantes ou à type hétérogène.",
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

        def test_chart_data_endpoint_exposes_the_new_charts(self):
            """L'endpoint JSON sert aussi les graphiques « moments » et structurel."""
            data_file = DataFile.objects.create(
                file=make_upload("mixte.csv", MIXED_CSV_CONTENT),
                original_name="mixte.csv",
                owner=self.user,
            )
            run_cleaning(data_file, {"trim_whitespace": True})

            response = self.client.get(
                reverse("core:dataset_chart_data", args=[data_file.pk])
            )
            self.assertEqual(response.status_code, 200)

            payload = response.json()
            kinds = {chart["slug"]: chart["kind"] for chart in payload["charts"]}
            self.assertEqual(kinds["moments"], "moments")
            self.assertEqual(kinds["structural"], "hbar")

            moments = next(c for c in payload["charts"] if c["slug"] == "moments")
            self.assertEqual(moments["data"]["labels"]["skewness"], "Asymétrie")
            self.assertEqual(moments["data"]["labels"]["kurtosis"], "Aplatissement")
            self.assertTrue(moments["data"]["items"])

            structural = next(c for c in payload["charts"] if c["slug"] == "structural")
            labels = {i["label"]: i["value"] for i in structural["data"]["items"]}
            self.assertEqual(labels["Colonne vide"], 1)
            self.assertEqual(labels["Colonne constante"], 1)
            self.assertEqual(labels["Type hétérogène"], 1)

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


class PreviewCleaningTests(TestCase):
    """L'aperçu doit simuler le nettoyage sans jamais rien écrire.

    Le cœur du contrat : l'aperçu et le nettoyage réel traversent le même code
    (``_execute_cleaning``), donc les chiffres annoncés ne peuvent pas diverger
    de ce qui sera réellement appliqué. Ces tests verrouillent les deux moitiés
    de cette promesse : « rien n'est écrit » et « les chiffres sont les mêmes ».
    """

    OPTIONS = {
        "trim_whitespace": True,
        "normalize_case": True,
        "normalize_emails": True,
        "remove_duplicates": True,
        "dedupe_column": "email",
        # Sans cette option, la déduplication est sensible à la casse et
        # « alice@example.com » / « Alice@Example.COM » ne sont pas fusionnés.
        "dedupe_ignore_case": True,
    }

    def setUp(self):
        self.user = User.objects.create_user("previewuser", password="MotDePasse!2024")
        self.client.force_login(self.user)
        self.data_file = DataFile.objects.create(
            owner=self.user, file=make_upload(), original_name="clients.csv"
        )

    def _snapshot(self):
        """Capture l'état persisté que l'aperçu ne doit pas modifier."""
        self.data_file.refresh_from_db()
        return {
            "status": self.data_file.status,
            "progress": self.data_file.progress,
            "cleaned_file": self.data_file.cleaned_file.name,
            "report_file": self.data_file.report_file.name,
            "change_log_file": self.data_file.change_log_file.name,
            "quality_before": self.data_file.quality_before,
            "quality_after": self.data_file.quality_after,
            "rows_count": self.data_file.rows_count,
            "columns_count": self.data_file.columns_count,
            "issues_count": self.data_file.issues_count,
            "changes_count": self.data_file.changes_count,
            "metrics": self.data_file.metrics,
            "cleaned_at": self.data_file.cleaned_at,
        }

    def test_preview_changes_nothing_on_disk_or_in_database(self):
        """Simuler ne doit écrire ni fichier, ni colonne, ni horodatage."""
        before = self._snapshot()

        preview = preview_cleaning(self.data_file, self.OPTIONS)

        self.assertIsNotNone(preview)
        self.assertEqual(self._snapshot(), before)

    def test_preview_reports_real_before_and_after_values(self):
        """L'aperçu montre les vraies corrections, pas une comparaison devinée."""
        preview = preview_cleaning(self.data_file, self.OPTIONS)

        self.assertEqual(preview["rows_before"], 4)
        self.assertEqual(preview["rows_after"], 3)
        self.assertTrue(preview["has_changes"])

        # Le libellé du score est repérable par son unité, jamais par son texte.
        scores = [row for row in preview["indicators"] if row["unit"] == "%"]
        self.assertEqual(len(scores), 1)
        self.assertEqual(scores[0]["before"], preview["before"]["score"])
        self.assertEqual(scores[0]["after"], preview["after"]["score"])

        entries = preview["change_log"]["rows"]
        self.assertEqual(preview["change_log"]["total"], len(entries))
        self.assertFalse(preview["change_log"]["truncated"])
        # Les vraies valeurs, avant → après, relevées par le nettoyeur lui-même.
        self.assertTrue(
            any(e["before"] == "  alice " and e["after"] == "Alice" for e in entries)
        )
        self.assertTrue(
            any(
                e["before"] == "Alice@Example.COM" and e["after"] == "alice@example.com"
                for e in entries
            )
        )
        self.assertTrue(
            any(
                e["column"] == "(ligne entière)" and e["kind"] == "doublon"
                for e in entries
            ),
            "La ligne supprimée par déduplication doit apparaître dans le journal.",
        )

    def test_preview_numbers_match_an_actual_run(self):
        """Les chiffres annoncés sont exactement ceux du nettoyage réel.

        C'est la garantie structurelle du refactor : les deux chemins partagent
        ``_execute_cleaning``, donc l'aperçu ne peut pas mentir.
        """
        preview = preview_cleaning(self.data_file, self.OPTIONS)

        run_cleaning(self.data_file, self.OPTIONS)
        self.data_file.refresh_from_db()

        self.assertEqual(self.data_file.status, DataFile.Status.CLEANED)
        self.assertEqual(self.data_file.rows_count, preview["rows_after"])
        self.assertEqual(self.data_file.quality_before, preview["before"]["score"])
        self.assertEqual(self.data_file.quality_after, preview["after"]["score"])
        self.assertEqual(self.data_file.changes_count, preview["change_log"]["total"])

    def test_preview_is_identical_when_repeated(self):
        """Simuler deux fois donne le même résultat : rien ne s'accumule."""
        first = preview_cleaning(self.data_file, self.OPTIONS)
        second = preview_cleaning(self.data_file, self.OPTIONS)

        self.assertEqual(first["before"], second["before"])
        self.assertEqual(first["after"], second["after"])
        self.assertEqual(
            first["change_log"]["rows"], second["change_log"]["rows"]
        )

    def test_preview_returns_none_for_unreadable_file(self):
        """Un fichier illisible ne lève pas : la vue affichera un message."""
        before = self._snapshot()
        Path(self.data_file.file.path).unlink()

        self.assertIsNone(preview_cleaning(self.data_file, self.OPTIONS))
        self.assertEqual(self._snapshot(), before)

    def test_preview_action_never_starts_cleaning(self):
        """La route d'aperçu doit rester synchrone et sans effet de bord."""
        calls = []

        with mock.patch.object(
            views, "start_cleaning", lambda *a, **k: calls.append((a, k))
        ):
            response = self.client.post(
                reverse("core:dataset_detail", args=[self.data_file.pk]),
                {**self.OPTIONS, "action": "preview", "dedupe_column": "email"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(calls, [])
        self.assertContains(response, 'id="preview-card"')
        self.assertIn("preview", response.context)
        self.data_file.refresh_from_db()
        self.assertEqual(self.data_file.status, DataFile.Status.UPLOADED)

    def test_preview_action_renders_operations_and_list(self):
        """Les opérations simulées sont traduites au rendu, jamais stockées.

        L'aperçu renvoie des codes stables (``normalize_case``…) et non du texte
        figé : le même résultat peut donc être réaffiché dans n'importe quelle
        langue, ce qui est exactement la garantie anti-« traduction gelée ».
        """
        response = self.client.post(
            reverse("core:dataset_detail", args=[self.data_file.pk]),
            {**self.OPTIONS, "action": "preview", "dedupe_column": "email"},
        )

        self.assertEqual(response.status_code, 200)
        preview = response.context["preview"]
        self.assertTrue(preview["rendered_operations"])
        self.assertTrue(
            any("Normalisation de la casse" in op for op in preview["rendered_operations"])
        )

        # Les codes bruts ne contiennent aucun texte traduit…
        codes = [code for code, _ in preview["operations"]]
        self.assertIn("normalize_case", codes)
        self.assertFalse(
            any("Normalis" in code or "Case" in code for code in codes),
            "Les codes d'opération doivent rester neutres (jamais traduits).",
        )

        # …et se rendent donc dans n'importe quelle langue, après coup.
        with translation.override("en"):
            rendered_en = render_operations(preview["operations"])
        self.assertTrue(any("Case normalization" in op for op in rendered_en))
        self.assertFalse(any("Normalisation" in op for op in rendered_en))

    def test_post_without_action_still_starts_cleaning(self):
        """Le bouton « Nettoyer » garde le comportement d'origine."""
        calls = []

        with mock.patch.object(
            views, "start_cleaning", lambda *a, **k: calls.append((a, k))
        ):
            response = self.client.post(
                reverse("core:dataset_detail", args=[self.data_file.pk]),
                {**self.OPTIONS, "dedupe_column": "email"},
            )

        self.assertEqual(len(calls), 1)
        self.assertRedirects(
            response, reverse("core:dataset_detail", args=[self.data_file.pk])
        )

    def test_confirm_button_cleans_the_previewed_options(self):
        """Le bouton de confirmation relance le même endpoint en mode réel."""
        calls = []

        with mock.patch.object(
            views, "start_cleaning", lambda *a, **k: calls.append((a, k))
        ):
            response = self.client.post(
                reverse("core:dataset_detail", args=[self.data_file.pk]),
                {**self.OPTIONS, "action": "clean", "dedupe_column": "email"},
            )

        self.assertEqual(len(calls), 1)
        self.assertRedirects(
            response, reverse("core:dataset_detail", args=[self.data_file.pk])
        )

    def test_preview_is_denied_for_anonymous_users(self):
        """L'aperçu suit les mêmes règles d'accès que le nettoyage."""
        self.client.logout()

        response = self.client.post(
            reverse("core:dataset_detail", args=[self.data_file.pk]),
            {**self.OPTIONS, "action": "preview", "dedupe_column": "email"},
        )

        self.assertEqual(response.status_code, 302)
        self.data_file.refresh_from_db()
        self.assertEqual(self.data_file.status, DataFile.Status.UPLOADED)

    def test_preview_card_is_absent_on_plain_get(self):
        """Un simple chargement de page n'affiche pas de faux aperçu."""
        response = self.client.get(
            reverse("core:dataset_detail", args=[self.data_file.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="preview-card"')
        self.assertNotIn("preview", response.context)


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


class KeyNameTranslationTests(TestCase):
    """Les noms de touches des raccourcis suivent la langue de l'interface.

    Les balises <kbd> de shortcuts.html et de la palette Ctrl+K affichaient
    "Entrée" et "Échap" en clair : invisibles pour l'extracteur, elles
    restaient en français quelle que soit la langue. Elles passent désormais
    par {% translate %} et tools/translations/key_names.py.
    """

    TEMPLATES = ("core/shortcuts.html", "core/base.html")

    TRANSLATIONS = {
        "en": ("Enter", "Esc"),
        "de": ("Eingabe", "Esc"),
        "ar": ("إدخال", "إلغاء"),
        "ru": ("Ввод", "Выход"),
    }

    def setUp(self):
        self.user = User.objects.create_user(username="keynames")
        self.client.force_login(self.user)

    def render(self, view_name, language):
        session = self.client.session
        session["django_language"] = language
        session.save()
        return self.client.get(reverse(view_name)).content.decode("utf-8")

    def test_every_template_wraps_the_key_names(self):
        root = Path(__file__).resolve().parent.parent / "templates"

        for name in self.TEMPLATES:
            source = (root / name).read_text(encoding="utf-8")
            for literal in ('<kbd class="dz-kbd">Entrée</kbd>',):
                self.assertNotIn(
                    literal,
                    source,
                    f"{literal} reste code en dur dans {name}",
                )

    def test_shortcuts_page_is_translated(self):
        for code, (enter, escape) in self.TRANSLATIONS.items():
            html = self.render("core:shortcuts", code)
            self.assertIn(f'<kbd class="dz-kbd">{enter}</kbd>', html)
            self.assertIn(f'<kbd class="dz-kbd">{escape}</kbd>', html)
            self.assertNotIn('<kbd class="dz-kbd">Entrée</kbd>', html)
            self.assertNotIn('<kbd class="dz-kbd">Échap</kbd>', html)

    def test_french_keeps_the_source_strings(self):
        html = self.render("core:shortcuts", "fr")

        self.assertIn('<kbd class="dz-kbd">Entrée</kbd>', html)
        self.assertIn('<kbd class="dz-kbd">Échap</kbd>', html)

    def test_catalog_covers_every_language(self):
        from django.utils.translation import gettext as _

        from tools.translations import CATALOGS
        from tools.translations.key_names import KEYS_A, KEY_NAME_TRANSLATIONS

        self.assertEqual(KEYS_A, ("Entrée", "Échap"))

        for code, catalog in CATALOGS.items():
            if code == "fr":
                continue
            self.assertIn(code, KEY_NAME_TRANSLATIONS, f"{code} sans noms de touches")
            for key in KEYS_A:
                self.assertIn(key, catalog, f"{key} absent du catalogue {code}")

        for code, (enter, escape) in self.TRANSLATIONS.items():
            with translation.override(code):
                self.assertEqual(_("Entrée"), enter)
                self.assertEqual(_("Échap"), escape)


class FrenchSourceTranslationTests(TestCase):
    """Les messages écrits en anglais s'affichent en français.

    Le français est la langue source de DataZen : son catalogue reste vide et
    ``gettext`` renvoie le msgid tel quel. Une partie du code (contrôle de
    cohérence, tableau de bord, exports) déclare pourtant ses messages en
    anglais, si bien que ces libellés restaient anglais dans une interface
    française. ``tools/translations/french_source.py`` comble ce trou.
    """

    def sample_frame(self):
        import pandas as pd

        return pd.DataFrame(
            {
                "email": ["a@example.com", "b@example.com", "inconnu"],
                "commentaire": ["ok", None, "ok"],
            }
        )

    def test_consistency_checks_follow_the_active_language(self):
        frame = self.sample_frame()
        detection = build_detection(frame)

        with translation.override("fr"):
            checks_fr = verify_consistency(frame, detection=detection)["checks"]
        with translation.override("en"):
            checks_en = verify_consistency(frame, detection=detection)["checks"]

        labels_fr = [check["label"] for check in checks_fr]
        labels_en = [check["label"] for check in checks_en]

        self.assertIn("Total des valeurs manquantes", labels_fr)
        self.assertIn("Valeurs manquantes par colonne", labels_fr)
        self.assertIn("Valeurs inconnues par colonne", labels_fr)
        self.assertIn("Emails : valides + invalides + inconnus = total", labels_fr)
        self.assertIn("Total missing values", labels_en)
        self.assertIn("Missing values by column", labels_en)

        self.assertFalse(
            any("missing values" in label for label in labels_fr),
            "Le contrôle de cohérence reste partiellement en anglais.",
        )

    def test_consistency_details_are_translated(self):
        frame = self.sample_frame()
        detection = build_detection(frame)

        with translation.override("fr"):
            details = [
                check["detail"]
                for check in verify_consistency(frame, detection=detection)["checks"]
            ]

        self.assertTrue(any(detail.startswith("Annoncé ") for detail in details))
        self.assertFalse(any("Reported" in detail for detail in details))

    def test_score_explanations_follow_the_active_language(self):
        entries = [
            {"type": "warn", "code": "missing_values", "params": {"count": 3}},
            {"type": "ok", "code": "no_exact_duplicates", "params": {}},
        ]

        with translation.override("fr"):
            fr = [item["text"] for item in render_score_explanations(entries)]
        with translation.override("en"):
            en = [item["text"] for item in render_score_explanations(entries)]

        self.assertEqual(fr[0], "3 valeur(s) manquante(s)")
        self.assertEqual(fr[1], "Aucun doublon exact")
        self.assertEqual(en[0], "3 missing value(s)")
        self.assertEqual(en[1], "No exact duplicates")

    def test_correction_types_follow_the_active_language(self):
        codes = ["doublon", "casse", "email"]

        with translation.override("fr"):
            fr = render_correction_types(codes)
        with translation.override("en"):
            en = render_correction_types(codes)

        self.assertEqual(fr, ["Doublon", "Casse", "Courriel"])
        self.assertEqual(en, ["Duplicate", "Case", "Email"])

    def test_french_catalog_only_holds_english_sources(self):
        from tools.translations import CATALOGS
        from tools.translations.french_source import FRENCH_SOURCE_TRANSLATIONS

        self.assertEqual(set(FRENCH_SOURCE_TRANSLATIONS), {"fr"})

        for msgid, msgstr in FRENCH_SOURCE_TRANSLATIONS["fr"].items():
            self.assertNotEqual(
                msgid,
                msgstr,
                f"« {msgid} » est identique dans les deux langues : inutile ici.",
            )
            self.assertEqual(CATALOGS["fr"][msgid], msgstr)

    def test_other_languages_keep_their_own_wording(self):
        from django.utils.translation import gettext as _

        with translation.override("de"):
            self.assertEqual(_("Total missing values"), "Fehlende Werte insgesamt")
        with translation.override("es"):
            self.assertNotEqual(_("Total missing values"), "Total missing values")

    def test_plural_forms_never_fall_back_to_the_source_language(self):
        """Chaque langue fournit toutes les formes plurielles déclarées.

        Les catalogues ne déclarent souvent que le singulier d'un msgid
        pluriel. Sans complétion, ``msgstr[0]`` seul est écrit dans le ``.mo``
        et ``gettext`` retombe sur le msgid — donc sur le français — dès que
        la langue demande une autre forme.
        """
        from django.conf import settings

        msgid = "%(counter)s valide,"
        plural = "%(counter)s valides,"

        for code, _name in settings.LANGUAGES:
            if code == "fr":
                continue
            with translation.override(code):
                for count in (1, 2, 5, 21, 100):
                    rendered = translation.ngettext(msgid, plural, count)
                    self.assertNotIn(
                        "valide",
                        rendered,
                        f"« {code} » retombe sur le français pour n={count}.",
                    )

    def test_plural_forms_are_written_for_every_declared_form(self):
        from tools.i18n_build import plural_count, plural_value

        self.assertEqual(plural_count("en"), 2)
        self.assertEqual(plural_count("ru"), 3)
        self.assertEqual(plural_count("ar"), 6)
        self.assertEqual(plural_count("ja"), 1)

        self.assertEqual(plural_value("seul", "en"), ["seul", "seul"])
        self.assertEqual(plural_value(("un", "plusieurs"), "en"), ["un", "plusieurs"])
        self.assertEqual(plural_value(("un", "plusieurs"), "ja"), ["un"])
        self.assertEqual(
            plural_value("seul", "ru"), ["seul", "seul", "seul"]
        )


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


# ---------------------------------------------------------------------------
# Collaboration : rôles, partage, versions, planification, lots
# ---------------------------------------------------------------------------


class RolePermissionTests(TestCase):
    """Le rôle décide de ce que le compte peut faire, côté serveur."""

    def setUp(self):
        self.admin = User.objects.create_user("roleadmin", password=PRO_USER_PASSWORD)
        self.admin.profile.role = Profile.Role.ADMIN
        self.admin.profile.save()
        self.editor = User.objects.create_user("roleeditor", password=PRO_USER_PASSWORD)
        self.viewer = User.objects.create_user("roleviewer", password=PRO_USER_PASSWORD)
        self.viewer.profile.role = Profile.Role.VIEWER
        self.viewer.profile.save()
        self.data_file = make_cleaned_file(self.editor)
        # Un second nettoyage sans option laisse le fichier « propre » : les
        # tests de refus peuvent alors prouver qu'aucune écriture n'a eu lieu.
        run_cleaning(self.data_file, {})
        self.data_file.refresh_from_db()

    def test_default_role_is_editor(self):
        self.assertEqual(self.editor.profile.role, Profile.Role.EDITOR)

    def test_role_helpers_agree_with_the_stored_role(self):
        self.assertTrue(permissions_service.is_admin(self.admin))
        self.assertFalse(permissions_service.is_admin(self.editor))
        self.assertTrue(permissions_service.can_edit(self.editor))
        self.assertFalse(permissions_service.can_edit(self.viewer))

    def test_a_superuser_is_always_an_admin(self):
        root = User.objects.create_superuser("roleroot", password=PRO_USER_PASSWORD)
        self.assertTrue(permissions_service.is_admin(root))
        self.assertTrue(permissions_service.can_edit(root))

    def test_an_anonymous_visitor_has_no_role(self):
        self.assertIsNone(permissions_service.role_of(AnonymousUser()))

    def test_a_viewer_cannot_clean_a_dataset(self):
        self.client.force_login(self.viewer)
        before = self.data_file.changes_count
        versions_before = self.data_file.versions.count()
        response = self.client.post(
            reverse("core:dataset_detail", args=[self.data_file.pk]),
            {"trim_whitespace": "on", "action": "clean"},
        )
        self.assertEqual(response.status_code, 302)
        self.data_file.refresh_from_db()
        self.assertEqual(self.data_file.changes_count, before)
        self.assertEqual(self.data_file.versions.count(), versions_before)

    def test_a_viewer_cannot_preview_a_cleaning(self):
        self.client.force_login(self.viewer)
        response = self.client.post(
            reverse("core:dataset_detail", args=[self.data_file.pk]),
            {"trim_whitespace": "on", "action": "preview"},
        )
        self.assertEqual(response.status_code, 302)

    def test_a_viewer_cannot_delete_a_dataset(self):
        self.client.force_login(self.viewer)
        response = self.client.post(
            reverse("core:delete_dataset", args=[self.data_file.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(DataFile.objects.filter(pk=self.data_file.pk).exists())

    def test_a_viewer_cannot_create_a_cleaning_rule(self):
        self.client.force_login(self.viewer)
        self.client.post(
            reverse("core:rules_list"),
            {
                "name": "Interdite",
                "operation": CleaningRule.Operation.TRIM_WHITESPACE,
                "column": "nom",
                "is_active": "on",
            },
        )
        self.assertFalse(CleaningRule.objects.filter(name="Interdite").exists())

    def test_a_viewer_cannot_open_the_roles_page(self):
        self.client.force_login(self.viewer)
        response = self.client.get(reverse("core:roles"))
        self.assertEqual(response.status_code, 302)

    def test_an_editor_cannot_open_the_roles_page(self):
        self.client.force_login(self.editor)
        response = self.client.get(reverse("core:roles"))
        self.assertEqual(response.status_code, 302)

    def test_an_admin_opens_the_roles_page(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("core:roles"))
        self.assertEqual(response.status_code, 200)

    def test_an_admin_changes_a_role(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("core:roles"),
            {"user_id": self.viewer.pk, "role": Profile.Role.EDITOR},
        )
        self.assertEqual(response.status_code, 302)
        self.viewer.refresh_from_db()
        self.assertEqual(self.viewer.profile.role, Profile.Role.EDITOR)

    def test_an_unknown_role_is_refused(self):
        self.client.force_login(self.admin)
        self.client.post(
            reverse("core:roles"), {"user_id": self.viewer.pk, "role": "root"}
        )
        self.viewer.refresh_from_db()
        self.assertEqual(self.viewer.profile.role, Profile.Role.VIEWER)

    def test_an_admin_cannot_change_its_own_role(self):
        self.client.force_login(self.admin)
        self.client.post(
            reverse("core:roles"),
            {"user_id": self.admin.pk, "role": Profile.Role.VIEWER},
        )
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.profile.role, Profile.Role.ADMIN)

    def test_the_roles_page_counts_the_files_of_each_account(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("core:roles"))
        rows = {row["user"].pk: row["files_count"] for row in response.context["users"]}
        self.assertEqual(rows[self.editor.pk], 1)
        self.assertEqual(rows[self.viewer.pk], 0)

    def test_an_admin_sees_every_dataset(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("core:dataset_detail", args=[self.data_file.pk]))
        self.assertEqual(response.status_code, 200)

    def test_a_viewer_does_not_see_a_foreign_dataset(self):
        self.client.force_login(self.viewer)
        response = self.client.get(reverse("core:dataset_detail", args=[self.data_file.pk]))
        self.assertEqual(response.status_code, 302)


class DatasetShareTests(TestCase):
    """Le partage ouvre un accès en lecture, nominatif ou par lien public."""

    def setUp(self):
        self.owner = User.objects.create_user("shareowner", password=PRO_USER_PASSWORD)
        self.guest = User.objects.create_user("shareguest", password=PRO_USER_PASSWORD)
        self.data_file = make_cleaned_file(self.owner)

    def _share(self, **kwargs):
        defaults = {
            "data_file": self.data_file,
            "created_by": self.owner,
            "token": permissions_service.new_share_token(),
        }
        defaults.update(kwargs)
        return DatasetShare.objects.create(**defaults)

    def test_the_owner_opens_the_share_page(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:share_dataset", args=[self.data_file.pk]))
        self.assertEqual(response.status_code, 200)

    def test_a_recipient_cannot_manage_the_shares(self):
        self._share(shared_with=self.guest, permission=DatasetShare.Permission.VIEW)
        self.client.force_login(self.guest)
        response = self.client.get(reverse("core:share_dataset", args=[self.data_file.pk]))
        self.assertEqual(response.status_code, 302)

    def test_a_named_share_grants_read_access(self):
        self._share(shared_with=self.guest, permission=DatasetShare.Permission.VIEW)
        self.client.force_login(self.guest)
        response = self.client.get(reverse("core:dataset_detail", args=[self.data_file.pk]))
        self.assertEqual(response.status_code, 200)

    def test_a_view_share_does_not_allow_downloading(self):
        self._share(shared_with=self.guest, permission=DatasetShare.Permission.VIEW)
        self.client.force_login(self.guest)
        for name in (
            "core:download_cleaned",
            "core:download_original",
            "core:download_report",
            "core:download_report_html",
            "core:download_changelog",
            "core:download_json",
        ):
            with self.subTest(view=name):
                response = self.client.get(reverse(name, args=[self.data_file.pk]))
                self.assertEqual(response.status_code, 302)

    def test_a_download_share_allows_downloading(self):
        self._share(shared_with=self.guest, permission=DatasetShare.Permission.DOWNLOAD)
        self.client.force_login(self.guest)
        for name in (
            "core:download_cleaned",
            "core:download_original",
            "core:download_report",
            "core:download_report_html",
            "core:download_changelog",
            "core:download_json",
        ):
            with self.subTest(view=name):
                response = self.client.get(reverse(name, args=[self.data_file.pk]))
                self.assertEqual(response.status_code, 200)

    def test_a_view_share_still_allows_reading_the_report(self):
        self._share(shared_with=self.guest, permission=DatasetShare.Permission.VIEW)
        self.client.force_login(self.guest)
        response = self.client.get(reverse("core:view_report", args=[self.data_file.pk]))
        self.assertEqual(response.status_code, 200)

    def test_revoking_a_share_removes_the_access(self):
        share = self._share(
            shared_with=self.guest, permission=DatasetShare.Permission.VIEW
        )
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("core:share_revoke", args=[self.data_file.pk, share.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(DatasetShare.objects.filter(pk=share.pk).exists())
        self.client.force_login(self.guest)
        response = self.client.get(reverse("core:dataset_detail", args=[self.data_file.pk]))
        self.assertEqual(response.status_code, 302)

    def test_an_expired_share_no_longer_grants_access(self):
        self._share(
            shared_with=self.guest,
            permission=DatasetShare.Permission.VIEW,
            expires_at=timezone.now() - timedelta(hours=1),
        )
        self.client.force_login(self.guest)
        response = self.client.get(reverse("core:dataset_detail", args=[self.data_file.pk]))
        self.assertEqual(response.status_code, 302)

    def test_a_public_link_is_readable_without_an_account(self):
        share = self._share(
            shared_with=None, permission=DatasetShare.Permission.DOWNLOAD
        )
        response = self.client.get(reverse("core:shared_dataset", args=[share.token]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["shared_view"])
        self.assertIn("preview_rows", response.context)

    def test_a_public_link_downloads_the_cleaned_file(self):
        share = self._share(
            shared_with=None, permission=DatasetShare.Permission.DOWNLOAD
        )
        response = self.client.get(
            reverse("core:shared_dataset_download", args=[share.token])
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])

    def test_a_public_link_without_download_right_redirects(self):
        share = self._share(shared_with=None, permission=DatasetShare.Permission.VIEW)
        response = self.client.get(
            reverse("core:shared_dataset_download", args=[share.token])
        )
        self.assertEqual(response.status_code, 302)

    def test_an_unknown_token_is_refused(self):
        response = self.client.get(reverse("core:shared_dataset", args=["inconnu"]))
        self.assertEqual(response.status_code, 302)

    def test_an_expired_public_link_is_refused(self):
        share = self._share(
            shared_with=None,
            permission=DatasetShare.Permission.DOWNLOAD,
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        response = self.client.get(reverse("core:shared_dataset", args=[share.token]))
        self.assertEqual(response.status_code, 302)

    def test_a_revoked_public_link_is_refused(self):
        share = self._share(
            shared_with=None,
            permission=DatasetShare.Permission.DOWNLOAD,
            is_active=False,
        )
        response = self.client.get(reverse("core:shared_dataset", args=[share.token]))
        self.assertEqual(response.status_code, 302)

    def test_the_share_form_refuses_sharing_with_oneself(self):
        form = ShareForm(
            data={"shared_with": self.owner.pk, "permission": "view"},
            data_file=self.data_file,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("shared_with", form.errors)

    def test_the_share_form_refuses_a_duplicate_recipient(self):
        self._share(shared_with=self.guest, permission=DatasetShare.Permission.VIEW)
        form = ShareForm(
            data={"shared_with": self.guest.pk, "permission": "view"},
            data_file=self.data_file,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("shared_with", form.errors)

    def test_the_share_form_accepts_a_public_link(self):
        form = ShareForm(
            data={"public_link": "on", "permission": "download"},
            data_file=self.data_file,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data["shared_with"])

    def test_two_share_tokens_never_collide(self):
        tokens = {permissions_service.new_share_token() for _ in range(50)}
        self.assertEqual(len(tokens), 50)


class DatasetVersionTests(TestCase):
    """Chaque nettoyage archivé devient une version comparable et restaurable."""

    def setUp(self):
        self.user = User.objects.create_user("veruser", password=PRO_USER_PASSWORD)
        self.data_file = make_cleaned_file(self.user)

    def test_a_cleaning_run_records_a_version(self):
        versions = list(self.data_file.versions.values_list("number", flat=True))
        self.assertEqual(versions, [1])

    def test_the_version_keeps_the_quality_scores(self):
        version = self.data_file.versions.get(number=1)
        self.assertEqual(version.quality_after, self.data_file.quality_after)
        self.assertEqual(version.rows_count, self.data_file.rows_count)

    def test_the_version_stores_operation_codes_not_translated_text(self):
        version = self.data_file.versions.get(number=1)
        codes = [entry[0] for entry in version.operations]
        self.assertIn("trim_whitespace", codes)

    def test_a_second_run_increments_the_number(self):
        run_cleaning(self.data_file, {"normalize_case": True})
        self.data_file.refresh_from_db()
        self.assertEqual(
            list(self.data_file.versions.values_list("number", flat=True)), [2, 1]
        )

    def test_next_number_follows_the_highest_version(self):
        self.assertEqual(version_service.next_number(self.data_file), 2)
        run_cleaning(self.data_file, {"normalize_case": True})
        self.data_file.refresh_from_db()
        self.assertEqual(version_service.next_number(self.data_file), 3)

    def test_a_preview_does_not_record_a_version(self):
        preview_cleaning(self.data_file, {"normalize_case": True})
        self.assertEqual(self.data_file.versions.count(), 1)

    def test_the_versions_page_lists_the_history(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("core:dataset_versions", args=[self.data_file.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["entries"]), 1)

    def test_the_versions_page_renders_translated_operations(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("core:dataset_versions", args=[self.data_file.pk])
        )
        labels = [entry["operations"] for entry in response.context["entries"]]
        self.assertTrue(labels[0])

    def test_comparing_two_versions_reports_the_delta(self):
        run_cleaning(self.data_file, {"normalize_case": True})
        self.data_file.refresh_from_db()
        before = self.data_file.versions.get(number=1)
        after = self.data_file.versions.get(number=2)
        comparison = version_service.compare_versions(before, after)
        self.assertIn("indicators", comparison)
        self.assertIn("delta", comparison)

    def test_the_compare_page_accepts_two_versions(self):
        run_cleaning(self.data_file, {"normalize_case": True})
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("core:version_compare", args=[self.data_file.pk]),
            {"before": 1, "after": 2},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["before"].number, 1)
        self.assertEqual(response.context["after"].number, 2)

    def test_the_compare_page_falls_back_on_unknown_numbers(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("core:version_compare", args=[self.data_file.pk]),
            {"before": 99, "after": "abc"},
        )
        self.assertEqual(response.status_code, 200)

    def test_the_compare_page_redirects_without_any_version(self):
        empty = DataFile.objects.create(
            file=make_upload(), original_name="vide.csv", owner=self.user
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:version_compare", args=[empty.pk]))
        self.assertEqual(response.status_code, 302)

    def test_downloading_a_version_returns_its_file(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("core:version_download", args=[self.data_file.pk, 1])
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])

    def test_restoring_a_version_rewrites_the_current_file(self):
        version = self.data_file.versions.get(number=1)
        # Un second passage avec une option supplémentaire produit un fichier
        # différent : la restauration doit ramener exactement celui de la v1.
        run_cleaning(self.data_file, {"normalize_case": True})
        self.data_file.refresh_from_db()
        self.assertNotEqual(
            Path(self.data_file.cleaned_file.path).read_bytes(),
            Path(version.cleaned_file.path).read_bytes(),
        )
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("core:version_restore", args=[self.data_file.pk, 1])
        )
        self.assertEqual(response.status_code, 302)
        self.data_file.refresh_from_db()
        self.assertEqual(
            Path(self.data_file.cleaned_file.path).read_bytes(),
            Path(version.cleaned_file.path).read_bytes(),
        )
        self.assertEqual(self.data_file.changes_count, version.changes_count)

    def test_a_viewer_cannot_restore_a_version(self):
        viewer = User.objects.create_user("verviewer", password=PRO_USER_PASSWORD)
        viewer.profile.role = Profile.Role.VIEWER
        viewer.profile.save()
        DatasetShare.objects.create(
            data_file=self.data_file,
            shared_with=viewer,
            permission=DatasetShare.Permission.DOWNLOAD,
            token=permissions_service.new_share_token(),
            created_by=self.user,
        )
        self.client.force_login(viewer)
        response = self.client.post(
            reverse("core:version_restore", args=[self.data_file.pk, 1])
        )
        self.assertEqual(response.status_code, 302)

    def test_a_view_only_share_cannot_download_a_version(self):
        guest = User.objects.create_user("verguest", password=PRO_USER_PASSWORD)
        DatasetShare.objects.create(
            data_file=self.data_file,
            shared_with=guest,
            permission=DatasetShare.Permission.VIEW,
            token=permissions_service.new_share_token(),
            created_by=self.user,
        )
        self.client.force_login(guest)
        response = self.client.get(
            reverse("core:version_download", args=[self.data_file.pk, 1])
        )
        self.assertEqual(response.status_code, 302)

    def test_a_failed_cleaning_does_not_record_a_version(self):
        broken = DataFile.objects.create(
            file=make_upload(), original_name="casse.csv", owner=self.user
        )
        with mock.patch(
            "core.services.pipeline.read_dataframe", side_effect=ValueError("illisible")
        ):
            with self.assertRaises(ValueError):
                run_cleaning(broken, {"trim_whitespace": True})
        self.assertEqual(broken.versions.count(), 0)

    def test_version_numbers_are_unique_per_dataset(self):
        with self.assertRaises(Exception):
            DatasetVersion.objects.create(
                data_file=self.data_file,
                number=1,
                created_by=self.user,
            )


class CleaningScheduleTests(TestCase):
    """Les nettoyages récurrents sont pilotés par une commande, pas un démon."""

    def setUp(self):
        self.user = User.objects.create_user("scheduser", password=PRO_USER_PASSWORD)
        self.data_file = make_cleaned_file(self.user)

    def _create(self, **kwargs):
        defaults = {
            "data_file": self.data_file,
            "owner": self.user,
            "frequency": CleaningSchedule.Frequency.DAILY,
            "options": {"trim_whitespace": True},
            "rule_ids": [],
            "next_run_at": timezone.now(),
        }
        defaults.update(kwargs)
        return CleaningSchedule.objects.create(**defaults)

    def test_the_schedules_page_renders(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:schedules"))
        self.assertEqual(response.status_code, 200)

    def test_creating_a_schedule_from_the_page(self):
        self.client.force_login(self.user)
        before = timezone.now()
        response = self.client.post(
            reverse("core:schedules"),
            {"data_file": self.data_file.pk, "frequency": "daily", "trim_whitespace": "on"},
        )
        self.assertEqual(response.status_code, 302)
        schedule = CleaningSchedule.objects.get()
        self.assertTrue(schedule.options["trim_whitespace"])
        self.assertGreaterEqual(schedule.next_run_at, before)

    def test_a_viewer_cannot_create_a_schedule(self):
        viewer = User.objects.create_user("schedviewer", password=PRO_USER_PASSWORD)
        viewer.profile.role = Profile.Role.VIEWER
        viewer.profile.save()
        self.client.force_login(viewer)
        self.client.post(
            reverse("core:schedules"),
            {"data_file": self.data_file.pk, "frequency": "daily"},
        )
        self.assertEqual(CleaningSchedule.objects.count(), 0)

    def test_the_next_run_is_computed_from_the_frequency(self):
        schedule = self._create(frequency=CleaningSchedule.Frequency.WEEKLY)
        start = timezone.now()
        following = schedule.compute_next_run(start)
        self.assertGreaterEqual(following - start, timedelta(days=6))

    def test_toggling_a_schedule_suspends_it(self):
        schedule = self._create()
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("core:schedule_toggle", args=[schedule.pk])
        )
        self.assertEqual(response.status_code, 302)
        schedule.refresh_from_db()
        self.assertFalse(schedule.is_active)

    def test_reactivating_a_late_schedule_moves_the_next_run_forward(self):
        schedule = self._create(next_run_at=timezone.now() - timedelta(days=3))
        schedule.is_active = False
        schedule.save(update_fields=["is_active"])
        self.client.force_login(self.user)
        self.client.post(reverse("core:schedule_toggle", args=[schedule.pk]))
        schedule.refresh_from_db()
        self.assertTrue(schedule.is_active)
        self.assertGreater(schedule.next_run_at, timezone.now())

    def test_deleting_a_schedule(self):
        schedule = self._create()
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("core:schedule_delete", args=[schedule.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(CleaningSchedule.objects.count(), 0)

    def test_another_account_cannot_touch_the_schedule(self):
        schedule = self._create()
        intruder = User.objects.create_user("schedintruder", password=PRO_USER_PASSWORD)
        self.client.force_login(intruder)
        response = self.client.post(
            reverse("core:schedule_delete", args=[schedule.pk])
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(CleaningSchedule.objects.count(), 1)

    def test_running_a_schedule_now_starts_a_cleaning(self):
        schedule = self._create()
        self.client.force_login(self.user)
        response = self.client.post(reverse("core:schedule_run", args=[schedule.pk]))
        self.assertEqual(response.status_code, 302)
        schedule.refresh_from_db()
        self.assertEqual(schedule.run_count, 1)
        self.assertEqual(schedule.last_status, "started")
        self.assertIsNotNone(schedule.last_run_at)

    def test_due_schedules_only_returns_the_late_ones(self):
        late = self._create(next_run_at=timezone.now() - timedelta(hours=1))
        self._create(next_run_at=timezone.now() + timedelta(days=1))
        due = list(schedule_service.due_schedules())
        self.assertEqual([entry.pk for entry in due], [late.pk])

    def test_a_suspended_schedule_is_never_due(self):
        self._create(
            next_run_at=timezone.now() - timedelta(hours=1), is_active=False
        )
        self.assertEqual(list(schedule_service.due_schedules()), [])

    def test_running_the_due_schedules_advances_the_next_run(self):
        schedule = self._create(next_run_at=timezone.now() - timedelta(hours=1))
        self.assertEqual(schedule_service.run_due_schedules(), 1)
        schedule.refresh_from_db()
        self.assertGreater(schedule.next_run_at, timezone.now())
        self.assertEqual(schedule.run_count, 1)

    def test_the_management_command_reports_nothing_to_do(self):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("run_schedules", "--dry-run", stdout=out)
        self.assertIn("Aucune", out.getvalue())

    def test_the_management_command_runs_a_due_schedule(self):
        from io import StringIO

        from django.core.management import call_command

        schedule = self._create(next_run_at=timezone.now() - timedelta(hours=1))
        out = StringIO()
        call_command("run_schedules", stdout=out)
        schedule.refresh_from_db()
        self.assertEqual(schedule.run_count, 1)

    def test_the_management_command_dry_run_changes_nothing(self):
        from io import StringIO

        from django.core.management import call_command

        schedule = self._create(next_run_at=timezone.now() - timedelta(hours=1))
        call_command("run_schedules", "--dry-run", stdout=StringIO())
        schedule.refresh_from_db()
        self.assertEqual(schedule.run_count, 0)

    def test_the_schedule_keeps_the_saved_rules(self):
        rule = CleaningRule.objects.create(
            owner=self.user,
            name="Regle",
            operation=CleaningRule.Operation.TRIM_WHITESPACE,
            column="nom",
        )
        self.client.force_login(self.user)
        self.client.post(
            reverse("core:schedules"),
            {
                "data_file": self.data_file.pk,
                "frequency": "daily",
                "trim_whitespace": "on",
                "rules": [rule.pk],
            },
        )
        schedule = CleaningSchedule.objects.get()
        self.assertEqual(schedule.rule_ids, [rule.pk])


class BatchCleaningTests(TestCase):
    """Le lot réutilise le pipeline unitaire, en série et sous plafond."""

    def setUp(self):
        self.user = User.objects.create_user("batchuser", password=PRO_USER_PASSWORD)
        self.files = [
            DataFile.objects.create(
                file=make_upload(f"lot{i}.csv"), original_name=f"lot{i}.csv", owner=self.user
            )
            for i in range(3)
        ]

    def test_the_batch_page_renders(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:batch_cleaning"))
        self.assertEqual(response.status_code, 200)

    def test_a_viewer_cannot_start_a_batch(self):
        viewer = User.objects.create_user("batchviewer", password=PRO_USER_PASSWORD)
        viewer.profile.role = Profile.Role.VIEWER
        viewer.profile.save()
        self.client.force_login(viewer)
        response = self.client.post(
            reverse("core:batch_cleaning"),
            {"files": [self.files[0].pk], "trim_whitespace": "on"},
        )
        self.assertEqual(response.status_code, 302)
        self.files[0].refresh_from_db()
        self.assertEqual(self.files[0].status, DataFile.Status.UPLOADED)

    def test_the_batch_starts_every_selected_file(self):
        result = batch_service.start_batch(
            self.files, {"trim_whitespace": True}, session_key="k", language="fr"
        )
        self.assertEqual(result["started"], 3)
        self.assertEqual(result["skipped"], [])

    def test_the_batch_refuses_more_than_the_cap(self):
        many = [
            DataFile.objects.create(
                file=make_upload(f"gros{i}.csv"), original_name=f"gros{i}.csv", owner=self.user
            )
            for i in range(batch_service.MAX_BATCH_SIZE + 5)
        ]
        result = batch_service.start_batch(
            many, {"trim_whitespace": True}, session_key="k", language="fr"
        )
        self.assertEqual(result["started"], batch_service.MAX_BATCH_SIZE)
        self.assertEqual(len(result["skipped"]), 5)

    def test_a_failing_file_does_not_stop_the_batch(self):
        with mock.patch(
            "core.services.batch.start_cleaning",
            side_effect=[None, RuntimeError("boum"), None],
        ):
            result = batch_service.start_batch(
                self.files, {"trim_whitespace": True}, session_key="k", language="fr"
            )
        self.assertEqual(result["started"], 2)
        self.assertEqual(len(result["skipped"]), 1)

    def test_the_batch_form_only_offers_visible_files(self):
        other = User.objects.create_user("batchother", password=PRO_USER_PASSWORD)
        foreign = DataFile.objects.create(
            file=make_upload("etranger.csv"), original_name="etranger.csv", owner=other
        )
        form = BatchCleaningForm(files=DataFile.objects.filter(owner=self.user))
        offered = set(form.fields["files"].queryset.values_list("pk", flat=True))
        self.assertNotIn(foreign.pk, offered)
        self.assertEqual(offered, {entry.pk for entry in self.files})

    def test_the_batch_form_requires_at_least_one_file(self):
        form = BatchCleaningForm(
            data={"trim_whitespace": "on"}, files=DataFile.objects.filter(owner=self.user)
        )
        self.assertFalse(form.is_valid())
        self.assertIn("files", form.errors)

    def test_the_batch_options_match_the_single_file_form(self):
        form = BatchCleaningForm(files=DataFile.objects.filter(owner=self.user))
        single = CleaningOptionsForm(columns=["nom"])
        self.assertEqual(set(form.fields), set(single.fields) | {"files"})
