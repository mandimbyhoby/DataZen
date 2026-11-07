"""Vues de l'application DataZen."""
import html
import io
import uuid
from pathlib import Path

import pandas as pd
from django.conf import settings
from django.contrib import messages
from django.http import FileResponse
from django.shortcuts import redirect, render

from .forms import CleaningOptionsForm, DataFileUploadForm
from .models import DataFile
from .services.cleaning import DataCleaner, restore_semantic_types
from .services.dashboard import build_dashboard
from .services.exporter import export_dataframe
from .services.markdown import markdown_to_html
from .services.reader import dataframe_to_rows, read_dataframe
from .services.report import build_report
from .services.review import apply_decision, build_review_groups
from .services.validation import (
    build_detection,
    compute_quality_score,
    count_missing_cells,
    verify_consistency,
)

PREVIEW_LIMIT = 10

# Types MIME explicites : sur Windows, `mimetypes` ne connaît pas `.xlsx`,
# sinon le fichier est servi en `application/octet-stream` et devient
# illisible pour les lecteurs Excel en ligne.
CONTENT_TYPES = {
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
}


def index(request):
    """Page d'accueil : téléversement et liste des fichiers (avec recherche)."""
    if request.method == "POST":
        form = DataFileUploadForm(request.POST, request.FILES)
        if form.is_valid():
            data_file = form.save()
            messages.success(request, "Fichier téléversé avec succès.")
            return redirect("core:dataset_detail", pk=data_file.pk)
    else:
        form = DataFileUploadForm()

    # Recherche textuelle par nom de fichier (insensible à la casse).
    query = request.GET.get("q", "").strip()
    # Filtre par statut (uploaded / processing / cleaned / error).
    status = request.GET.get("status", "").strip()
    valid_statuses = {choice.value for choice in DataFile.Status}

    files_qs = DataFile.objects.all()
    if query:
        files_qs = files_qs.filter(original_name__icontains=query)
    if status in valid_statuses:
        files_qs = files_qs.filter(status=status)

    total_files = files_qs.count()
    # Affiche un nombre raisonnable de fichiers (au lieu de 5), pour pouvoir
    # retrouver un fichier parmi les nombreux téléversements.
    recent_files = list(files_qs[:50])

    # Statistiques globales (indépendantes de la recherche/filtre) : elles
    # donnent une vue d'ensemble de l'activité de nettoyage.
    all_files = DataFile.objects.all()
    global_stats = {
        "total": all_files.count(),
        "cleaned": all_files.filter(status=DataFile.Status.CLEANED).count(),
        "pending": all_files.filter(status=DataFile.Status.UPLOADED).count(),
        "errors": all_files.filter(status=DataFile.Status.ERROR).count(),
    }

    context = {
        "form": form,
        "recent_files": recent_files,
        "query": query,
        "status": status,
        "status_choices": DataFile.Status.choices,
        "total_files": total_files,
        "global_stats": global_stats,
    }
    return render(request, "core/index.html", context)


