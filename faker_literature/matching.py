"""Name and title normalization, and detection of works already catalogued.

The editor, the Wikidata importer and the store share these rules so that a
work is recognized the same way whichever path it comes from.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from typing import Any

# Years may differ by a little between sources (writing, first edition...)
YEAR_TOLERANCE = 2

# An article is a whole word ("The Iliad", "L'Iliade"), never the start of one ("Anna", "Theogony")
LEADING_ARTICLE = re.compile(r"^(?:(?:le|la|les|un|une|the|a|an)\s+|l['’]\s*)(?=\S)", re.IGNORECASE)


def sort_key(value: str | Mapping[str, str]) -> str:
    """Accent-insensitive sort key, so that "Émile Zola" sorts among the E.

    Localized ``{locale: name}`` mappings sort by their French name.
    """
    name = value.get("fr_FR", "") if isinstance(value, Mapping) else value
    return "".join(c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c)).casefold()


def name_key(name: str | Mapping[str, str]) -> str:
    """Compare names regardless of accents, case, spaces and punctuation ("J. D." == "J.D.")."""
    return "".join(c for c in sort_key(name) if c.isalnum())


def title_key(title: str) -> str:
    """Compare titles regardless of a leading article ("L'Iliade" == "Iliade")."""
    return name_key(LEADING_ARTICLE.sub("", title.strip()))


def names(value: str | Mapping[str, str]) -> set[str]:
    """Return every spelling of a plain or localized name."""
    return set(value.values()) if isinstance(value, Mapping) else {value}


def _titles(book: Mapping[str, Any]) -> set[str]:
    return {key for key in (title_key(title) for title in names(book["title"]) if title) if key}


class DuplicateIndex:
    """Find, among ``books``, the one a new record describes.

    Two records are the same work when they share a Wikidata id, or else a
    title in any locale (ignoring case, accents, punctuation and a leading
    article).  With ``year_tolerance``, matching titles must also have years
    at most that far apart: "The Lost World" of 1912 is not the one of 1995.
    """

    def __init__(self, books: Iterable[Mapping[str, Any]], year_tolerance: int | None = None) -> None:
        self.year_tolerance = year_tolerance
        self._by_id: dict[str, Mapping[str, Any]] = {}
        self._by_title: dict[str, list[Mapping[str, Any]]] = {}
        for book in books:
            if book.get("wikidata_id"):
                self._by_id.setdefault(book["wikidata_id"], book)
            for key in _titles(book):
                self._by_title.setdefault(key, []).append(book)

    def find(self, record: Mapping[str, Any]) -> Mapping[str, Any] | None:
        """Return the known book matching ``record``, or ``None``."""
        if record.get("wikidata_id") in self._by_id:
            return self._by_id[record["wikidata_id"]]
        for key in _titles(record):
            for book in self._by_title.get(key, ()):
                if self.year_tolerance is None or abs(book["year"] - record["year"]) <= self.year_tolerance:
                    return book
        return None

    def __contains__(self, record: object) -> bool:
        return isinstance(record, Mapping) and self.find(record) is not None
