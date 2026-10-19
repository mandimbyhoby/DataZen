"""Formulaires de l'application DataZen."""
from django import forms
from django.contrib.auth.forms import PasswordChangeForm, UserCreationForm
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _

from .models import (
    ApiToken,
    CleaningRule,
    CleaningSchedule,
    DataFile,
    DatasetShare,
    Profile,
    Webhook,
)

# Noms de colonnes candidats pour servir de clé de déduplication par défaut
# (une valeur censée être unique par enregistrement : email, téléphone…).
KEY_COLUMN_CANDIDATES = (
    "email",
    "e-mail",
    "email_address",
    "mail",
    "courriel",
    "telephone",
    "téléphone",
    "phone",
    "tel",
    "client_id",
    "code_client",
)


def detect_key_column(columns):
    """Renvoie la première colonne ressemblant à une clé unique, sinon None."""
    lowered = {str(c).strip().lower(): c for c in columns}
    for candidate in KEY_COLUMN_CANDIDATES:
        if candidate in lowered:
            return lowered[candidate]
    return None


class DataFileUploadForm(forms.ModelForm):
    """Formulaire de téléversement d'un fichier de données (CSV / Excel)."""

    MAX_FILE_SIZE = 20 * 1024 * 1024
    SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls"}

    class Meta:
        model = DataFile
        fields = ["file"]
        widgets = {
            "file": forms.ClearableFileInput(
                attrs={
                    "class": "dz-file-input",
                    "accept": ".csv,.xlsx,.xls",
                }
            ),
        }

    def clean_file(self):
        uploaded_file = self.cleaned_data["file"]
        extension = "." + uploaded_file.name.rsplit(".", 1)[-1].lower() if "." in uploaded_file.name else ""
        if extension not in self.SUPPORTED_EXTENSIONS:
            raise forms.ValidationError(_("Choisissez un fichier CSV ou Excel (.csv, .xlsx, .xls)."))
        if uploaded_file.size > self.MAX_FILE_SIZE:
            raise forms.ValidationError(_("Le fichier ne doit pas dépasser 20 Mo."))
        return uploaded_file

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.original_name = self.cleaned_data["file"].name
        if commit:
            instance.save()
        return instance


