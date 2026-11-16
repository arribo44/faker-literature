"""Fill the literary awards of the bundled books from Wikidata.

Every book with a ``wikidata_id`` gets the literary awards (P166, instances of
a subclass of "literary award", Q378427) its work received, as ids of the
``awards`` vocabulary at the top of the catalogue: ``{"Q187300": {"fr_FR":
"prix Goncourt", "en_US": "Prix Goncourt"}}``.  Awards without both a French
and an English label are left out, and so are the "best books" lists that
Wikidata files as awards.

Usage::

    python tools/literature_editor/update_awards.py [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import editor

from faker_literature.importers.wikidata import _entity_id, run_query

BATCH_SIZE = 100
PAUSE = 1.0

AWARDS_QUERY = """
SELECT ?work ?award ?fr ?en WHERE {
  VALUES ?work { %s }
  ?work p:P166 ?statement .
  ?statement ps:P166 ?award ; wikibase:rank ?rank .
  FILTER(?rank != wikibase:DeprecatedRank)
  ?award wdt:P31/wdt:P279* wd:Q378427 .
  ?award rdfs:label ?fr . FILTER(LANG(?fr) = "fr")
  ?award rdfs:label ?en . FILTER(LANG(?en) = "en")
}
"""

# "Best books" lists filed as literary awards on Wikidata
NOT_AWARDS = {
    "Q671613",    # Modern Library 100 Best Novels
    "Q4630676",   # 20th Century's Greatest Hits: 100 English-Language Books of Fiction
    "Q20899118",  # NPR Top 100 Science Fiction and Fantasy Books
}


def parse_awards(rows):
    """Return ``({work: [award ids]}, {award id: {"fr_FR": label, "en_US": label}})``."""
    works, labels = {}, {}
    for row in rows:
        award = _entity_id(row["award"]["value"])
        if award in NOT_AWARDS:
            continue
        labels.setdefault(award, {"fr_FR": row["fr"]["value"], "en_US": row["en"]["value"]})
        received = works.setdefault(_entity_id(row["work"]["value"]), [])
        if award not in received:
            received.append(award)
    return works, labels


def fetch_awards(work_ids):
    rows = []
    for start in range(0, len(work_ids), BATCH_SIZE):
        batch = work_ids[start:start + BATCH_SIZE]
        rows += run_query(AWARDS_QUERY % " ".join("wd:" + work for work in batch))
        time.sleep(PAUSE)
    return parse_awards(rows)


def _with_awards(book, awards):
    """Return ``book`` with its ``awards`` right after its genres (or without, when none)."""
    updated = {}
    for key, value in book.items():
        if key == "awards":
            continue
        updated[key] = value
        if key == "genre" and awards:
            updated["awards"] = awards
    return updated


def update(data, works, labels):
    """Replace the awards vocabulary and the awards of every book; return what happened."""
    report = Counter()
    used = set()
    for author in data["authors"]:
        for index, book in enumerate(author["books"]):
            awards = sorted(works.get(book.get("wikidata_id"), []), key=lambda award: labels[award]["en_US"])
            author["books"][index] = _with_awards(book, awards)
            used.update(awards)
            report["books with an award" if awards else "books without award"] += 1
    vocabulary = {award: labels[award] for award in sorted(used, key=lambda award: int(award[1:]))}
    # The vocabulary comes right after the genres
    reordered = {}
    for key, value in data.items():
        if key == "awards":
            continue
        reordered[key] = value
        if key == "genres":
            reordered["awards"] = vocabulary
    data.clear()
    data.update(reordered)
    report["awards"] = len(vocabulary)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--catalogue", type=Path, default=editor.CATALOGUE_PATH)
    parser.add_argument("--dry-run", action="store_true", help="report without writing the catalogue")
    args = parser.parse_args(argv)

    data = editor.load_catalogue(args.catalogue)
    ids = sorted({book["wikidata_id"] for author in data["authors"] for book in author["books"]
                  if "wikidata_id" in book})
    report = update(data, *fetch_awards(ids))
    print(dict(report))
    if not args.dry_run:
        editor.save_catalogue(data, args.catalogue)
        print(f"catalogue written to {args.catalogue}")


if __name__ == "__main__":
    main()
