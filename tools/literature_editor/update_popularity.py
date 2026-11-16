"""Fill the ``popularity`` of the bundled books: the number of Wikipedia articles of their work.

Books with a ``wikidata_id`` get the sitelinks count of that work.  Books
entered by hand, without one, are first looked up on Wikidata by title and
author (the first search hit written by the same author wins); when found,
they get its ``wikidata_id`` too, unless another book already has it.

Usage::

    python tools/literature_editor/update_popularity.py [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import editor

from faker_literature.importers.wikidata import (
    ITEM_AUTHORS_QUERY,
    _entity_id,
    match_work,
    parse_item_authors,
    run_query,
    search_items,
)
from faker_literature.matching import names

BATCH_SIZE = 40
PAUSE = 1.0
SEARCH_PAUSE = 0.2

SITELINKS_QUERY = """
SELECT ?work ?links WHERE {
  VALUES ?work { %s }
  ?work wikibase:sitelinks ?links .
}
"""


def _batches(values, size=BATCH_SIZE):
    for start in range(0, len(values), size):
        yield values[start:start + size]


def find_works(data, log=print):
    """Look the books without ``wikidata_id`` up; return ``{(author index, book index): work id}``."""
    missing = [(a, b) for a, author in enumerate(data["authors"]) for b, book in enumerate(author["books"])
               if "wikidata_id" not in book]
    log(f"{len(missing)} books without a Wikidata id")
    hits = {}
    for count, (a, b) in enumerate(missing, 1):
        title = data["authors"][a]["books"][b]["title"]
        # The English title first, then the French one when it differs
        found = []
        for text in dict.fromkeys([title["en_US"], title["fr_FR"]]):
            found += [item for item in search_items(text) if item not in found]
            time.sleep(SEARCH_PAUSE)
        hits[a, b] = found
        if count % 50 == 0:
            log(f"  {count}/{len(missing)} searched")

    items = {}
    for batch in _batches(sorted({item for found in hits.values() for item in found})):
        items.update(parse_item_authors(run_query(ITEM_AUTHORS_QUERY % " ".join("wd:" + item for item in batch))))
        time.sleep(PAUSE)

    works = {}
    for (a, b), found in hits.items():
        match = match_work(names(data["authors"][a]["name"]), found, items)
        if match:
            works[a, b] = match[0]
    return works


def sitelinks(work_ids):
    """Return ``{work id: number of Wikipedia articles}``."""
    counts = {}
    for batch in _batches(sorted(work_ids)):
        for row in run_query(SITELINKS_QUERY % " ".join("wd:" + work for work in batch)):
            counts[_entity_id(row["work"]["value"])] = int(row["links"]["value"])
        time.sleep(PAUSE)
    return counts


def _with(book, **fields):
    """Return ``book`` with ``fields`` set, ``wikidata_id`` and ``popularity`` last."""
    updated = {key: value for key, value in book.items() if key not in ("popularity", "wikidata_id")}
    merged = {**{key: book[key] for key in ("popularity", "wikidata_id") if key in book}, **fields}
    for key in ("popularity", "wikidata_id"):
        if merged.get(key) is not None:
            updated[key] = merged[key]
    return updated


def update(data, works, counts):
    """Set the found ``wikidata_id`` and every ``popularity``; return what happened."""
    report = Counter()
    used = Counter(book["wikidata_id"] for author in data["authors"] for book in author["books"]
                   if "wikidata_id" in book)
    for (a, b), work in works.items():
        if used[work]:
            report["found, but the work is already in the catalogue"] += 1
            continue
        used[work] += 1
        data["authors"][a]["books"][b] = _with(data["authors"][a]["books"][b], wikidata_id=work)
        report["Wikidata id found"] += 1
    for author in data["authors"]:
        for index, book in enumerate(author["books"]):
            popularity = counts.get(book.get("wikidata_id"))
            if popularity:
                author["books"][index] = _with(book, popularity=popularity)
                report["popularity set"] += 1
            else:
                report["no popularity"] += 1
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--catalogue", type=Path, default=editor.CATALOGUE_PATH)
    parser.add_argument("--dry-run", action="store_true", help="report without writing the catalogue")
    args = parser.parse_args(argv)

    data = editor.load_catalogue(args.catalogue)
    works = find_works(data)
    ids = {book["wikidata_id"] for author in data["authors"] for book in author["books"] if "wikidata_id" in book}
    counts = sitelinks(ids | set(works.values()))
    report = update(data, works, counts)
    print(dict(report))
    if not args.dry_run:
        editor.save_catalogue(data, args.catalogue)
        print(f"catalogue written to {args.catalogue}")


if __name__ == "__main__":
    main()
