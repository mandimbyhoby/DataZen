"""Limitation des tentatives de connexion (anti-force brute).

Le formulaire de connexion accepte un nom d'utilisateur et un mot de passe
sans aucun mécanisme de ralentissement : un script peut donc essayer des
milliers de combinaisons. Ce module compte les échecs par couple
(adresse IP, nom d'utilisateur) et bloque temporairement au-delà d'un seuil.

Le compteur vit dans le cache Django. Avec ``LocMemCache`` il est propre à
chaque processus : c'est suffisant pour un déploiement mono-processus
(waitress), mais un déploiement multi-processus doit configurer un cache
partagé (Redis ou Memcached) pour que le blocage soit global.
"""
from __future__ import annotations

import hashlib
import time

from django.conf import settings
from django.core.cache import cache

# Préfixe des clés pour ne pas entrer en collision avec d'autres usages du cache.
_KEY_PREFIX = "dz-login-throttle"


def _client_ip(request) -> str:
    """Retourne l'adresse IP du client, derrière un proxy de confiance."""
    # ``REMOTE_ADDR`` est la seule valeur non falsifiable ; on ne lit
    # ``X-Forwarded-For`` que si le déploiement déclare un proxy.
    if getattr(settings, "USE_X_FORWARDED_HOST", False):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "0.0.0.0")


def _digest(value: str) -> str:
    """Réduit une valeur à une empreinte courte et sûre pour une clé de cache."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


def _keys(request, username: str) -> tuple[str, str]:
    """Clés de comptage : par identifiant, et par IP seule.

    La clé par identifiant arrête une attaque ciblée sur un compte ; la clé par
    IP seule arrête le bourrage d'identifiants qui essaie un mot de passe
    unique sur des centaines de comptes.
    """
    ip = _client_ip(request)
    return (
        f"{_KEY_PREFIX}:user:{_digest(f'{ip}|{username.lower()}')}",
        f"{_KEY_PREFIX}:ip:{_digest(ip)}",
    )


def _limits() -> tuple[int, int, int]:
    """(tentatives par identifiant, tentatives par IP, fenêtre en secondes)."""
    return (
        int(getattr(settings, "LOGIN_THROTTLE_MAX_PER_USER", 5)),
        int(getattr(settings, "LOGIN_THROTTLE_MAX_PER_IP", 20)),
        int(getattr(settings, "LOGIN_THROTTLE_WINDOW", 900)),
    )


def _read(key: str) -> tuple[int, float]:
    """Retourne (nombre d'échecs, horodatage d'expiration) pour une clé.

    L'échéance est stockée avec le compteur plutôt que lue via ``cache.ttl`` :
    ``LocMemCache`` n'implémente pas ``ttl``, et le code doit fonctionner avec
    les deux moteurs.
    """
    entry = cache.get(key)
    if not isinstance(entry, dict):
        return 0, 0.0
    expires_at = float(entry.get("exp", 0.0))
    if expires_at <= time.time():
        return 0, 0.0
    return int(entry.get("n", 0)), expires_at


def is_locked_out(request, username: str) -> bool:
    """Indique si de nouvelles tentatives doivent être refusées."""
    max_user, max_ip, _ = _limits()
    user_key, ip_key = _keys(request, username)
    return _read(user_key)[0] >= max_user or _read(ip_key)[0] >= max_ip


def register_failure(request, username: str) -> None:
    """Incrémente les compteurs après un échec d'authentification."""
    _, _, window = _limits()
    now = time.time()
    for key in _keys(request, username):
        count, expires_at = _read(key)
        # La fenêtre glisse tant que le seuil n'est pas atteint, puis se fige
        # pour garantir un blocage réellement temporisé.
        cache.set(key, {"n": count + 1, "exp": expires_at or now + window}, window)


def reset(request, username: str) -> None:
    """Efface les compteurs après une connexion réussie."""
    cache.delete_many(list(_keys(request, username)))


def remaining_seconds(request, username: str) -> int:
    """Secondes restantes avant la fin du blocage (0 si non bloqué)."""
    max_user, max_ip, _ = _limits()
    user_key, ip_key = _keys(request, username)
    for key, limit in ((user_key, max_user), (ip_key, max_ip)):
        count, expires_at = _read(key)
        if count >= limit:
            return max(1, int(expires_at - time.time()))
    return 0