class CleaningOptionsForm(forms.Form):
    """Options de nettoyage appliquées aux données."""

    remove_duplicates = forms.BooleanField(
        required=False,
        initial=False,
        label=_("Supprimer les doublons (confirmation requise)"),
        help_text=_(
            "Les doublons sont signalés mais jamais supprimés automatiquement. "
            "Cochez cette case pour les supprimer explicitement."
        ),
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    dedupe_column = forms.ChoiceField(
        required=False,
        label=_("Colonne clé pour la déduplication"),
        choices=[],
        help_text=_(
            "Choisissez une colonne unique (ex. email) pour fusionner les "
            "variantes d'un même enregistrement (Alice / alice). Laissez vide "
            "pour ne supprimer que les lignes 100 % identiques."
        ),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    dedupe_ignore_case = forms.BooleanField(
        required=False,
        initial=True,
        label=_("Ignorer la casse (Alice = alice)"),
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    trim_whitespace = forms.BooleanField(
        required=False,
        initial=True,
        label=_("Supprimer les espaces superflus"),
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    normalize_case = forms.BooleanField(
        required=False,
        initial=True,
        label=_("Normaliser la casse (emails en minuscules, noms en Capitales)"),
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    normalize_phones = forms.BooleanField(
        required=False,
        initial=True,
        label=_("Normaliser les téléphones (06XXXXXXXX)"),
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    normalize_dates = forms.BooleanField(
        required=False,
        initial=True,
        label=_("Normaliser les dates (AAAA-MM-JJ)"),
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    normalize_emails = forms.BooleanField(
        required=False,
        initial=True,
        label=_("Valider et corriger les emails (erreurs évidentes seulement)"),
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    normalize_salaries = forms.BooleanField(
        required=False,
        initial=True,
        label=_("Convertir les montants en valeurs numériques"),
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    fill_missing = forms.BooleanField(
        required=False,
        initial=False,
        label=_("Remplacer les valeurs manquantes"),
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    fill_missing_value = forms.CharField(
        required=False,
        label=_("Valeur de remplacement"),
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": _("ex : 0 ou Inconnu"),
            }
        ),
    )
    regex_rules = forms.CharField(
            required=False,
            label=_("Règles de validation regex personnalisées"),
            help_text=_(
                "Une règle par ligne, au format « colonne:motif ». Exemple : "
                "« code_postal:^\\d{5}$ ». Les valeurs ne correspondant pas au "
                "motif seront signalées (jamais modifiées)."
            ),
            widget=forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "code_postal:^\\d{5}$\nreference:^[A-Z]{2}-\\d+$",
                }
            ),
        )
    anonymize = forms.BooleanField(
            required=False,
            initial=False,
            label=_("Anonymiser les données sensibles (noms, emails, téléphones)"),
            help_text=_(
                "Remplace les noms, emails et téléphones par des pseudonymes "
                "déterministes (même valeur → même pseudonyme). Les relations "
                "entre lignes sont préservées."
            ),
            widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        )

    def __init__(self, *args, columns=None, **kwargs):
        super().__init__(*args, **kwargs)
        if columns is not None:
            self.fields["dedupe_column"].choices = [
                ("", _("— Toutes les colonnes —")),
                *[(c, c) for c in columns],
            ]
            # Présélectionne une colonne clé pertinente (ex. email) pour que
            # la déduplication fusionne automatiquement les variantes d'un
            # même enregistrement (Alice / alice).
            key = detect_key_column(columns)
            if key:
                self.initial["dedupe_column"] = key


class SignUpForm(UserCreationForm):
    """Formulaire d'inscription (nom d'utilisateur + mot de passe)."""

    email = forms.EmailField(
        required=False,
        label=_("Adresse email"),
        widget=forms.EmailInput(attrs={"class": "form-control"}),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("username", "password1", "password2"):
            self.fields[name].widget.attrs["class"] = "form-control"


class CleaningRuleForm(forms.ModelForm):
    """Création d'une règle de nettoyage personnalisée et réutilisable."""

    class Meta:
        model = CleaningRule
        fields = ["name", "operation", "column", "value", "is_active"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": _("ex : Emails en minuscules"),
                }
            ),
            "operation": forms.Select(attrs={"class": "form-select"}),
            "column": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": _("ex : email (vide = toutes les colonnes)"),
                }
            ),
            "value": forms.TextInput(
                attrs={"class": "form-control", "placeholder": _("ex : 0 ou Inconnu")}
            ),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class ProfileForm(forms.ModelForm):
    """Édition du profil : identité, photo et présentation.

    Les champs `first_name`, `last_name` et `email` appartiennent au modèle
    `User` : ils sont déclarés ici pour être enregistrés dans la même
    transaction que le profil.
    """

    MAX_AVATAR_MB = 5
    ALLOWED_AVATAR_TYPES = ("image/jpeg", "image/png", "image/webp", "image/gif")

    first_name = forms.CharField(
        required=False,
        max_length=150,
        label=_("Prénom"),
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "given-name"}),
    )
    last_name = forms.CharField(
        required=False,
        max_length=150,
        label=_("Nom"),
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "family-name"}),
    )
    email = forms.EmailField(
        required=False,
        label=_("Adresse email"),
        widget=forms.EmailInput(attrs={"class": "form-control", "autocomplete": "email"}),
    )

    class Meta:
        model = Profile
        fields = [
            "avatar",
            "bio",
            "job_title",
            "organisation",
            "location",
            "website",
            "theme_preference",
            "date_format",
            "email_notifications",
            "public_profile",
            "retention_days",
            "auto_purge",
        ]
        widgets = {
            "avatar": forms.ClearableFileInput(
                attrs={"class": "form-control", "accept": "image/*"}
            ),
            "bio": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "maxlength": 500,
                    "placeholder": _("Quelques mots sur vous, votre équipe, vos jeux de données…"),
                }
            ),
            "job_title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "autocomplete": "organization-title",
                    "placeholder": _("Analyste de données"),
                }
            ),
            "organisation": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "autocomplete": "organization",
                    "placeholder": _("Nom de votre entreprise ou équipe"),
                }
            ),
            "location": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "autocomplete": "address-level2",
                    "placeholder": _("Antananarivo, Madagascar"),
                }
            ),
            "website": forms.URLInput(
                attrs={
                    "class": "form-control",
                    "autocomplete": "url",
                    "placeholder": _("https://exemple.com"),
                }
            ),
            "theme_preference": forms.Select(attrs={"class": "form-select"}),
            "date_format": forms.Select(attrs={"class": "form-select"}),
            "email_notifications": forms.CheckboxInput(
                attrs={"class": "form-check-input", "role": "switch"}
            ),
            "public_profile": forms.CheckboxInput(
                attrs={"class": "form-check-input", "role": "switch"}
            ),
            "retention_days": forms.NumberInput(
                attrs={"class": "form-control", "min": 0, "max": 3650, "step": 1}
            ),
            "auto_purge": forms.CheckboxInput(
                attrs={"class": "form-check-input", "role": "switch"}
            ),
        }
        labels = {
            "email_notifications": _("Notifications par email"),
            "public_profile": _("Profil public"),
            "retention_days": _("Durée de conservation (jours)"),
            "auto_purge": _("Purger automatiquement"),
        }
        help_texts = {
            "email_notifications": _("Recevoir un message lorsqu'un nettoyage se termine."),
            "public_profile": _("Autoriser les autres utilisateurs à consulter votre profil."),
            "retention_days": _(
                "Fichiers nettoyés plus anciens que cette durée (0 = conservation illimitée)."
            ),
            "auto_purge": _(
                "Supprimer définitivement les fichiers expirés au lieu de les archiver."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.user_id:
            user = self.instance.user
            self.fields["first_name"].initial = user.first_name
            self.fields["last_name"].initial = user.last_name
            self.fields["email"].initial = user.email
        # Les préférences ont une valeur par défaut : un formulaire partiel
        # (tests, envoi sans ces champs) ne doit pas être rejeté.
        self.fields["theme_preference"].required = False
        self.fields["date_format"].required = False
        self.fields["retention_days"].required = False

    def clean_theme_preference(self):
        value = self.cleaned_data.get("theme_preference")
        if value:
            return value
        return self.instance.theme_preference or Profile.Theme.SYSTEM

    def clean_date_format(self):
        value = self.cleaned_data.get("date_format")
        if value:
            return value
        return self.instance.date_format or Profile.DateFormat.DMY

    def clean_retention_days(self):
        value = self.cleaned_data.get("retention_days")
        if value is not None and value != "":
            return value
        return self.instance.retention_days

    def clean_avatar(self):
        avatar = self.cleaned_data.get("avatar")
        # Un fichier déjà enregistré (instance existante) n'est pas revalidé.
        if not avatar or not hasattr(avatar, "content_type"):
            return avatar
        if avatar.content_type not in self.ALLOWED_AVATAR_TYPES:
            raise forms.ValidationError(
                "Format non pris en charge. Utilisez une image JPEG, PNG, WebP ou GIF."
            )
        limit = self.MAX_AVATAR_MB * 1024 * 1024
        if avatar.size > limit:
            raise forms.ValidationError(
                f"L'image ne doit pas dépasser {self.MAX_AVATAR_MB} Mo."
            )
        return avatar

    def save(self, commit=True):
        profile = super().save(commit=commit)
        user = profile.user
        user.first_name = self.cleaned_data.get("first_name", "")
        user.last_name = self.cleaned_data.get("last_name", "")
        user.email = self.cleaned_data.get("email", "")
        if commit:
            user.save(update_fields=["first_name", "last_name", "email"])
        return profile


class StyledPasswordChangeForm(PasswordChangeForm):
    """Formulaire de changement de mot de passe habillé avec Bootstrap.

    Le module JS de bascule d'affichage s'applique automatiquement à tout
    champ `input[type="password"]`, y compris ceux-ci.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
            field.widget.attrs.setdefault("autocomplete", "new-password")
        self.fields["old_password"].widget.attrs["autocomplete"] = "current-password"


class ApiTokenForm(forms.ModelForm):
    """Création d'un jeton d'accès à l'API REST."""

    class Meta:
        model = ApiToken
        fields = ["name", "expires_at"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": _("ex : Intégration Power BI"),
                }
            ),
            "expires_at": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"}
            ),
        }
        labels = {
            "name": _("Nom du jeton"),
            "expires_at": _("Date d'expiration"),
        }
        help_texts = {
            "expires_at": _("Laissez vide pour un jeton sans expiration."),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Un formulaire partiel (tests, envoi sans date) ne doit pas être rejeté.
        self.fields["expires_at"].required = False


class WebhookForm(forms.ModelForm):
    """Création d'un webhook (notification HTTP sortante)."""

    class Meta:
        model = Webhook
        fields = ["name", "url", "event", "secret", "is_active"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": _("ex : Slack — nettoyages"),
                }
            ),
            "url": forms.URLInput(
                attrs={
                    "class": "form-control",
                    "placeholder": _("https://hooks.exemple.com/datazen"),
                }
            ),
            "event": forms.Select(attrs={"class": "form-select"}),
            "secret": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": _("Clé de signature HMAC (facultative)"),
                }
            ),
            "is_active": forms.CheckboxInput(
                attrs={"class": "form-check-input", "role": "switch"}
            ),
        }
        labels = {
            "name": _("Nom"),
            "url": _("URL de destination"),
            "event": _("Événement déclencheur"),
            "secret": _("Clé de signature"),
            "is_active": _("Actif"),
        }
        help_texts = {
            "secret": _("Ajoutée à l'en-tête X-DataZen-Signature (HMAC-SHA256)."),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["secret"].required = False

    def clean_url(self):
        """Valide l'URL de destination (protection SSRF)."""
        from .services.api import WebhookUrlError, validate_webhook_url

        url = self.cleaned_data.get("url", "")
        try:
            return validate_webhook_url(url, resolve=False)
        except WebhookUrlError as exc:
            raise forms.ValidationError(str(exc)) from exc


class ShareForm(forms.Form):
    """Création d'un partage : destinataire nommé **ou** lien public.

    Le formulaire ne devine pas l'intention : cocher « lien public » crée un
    jeton, sinon un destinataire est exigé. Les deux cas restent en lecture
    seule pour le destinataire.
    """

    shared_with = forms.ModelChoiceField(
        required=False,
        queryset=User.objects.none(),
        label=_("Destinataire"),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    public_link = forms.BooleanField(
        required=False,
        label=_("Créer un lien public"),
        help_text=_(
            "Toute personne possédant le lien peut consulter le jeu de données, "
            "sans compte. Le lien est révocable et peut expirer."
        ),
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    permission = forms.ChoiceField(
        choices=DatasetShare.Permission.choices,
        initial=DatasetShare.Permission.VIEW,
        label=_("Droit accordé"),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    expires_at = forms.DateTimeField(
        required=False,
        label=_("Expiration"),
        help_text=_("Laissez vide pour un partage sans expiration."),
        widget=forms.DateTimeInput(
            attrs={"class": "form-control", "type": "datetime-local"}
        ),
    )

    def __init__(self, *args, data_file=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.data_file = data_file
        # On ne propose jamais le propriétaire ni les comptes déjà destinataires
        # d'un partage actif : ces choix n'auraient aucun effet.
        excluded = set()
        if data_file is not None:
            excluded.add(data_file.owner_id)
            excluded.update(
                data_file.shares.exclude(shared_with=None).values_list(
                    "shared_with_id", flat=True
                )
            )
        self.fields["shared_with"].queryset = (
            User.objects.exclude(pk__in=excluded).order_by("username")
            if excluded
            else User.objects.order_by("username")
        )

    def clean(self):
        """Exige soit un destinataire, soit le mode « lien public »."""
        cleaned = super().clean()
        if cleaned.get("public_link"):
            cleaned["shared_with"] = None
        elif not cleaned.get("shared_with"):
            raise forms.ValidationError(
                _("Choisissez un destinataire ou cochez « Créer un lien public ».")
            )
        return cleaned


class _CleaningOptionsMixin:
    """Sépare les options de nettoyage des champs propres au formulaire.

    Les formulaires de lot et de planification réutilisent
    :class:`CleaningOptionsForm` par héritage : les options disponibles, leurs
    valeurs par défaut et leur signification restent donc définies à un seul
    endroit, et un nettoyage par lot ne peut pas diverger d'un nettoyage
    unitaire.
    """

    EXTRA_FIELDS = ()

    def cleaned_options(self):
        """Options de nettoyage prêtes pour le pipeline."""
        return {
            name: value
            for name, value in self.cleaned_data.items()
            if name not in self.EXTRA_FIELDS
        }


class BatchCleaningForm(_CleaningOptionsMixin, CleaningOptionsForm):
    """Nettoyage de plusieurs fichiers avec un jeu d'options commun."""

    EXTRA_FIELDS = ("files",)

    files = forms.ModelMultipleChoiceField(
        queryset=DataFile.objects.none(),
        label=_("Fichiers à nettoyer"),
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
    )

    def __init__(self, *args, files=None, **kwargs):
        super().__init__(*args, **kwargs)
        # La colonne clé de déduplication dépend des colonnes du fichier : elle
        # n'a pas de choix communs à plusieurs fichiers, elle est donc saisie
        # librement (une colonne absente d'un fichier est simplement ignorée).
        self.fields["dedupe_column"] = forms.CharField(
            required=False,
            label=_("Colonne clé pour la déduplication"),
            help_text=_(
                "Nom de la colonne unique (ex. email). Laissez vide pour ne "
                "supprimer que les lignes 100 % identiques. Une colonne absente "
                "d'un fichier est ignorée pour ce fichier."
            ),
            widget=forms.TextInput(attrs={"class": "form-control"}),
        )
        if files is not None:
            self.fields["files"].queryset = files

    def clean_files(self):
        """Refuse un lot vide : sans sélection, rien ne serait lancé."""
        files = self.cleaned_data["files"]
        if not files:
            raise forms.ValidationError(_("Sélectionnez au moins un fichier."))
        return files


class ScheduleForm(_CleaningOptionsMixin, CleaningOptionsForm):
    """Planification récurrente du nettoyage d'un jeu de données."""

    EXTRA_FIELDS = ("data_file", "frequency", "first_run_at", "rules")

    data_file = forms.ModelChoiceField(
        queryset=DataFile.objects.none(),
        label=_("Jeu de données"),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    frequency = forms.ChoiceField(
        choices=CleaningSchedule.Frequency.choices,
        initial=CleaningSchedule.Frequency.WEEKLY,
        label=_("Fréquence"),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    first_run_at = forms.DateTimeField(
        required=False,
        label=_("Première exécution"),
        help_text=_("Laissez vide pour démarrer à la prochaine échéance."),
        widget=forms.DateTimeInput(
            attrs={"class": "form-control", "type": "datetime-local"}
        ),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["dedupe_column"] = forms.CharField(
            required=False,
            label=_("Colonne clé pour la déduplication"),
            widget=forms.TextInput(attrs={"class": "form-control"}),
        )
        if user is not None:
            self.fields["data_file"].queryset = DataFile.objects.filter(owner=user)

    def cleaned_rule_ids(self):
        """Règles personnalisées cochées, conservées par identifiant."""
        return [int(pk) for pk in self.data.getlist("rules") if str(pk).isdigit()]

