"""Faker provider for generating literature-related data."""

from __future__ import annotations

import copy
import datetime
import itertools
import statistics
from collections import Counter
from collections.abc import Callable, Hashable, Iterable, Sequence
from typing import Any, TypeVar

from faker.providers import BaseProvider
from tinydb import Query
from tinydb.queries import QueryLike
from tinydb.table import Table

from faker_literature.citation import format_citation
from faker_literature.edition import CURRENCIES, FORMATS, make_isbn13, round_price
from faker_literature.matching import name_key
from faker_literature.store import LOCALES, BookStore, LocalizedBook, PathLike, Record, default_db_path, pick

__version__ = "0.4.0"
__all__ = ["LiteratureProvider", "BookFilter", "BookStore", "default_db_path", "__version__"]

T = TypeVar("T")

# Fields of the localized books used by the provider but left out of book()
INTERNAL_FIELDS = ("popularity", "writer_born", "writer_died", "awards")

# Editions of older works are drawn from this year on
EARLIEST_EDITION_YEAR = 1950

# Books written together list their authors in one string: "Author A, Author B"
CO_AUTHOR_SEPARATOR = ", "


def _authors(writer: str) -> list[str]:
    """Split the ``writer`` of a co-written book into its authors."""
    return writer.split(CO_AUTHOR_SEPARATOR)


def _has_genre(book: LocalizedBook, genre: str | None) -> bool:
    return genre is None or genre.casefold() in (g.casefold() for g in book["genre"])


def _median_popularity(books: Sequence[LocalizedBook]) -> float:
    """Popularity given to the books that have none: the median of the others, or 1."""
    known = [book["popularity"] for book in books if book.get("popularity")]
    return float(statistics.median(known)) if known else 1.0


