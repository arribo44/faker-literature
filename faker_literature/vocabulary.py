"""Controlled vocabulary of literary genres.

``literature.json`` lists every genre once, under ``genres``, with one label
per locale and optional aliases; books refer to genres by id.  A genre thus has
a single translation, and labels coming from Wikidata or typed in the editor
("crime fiction", "police") are mapped onto the existing genre ("crime").
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from typing import Any

from faker_literature.matching import name_key

LOCALES = ("fr_FR", "en_US")
# {id: {"fr_FR": label, "en_US": label, "aliases": {locale: [label, ...]}}}
Genres = dict[str, dict[str, Any]]
GENRE_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def slugify(text: str) -> str:
    """Return an id such as ``children-s-literature`` for ``children's literature``."""
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


class GenreVocabulary:
    """Genres by id, with lookups by label or alias in either locale.

    ``genres`` is the ``{id: {"fr_FR": ..., "en_US": ..., "aliases": {...}}}``
    mapping stored in ``literature.json``; :meth:`add` modifies it in place.
    """

    def __init__(self, genres: Genres) -> None:
        self.genres = genres
        self._index: dict[str, dict[str, str]] = {locale: {} for locale in LOCALES}
        for genre_id, genre in genres.items():
            self._check(genre_id, genre)
            self._register(genre_id, genre)

    @staticmethod
    def _labels(genre: dict[str, Any], locale: str) -> list[Any]:
        return [genre[locale], *genre.get("aliases", {}).get(locale, ())]

    def _check(self, genre_id: object, genre: object) -> None:
        if not isinstance(genre_id, str) or not GENRE_ID.fullmatch(genre_id):
            raise ValueError(f"genre id {genre_id!r}: expected lower-case words joined by '-'")
        if not isinstance(genre, dict):
            raise ValueError(f"genre {genre_id}: expected a mapping")
        for locale in LOCALES:
            labels = self._labels(genre, locale)
            if not all(isinstance(label, str) and label.strip() for label in labels):
                raise ValueError(f"genre {genre_id}[{locale}]: expected non-empty labels")
            for label in labels:
                owner = self._index[locale].get(name_key(label))
                if owner not in (None, genre_id):
                    raise ValueError(f"genre {genre_id}[{locale}]: label {label!r} already used by {owner}")

    def _register(self, genre_id: str, genre: dict[str, Any]) -> None:
        for locale in LOCALES:
            for label in self._labels(genre, locale):
                self._index[locale][name_key(label)] = genre_id

    def __contains__(self, genre_id: object) -> bool:
        return genre_id in self.genres

    def match(self, label: str | None, locale: str) -> str | None:
        """Return the id of the genre called ``label``, or ``None``.

        The label is looked up in ``locale`` first, then in the other locale
        (some labels such as "fantasy" or "thriller" are used in both).
        """
        key = name_key(label or "")
        if not key:
            return None
        for lookup in (locale, *(other for other in LOCALES if other != locale)):
            if key in self._index[lookup]:
                return self._index[lookup][key]
        return None

    def labels(self, locale: str) -> list[str]:
        """Return the label of every genre in ``locale``, sorted."""
        return sorted((genre[locale] for genre in self.genres.values()), key=str.casefold)

    def resolve(self, genre_ids: Iterable[str]) -> dict[str, list[str]]:
        """Return the ``{locale: [labels]}`` of a list of genre ids."""
        genre_ids = list(genre_ids)
        unknown = [genre_id for genre_id in genre_ids if genre_id not in self.genres]
        if unknown:
            raise ValueError(f"genre: unknown genre ids {unknown}")
        return {locale: [self.genres[genre_id][locale] for genre_id in genre_ids] for locale in LOCALES}

    def add(self, fr_label: str, en_label: str) -> str:
        """Add the genre ``fr_label`` / ``en_label`` and return its new id."""
        genre = {"fr_FR": fr_label.strip(), "en_US": en_label.strip()}
        base = slugify(genre["en_US"]) or slugify(genre["fr_FR"])
        if not base:
            raise ValueError(f"genre: cannot build an id for {en_label!r}")
        genre_id, suffix = base, 2
        while genre_id in self.genres:
            genre_id, suffix = f"{base}-{suffix}", suffix + 1
        self._check(genre_id, genre)
        self.genres[genre_id] = genre
        self._register(genre_id, genre)
        return genre_id
