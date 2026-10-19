"""Rôles et règles d'accès aux jeux de données.

Ce module centralise les décisions de droit afin que les vues, l'API et les
services n'aient jamais à réinterpréter la logique. Trois niveaux coexistent :

* le **rôle** du compte (lecteur, éditeur, administrateur) ;
* la **propriété** du jeu de données ;
* le **partage** explicite, en lecture seule, accordé par le propriétaire.

Un superutilisateur conserve un accès total, quel que soit son profil.
"""
import secrets

from django.db.models import Q
from django.utils import timezone

from ..models import DatasetShare, Profile

TOKEN_BYTES = 24


def not_expired():
    """Filtre des partages encore valides.

    Un partage sans date d'expiration reste valide indéfiniment. L'instant de
    référence est évalué à chaque appel : un filtre figé à l'import laisserait
    un lien expiré accessible jusqu'au redémarrage du serveur.
    """
    return Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())


def role_of(user):
    """Renvoie le rôle effectif du compte connecté.

    Le profil est créé par un signal à l'inscription ; le repli par défaut
    couvre les comptes créés hors application (données de démonstration).
    """
    if not getattr(user, "is_authenticated", False):
        return None
    if user.is_superuser:
        return Profile.Role.ADMIN
    return getattr(getattr(user, "profile", None), "role", Profile.Role.EDITOR)


def is_admin(user):
    """Vrai si le compte administre l'application."""
    return role_of(user) == "admin"


def can_edit(user):
    """Vrai si le compte peut transformer des données (nettoyer, supprimer)."""
    return role_of(user) in ("editor", "admin")


def can_view(user, data_file):
    """Vrai si le compte peut consulter le jeu de données."""
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    if data_file.owner_id == user.pk:
        return True
    if is_admin(user):
        return True
    return valid_shares_for(user).filter(data_file_id=data_file.pk).exists()


def can_download(user, data_file):
    """Vrai si le compte peut télécharger les fichiers du jeu de données.

    Un partage en consultation seule autorise l'affichage mais pas l'export.
    """
    if user.is_superuser or data_file.owner_id == user.pk or is_admin(user):
        return True
    shares = valid_shares_for(user).filter(data_file_id=data_file.pk)
    return shares.filter(permission=DatasetShare.Permission.DOWNLOAD).exists()


def valid_shares_for(user):
    """Partages nominatifs encore valides dont l'utilisateur est destinataire."""
    return DatasetShare.objects.filter(
        shared_with=user,
        is_active=True,
    ).filter(not_expired())


def shared_dataset_ids(user):
    """Identifiants des jeux de données partagés avec l'utilisateur."""
    return valid_shares_for(user).values_list("data_file_id", flat=True)


def new_share_token():
    """Jeton opaque utilisé dans les liens de partage publics."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def share_for_token(token, data_file=None):
    """Renvoie le partage correspondant à un jeton, s'il est encore valide."""
    query = DatasetShare.objects.select_related("data_file", "shared_with").filter(
        token=token, is_active=True
    )
    if data_file is not None:
        query = query.filter(data_file=data_file)
    return query.filter(not_expired()).first()