class BookFilter:
    """The filters shared by the drawing methods (see :meth:`LiteratureProvider.book`)."""

    def __init__(
        self,
        genre: str | None = None,
        nationality: str | None = None,
        author: str | None = None,
        after: int | None = None,
        before: int | None = None,
        century: int | None = None,
        award: str | None = None,
    ) -> None:
        if century is not None:
            if century == 0:
                raise ValueError("century: there is no century 0 (use 1 for years 1-100, -1 for 100-1 BC)")
            # 19 -> 1801..1900, -5 -> 500..401 BC
            first, last = (century * 100 - 99, century * 100) if century > 0 else (century * 100, century * 100 + 99)
            after = first if after is None else max(after, first)
            before = last if before is None else min(before, last)
        self.description = {name: value for name, value in (
            ("genre", genre), ("nationality", nationality), ("author", author),
            ("after", after), ("before", before), ("award", award)) if value is not None}
        self.genre = None if genre is None else genre.casefold()
        any_nationality = nationality == LiteratureProvider.ANY_NATIONALITY
        self.nationality = None if nationality is None or any_nationality else nationality.casefold()
        self.author = None if author is None else name_key(author)
        self.after = after
        self.before = before
        # "*": any award; otherwise part of an award's name, case-insensitive ("goncourt")
        self.award = None if award is None else award.casefold()
        # Cache key of the pools drawn with these filters
        self.key = (self.genre, self.nationality, self.author, after, before, self.award)

    def matches(self, book: LocalizedBook) -> bool:
        year = book["year"]
        return (
            (self.after is None or year >= self.after)
            and (self.before is None or year <= self.before)
            and (self.nationality is None or book["nationality"].casefold() == self.nationality)
            and (self.genre is None or _has_genre(book, self.genre))
            and (self.author is None or any(
                name_key(name) == self.author for name in [book["writer"], *_authors(book["writer"])]))
            and (self.award is None or (bool(book.get("awards")) if self.award == "*" else any(
                self.award in award.casefold() for award in book.get("awards", ()))))
        )

    def __str__(self) -> str:
        return ", ".join(f"{name}={value!r}" for name, value in self.description.items()) or "no filter"


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
        """Return a caller-owned copy of a localized record, without the internal fields."""
        exported = dict(book, genre=list(book["genre"]))
        for field in INTERNAL_FIELDS:
            exported.pop(field, None)
        return exported

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

    def books_by_award(self, award: str) -> list[LocalizedBook]:
        """Return the books that received an award, by part of its name (case-insensitive), or ``"*"`` for any."""
        book_filter = BookFilter(award=award)
        return [self._export(book) for book in self._catalogue if book_filter.matches(book)]

    def all_awards(self) -> list[str]:
        """Return the sorted literary awards of the catalogue, in the current locale."""
        return list(self._pool("all_awards", lambda books: sorted(
            {award for book in books for award in book.get("awards", ())}, key=str.casefold)))

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

    def _weights(self, books: Sequence[LocalizedBook]) -> list[float]:
        """Return the drawing weights of ``books``: the square of their popularity.

        Squared, the best known tenth of the catalogue makes about three
        quarters of the draws (less than half in plain proportion, the long
        tail of little-known books weighing too much).  Books without a
        popularity count as the median one.
        """
        default = self._pool("median_popularity", _median_popularity)
        return [float(book["popularity"] if book.get("popularity") else default) ** 2 for book in books]

    def _draw(
        self,
        what: str,
        values_of: Callable[[LocalizedBook], Iterable[T]],
        filters: BookFilter,
        popular: bool,
    ) -> T:
        """Draw one of the values ``values_of`` gives for the books matching ``filters``.

        Each book contributes its values once, or in proportion to its
        popularity when ``popular`` is true.
        """
        def build(books: tuple[LocalizedBook, ...]) -> tuple[tuple[T, ...], tuple[float, ...] | None]:
            matching = [book for book in books if filters.matches(book)]
            pairs = [(value, book) for book in matching for value in values_of(book)]
            values = tuple(value for value, _ in pairs)
            if not popular:
                return values, None
            return values, tuple(itertools.accumulate(self._weights([book for _, book in pairs])))

        values, cum_weights = self._pool((what, filters.key, popular), build)
        if not values:
            raise ValueError(f"No {what} found for {filters}")
        drawn: T
        if cum_weights is None:
            drawn = self.random_element(values)
        else:
            drawn = self.generator.random.choices(values, cum_weights=cum_weights)[0]
        return drawn

    def book(
        self,
        genre: str | None = None,
        nationality: str | None = None,
        author: str | None = None,
        after: int | None = None,
        before: int | None = None,
        century: int | None = None,
        popular: bool = False,
        award: str | None = None,
    ) -> LocalizedBook:
        """Return a coherent fake book record, optionally filtered.

        Every drawing method accepts the same filters, combined with "and":

        - ``genre``: one of the book's genres (case-insensitive);
        - ``nationality``: the author's nationality, in the current locale's
          language (case-insensitive), or :attr:`ANY_NATIONALITY`;
        - ``author``: the author or a co-author, ignoring case, accents and
          punctuation;
        - ``after`` / ``before``: first publication in or after / before or in
          that year (negative for BC);
        - ``century``: first publication in that century (``19`` for 1801-1900,
          ``-5`` for 500-401 BC);
        - ``award``: a literary award the work received, by part of its name
          (``"goncourt"``, ``"hugo"``, case-insensitive), or ``"*"`` for any.

        With ``popular=True``, well-known books (those having the most
        Wikipedia articles) are drawn more often.  A ``ValueError`` is raised
        when no book matches.
        """
        filters = BookFilter(genre, nationality, author, after, before, century, award)
        return self._export(self._draw("book", lambda book: (book,), filters, popular))

    def literary_work(self, **filters: Any) -> LocalizedBook:
        """Alias for :meth:`book` suitable for generated datasets."""
        return self.book(**filters)

    def books_sample(self, n: int, popular: bool = False, **filters: Any) -> list[LocalizedBook]:
        """Return ``n`` different books, drawn without replacement (see :meth:`book` for the filters).

        ``fake.unique.book()`` cannot work, a book being a dictionary: use this
        method to fill a table with distinct books.  With ``popular=True``,
        well-known books are more likely to be drawn.  A ``ValueError`` is
        raised when fewer than ``n`` books match.
        """
        book_filter = BookFilter(**filters)
        books = self._pool(("matching", book_filter.key),
                           lambda catalogue: tuple(book for book in catalogue if book_filter.matches(book)))
        if not 0 <= n <= len(books):
            raise ValueError(f"Cannot draw {n} books: {len(books)} match {book_filter}")
        rng = self.generator.random
        if popular:
            # Weighted sampling without replacement (Efraimidis-Spirakis): the n highest u ** (1 / weight)
            keys = [rng.random() ** (1 / weight) for weight in self._weights(books)]
            chosen = [books[i] for i in sorted(range(len(books)), key=keys.__getitem__, reverse=True)[:n]]
        else:
            chosen = rng.sample(books, n)
        return [self._export(book) for book in chosen]

    def edition(self, popular: bool = False, **filters: Any) -> dict[str, Any]:
        """Return a coherent edition of a catalogue work (see :meth:`book` for the filters).

        The edition keeps the work's fields (``writer``, ``nationality``,
        ``title``, ``genre``, ``year`` of first publication) and adds:

        - ``publisher``: the work's publisher, or a publisher of the locale's
          own writers (French publishers for a French edition);
        - ``edition_year``: between the first publication (or 1950 for older
          works) and the current year;
        - ``format``: pocket, paperback or hardcover, in the locale's language;
        - ``pages``: the work's page count adjusted to the format;
        - ``price`` and ``currency``: a shop price for that format (EUR or USD);
        - ``isbn``: a valid ISBN-13 whose prefix belongs to the publisher.
        """
        book = self.book(popular=popular, **filters)
        rng = self.generator.random
        locale = self.provider_locale
        publisher = book["publisher"]
        if not publisher or rng.random() < 0.5:
            # Another publisher of the locale's own writers: French publishers for a French edition
            try:
                publisher = self.publisher(nationality=self.LOCALE_DEFAULT_NATIONALITY[locale])
            except ValueError:
                publisher = self.publisher()
        current_year = datetime.date.today().year
        first_year = min(max(book["year"], EARLIEST_EDITION_YEAR), current_year)
        edition_format = rng.choice(FORMATS[locale])
        base_pages = book["pages"] if book["pages"] is not None else self.pages()
        price = rng.uniform(edition_format.min_price, edition_format.max_price)
        edition = dict(book)
        edition.update({
            "publisher": publisher,
            "edition_year": rng.randint(first_year, current_year),
            "format": edition_format.name,
            "pages": max(1, round(base_pages * edition_format.page_ratio)),
            "price": round_price(price, locale),
            "currency": CURRENCIES[locale],
            "isbn": make_isbn13(publisher, locale, rng.randrange(10000)),
        })
        return edition

    def citation(self, style: str = "apa", book: LocalizedBook | None = None, **filters: Any) -> str:
        """Return the bibliographic reference of a book, in the ``apa``, ``mla`` or ``chicago`` style.

        The book is drawn with ``filters`` (see :meth:`book`) unless given.
        Titles are not italicized (plain text); years BC read "800 BC" in
        English, "800 av. J.-C." in French.
        """
        if book is None:
            book = self.book(**filters)
        elif filters:
            raise TypeError("citation(): pass either a book or filters, not both")
        return format_citation(book, style, self.provider_locale)

    def writer(
        self,
        nationality: str | None = None,
        genre: str | None = None,
        after: int | None = None,
        before: int | None = None,
        century: int | None = None,
        popular: bool = False,
        award: str | None = None,
    ) -> str:
        """Return a famous writer, optionally filtered (see :meth:`book` for the filters).

        By default, nationality is derived from the current locale
        (e.g. ``fr_FR`` -> French writers, ``en_US`` -> American writers).
        Pass ``nationality`` to target a different nationality (in the current
        locale's language, case-insensitively), or :attr:`ANY_NATIONALITY`
        (``"*"``) for writers of every nationality.  Writers are drawn in
        proportion to their number of books (or to their books' popularity
        with ``popular=True``); the authors of a co-written book are drawn one
        by one.
        """
        if nationality is None:
            nationality = self.LOCALE_DEFAULT_NATIONALITY[self.provider_locale]
        filters = BookFilter(genre, nationality, None, after, before, century, award)
        drawn: str = self._draw("writer", lambda book: _authors(book["writer"]), filters, popular)
        return drawn

    author = writer

    def title(
        self,
        genre: str | None = None,
        nationality: str | None = None,
        author: str | None = None,
        after: int | None = None,
        before: int | None = None,
        century: int | None = None,
        popular: bool = False,
        award: str | None = None,
    ) -> str:
        """Return a well-known literary title, optionally filtered (see :meth:`book`)."""
        filters = BookFilter(genre, nationality, author, after, before, century, award)
        drawn: str = self._draw("title", lambda book: (book["title"],), filters, popular)
        return drawn

    def genre(
        self,
        nationality: str | None = None,
        author: str | None = None,
        after: int | None = None,
        before: int | None = None,
        century: int | None = None,
        popular: bool = False,
        award: str | None = None,
    ) -> str:
        """Return a literary genre translated for the current locale, optionally filtered (see :meth:`book`).

        Genres are drawn in proportion to their number of books.
        """
        filters = BookFilter(None, nationality, author, after, before, century, award)
        drawn: str = self._draw("genre", lambda book: book["genre"], filters, popular)
        return drawn

    def publication_year(self, **filters: Any) -> int:
        """Return a publication year represented in the catalogue, optionally filtered (see :meth:`book`)."""
        popular = filters.pop("popular", False)
        drawn: int = self._draw("year", lambda book: (book["year"],), BookFilter(**filters), popular)
        return drawn

    def pages(self, **filters: Any) -> int:
        """Return a plausible page count from the catalogue, optionally filtered (see :meth:`book`)."""
        popular = filters.pop("popular", False)
        drawn: int = self._draw("pages", lambda book: () if book["pages"] is None else (book["pages"],),
                                BookFilter(**filters), popular)
        return drawn

    def publisher(self, **filters: Any) -> str:
        """Return a publisher represented in the catalogue, optionally filtered (see :meth:`book`)."""
        popular = filters.pop("popular", False)
        drawn: str = self._draw("publisher", lambda book: (book["publisher"],) if book["publisher"] else (),
                                BookFilter(**filters), popular)
        return drawn

    def award(
        self,
        genre: str | None = None,
        nationality: str | None = None,
        author: str | None = None,
        after: int | None = None,
        before: int | None = None,
        century: int | None = None,
        popular: bool = False,
    ) -> str:
        """Return a literary award received by a catalogue work, optionally filtered (see :meth:`book`).

        Awards are drawn in proportion to their number of awarded books.
        """
        filters = BookFilter(genre, nationality, author, after, before, century)
        drawn: str = self._draw("award", lambda book: book.get("awards", ()), filters, popular)
        return drawn

    def writer_profile(self, name: str | None = None, **filters: Any) -> dict[str, Any]:
        """Return the profile of a writer: life, nationality, books and main genres.

        ``name`` picks the writer (ignoring case, accents and punctuation);
        otherwise one is drawn like :meth:`writer`, with the same filters.
        The profile holds ``name``, ``nationality``, ``born`` and ``died``
        (years, ``None`` when unknown or for living writers), ``books`` (their
        ``title`` and ``year``, oldest first) and ``genres`` (the five most
        frequent) and ``awards`` (those their books received).  A
        ``ValueError`` is raised for an unknown name.
        """
        if name is None:
            name = self.writer(**filters)
        elif filters:
            raise TypeError("writer_profile(): pass either a name or filters, not both")
        wanted = name_key(name)
        books = sorted((book for book in self._catalogue
                        if any(name_key(author) == wanted for author in _authors(book["writer"]))),
                       key=lambda book: (book["year"], book["title"]))
        if not books:
            raise ValueError(f"No writer named {name!r}")
        single = [book for book in books if CO_AUTHOR_SEPARATOR not in book["writer"]] or books
        genres = Counter(genre for book in books for genre in book["genre"])
        return {
            "name": next((author for author in _authors(books[0]["writer"]) if name_key(author) == wanted), name),
            "nationality": single[0]["nationality"],
            "born": single[0].get("writer_born"),
            "died": single[0].get("writer_died"),
            "books": [{"title": book["title"], "year": book["year"]} for book in books],
            "genres": [genre for genre, _ in genres.most_common(5)],
            "awards": sorted({award for book in books for award in book.get("awards", ())}, key=str.casefold),
        }

    def nationality(self) -> str:
        """Return an author nationality for the current locale.

        Each author counts once, whatever their number of books.
        """
        def build(books: tuple[LocalizedBook, ...]) -> tuple[str, ...]:
            by_author = {author: book["nationality"] for book in books for author in _authors(book["writer"])}
            return tuple(by_author[author] for author in sorted(by_author))

        return self.random_element(self._pool("nationalities", build))
