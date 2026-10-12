"""Revue manuelle des doublons potentiels (DataZen).

Ce module construit la liste des groupes de doublons potentiels détectés
(réutilise :func:`validation.build_detection`) et applique les décisions
manuelles de l'utilisateur (conserver A, conserver B, fusionner, conserver
les deux, ignorer) sur le DataFrame final.

Principes :
- Les doublons potentiels ne sont **jamais** supprimés automatiquement.
- « Inconnu » n'est **jamais** considéré comme une différence réelle.
- Toute action est tracée dans le journal (mêmes colonnes que le journal
  existant : ``ligne, colonne, ancienne_valeur, nouvelle_valeur,
  type_correction, raison``).
- Aucune hypothèse sur les colonnes présentes : la comparaison est dynamique.
"""

import pandas as pd
from django.utils.translation import gettext as _

from .cleaning import UNKNOWN_VALUE, _is_identifier, is_unknown
from .validation import build_detection


def _display(value):
    """Convertit une valeur en texte lisible (vide si absente)."""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value)


def _is_empty(value):
    """Vrai si la valeur est absente (NaN/None) ou « Inconnu »."""
    return pd.isna(value) if not isinstance(value, str) else (is_unknown(value) or value.strip() == "")


def compare_values(a, b):
    """Compare deux valeurs et renvoie ``(statut, libellé)``.

    Règles :
    - « Inconnu » et « Inconnu » → identique.
    - « Inconnu » et valeur connue → inconnu (pas une différence réelle).
    - même valeur connue → identique.
    - valeurs connues différentes → différent.
    """
    a_absent = _is_empty(a)
    b_absent = _is_empty(b)
    if a_absent and b_absent:
        return "identique", "✅ identique"
    if a_absent or b_absent:
        return "inconnu", "⚪ inconnu"
    if _display(a).strip() == _display(b).strip():
        return "identique", "✅ identique"
    return "different", "❌ différent"


def _column_status(values):
    """Statut global d'une colonne à travers plusieurs valeurs du groupe."""
    known = [v for v in values if not _is_empty(v)]
    n_empty = len(values) - len(known)
    distinct = {_display(v).strip() for v in known}
    if not known:
        return "identique"  # toutes « Inconnu » → identiques
    if len(distinct) == 1:
        return "inconnu" if n_empty else "identique"
    return "different"


def _label_for(status):
    return {"identique": "✅ identique", "different": "❌ différent", "inconnu": "⚪ inconnu"}[status]


def build_review_groups(df):
    """Construit les groupes de doublons potentiels pour la revue manuelle.

    Gère les groupes de **2 lignes ou plus**. Chaque groupe contient :
    numéro, lignes (1-based), ids, ancien_ids, score de similarité, raison,
    tableau comparatif ``comparisons`` (colonne → valeurs de chaque ligne,
    statut, libellé) et les compteurs « champs identiques / différents /
    inconnus » ainsi que les listes de colonnes correspondantes.
    """
    detection = build_detection(df)
    groups = []
    for p in detection["potential_duplicates"]:
        rows = p["rows"]
        if len(rows) < 2:
            continue

        # Colonnes comparées : tout sauf les identifiants (id, ancien_id…).
        cols = [c for c in df.columns if not _is_identifier(c)]

        comparisons = []
        n_identical = n_diff = n_unknown = 0
        identiques = []
        differentes = []
        inconnues = []
        for c in cols:
            values = [df.iloc[r][c] for r in rows]
            status = _column_status(values)
            libelle = _label_for(status)
            if status == "identique":
                n_identical += 1
                identiques.append(str(c))
            elif status == "different":
                n_diff += 1
                differentes.append(str(c))
            else:
                n_unknown += 1
                inconnues.append(str(c))
            comparisons.append(
                {
                    "colonne": str(c),
                    "valeurs": [_display(v) for v in values],
                    "statut": status,
                    "libelle": libelle,
                }
            )

        id_col = "id" if "id" in df.columns else None
        anc_col = "ancien_id" if "ancien_id" in df.columns else None

        lines = []
        for r in rows:
            lines.append(
                {
                    "ligne": r + 1,
                    "ancien_id": _display(df.iloc[r][anc_col]) if anc_col else "",
                    "id": _display(df.iloc[r][id_col]) if id_col else "",
                    "valeurs": {str(c): _display(df.iloc[r][c]) for c in cols},
                }
            )

        groups.append(
            {
                "n": len(groups) + 1,
                "rows": [int(r) for r in rows],
                "lignes": [r + 1 for r in rows],
                "nb_lignes": len(rows),
                "ids": [_display(df.iloc[r][id_col]) if id_col else str(r + 1) for r in rows],
                "ancien_ids": [_display(df.iloc[r][anc_col]) if anc_col else "" for r in rows],
                "score": round(p.get("score", 0.0) * 100, 1),
                "raison": p.get("reason", ""),
                "columns": [str(c) for c in cols],
                "lines": lines,
                "comparisons": comparisons,
                "n_identical": n_identical,
                "n_diff": n_diff,
                "n_unknown": n_unknown,
                "colonnes_identiques": ", ".join(identiques) or "—",
                "colonnes_differentes": ", ".join(differentes) or "—",
                "colonnes_inconnues": ", ".join(inconnues) or "—",
            }
        )
    return groups


