"""Recherche globale : sources multiples et classement par pertinence.

La palette Ctrl+K interroge ce module, qui agrège en une seule requête les
fichiers, les règles de nettoyage, les pages de l'interface, le journal
d'activité, les jetons d'API et les webhooks visibles par l'utilisateur.

Deux principes guident l'implémentation :

- **Tout est cherché, pas seulement les noms.** Un fichier est trouvable par
  une de ses colonnes, une règle par son opération ou sa colonne cible, une
  page par son URL ou ses mots-clés anglais.
- **Le classement est déterministe.** Chaque résultat reçoit un score de
  pertinence (correspondance exacte, préfixe, début de mot, sous-chaîne) et
  les résultats sont triés par score décroissant, puis par libellé.

La comparaison ignore la casse **et les accents** : « regles » trouve
« Règles de nettoyage ». Le filtrage se fait donc en Python sur une fenêtre
bornée (``SCAN_LIMIT``) plutôt qu'en SQL, dont le ``LIKE`` ne sait pas replier
les accents.
"""
from __future__ import annotations

import unicodedata

from django.urls import reverse
from django.utils.formats import date_format
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _lazy

from ..models import ActivityLog, ApiToken, CleaningRule, DataFile, Webhook
from ..views import _visible_files, _visible_rules

# Nombre maximal de résultats renvoyés à la palette.
MAX_RESULTS = 20
# Nombre maximal de résultats par famille, avant le tri global.
PER_TYPE = 6
# Fenêtre d'analyse : au-delà, on ne cherche plus (protection contre les
# comptes qui accumuleraient des milliers d'entrées).
SCAN_LIMIT = 500

# Pages de l'interface : libellé, nom d'URL, icône et mots-clés de recherche.
# Les mots-clés couvrent les termes anglais et les synonymes métier, afin que
# « dashboard » ou « rgpd » trouvent la bonne page.
#
# Les libellés sont paresseux (``gettext_lazy``) : ils sont résolus au moment
# de la recherche, dans la langue de la requête, et non à l'import du module.
PAGES = (
    (
        _lazy("Tableau de bord"),
        "core:dashboard",
        "📊",
        ("dashboard", "tableau", "kpi", "statistique", "synthese", "pilotage"),
    ),
    (
        _lazy("Accueil"),
        "core:index",
        "🏠",
        ("accueil", "home", "fichier", "televerser", "upload", "import"),
    ),
    (
        _lazy("Activité"),
        "core:activity",
        "🕓",
        ("activity", "activite", "journal", "historique", "log", "trace"),
    ),
    (
        _lazy("Règles de nettoyage"),
        "core:rules_list",
        "⚙️",
        ("regle", "rule", "nettoyage", "operation", "deduplication"),
    ),
    (
        _lazy("API et intégrations"),
        "core:api_tokens",
        "🔌",
        ("api", "jeton", "token", "integration", "rest", "acces"),
    ),
    (
        _lazy("Webhooks"),
        "core:webhooks",
        "🔔",
        ("webhook", "alerte", "notification", "callback", "evenement"),
    ),
    (
        _lazy("Mon profil"),
        "core:profile",
        "👤",
        ("profil", "profile", "compte", "avatar", "mot de passe", "securite"),
    ),
    (
        _lazy("Rétention des données"),
        "core:retention",
        "🗄️",
        ("retention", "purge", "archive", "rgpd", "conservation", "nettoyage"),
    ),
    (
        _lazy("Raccourcis clavier"),
        "core:shortcuts",
        "⌨️",
        ("raccourci", "shortcut", "clavier", "aide", "help", "touche"),
    ),
)

# Libellés de famille affichés dans la palette, résolus à l'appel eux aussi.
TYPE_LABELS = {
    "dataset": _lazy("Fichier"),
    "rule": _lazy("Règle"),
    "page": _lazy("Page"),
    "activity": _lazy("Activité"),
    "token": _lazy("Jeton"),
    "webhook": _lazy("Webhook"),
}


def _type_label(kind):
    """Libellé traduit d'une famille de résultats."""
    return str(TYPE_LABELS.get(kind, kind))



def fold(text):
    """Minuscule sans accents, pour comparer « Règles » et « regles »."""
    decomposed = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(
        char for char in decomposed if not unicodedata.combining(char)
    ).casefold()


