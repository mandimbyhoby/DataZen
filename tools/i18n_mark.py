"""Marque les textes visibles des templates avec des balises de traduction.

Le repérage s'appuie sur une lecture token par token du template : balises
Django (``{% %}``), variables (``{{ }}``), commentaires HTML, balises HTML et
texte. Seuls le texte et les valeurs de certains attributs HTML sont
transformés, ce qui évite de toucher au JavaScript ou aux balises Django.

Les remplacements sont appliqués du dernier au premier : les décalages
calculés sur le fichier d'origine restent donc tous valides.

La balise ``{% load i18n %}`` est ajoutée après un éventuel ``{% extends %}``,
car Django interdit toute autre balise avant l'héritage de template.

Attention : les fichiers sont lus et écrits en UTF-8.

Usage :
    python tools/i18n_mark.py --dry-run          # inventaire seulement
    python tools/i18n_mark.py --apply            # réécrit les templates
    python tools/i18n_mark.py --apply --only X   # un seul template
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"

SKIP_TAGS = ("script", "style", "pre", "code", "svg", "textarea")
TRANSLATABLE_ATTRS = ("placeholder", "title", "aria-label", "alt", "label")

TOKEN_RE = re.compile(
    r"\{%-?.*?-?%\}"
    r"|\{\{.*?\}\}"
    r"|<!--.*?-->"
    r"|<[^>]*>",
    re.DOTALL,
)

TAG_NAME_RE = re.compile(r"(?s)^<\s*/?\s*([a-zA-Z][a-zA-Z0-9:-]*)")
ATTR_RE = re.compile(
    r'\b('
    + "|".join(re.escape(a) for a in TRANSLATABLE_ATTRS)
    + r')\s*=\s*"([^"{}<>]*)"'
)
HAS_LETTER = re.compile(
    r"[A-Za-z\u00c0-\u024f\u0370-\u03ff\u0400-\u04ff\u0530-\u058f"
    r"\u0590-\u05ff\u0600-\u06ff\u0900-\u097f\u0e00-\u0e7f"
    r"\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7af]"
)
# Un noeud de texte qui contient l'un de ces caractères est du code, pas de la prose.
CODE_CHARS = re.compile(r"[{}<>$#@\\|]")


def strip_django(text: str) -> str:
    """Supprime variables et balises Django d'un fragment de template."""
    return re.sub(r"(?s)\{%-?.*?-?%\}|\{\{.*?\}\}", " ", text)


def is_translatable(text: str) -> bool:
    """Vrai si le texte mérite une balise de traduction."""
    stripped = text.strip()
    if len(stripped) < 2:
        return False
    if not HAS_LETTER.search(stripped):
        return False
    return not CODE_CHARS.search(strip_django(stripped))


def _quote(text: str) -> str:
    """Échappe un texte pour l'insérer dans ``{% translate "..." %}``."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


def build_replacement(text: str) -> str:
    """Construit la balise de traduction en conservant les espaces externes."""
    core = text.strip()
    leading = text[: len(text) - len(text.lstrip())]
    trailing = text[len(text.rstrip()) :]

    if "\n" in core or "\r" in core:
        return (
            f"{leading}{{% blocktranslate trimmed %}}{core}"
            f"{{% endblocktranslate %}}{trailing}"
        )
    return f'{leading}{{% translate "{_quote(core)}" %}}{trailing}'


def find_text_spans(masked: str) -> list[tuple[int, int, str]]:
    """Repère les noeuds de texte hors balises dont la traduction a du sens."""
    spans: list[tuple[int, int, str]] = []
    pos = 0
    skip_depth = 0

    for match in TOKEN_RE.finditer(masked):
        if match.start() > pos and skip_depth == 0:
            chunk = masked[pos : match.start()]
            if is_translatable(chunk):
                spans.append((pos, match.start(), build_replacement(chunk)))

        token = match.group(0)
        if token.startswith("<"):
            name = TAG_NAME_RE.match(token)
            tag = name.group(1).lower() if name else ""
            if tag in SKIP_TAGS:
                if token.startswith("</"):
                    skip_depth = max(0, skip_depth - 1)
                elif not token.endswith("/>"):
                    skip_depth += 1
            elif tag == "br" and token == "<br>":
                pass
        pos = match.end()

    if pos < len(masked) and skip_depth == 0:
        chunk = masked[pos:]
        if is_translatable(chunk):
            spans.append((pos, len(masked), build_replacement(chunk)))

    return spans


def find_attr_spans(masked: str) -> list[tuple[int, int, str]]:
    """Repère les valeurs d'attributs HTML traduisibles."""
    spans: list[tuple[int, int, str]] = []
    for token in TOKEN_RE.finditer(masked):
        tag_html = token.group(0)
        if not tag_html.startswith("<"):
            continue
        for attr in ATTR_RE.finditer(tag_html):
            value = attr.group(2)
            if not is_translatable(value):
                continue
            start = token.start() + attr.start(2)
            end = token.start() + attr.end(2)
            spans.append((start, end, build_replacement(value)))
    return spans


