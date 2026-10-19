"""Génération du rapport automatique de qualité des données (Markdown)."""

from datetime import datetime

from django.utils.translation import gettext as _

from .operations import render_operations, render_score_explanations


def _total_changes(changes):
    """Nombre total de corrections effectuées (hors suppressions de doublons)."""
    if not changes:
        return 0
    keys = ("phones", "dates", "categories", "salaries", "emails_corriges")
    return sum(changes.get(k, 0) for k in keys)


def _format_score(lines, score, title):
    """Ajoute le score de qualité, ses composantes et l'explication."""
    if not score:
        return
    lines.append(f"## {title}")
    lines.append("")
    lines.append(f"**Score global : {score.get('total', '—')} / 100**")
    lines.append("")
    lines.append("| " + _("Dimension") + " | " + _("Score") + " | " + _("Pondération") + " |")
    lines.append("| --- | --- | --- |")
    components = score.get("components", {})
    weights = score.get("weights", {})
    for name in components:
        lines.append(
            f"| {name} | {components[name]} / 100 | {weights.get(name, '—')} % |"
        )
    lines.append("")

    # Explication automatique : principaux éléments qui font varier le score.
    explanations = render_score_explanations(score.get("explanations", []))
    if explanations:
        lines.append("### 🔎 " + _("Explication du score"))
        lines.append("")
        for item in explanations:
            marker = "⚠️" if item.get("type") == "warn" else "✅"
            lines.append(f"- {marker} {item.get('text', '')}")
        lines.append("")


def _format_anomalies(lines, detection, title):
    """Ajoute le tableau détaillé des anomalies."""
    lines.append(f"## {title}")
    lines.append("")
    if not detection:
        lines.append(_("Aucune anomalie."))
        lines.append("")
        return

    rows = []

    for p in detection.get("potential_duplicates", []):
        ids = ", ".join(f"Ligne {r + 1}" for r in p["rows"])
        rows.append(
            (
                _("Doublon potentiel"),
                ids,
                f"score {p.get('score', '—')}",
                ", ".join(p.get("similar_columns", [])) or "—",
                p.get("recommendation", _("à vérifier manuellement")),
            )
        )

    for f in detection.get("fuzzy_duplicates", []):
        ids = f"Ligne {f['row_a'] + 1} ↔ {f['row_b'] + 1}"
        rows.append(
            (
                _("Doublon par similarité"),
                ids,
                f"score {f.get('score', '—')}",
                ", ".join(f.get("similar_columns", [])) or "—",
                f.get("recommendation", _("à vérifier manuellement")),
            )
        )

    for idx, col, value in detection.get("emails", {}).get("issues", []):
        rows.append(
            (
                _("Email invalide"),
                f"Ligne {idx + 1} ({col})",
                f"`{value}`",
                _("format invalide"),
                _("à corriger manuellement"),
            )
        )

    for col, info in detection.get("missing", {}).items():
        rows.append(
            (
                _("Valeur manquante"),
                f"Colonne `{col}`",
                f"{info['count']} cellule(s) ({info['percent']} %)",
                _("donnée absente"),
                _("conservée (non inventée)"),
            )
        )

    for col, info in detection.get("dates", {}).items():
        if info.get("invalid"):
            rows.append(
                (
                    _("Date invalide"),
                    f"Colonne `{col}`",
                    f"{info['invalid']} valeur(s)",
                    _("format non reconnu"),
                    _("à corriger manuellement"),
                )
            )

    for col, info in detection.get("phones", {}).items():
        if info.get("invalid"):
            rows.append(
                (
                    _("Téléphone invalide"),
                    f"Colonne `{col}`",
                    f"{info['invalid']} numéro(s)",
                    _("longueur/format incorrect"),
                    _("à corriger manuellement"),
                )
            )

    for o in detection.get("outliers", []):
        rows.append(
            (
                _("Valeur aberrante"),
                f"Ligne {o['ligne']} ({o['colonne']})",
                f"{o['valeur']:g}",
                f"hors [{o['borne_basse']:g} ; {o['borne_haute']:g}]",
                _("à vérifier manuellement"),
            )
        )

    if not rows:
        lines.append(_("Aucune anomalie restante."))
        lines.append("")
        return

    lines.append(
            "| " + _("Type") + " | " + _("Localisation") + " | " + _("Détail")
            + " | " + _("Raison") + " | " + _("Recommandation") + " |"
        )
    lines.append("| --- | --- | --- | --- | --- |")
    for r in rows:
        lines.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} |")
    lines.append("")


