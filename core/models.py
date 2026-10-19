"""Modèles de données de l'application DataZen."""
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


def avatar_upload_to(instance, filename):
    """Range les photos de profil par utilisateur, sous un nom unique."""
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    return f"avatars/{instance.user_id}/{uuid4().hex}.{extension}"


class DataFile(models.Model):
    """Fichier de données téléversé en attente de nettoyage."""

    class Status(models.TextChoices):
        UPLOADED = "uploaded", _("Téléversé")
        PROCESSING = "processing", _("En cours de traitement")
        CLEANED = "cleaned", _("Nettoyé")
        ERROR = "error", _("Erreur")

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="data_files",
        null=True,
        blank=True,
        verbose_name=_("Propriétaire"),
    )
    file = models.FileField(upload_to="uploads/%Y/%m/%d/")
    original_name = models.CharField(max_length=255)
    cleaned_file = models.FileField(
        upload_to="cleaned/%Y/%m/%d/",
        blank=True,
        null=True,
        verbose_name=_("Fichier nettoyé"),
    )
    report_file = models.FileField(
        upload_to="reports/%Y/%m/%d/",
        blank=True,
        null=True,
        verbose_name=_("Rapport de nettoyage"),
    )
    change_log_file = models.FileField(
        upload_to="logs/%Y/%m/%d/",
        blank=True,
        null=True,
        verbose_name=_("Journal des modifications"),
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.UPLOADED,
    )
    # Progression du traitement asynchrone (0-100), affichée pendant le
    # nettoyage en arrière-plan.
    progress = models.PositiveSmallIntegerField(default=0)
    error_message = models.TextField(blank=True, default="")

    # Indicateurs de qualité figés au moment du nettoyage : ils alimentent le
    # tableau de bord global sans relire les fichiers à chaque affichage.
    quality_before = models.FloatField(null=True, blank=True)
    quality_after = models.FloatField(null=True, blank=True)
    rows_count = models.PositiveIntegerField(null=True, blank=True)
    columns_count = models.PositiveSmallIntegerField(null=True, blank=True)
    issues_count = models.PositiveIntegerField(null=True, blank=True)
    changes_count = models.PositiveIntegerField(null=True, blank=True)

    # Instantané léger des indicateurs (doublons, erreurs, aberrants…) figé
    # lors du nettoyage. Il permet au tableau de bord global d'agréger les
    # problèmes sans relire chaque fichier.
    metrics = models.JSONField(default=dict, blank=True)

    cleaned_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    archive_exempt_from_auto = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Fichier de données")
        verbose_name_plural = _("Fichiers de données")

    def __str__(self):
        return self.original_name


