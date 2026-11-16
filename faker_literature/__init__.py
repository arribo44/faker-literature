"""Faker provider for generating literature-related data."""

from __future__ import annotations

import copy
from collections.abc import Callable, Hashable
from typing import Any, TypeVar

from faker.providers import BaseProvider
from tinydb import Query
from tinydb.queries import QueryLike
from tinydb.table import Table

from faker_literature.matching import name_key
from faker_literature.store import LOCALES, BookStore, LocalizedBook, PathLike, Record, default_db_path, pick

__version__ = "0.3.0"
__all__ = ["LiteratureProvider", "BookStore", "default_db_path", "__version__"]

T = TypeVar("T")

# Books written together list their authors in one string: "Author A, Author B"
CO_AUTHOR_SEPARATOR = ", "


def _authors(writer: str) -> list[str]:
    """Split the ``writer`` of a co-written book into its authors."""
    return writer.split(CO_AUTHOR_SEPARATOR)


def _has_genre(book: LocalizedBook, genre: str | None) -> bool:
    return genre is None or genre.casefold() in (g.casefold() for g in book["genre"])


class LiteratureProvider(BaseProvider):
    """Generate authors, books, genres and publishing details in two locales.

    Text filters (nationality, genre, author name) ignore case.  Random values
    are drawn from pools computed once per locale and cached until the
    catalogue changes.
    """

    SUPPORTED_LOCALES = LOCALES

    LOCALE_DEFAULT_NATIONALITY = {
        "fr_FR": "français",
        "en_US": "American",
    }

    # writer(nationality=ANY_NATIONALITY): writers of every nationality
    ANY_NATIONALITY = "*"

    # Catalogue shared by every provider instance (lazy initialization)
    _store: BookStore | None = None

    @classmethod
    def use_database(cls, path: PathLike | None = None) -> BookStore:
        """Point every provider at the catalogue persisted at ``path``.

        The file is created if needed, typically at :func:`default_db_path`,
        and keeps books imported from external datasets.  ``None`` switches
        back to the bundled catalogue held in memory.
        """
        if cls._store is not None:
            cls._store.close()
        cls._store = BookStore(path)
        return cls._store

    @classmethod
    def _get_store(cls) -> BookStore:
        if cls._store is None:
            cls._store = BookStore()
        return cls._store

    @classmethod
    def _resolve_locale(cls, locale: object, fallback_locale: str | None = None) -> str:
        """Map ``locale`` to a supported one, falling back on its language, then on ``fallback_locale``."""
        if isinstance(locale, str) and locale in cls.SUPPORTED_LOCALES:
            return locale
        language = str(locale).replace("-", "_").split("_")[0]
        for supported in cls.SUPPORTED_LOCALES:
            if supported.split("_")[0] == language:
                return supported
        if fallback_locale is not None:
            return cls._resolve_locale(fallback_locale)
        raise ValueError(
            f"Unsupported locale {locale!r}; supported locales are {', '.join(cls.SUPPORTED_LOCALES)} "
            "(pass fallback_locale to use one of them instead)"
        )

    @classmethod
    def register(cls, fake: Any, fallback_locale: str | None = None) -> None:
        """Add the provider to ``fake``, a ``Faker`` with one or several locales.

        ``Faker(["fr_FR", "en_US"]).add_provider()`` is not supported by Faker
        in multi-locale mode: this method adds the provider to each locale.
        Locales the provider does not support (``de_DE``...) raise a
        ``ValueError``, unless ``fallback_locale`` (e.g. ``"en_US"``) names the
        locale to use for them.  Nothing is added when a locale is refused.
        """
        generators = [generator for _, generator in fake.items()] if hasattr(fake, "items") else [fake]
        providers = [cls(generator, fallback_locale) for generator in generators]
        for generator, provider in zip(generators, providers, strict=True):
            generator.add_provider(provider)

    def __init__(self, generator: Any, fallback_locale: str | None = None) -> None:
        super().__init__(generator)
        # Faker has no public accessor for a generator's locale
        config = getattr(generator, "_Generator__config", {})
        locale = config.get("locale", "en_US") if isinstance(config, dict) else "en_US"
        self._provider_locale = self._resolve_locale(locale, fallback_locale)
        self._get_store()

    @property
    def provider_locale(self) -> str:
        """Return the locale used by this provider."""
        return self._provider_locale

    @property
    def store(self) -> BookStore:
        """Return the :class:`BookStore` shared by every provider."""
        return self._get_store()

    @property
    def db(self) -> Table:
        """Return the TinyDB table holding the book records."""
        return self._get_store().books

    @property
    def books_flat(self) -> list[Record]:
        """Return a copy of every raw (non-localized) book record."""
        return [dict(book) for book in copy.deepcopy(self._get_store().books.all())]

    @property
    def _catalogue(self) -> tuple[LocalizedBook, ...]:
        return self._get_store().localized(self.provider_locale)

    @staticmethod
    def _export(book: LocalizedBook) -> LocalizedBook:
        """Return a caller-owned copy of a localized record."""
        return dict(book, genre=list(book["genre"]))

    @property
    def books(self) -> tuple[LocalizedBook, ...]:
        """Return the shared catalogue localized for the current locale."""
        return tuple(self._export(book) for book in self._catalogue)

    def _search(self, condition: QueryLike) -> list[LocalizedBook]:
        return [self._export(book) for book in self._get_store().search(condition, self.provider_locale)]

    def _pool(self, key: Hashable, build: Callable[[tuple[LocalizedBook, ...]], T]) -> T:
        """Return a value derived from the localized catalogue, cached until the catalogue changes."""
        return self._get_store().derived(self.provider_locale, key, build)

    # Query methods with advanced filtering
    def books_by_author(self, author_name: str) -> list[LocalizedBook]:
        """Query books by author name (as spelled in the current locale).

        Case, accents and punctuation are ignored ("emile zola" finds "Émile
        Zola"), and a co-author finds the books written together.
        """
        locale = self.provider_locale
        wanted = name_key(author_name)

        def matches(writer: Any) -> bool:
            name = pick(writer, locale)
            return any(name_key(author) == wanted for author in [name, *_authors(name)])

        return self._search(Query().writer.test(matches))

    def books_by_genre(self, genre_name: str) -> list[LocalizedBook]:
        """Query books by genre, case-insensitively, in the current locale."""
        locale = self.provider_locale
        wanted = genre_name.casefold()
        return self._search(
            Query().genre.test(lambda genres: wanted in (g.casefold() for g in pick(genres, locale)))
        )

    def books_by_year(self, year: int) -> list[LocalizedBook]:
        """Query books published in a specific year."""
        return self._search(Query().year == year)

    def books_by_year_range(self, start_year: int, end_year: int) -> list[LocalizedBook]:
        """Query books published within a year range."""
        Book = Query()
        return self._search((Book.year >= start_year) & (Book.year <= end_year))

    def all_authors(self) -> list[str]:
        """Return the sorted list of authors (co-authors are listed separately)."""
        return list(self._pool("all_authors", lambda books: sorted(
            {author for book in books for author in _authors(book["writer"])})))

    def all_genres(self) -> list[str]:
        """Return list of all unique genres for the current locale."""
        return list(self._pool("all_genres", lambda books: sorted(
            {genre for book in books for genre in book["genre"]})))

    def all_nationalities(self) -> list[str]:
        """Return list of all unique author nationalities for the current locale."""
        return list(self._pool("all_nationalities", lambda books: sorted(
            {book["nationality"] for book in books})))

    # Standard methods (for Faker compatibility)
    @staticmethod
    def _book_matches_genre(book: LocalizedBook, genre_name: str) -> bool:
        """Check if a book's genre includes the given genre (case-insensitive)."""
        return _has_genre(book, genre_name)

    def book(self) -> LocalizedBook:
        """Return a coherent fake book record."""
        return self._export(self.random_element(self._catalogue))

    def writer(self, nationality: str | None = None, genre: str | None = None) -> str:
        """Return a famous writer, optionally filtered by nationality and/or genre.

        By default, nationality is derived from the current locale
        (e.g. ``fr_FR`` -> French writers, ``en_US`` -> American writers).
        Pass ``nationality`` to target a different nationality (in the current
        locale's language, case-insensitively), or :attr:`ANY_NATIONALITY`
        (``"*"``) for writers of every nationality.  Pass ``genre`` to restrict
        to writers of that genre.  Writers are drawn in proportion to their
        number of books; the authors of a co-written book are drawn one by one.
        """
        if nationality is None:
            nationality = self.LOCALE_DEFAULT_NATIONALITY[self.provider_locale]
        wanted = None if nationality == self.ANY_NATIONALITY else nationality.casefold()

        def build(books: tuple[LocalizedBook, ...]) -> tuple[str, ...]:
            return tuple(
                author for book in books
                if (wanted is None or book["nationality"].casefold() == wanted) and _has_genre(book, genre)
                for author in _authors(book["writer"])
            )

        writers = self._pool(("writers", wanted, None if genre is None else genre.casefold()), build)
        if not writers:
            raise ValueError(f"No writer found for nationality={nationality!r}, genre={genre!r}")
        return self.random_element(writers)

    author = writer

    def title(self, genre: str | None = None) -> str:
        """Return a well-known literary title, optionally filtered by genre (case-insensitive)."""
        key = ("titles", None if genre is None else genre.casefold())
        titles: tuple[str, ...] = self._pool(key, lambda books: tuple(
            book["title"] for book in books if _has_genre(book, genre)))
        if not titles:
            raise ValueError(f"No title found for genre={genre!r}")
        return self.random_element(titles)

    def genre(self) -> str:
        """Return a literary genre translated for the current locale.

        Genres are drawn in proportion to their number of books.
        """
        genres: tuple[str, ...] = self._pool("genres", lambda books: tuple(
            genre for book in books for genre in book["genre"]))
        return self.random_element(genres)

    def publication_year(self) -> int:
        """Return a publication year represented in the catalogue."""
        years: tuple[int, ...] = self._pool("years", lambda books: tuple(book["year"] for book in books))
        return self.random_element(years)

    def pages(self) -> int:
        """Return a plausible page count from the catalogue."""
        pages: tuple[int, ...] = self._pool("pages", lambda books: tuple(
            book["pages"] for book in books if book["pages"] is not None))
        return self.random_element(pages)

    def publisher(self) -> str:
        """Return a publisher represented in the catalogue."""
        publishers: tuple[str, ...] = self._pool("publishers", lambda books: tuple(
            book["publisher"] for book in books if book["publisher"]))
        return self.random_element(publishers)

    def nationality(self) -> str:
        """Return an author nationality for the current locale.

        Each author counts once, whatever their number of books.
        """
        def build(books: tuple[LocalizedBook, ...]) -> tuple[str, ...]:
            by_author = {author: book["nationality"] for book in books for author in _authors(book["writer"])}
            return tuple(by_author[author] for author in sorted(by_author))

        return self.random_element(self._pool("nationalities", build))

    def literary_work(self) -> LocalizedBook:
        """Alias for :meth:`book` suitable for generated datasets."""
        return self.book()
