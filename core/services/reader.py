"""Lecture de fichiers de données (CSV / Excel) avec Pandas."""
from pathlib import Path

import pandas as pd

SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls"}


def read_dataframe(file_path):
    """Lit un fichier CSV ou Excel et renvoie un DataFrame pandas."""
    path = Path(file_path)
    ext = path.suffix.lower()
    if ext == ".csv":
        # Auto-détection du séparateur (virgule ou point-virgule) et
        # gestion du BOM UTF-8, pour relire indifféremment les fichiers
        # importés et les fichiers nettoyés exportés par l'application.
        return pd.read_csv(path, sep=None, engine="python", encoding="utf-8-sig")
    if ext in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    raise ValueError(f"Format de fichier non supporté : {ext}")


def dataframe_to_rows(df, limit=10):
    """Convertit les premières lignes d'un DataFrame en liste de listes."""
    head = df.head(limit)
    head = head.astype(object).where(pd.notna(head), None)
    return head.values.tolist()
