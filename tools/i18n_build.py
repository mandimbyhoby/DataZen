"""Génère les catalogues de traduction (.po + .mo) sans GNU gettext.

Ce script remplace ``makemessages`` / ``compilemessages``, indisponibles sur
cette machine. Il s'appuie sur :

* ``tools/i18n_extract.py`` pour l'inventaire des chaînes (msgid) ;
* ``tools/translations/`` pour les traductions (msgstr).

Le format binaire ``.mo`` est écrit à la main (``struct``), ce qui évite toute
dépendance externe.

Usage :
    python tools/i18n_build.py                 # toutes les langues
    python tools/i18n_build.py --only en es    # langues choisies
    python tools/i18n_build.py --stats         # taux de couverture
"""

from __future__ import annotations

import argparse
import json
import os
import struct
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "tools"))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "datazen.settings")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402

from tools.i18n_extract import (  # noqa: E402
    extract_compiled,
    extract_python,
    extract_templates,
)
from tools.translations import CATALOGS, LANGUAGE_NAMES  # noqa: E402

LOCALE_DIR = BASE_DIR / "locale"
PLURAL_FORMS = {
    "ar": "nplurals=6; plural=(n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 : n%100>=11 ? 4 : 5);",
    "cs": "nplurals=3; plural=(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2;",
    "da": "nplurals=2; plural=(n != 1);",
    "de": "nplurals=2; plural=(n != 1);",
    "en": "nplurals=2; plural=(n != 1);",
    "es": "nplurals=2; plural=(n != 1);",
    "fi": "nplurals=2; plural=(n != 1);",
    "fr": "nplurals=2; plural=(n > 1);",
    "hi": "nplurals=2; plural=(n != 1);",
    "id": "nplurals=1; plural=0;",
    "it": "nplurals=2; plural=(n != 1);",
    "ja": "nplurals=1; plural=0;",
    "ko": "nplurals=1; plural=0;",
    "nl": "nplurals=2; plural=(n != 1);",
    "pl": "nplurals=3; plural=(n==1 ? 0 : n%10>=2 && n%10<=4 && (n%100<12 || n%100>14) ? 1 : 2);",
    "pt": "nplurals=2; plural=(n != 1);",
    "ro": "nplurals=3; plural=(n==1 ? 0 : (n==0 || (n%100 > 0 && n%100 < 20)) ? 1 : 2);",
    "ru": "nplurals=3; plural=(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<12 || n%100>14) ? 1 : 2);",
    "sv": "nplurals=2; plural=(n != 1);",
    "th": "nplurals=1; plural=0;",
    "tr": "nplurals=2; plural=(n > 1);",
    "vi": "nplurals=1; plural=0;",
    "zh-hans": "nplurals=1; plural=0;",
}


def plural_count(code: str) -> int:
    """Nombre de formes plurielles déclarées pour une langue.

    ``PLURAL_FORMS`` commence toujours par ``nplurals=N;`` : on relit ``N``
    plutôt que de dupliquer la table.
    """
    declaration = PLURAL_FORMS.get(code, PLURAL_FORMS["en"])
    return int(declaration.split("nplurals=", 1)[1].split(";", 1)[0])


def plural_value(value, code: str) -> list[str]:
    """Normalise une traduction plurielle en liste de ``nplurals`` formes.

    Les catalogues déclarent souvent une seule forme (le singulier) pour un
    msgid pluriel. Sans complétion, ``write_mo`` n'écrit que ``msgstr[0]`` et
    ``gettext`` retombe sur le msgid — donc sur le français — dès que la
    langue demande une autre forme. On réplique la forme fournie sur toutes
    les formes attendues, ce qui est le comportement voulu pour les langues
    à deux formes (anglais, allemand…) comme pour celles à forme unique.
    """
    forms = list(value) if isinstance(value, (list, tuple)) else [value or ""]
    expected = plural_count(code)
    while len(forms) < expected:
        forms.append(forms[-1] if forms else "")
    return forms[:expected]


