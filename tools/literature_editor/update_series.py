"""Fill the series of the bundled books from Wikidata.

Every book with a ``wikidata_id`` gets the series (P179) its work belongs to,
with its rank in the series (P1545 qualifier) when Wikidata gives one, as ids
of the ``series`` vocabulary at the top of the catalogue: ``{"Q6027":
{"fr_FR": "Les Rougon-Macquart", "en_US": "Les Rougon-Macquart"}}``.

Wikidata also files under P179 editorial collections, magazines, film
franchises or television series: only the items that are a series or a cycle
of books, or a recurring character (Maigret, Adam Dalgliesh: the series of
novels about them), are kept.  Series names fall back on the multilingual
label (``mul``), then on the other language.

Usage::

    python tools/literature_editor/update_series.py [--dry-run]
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import editor

from faker_literature.importers.wikidata import _entity_id, run_query

BATCH_SIZE = 100
PAUSE = 1.0
MAX_POSITION = 10000

SERIES_QUERY = """
SELECT ?work ?series ?position ?fr ?en ?mul ?type WHERE {
  VALUES ?work { %s }
  ?work p:P179 ?statement .
  ?statement ps:P179 ?series ; wikibase:rank ?rank .
  FILTER(?rank != wikibase:DeprecatedRank)
  OPTIONAL { ?statement pq:P1545 ?position }
  OPTIONAL { ?series rdfs:label ?fr . FILTER(LANG(?fr) = "fr") }
  OPTIONAL { ?series rdfs:label ?en . FILTER(LANG(?en) = "en") }
  OPTIONAL { ?series rdfs:label ?mul . FILTER(LANG(?mul) = "mul") }
  OPTIONAL { ?series wdt:P31 ?class . ?class rdfs:label ?type . FILTER(LANG(?type) = "en") }
}
"""

# English labels of the classes (P31) of a series of books: "novel series", "literary trilogy"...
SERIES_TYPE = re.compile(
    r"\b(series|sequence|cycle|saga|long-series books"
    r"|(?:di|dy|du|tri|tetra|penta|hexa|hepta|octa|ennea|deca)log(?:y|ies))\b")
# ... and of a recurring character, whose novels make a series
CHARACTER_TYPE = re.compile(r"\b(character|fictional human)\b")
# Series and characters of something else than books
NOT_BOOKS = re.compile(r"\b(television|tv|film|comic|anime|manga|video game|podcast)\b")


def is_book_series(types):
    """Tell whether an item with these English class labels is a series of books (or a recurring character)."""
    return any((SERIES_TYPE.search(label) or CHARACTER_TYPE.search(label)) and not NOT_BOOKS.search(label)
               for label in map(str.casefold, types))


# English words that describe a series rather than name it: "canon of Hercule Poirot", "Wallander novels"
CANON_PREFIX = re.compile(r"^canon of\s+", re.IGNORECASE)
DESCRIPTIVE_SUFFIX = re.compile(r"\s+(?:book\s+series|series|novels|books|casebooks)$", re.IGNORECASE)


def english_name(label):
    """Return the English name of a series, without "canon of" ("canon of Hercule Poirot" -> "Hercule Poirot")."""
    return CANON_PREFIX.sub("", label)


def borrowed_name(english):
    """Return the name a series without French name takes in French: its English name without descriptive words.

    "Wallander novels" -> "Wallander", "Robert Langdon series" -> "Robert
    Langdon"; proper names ("Foundation Trilogy", "Dirk Pitt") are kept as
    they are, like the titles of untranslated works.
    """
    return DESCRIPTIVE_SUFFIX.sub("", english_name(english)) or english


def _position(text):
    """Return a rank such as "3" as an integer, or None ("3.2", "prequel", out of range)."""
    if text and text.isdigit() and 0 < int(text) <= MAX_POSITION:
        return int(text)
    return None


def parse_series(rows):
    """Return ``({work: [{"id", "position"?}]}, {series id: {"fr_FR": name, "en_US": name}})``.

    Only the series of books are kept (see :func:`is_book_series`), and only
    those that have a name in at least one language.
    """
    types, names, memberships = {}, {}, {}
    for row in rows:
        series = _entity_id(row["series"]["value"])
        value = {key: row[key]["value"] for key in ("fr", "en", "mul") if key in row}
        known = names.setdefault(series, {})
        for key, text in value.items():
            known.setdefault(key, text)
        if "type" in row:
            types.setdefault(series, set()).add(row["type"]["value"])
        work = _entity_id(row["work"]["value"])
        position = _position(row.get("position", {}).get("value"))
        entries = memberships.setdefault(work, {})
        # Several statements, or several class labels per statement: keep a known rank
        if entries.get(series) is None:
            entries[series] = position

    labels = {}
    for series, known in names.items():
        en = known.get("en") or known.get("mul") or known.get("fr")
        en = en and english_name(en)
        fr = known.get("fr") or known.get("mul") or (en and borrowed_name(en))
        if fr and en and is_book_series(types.get(series, ())):
            labels[series] = {"fr_FR": fr, "en_US": en}

    works = {}
    for work, entries in memberships.items():
        kept = [{"id": series, **({} if position is None else {"position": position})}
                for series, position in entries.items() if series in labels]
        if kept:
            works[work] = kept
    return works, labels


def fetch_series(work_ids):
    rows = []
    for start in range(0, len(work_ids), BATCH_SIZE):
        batch = work_ids[start:start + BATCH_SIZE]
        rows += run_query(SERIES_QUERY % " ".join("wd:" + work for work in batch))
        time.sleep(PAUSE)
    return parse_series(rows)


def _with_series(book, series):
    """Return ``book`` with its ``series`` right after its awards, or its genres (or without, when none)."""
    anchor = "awards" if "awards" in book else "genre"
    updated = {}
    for key, value in book.items():
        if key == "series":
            continue
        updated[key] = value
        if key == anchor and series:
            updated["series"] = series
    return updated


def update(data, works, labels):
    """Replace the series vocabulary and the series of every book; return what happened."""
    report = Counter()
    used = set()
    for author in data["authors"]:
        for index, book in enumerate(author["books"]):
            series = sorted(works.get(book.get("wikidata_id"), []), key=lambda entry: labels[entry["id"]]["en_US"])
            author["books"][index] = _with_series(book, series)
            used.update(entry["id"] for entry in series)
            report["books in a series" if series else "books without series"] += 1
            report["ranks"] += sum("position" in entry for entry in series)
    vocabulary = {series: labels[series] for series in sorted(used, key=lambda series: int(series[1:]))}
    # The vocabulary comes right after the awards (or the genres)
    anchor = "awards" if "awards" in data else "genres"
    reordered = {}
    for key, value in data.items():
        if key == "series":
            continue
        reordered[key] = value
        if key == anchor:
            reordered["series"] = vocabulary
    data.clear()
    data.update(reordered)
    report["series"] = len(vocabulary)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--catalogue", type=Path, default=editor.CATALOGUE_PATH)
    parser.add_argument("--dry-run", action="store_true", help="report without writing the catalogue")
    args = parser.parse_args(argv)

    data = editor.load_catalogue(args.catalogue)
    ids = sorted({book["wikidata_id"] for author in data["authors"] for book in author["books"]
                  if "wikidata_id" in book})
    report = update(data, *fetch_series(ids))
    print(dict(report))
    if not args.dry_run:
        editor.save_catalogue(data, args.catalogue)
        print(f"catalogue written to {args.catalogue}")


if __name__ == "__main__":
    main()
