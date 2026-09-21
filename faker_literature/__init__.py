"""Faker provider for generating literature-related data."""

import json
from pathlib import Path
from faker.providers import BaseProvider
from tinydb import TinyDB, Query


class LiteratureProvider(BaseProvider):
    """Generate authors, books, genres and publishing details in two locales."""

    SUPPORTED_LOCALES = ("fr_FR", "en_US")

    LOCALE_DEFAULT_NATIONALITY = {
        "fr_FR": "français",
        "en_US": "American",
    }

    # Class variable to hold the TinyDB instance (lazy initialization)
    _db = None
    _books_flat = None

    @classmethod
    def _init_db(cls):
        """Initialize TinyDB from optimized JSON file."""
        if cls._db is not None:
            return cls._db, cls._books_flat

        # Load optimized JSON with authors
        data_path = Path(__file__).parent / "DATAS" / "literature.json"
        with open(data_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Initialize TinyDB with file storage
        db_path = Path(__file__).parent / "DATAS" / ".literature_db.json"
        db = TinyDB(str(db_path), indent=4, ensure_ascii=False)
        
        # Check if database is empty, if so populate it
        if len(db) == 0:
            # Flatten and insert all books with author info
            for author_entry in data["authors"]:
                author_name = author_entry["name"]
                for book in author_entry["books"]:
                    flat_book = {
                        "writer": author_name,
                        "nationality": author_entry["nationality"],
                        **book
                    }
                    db.insert(flat_book)

        # Build flat books list from database
        flat_books = db.all()

        cls._db = db
        cls._books_flat = flat_books
        return db, flat_books

    def __init__(self, generator):
        super().__init__(generator)
        config = getattr(generator, "_Generator__config", {})
        locale = config.get("locale", "en_US") if isinstance(config, dict) else "en_US"
        if locale not in self.SUPPORTED_LOCALES:
            raise ValueError(
                f"Unsupported locale {locale!r}; supported locales are {', '.join(self.SUPPORTED_LOCALES)}"
            )
        self._provider_locale = locale
        # Ensure DB is initialized
        self.__class__._init_db()

    @property
    def provider_locale(self):
        """Return the locale used by this provider."""
        return self._provider_locale

    @property
    def db(self):
        """Return TinyDB instance."""
        return self._init_db()[0]

    @property
    def books_flat(self):
        """Return flat list of all books."""
        return self._init_db()[1]

    @property
    def books(self):
        """Return the shared catalogue localized for the current locale."""
        locale = self.provider_locale
        return tuple(
            {
                "writer": book["writer"],
                "nationality": book["nationality"][locale],
                "title": book["title"][locale],
                "genre": book["genre"][locale],
                "year": book["year"],
                "pages": book["pages"][locale],
                "publisher": book["publisher"][locale],
            }
            for book in self.books_flat
        )

    # Query methods with advanced filtering
    def books_by_author(self, author_name):
        """Query books by author name."""
        Book = Query()
        results = self.db.search(Book.writer == author_name)
        locale = self.provider_locale
        return [
            {
                "writer": book["writer"],
                "nationality": book["nationality"][locale],
                "title": book["title"][locale],
                "genre": book["genre"][locale],
                "year": book["year"],
                "pages": book["pages"][locale],
                "publisher": book["publisher"][locale],
            }
            for book in results
        ]

    def books_by_genre(self, genre_name):
        """Query books by genre (searches both locale variants)."""
        locale = self.provider_locale
        results = []
        for book in self.books_flat:
            genres = book["genre"][locale] if isinstance(book["genre"], dict) else book["genre"]
            if isinstance(genres, list):
                if genre_name.lower() in [g.lower() for g in genres]:
                    results.append({
                        "writer": book["writer"],
                        "nationality": book["nationality"][locale],
                        "title": book["title"][locale],
                        "genre": genres,
                        "year": book["year"],
                        "pages": book["pages"][locale],
                        "publisher": book["publisher"][locale],
                    })
            else:
                if genre_name.lower() == genres.lower():
                    results.append({
                        "writer": book["writer"],
                        "nationality": book["nationality"][locale],
                        "title": book["title"][locale],
                        "genre": [genres],
                        "year": book["year"],
                        "pages": book["pages"][locale],
                        "publisher": book["publisher"][locale],
                    })
        return results

    def books_by_year(self, year):
        """Query books published in a specific year."""
        Book = Query()
        results = self.db.search(Book.year == year)
        locale = self.provider_locale
        return [
            {
                "writer": book["writer"],
                "nationality": book["nationality"][locale],
                "title": book["title"][locale],
                "genre": book["genre"][locale],
                "year": book["year"],
                "pages": book["pages"][locale],
                "publisher": book["publisher"][locale],
            }
            for book in results
        ]

    def books_by_year_range(self, start_year, end_year):
        """Query books published within a year range."""
        Book = Query()
        results = self.db.search((Book.year >= start_year) & (Book.year <= end_year))
        locale = self.provider_locale
        return [
            {
                "writer": book["writer"],
                "nationality": book["nationality"][locale],
                "title": book["title"][locale],
                "genre": book["genre"][locale],
                "year": book["year"],
                "pages": book["pages"][locale],
                "publisher": book["publisher"][locale],
            }
            for book in results
        ]

    def all_authors(self):
        """Return list of all unique authors."""
        return sorted(set(book["writer"] for book in self.books_flat))

    def all_genres(self):
        """Return list of all unique genres for the current locale."""
        locale = self.provider_locale
        genres = set()
        for book in self.books_flat:
            if isinstance(book["genre"], dict):
                book_genres = book["genre"][locale]
            else:
                book_genres = book["genre"] if isinstance(book["genre"], list) else [book["genre"]]
            genres.update(book_genres)
        return sorted(genres)

    def all_nationalities(self):
        """Return list of all unique author nationalities for the current locale."""
        locale = self.provider_locale
        return sorted(set(book["nationality"][locale] for book in self.books_flat))

    # Standard methods (for Faker compatibility)
    @staticmethod
    def _book_matches_genre(book, genre_name):
        """Check if a book's genre includes the given genre (case-insensitive)."""
        genres = book["genre"]
        if isinstance(genres, list):
            return genre_name.lower() in [g.lower() for g in genres]
        return genre_name.lower() == genres.lower()

    def book(self):
        """Return a coherent fake book record."""
        return dict(self.random_element(self.books))

    def writer(self, nationality=None, genre=None):
        """Return a famous writer, optionally filtered by nationality and/or genre.

        By default, nationality is derived from the current locale
        (e.g. ``fr_FR`` -> French writers, ``en_US`` -> American writers).
        Pass ``nationality`` to target a different nationality (in the current
        locale's language).  Pass ``genre`` to restrict to writers of that genre.
        """
        if nationality is None:
            nationality = self.LOCALE_DEFAULT_NATIONALITY.get(self.provider_locale)
        pool = [b for b in self.books if b["nationality"] == nationality]
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
        pool = self.books
        if genre is not None:
            pool = [b for b in pool if self._book_matches_genre(b, genre)]
        titles = [b["title"] for b in pool]
        if not titles:
            raise ValueError(f"No title found for genre={genre!r}")
        return self.random_element(titles)

    def genre(self):
        """Return a literary genre translated for the current locale."""
        locale = self.provider_locale
        genres = []
        for book in self.books:
            # book["genre"] is already localized from the books property
            if isinstance(book["genre"], list):
                genres.extend(book["genre"])
            else:
                genres.append(book["genre"])
        return self.random_element(genres)

    def publication_year(self):
        """Return a publication year represented in the catalogue."""
        return self.random_element([book["year"] for book in self.books])

    def pages(self):
        """Return a plausible page count from the catalogue."""
        return self.random_element([book["pages"] for book in self.books])

    def publisher(self):
        """Return a publisher represented in the catalogue."""
        return self.random_element([book["publisher"] for book in self.books])

    def nationality(self):
        """Return an author nationality for the current locale."""
        return self.random_element([book["nationality"] for book in self.books])

    def literary_work(self):
        """Alias for :meth:`book` suitable for generated datasets."""
        return self.book()