def _ligne_of(row):
    """Numéro de ligne « originel » d'une ligne (ancien_id si dispo, sinon id)."""
    for key in ("ancien_id", "id"):
        if key in row.index and not _is_empty(row[key]):
            return _display(row[key])
    return ""


def _entry(ligne, colonne, ancienne, nouvelle, type_correction, raison):
    """Construit une entrée du journal (schéma strict du journal existant)."""
    return {
        "ligne": ligne,
        "colonne": colonne,
        "ancienne_valeur": ancienne,
        "nouvelle_valeur": nouvelle,
        "type_correction": type_correction,
        "raison": raison,
    }


def _remove_entry(row, kept):
    """Entrée de journal pour une ligne supprimée (doublon manuel)."""
    return _entry(
        _ligne_of(row),
        "(ligne entière)",
        "doublon potentiel",
        "supprimée",
        "doublon manuel",
        f"Doublon potentiel confirmé par l'utilisateur : {kept}.",
    )


def _merge_pair(base_row, other_row, entries, ligne_other=""):
    """Fusionne ``other_row`` dans ``base_row`` (dictionnaires).

    Règles :
    - A renseigné et B « Inconnu » → conserver A.
    - B renseigné et A « Inconnu » → conserver B.
    - identiques → conserver la valeur.
    - différents et tous deux renseignés → **conserver A** et journaliser le
      conflit (aucun écrasement silencieux).
    """
    for c, a in base_row.items():
        if c in ("id", "ancien_id"):
            continue
        b = other_row.get(c)
        a_absent = _is_empty(a)
        b_absent = _is_empty(b)
        if a_absent and not b_absent:
            base_row[c] = b
        elif b_absent and not a_absent:
            pass  # conserver A
        elif a_absent and b_absent:
            pass
        elif _display(a).strip() == _display(b).strip():
            pass
        else:
            # Conflit réel : conserver A, journaliser.
            base_row[c] = a
            entries.append(
                _entry(
                    ligne_other,
                    str(c),
                    _display(b),
                    _display(a),
                    "fusion",
                    f"Conflit lors de la fusion (colonne « {c} ») : valeur de A conservée, valeur de B non retenue.",
                )
            )
    return base_row


def apply_decision(df, ancien_ids, action):
    """Applique une décision manuelle sur un groupe de doublons potentiels.

    ``ancien_ids`` identifie de façon stable les lignes du groupe (insensible
    aux renumérotations). ``action`` ∈ {keep_a, keep_b, merge, keep_both,
    ignore}. Gère les groupes de 2 lignes ou plus. Retourne
    ``(nouveau_df, journal_entries)``.
    """
    id_col = "ancien_id" if "ancien_id" in df.columns else "id"
    target = {str(x).strip() for x in ancien_ids if str(x).strip()}

    positions = [
        idx
        for idx in df.index
        if str(df.at[idx, id_col]).strip() in target
    ]
    positions = sorted(positions)
    if len(positions) < 2:
        return df, []

    rows = [df.iloc[p] for p in positions]

    if action == "keep_a":
        # Conserver la 1re ligne du groupe, supprimer les autres.
        df2 = df.drop(index=positions[1:]).reset_index(drop=True)
        entries = [_remove_entry(rows[i], "ligne 1 conservée") for i in range(1, len(rows))]
    elif action == "keep_b":
        # Conserver la 2e ligne du groupe, supprimer les autres.
        drop = positions[:1] + positions[2:]
        df2 = df.drop(index=drop).reset_index(drop=True)
        entries = [
            _remove_entry(rows[i], "ligne 2 conservée")
            for i in range(len(rows))
            if i != 1
        ]
    elif action == "merge":
        # Fusionner toutes les lignes du groupe en une seule.
        base = {c: rows[0][c] for c in df.columns}
        entries = []
        for other in rows[1:]:
            _merge_pair(
                base,
                {c: other[c] for c in df.columns},
                entries,
                _ligne_of(other),
            )
        entries.insert(
            0,
            _entry(
                _ligne_of(rows[0]),
                "(ligne entière)",
                f"fusion de {len(rows)} lignes",
                "fusionnée",
                "fusion manuelle",
                "Fusion des lignes du groupe en une seule (doublon potentiel confirmé).",
            ),
        )
        df2 = df.drop(index=positions).reset_index(drop=True)
        df2.loc[len(df2)] = base
        df2 = df2[df.columns]
    elif action == "ignore":
        df2 = df
        entries = [
            _entry(
                _ligne_of(rows[0]),
                "(ligne entière)",
                "doublon potentiel",
                "conservée",
                "revue manuelle",
                "Doublon potentiel examiné : les lignes sont conservées.",
            )
        ]
    else:  # keep_both
        df2 = df
        entries = [
            _entry(
                _ligne_of(rows[0]),
                "(ligne entière)",
                "doublon potentiel",
                "conservée",
                "revue manuelle",
                "Doublon potentiel examiné et conservé (pas un doublon).",
            )
        ]

    return df2, entries
