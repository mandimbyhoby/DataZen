"""Jetons d'API et webhooks : authentification et notifications sortantes.

L'API de DataZen est volontairement minimaliste (Django « nu », sans DRF) :

- un jeton ``dz_<préfixe>_<secret>`` est généré une seule fois puis seul son
  condensé SHA-256 est conservé en base ;
- les webhooks sont appelés en tâche de fond (``threading``) afin de ne jamais
  ralentir la requête utilisateur, avec une signature HMAC optionnelle.

Aucune exception réseau ne remonte : elle est journalisée et le code HTTP
obtenu (ou ``0`` en cas d'échec) est mémorisé sur le webhook.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import secrets
import socket
import threading
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext as _

from ..models import ApiToken, Webhook

logger = logging.getLogger(__name__)

# Durée maximale d'un appel de webhook (secondes).
WEBHOOK_TIMEOUT = 6

WEBHOOK_SCHEMES = {"http", "https"}


class WebhookUrlError(ValueError):
    """URL de webhook refusée (schéma, hôte ou port non autorisé)."""


def _is_blocked_address(ip):
    """Vrai si l'adresse IP ne doit jamais être joignable par un webhook."""
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_webhook_url(url, resolve=True):
    """Valide l'URL de destination d'un webhook (protection SSRF).

    Une URL de webhook est fournie par l'utilisateur puis appelée par le
    serveur : sans contrôle, elle permet de sonder le réseau interne
    (``127.0.0.1``, ``169.254.169.254``, plages RFC1918) et de lire le code
    de réponse. On n'accepte donc que ``http``/``https``, on exclut les
    identifiants dans l'URL, et on refuse toute adresse privée, boucle locale,
    lien-local ou réservée — y compris celles écrites en littéral.

    ``resolve`` ajoute la résolution DNS pour bloquer un nom d'hôte qui pointe
    vers le réseau interne. Elle n'est faite qu'au moment de l'appel réel
    (``_post``) : à la saisie, un domaine non résolvable est légitime (tests,
    environnement hors ligne) et une résolution tardive protège en plus contre
    le rebinding DNS.

    Renvoie l'URL nettoyée. Lève :class:`WebhookUrlError` si elle est refusée.
    """
    candidate = (url or "").strip()
    if not candidate:
        raise WebhookUrlError(_("Une URL de destination est requise."))

    try:
        parts = urllib.parse.urlsplit(candidate)
    except ValueError as exc:  # pragma: no cover — urlsplit est très tolérant
        raise WebhookUrlError(_("URL illisible.")) from exc

    scheme = parts.scheme.lower()
    if scheme not in WEBHOOK_SCHEMES:
        raise WebhookUrlError(_("Seuls les schémas http et https sont autorisés."))
    if parts.username or parts.password:
        raise WebhookUrlError(_("Les identifiants intégrés à l'URL sont refusés."))

    host = parts.hostname
    if not host:
        raise WebhookUrlError(_("Le nom d'hôte est absent de l'URL."))

    try:
        port = parts.port
    except ValueError as exc:
        raise WebhookUrlError(_("Le port est invalide.")) from exc

    if host.lower() in {"localhost", "localhost.localdomain"}:
        raise WebhookUrlError(_("Les adresses locales sont refusées."))

    # Adresse littérale (IPv4, IPv6, éventuellement entre crochets).
    try:
        literal = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        literal = None
    if literal is not None:
        if _is_blocked_address(literal):
            raise WebhookUrlError(_("Les adresses internes sont refusées."))
    elif resolve:
        try:
            resolved = socket.getaddrinfo(host, port or 443, proto=socket.IPPROTO_TCP)
        except OSError as exc:
            raise WebhookUrlError(
                _("Le nom d'hôte du webhook est introuvable.")
            ) from exc
        for entry in resolved:
            address = entry[4][0].split("%")[0]
            try:
                ip = ipaddress.ip_address(address)
            except ValueError:
                continue
            if _is_blocked_address(ip):
                raise WebhookUrlError(
                    _("Le nom d'hôte du webhook pointe vers une adresse interne.")
                )

    return urllib.parse.urlunsplit(
        (scheme, parts.netloc, parts.path, parts.query, parts.fragment)
    )


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Interdit les redirections : elles contourneraient la validation SSRF."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        raise urllib.error.HTTPError(
            req.full_url, code, "Redirection refusée", headers, fp
        )