class CleaningRule(models.Model):
    """Règle de nettoyage personnalisée, réutilisable d'un dataset à l'autre.

    Une règle décrit une opération de nettoyage (déduplication, normalisation
    d'une colonne, remplissage, anonymisation…) que l'utilisateur peut
    appliquer en un clic sur n'importe quel fichier.
    """

    class Operation(models.TextChoices):
        REMOVE_DUPLICATES = "remove_duplicates", _("Supprimer les doublons")
        TRIM_WHITESPACE = "trim_whitespace", _("Supprimer les espaces superflus")
        NORMALIZE_CASE = "normalize_case", _("Normaliser la casse")
        NORMALIZE_EMAILS = "normalize_emails", _("Normaliser les emails")
        NORMALIZE_PHONES = "normalize_phones", _("Normaliser les téléphones")
        NORMALIZE_DATES = "normalize_dates", _("Normaliser les dates")
        NORMALIZE_SALARIES = "normalize_salaries", _("Convertir les montants")
        FILL_MISSING = "fill_missing", _("Remplir les valeurs manquantes")
        ANONYMIZE = "anonymize", _("Anonymiser les données sensibles")

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cleaning_rules",
        null=True,
        blank=True,
        verbose_name=_("Propriétaire"),
    )
    name = models.CharField(max_length=120, verbose_name=_("Nom de la règle"))
    operation = models.CharField(
        max_length=32,
        choices=Operation.choices,
        verbose_name=_("Opération"),
    )
    column = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name=_("Colonne ciblée"),
        help_text=_("Laisser vide pour appliquer à toutes les colonnes."),
    )
    value = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name=_("Valeur"),
        help_text=_("Valeur de remplacement (pour le remplissage)."),
    )
    is_active = models.BooleanField(default=True, verbose_name=_("Active"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = _("Règle de nettoyage")
        verbose_name_plural = _("Règles de nettoyage")

    def __str__(self):
        return self.name


class Profile(models.Model):
    """Informations de profil complétant le compte utilisateur.

    Séparé de `auth.User` pour ne pas dépendre d'un modèle utilisateur
    personnalisé : le profil est créé automatiquement à l'inscription.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
        verbose_name=_("Utilisateur"),
    )
    avatar = models.ImageField(
        upload_to=avatar_upload_to,
        blank=True,
        null=True,
        verbose_name=_("Photo de profil"),
    )
    bio = models.TextField(
        blank=True,
        default="",
        max_length=500,
        verbose_name=_("Présentation"),
    )
    job_title = models.CharField(
        max_length=120,
        blank=True,
        default="",
        verbose_name=_("Fonction"),
    )
    organisation = models.CharField(
        max_length=120,
        blank=True,
        default="",
        verbose_name=_("Organisation"),
    )
    location = models.CharField(
        max_length=120,
        blank=True,
        default="",
        verbose_name=_("Localisation"),
    )
    website = models.URLField(
        blank=True,
        default="",
        max_length=200,
        verbose_name=_("Site web"),
    )

    class Theme(models.TextChoices):
        SYSTEM = "system", _("Système")
        LIGHT = "light", _("Clair")
        DARK = "dark", _("Sombre")

    class DateFormat(models.TextChoices):
        DMY = "d/m/Y", _("JJ/MM/AAAA")
        MDY = "m/d/Y", _("MM/JJ/AAAA")
        YMD = "Y-m-d", _("AAAA-MM-JJ")

    theme_preference = models.CharField(
        max_length=10,
        choices=Theme.choices,
        default=Theme.SYSTEM,
        verbose_name=_("Thème préféré"),
    )
    language = models.CharField(
        max_length=10,
        blank=True,
        default="",
        verbose_name=_("Langue de l'interface"),
        help_text=_("Code de langue (fr, en, es…). Vide = langue de l'application."),
    )
    date_format = models.CharField(
        max_length=10,
        choices=DateFormat.choices,
        default=DateFormat.DMY,
        verbose_name=_("Format de date"),
    )
    email_notifications = models.BooleanField(
        default=True,
        verbose_name=_("Recevoir les notifications par email"),
    )
    public_profile = models.BooleanField(
        default=False,
        verbose_name=_("Profil visible publiquement"),
    )

    class Role(models.TextChoices):
        VIEWER = "viewer", _("Lecteur")
        EDITOR = "editor", _("Éditeur")
        ADMIN = "admin", _("Administrateur")

    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.EDITOR,
        verbose_name=_("Rôle"),
        help_text=_(
            "Lecteur : consultation et téléchargement. "
            "Éditeur : peut aussi nettoyer et supprimer ses fichiers. "
            "Administrateur : gère les rôles et voit tous les fichiers."
        ),
    )
    retention_days = models.PositiveSmallIntegerField(
        default=180,
        verbose_name=_("Durée de conservation (jours)"),
        help_text=_(
            "Les fichiers nettoyés sont archivés puis purgés après cette durée "
            "(0 = conservation illimitée)."
        ),
    )
    auto_purge = models.BooleanField(
        default=False,
        verbose_name=_("Purger automatiquement les fichiers expirés"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Profil")
        verbose_name_plural = _("Profils")

    def __str__(self):
        return f"Profil de {self.user.username}"

    @property
    def initials(self):
        """Initiales de repli quand aucune photo n'est définie."""
        source = self.user.get_full_name() or self.user.username
        parts = [p for p in source.replace("@", " ").replace(".", " ").split() if p]
        if not parts:
            return "?"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()

    @property
    def completion(self):
        """Taux de complétion du profil (0-100) et champs encore manquants."""
        checks = [
            (_("Photo de profil"), bool(self.avatar)),
            (_("Prénom"), bool(self.user.first_name)),
            (_("Nom"), bool(self.user.last_name)),
            (_("Adresse email"), bool(self.user.email)),
            (_("Présentation"), bool(self.bio.strip())),
            (_("Fonction"), bool(self.job_title.strip())),
            (_("Organisation"), bool(self.organisation.strip())),
            (_("Localisation"), bool(self.location.strip())),
            (_("Site web"), bool(self.website.strip())),
        ]
        done = [label for label, ok in checks if ok]
        missing = [label for label, ok in checks if not ok]
        percent = round(len(done) * 100 / len(checks))
        return {"percent": percent, "missing": missing, "done": len(done), "total": len(checks)}

    @property
    def display_name(self):
        """Nom complet si renseigné, sinon le nom d'utilisateur."""
        return self.user.get_full_name() or self.user.username

    def is_admin(self):
        """Un superutilisateur est toujours administrateur."""
        return self.user.is_superuser or self.role == self.Role.ADMIN

    def can_edit(self):
        """Autorise les actions qui transforment les données (nettoyage…)."""
        return self.user.is_superuser or self.role in (self.Role.EDITOR, self.Role.ADMIN)

    def can_delete(self):
        """Autorise la suppression d'un jeu de données."""
        return self.can_edit()


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, created, **kwargs):
    """Garantit qu'un profil existe pour chaque utilisateur."""
    if created:
        Profile.objects.get_or_create(user=instance)


class ActivityLog(models.Model):
    """Journal d'activité : trace les actions utiles de l'utilisateur.

    Chaque entrée décrit une action (téléversement, nettoyage, export,
    suppression…) et, si possible, le fichier concerné. Le journal alimente la
    page « Activité » et le fil des dernières opérations.
    """

    class Action(models.TextChoices):
        UPLOAD = "upload", _("Téléversement")
        CLEAN = "clean", _("Nettoyage")
        DOWNLOAD = "download", _("Téléchargement")
        REPORT = "report", _("Consultation du rapport")
        CHART = "chart", _("Consultation des graphiques")
        RULE_CREATE = "rule_create", _("Création de règle")
        RULE_DELETE = "rule_delete", _("Suppression de règle")
        ARCHIVE = "archive", _("Archivage")
        RESTORE = "restore", _("Restauration")
        DELETE = "delete", _("Suppression")
        LOGIN = "login", _("Connexion")
        API = "api", _("Appel API")
        TOKEN_CREATE = "token_create", _("Création de jeton")
        TOKEN_REVOKE = "token_revoke", _("Révocation de jeton")

    class Level(models.TextChoices):
        INFO = "info", _("Information")
        SUCCESS = "success", _("Succès")
        WARNING = "warning", _("Avertissement")
        DANGER = "danger", _("Erreur")

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="activities",
        null=True,
        blank=True,
        verbose_name=_("Propriétaire"),
    )
    data_file = models.ForeignKey(
        DataFile,
        on_delete=models.SET_NULL,
        related_name="activities",
        null=True,
        blank=True,
        verbose_name=_("Fichier"),
    )
    action = models.CharField(
        max_length=24, choices=Action.choices, verbose_name=_("Action")
    )
    level = models.CharField(
        max_length=10,
        choices=Level.choices,
        default=Level.INFO,
        verbose_name=_("Niveau"),
    )
    # Message déjà traduit au moment de l'enregistrement : le journal reste
    # lisible même si les libellés changent plus tard.
    message = models.CharField(max_length=255, blank=True, default="")
    detail = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Activité")
        verbose_name_plural = _("Activités")
        indexes = [models.Index(fields=["owner", "-created_at"])]

    def __str__(self):
        return f"{self.get_action_display()} — {self.message or self.created_at:%Y-%m-%d %H:%M}"


