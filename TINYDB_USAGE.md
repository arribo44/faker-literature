# TinyDB Integration & Advanced Query Methods

## Overview

The literature data has been migrated from a simple Python tuple to an optimized JSON structure with TinyDB, enabling advanced querying capabilities while reducing data redundancy.

## Data Structure

### Previous Structure (Flat)
```json
[
  {
    "writer": "Victor Hugo",
    "year": 1862,
    "genre": ["roman historique", "classique"],
    "title": {"fr_FR": "Les Misérables", "en_US": "..."},
    ...
  },
  {
    "writer": "Victor Hugo",
    "year": 1831,
    ...
  }
]
```

### Optimized Structure (By Author)
```json
{
  "authors": [
    {
      "name": "Victor Hugo",
      "books": [
        {
          "year": 1862,
          "genre": {
            "fr_FR": ["roman historique", "classique"],
            "en_US": ["historical novel", "classic"]
          },
          "title": {"fr_FR": "Les Misérables", "en_US": "Les Misérables"},
          "pages": {"fr_FR": 1463, "en_US": 1463},
          "publisher": {"fr_FR": "...", "en_US": "..."}
        },
        ...
      ]
    },
    ...
  ]
}
```

## Benefits

✅ **Reduced Redundancy** - Author name appears once per author instead of once per book  
✅ **Better Organization** - Data grouped logically by author  
✅ **Faster Queries** - TinyDB enables efficient filtering and searching  
✅ **Advanced Methods** - Built-in query methods for complex data retrieval

## Advanced Query Methods

### 1. Query Books by Author
```python
from faker import Faker
from faker_literature import LiteratureProvider

fake = Faker('fr_FR')
fake.add_provider(LiteratureProvider)
provider = LiteratureProvider(fake)

# Get all books by Victor Hugo
hugo_books = provider.books_by_author("Victor Hugo")
for book in hugo_books:
    print(f"{book['title']} ({book['year']})")
```

### 2. Query Books by Genre
```python
# Get all books in the 'fantasy' genre
fantasy_books = provider.books_by_genre("fantasy")
for book in fantasy_books:
    print(f"{book['title']} by {book['writer']}")
```

### 3. Query Books by Year
```python
# Get all books published in 1862
books_1862 = provider.books_by_year(1862)
for book in books_1862:
    print(f"{book['title']} by {book['writer']}")
```

### 4. Query Books by Year Range
```python
# Get all books published between 2000-2010
books_range = provider.books_by_year_range(2000, 2010)
for book in books_range:
    print(f"{book['title']} ({book['year']})")
```

### 5. Get All Authors
```python
# Get a sorted list of all unique authors
all_authors = provider.all_authors()
print(f"Total authors: {len(all_authors)}")
print(f"First 10: {all_authors[:10]}")
```

### 6. Get All Genres
```python
# Get a sorted list of all unique genres
all_genres = provider.all_genres()
print(f"Total genres: {len(all_genres)}")
print(f"First 15: {all_genres[:15]}")
```

## Data Storage

### Locations
- **Source Data**: `DATAS/literature.json` - bundled catalogue, read-only
- **Default store**: in memory (`tinydb.storages.MemoryStorage`), nothing is written to disk
- **Persistent store** (optional): any path passed to `LiteratureProvider.use_database()`, typically `default_db_path()` (`~/.cache/faker-literature/literature_db.json` on Linux, `%LOCALAPPDATA%\faker-literature\` on Windows)

### Bundled catalogue
- `literature.json`: ~270 KB (12,000 lines)
- 164 authors, 425 books, ~200 unique genres per locale

### Sources
Every record carries a `source` field (`builtin`, `wikidata`, ...).
`BookStore.replace_source(source, books)` validates all the records first, then
replaces the books of that source only. A persistent store records the SHA-256
of `literature.json` and re-syncs the `builtin` books when it changes, keeping
imported books.

Text fields (`writer`, `nationality`, `title`, `publisher`) may be a plain string
or a `{"fr_FR": ..., "en_US": ...}` mapping; `pages` and `publisher` may be `null`.

## Backward Compatibility

All original Faker methods are preserved and work exactly as before:

```python
fake.book()              # Return a random book
fake.writer()            # Return a random writer
fake.author()            # Alias for writer()
fake.title()             # Return a random title
fake.genre()             # Return a random genre
fake.publication_year()  # Return a random year
fake.pages()             # Return a random page count
fake.publisher()         # Return a random publisher
fake.literary_work()     # Alias for book()
```

## Implementation Details

### Lazy Initialization
The shared `BookStore` is created on first use by `LiteratureProvider._get_store()`
and reused by every provider instance.

### Caching
Generation methods draw from a localized snapshot of the catalogue, built once
per locale and invalidated whenever a source is replaced. Query methods
(`books_by_*`) go through TinyDB.

### Locale Support
All methods respect the configured locale (fr_FR or en_US) for:
- Titles
- Publishers
- Page counts
- **Genres** ✨ (Now fully localized with proper translations)

## Genre Localization

Genres are now fully localized per locale, just like titles and publishers:

```python
from faker import Faker
from faker_literature import LiteratureProvider

# French locale - genres in French
fake_fr = Faker('fr_FR')
fake_fr.add_provider(LiteratureProvider)
print(fake_fr.genre())  # E.g., "philosophique", "drame romantique"
print(fake_fr.all_genres()[:5])  # ['adolescence', 'amitié', 'américain', 'anthologie', 'anthropologie']

# English locale - genres in English
fake_en = Faker('en_US')
fake_en.add_provider(LiteratureProvider)
print(fake_en.genre())  # E.g., "philosophical", "romantic drama"
print(fake_en.all_genres()[:5])  # ['absurd novel', 'adolescence', 'adventure', 'adventure novel', 'adventures']

# Books return localized genres
book_fr = fake_fr.book()
print(book_fr['genre'])  # ['genre1_fr', 'genre2_fr']

book_en = fake_en.book()
print(book_en['genre'])  # ['genre1_en', 'genre2_en']
```

All 425 bundled books have genre lists for both fr_FR and en_US locales.

## Requirements

```
tinydb>=4.0.0
faker>=20.0.0
```

Install with:
```bash
pip install tinydb faker
```

## Query Performance

TinyDB has no index: every `books_by_*()` query scans all the records, and a
file-backed store re-reads the whole JSON file on each query. This is fine for
a few thousand books; beyond that, a SQLite-backed store would be preferable.
