"""Add the books of a Goodreads export to the bundled catalogue, through Wikidata.

The export (``books.csv``: title, authors, ratings count...) only gives
English titles, edition dates and no genre or nationality.  It is used as a
list of works to look up: each book is searched on Wikidata by title, kept
when one of its authors matches, and the work found (an edition leads to the
work it belongs to) gives the French and English titles, the original year,
the genres, the nationality, the page count and the publisher, all CC0.
Nothing else comes from the export.

Usage::

    python tools/goodreads_import/import_goodreads.py data/goodreads/books.csv

The searches and the Wikidata answers are cached next to the export
(``<export>.cache.json``): an interrupted import resumes where it stopped.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "literature_editor"))

import editor

from faker_literature.importers.wikidata import (
    DATES_PATTERN,
    DETAILS_QUERY,
    USER_AGENT,
    _entity_id,
    known_nationalities,
    parse_bindings,
    run_query,
)
from faker_literature.matching import YEAR_TOLERANCE, DuplicateIndex, name_key, title_key
from faker_literature.vocabulary import GenreVocabulary

SEARCH_API = "https://www.wikidata.org/w/api.php"
SEARCH_RESULTS = 5
BATCH_SIZE = 40
PAUSE = 1.0
SEARCH_PAUSE = 0.2

# Books rated by fewer readers are rarely on Wikidata
MIN_RATINGS = 1000
# At most this many books per author in the catalogue, so that prolific authors do not dominate the draws
MAX_PER_AUTHOR = 5
# Books looked up per author: some are not found on Wikidata
LOOKUPS_PER_AUTHOR = 2 * MAX_PER_AUTHOR

# Box sets, omnibus editions, reading guides and the like are not works
NOT_A_WORK = re.compile(
    r"box(ed)? set|collection|omnibus|complete|companion|guide|cliffsnotes|sparknotes|study|vol\.|volume|"
    r"#\d+-\d+|books? \d+-\d+|anthology|selected|treasury|trilogy|quartet|reader",
    re.IGNORECASE,
)

# Wikidata genres missing from the vocabulary, mapped onto a known genre: {id: (French, English aliases)}
GENRE_ALIASES = {
    "chivalric": (["roman de chevalerie"], ["chivalric romance"]),
    "children-s-literature": (
        ["livre pour enfants", "fiction pour enfants"], ["children's book", "children's fiction"]),
    "crime": (["littérature policière"], ["crime literature"]),
    "dystopian": (["fiction dystopique"], ["dystopian fiction"]),
    "epic-poetry": (["poème épique"], ["epic poem"]),
    "feminist": (["littérature féministe"], ["feminist literature"]),
    "historical-novel": (["fiction historique"], ["historical fiction"]),
    "noir": (["hardboiled"], ["hardboiled"]),
    "philosophical-novel": (["fiction philosophique"], ["philosophical fiction"]),
    "theater": (["pièce de théâtre"], ["play"]),
    "travel": (["littérature de voyage"], ["travel literature"]),
}
# Genres added to the vocabulary, kept only when a book uses them
NEW_GENRES = {
    "alternate-history": {"fr_FR": "uchronie", "en_US": "alternate history"},
    "high-fantasy": {"fr_FR": "high fantasy", "en_US": "high fantasy"},
    "non-fiction": {"fr_FR": "non-fiction", "en_US": "non-fiction",
                    "aliases": {"fr_FR": ["littérature non-fictionnelle"], "en_US": ["non-fiction literature"]}},
    "novella": {"fr_FR": "novella", "en_US": "novella", "aliases": {"fr_FR": ["court roman"]}},
    "science-fantasy": {"fr_FR": "science fantasy", "en_US": "science fantasy"},
    "short-story-collection": {"fr_FR": "recueil de nouvelles", "en_US": "short story collection"},
    "young-adult": {"fr_FR": "jeunes adultes", "en_US": "young adult",
                    "aliases": {"fr_FR": ["littérature pour jeunes adultes", "fiction Young Adult"],
                                "en_US": ["young adult literature", "young adult fiction"]}},
}

# Items found by the search, or the work they are an edition of, with the names of their authors
AUTHORS_QUERY = """
SELECT ?item ?work ?author ?name WHERE {
  VALUES ?item { %s }
  { ?item wdt:P50 ?author . BIND(?item AS ?work) }
  UNION { ?item wdt:P629 ?work . ?work wdt:P50 ?author . }
  { ?author rdfs:label ?name . FILTER(LANG(?name) IN ("en", "mul", "fr")) }
  UNION { ?author skos:altLabel ?name . FILTER(LANG(?name) IN ("en", "mul")) }
}
"""


# Reading the export

def clean_title(title: str) -> str:
    """Drop the series ("(Harry Potter  #6)") and the subtitle of a Goodreads title."""
    title = re.sub(r"\s*\([^)]*\)\s*$", "", title)
    title = title.split(":")[0]
    return re.sub(r"\s+", " ", title).strip()


def read_candidates(path, min_ratings=MIN_RATINGS, per_author=LOOKUPS_PER_AUTHOR):
    """Return the works of the export worth looking up, most rated first.

    Rows broken by a comma in an author name, books with few ratings, box
    sets and guides are left out; the editions of a work are merged; at most
    ``per_author`` works are kept per (first) author.
    """
    with open(path, encoding="utf-8", newline="") as file:
        rows = csv.reader(file)
        header = [column.strip() for column in next(rows)]
        books = [dict(zip(header, row, strict=True)) for row in rows if len(row) == len(header)]
    works = {}
    for book in books:
        ratings = int(book["ratings_count"]) if book["ratings_count"].isdigit() else 0
        if ratings < min_ratings or NOT_A_WORK.search(book["title"]):
            continue
        title = clean_title(book["title"])
        authors = [author.strip() for author in book["authors"].split("/") if author.strip()]
        if not (title and authors):
            continue
        key = (name_key(authors[0]), title_key(title))
        if key not in works or ratings > works[key]["ratings"]:
            works[key] = {"id": book["bookID"], "title": title, "authors": authors, "ratings": ratings}
    ranked = sorted(works.values(), key=lambda work: -work["ratings"])
    counts = Counter()
    selected = []
    for work in ranked:
        author = name_key(work["authors"][0])
        if counts[author] < per_author:
            counts[author] += 1
            selected.append(work)
    return selected


# Looking the works up

def search(title):
    """Return the items whose label matches ``title`` and that have an author (P50)."""
    params = {"action": "query", "list": "search", "srsearch": f"{title} haswbstatement:P50",
              "srlimit": SEARCH_RESULTS, "srnamespace": 0, "format": "json"}
    request = urllib.request.Request(f"{SEARCH_API}?{urllib.parse.urlencode(params)}",
                                     headers={"User-Agent": USER_AGENT})
    for attempt in range(1, 5):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.load(response)
            # A busy API answers {"error": {...}} with HTTP 200
            if "query" not in payload:
                raise ValueError(f"Wikidata search failed: {payload.get('error', payload)}")
            return [hit["title"] for hit in payload["query"]["search"]]
        except (OSError, ValueError):
            if attempt == 4:
                raise
            time.sleep(2 ** attempt)
    return []


def parse_authors(rows):
    """Return ``{item: (work, {author: {name keys}})}`` from the rows of ``AUTHORS_QUERY``."""
    items = {}
    for row in rows:
        item = _entity_id(row["item"]["value"])
        work, authors = items.setdefault(item, (_entity_id(row["work"]["value"]), {}))
        authors.setdefault(_entity_id(row["author"]["value"]), set()).add(name_key(row["name"]["value"]))
    return items


def match_work(book, hits, items):
    """Return ``(work, author)`` for the first search hit written by one of the book's authors."""
    wanted = {name_key(author) for author in book["authors"]}
    for item in hits:
        work, authors = items.get(item, (None, {}))
        for author, names in authors.items():
            if names & wanted:
                return work, author
    return None