TOKEN_PREFIX = "dz"
# Conservé uniquement pour reconnaître les condensés produits avant le passage
# au hachage keyé : un jeton hérité est accepté une fois puis réécrit.
SALT_PREFIX = "datazen"


def generate_token():
    """Crée un couple ``(jeton en clair, préfixe, condensé)``.

    Le jeton en clair n'est jamais stocké : seul son condensé est enregistré,
    comme pour un mot de passe.
    """
    prefix = secrets.token_hex(4)
    secret = secrets.token_urlsafe(32)
    clear = f"{TOKEN_PREFIX}_{prefix}_{secret}"
    return clear, prefix, hash_token(clear)


def hash_token(clear_token):
    """Condensé keyé (HMAC-SHA256) d'un jeton en clair.

    Le sel statique d'origine n'apportait rien : une clé de hachage dérivée de
    ``SECRET_KEY`` empêche la précomputation entre installations et rend les
    condensés inexploitables sans la clé du serveur.
    """
    key = settings.SECRET_KEY.encode("utf-8")
    return hmac.new(key, clear_token.encode("utf-8"), hashlib.sha256).hexdigest()


def legacy_token_hash(clear_token):
    """Ancien condensé (SHA-256 à sel statique), pour migrer les jetons en base."""
    salted = f"{SALT_PREFIX}:{clear_token}".encode("utf-8")
    return hashlib.sha256(salted).hexdigest()


def generate_secret():
    """Clé de signature HMAC pour un nouveau webhook."""
    return secrets.token_hex(24)


def create_token(user, name, expires_at=None):
    """Crée un jeton d'API pour l'utilisateur et renvoie ``(instance, clair)``."""
    clear, prefix, digest = generate_token()
    token = ApiToken.objects.create(
        owner=user,
        name=name or "Jeton",
        prefix=prefix,
        key_hash=digest,
        expires_at=expires_at,
    )
    return token, clear


def resolve_token(clear_token):
    """Retrouve un jeton valide à partir de sa valeur en clair (ou ``None``)."""
    if not clear_token or not clear_token.startswith(f"{TOKEN_PREFIX}_"):
        return None
    token = (
        ApiToken.objects.select_related("owner")
        .filter(key_hash=hash_token(clear_token))
        .first()
    )
    if token is None:
        # Jeton créé avant le passage au hachage keyé : on le reconnaît une
        # dernière fois puis on réécrit son condensé au format actuel.
        legacy = legacy_token_hash(clear_token)
        token = (
            ApiToken.objects.select_related("owner")
            .filter(key_hash=legacy)
            .first()
        )
        if token is not None:
            ApiToken.objects.filter(pk=token.pk).update(key_hash=hash_token(clear_token))
    if token is None or not token.is_valid:
        return None
    return token


def touch_token(token):
    """Met à jour la date et le compteur d'utilisation d'un jeton."""
    try:
        ApiToken.objects.filter(pk=token.pk).update(
            last_used_at=timezone.now(),
            call_count=token.call_count + 1,
        )
    except Exception:  # noqa: BLE001 — statistique d'usage non critique
        logger.exception("Impossible de mettre à jour le jeton %s", token.pk)


def visible_tokens(user):
    """Jetons visibles par l'utilisateur (tous pour un superutilisateur)."""
    queryset = ApiToken.objects.select_related("owner")
    if user.is_superuser:
        return queryset
    return queryset.filter(owner=user)


def revoke_token(token):
    """Désactive un jeton (révocation ; le journal d'activité garde la trace)."""
    token.is_active = False
    token.save(update_fields=["is_active"])
    return token


def token_stats(user):
    """Compteurs d'en-tête de la page « API »."""
    tokens = visible_tokens(user)
    return {
        "total": tokens.count(),
        "active": sum(1 for token in tokens if token.is_valid),
        "calls": sum(token.call_count for token in tokens),
    }