def po_escape(text: str) -> str:
    """Échappe une chaîne pour un fichier .po."""
    return (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
        .replace("\r", "\\r")
    )


def collect_entries() -> list[tuple[str, str | None, str | None]]:
    """Retourne les entrées triées : ``(msgid, msgid_plural, context)``.

    Le contrat est uniforme pour les trois extracteurs, ce qui permet de
    distinguer un pluriel d'un contexte : le contexte alimente ``msgctxt``
    (et la clé ``contexte\\x04msgid`` du ``.mo``), le pluriel alimente
    ``msgid_plural``. Un même ``msgid`` peut apparaître avec et sans
    contexte : ce sont alors deux entrées distinctes.
    """
    seen: set[tuple[str, str | None]] = set()
    plurals: dict[tuple[str, str | None], str] = {}
    for group in (extract_compiled(), extract_templates(), extract_python()):
        for messages in group.values():
            for msgid, plural, context in messages:
                key = (msgid, context)
                seen.add(key)
                if plural and key not in plurals:
                    plurals[key] = plural
    entries = [(msgid, plurals.get((msgid, context)), context) for msgid, context in seen]
    return sorted(entries, key=lambda entry: (entry[2] or "", entry[0]))


def catalog_value(catalog: dict[str, str], msgid: str, context: str | None):
    """Traduction d'une entrée contextuelle, avec repli sur le msgid nu.

    ``DjangoTranslation.pgettext`` cherche la clé ``contexte\\x04msgid`` : une
    entrée contextuelle doit donc être présente sous cette forme dans le
    catalogue. À défaut, on réutilise la traduction non contextuelle.
    """
    if context:
        value = catalog.get(f"{context}\x04{msgid}")
        if value:
            return value
    return catalog.get(msgid, "")


def write_po(
    path: Path,
    code: str,
    entries: list[tuple[str, str | None, str | None]],
    catalog: dict[str, str],
) -> int:
    """Écrit un fichier .po et retourne le nombre de chaînes traduites."""
    header = (
        "Project-Id-Version: DataZen 1.0\n"
        "Report-Msgid-Bugs-To: \n"
        "MIME-Version: 1.0\n"
        "Content-Type: text/plain; charset=UTF-8\n"
        "Content-Transfer-Encoding: 8bit\n"
        f"Language: {code}\n"
        f"Plural-Forms: {PLURAL_FORMS.get(code, PLURAL_FORMS['en'])}\n"
    )
    lines = [
        "# Catalogue de traduction DataZen.",
        "# Généré par tools/i18n_build.py — ne pas éditer à la main.",
        "msgid \"\"",
        "msgstr \"\"",
    ]
    lines += [f'"{line}\\n"' for line in header.splitlines()]

    translated = 0
    for msgid, plural, context in entries:
        value = catalog_value(catalog, msgid, context)
        if value:
            translated += 1
        lines.append("")
        if context:
            lines.append(f'msgctxt "{po_escape(context)}"')
        lines.append(f'msgid "{po_escape(msgid)}"')
        if plural:
            lines.append(f'msgid_plural "{po_escape(plural)}"')
            for index, form in enumerate(plural_value(value, code)):
                lines.append(f'msgstr[{index}] "{po_escape(form)}"')
        else:
            lines.append(f'msgstr "{po_escape(value)}"')

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return translated


def mo_key(msgid: str, plural: str | None, context: str | None) -> bytes:
    """Clé binaire d'une entrée ``.mo`` (format GNU).

    Le contexte et le pluriel sont encodés dans la clé elle-même :
    ``contexte\\x04msgid`` et ``msgid\\x00msgid_plural``. C'est exactement ce
    que ``GNUTranslations`` attend pour ``pgettext`` et ``ngettext``.
    """
    key = f"{context}\x04{msgid}" if context else msgid
    if plural:
        key = f"{key}\x00{plural}"
    return key.encode("utf-8")


