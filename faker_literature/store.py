"""TinyDB-backed storage for the literature catalogue.

Books are stored as flat records whose text fields are either plain strings
or ``{locale: value}`` dictionaries.  Every record carries a ``source`` field
so that books imported from external datasets can live next to the bundled
catalogue and be replaced independently of it.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import threading
from collections.abc import Callable, Hashable, Iterable, Mapping
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, TypeVar

from tinydb import Query, TinyDB
from tinydb.queries import QueryLike
from tinydb.storages import MemoryStorage
from tinydb.table import Table

from faker_literature._storage import AtomicJSONStorage, FileLock
from faker_literature.matching import YEAR_TOLERANCE, DuplicateIndex
from faker_literature.vocabulary import GenreVocabulary

# A raw record: text fields are strings or {locale: value} mappings
Record = dict[str, Any]
# A record resolved for one locale, as returned by the provider
LocalizedBook = dict[str, Any]
PathLike = str | os.PathLike[str]
T = TypeVar("T")

LOCALES = ("fr_FR", "en_US")
SCHEMA_VERSION = 1
BUILTIN_SOURCE = "builtin"
BUILTIN_DATA = Path(__file__).parent / "DATAS" / "literature.json"

MAX_TEXT_LENGTH = 300
MAX_GENRES = 20
MIN_YEAR, MAX_YEAR = -3000, 2100
MAX_PAGES = 100000

# Fields of the schema; other ("extra") fields such as ``isbn`` are kept as is
SCHEMA_FIELDS = {
    "writer", "nationality", "title", "title_untranslated", "genre", "year", "pages", "pages_estimated", "publisher",
    "publisher_estimated", "popularity", "writer_born", "writer_died", "awards", "source", "wikidata_id",
}
MAX_EXTRA_FIELDS = 20
MAX_POPULARITY = 10**9
EXTRA_FIELD_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")
WIKIDATA_ID = re.compile(r"Q[1-9][0-9]{0,11}")


def default_db_path() -> Path:
    """Return a per-user cache location for a persistent catalogue."""
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "faker-literature" / "literature_db.json"


def load_vocabulary(path: PathLike = BUILTIN_DATA) -> GenreVocabulary:
    """Return the :class:`GenreVocabulary` of the bundled JSON."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return GenreVocabulary(data["genres"])


def load_builtin_books(path: PathLike = BUILTIN_DATA) -> tuple[list[Record], str]:
    """Read the bundled JSON and return ``(flat records, sha256 of the file)``.

    Books refer to genres by id: records get the ``{locale: [labels]}`` of
    the vocabulary instead.
    """
    raw = Path(path).read_bytes()
    data = json.loads(raw.decode("utf-8"))
    vocabulary = GenreVocabulary(data["genres"])
    awards = data.get("awards", {})
    books = []
    for author in data["authors"]:
        for book in author["books"]:
            life = {f"writer_{key}": author[key] for key in ("born", "died") if key in author}
            books.append({
                "writer": author["name"],
                "nationality": author["nationality"],
                **life,
                **book,
                "genre": vocabulary.resolve(book["genre"]),
                **({"awards": {locale: [awards[award][locale] for award in book["awards"]] for locale in LOCALES}}
                   if book.get("awards") else {}),
                "source": BUILTIN_SOURCE,
            })
    return books, hashlib.sha256(raw).hexdigest()


# Validation

def _check_string(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field}: expected a non-empty string, got {value!r}")
    if len(value) > MAX_TEXT_LENGTH:
        raise ValueError(f"{field}: longer than {MAX_TEXT_LENGTH} characters")


def _check_localized(value: object, field: str, check: Callable[[Any, str], None], allow_plain: bool = False) -> None:
    if allow_plain and not isinstance(value, dict):
        check(value, field)
        return
    if not isinstance(value, dict):
        raise ValueError(f"{field}: expected a {{locale: value}} mapping")
    missing = set(LOCALES) - set(value)
    if missing:
        raise ValueError(f"{field}: missing locales {sorted(missing)}")
    for locale in LOCALES:
        check(value[locale], f"{field}[{locale}]")


def _check_genres(value: object, field: str) -> None:
    if not isinstance(value, (list, tuple)) or not value or len(value) > MAX_GENRES:
        raise ValueError(f"{field}: expected 1 to {MAX_GENRES} genres")
    for index, genre in enumerate(value):
        _check_string(genre, f"{field}[{index}]")


def _check_awards(value: object, field: str) -> None:
    if not isinstance(value, (list, tuple)) or len(value) > MAX_GENRES:
        raise ValueError(f"{field}: expected 0 to {MAX_GENRES} awards")
    for index, award in enumerate(value):
        _check_string(award, f"{field}[{index}]")


def _check_pages(value: object, field: str) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= MAX_PAGES:
        raise ValueError(f"{field}: expected a page count between 1 and {MAX_PAGES}")


def _check_optional_string(value: object, field: str) -> None:
    if value is not None:
        _check_string(value, field)


