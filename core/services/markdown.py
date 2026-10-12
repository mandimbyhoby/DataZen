"""Conversion Markdown → HTML pour l'affichage des rapports (DataZen).

Ce module convertit le rapport de nettoyage (Markdown) en HTML afin de
pouvoir le consulter directement dans le navigateur, sans téléchargement.

Il ne dépend d'aucune bibliothèque externe : il gère uniquement le
sous-ensemble Markdown réellement produit par :mod:`core.services.report`
(titres, tableaux, listes, gras, code inline, séparateurs). Le contenu est
échappé avant conversion pour éviter toute injection HTML.
"""

import html
import re

# Titres : ``#`` à ``######`` en début de ligne.
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
# Séparateur de tableau Markdown : ``| --- | --- |``.
_TABLE_SEP_RE = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?$")
# Élément de liste : ``- texte`` ou ``* texte``.
_LIST_RE = re.compile(r"^[-*]\s+(.*)$")
# Gras ``**texte**`` et code inline `` `texte` ``.
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_CODE_RE = re.compile(r"`([^`]+)`")


def _inline(text):
    """Applique les transformations inline (gras, code) sur du texte échappé."""
    text = _BOLD_RE.sub(r"<strong>\1</strong>", text)
    text = _CODE_RE.sub(r"<code>\1</code>", text)
    return text


def _split_row(line):
    """Découpe une ligne de tableau Markdown en cellules."""
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [cell.strip() for cell in line.split("|")]


def markdown_to_html(text):
    """Convertit un texte Markdown en HTML (sous-ensemble du rapport)."""
    if not text:
        return ""

    lines = text.splitlines()
    out = []
    i = 0
    n = len(lines)

    while i < n:
        raw = lines[i]
        line = raw.rstrip()
        stripped = line.strip()

        # Ligne vide : sépare les blocs.
        if not stripped:
            i += 1
            continue

        # Titre.
        heading = _HEADING_RE.match(stripped)
        if heading:
            level = len(heading.group(1))
            content = _inline(html.escape(heading.group(2).strip()))
            out.append(f"<h{level}>{content}</h{level}>")
            i += 1
            continue

        # Séparateur horizontal.
        if stripped in {"---", "***", "___"}:
            out.append("<hr>")
            i += 1
            continue

        # Tableau : une ligne ``| ... |`` suivie d'un séparateur.
        if stripped.startswith("|") and i + 1 < n and _TABLE_SEP_RE.match(
            lines[i + 1].strip()
        ):
            header = _split_row(stripped)
            i += 2  # saute l'entête et le séparateur
            body = []
            while i < n and lines[i].strip().startswith("|"):
                body.append(_split_row(lines[i].strip()))
                i += 1
            out.append('<div class="table-responsive">')
            out.append('<table class="table table-sm table-striped align-middle">')
            out.append("<thead><tr>")
            for cell in header:
                out.append(f"<th>{_inline(html.escape(cell))}</th>")
            out.append("</tr></thead><tbody>")
            for row in body:
                out.append("<tr>")
                for cell in row:
                    out.append(f"<td>{_inline(html.escape(cell))}</td>")
                out.append("</tr>")
            out.append("</tbody></table></div>")
            continue

        # Liste à puces.
        if _LIST_RE.match(stripped):
            items = []
            while i < n and _LIST_RE.match(lines[i].strip()):
                item = _LIST_RE.match(lines[i].strip()).group(1)
                items.append(f"<li>{_inline(html.escape(item))}</li>")
                i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
            continue

        # Paragraphe (regroupe les lignes consécutives).
        paragraph = [stripped]
        i += 1
        while i < n:
            nxt = lines[i].strip()
            if (
                not nxt
                or _HEADING_RE.match(nxt)
                or _LIST_RE.match(nxt)
                or nxt.startswith("|")
                or nxt in {"---", "***", "___"}
            ):
                break
            paragraph.append(nxt)
            i += 1
        content = _inline(html.escape(" ".join(paragraph)))
        out.append(f"<p>{content}</p>")

    return "\n".join(out)