def _folded_map(text):
    """Replie ``text`` et renvoie la correspondance vers les index d'origine.

    Le repliage raccourcit parfois la chaîne (un accent décomposé se réduit à
    sa lettre de base). Les index trouvés dans la version repliée ne sont donc
    pas valides dans le texte d'origine ; cette table permet de les traduire
    pour surligner la bonne portion.
    """
    source = str(text or "")
    characters = []
    mapping = []
    for index, char in enumerate(source):
        for piece in unicodedata.normalize("NFKD", char):
            if unicodedata.combining(piece):
                continue
            for folded in piece.casefold():
                characters.append(folded)
                mapping.append(index)
    return "".join(characters), mapping


def match(label, query):
    """Pertinence d'un libellé face à la requête.

    Renvoie ``(score, debut, fin)`` où ``debut``/``fin`` délimitent, **dans le
    libellé d'origine**, la portion à mettre en évidence (``fin`` vaut ``-1``
    si aucune correspondance). Le score décroît de la correspondance exacte
    (100) à la simple sous-chaîne (50).
    """
    folded, mapping = _folded_map(label)
    query = fold(query)
    if not folded or not query:
        return 0, -1, -1

    def span(position):
        """Traduit une position repliée en intervalle du texte d'origine."""
        start = mapping[position]
        last = min(position + len(query), len(mapping)) - 1
        return start, mapping[last] + 1

    if folded == query:
        return 100, 0, len(str(label or ""))
    if folded.startswith(query):
        return 85, *span(0)
    position = folded.find(query)
    if position < 0:
        return 0, -1, -1
    if position > 0 and not folded[position - 1].isalnum():
        return 70, *span(position)
    return 50, *span(position)


def _best(candidates, query):
    """Meilleur score parmi plusieurs champs d'un même élément.

    ``candidates`` est une suite de couples ``(texte, préfixe de contexte)``.
    Le préfixe alimente l'infobulle (« colonne : email ») et n'est renvoyé que
    lorsque la correspondance vient de ce champ. Le cinquième élément du
    résultat est le texte réellement trouvé, ce qui permet à l'appelant de
    savoir si le surlignage doit porter sur le libellé affiché ou non.
    """
    best = (0, -1, -1, "", "")
    for text, context in candidates:
        score, start, end = match(text, query)
        if score > best[0]:
            best = (score, start, end, context, text)
    return best


def _entry(kind, label, hint, url, score, start, end, icon):
    """Construit un résultat homogène pour la palette."""
    return {
        "type": kind,
        "type_label": _type_label(kind),
        "icon": icon,
        "label": label,
        "hint": hint,
        "url": url,
        "score": score,
        "highlight": label[start:end] if start >= 0 and end > start else "",
    }


def _label_span(label, matched, start, end):
    """N'autorise le surlignage que si la correspondance vient du libellé.

    Un fichier trouvé par une de ses colonnes, une page trouvée par un
    mot-clé anglais ou une activité trouvée dans son détail ne doivent pas
    surligner une portion arbitraire du libellé affiché.
    """
    if matched != label:
        return -1, -1
    return start, end


def _dataset_results(user, query):
    results = []
    queryset = _visible_files(user).order_by("-created_at")[:SCAN_LIMIT]
    for data_file in queryset:
        columns = (data_file.metrics or {}).get("columns") or []
        candidates = [(data_file.original_name, "")]
        candidates += [
            (str(column), _("colonne : %(name)s") % {"name": column})
            for column in columns
        ]
        score, start, end, context, matched = _best(candidates, query)
        if not score:
            continue
        start, end = _label_span(data_file.original_name, matched, start, end)
        details = [data_file.get_status_display()]
        if data_file.rows_count is not None:
            details.append(_("%(count)s lignes") % {"count": data_file.rows_count})
        if data_file.columns_count:
            details.append(_("%(count)s colonnes") % {"count": data_file.columns_count})
        hint = " · ".join(details)
        if context:
            hint = f"{context} · {hint}"
        results.append(
            _entry(
                "dataset",
                data_file.original_name,
                hint,
                reverse("core:dataset_detail", args=[data_file.pk]),
                score,
                start,
                end,
                "📄",
            )
        )
    return results


def _rule_results(user, query):
    results = []
    for rule in _visible_rules(user).order_by("name")[:SCAN_LIMIT]:
        candidates = [
            (rule.name, ""),
            (
                rule.get_operation_display(),
                _("opération : %(name)s") % {"name": rule.get_operation_display()},
            ),
        ]
        if rule.column:
            candidates.append(
                (rule.column, _("colonne : %(name)s") % {"name": rule.column})
            )
        score, start, end, context, matched = _best(candidates, query)
        if not score:
            continue
        start, end = _label_span(rule.name, matched, start, end)
        hint = rule.get_operation_display()
        if not rule.is_active:
            hint = f"{hint} · {_('inactive')}"
        if context:
            hint = f"{context} · {hint}"
        results.append(
            _entry(
                "rule",
                rule.name,
                hint,
                reverse("core:rules_list"),
                score,
                start,
                end,
                "⚙️",
            )
        )
    return results