def _format_change_log(lines, change_log):
    """Ajoute un extrait du journal des modifications."""
    lines.append("## " + _("Journal des modifications (extrait)"))
    lines.append("")
    if change_log is None or len(change_log) == 0:
        lines.append(_("Aucune modification enregistrée."))
        lines.append("")
        return
    lines.append(
        "| " + _("Ligne") + " | " + _("Colonne") + " | " + _("Ancienne valeur")
        + " | " + _("Nouvelle valeur") + " | " + _("Type") + " | " + _("Raison") + " |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for _index, row in change_log.head(30).iterrows():
        old = str(row.get("ancienne_valeur", "")).replace("|", "\\|")
        new = str(row.get("nouvelle_valeur", "")).replace("|", "\\|")
        reason = str(row.get("raison", "")).replace("|", "\\|")
        lines.append(
            f"| {row.get('ligne', '')} | {row.get('colonne', '')} | "
            f"`{old}` | `{new}` | {row.get('type_correction', '')} | {reason} |"
        )
    if len(change_log) > 30:
        lines.append("")
        lines.append(f"_… et {len(change_log) - 30} autres modifications._")
    lines.append("")


def _format_email_audit(lines, email_audit):
    """Ajoute le tableau d'audit des emails."""
    if email_audit is None or len(email_audit) == 0:
        return
    lines.append("## " + _("Audit des emails"))
    lines.append("")
    lines.append(
        "| " + _("Ligne") + " | " + _("Colonne") + " | " + _("Email original")
        + " | " + _("Email nettoyé") + " | " + _("Statut") + " | " + _("Action") + " |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for _index, row in email_audit.iterrows():
        original = str(row.get("email_original", "")).replace("|", "\\|")
        cleaned = str(row.get("email_nettoye", "")).replace("|", "\\|")
        status = row.get("statut_email", "")
        action = str(row.get("action_email", "")).replace("|", "\\|")
        lines.append(
            f"| {row.get('ligne', '')} | {row.get('colonne', '')} | "
            f"`{original}` | `{cleaned}` | {status} | {action} |"
        )
    lines.append("")


def _format_consistency(lines, consistency):
    """Ajoute la section de contrôle de cohérence des statistiques."""
    if not consistency:
        return
    lines.append("## " + _("Contrôle de cohérence"))
    lines.append("")
    status = "✅ Cohérent" if consistency.get("ok") else "⚠️ Incohérences détectées"
    lines.append(f"**Résultat :** {status}")
    lines.append("")
    lines.append("| Contrôle | État | Détail |")
    lines.append("| --- | --- | --- |")
    for check in consistency.get("checks", []):
        etat = "✅" if check["ok"] else "❌"
        lines.append(f"| {check['label']} | {etat} | {check['detail']} |")
    lines.append("")


def _format_profile(lines, profile):
    """Ajoute le tableau de profilage statistique par colonne."""
    if not profile:
        return
    lines.append("## 🔬 " + _("Profilage statistique"))
    lines.append("")
    lines.append(
        "| " + _("Colonne") + " | " + _("Type") + " | " + _("Complétude")
        + " | " + _("Uniques") + " | " + _("Moyenne") + " | " + _("Médiane")
        + " | " + _("Écart-type") + " | " + _("Variance") + " | "
        + _("Asymétrie") + " | " + _("Aplatissement") + " | " + _("Min")
        + " | " + _("Max") + " | " + _("Outliers") + " |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for row in profile:
        lines.append(
            f"| {row.get('colonne', '')} | {row.get('type', '')} | "
            f"{row.get('completude', '—')} % | {row.get('n_unique', '—')} | "
            f"{row.get('moyenne', '—')} | {row.get('mediane', '—')} | "
            f"{row.get('ecart_type', '—')} | {row.get('variance', '—')} | "
            f"{row.get('asymetrie', '—')} | {row.get('aplatissement', '—')} | "
            f"{row.get('min', '—')} | {row.get('max', '—')} | "
            f"{row.get('outliers', 0)} |"
        )
    lines.append("")

    # Lecture statistique des colonnes numériques : signale les distributions
    # les plus asymétriques, les plus « pointues » et les plus dispersées.
    numeric = [r for r in profile if r.get("type") == "numérique"]
    if not numeric:
        return

    def _as_float(value):
        try:
            return float(str(value).replace(",", "."))
        except (TypeError, ValueError):
            return None

    skew_candidates = [
        (r["colonne"], v)
        for r in numeric
        for v in [_as_float(r.get("asymetrie"))]
        if v is not None
    ]
    if skew_candidates:
        worst = max(skew_candidates, key=lambda item: abs(item[1]))
        if abs(worst[1]) >= 1:
            lines.append(
                "- "
                + _(
                    "Distribution la plus asymétrique : « %(colonne)s » "
                    "(asymétrie %(valeur)s) — moyenne et médiane s'écartent "
                    "sensiblement, une transformation ou un traitement par "
                    "quantiles est à envisager."
                )
                % {"colonne": worst[0], "valeur": f"{worst[1]:.2f}"}
            )

    kurt_candidates = [
        (r["colonne"], v)
        for r in numeric
        for v in [_as_float(r.get("aplatissement"))]
        if v is not None
    ]
    if kurt_candidates:
        worst = max(kurt_candidates, key=lambda item: abs(item[1]))
        if abs(worst[1]) >= 1:
            lines.append(
                "- "
                + _(
                    "Distribution la plus concentrée/pointue : « %(colonne)s » "
                    "(aplatissement %(valeur)s) — forte densité autour de la "
                    "moyenne avec des valeurs extrêmes marquées."
                )
                % {"colonne": worst[0], "valeur": f"{worst[1]:.2f}"}
            )

    with_outliers = [(r["colonne"], r.get("outliers", 0)) for r in numeric]
    total_outliers = sum(count for _c, count in with_outliers)
    if total_outliers:
        top = sorted(with_outliers, key=lambda item: item[1], reverse=True)[:3]
        detail = ", ".join(f"« {c} » ({n})" for c, n in top if n)
        lines.append(
            "- "
            + _(
                "%(total)s valeur(s) aberrante(s) détectée(s) (méthode IQR). "
                "Colonnes les plus concernées : %(detail)s."
            )
            % {"total": total_outliers, "detail": detail}
        )
    lines.append("")


def build_report(
    data_file_name,
    operations,
    before,
    after,
    detected=None,
    validation=None,
    changes=None,
    quality_before=None,
    quality_after=None,
    change_log=None,
    email_audit=None,
    consistency=None,
    profile=None,
):
    """Construit le rapport complet de qualité des données en Markdown.

    - ``before`` / ``after`` : statistiques ``{rows, columns, duplicates, missing}``.
    - ``detected`` : analyse avant nettoyage (``build_detection``).
    - ``validation`` : analyse après nettoyage (``build_detection``).
    - ``changes`` : compteurs des corrections effectuées.
    - ``quality_before`` / ``quality_after`` : scores de qualité.
    - ``change_log`` : DataFrame du journal des modifications.
    - ``email_audit`` : DataFrame d'audit des emails.
    - ``consistency`` : résultat de ``verify_consistency``.
    - ``profile`` : profilage statistique par colonne (``profile_dataframe``).
    """
    lines = []
    timestamp = datetime.now().strftime("%d/%m/%Y à %H:%M:%S")

    lines.append("# === RAPPORT DE QUALITÉ DES DONNÉES ===")
    lines.append("")
    lines.append(f"- **Fichier :** `{data_file_name}`")
    lines.append(f"- **Généré le :** {timestamp}")
    lines.append("")

    # --- Score de qualité ---
    lines.append("## Score de qualité")
    lines.append("")
    lines.append(
        f"- Score avant nettoyage : **"
        f"{quality_before.get('total') if quality_before else '—'} / 100**"
    )
    lines.append(
        f"- Score après nettoyage : **"
        f"{quality_after.get('total') if quality_after else '—'} / 100**"
    )
    lines.append("")
    _format_score(lines, quality_after, _("Composantes du score (après nettoyage)"))

    # --- Synthèse ---
    lines.append("## Synthèse")
    lines.append("")
    lines.append("| Indicateur | Valeur |")
    lines.append("| --- | --- |")
    lines.append(f"| Lignes avant nettoyage | {before.get('rows', '—')} |")
    lines.append(f"| Lignes après nettoyage | {after.get('rows', '—')} |")
    lines.append(
        f"| Doublons exacts supprimés | "
        f"{max(0, before.get('duplicates', 0) - after.get('duplicates', 0))} |"
    )
    lines.append(
        f"| Doublons potentiels détectés | "
        f"{len(validation.get('potential_duplicates', [])) if validation else '—'} |"
    )
    em = validation.get("emails", {}) if validation else {}
    unknown = validation.get("unknown", {}) if validation else {}
    lines.append(f"| Emails valides | {em.get('valid', '—')} |")
    lines.append(f"| Emails invalides | {em.get('invalid', '—')} |")
    lines.append(f"| Emails inconnus | {em.get('unknown', '—')} |")
    lines.append(
        f"| Emails corrigés | {changes.get('emails_corriges', 0) if changes else 0} |"
    )
    lines.append(
        f"| Téléphones corrigés | {changes.get('phones', 0) if changes else 0} |"
    )
    lines.append(
        f"| Téléphones invalides | "
        f"{sum(v['invalid'] for v in validation.get('phones', {}).values()) if validation else '—'} |"
    )
    lines.append(
        f"| Dates corrigées | {changes.get('dates', 0) if changes else 0} |"
    )
    lines.append(
        f"| Dates invalides | "
        f"{sum(v['invalid'] for v in validation.get('dates', {}).values()) if validation else '—'} |"
    )
    lines.append(
        f"| Catégories normalisées | {changes.get('categories', 0) if changes else 0} |"
    )
    lines.append(
        f"| Salaires convertis | {changes.get('salaries', 0) if changes else 0} |"
    )
    lines.append(f"| Valeurs manquantes restantes | {after.get('missing', '—')} |")
    lines.append(f"| Valeurs « Inconnu » | {sum(unknown.values())} |")
    lines.append(f"| **Nombre total de corrections** | **{_total_changes(changes)}** |")
    lines.append("")

    # --- Détection ---
    _format_anomalies(lines, detected, _("Problèmes détectés"))

    # --- Opérations appliquées ---
    lines.append(f"## {_('Opérations appliquées')}")
    lines.append("")
    rendered_operations = render_operations(operations)
    if rendered_operations:
        for op in rendered_operations:
            lines.append(f"- {op}")
    else:
        lines.append(f"- {_('Aucune opération.')}")
    lines.append("")

    # --- Journal des modifications ---
    _format_change_log(lines, change_log)

    # --- Audit des emails ---
    _format_email_audit(lines, email_audit)

    # --- Contrôle de cohérence ---
    _format_consistency(lines, consistency)

    # --- Profilage statistique ---
    _format_profile(lines, profile)

    # --- Anomalies restantes ---
    _format_anomalies(lines, validation, _("Anomalies restantes (à traiter manuellement)"))

    lines.append("---")
    lines.append("_Rapport généré automatiquement par DataZen._")
    return "\n".join(lines)