def dataset_detail(request, pk):
    """Prévisualisation et nettoyage d'un fichier téléversé."""
    try:
        data_file = DataFile.objects.get(pk=pk)
    except DataFile.DoesNotExist:
        messages.error(
            request,
            "Ce fichier n'existe plus. Veuillez le téléverser à nouveau.",
        )
        return redirect("core:index")

    try:
        df = read_dataframe(data_file.file.path)
    except Exception as exc:  # noqa: BLE001 — message utilisateur clair
        messages.error(request, f"Impossible de lire ce fichier : {exc}")
        return redirect("core:index")

    form = CleaningOptionsForm(request.POST or None, columns=list(df.columns))

    # Détection : analyse des problèmes avant nettoyage.
    issues = build_detection(df)
    quality_before = compute_quality_score(df, issues)

    context = {
        "data_file": data_file,
        "columns": list(df.columns),
        "stats": _stats(df),
        "preview_rows": dataframe_to_rows(df, limit=PREVIEW_LIMIT),
        "form": form,
        "issues": issues,
        "quality_before": quality_before,
    }

    # Si un nettoyage a déjà eu lieu, on reconstruit tout le contexte
    # « après nettoyage » (score, dashboard, revue, validation, cohérence,
    # journal) directement depuis le fichier nettoyé, afin que la page reste
    # cohérente lors d'un simple rechargement (GET).
    if request.method == "GET" and data_file.cleaned_file:
        try:
            context.update(_build_cleaned_context(data_file, request))
        except Exception:
            # Un fichier nettoyé illisible ne doit pas casser l'affichage.
            pass

    if request.method == "POST" and form.is_valid():
        before = _stats(df)
        operations = []

        cleaner = DataCleaner(df)
        if form.cleaned_data.get("remove_duplicates"):
            ignore_case = form.cleaned_data.get("dedupe_ignore_case", False)
            # Ne supprime que les doublons exacts (lignes identiques). Les
            # doublons potentiels sont signalés, jamais supprimés ici.
            cleaner.remove_duplicates(subset=None, ignore_case=ignore_case)
            removed = cleaner.changes.get("duplicates_removed", 0)
            operations.append(
                f"Suppression des doublons exacts ({removed} supprimé(s))"
            )
        if form.cleaned_data.get("normalize_case"):
            cleaner.normalize_text()
            operations.append("Normalisation de la casse (noms, libellés, villes)")
            cleaner.normalize_categories()
            operations.append(
                f"Normalisation des catégories "
                f"({cleaner.changes.get('categories', 0)} corrigée(s))"
            )
            cleaner.normalize_codes()
            operations.append(
                f"Normalisation des codes/références "
                f"({cleaner.changes.get('codes', 0)} corrigé(s))"
            )
        if form.cleaned_data.get("normalize_emails"):
            cleaner.normalize_emails()
            operations.append(
                f"Validation et correction des emails "
                f"({cleaner.changes.get('emails_corriges', 0)} corrigé(s), "
                f"{cleaner.changes.get('emails_invalides', 0)} invalide(s))"
            )
        if form.cleaned_data.get("normalize_phones"):
            cleaner.normalize_phones()
            operations.append(
                f"Normalisation des téléphones "
                f"({cleaner.changes.get('phones', 0)} corrigé(s))"
            )
        if form.cleaned_data.get("normalize_dates"):
            cleaner.normalize_dates()
            operations.append(
                f"Normalisation des dates "
                f"({cleaner.changes.get('dates', 0)} corrigée(s))"
            )
        if form.cleaned_data.get("normalize_salaries"):
            cleaner.normalize_salaries()
            operations.append(
                f"Conversion des montants "
                f"({cleaner.changes.get('salaries', 0)} converti(s))"
            )
        if form.cleaned_data.get("trim_whitespace"):
            cleaner.trim_whitespace()
            operations.append("Suppression des espaces superflus")
        cleaner.normalize_unknown()
        operations.append(
            f"Canonicalisation du marqueur « Inconnu » "
            f"({cleaner.changes.get('unknown', 0)} corrigé(s))"
        )
        cleaner.normalize_integers()
        operations.append(
            f"Conversion des compteurs en entiers "
            f"({cleaner.changes.get('integers', 0)} converti(s))"
        )
        cleaner.renumber_identifiers()
        operations.append("Renumérotation des identifiants (ancien id conservé)")
        if form.cleaned_data.get("fill_missing"):
            value = form.cleaned_data.get("fill_missing_value", "")
            cleaner.fill_missing(value)
            operations.append(
                f"Remplissage des valeurs manquantes par « {value} » "
                "(les montants, codes et dates ne reçoivent jamais un texte)"
            )

        cleaned_df = cleaner.result
        after = _stats(cleaned_df)

        # Validation : on ré-analyse le résultat pour signaler ce qui reste.
        validation = build_detection(cleaned_df)
        quality_after = compute_quality_score(cleaned_df, validation)

        # Contrôle de cohérence : compare les statistiques annoncées aux
        # valeurs réelles du DataFrame final et signale toute divergence.
        change_log_df = cleaner.change_log_df
        consistency = verify_consistency(
            cleaned_df,
            detection=validation,
            change_log_df=change_log_df,
            changes=cleaner.changes,
        )

        rel_path = _save_cleaned_file(data_file, cleaned_df)
        data_file.cleaned_file.name = rel_path
        data_file.status = DataFile.Status.CLEANED
        data_file.save()

        # Journal des modifications (traçabilité).
        if not change_log_df.empty:
            change_log_rel = _save_change_log_file(data_file, change_log_df)
            data_file.change_log_file.name = change_log_rel

        # Rapport automatique de qualité des données.
        report_text = build_report(
            data_file.original_name,
            operations,
            before,
            after,
            detected=issues,
            validation=validation,
            changes=cleaner.changes,
            quality_before=quality_before,
            quality_after=quality_after,
            change_log=change_log_df,
            email_audit=cleaner.email_audit,
            consistency=consistency,
        )
        report_rel = _save_report_file(data_file, report_text)
        data_file.report_file.name = report_rel
        data_file.save(
            update_fields=["report_file", "change_log_file", "updated_at"]
        )

        # Persistance des opérations en session (équivalent st.session_state) :
        # permet de réafficher le dashboard et les opérations après rechargement.
        request.session[f"operations_{data_file.pk}"] = operations

        context.update(_build_cleaned_context(data_file, request))
        messages.success(request, "Nettoyage terminé avec succès.")

    return render(request, "core/dataset_detail.html", context)


