"""Controlled vocabularies of literary genres and publishers.

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
# Letters that Unicode does not decompose into a base letter and an accent ("Yapı" -> "yapi")
UNDECOMPOSABLE = str.maketrans({"ı": "i", "ø": "o", "Ø": "O", "ł": "l", "Ł": "L", "đ": "d", "Đ": "D",
                                "ß": "ss", "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE"})


def slugify(text: str) -> str:
    """Return an id such as ``children-s-literature`` for ``children's literature``."""
    text = "".join(c for c in unicodedata.normalize("NFKD", text.translate(UNDECOMPOSABLE))
                   if not unicodedata.combining(c))
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


# {id: {"name": name or {locale: name}, "aliases": [...], "country": "FR", "wikidata_id": "Q..."}}
Publishers = dict[str, dict[str, Any]]
PUBLISHER_FIELDS = {"name", "aliases", "country", "wikidata_id"}
COUNTRY_CODE = re.compile(r"[A-Z]{2}")
WIKIDATA_ID = re.compile(r"Q[1-9][0-9]{0,11}")


class PublisherVocabulary:
    """Publishers by id, with lookups by name or alias.

    ``publishers`` is the ``{id: {"name": ..., "aliases": [...], "country":
    ..., "wikidata_id": ...}}`` mapping stored in ``literature.json``; books
    refer to publishers by id, one per locale.  A name is usually the same in
    both locales ("Gallimard"), or a ``{locale: name}`` mapping when the
    publisher is known under a translated name ("Le Messager russe" / "The
    Russian Messenger").  ``country`` is an ISO 3166-1 alpha-2 code.  Names
    and aliases are compared regardless of case, accents and punctuation
    ("Le Livre de poche" == "Le Livre de Poche"), and belong to a single
    publisher; other spellings ("Chapman and Hall") are listed as aliases.  :meth:`add` modifies the mapping in place.
    """

    def __init__(self, publishers: Publishers) -> None:
        self.publishers = publishers
        self._index: dict[str, str] = {}
        for publisher_id, publisher in publishers.items():
            self._check(publisher_id, publisher)
            self._register(publisher_id, publisher)

    @staticmethod
    def _labels(publisher: dict[str, Any]) -> list[Any]:
        name = publisher["name"]
        names = list(name.values()) if isinstance(name, dict) else [name]
        return [*names, *publisher.get("aliases", ())]

    def _check(self, publisher_id: object, publisher: object) -> None:
        if not isinstance(publisher_id, str) or not GENRE_ID.fullmatch(publisher_id):
            raise ValueError(f"publisher id {publisher_id!r}: expected lower-case words joined by '-'")
        if not isinstance(publisher, dict):
            raise ValueError(f"publisher {publisher_id}: expected a mapping")
        unknown = set(publisher) - PUBLISHER_FIELDS
        if unknown:
            raise ValueError(f"publisher {publisher_id}: unknown fields {sorted(unknown)}")
        name = publisher.get("name")
        if isinstance(name, dict) and set(name) != set(LOCALES):
            raise ValueError(f"publisher {publisher_id}: a localized name needs exactly the locales {list(LOCALES)}")
        if not isinstance(publisher.get("aliases", []), list):
            raise ValueError(f"publisher {publisher_id}: aliases must be a list")
        labels = self._labels(publisher) if name is not None else [None]
        if not all(isinstance(label, str) and label.strip() == label and label for label in labels):
            raise ValueError(f"publisher {publisher_id}: expected non-empty names without surrounding spaces")
        country = publisher.get("country")
        if country is not None and not (isinstance(country, str) and COUNTRY_CODE.fullmatch(country)):
            raise ValueError(f"publisher {publisher_id}: country {country!r} is not an ISO 3166-1 alpha-2 code")
        wikidata_id = publisher.get("wikidata_id")
        if wikidata_id is not None and not (isinstance(wikidata_id, str) and WIKIDATA_ID.fullmatch(wikidata_id)):
            raise ValueError(f"publisher {publisher_id}: invalid wikidata_id {wikidata_id!r}")
        for label in labels:
            owner = self._index.get(name_key(str(label)))
            if owner not in (None, publisher_id):
                raise ValueError(f"publisher {publisher_id}: name {label!r} already used by {owner}")

    def _register(self, publisher_id: str, publisher: dict[str, Any]) -> None:
        for label in self._labels(publisher):
            self._index[name_key(label)] = publisher_id

    def __contains__(self, publisher_id: object) -> bool:
        return publisher_id in self.publishers

    def match(self, label: str | None) -> str | None:
        """Return the id of the publisher called ``label`` (name or alias), or ``None``."""
        key = name_key(label or "")
        return self._index.get(key) if key else None

    def name(self, publisher_id: str, locale: str) -> str:
        """Return the name of the publisher ``publisher_id`` in ``locale``."""
        if publisher_id not in self.publishers:
            raise ValueError(f"publisher: unknown publisher id {publisher_id!r}")
        name = self.publishers[publisher_id]["name"]
        return str(name[locale] if isinstance(name, dict) else name)

    def canonical(self, label: str | None, locale: str) -> str | None:
        """Return the catalogue name of the publisher called ``label``, or ``label`` itself when unknown."""
        publisher_id = self.match(label)
        return self.name(publisher_id, locale) if publisher_id else label

    def names(self, locale: str) -> list[str]:
        """Return the name of every publisher in ``locale``, sorted."""
        return sorted((self.name(publisher_id, locale) for publisher_id in self.publishers), key=str.casefold)

    def resolve(self, publisher_ids: dict[str, str | None] | None) -> dict[str, str | None] | None:
        """Return the ``{locale: name}`` of a book's ``{locale: publisher id}`` (``None`` stays ``None``)."""
        if publisher_ids is None:
            return None
        names: dict[str, str | None] = {}
        for locale in LOCALES:
            publisher_id = publisher_ids.get(locale)
            names[locale] = self.name(publisher_id, locale) if publisher_id else None
        return names

    def add(self, name: str, country: str | None = None, wikidata_id: str | None = None) -> str:
        """Add the publisher ``name`` and return its new id."""
        publisher: dict[str, Any] = {"name": name.strip()}
        if country:
            publisher["country"] = country
        if wikidata_id:
            publisher["wikidata_id"] = wikidata_id
        base = slugify(publisher["name"])
        if not base:
            raise ValueError(f"publisher: cannot build an id for {name!r}")
        publisher_id, suffix = base, 2
        while publisher_id in self.publishers:
            publisher_id, suffix = f"{base}-{suffix}", suffix + 1
        self._check(publisher_id, publisher)
        self.publishers[publisher_id] = publisher
        self._register(publisher_id, publisher)
        return publisher_id

    def ensure(self, name: str) -> tuple[str, bool]:
        """Return ``(id, created)`` of the publisher called ``name``, adding it when unknown."""
        publisher_id = self.match(name)
        return (publisher_id, False) if publisher_id else (self.add(name), True)