def strip_ignored(raw: str) -> str:
    """Neutralise les zones à ne jamais traduire (script, style, commentaires)."""
    for tag in SKIP_TAGS:
        raw = re.sub(
            rf"(?is)<{tag}\b.*?</{tag}>", lambda m: " " * len(m.group(0)), raw
        )
    raw = re.sub(
        r"(?s)\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}",
        lambda m: " " * len(m.group(0)),
        raw,
    )
    return re.sub(r"(?s)<!--.*?-->", lambda m: " " * len(m.group(0)), raw)


def load_after_extends(text: str) -> str:
    """Insère ``{% load i18n %}`` au bon endroit du template."""
    if not re.search(r"\{%\s*(?:translate|blocktranslate|blocktrans)\b", text):
        return text
    if re.search(r"\{%\s*load\b[^%]*\bi18n\b[^%]*%\}", text):
        return text

    load_match = re.search(r"\{%\s*load\b([^%]*)%\}", text)
    if load_match:
        tags = [t for t in load_match.group(1).split() if t != "i18n"]
        replacement = "{% load " + " ".join(tags + ["i18n"]) + " %}"
        return text[: load_match.start()] + replacement + text[load_match.end() :]

    extends_match = re.search(r"\{%\s*extends\b[^%]*%\}", text)
    if extends_match:
        insert_at = extends_match.end()
        return text[:insert_at] + "\n{% load i18n %}" + text[insert_at:]

    return "{% load i18n %}\n" + text


def mark_template(path: Path) -> tuple[str, list[str]]:
    """Retourne le template marqué et la liste des chaînes extraites."""
    raw = path.read_text(encoding="utf-8")
    masked = strip_ignored(raw)

    spans = find_text_spans(masked) + find_attr_spans(masked)
    spans = [s for s in sorted(spans, key=lambda s: s[0]) if s[0] != s[1]]
    if not spans:
        return raw, []

    result = raw
    for start, end, replacement in sorted(spans, key=lambda s: s[0], reverse=True):
        result = result[:start] + replacement + result[end:]

    return load_after_extends(result), [_quote(s[2]) for s in spans]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--only", default="")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    catalog: dict[str, list[str]] = {}
    total = 0

    paths = sorted(TEMPLATES_DIR.rglob("*.html"))
    if args.only:
        paths = [p for p in paths if args.only in p.name]

    for path in paths:
        marked, strings = mark_template(path)
        if not strings:
            continue
        if args.apply:
            path.write_text(marked, encoding="utf-8")

        key = str(path.relative_to(BASE_DIR)).replace("\\", "/")
        catalog[key] = strings
        total += len(strings)
        print(f"  {len(strings):4}  {path.name}")

    print(f"\n{total} chaînes dans {len(catalog)} templates")

    if args.out:
        Path(args.out).write_text(
            json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"catalogue écrit dans {args.out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