def download_cleaned(request, pk):
    """Télécharge le fichier nettoyé, au format CSV ou Excel (au choix).

    Le paramètre ``format`` (``csv`` / ``xlsx``) permet de convertir à la
    volée : un fichier d'origine Excel peut être téléchargé en CSV et
    inversement, sans modifier le fichier nettoyé stocké.
    """
    try:
        data_file = DataFile.objects.get(pk=pk)
    except DataFile.DoesNotExist:
        messages.error(
            request,
            "Ce fichier n'existe plus. Veuillez le téléverser à nouveau.",
        )
        return redirect("core:index")

    if not data_file.cleaned_file:
        messages.error(request, "Aucun fichier nettoyé n'est disponible.")
        return redirect("core:dataset_detail", pk=pk)

    filename = Path(data_file.cleaned_file.name).name
    current_ext = Path(filename).suffix.lower().lstrip(".")

    # Conversion à la volée vers un autre format si demandé.
    fmt = request.GET.get("format", "").strip().lower()
    if fmt in {"csv", "xlsx", "xls"} and fmt != current_ext:
        try:
            df = restore_semantic_types(
                read_dataframe(data_file.cleaned_file.path)
            )
            if fmt == "csv":
                buffer = io.BytesIO()
                df.to_csv(
                    buffer, index=False, sep=";", encoding="utf-8-sig"
                )
                buffer.seek(0)
                return FileResponse(
                    buffer,
                    as_attachment=True,
                    filename=f"{Path(filename).stem}.csv",
                    content_type=CONTENT_TYPES[".csv"],
                )
            buffer = io.BytesIO()
            df.to_excel(buffer, index=False)
            buffer.seek(0)
            return FileResponse(
                buffer,
                as_attachment=True,
                filename=f"{Path(filename).stem}.xlsx",
                content_type=CONTENT_TYPES[".xlsx"],
            )
        except Exception as exc:  # noqa: BLE001 — message utilisateur clair
            messages.error(request, f"Impossible de convertir le fichier : {exc}")
            return redirect("core:dataset_detail", pk=pk)

    content_type = CONTENT_TYPES.get(
        Path(filename).suffix.lower(), "application/octet-stream"
    )
    return FileResponse(
        data_file.cleaned_file.open("rb"),
        as_attachment=True,
        filename=filename,
        content_type=content_type,
    )