def _check_extra_fields(book: Mapping[Any, Any]) -> None:
    extras = [name for name in book if name not in SCHEMA_FIELDS]
    if len(extras) > MAX_EXTRA_FIELDS:
        raise ValueError(f"book: more than {MAX_EXTRA_FIELDS} extra fields")
    for name in extras:
        if not isinstance(name, str) or not EXTRA_FIELD_NAME.fullmatch(name):
            raise ValueError(f"{name!r}: extra field names are identifiers of at most 64 characters")
        value = book[name]
        if isinstance(value, str):
            if len(value) > MAX_TEXT_LENGTH:
                raise ValueError(f"{name}: longer than {MAX_TEXT_LENGTH} characters")
        elif isinstance(value, float):
            if not math.isfinite(value):
                raise ValueError(f"{name}: expected a finite number")
        elif value is not None and not isinstance(value, (bool, int)):
            raise ValueError(f"{name}: extra fields hold a string, a number, a boolean or None")


def validate_book(book: object) -> None:
    """Raise ``ValueError`` if ``book`` does not follow the catalogue schema."""
    if not isinstance(book, dict):
        raise ValueError("book: expected a mapping")
    _check_localized(book.get("writer"), "writer", _check_string, allow_plain=True)
    _check_localized(book.get("nationality"), "nationality", _check_string)
    _check_localized(book.get("title"), "title", _check_string)
    # True when the work was never translated into French: its French title is the original one
    if "title_untranslated" in book:
        if not isinstance(book["title_untranslated"], bool):
            raise ValueError("title_untranslated: expected true or false")
        if book["title_untranslated"] and book["title"]["fr_FR"] != book["title"]["en_US"]:
            raise ValueError("title_untranslated: the French title differs from the English one")
    _check_localized(book.get("genre"), "genre", _check_genres)
    year = book.get("year")
    if isinstance(year, bool) or not isinstance(year, int) or not MIN_YEAR <= year <= MAX_YEAR:
        raise ValueError(f"year: expected an integer between {MIN_YEAR} and {MAX_YEAR}")
    if book.get("pages") is not None:
        _check_localized(book["pages"], "pages", _check_pages)
    if book.get("publisher") is not None:
        _check_localized(book["publisher"], "publisher", _check_optional_string)
    # Literary awards received by the work, localized like the genres
    if book.get("awards") is not None:
        _check_localized(book["awards"], "awards", _check_awards)
    # True when the page counts estimate the usual length of the work, and when the publishers
    # are plausible but were not checked against a source: neither describes a known edition
    for field in ("pages", "publisher"):
        flag = f"{field}_estimated"
        if flag in book:
            if not isinstance(book[flag], bool):
                raise ValueError(f"{flag}: expected true or false")
            if book[flag] and not book.get(field):
                raise ValueError(f"{flag}: no {'page count' if field == 'pages' else field} to qualify")
    # How well known the work is: its number of Wikipedia articles for the bundled books
    popularity = book.get("popularity")
    if popularity is not None and (isinstance(popularity, bool) or not isinstance(popularity, int)
                                   or not 0 < popularity <= MAX_POPULARITY):
        raise ValueError(f"popularity: expected an integer between 1 and {MAX_POPULARITY}")
    # Years of birth and death of the (single) author
    for field in ("writer_born", "writer_died"):
        value = book.get(field)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int)
                                  or not MIN_YEAR <= value <= MAX_YEAR):
            raise ValueError(f"{field}: expected a year between {MIN_YEAR} and {MAX_YEAR}")
    if book.get("writer_born") is not None and book.get("writer_died") is not None \
            and book["writer_died"] < book["writer_born"]:
        raise ValueError("writer_died: before writer_born")
    _check_string(book.get("source"), "source")
    wikidata_id = book.get("wikidata_id")
    if "wikidata_id" in book and not (isinstance(wikidata_id, str) and WIKIDATA_ID.fullmatch(wikidata_id)):
        raise ValueError(f"wikidata_id: expected an id such as Q1234, got {book['wikidata_id']!r}")
    _check_extra_fields(book)


# Localization

def pick(value: Any, locale: str) -> Any:
    """Return ``value[locale]`` for localized mappings, ``value`` itself otherwise."""
    return value.get(locale) if isinstance(value, dict) else value


def localize_book(book: Mapping[str, Any], locale: str) -> LocalizedBook:
    """Return a new record with every field resolved for ``locale``.

    ``genre`` is a tuple so that cached records cannot be modified in place.
    """
    return {
        "writer": pick(book["writer"], locale),
        "nationality": pick(book["nationality"], locale),
        "title": pick(book["title"], locale),
        "genre": tuple(pick(book["genre"], locale)),
        "year": book["year"],
        "pages": pick(book.get("pages"), locale),
        "publisher": pick(book.get("publisher"), locale),
        "popularity": book.get("popularity"),
        "writer_born": book.get("writer_born"),
        "writer_died": book.get("writer_died"),
        "awards": tuple(pick(book.get("awards") or {}, locale) or ()),
    }