def write_mo(
    path: Path,
    code: str,
    entries_in: list[tuple[str, str | None, str | None]],
    catalog: dict[str, str],
) -> None:
    """Écrit un fichier .mo binaire (format GNU, little-endian)."""
    header = (
        "Project-Id-Version: DataZen 1.0\n"
        "MIME-Version: 1.0\n"
        "Content-Type: text/plain; charset=UTF-8\n"
        "Content-Transfer-Encoding: 8bit\n"
        f"Language: {code}\n"
        f"Plural-Forms: {PLURAL_FORMS.get(code, PLURAL_FORMS['en'])}\n"
    )
    # L'entrée d'en-tête (msgid vide) porte le charset : sans elle, Python
    # retombe sur ASCII et échoue sur les accents.
    entries: list[tuple[bytes, bytes]] = [(b"", header.encode("utf-8"))]

    for msgid, plural, context in entries_in:
        value = catalog_value(catalog, msgid, context)
        if not value:
            continue
        if plural:
            forms = plural_value(value, code)
            body = b"\x00".join(form.encode("utf-8") for form in forms)
        else:
            body = value.encode("utf-8")
        entries.append((mo_key(msgid, plural, context), body))

    entries.sort(key=lambda item: item[0])

    count = len(entries)
    # En-tête : 7 mots de 32 bits.
    key_table_offset = 7 * 4
    value_table_offset = key_table_offset + count * 8
    string_offset = value_table_offset + count * 8

    key_table = bytearray()
    key_blob = bytearray()
    for key, _body in entries:
        key_table += struct.pack("<II", len(key), string_offset + len(key_blob))
        key_blob += key + b"\x00"

    # Les valeurs commencent après l'intégralité du bloc des clés : il faut
    # donc construire les clés d'abord, puis calculer les offsets des valeurs.
    value_base = string_offset + len(key_blob)
    value_table = bytearray()
    value_blob = bytearray()
    for _key, body in entries:
        value_table += struct.pack("<II", len(body), value_base + len(value_blob))
        value_blob += body + b"\x00"

    output = bytearray()
    output += struct.pack(
        "<7I",
        0x950412DE,  # magic
        0,  # revision
        count,
        key_table_offset,
        value_table_offset,
        0,  # hash table size
        0,  # hash table offset
    )
    output += key_table
    output += value_table
    output += key_blob
    output += value_blob

    path.write_bytes(bytes(output))


def build(codes: list[str] | None = None, stats_only: bool = False) -> None:
    entries = collect_entries()
    codes = codes or list(CATALOGS.keys())
    contextual = sum(1 for _msgid, _plural, context in entries if context)
    plural_count = sum(1 for _msgid, plural, _context in entries if plural)

    print(
        f"{len(entries)} chaînes à traduire "
        f"({plural_count} plurielles, {contextual} contextuelles)."
    )
    print()

    for code in codes:
        catalog = CATALOGS.get(code)
        if catalog is None:
            print(f"  {code:<8} absent de tools/translations/ — ignoré")
            continue

        translated = sum(
            1
            for msgid, _plural, context in entries
            if catalog_value(catalog, msgid, context)
        )
        percent = translated * 100 // max(len(entries), 1)
        name = LANGUAGE_NAMES.get(code, code)
        print(f"  {code:<8} {name:<22} {translated:>3}/{len(entries)} ({percent:>3}%)")

        if stats_only:
            continue

        target = LOCALE_DIR / code.replace("-", "_") / "LC_MESSAGES"
        target.mkdir(parents=True, exist_ok=True)
        write_po(target / "django.po", code, entries, catalog)
        write_mo(target / "django.mo", code, entries, catalog)

    if not stats_only:
        print()
        print(f"Catalogues écrits dans {LOCALE_DIR}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="*", help="codes de langue à générer")
    parser.add_argument("--stats", action="store_true", help="afficher la couverture seulement")
    args = parser.parse_args()
    build(args.only, args.stats)


if __name__ == "__main__":
    main()