def download_original(request, pk):
    """Télécharge le fichier d'origine (avant nettoyage)."""
    try:
        data_file = DataFile.objects.get(pk=pk)
    except DataFile.DoesNotExist:
        messages.error(
            request,
            "Ce fichier n'existe plus. Veuillez le téléverser à nouveau.",
        )
        return redirect("core:index")

    if not data_file.file:
        messages.error(request, "Aucun fichier d'origine n'est disponible.")
        return redirect("core:dataset_detail", pk=pk)

    filename = Path(data_file.file.name).name
    content_type = CONTENT_TYPES.get(
        Path(filename).suffix.lower(), "application/octet-stream"
    )
    return FileResponse(
        data_file.file.open("rb"),
        as_attachment=True,
        filename=filename,
        content_type=content_type,
    )


def delete_dataset(request, pk):
    """Supprime un fichier de données et tous ses fichiers associés.

    Suppression explicite (POST avec confirmation) : l'utilisateur garde
    toujours la main. Les fichiers physiques (original, nettoyé, rapport,
    journal) sont également supprimés du stockage.
    """
    try:
        data_file = DataFile.objects.get(pk=pk)
    except DataFile.DoesNotExist:
        messages.error(request, "Ce fichier n'existe plus.")
        return redirect("core:index")

    if request.method != "POST":
        return redirect("core:dataset_detail", pk=pk)

    name = data_file.original_name
    for field in (
        data_file.file,
        data_file.cleaned_file,
        data_file.report_file,
        data_file.change_log_file,
    ):
        if field:
            field.delete(save=False)
    data_file.delete()

    messages.success(request, f"Fichier « {name} » supprimé.")
    return redirect("core:index")


def download_report(request, pk):
    """Télécharge le rapport de nettoyage."""
    try:
        data_file = DataFile.objects.get(pk=pk)
    except DataFile.DoesNotExist:
        messages.error(
            request,
            "Ce fichier n'existe plus. Veuillez le téléverser à nouveau.",
        )
        return redirect("core:index")

    if not data_file.report_file:
        messages.error(request, "Aucun rapport de nettoyage n'est disponible.")
        return redirect("core:dataset_detail", pk=pk)

    filename = Path(data_file.report_file.name).name
    return FileResponse(
        data_file.report_file.open("rb"),
        as_attachment=True,
        filename=filename,
        content_type="text/markdown; charset=utf-8",
    )


def view_report(request, pk):
    """Affiche le rapport de nettoyage directement dans le navigateur.

    Le rapport est stocké en Markdown ; il est converti en HTML via
    :func:`core.services.markdown.markdown_to_html` pour une lecture
    confortable, sans téléchargement.
    """
    try:
        data_file = DataFile.objects.get(pk=pk)
    except DataFile.DoesNotExist:
        messages.error(
            request,
            "Ce fichier n'existe plus. Veuillez le téléverser à nouveau.",
        )
        return redirect("core:index")

    if not data_file.report_file:
        messages.error(request, "Aucun rapport de nettoyage n'est disponible.")
        return redirect("core:dataset_detail", pk=pk)

    try:
        markdown_text = Path(data_file.report_file.path).read_text(
            encoding="utf-8"
        )
    except Exception as exc:  # noqa: BLE001 — message utilisateur clair
        messages.error(request, f"Impossible de lire le rapport : {exc}")
        return redirect("core:dataset_detail", pk=pk)

    context = {
        "data_file": data_file,
        "report_html": markdown_to_html(markdown_text),
    }
    return render(request, "core/report_view.html", context)