def webhook_payload(event, data_file=None, extra=None):
    """Charge utile JSON commune à tous les webhooks."""
    payload = {
        "event": event,
        "sent_at": timezone.now().isoformat(),
        "application": "DataZen",
    }
    if data_file is not None:
        payload["dataset"] = {
            "id": data_file.pk,
            "name": data_file.original_name,
            "status": data_file.status,
            "score_before": data_file.quality_before,
            "score_after": data_file.quality_after,
            "rows": data_file.rows_count,
            "columns": data_file.columns_count,
            "issues": data_file.issues_count,
            "changes": data_file.changes_count,
        }
    if extra:
        payload["data"] = extra
    return payload


def _signature(secret, body):
    """Signature HMAC-SHA256 du corps, exposée dans l'en-tête ``X-DataZen-Signature``."""
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _post(webhook, payload):
    """Appel HTTP réel d'un webhook ; renvoie le code de statut (0 si échec).

    L'URL est revalidée ici (et pas seulement à la saisie) car une redirection
    DNS ou un enregistrement modifié après coup pourrait pointer vers le réseau
    interne. Les redirections HTTP sont refusées pour la même raison.
    """
    try:
        safe_url = validate_webhook_url(webhook.url, resolve=True)
    except WebhookUrlError as exc:
        logger.warning("Webhook %s refusé : %s", webhook.pk, exc)
        return 0

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "User-Agent": "DataZen-Webhook/1.0",
        "X-DataZen-Event": str(payload.get("event", "")),
    }
    if webhook.secret:
        headers["X-DataZen-Signature"] = _signature(webhook.secret, body)

    request = urllib.request.Request(safe_url, data=body, headers=headers)
    opener = urllib.request.build_opener(_NoRedirectHandler)
    try:
        with opener.open(request, timeout=WEBHOOK_TIMEOUT) as response:
            return int(getattr(response, "status", 200) or 200)
    except urllib.error.HTTPError as exc:
        return int(exc.code)
    except Exception:  # noqa: BLE001 — réseau, DNS, timeout…
        logger.warning("Webhook %s injoignable", webhook.pk)
        return 0


def trigger(user, event, data_file=None, extra=None):
    """Déclenche en arrière-plan tous les webhooks abonnés à ``event``.

    Renvoie le nombre de webhooks programmés (jamais le résultat de l'appel :
    celui-ci est mémorisé sur le webhook à la fin de la requête HTTP).
    """
    if user is None:
        return 0
    queryset = Webhook.objects.filter(owner=user, event=event, is_active=True)
    payload = webhook_payload(event, data_file, extra)
    count = 0
    for webhook in queryset:
        count += 1
        thread = threading.Thread(
            target=_deliver, args=(webhook.pk, payload), daemon=True
        )
        thread.start()
    return count


def _deliver(webhook_pk, payload):
    """Livraison effective d'un webhook (exécutée dans un fil d'arrière-plan)."""
    webhook = Webhook.objects.filter(pk=webhook_pk).first()
    if webhook is None or not webhook.is_active:
        return
    status = _post(webhook, payload)
    try:
        Webhook.objects.filter(pk=webhook_pk).update(
            last_status=status,
            last_triggered_at=timezone.now(),
        )
    except Exception:  # noqa: BLE001 — trace de livraison non critique
        logger.exception("Impossible de mémoriser la livraison du webhook %s", webhook_pk)


def send_test(webhook):
    """Envoie un événement de test **synchrone** et renvoie le code obtenu."""
    payload = webhook_payload(
        webhook.event,
        extra={"test": True, "message": "Événement de test DataZen"},
    )
    status = _post(webhook, payload)
    Webhook.objects.filter(pk=webhook.pk).update(
        last_status=status,
        last_triggered_at=timezone.now(),
    )
    return status


def visible_webhooks(user):
    """Webhooks visibles par l'utilisateur."""
    queryset = Webhook.objects.select_related("owner")
    if user.is_superuser:
        return queryset
    return queryset.filter(owner=user)


def webhook_stats(user):
    """Compteurs d'en-tête de la page « Webhooks »."""
    webhooks = list(visible_webhooks(user))
    return {
        "total": len(webhooks),
        "active": sum(1 for hook in webhooks if hook.is_active),
        "failing": sum(
            1 for hook in webhooks if hook.last_status is not None and hook.last_status >= 400
        ),
    }