class ApiToken(models.Model):
    """Jeton d'accès à l'API REST, propre à un utilisateur.

    Seul le condensé (SHA-256) du jeton est stocké ; la valeur en clair n'est
    affichée qu'une seule fois, à la création.
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="api_tokens",
        verbose_name=_("Propriétaire"),
    )
    name = models.CharField(max_length=120, verbose_name=_("Nom du jeton"))
    prefix = models.CharField(max_length=16, verbose_name=_("Préfixe"))
    key_hash = models.CharField(max_length=64, unique=True, verbose_name=_("Condensé"))
    is_active = models.BooleanField(default=True, verbose_name=_("Actif"))
    last_used_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Dernière utilisation"))
    call_count = models.PositiveIntegerField(default=0, verbose_name=_("Nombre d'appels"))
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Expiration"))

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Jeton d'API")
        verbose_name_plural = _("Jetons d'API")

    def __str__(self):
        return f"{self.name} ({self.prefix}…)"

    @property
    def is_expired(self):
        """Vrai si le jeton a dépassé sa date d'expiration."""
        return bool(self.expires_at and self.expires_at <= timezone.now())

    @property
    def is_valid(self):
        """Vrai si le jeton est utilisable (actif et non expiré)."""
        return self.is_active and not self.is_expired


