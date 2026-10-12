"""Filtres de template personnalisés pour DataZen."""
from django import template

from ..services.cleaning import is_unknown

register = template.Library()


@register.filter(name="is_unknown")
def is_unknown_filter(value):
    """Indique si une valeur est le marqueur « Inconnu » (insensible à la casse).

    Permet au template de mettre en évidence ``Inconnu``, ``INCONNU``,
    ``inconnu``… de façon homogène, y compris dans l'aperçu des données
    brutes (avant nettoyage).
    """
    return is_unknown(value)