# Writing the catalogue

def extend_vocabulary(genres):
    """Add ``GENRE_ALIASES`` and ``NEW_GENRES`` to ``genres`` in place; return the ids added."""
    for genre_id, (fr, en) in GENRE_ALIASES.items():
        aliases = genres[genre_id].setdefault("aliases", {})
        for locale, labels in (("fr_FR", fr), ("en_US", en)):
            known = aliases.setdefault(locale, [])
            known.extend(label for label in labels if label not in known)
    added = [genre_id for genre_id in NEW_GENRES if genre_id not in genres]
    for genre_id in added:
        genres[genre_id] = json.loads(json.dumps(NEW_GENRES[genre_id]))
    GenreVocabulary(genres)  # raises if a label is now ambiguous
    return added


def drop_unused_genres(data, genre_ids):
    """Remove the genres of ``genre_ids`` that no book uses."""
    used = {genre for author in data["authors"] for book in author["books"] for genre in book["genre"]}
    for genre_id in genre_ids:
        if genre_id not in used:
            del data["genres"][genre_id]


def _flag_untranslated(entry, wikidata_id):
    """Add ``"title_untranslated": true`` right after the title of the book ``wikidata_id``."""
    books = entry["books"]
    index = next(i for i, book in enumerate(books) if book.get("wikidata_id") == wikidata_id)
    flagged = {}
    for key, value in books[index].items():
        flagged[key] = value
        if key == "title":
            flagged["title_untranslated"] = True
    books[index] = flagged


