"""Export de DataFrames pandas vers CSV / Excel."""
from pathlib import Path

import pandas as pd

# Caractères qui déclenchent l'évaluation d'une formule par Excel / LibreOffice.
# Une cellule commençant par l'un d'eux est interprétée comme une formule, ce
# qui permet une exécution de commande (DDE) ou une exfiltration via
# HYPERLINK dès que la victime ouvre le fichier exporté.
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def neutralize_formula(value):
    """Neutralise une valeur qui serait interprétée comme une formule.

    Le préfixe ``'`` est la convention tableur : la cellule reste du texte et
    la valeur affichée est inchangée. Les valeurs non textuelles (nombres,
    dates, booléens) sont renvoyées telles quelles — un nombre négatif doit
    rester un nombre.
    """
    if not isinstance(value, str) or not value:
        return value
    if value.startswith(FORMULA_PREFIXES):
        return "'" + value
    return value


def neutralize_dataframe(dataframe):
    """Renvoie une copie du DataFrame avec les formules neutralisées.

    Seules les colonnes de type texte sont parcourues : les colonnes
    numériques ou temporelles ne peuvent pas porter de formule. Depuis pandas 3,
    une colonne de chaînes n'a plus le type ``object`` mais ``StringDtype`` :
    les deux formes sont donc reconnues.
    """
    if dataframe is None or dataframe.empty:
        return dataframe
    text_columns = [
        column
        for column in dataframe.columns
        if dataframe[column].dtype == object
        or isinstance(dataframe[column].dtype, pd.CategoricalDtype)
        or pd.api.types.is_string_dtype(dataframe[column].dtype)
    ]
    if not text_columns:
        return dataframe
    safe = dataframe.copy()
    for column in text_columns:
        safe[column] = safe[column].map(neutralize_formula)
    return safe


def export_dataframe(dataframe, path):
    """Exporte un DataFrame vers un fichier (format déduit de l'extension)."""
    path = Path(path)
    ext = path.suffix.lower()
    dataframe = neutralize_dataframe(dataframe)
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