class Webhook(models.Model):
    """Point d'alerte HTTP appelé lorsqu'un événement se produit.

    L'appel est déclenché en tâche de fond (``threading``) pour ne jamais
    ralentir le traitement de la requête utilisateur.
    """

    class Event(models.TextChoices):
        CLEANING_DONE = "cleaning_done", _("Nettoyage terminé")
        CLEANING_ERROR = "cleaning_error", _("Erreur de nettoyage")
        UPLOAD = "upload", _("Fichier téléversé")
        DELETE = "delete", _("Fichier supprimé")

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="webhooks",
        verbose_name=_("Propriétaire"),
    )
    name = models.CharField(max_length=120, verbose_name=_("Nom"))
    url = models.URLField(max_length=500, verbose_name=_("URL de destination"))
    event = models.CharField(
        max_length=24, choices=Event.choices, verbose_name=_("Événement")
    )
    secret = models.CharField(
        max_length=64, blank=True, default="", verbose_name=_("Clé de signature")
    )
    is_active = models.BooleanField(default=True, verbose_name=_("Actif"))
    last_status = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name=_("Dernier code HTTP")
    )
    last_triggered_at = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Dernier déclenchement")
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = _("Webhook")
        verbose_name_plural = _("Webhooks")

    def clean(self):
        """Refuse une URL de destination qui vise le réseau interne (SSRF)."""
        super().clean()
        if not self.url:
            return
        from .services.api import WebhookUrlError, validate_webhook_url

        try:
            self.url = validate_webhook_url(self.url, resolve=False)
        except WebhookUrlError as exc:
            raise ValidationError({"url": ValidationError(str(exc))}) from exc

    def save(self, *args, **kwargs):
        """Rejoue la validation d'URL même hors formulaire (admin, scripts)."""
        if self.url and not kwargs.get("raw"):
            from .services.api import WebhookUrlError, validate_webhook_url

            try:
                self.url = validate_webhook_url(self.url, resolve=False)
            except WebhookUrlError as exc:
                raise ValidationError({"url": ValidationError(str(exc))}) from exc
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} → {self.event}"


class DatasetShare(models.Model):
    """Partage d'un jeu de données avec un utilisateur ou via un lien public.

    Deux usages cohabitent : un partage nominatif (``shared_with`` renseigné,
    le destinataire retrouve le fichier dans sa liste) et un lien public
    (``shared_with`` vide, le jeton suffit). Le droit accordé est toujours en
    lecture seule : seul le propriétaire modifie les données.
    """

    class Permission(models.TextChoices):
        VIEW = "view", _("Consultation")
        DOWNLOAD = "download", _("Consultation et téléchargement")

    data_file = models.ForeignKey(
        DataFile,
        on_delete=models.CASCADE,
        related_name="shares",
        verbose_name=_("Fichier"),
    )
    shared_with = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="shared_datasets",
        null=True,
        blank=True,
        verbose_name=_("Destinataire"),
        help_text=_("Vide pour créer un lien public."),
    )
    permission = models.CharField(
        max_length=10,
        choices=Permission.choices,
        default=Permission.VIEW,
        verbose_name=_("Droit accordé"),
    )
    token = models.CharField(
        max_length=64, unique=True, db_index=True, verbose_name=_("Jeton du lien")
    )
    expires_at = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Expiration")
    )
    is_active = models.BooleanField(default=True, verbose_name=_("Actif"))
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_shares",
        null=True,
        blank=True,
        verbose_name=_("Créé par"),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Partage")
        verbose_name_plural = _("Partages")

    def __str__(self):
        target = self.shared_with.username if self.shared_with_id else _("lien public")
        return f"{self.data_file} → {target}"

    @property
    def is_public_link(self):
        """Vrai lorsque le partage se fait par lien, sans destinataire nommé."""
        return self.shared_with_id is None

    @property
    def is_expired(self):
        """Vrai si la date d'expiration est dépassée."""
        return bool(self.expires_at and self.expires_at <= timezone.now())

    @property
    def is_valid(self):
        """Vrai si le partage est encore utilisable."""
        return self.is_active and not self.is_expired


