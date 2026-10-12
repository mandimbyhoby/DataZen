"""Extrait les chaînes traduisibles des templates et du code Python.

GNU gettext n'est pas installé sur cette machine : ce module remplace
``makemessages`` en analysant directement les sources Django.

- Templates : on réutilise le ``templatize()`` de Django — celui-là même
  qu'utilise ``makemessages``. Il garantit une fidélité parfaite sur les
  balises ``{% translate %}`` / ``{% blocktranslate %}`` : espaces fusionnés
  (``trimmed``), variables converties en ``%(nom)s``, contextes et pluriels.
  Sa sortie est écrite dans la syntaxe comprise par xgettext ; elle est relue
  ici par ``scan_literals``.
- Python : appels ``gettext``, ``gettext_lazy``, ``ngettext``, ``pgettext``
  et leurs alias ``_`` / ``_lazy``, repérés via l'AST (donc sans exécuter le
  code et sans faux positifs dans les chaînes de caractères).

Usage :
    python tools/i18n_extract.py --out locale/catalog.json
    python tools/i18n_extract.py --pot locale/django.pot
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
PACKAGE_DIR = BASE_DIR / "core"

GETTEXT_NAMES = {
    "gettext": 1,
    "gettext_lazy": 1,
    "_": 1,
    "_lazy": 1,
    "ngettext": 3,
    "ngettext_lazy": 3,
    "pgettext": 2,
    "pgettext_lazy": 2,
    "npgettext": 4,
    "npgettext_lazy": 4,
}

CALL_RE = re.compile(r"\b(gettext|ngettext|pgettext|npgettext)\s*\(")
LITERAL_RE = re.compile(r"""\s*u?(?P<quote>["'])(?P<body>(?:\\.|(?!\1).)*)(?P=quote)""", re.DOTALL)
SKIP_RE = re.compile(r"[\s,#]*")
UNESCAPE = {"\\n": "\n", "\\t": "\t", '\\"': '"', "\\'": "'", "\\\\": "\\"}


def _unescape(text: str) -> str:
    """Annule l'échappement des littéraux produits par ``templatize``."""
    return re.sub(r"\\.", lambda m: UNESCAPE.get(m.group(0), m.group(0)), text)


def scan_literals(source: str) -> list[tuple[str, str | None, str | None]]:
    """Relit la sortie de ``templatize`` et retourne les messages trouvés.

    Chaque entrée suit le contrat uniforme ``(msgid, msgid_plural, context)`` :
    les deux derniers valent ``None`` quand le pluriel ou le contexte sont
    absents. ``templatize`` produit ``pgettext`` pour ``{% translate …
    context "…" %}`` et ``npgettext`` pour un ``{% blocktranslate … context
    "…" %}`` pluriel.
    """
    messages: list[tuple[str, str | None, str | None]] = []
    for match in CALL_RE.finditer(source):
        kind = match.group(1)
        wanted = {"gettext": 1, "pgettext": 2, "ngettext": 2, "npgettext": 3}[kind]
        args: list[str] = []
        position = match.end()
        while len(args) < wanted:
            position = SKIP_RE.match(source, position).end()
            literal = LITERAL_RE.match(source, position)
            if literal is None:
                break
            args.append(_unescape(literal.group("body")))
            position = literal.end()
        if len(args) != wanted:
            continue
        if kind == "gettext":
            messages.append((args[0], None, None))
        elif kind == "ngettext":
            messages.append((args[0], args[1], None))
        elif kind == "pgettext":
            messages.append((args[1], None, args[0]))
        else:
            messages.append((args[1], args[2], args[0]))
    return messages


def extract_templates() -> dict[str, list[tuple[str, str | None, str | None]]]:
    """Retourne ``{chemin relatif: [messages]}`` pour tous les templates."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "datazen.settings")
    sys.path.insert(0, str(BASE_DIR))
    try:
        import django

        django.setup()
        from django.utils.translation.template import templatize
    except Exception:  # pragma: no cover - dépend d'un environnement Django
        return {}

    found: dict[str, list[tuple[str, ...]]] = {}
    for path in sorted(TEMPLATES_DIR.rglob("*.html")):
        raw = path.read_text(encoding="utf-8")
        try:
            templatized = templatize(raw, str(path))
        except SyntaxError:
            continue
        messages = scan_literals(templatized)
        if messages:
            key = str(path.relative_to(BASE_DIR)).replace("\\", "/")
            found[key] = messages
    return found


def extract_compiled() -> dict[str, list[tuple[str, str | None, str | None]]]:
    """Extrait les messages depuis les templates *compilés* par Django.

    C'est la source de vérité : ``TranslateNode`` et ``BlockTranslateNode``
    sont exactement les nœuds exécutés au rendu, donc les msgid obtenus ici
    sont, par construction, ceux recherchés dans le catalogue.

    À ne pas confondre avec ``extract_templates``, qui interroge l'analyseur
    statique de ``makemessages``. Les deux sont conservés car leurs résultats
    se recoupent : le premier alimente les catalogues, le second sert de
    contrôle de non-régression.
    """
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "datazen.settings")
    sys.path.insert(0, str(BASE_DIR))
    try:
        import django

        django.setup()
        from django.template.loader import get_template
        from django.templatetags.i18n import BlockTranslateNode, TranslateNode
        from django.utils.translation import trim_whitespace
    except Exception:  # pragma: no cover - dépend d'un environnement Django
        return {}

    found: dict[str, list[tuple[str, ...]]] = {}
    for path in sorted(TEMPLATES_DIR.rglob("*.html")):
        key = str(path.relative_to(BASE_DIR)).replace("\\", "/")
        name = key[len("templates/") :] if key.startswith("templates/") else key
        try:
            nodelist = get_template(name).template.nodelist
        except Exception:
            continue

        messages: list[tuple[str, str | None, str | None]] = []
        for node in nodelist.get_nodes_by_type(TranslateNode):
            if node.noop:
                continue
            value = _expression_literal(node.filter_expression)
            if not isinstance(value, str):
                continue
            messages.append((value, None, _context_literal(node.message_context)))

        for node in nodelist.get_nodes_by_type(BlockTranslateNode):
            singular, _ = node.render_token_list(node.singular)
            if node.trimmed:
                singular = trim_whitespace(singular)
            plural = None
            if node.plural and node.countervar and node.counter:
                plural, _ = node.render_token_list(node.plural)
                if node.trimmed:
                    plural = trim_whitespace(plural)
            messages.append((singular, plural, _context_literal(node.message_context)))

        if messages:
            found[key] = messages

    return found


def _expression_literal(expression) -> str | None:
    """Littéral d'une ``FilterExpression``, ou ``None`` si elle est dynamique.

    Deux formes coexistent : ``TranslateNode.__init__`` remplace ``.var`` par
    une ``Variable`` dès que la chaîne est un littéral (elle expose alors
    ``.literal``), tandis qu'une expression déjà compilée depuis un token
    entre guillemets garde le ``str`` dans ``.var``. On retombe enfin sur le
    token brut, débarrassé de ses guillemets, pour les autres cas.
    """
    if expression is None:
        return None
    var = getattr(expression, "var", None)
    if isinstance(var, str):
        return var
    literal = getattr(var, "literal", None)
    if isinstance(literal, str):
        return literal
    token = getattr(expression, "token", None)
    if isinstance(token, str) and len(token) > 1 and token[0] == token[-1] and token[0] in "\"'":
        return _unescape(token[1:-1])
    return None


def _context_literal(expression) -> str | None:
    """Contexte de traduction d'un nœud, ou ``None`` s'il est absent/dynamique.

    ``TranslateNode.message_context`` est une ``FilterExpression`` (et non une
    chaîne) : il faut donc en extraire le littéral, comme pour le msgid.
    """
    return _expression_literal(expression)


def _literal(node: ast.AST) -> str | None:
    """Valeur d'un littéral chaîne, ou ``None`` si ce n'en est pas un."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def extract_python() -> dict[str, list[tuple[str, str | None, str | None]]]:
    """Retourne ``{chemin relatif: [messages]}`` pour le code Python."""
    found: dict[str, list[tuple[str, ...]]] = {}

    for path in sorted(PACKAGE_DIR.rglob("*.py")):
        if "migrations" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue

        messages: list[tuple[str, ...]] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = (
                func.id
                if isinstance(func, ast.Name)
                else func.attr
                if isinstance(func, ast.Attribute)
                else None
            )
            if name not in GETTEXT_NAMES or not node.args:
                continue

            first = _literal(node.args[0])
            if first is None:
                continue

            if name in ("pgettext", "pgettext_lazy", "npgettext", "npgettext_lazy"):
                if len(node.args) < 2:
                    continue
                singular = _literal(node.args[1])
                if singular is None:
                    continue
                plural = None
                if name.startswith("n"):
                    if len(node.args) < 3:
                        continue
                    plural = _literal(node.args[2])
                    if plural is None:
                        continue
                messages.append((singular, plural, first))
            elif name.startswith("ngettext"):
                if len(node.args) < 2:
                    continue
                second = _literal(node.args[1])
                if second is None:
                    continue
                messages.append((first, second, None))
            else:
                messages.append((first, None, None))

        if messages:
            key = str(path.relative_to(BASE_DIR)).replace("\\", "/")
            found[key] = messages

    return found


def collect() -> list[str]:
    """Liste triée de toutes les chaînes uniques à traduire.

    Les templates compilés font foi ; l'analyse statique et le code Python
    complètent l'inventaire.
    """
    found: set[str] = set()
    for group in (extract_compiled(), extract_templates(), extract_python()):
        for messages in group.values():
            for msgid, plural, _context in messages:
                found.add(msgid)
                if plural:
                    found.add(plural)
    return sorted(found)


def po_escape(text: str) -> str:
    """Échappe une chaîne pour un fichier ``.po``."""
    out = text.replace("\\", "\\\\").replace('"', '\\"')
    return out.replace("\n", "\\n").replace("\t", "\\t").replace("\r", "")


def write_pot(entries: list[str], destination: Path) -> None:
    """Écrit un catalogue source au format ``.pot``."""
    lines = [
        'msgid ""',
        'msgstr ""',
        '"Content-Type: text/plain; charset=UTF-8\\n"',
        '"Content-Transfer-Encoding: 8bit\\n"',
        "",
    ]
    for msgid in entries:
        lines.append(f'msgid "{po_escape(msgid)}"')
        lines.append('msgstr ""')
        lines.append("")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="")
    parser.add_argument("--pot", default="")
    args = parser.parse_args()

    templates = extract_compiled()
    static = extract_templates()
    python = extract_python()
    ordered = sorted(
        {
            msgid
            for group in (templates, static, python)
            for messages in group.values()
            for msgid, _plural, _context in messages
        }
    )

    print(f"{len(templates)} templates compilés, {len(static)} analysés, {len(python)} fichiers .py")
    print(f"{len(ordered)} chaînes uniques")

    if args.out:
        destination = Path(args.out)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(
                {"compiled": templates, "static": static, "python": python},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"inventaire écrit dans {args.out}")

    if args.pot:
        write_pot(ordered, Path(args.pot))
        print(f"catalogue source écrit dans {args.pot}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