def add_records(data, records, authors, max_per_author=MAX_PER_AUTHOR, log=print):
    """Add ``records`` to the catalogue ``data`` in order and return the reasons of the skipped ones.

    ``authors`` maps each work to its author's Wikidata id.  Works with
    several authors, works already in the catalogue (same Wikidata id, or
    same title within a few years) and books beyond ``max_per_author`` are
    skipped.  An author already in the catalogue keeps its name and
    nationality.
    """
    known_ids = {book.get("wikidata_id") for author in data["authors"] for book in author["books"]}
    index = DuplicateIndex([book for author in data["authors"] for book in author["books"]],
                           year_tolerance=YEAR_TOLERANCE)
    skipped = Counter()
    for record in records:
        writer = record["writer"]
        if ", " in writer["en_US"] or ", " in writer["fr_FR"]:
            skipped["several authors"] += 1
            continue
        if record["wikidata_id"] in known_ids or record in index:
            skipped["already in the catalogue"] += 1
            continue
        author_id = authors[record["wikidata_id"]]
        entry = editor.find_author(data, author_id, writer.values())
        if entry is not None and len(entry["books"]) >= max_per_author:
            skipped["author already has enough books"] += 1
            continue
        raw_author = {"wikidata_id": author_id, "name": writer, "nationality": record["nationality"]}
        raw_book = {key: record[key] for key in ("wikidata_id", "title", "year", "genre")}
        raw_book["pages"] = record["pages"] or {}
        raw_book["publisher"] = record["publisher"] or {}
        try:
            editor.add_book(data, raw_author, raw_book)
        except ValueError as error:
            skipped["refused by the editor"] += 1
            log(f"  {record['wikidata_id']} {writer['en_US']} / {record['title']['en_US']}: {error}")
            continue
        if record.get("title_untranslated"):
            _flag_untranslated(editor.find_author(data, author_id, writer.values()), record["wikidata_id"])
        known_ids.add(record["wikidata_id"])
    return skipped


# Running the import

class Cache:
    """The searches and Wikidata answers of an import, saved after each step."""

    def __init__(self, path):
        self.path = Path(path)
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {}
        for key in ("search", "authors", "details"):
            self.data.setdefault(key, {})

    def save(self):
        self.path.write_text(json.dumps(self.data, ensure_ascii=False))

    def __getitem__(self, key):
        return self.data[key]


