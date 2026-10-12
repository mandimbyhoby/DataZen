"""Export de DataFrames pandas vers CSV / Excel."""
from pathlib import Path


def export_dataframe(dataframe, path):
    """Exporte un DataFrame vers un fichier (format déduit de l'extension)."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".csv":
        # Séparateur ";" + BOM UTF-8 : nécessaire pour Excel en français
        # (le séparateur de liste fr-FR est ";", la virgule étant le décimal).
        dataframe.to_csv(
            path,
            index=False,
            sep=";",
            encoding="utf-8-sig",
        )
    elif ext in {".xlsx", ".xls"}:
        dataframe.to_excel(path, index=False)
    else:
        raise ValueError(f"Format d'export non supporté : {ext}")