class BookStore:
    """Catalogue of flat book records kept in TinyDB.

    Without ``path`` the database lives in memory and nothing touches the disk.
    With ``path`` it is persisted there: the bundled books are re-synced
    whenever the bundled JSON changes, while imported books are kept.

    A persistent database may be shared by several processes: every write
    replaces the file atomically, under a lock held through ``<path>.lock``.
    Each store caches its localized books until its own next write, so a
    process does not see the books another one imports until it reopens the
    database.  On opening, every record is validated again, so a database
    edited by hand or damaged is reported instead of producing broken data.
    """

    def __init__(self, path: PathLike | None = None, builtin_path: PathLike = BUILTIN_DATA) -> None:
        self.path = None if path is None else Path(path)
        if self.path is None:
            self._db = TinyDB(storage=MemoryStorage)
            self._lock: AbstractContextManager[Any] = threading.RLock()
        else:
            self._db = TinyDB(
                str(self.path), storage=AtomicJSONStorage, create_dirs=True,
                indent=2, ensure_ascii=False,
            )
            self._lock = FileLock(self.path.with_name(self.path.name + ".lock"))
        self._localized: dict[str, tuple[LocalizedBook, ...]] = {}
        self._derived: dict[tuple[str, Hashable], Any] = {}
        # Imported books dropped by the last re-sync of the bundled catalogue
        self.removed_duplicates = 0
        with self._lock:
            self._sync_builtin(builtin_path)
            if self.path is not None:
                self._validate_stored()

    def _validate_stored(self) -> None:
        for book in self.books.all():
            try:
                validate_book(book)
            except ValueError as error:
                raise ValueError(
                    f"{self.path}: invalid record #{book.doc_id} ({error}); "
                    "delete the file and import your datasets again"
                ) from None

    @property
    def books(self) -> Table:
        """Return the TinyDB table holding the book records."""
        return self._db.table("books")

    def _sync_builtin(self, builtin_path: PathLike) -> None:
        books, digest = load_builtin_books(builtin_path)
        expected = {"schema": SCHEMA_VERSION, "builtin_sha256": digest}
        meta = self._db.table("meta")
        if meta.all() == [expected]:
            return
        self.replace_source(BUILTIN_SOURCE, books)
        self.removed_duplicates = self._drop_builtin_duplicates(books)
        meta.truncate()
        meta.insert(expected)

    def _drop_builtin_duplicates(self, builtin: Iterable[Mapping[str, Any]]) -> int:
        """Remove imported books that the new bundled catalogue now contains."""
        index = DuplicateIndex(builtin, year_tolerance=YEAR_TOLERANCE)
        duplicates = [book.doc_id for book in self.books.all()
                      if book["source"] != BUILTIN_SOURCE and book in index]
        if duplicates:
            self.books.remove(doc_ids=duplicates)
            self._invalidate()
        return len(duplicates)

    def replace_source(self, source: str, books: Iterable[Mapping[str, Any]]) -> int:
        """Replace every book of ``source`` with ``books`` and return their count.

        All records are validated before anything is written, so an invalid
        record leaves the store unchanged.
        """
        books = [dict(book, source=source) for book in books]
        for index, book in enumerate(books):
            try:
                validate_book(book)
            except ValueError as error:
                raise ValueError(f"{source} book #{index}: {error}") from None
        with self._lock:
            self.books.remove(Query().source == source)
            self.books.insert_multiple(books)
            self._invalidate()
        return len(books)

    def sources(self) -> dict[str, int]:
        """Return the number of books stored for each source."""
        counts: dict[str, int] = {}
        for book in self.books.all():
            counts[book["source"]] = counts.get(book["source"], 0) + 1
        return counts

    def _invalidate(self) -> None:
        self._localized.clear()
        self._derived.clear()

    def derived(self, locale: str, key: Hashable, build: Callable[[tuple[LocalizedBook, ...]], T]) -> T:
        """Return ``build(self.localized(locale))``, computed once per ``locale`` and ``key``.

        Used for values derived from the whole catalogue, such as the pools
        random values are drawn from; recomputed after the next write.
        """
        if (locale, key) not in self._derived:
            self._derived[locale, key] = build(self.localized(locale))
        value: T = self._derived[locale, key]
        return value

    def localized(self, locale: str) -> tuple[LocalizedBook, ...]:
        """Return every book localized for ``locale`` (cached until the next write)."""
        if locale not in self._localized:
            self._localized[locale] = tuple(
                localize_book(book, locale) for book in self.books.all()
            )
        return self._localized[locale]

    def search(self, condition: QueryLike, locale: str) -> list[LocalizedBook]:
        """Return the books matching a TinyDB ``condition``, localized for ``locale``."""
        return [localize_book(book, locale) for book in self.books.search(condition)]

    def close(self) -> None:
        """Release the underlying storage."""
        self._db.close()