def _batches(values, size=BATCH_SIZE):
    for start in range(0, len(values), size):
        yield values[start:start + size]


def lookup(candidates, cache, log=print):
    """Search, check the authors and fetch the details; return ``(rows, {work: author}, ordered works)``."""
    for count, book in enumerate(candidates, 1):
        if book["id"] not in cache["search"]:
            cache["search"][book["id"]] = search(book["title"])
            time.sleep(SEARCH_PAUSE)
            if count % 100 == 0:
                cache.save()
                log(f"  {count}/{len(candidates)} searched")
    cache.save()

    items = sorted({item for book in candidates for item in cache["search"][book["id"]]} - set(cache["authors"]))
    for batch in _batches(items):
        rows = run_query(AUTHORS_QUERY % " ".join("wd:" + item for item in batch))
        found = parse_authors(rows)
        for item in batch:
            work, names = found.get(item, (None, {}))
            cache["authors"][item] = [work, {author: sorted(keys) for author, keys in names.items()}]
        cache.save()
        time.sleep(PAUSE)
    items = {item: (work, {author: set(keys) for author, keys in names.items()})
             for item, (work, names) in cache["authors"].items()}

    authors, ordered = {}, []
    for book in candidates:
        match = match_work(book, cache["search"][book["id"]], items)
        if match and match[0] not in authors:
            authors[match[0]] = match[1]
            ordered.append(match[0])
    log(f"{len(ordered)} works matched on Wikidata out of {len(candidates)} books")

    missing = [work for work in ordered if work not in cache["details"]]
    for batch in _batches(missing):
        rows = run_query(DETAILS_QUERY % {"works": " ".join("wd:" + work for work in batch), "dates": DATES_PATTERN})
        by_work = {work: [] for work in batch}
        for row in rows:
            by_work[_entity_id(row["work"]["value"])].append(row)
        cache["details"].update(by_work)
        cache.save()
        time.sleep(PAUSE)
    return authors, ordered


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("export", type=Path, help="the Goodreads books.csv")
    parser.add_argument("--catalogue", type=Path, default=editor.CATALOGUE_PATH)
    parser.add_argument("--limit", type=int, help="look up the first LIMIT works only (most rated first)")
    parser.add_argument("--max-per-author", type=int, default=MAX_PER_AUTHOR)
    parser.add_argument("--min-ratings", type=int, default=MIN_RATINGS)
    parser.add_argument("--dry-run", action="store_true", help="report without writing the catalogue")
    args = parser.parse_args(argv)

    candidates = read_candidates(args.export, args.min_ratings, 2 * args.max_per_author)[:args.limit]
    print(f"{len(candidates)} works to look up")
    cache = Cache(args.export.with_name(args.export.name + ".cache.json"))
    authors, ordered = lookup(candidates, cache)

    data = editor.load_catalogue(args.catalogue)
    added_genres = extend_vocabulary(data["genres"])
    vocabulary = GenreVocabulary(data["genres"])
    nationalities = known_nationalities()
    records = []
    for work in ordered:
        records += parse_bindings(cache["details"][work], vocabulary, nationalities, untranslated_titles=True)
    print(f"{len(records)} works with a known genre, a nationality and a year")

    before = sum(len(author["books"]) for author in data["authors"])
    skipped = add_records(data, records, authors, args.max_per_author)
    drop_unused_genres(data, added_genres)
    added = sum(len(author["books"]) for author in data["authors"]) - before
    print(f"{added} books added; skipped: {dict(skipped)}")
    print(f"new genres used: {sorted(set(added_genres) & set(data['genres']))}")
    if not args.dry_run:
        editor.save_catalogue(data, args.catalogue)
        print(f"catalogue written to {args.catalogue}")


if __name__ == "__main__":
    main()