def download_report_html(request, pk):
    """Télécharge le rapport converti en HTML autonome (stylé)."""
    try:
        data_file = DataFile.objects.get(pk=pk)
    except DataFile.DoesNotExist:
        messages.error(
            request,
            "Ce fichier n'existe plus. Veuillez le téléverser à nouveau.",
        )
        return redirect("core:index")

    if not data_file.report_file:
        messages.error(request, "Aucun rapport de nettoyage n'est disponible.")
        return redirect("core:dataset_detail", pk=pk)

    try:
        markdown_text = Path(data_file.report_file.path).read_text(
            encoding="utf-8"
        )
    except Exception as exc:  # noqa: BLE001 — message utilisateur clair
        messages.error(request, f"Impossible de lire le rapport : {exc}")
        return redirect("core:dataset_detail", pk=pk)

    body = markdown_to_html(markdown_text)
    title = html.escape(data_file.original_name)
    document = _wrap_html_document(title, body)

    buffer = io.BytesIO(document.encode("utf-8"))
    stem = Path(data_file.report_file.name).stem
    return FileResponse(
        buffer,
        as_attachment=True,
        filename=f"{stem}.html",
        content_type="text/html; charset=utf-8",
    )


def _wrap_html_document(title, body):
    """Enveloppe un fragment HTML dans un document autonome et stylé."""
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Rapport — {title}</title>
<style>
  body {{ font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
         max-width: 960px; margin: 2rem auto; padding: 0 1rem; color: #212529; }}
  h1, h2, h3 {{ color: #0d6efd; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
  th, td {{ border: 1px solid #dee2e6; padding: 0.5rem 0.75rem; text-align: left; }}
  th {{ background: #f8f9fa; }}
  code {{ background: #f1f3f5; padding: 0.1rem 0.3rem; border-radius: 0.25rem; }}
  hr {{ border: none; border-top: 1px solid #dee2e6; margin: 1.5rem 0; }}
</style>
</head>
<body>
{body}
</body>
</html>"""


def download_change_log(request, pk):
    """Télécharge le journal des modifications (change_log)."""
    try:
        data_file = DataFile.objects.get(pk=pk)
    except DataFile.DoesNotExist:
        messages.error(
            request,
            "Ce fichier n'existe plus. Veuillez le téléverser à nouveau.",
        )
        return redirect("core:index")

    if not data_file.change_log_file:
        messages.error(
            request, "Aucun journal des modifications n'est disponible."
        )
        return redirect("core:dataset_detail", pk=pk)

    filename = Path(data_file.change_log_file.name).name
    return FileResponse(
        data_file.change_log_file.open("rb"),
        as_attachment=True,
        filename=filename,
        content_type="text/csv; charset=utf-8",
    )


def review_duplicate(request, pk):
    """Applique une décision manuelle sur un doublon potentiel.

    L'action n'est jamais appliquée sans interaction explicite de
    l'utilisateur (POST avec ``action`` + confirmation dans l'interface).
    Après application, le DataFrame final est mis à jour, les ``id``
    renumérotés (``ancien_id`` conservé), le journal complété, puis on
    redirige vers la page de détail qui recalcule score/dashboard/validation.
    """
    try:
        data_file = DataFile.objects.get(pk=pk)
    except DataFile.DoesNotExist:
        messages.error(request, "Ce fichier n'existe plus.")
        return redirect("core:index")

    if request.method != "POST":
        return redirect("core:dataset_detail", pk=pk)

    if not data_file.cleaned_file:
        messages.error(request, "Aucun fichier nettoyé n'est disponible.")
        return redirect("core:dataset_detail", pk=pk)

    action = request.POST.get("action", "")
    ancien_ids = [
        x for x in request.POST.get("ancien_ids", "").split(",") if x.strip()
    ]

    valid_actions = {"keep_a", "keep_b", "merge", "keep_both", "ignore"}
    if action not in valid_actions or not ancien_ids:
        messages.error(request, "Action invalide.")
        return redirect("core:dataset_detail", pk=pk)

    try:
        cleaned_df = restore_semantic_types(
            read_dataframe(data_file.cleaned_file.path)
        )
        new_df, entries = apply_decision(cleaned_df, ancien_ids, action)

        # Renumérotation des id (ancien_id conservé) via le moteur existant.
        if action in {"keep_a", "keep_b", "merge"}:
            renumbered = DataCleaner(new_df)
            renumbered.renumber_identifiers()
            new_df = renumbered.result

        # Écrit le DataFrame final dans le fichier nettoyé (même chemin).
        _overwrite_cleaned_file(data_file, new_df)

        # Ajoute les entrées manuelles au journal (schéma strict conservé).
        _append_change_log(data_file, entries)
    except Exception as exc:  # noqa: BLE001 — message utilisateur clair
        messages.error(request, f"Impossible d'appliquer la décision : {exc}")
        return redirect("core:dataset_detail", pk=pk)

    messages.success(request, "Décision appliquée avec succès.")
    return redirect("core:dataset_detail", pk=pk)


def _stats(df):
    """Calcule des statistiques simples sur un DataFrame.

    ``duplicates`` = doublons **exacts** (casse/espaces ignorés, colonnes
    d'identifiant exclues), calculés par :func:`validation.detect_duplicates`
    afin d'être cohérents avec le reste de l'application (le simple
    ``df.duplicated()`` inclurait ``id``/``ancien_id`` et serait trompeur).
    """
    return {
        "rows": len(df),
        "columns": df.shape[1],
        "duplicates": build_detection(df)["duplicates"],
        "missing": count_missing_cells(df),
    }


def _save_cleaned_file(data_file, df):
    """Exporte le DataFrame nettoyé et renvoie son chemin relatif."""
    original = Path(data_file.original_name or "donnees.csv")
    ext = original.suffix.lower() or ".csv"
    if ext not in {".csv", ".xlsx", ".xls"}:
        ext = ".csv"

    filename = f"{original.stem}_nettoye_{uuid.uuid4().hex[:6]}{ext}"
    rel_dir = Path("cleaned")
    abs_dir = Path(settings.MEDIA_ROOT) / rel_dir
    abs_dir.mkdir(parents=True, exist_ok=True)

    export_dataframe(df, abs_dir / filename)
    return (rel_dir / filename).as_posix()


def _save_report_file(data_file, report_text):
    """Écrit le rapport de nettoyage et renvoie son chemin relatif."""
    original = Path(data_file.original_name or "donnees.csv")
    filename = f"{original.stem}_rapport_{uuid.uuid4().hex[:6]}.md"
    rel_dir = Path("reports")
    abs_dir = Path(settings.MEDIA_ROOT) / rel_dir
    abs_dir.mkdir(parents=True, exist_ok=True)

    (abs_dir / filename).write_text(report_text, encoding="utf-8")
    return (rel_dir / filename).as_posix()


def _save_change_log_file(data_file, change_log_df):
    """Écrit le journal des modifications (CSV) et renvoie son chemin relatif."""
    original = Path(data_file.original_name or "donnees.csv")
    filename = f"{original.stem}_change_log_{uuid.uuid4().hex[:6]}.csv"
    rel_dir = Path("logs")
    abs_dir = Path(settings.MEDIA_ROOT) / rel_dir
    abs_dir.mkdir(parents=True, exist_ok=True)

    export_dataframe(change_log_df, abs_dir / filename)
    return (rel_dir / filename).as_posix()


# Colonnes strictes du journal de modification (ne jamais en ajouter).
CHANGE_LOG_COLUMNS = [
    "ligne",
    "colonne",
    "ancienne_valeur",
    "nouvelle_valeur",
    "type_correction",
    "raison",
]


def _empty_change_log():
    """Journal vide avec le schéma strict du journal."""
    return pd.DataFrame(columns=CHANGE_LOG_COLUMNS)


def _read_change_log(data_file):
    """Relit le journal de modification existant (ou un journal vide)."""
    if not data_file.change_log_file:
        return _empty_change_log()
    path = Path(settings.MEDIA_ROOT) / data_file.change_log_file.name
    if not path.exists():
        return _empty_change_log()
    try:
        return read_dataframe(str(path))
    except Exception:
        return _empty_change_log()


def _changes_from_log(change_log_df):
    """Reconstruit les compteurs ``changes`` depuis le journal (pour le
    contrôle de cohérence après rechargement/relecture)."""
    changes = {}
    if change_log_df is not None and not change_log_df.empty:
        if "type_correction" in change_log_df.columns:
            vc = change_log_df["type_correction"].value_counts()
            changes["emails_corriges"] = int(vc.get("email", 0))
            changes["phones"] = int(vc.get("téléphone", 0))
            changes["dates"] = int(vc.get("date", 0))
            changes["categories"] = int(vc.get("catégorie", 0))
            changes["salaries"] = int(vc.get("numérique", 0))
            changes["duplicates_removed"] = int(vc.get("doublon", 0))
    return changes


def _build_cleaned_context(data_file, request):
    """Reconstruit tout le contexte « après nettoyage » depuis le fichier nettoyé.

    Réutilise uniquement les fonctions existantes : aucun calcul dupliqué.
    """
    cleaned_df = restore_semantic_types(
        read_dataframe(data_file.cleaned_file.path)
    )
    change_log_df = _read_change_log(data_file)

    validation = build_detection(cleaned_df)
    quality_after = compute_quality_score(cleaned_df, validation)
    consistency = verify_consistency(
        cleaned_df,
        detection=validation,
        change_log_df=change_log_df,
        changes=_changes_from_log(change_log_df),
    )
    operations = request.session.get(f"operations_{data_file.pk}", [])
    dashboard = build_dashboard(
        cleaned_df,
        detection=validation,
        score=quality_after,
        change_log_df=change_log_df,
        operations=operations,
    )
    review_groups = build_review_groups(cleaned_df)

    return {
        "cleaned": True,
        "cleaned_stats": _stats(cleaned_df),
        "cleaned_columns": list(cleaned_df.columns),
        # Affiche TOUTES les lignes du résultat nettoyé (le fichier a déjà été
        # dédupliqué ; il est en général petit). Limiter l'aperçu faisait croire
        # à tort que des lignes (ex. une ligne fusionnée en fin de tableau)
        # avaient disparu.
        "cleaned_preview_rows": dataframe_to_rows(cleaned_df, limit=None),
        "report": data_file.report_file,
        "operations": operations,
        "validation": validation,
        "quality_after": quality_after,
        "change_log": data_file.change_log_file,
        "consistency": consistency,
        "dashboard": dashboard,
        "review_groups": review_groups,
    }


def _overwrite_cleaned_file(data_file, df):
    """Réécrit le DataFrame final dans le fichier nettoyé existant."""
    path = Path(settings.MEDIA_ROOT) / data_file.cleaned_file.name
    path.parent.mkdir(parents=True, exist_ok=True)
    export_dataframe(df, path)


def _append_change_log(data_file, entries):
    """Ajoute des entrées au journal de modification (même schéma strict)."""
    if not entries:
        return
    existing = _read_change_log(data_file)
    new = pd.DataFrame(entries, columns=CHANGE_LOG_COLUMNS)
    combined = pd.concat([existing, new], ignore_index=True)

    if not data_file.change_log_file:
        data_file.change_log_file.name = _save_change_log_file(data_file, combined)
    else:
        path = Path(settings.MEDIA_ROOT) / data_file.change_log_file.name
        export_dataframe(combined, path)
    data_file.save(update_fields=["change_log_file", "updated_at"])
