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
| Authors | 1,006 |
| Books | 2,255 |
| Genres | 220 per locale |
| Nationalities | 56 |
| Publishers | 520 |
| Literary awards | 84 |
| Series | 266 |
| Years covered | 800 BC → 2024 |

Classics, philosophy, crime fiction, science fiction, fantasy, horror, poetry, drama, essays and contemporary novels by French, American, British, Italian, Greek, Roman, Russian, German, Japanese, Latin-American writers, and more. 422 books were entered by hand; the others come from Wikidata, most of them picked among the most rated books of a Goodreads export (see [tools/goodreads_import](tools/goodreads_import/README.md)). Writers from English-speaking countries account for about three quarters of the books; 638 works never translated into French keep their original title in both locales (`"title_untranslated": true` in their raw record).

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

> **About page counts and publishers.** The 422 books entered by hand have a page count that *estimates* the usual length of the work in each language (French editions are often a little longer), and a plausible publisher (often the first or a common one) that was not checked against a source. These values are realistic enough for test data but do not describe a specific edition, and the page count and the publisher of a book may come from different editions: their raw records carry `"pages_estimated": true` and `"publisher_estimated": true` (see `provider.books_flat`). The other books carry the page count and publisher of a real edition in each locale's language: an English or French edition found on Wikidata, the edition described by the infobox of the work's Wikipedia article (the French translation in the French article, the original edition of an English work in the English one), or else, in French, the edition of the usual French publisher of the work in the general catalogue of the [Bibliothèque nationale de France](https://catalogue.bnf.fr/). A value that no source gives is `None`.

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

`writer_profile()` describes a writer: life, nationality, books and main genres. Pass a name, or the filters of `writer()` to draw one:

```python
fake.writer_profile("victor hugo")
# {'name': 'Victor Hugo', 'nationality': 'French', 'born': 1802, 'died': 1885,
#  'books': [{'title': "Han d'Islande", 'year': 1823}, ..., {'title': 'Ninety-Three', 'year': 1874}],
#  'genres': ['historical novel', 'novel', 'poetry', 'lyrical', 'romantic drama']}

fake.writer_profile(nationality="Japanese")   # a Japanese writer's profile
```

`born` and `died` come from Wikidata (negative for BC); `died` is `None` for living writers, and both are `None` when unknown. The catalogue is checked against them: no book is published before its author is 12, nor more than 60 years after their death.

If no writer matches the filters, a `ValueError` is raised:

```python
fake.writer(nationality="American", genre="nope")
# ValueError: No writer found for genre='nope', nationality='American'
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

Each of these methods is an **independent** random draw from the catalogue. Use `book()` when the values must belong together. Genres, years, page counts and publishers are drawn in proportion to their number of books. In `fr_FR`, `publisher()` leaves out the works never translated into French, whose publisher is that of their original, foreign edition, unless the filters leave no other publisher.

The values are drawn from pools computed once per locale and kept until the catalogue changes, so generating large datasets stays fast (a few microseconds per value).

---

### 🎯 Filtering Every Draw

`book()`, `title()`, `writer()`, `genre()`, `publication_year()`, `pages()`, `publisher()`, `books_sample()`, `edition()` and `citation()` accept the same filters, combined with "and":

| Filter | Meaning |
|--------|---------|
| `genre` | one of the book's genres (current locale, case-insensitive) |
| `nationality` | the author's nationality (current locale, case-insensitive), or `"*"` for any |
| `author` | the author or a co-author, ignoring case, accents and punctuation |
| `after`, `before` | first published in or after / before or in that year (negative for BC) |
| `century` | first published in that century: `19` for 1801-1900, `-5` for 500-401 BC |
| `award` | a literary award the work received, by part of its name (`"goncourt"`, `"hugo"`), or `"*"` for any |
| `series` | a series the work belongs to, by part of its name (`"rougon"`, `"discworld"`), or `"*"` for any |
| `popular` | `True` to draw well-known books more often (see below) |

```python
fake.book(nationality="French", century=19)       # Balzac, Hugo, Zola, Flaubert...
fake.title(genre="science fiction", after=2000)   # "The Yiddish Policemen's Union"
fake.publisher(nationality="Japanese")            # "Chūōkōron Shinsha"
fake.publication_year(author="Agatha Christie")   # 1926
fake_fr.book(genre="tragédie", before=-400)       # Eschyle, Sophocle, Euripide
```

Only `writer()` filters by default, on the locale's nationality (see above). When no book matches, a `ValueError` names the filters.

#### ⭐ Popular books

By default every book of the catalogue has the same chance, so a well-known book is as frequent as an obscure one. With `popular=True`, books are weighted by their **popularity**, their number of Wikipedia articles (*Don Quixote* has more than 100, a recent thriller a handful), squared: the best known tenth of the catalogue then makes about three quarters of the draws.

```python
fake.title(popular=True)                    # "Pride and Prejudice", "The Iliad", "Fahrenheit 451"...
fake.writer(nationality="*", popular=True)  # "Leo Tolstoy", "Honoré de Balzac"...
```

Your own datasets may give their books a `popularity` (a positive integer); books without one count as the median popularity of the catalogue.

#### 🎲 Distinct books

`fake.unique.book()` cannot work, a book being a dictionary. `books_sample()` draws books **without replacement**:

```python
fake.books_sample(20)                                      # 20 different books
fake.books_sample(5, nationality="Russian", popular=True)  # 5 well-known Russian books
```

---

### 🏆 Literary Awards

186 works of the catalogue received one of 84 literary awards (Hugo, Pulitzer, Nebula, Booker, Goncourt, Newbery, Femina...), as recorded by Wikidata:

```python
fake.award()                                  # "Hugo Award for Best Novel"
fake_fr.award(nationality="français")         # "prix Goncourt"
fake.book(award="booker")                     # a Booker Prize winner
fake.title(award="*", century=20)             # any awarded 20th-century work
fake.books_by_award("Pulitzer Prize for Fiction")
fake.all_awards()                             # the 84 awards, sorted, localized
fake.writer_profile("Ursula K. Le Guin")["awards"]
# ['Hugo Award for Best Novel', 'Locus Award for Best Fantasy Novel', ...]
```

The `award` filter matches part of the name, case-insensitively: `"goncourt"` also finds the *Goncourt des lycéens*. Awards are not part of `book()`'s record.

---

### 📚 Series

504 works of the catalogue belong to one of 266 series or cycles, as recorded by Wikidata (130 of them have at least two books in the catalogue): *Les Rougon-Macquart*, *La Comédie humaine*, *Harry Potter*, *Discworld*, *Foundation*... Series of novels about a recurring character (*Maigret*, *Hercule Poirot*, *Jack Reacher*) count as series.

```python
fake.series()                                  # "The Chronicles of Narnia"
fake_fr.series(nationality="français")         # "Les Rougon-Macquart"
fake.book(series="discworld")                  # a Discworld novel
fake.title(series="*", century=19)             # any 19th-century work that belongs to a series
fake.all_series()                              # the 266 series, sorted, localized

fake.books_in_series("Foundation Trilogy")     # the books in reading order, with their rank
# [{'title': 'Foundation', ..., 'position': 1},
#  {'title': 'Foundation and Empire', ..., 'position': 2},
#  {'title': 'Second Foundation', ..., 'position': 3}]

fake.writer_profile("Terry Pratchett")["series"]
# ['Discworld', 'Rincewind', 'Witches']
```

`books_in_series()` takes the name of a series, ignoring case, accents and punctuation, or a part of it that names a single series (`"rougon"`); it raises a `ValueError` when the name matches no series or several. Books are ordered by their rank in the series (`position`, known for two thirds of them), then by year; `position` is `None` when Wikidata does not give the rank.

The `series` filter matches part of the name, case-insensitively. Series are not part of `book()`'s record. When Wikidata has no French name for a series, the French locale uses the English one without its descriptive words (*Wallander novels* → *Wallander*), like the titles of untranslated works.

---

### 📕 Editions

`edition()` turns a catalogue work into a coherent **edition**, ready for a bookshop or a library database:

```python
fake_fr.edition()
# {'writer': 'Baruch Spinoza', 'nationality': 'néerlandais', 'title': 'Traité théologico-politique',
#  'genre': ['traité'], 'year': 1670,
#  'publisher': 'Gallimard', 'edition_year': 1989, 'format': 'poche', 'pages': 331,
#  'price': 11.7, 'currency': 'EUR', 'isbn': '978-2-1748-4121-4'}
```

- `edition_year` lies between the first publication (1950 for older works) and the current year;
- `format` is pocket, paperback or hardcover, in the locale's language, and changes the page count (more pages in pocket) and the price range;
- `publisher` is the work's own publisher, or a publisher of the locale's writers (French publishers for a French edition);
- `isbn` is a valid ISBN-13 (French group `2`, English groups `0` and `1`) whose prefix belongs to the publisher: two editions from the same publisher share it.

It accepts the filters above: `fake.edition(author="Jules Verne", popular=True)`.

---

### 📝 Citations

`citation()` formats the bibliographic reference of a book in the **APA**, **MLA** or **Chicago** style (plain text, titles not italicized):

```python
fake.citation("apa", author="J.R.R. Tolkien")
# 'Tolkien, J. R. R. (1954). The Fellowship of the Ring.'
fake.citation("chicago", genre="novel")
# 'Hugo, Victor. Les Misérables. A. Lacroix, Verboeckhoven & Cie, 1862.'
fake_fr.citation("mla", book=fake_fr.book())
# 'Balzac, Honoré de. Le Père Goriot. Edmond Werdet, 1835.'
```

Names are inverted ("Balzac, Honoré de"), abbreviated in APA ("Sartre, J.-P."), co-authors are joined with "&" / "and" (or "et" in French), and years BC read "800 BC" / "800 av. J.-C.". The surname is the last word of the name: compound Spanish surnames ("Reinaldo Arenas Fuentes") come out as "Fuentes, Reinaldo Arenas".

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
fake.books_by_genre("horror")           # 92 books
fake_fr.books_by_genre("roman policier")

# All books published in a year, or within a range (inclusive)
fake.books_by_year(1862)                # [{'writer': 'Victor Hugo', 'title': 'Les Misérables', ...}]
fake.books_by_year_range(1940, 1960)    # 189 books
fake.books_by_year_range(-500, 0)       # Ancient Greek works
```

Catalogue overview:

```python
fake.all_authors()        # ['A. A. Milne', 'A. S. Byatt', ...]  (sorted; co-authors listed separately)
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

- ranks works by number of Wikipedia articles and keeps those having a French **and** an English title, an author, a date precise to the decade at least, at least one known genre (or, failing that, a known form: novel, play...) and an author nationality;
- reads years as historical years (no year 0: Wikidata's 37 BC is `-37`), whereas the query service counts 1 BC as year 0;
- maps Wikidata genres onto the catalogue's genre vocabulary (*crime fiction* → *crime* / *polar*), so that a genre always has the same translation; genres missing from the vocabulary are dropped;
- localizes author names (*Evgueni Zamiatine* / *Yevgeny Zamyatin*, *Platon* / *Plato*);
- picks, for an author with several citizenships, the one of their country of birth (P. G. Wodehouse is British), and reuses the translations of the catalogue's nationalities (*British* is always *britannique*); an author already in the catalogue keeps their nationality;
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

store.sources()   # {'builtin': 2255, 'wikidata': 142, 'my_dataset': 1}
```

Record schema:

| Field | Required | Format |
|-------|----------|--------|
| `writer` | ✅ | string, or `{"fr_FR": str, "en_US": str}` |
| `nationality` | ✅ | `{"fr_FR": str, "en_US": str}` |
| `title` | ✅ | `{"fr_FR": str, "en_US": str}` |
| `title_untranslated` | ❌ | `true` when the work was never translated into French: both titles are the original one |
| `writer_born`, `writer_died` | ❌ | years of birth and death of the author (negative for BC), used by `writer_profile()` |
| `popularity` | ❌ | how well known the work is (a positive integer), used by `popular=True` |
| `awards` | ❌ | `{"fr_FR": [str, ...], "en_US": [str, ...]}`: literary awards received by the work |
| `series` | ❌ | `[{"name": {"fr_FR": str, "en_US": str}, "position": int}, ...]` (0 to 5 series): the series the work belongs to, with its rank (optional, 1 to 10000) |
| `genre` | ✅ | `{"fr_FR": [str, ...], "en_US": [str, ...]}` (1 to 20 genres) |
| `year` | ✅ | integer between -3000 and 2100 |
| `pages` | ❌ | `None`, or `{"fr_FR": int, "en_US": int}` (1 to 100000, each may be `None`) |
| `pages_estimated` | ❌ | `true` when `pages` is an estimate rather than the count of a known edition |
| `publisher` | ❌ | `None`, or `{"fr_FR": str, "en_US": str}` (each may be `None`) |
| `publisher_estimated` | ❌ | `true` when `publisher` is plausible but was not checked against a source |

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

Releasing a version:

1. set `__version__` in `faker_literature/__init__.py` and date its section in `CHANGELOG.md` (`## [X.Y.Z] - YYYY-MM-DD`);
2. merge into `main`, then tag and push: `git tag -a vX.Y.Z -m "Release faker-literature X.Y.Z" && git push origin vX.Y.Z`.

The `Release` workflow then tests and builds the package, checks that the tag matches the version and the changelog, publishes it on PyPI through [Trusted Publishing](https://docs.pypi.org/trusted-publishers/) (no API token stored), and creates the GitHub release with the changelog section as notes. Running the workflow by hand (*Actions → Release → Run workflow*) publishes on TestPyPI instead, as a dry run.

Project layout:

```
faker_literature/
├── __init__.py          # LiteratureProvider
├── citation.py          # APA, MLA and Chicago references
├── edition.py           # edition formats, prices and ISBN-13
├── __main__.py          # CLI (faker-literature): demo and import-wikidata
├── store.py             # BookStore: TinyDB storage, validation, localization
├── vocabulary.py        # GenreVocabulary and PublisherVocabulary: one name per genre or publisher, aliases
├── matching.py          # name/title normalization, duplicate detection
├── _storage.py          # atomic JSON storage and inter-process lock
├── importers/
│   └── wikidata.py      # Wikidata importer
└── DATAS/
    └── literature.json  # bundled catalogue: genre, award, series and publisher vocabularies + authors and books
tools/
├── literature_editor/   # local web page to add books to literature.json from Wikidata
└── goodreads_import/    # adds the works of a Goodreads export to literature.json, through Wikidata
```

---

## 🤝 Contributing

Contributions are welcome! Open a PR or issue to add authors and books to `literature.json`, write importers for new datasets (Open Library, Project Gutenberg, data.bnf.fr...), add new locales, or fix bugs.

When adding books, please provide both `fr_FR` and `en_US` values for every field, refer to genres and publishers by their id in the `genres` and `publishers` vocabularies at the top of `literature.json` (add a new entry there if needed, or an alias when the publisher is already there under another name), and run `pytest` before submitting: `tests/test_catalogue.py` checks the consistency of the catalogue.

---

## 📜 License

MIT License. See [LICENSE](LICENSE) for details. Imported Wikidata content is available under [CC0](https://creativecommons.org/publicdomain/zero/1.0/).

French page counts and publishers taken from the general catalogue of the Bibliothèque nationale de France: source *Bibliothèque nationale de France, catalogue général* ([catalogue.bnf.fr](https://catalogue.bnf.fr/)), reused under the [Licence Ouverte / Open Licence 2.0](https://www.etalab.gouv.fr/licence-ouverte-open-licence/) (Etalab). Only bibliographic facts are reused (publisher and number of pages of an edition).

Some page counts and publishers come from the infoboxes of [Wikipedia](https://www.wikipedia.org/) articles (French and English): bibliographic facts only, no text of the articles.