def _page_results(query):
    results = []
    for label, name, icon, keywords in PAGES:
        # ``label`` est paresseux : ``str()`` le résout dans la langue courante.
        translated = str(label)
        candidates = [(translated, "")] + [(keyword, "") for keyword in keywords]
        score, start, end, _context, matched = _best(candidates, query)
        if not score:
            continue
        # Une correspondance sur un mot-clé ne doit pas surligner le libellé.
        start, end = _label_span(translated, matched, start, end)
        results.append(
            _entry(
                "page",
                translated,
                _("Page"),
                reverse(name),
                score,
                start,
                end,
                icon,
            )
        )
    return results


def _activity_results(user, query):
    results = []
    queryset = (
        ActivityLog.objects.filter(owner=user)
        .select_related("data_file")
        .order_by("-created_at")[:SCAN_LIMIT]
    )
    for activity in queryset:
        candidates = [(activity.message, ""), (activity.detail, _("détail"))]
        score, start, end, context, matched = _best(candidates, query)
        if not score:
            continue
        # Le surlignage ne s'applique qu'au message, jamais au détail.
        start, end = _label_span(activity.message, matched, start, end)
        hint = " · ".join(
            part
            for part in (
                context,
                activity.get_action_display(),
                date_format(activity.created_at, "SHORT_DATETIME_FORMAT"),
            )
            if part
        )
        url = (
            reverse("core:dataset_detail", args=[activity.data_file_id])
            if activity.data_file_id
            else reverse("core:activity")
        )
        results.append(
            _entry("activity", activity.message, hint, url, score, start, end, "🕓")
        )
    return results


def _token_results(user, query):
    results = []
    for token in ApiToken.objects.filter(owner=user).order_by("-created_at")[:SCAN_LIMIT]:
        score, start, end, _context, _matched = _best([(token.name, "")], query)
        if not score:
            continue
        hint = f"{token.prefix}… · {_('actif') if token.is_active else _('révoqué')}"
        results.append(
            _entry(
                "token",
                token.name,
                hint,
                reverse("core:api_tokens"),
                score,
                start,
                end,
                "🔑",
            )
        )
    return results


def _webhook_results(user, query):
    results = []
    for webhook in Webhook.objects.filter(owner=user).order_by("-created_at")[:SCAN_LIMIT]:
        candidates = [(webhook.name, ""), (webhook.url, _("URL"))]
        score, start, end, context, matched = _best(candidates, query)
        if not score:
            continue
        start, end = _label_span(webhook.name, matched, start, end)
        hint = " · ".join(
            part
            for part in (
                context,
                webhook.get_event_display(),
                webhook.url,
            )
            if part
        )
        results.append(
            _entry(
                "webhook",
                webhook.name,
                hint,
                reverse("core:webhooks"),
                score,
                start,
                end,
                "🔔",
            )
        )
    return results


def search(user, query):
    """Recherche globale : renvoie ``{"query", "count", "results"}``.

    ``results`` est trié par pertinence décroissante puis par libellé, et
    tronqué à :data:`MAX_RESULTS`. Une requête vide ne renvoie rien.
    """
    query = (query or "").strip()
    if not query:
        return {"query": "", "count": 0, "results": []}

    folded = fold(query)
    results = []
    results += _dataset_results(user, folded)
    results += _rule_results(user, folded)
    results += _page_results(folded)
    results += _activity_results(user, folded)
    results += _token_results(user, folded)
    results += _webhook_results(user, folded)

    # Les pages sont peu nombreuses et très utiles : à pertinence égale, elles
    # passent devant les autres familles.
    priority = {"page": 0, "dataset": 1, "rule": 2, "activity": 3, "token": 4, "webhook": 5}
    results.sort(
        key=lambda item: (
            -item["score"],
            priority.get(item["type"], 9),
            len(item["label"]),
            item["label"].casefold(),
        )
    )

    # Aucune famille ne doit saturer la palette : on plafonne chaque type avant
    # la troncature globale, sinon une requête large (« csv ») ne montrerait
    # que des fichiers.
    kept = []
    per_type = {}
    for item in results:
        count = per_type.get(item["type"], 0)
        if count >= PER_TYPE:
            continue
        per_type[item["type"]] = count + 1
        kept.append(item)
        if len(kept) >= MAX_RESULTS:
            break

    return {"query": query, "count": len(kept), "results": kept}
