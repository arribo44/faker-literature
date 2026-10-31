"""Faker provider for generating literature-related data."""

import copy

from faker.providers import BaseProvider
from tinydb import Query

from faker_literature.store import LOCALES, BookStore, default_db_path, pick


__all__ = ["LiteratureProvider", "BookStore", "default_db_path"]


class LiteratureProvider(BaseProvider):
    """Generate authors, books, genres and publishing details in two locales."""

    SUPPORTED_LOCALES = LOCALES

    LOCALE_DEFAULT_NATIONALITY = {
        "fr_FR": "français",
        "en_US": "American",
    }

    # Catalogue shared by every provider instance (lazy initialization)
    _store = None

    @classmethod
    def use_database(cls, path=None):
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
    def _get_store(cls):
        if cls._store is None:
            cls._store = BookStore()
        return cls._store

    @classmethod
    def _resolve_locale(cls, locale):
        """Map ``locale`` to a supported one, falling back on its language."""
        if locale in cls.SUPPORTED_LOCALES:
            return locale
        language = str(locale).replace("-", "_").split("_")[0]
        for supported in cls.SUPPORTED_LOCALES:
            if supported.split("_")[0] == language:
                return supported
        raise ValueError(
            f"Unsupported locale {locale!r}; supported locales are {', '.join(cls.SUPPORTED_LOCALES)}"
        )

    def __init__(self, generator):
        super().__init__(generator)
        # Faker has no public accessor for a generator's locale
        config = getattr(generator, "_Generator__config", {})
        locale = config.get("locale", "en_US") if isinstance(config, dict) else "en_US"
        self._provider_locale = self._resolve_locale(locale)
        self._get_store()

    @property
    def provider_locale(self):
        """Return the locale used by this provider."""
        return self._provider_locale

    @property
    def store(self):
        """Return the :class:`BookStore` shared by every provider."""
        return self._get_store()

    @property
    def db(self):
        """Return the TinyDB table holding the book records."""
        return self._get_store().books

    @property
    def books_flat(self):
        """Return a copy of every raw (non-localized) book record."""
        return copy.deepcopy(self._get_store().books.all())

    @property
    def _catalogue(self):
        return self._get_store().localized(self.provider_locale)

    @staticmethod
    def _export(book):
        """Return a caller-owned copy of a localized record."""
        return dict(book, genre=list(book["genre"]))

    @property
    def books(self):
        """Return the shared catalogue localized for the current locale."""
        return tuple(self._export(book) for book in self._catalogue)

    def _search(self, condition):
        return [self._export(book) for book in self._get_store().search(condition, self.provider_locale)]

    # Query methods with advanced filtering
    def books_by_author(self, author_name):
        """Query books by author name (as spelled in the current locale)."""
        locale = self.provider_locale
        return self._search(Query().writer.test(lambda writer: pick(writer, locale) == author_name))

    def books_by_genre(self, genre_name):
        """Query books by genre, case-insensitively, in the current locale."""
        locale = self.provider_locale
        wanted = genre_name.lower()
        return self._search(
            Query().genre.test(lambda genres: wanted in (g.lower() for g in pick(genres, locale)))
        )

    def books_by_year(self, year):
        """Query books published in a specific year."""
        return self._search(Query().year == year)

    def books_by_year_range(self, start_year, end_year):
        """Query books published within a year range."""
        Book = Query()
        return self._search((Book.year >= start_year) & (Book.year <= end_year))

    def all_authors(self):
        """Return list of all unique authors."""
        return sorted(set(book["writer"] for book in self._catalogue))

    def all_genres(self):
        """Return list of all unique genres for the current locale."""
        return sorted(set(genre for book in self._catalogue for genre in book["genre"]))

    def all_nationalities(self):
        """Return list of all unique author nationalities for the current locale."""
        return sorted(set(book["nationality"] for book in self._catalogue))

    # Standard methods (for Faker compatibility)
    @staticmethod
    def _book_matches_genre(book, genre_name):
        """Check if a book's genre includes the given genre (case-insensitive)."""
        return genre_name.lower() in [g.lower() for g in book["genre"]]

    def book(self):
        """Return a coherent fake book record."""
        return self._export(self.random_element(self._catalogue))

    def writer(self, nationality=None, genre=None):
        """Return a famous writer, optionally filtered by nationality and/or genre.

        By default, nationality is derived from the current locale
        (e.g. ``fr_FR`` -> French writers, ``en_US`` -> American writers).
        Pass ``nationality`` to target a different nationality (in the current
        locale's language).  Pass ``genre`` to restrict to writers of that genre.
        """
        if nationality is None:
            nationality = self.LOCALE_DEFAULT_NATIONALITY.get(self.provider_locale)
        pool = [b for b in self._catalogue if b["nationality"] == nationality]
        if genre is not None:
            pool = [b for b in pool if self._book_matches_genre(b, genre)]
        writers = [b["writer"] for b in pool]
        if not writers:
            raise ValueError(
                f"No writer found for nationality={nationality!r}, genre={genre!r}"
            )
        return self.random_element(writers)

    author = writer

    def title(self, genre=None):
        """Return a well-known literary title, optionally filtered by genre."""
        pool = self._catalogue
        if genre is not None:
            pool = [b for b in pool if self._book_matches_genre(b, genre)]
        titles = [b["title"] for b in pool]
        if not titles:
            raise ValueError(f"No title found for genre={genre!r}")
        return self.random_element(titles)

    def genre(self):
        """Return a literary genre translated for the current locale."""
        return self.random_element([genre for book in self._catalogue for genre in book["genre"]])

    def publication_year(self):
        """Return a publication year represented in the catalogue."""
        return self.random_element([book["year"] for book in self._catalogue])

    def pages(self):
        """Return a plausible page count from the catalogue."""
        return self.random_element([book["pages"] for book in self._catalogue if book["pages"] is not None])

    def publisher(self):
        """Return a publisher represented in the catalogue."""
        return self.random_element([book["publisher"] for book in self._catalogue if book["publisher"]])

    def nationality(self):
        """Return an author nationality for the current locale."""
        return self.random_element([book["nationality"] for book in self._catalogue])

    def literary_work(self):
        """Alias for :meth:`book` suitable for generated datasets."""
        return self.book()