class DatasetVersion(models.Model):
    """Version figée d'un jeu de données après un nettoyage.

    Chaque nettoyage réussi crée une version : elle conserve une copie du
    fichier nettoyé et les indicateurs du moment, ce qui permet de consulter
    l'historique, de comparer deux versions et de revenir en arrière.
    """

    data_file = models.ForeignKey(
        DataFile,
        on_delete=models.CASCADE,
        related_name="versions",
        verbose_name=_("Fichier"),
    )
    number = models.PositiveIntegerField(verbose_name=_("Numéro de version"))
    cleaned_file = models.FileField(
        upload_to="versions/%Y/%m/%d/",
        blank=True,
        null=True,
        verbose_name=_("Fichier nettoyé"),
    )
    change_log_file = models.FileField(
        upload_to="versions/logs/%Y/%m/%d/",
        blank=True,
        null=True,
        verbose_name=_("Journal des modifications"),
    )
    quality_before = models.FloatField(null=True, blank=True)
    quality_after = models.FloatField(null=True, blank=True)
    rows_count = models.PositiveIntegerField(null=True, blank=True)
    columns_count = models.PositiveSmallIntegerField(null=True, blank=True)
    changes_count = models.PositiveIntegerField(null=True, blank=True)
    metrics = models.JSONField(default=dict, blank=True)
    # Codes d'opération appliqués, stockés sans traduction puis rendus à
    # l'affichage : l'historique reste lisible dans toutes les langues.
    operations = models.JSONField(default=list, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="dataset_versions",
        null=True,
        blank=True,
        verbose_name=_("Créée par"),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-number"]
        verbose_name = _("Version")
        verbose_name_plural = _("Versions")
        constraints = [
            models.UniqueConstraint(
                fields=["data_file", "number"], name="unique_version_per_dataset"
            )
        ]

    def __str__(self):
        return f"{self.data_file} — v{self.number}"


class CleaningSchedule(models.Model):
    """Nettoyage récurrent d'un jeu de données.

    La planification ne devine rien : une commande de gestion reprend les
    échéances dues et relance le nettoyage via le même chemin de code que
    l'interface, afin qu'un traitement planifié et un traitement manuel
    produisent exactement le même résultat.
    """

    class Frequency(models.TextChoices):
        DAILY = "daily", _("Quotidien")
        WEEKLY = "weekly", _("Hebdomadaire")
        MONTHLY = "monthly", _("Mensuel")

    data_file = models.ForeignKey(
        DataFile,
        on_delete=models.CASCADE,
        related_name="schedules",
        verbose_name=_("Fichier"),
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cleaning_schedules",
        verbose_name=_("Propriétaire"),
    )
    frequency = models.CharField(
        max_length=10,
        choices=Frequency.choices,
        default=Frequency.WEEKLY,
        verbose_name=_("Fréquence"),
    )
    options = models.JSONField(
        default=dict, blank=True, verbose_name=_("Options de nettoyage")
    )
    rule_ids = models.JSONField(
        default=list, blank=True, verbose_name=_("Règles appliquées")
    )
    next_run_at = models.DateTimeField(verbose_name=_("Prochaine exécution"))
    last_run_at = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Dernière exécution")
    )
    is_active = models.BooleanField(default=True, verbose_name=_("Actif"))
    run_count = models.PositiveIntegerField(default=0, verbose_name=_("Exécutions"))
    last_status = models.CharField(
        max_length=20, blank=True, default="", verbose_name=_("Dernier statut")
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["next_run_at"]
        verbose_name = _("Planification")
        verbose_name_plural = _("Planifications")

    def __str__(self):
        return f"{self.data_file} — {self.get_frequency_display()}"

    def compute_next_run(self, from_moment=None):
        """Calcule la prochaine échéance à partir d'un instant de référence."""
        from datetime import timedelta

        base = from_moment or timezone.now()
        step = {
            self.Frequency.DAILY: timedelta(days=1),
            self.Frequency.WEEKLY: timedelta(days=7),
            self.Frequency.MONTHLY: timedelta(days=30),
        }[self.frequency]
        return base + step
