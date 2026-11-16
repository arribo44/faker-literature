# Faker Literature Provider

[![PyPI version](https://badge.fury.io/py/faker-literature.svg)](https://badge.fury.io/py/faker-literature)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/arribo44/faker-literature/actions/workflows/ci.yml/badge.svg)](https://github.com/arribo44/faker-literature/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](https://opensource.org/licenses/MIT)

**A custom [Faker](https://faker.readthedocs.io/) provider for generating realistic literature data: writers, books, genres, publishers and more.**
Every record comes from a real catalogue of well-known works, so a generated book is always *coherent*: its title, writer, year, genres and publisher belong together. The provider supports **two locales** (`fr_FR`, `en_US`), and you can enlarge the catalogue by importing works from [Wikidata](https://www.wikidata.org/) or your own datasets.

---

## 📚 Bundled Catalogue

| | Count |
|---|---|
| Authors | 190 |
| Books | 518 |
| Genres | ~210 per locale |
| Nationalities | 24 |
| Years covered | 800 BC → 2024 |

Classics, philosophy, crime fiction, science fiction, fantasy, horror, poetry, drama, essays and contemporary novels by French, American, British, Italian, Greek, Roman, Russian, German, Japanese, Latin-American writers, and more.

---

## 🌍 Supported Locales

| Locale | Language | Example Writer | Example Title | Example Genre | Example Publisher |
|--------|----------|----------------|---------------|---------------|-------------------|
| `en_US` | English (US) | "Dashiell Hammett" | "Brave New World" | "science fiction" | "Penguin Classics" |
| `fr_FR` | French (France) | "Daniel Pennac" | "Le Meilleur des mondes" | "science-fiction" | "Gallimard" |

Titles, genres, nationalities, publishers and page counts are **localized**: the same book is *"Le Crime de l'Orient-Express"* (Le Livre de poche, 256 pages) in `fr_FR` and *"Murder on the Orient Express"* (William Collins, Sons, 240 pages) in `en_US`.

> **Default locale**: `en_US` (if no locale is specified).
>
> **Regional variants** fall back on their language: `fr_CA`, `fr_BE`, `fr_CH` → `fr_FR`; `en_GB`, `en_AU`, `en_CA` → `en_US`.
>
> **Any other locale** (e.g. `de_DE`) raises a `ValueError`, so unsupported data is never silently mixed into a dataset — unless you ask for a fallback, see below.

### Several Locales at Once

Faker does not support `add_provider()` on a multi-locale `Faker`. Use `LiteratureProvider.register()`, which adds the provider to every locale (it also works with a single locale):

```python
fake = Faker(["fr_FR", "en_US"])
LiteratureProvider.register(fake)

fake.book()             # French or English record, picked at random like any Faker value
fake["fr_FR"].title()   # "Le Meilleur des mondes"

# Unsupported locales: refused by default, or mapped onto a supported one
fake = Faker(["de_DE", "fr_FR"])
LiteratureProvider.register(fake, fallback_locale="en_US")   # de_DE draws English data
```

---

## 📦 Installation

```bash
pip install faker-literature
```

Or install from the repository:

```bash
git clone https://github.com/arribo44/faker-literature.git
cd faker-literature
pip install -e .
```

**Requirements**: Python 3.10+, `faker>=20.0.0`, `tinydb>=4.0.0`. The package ships type hints (`py.typed`).

---

## 🚀 Usage

### Basic Setup

```python
from faker import Faker
from faker_literature import LiteratureProvider

# Use default locale (en_US)
fake = Faker()
fake.add_provider(LiteratureProvider)

# Or specify a locale
fake_fr = Faker("fr_FR")
fake_fr.add_provider(LiteratureProvider)
```

---

### 📖 Books

`book()` returns one **coherent** record: all its fields describe the same real work.

```python
book = fake.book()
# {
#     'writer': 'Robert E. Howard',
#     'nationality': 'American',
#     'title': 'Skulls in the Stars',
#     'genre': ['horror', 'sword and sorcery'],
#     'year': 1928,
#     'pages': 176,
#     'publisher': 'Weird Tales'
# }

book_fr = fake_fr.book()
# {
#     'writer': 'Robert E. Howard',
#     'nationality': 'américain',
#     'title': 'Des crânes dans les étoiles',
#     'genre': ['horreur', 'épée et sorcellerie'],
#     'year': 1928,
#     'pages': 192,
#     'publisher': 'Pocket'
# }

# Alias, convenient in dataset definitions
work = fake.literary_work()  # same as fake.book()
```

| Key | Type | Description |
|-----|------|-------------|
| `writer` | `str` | Author name (co-authors are joined with `, `) |
| `nationality` | `str` | Author nationality, localized (`"British"` / `"britannique"`) |
| `title` | `str` | Title, localized (translated title in `fr_FR`, English title in `en_US`) |
| `genre` | `list[str]` | One or more genres, localized |
| `year` | `int` | Year of first publication (negative for BC: `-800` for Homer) |
| `pages` | `int` or `None` | Page count in that locale: of a real edition for books imported from Wikidata, otherwise an **estimate** of the usual length (see below) |
| `publisher` | `str` or `None` | Publisher of a typical edition in that locale |

Each call returns a **new dictionary**: you can modify it freely without affecting the catalogue.

> **About page counts.** Most bundled books were entered by hand, with a page count that *estimates* the usual length of the work in each language (French editions are often a little longer). These estimates are realistic enough for test data but do not describe a specific edition: their raw records carry `"pages_estimated": true` (see `provider.books_flat`). Books imported from Wikidata carry the page count of a real edition when Wikidata has one, and `None` otherwise.

---

### ✍️ Writers

```python
# Random writer — by default, a writer of the locale's nationality
writer = fake.writer()     # "Dashiell Hammett" (en_US -> American writers)
writer = fake_fr.writer()  # "Daniel Pennac"    (fr_FR -> French writers)

# Writer of a given nationality (spelled in the current locale, case-insensitive)
british = fake.writer(nationality="British")         # "Arthur C. Clarke"
britannique = fake_fr.writer(nationality="britannique")  # "William Shakespeare"

# Writer of any nationality
anyone = fake.writer(nationality=LiteratureProvider.ANY_NATIONALITY)  # or nationality="*"

# Writer of a given genre (case-insensitive, in the current locale)
horror = fake.writer(genre="horror")                 # "Stephen King"
sf = fake_fr.writer(genre="science-fiction")         # "Alain Damasio"

# Both filters at once
fake.writer(nationality="American", genre="horror")  # "Stephen King", "H. P. Lovecraft"...

# Alias, accepts the same parameters
author = fake.author(nationality="British")
```

> Writers are drawn **in proportion to their number of books**: prolific authors appear more often. The authors of a co-written book are drawn one by one, never as `"A, B"`.

If no writer matches the filters, a `ValueError` is raised:

```python
fake.writer(nationality="American", genre="nope")
# ValueError: No writer found for nationality='American', genre='nope'
```

---

### 🏷️ Titles

```python
# Random title
title = fake.title()       # "Brave New World" (en_US)
title = fake_fr.title()    # "Le Meilleur des mondes" (fr_FR)

# Title of a given genre
fake.title(genre="science fiction")    # "Downbelow Station"
fake_fr.title(genre="roman policier")  # "Les Dieux de la guerre"

fake.title(genre="nope")
# ValueError: No title found for genre='nope'
```

---

### 🎭 Genres, Nationalities & Publishing Details

```python
genre = fake.genre()                 # "utopia" (en_US), "poésie" (fr_FR)
nationality = fake.nationality()     # "French" (en_US), "français" (fr_FR) — any nationality, each author counting once
year = fake.publication_year()       # 1978
pages = fake.pages()                 # 112
publisher = fake.publisher()         # "Penguin Classics" (en_US), "Gallimard" (fr_FR)
```

Each of these methods is an **independent** random draw from the catalogue. Use `book()` when the values must belong together. Genres, years, page counts and publishers are drawn in proportion to their number of books.

The values are drawn from pools computed once per locale and kept until the catalogue changes, so generating large datasets stays fast (a few microseconds per value).

---

### 🔎 Querying the Catalogue

The provider also exposes query methods that return **every** matching book (as a list of `book()`-like dictionaries) instead of a random one:

```python
# All books by an author (as spelled in the current locale, ignoring case, accents
# and punctuation: "emile zola", "j d salinger"); a co-author finds the books written together
fake.books_by_author("Victor Hugo")
# [{'title': 'The Hunchback of Notre-Dame', 'year': 1831, ...},
#  {'title': 'The Rays and the Shadows', 'year': 1840, ...},
#  {'title': 'Les Misérables', 'year': 1862, ...}, ...]

# All books of a genre (case-insensitive, current locale)
fake.books_by_genre("horror")           # 26 books
fake_fr.books_by_genre("roman policier")

# All books published in a year, or within a range (inclusive)
fake.books_by_year(1862)                # [{'writer': 'Victor Hugo', 'title': 'Les Misérables', ...}]
fake.books_by_year_range(1940, 1960)    # 53 books
fake.books_by_year_range(-500, 0)       # Ancient Greek works
```

Catalogue overview:

```python
fake.all_authors()        # ['Agatha Christie', 'Alain Damasio', ...]  (190, sorted; co-authors listed separately)
fake.all_genres()         # ['absurd novel', 'absurdism', 'adolescence', ...]  (sorted, localized)
fake.all_nationalities()  # ['Algerian', 'American', 'Ancient Greek', 'Argentine', ...]
fake_fr.all_nationalities()  # ['algérien', 'allemand', 'américain', 'argentin', ...]
```

Use these lists to pick valid values for the `nationality` and `genre` filters.

---

### 🔁 Reproducible Data

Like every Faker provider, results are deterministic once Faker is seeded:

```python
Faker.seed(42)
first = fake.book()

Faker.seed(42)
assert fake.book() == first
```

---

### 🌐 Multiple Locales at Once

Faker's multi-locale mode does not proxy `add_provider()`, so add the provider to each locale:

```python
fake = Faker(["fr_FR", "en_US"])
for locale in ("fr_FR", "en_US"):
    fake[locale].add_provider(LiteratureProvider)

fake["fr_FR"].title()  # "L'Appel de Cthulhu"
fake["en_US"].title()  # "The Symposium"
```

---

### 🗂️ Generating a Dataset

```python
import csv

from faker import Faker
from faker_literature import LiteratureProvider

fake = Faker("fr_FR")
fake.add_provider(LiteratureProvider)
Faker.seed(0)

with open("library.csv", "w", newline="", encoding="utf-8") as file:
    writer = csv.DictWriter(file, fieldnames=["isbn", "title", "writer", "genre", "year", "pages", "publisher", "copies"])
    writer.writeheader()
    for _ in range(1000):
        book = fake.book()
        writer.writerow({
            "isbn": fake.isbn13(),                         # Faker's built-in ISBN provider
            "title": book["title"],
            "writer": book["writer"],
            "genre": " / ".join(book["genre"]),
            "year": book["year"],
            "pages": book["pages"],
            "publisher": book["publisher"],
            "copies": fake.random_int(min=1, max=12),
        })
```

---

## 🗄️ Enlarging the Catalogue

By default the bundled catalogue is loaded **in memory** and nothing is written to disk. To generate more varied data, you can store an enlarged catalogue in a **persistent database** (a TinyDB JSON file).

### Importing from Wikidata

Import well-known literary works from Wikidata (CC0 licence) into a database stored in your user cache directory:

```bash
faker-literature import-wikidata --limit 500 --min-sitelinks 30
```

| Option | Default | Description |
|--------|---------|-------------|
| `--limit` | `500` | Maximum number of works to import (capped at 5000) |
| `--min-sitelinks` | `30` | Only works described by at least this many Wikipedia articles: higher means more famous |
| `--db PATH` | user cache | Database file (option placed *before* the command) |

```bash
# Import into a specific file
faker-literature --db ./my_catalogue.json import-wikidata --limit 1000 --min-sitelinks 20
```

Default database location:

| OS | Path |
|----|------|
| Linux / macOS | `$XDG_CACHE_HOME/faker-literature/literature_db.json` (`~/.cache/...` by default) |
| Windows | `%LOCALAPPDATA%\faker-literature\literature_db.json` |

What the importer does:

- ranks works by number of Wikipedia articles and keeps those having a French **and** an English title, an author, a date precise to the decade at least, at least one known genre and an author nationality;
- reads years as historical years (no year 0: Wikidata's 37 BC is `-37`), whereas the query service counts 1 BC as year 0;
- maps Wikidata genres onto the catalogue's genre vocabulary (*crime fiction* → *crime* / *polar*), so that a genre always has the same translation; genres missing from the vocabulary are dropped;
- localizes author names (*Evgueni Zamiatine* / *Yevgeny Zamyatin*, *Platon* / *Plato*);
- skips works already present in the bundled catalogue (same Wikidata id, or same title ignoring case, accents and a leading article, year ± 2);
- validates every record before writing anything;
- **replaces** the previously imported Wikidata books when run again (no duplicates);
- retries, with an increasing delay, when the query service is busy (HTTP 429 / 5xx, cut responses, network errors).

> It needs network access to `query.wikidata.org` and takes one to a few minutes: the first query, which lists the candidate works, alone lasts about 40 seconds, close to the 60-second limit of the service (it is retried if the service cuts it).

### Using the Enlarged Catalogue

```python
from faker import Faker
from faker_literature import LiteratureProvider, default_db_path

LiteratureProvider.use_database(default_db_path())   # or any path

fake = Faker("en_US")
fake.add_provider(LiteratureProvider)
fake.book()   # now drawn from bundled + imported books
```

`use_database()` applies to **every** provider instance in the process. Call `LiteratureProvider.use_database(None)` to go back to the bundled in-memory catalogue.

When a new version of the package ships an updated bundled catalogue, the persistent database refreshes its bundled books automatically and **keeps** imported ones, except those the bundled catalogue now contains (same rules as the importer).

Several processes can share the persistent database (for example an import running while tests generate data): every write replaces the file atomically, under a lock held through `<database>.lock`. A process keeps the books it loaded until it reopens the database. On opening, every record is validated again: a database damaged or edited by hand raises a `ValueError` naming the faulty record, instead of producing broken data. Delete the file and import your datasets again to start afresh.

### Injecting Your Own Dataset

Books are grouped by **source**. `replace_source()` replaces all the books of one source with a new list:

```python
from faker_literature import LiteratureProvider, default_db_path

store = LiteratureProvider.use_database(default_db_path())

store.replace_source("my_dataset", [
    {
        "writer": {"fr_FR": "Murasaki Shikibu", "en_US": "Murasaki Shikibu"},
        "nationality": {"fr_FR": "japonais", "en_US": "Japanese"},
        "title": {"fr_FR": "Le Dit du Genji", "en_US": "The Tale of Genji"},
        "genre": {"fr_FR": ["roman", "classique"], "en_US": ["novel", "classic"]},
        "year": 1008,
        "pages": None,
        "publisher": None,
    },
])

store.sources()   # {'builtin': 518, 'wikidata': 142, 'my_dataset': 1}
```

Record schema:

| Field | Required | Format |
|-------|----------|--------|
| `writer` | ✅ | string, or `{"fr_FR": str, "en_US": str}` |
| `nationality` | ✅ | `{"fr_FR": str, "en_US": str}` |
| `title` | ✅ | `{"fr_FR": str, "en_US": str}` |
| `genre` | ✅ | `{"fr_FR": [str, ...], "en_US": [str, ...]}` (1 to 20 genres) |
| `year` | ✅ | integer between -3000 and 2100 |
| `pages` | ❌ | `None`, or `{"fr_FR": int, "en_US": int}` (1 to 100000, each may be `None`) |
| `pages_estimated` | ❌ | `true` when `pages` is an estimate rather than the count of a known edition |
| `publisher` | ❌ | `None`, or `{"fr_FR": str, "en_US": str}` (each may be `None`) |

Strings must be non-empty and at most 300 characters. The genres of your own datasets are free: they are not checked against the bundled genre vocabulary. `wikidata_id`, when present, must be a Wikidata id such as `Q35160`. Up to 20 extra fields (e.g. `isbn`, `copies`) are stored as is: their names must be identifiers, and their values a string (300 characters at most), a number, a boolean or `None`. If **any** record is invalid, `replace_source()` raises a `ValueError` naming the record and the field, and the database is left unchanged.

> The `builtin` source is managed by the package: do not replace it yourself.

### Storage API

| Member | Description |
|--------|-------------|
| `LiteratureProvider.use_database(path=None)` | Switch every provider to the database at `path` (created if needed), or back to the in-memory catalogue. Returns the `BookStore`. |
| `default_db_path()` | Per-user cache location for the persistent database. |
| `BookStore.replace_source(source, books)` | Validate then replace the books of `source`; returns the number stored. |
| `BookStore.sources()` | Number of books per source. |
| `BookStore.books` | The underlying TinyDB table, for custom queries. |
| `provider.store` | The shared `BookStore`. |
| `provider.books` | Every book, localized for the provider's locale. |
| `provider.books_flat` | A copy of every raw (non-localized) record. |

The `provider.*` properties are not exposed on the `Faker` object (Faker only proxies methods): use a provider instance, `provider = LiteratureProvider(fake)`.

Custom TinyDB query:

```python
from tinydb import Query

store = LiteratureProvider.use_database(default_db_path())
Book = Query()
store.books.search((Book.year < 1900) & (Book.source == "wikidata"))
```

> TinyDB has no index and reads the whole file for each query: it is comfortable up to a few thousand books.

---

## 🎯 Demo

Run the built-in demo to see every feature:

```bash
faker-literature            # or: python -m faker_literature
faker-literature --version
```

Or with an enlarged catalogue:

```bash
faker-literature --db ~/.cache/faker-literature/literature_db.json demo
```

Quick tour of both locales:

```bash
python -c "
from faker import Faker
from faker_literature import LiteratureProvider

for locale in ['en_US', 'fr_FR']:
    fake = Faker(locale)
    fake.add_provider(LiteratureProvider)
    print(f'\n=== {locale} ===')
    print(f'Writer: {fake.writer()}')
    print(f'Title: {fake.title()}')
    print(f'Genre: {fake.genre()}')
    print(f'Publisher: {fake.publisher()}')
    print(f'Book: {fake.book()}')
"
```

---

## 🧪 Development

```bash
git clone https://github.com/arribo44/faker-literature.git
cd faker-literature
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"      # tests, ruff, mypy, build and twine

pytest                       # run the test suite (no network needed)
pytest --cov=faker_literature
ruff check .                 # lint
mypy                         # type check (strict)
python -m build              # build the distributions
```

The version is defined once, in `faker_literature/__init__.py` (`__version__`); the packaging metadata lives in `pyproject.toml`. GitHub Actions runs the same checks on every push and pull request: lint and type check, the test suite on Python 3.10 to 3.14 (and on Windows), then a build of the package checked with `twine check` and installed from the wheel.

Project layout:

```
faker_literature/
├── __init__.py          # LiteratureProvider
├── __main__.py          # CLI (faker-literature): demo and import-wikidata
├── store.py             # BookStore: TinyDB storage, validation, localization
├── vocabulary.py        # GenreVocabulary: one translation per genre, aliases
├── matching.py          # name/title normalization, duplicate detection
├── _storage.py          # atomic JSON storage and inter-process lock
├── importers/
│   └── wikidata.py      # Wikidata importer
└── DATAS/
    └── literature.json  # bundled catalogue: genre vocabulary + authors and books
```

---

## 🤝 Contributing

Contributions are welcome! Open a PR or issue to add authors and books to `literature.json`, write importers for new datasets (Open Library, Project Gutenberg, data.bnf.fr...), add new locales, or fix bugs.

When adding books, please provide both `fr_FR` and `en_US` values for every field, refer to genres by their id in the `genres` vocabulary at the top of `literature.json` (add a new entry there if needed), and run `pytest` before submitting: `tests/test_catalogue.py` checks the consistency of the catalogue.

---

## 📜 License

MIT License. See [LICENSE](LICENSE) for details. Imported Wikidata content is available under [CC0](https://creativecommons.org/publicdomain/zero/1.0/).
