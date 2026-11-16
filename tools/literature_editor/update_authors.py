"""Fill the years of birth and death of the bundled authors from Wikidata.

Authors without a ``wikidata_id`` first get the one of the author (P50) of
their books on Wikidata whose name matches theirs.  Every author with an id
then gets ``born`` and ``died`` (years, negative for BC), when Wikidata gives
them to the year or the decade.  ``died`` is left out for living authors.

Usage::

    python tools/literature_editor/update_authors.py [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import editor

from faker_literature.importers.wikidata import _entity_id, _parse_year, run_query
from faker_literature.matching import name_key, names

BATCH_SIZE = 50
PAUSE = 1.0

BOOK_AUTHORS_QUERY = """
SELECT ?work ?author ?name WHERE {
  VALUES ?work { %s }
  ?work wdt:P50 ?author .
  { ?author rdfs:label ?name . FILTER(LANG(?name) IN ("en", "fr", "mul")) }
  UNION { ?author skos:altLabel ?name . FILTER(LANG(?name) IN ("en", "fr", "mul")) }
}
"""

# Birth (P569) and death (P570) dates with their precision, deprecated statements left out
LIFE_QUERY = """
SELECT ?author ?property ?time ?precision WHERE {
  VALUES ?author { %s }
  VALUES (?claim ?value ?property) {
    (p:P569 psv:P569 "born") (p:P570 psv:P570 "died")
  }
  ?author ?claim ?statement .
  ?statement ?value [ wikibase:timeValue ?time ; wikibase:timePrecision ?precision ] ;
             wikibase:rank ?rank .
  FILTER(?rank != wikibase:DeprecatedRank)
}
"""


def _batches(values, size=BATCH_SIZE):
    for start in range(0, len(values), size):
        yield values[start:start + size]


def find_authors(data):
    """Return ``{author index: Wikidata id}`` for the authors without id, found through their books."""
    missing = {index: author for index, author in enumerate(data["authors"]) if not author.get("wikidata_id")}
    works = {book["wikidata_id"]: index for index, author in missing.items() for book in author["books"]
             if "wikidata_id" in book}
    candidates = {}
    for batch in _batches(sorted(works)):
        for row in run_query(BOOK_AUTHORS_QUERY % " ".join("wd:" + work for work in batch)):
            index = works[_entity_id(row["work"]["value"])]
            author = _entity_id(row["author"]["value"])
            if name_key(row["name"]["value"]) in {name_key(name) for name in names(missing[index]["name"])}:
                candidates.setdefault(index, set()).add(author)
        time.sleep(PAUSE)
    # Ambiguous matches (two authors with the same name) are left out
    return {index: next(iter(found)) for index, found in candidates.items() if len(found) == 1}


def parse_lives(rows):
    """Return ``{author: {"born": year, "died": year}}``; the earliest year wins when Wikidata gives several."""
    lives = {}
    for row in rows:
        year = _parse_year(row["time"]["value"], row["precision"]["value"])
        if year is None:
            continue
        life = lives.setdefault(_entity_id(row["author"]["value"]), {})
        key = row["property"]["value"]
        life[key] = min(life.get(key, year), year)
    return lives


def fetch_lives(author_ids):
    lives = {}
    for batch in _batches(sorted(author_ids)):
        lives.update(parse_lives(run_query(LIFE_QUERY % " ".join("wd:" + author for author in batch))))
        time.sleep(PAUSE)
    return lives


def _with_life(author, qid, life):
    """Return the author entry with its id and life, in the catalogue's key order."""
    entry = {"name": author["name"]}
    if qid:
        entry["wikidata_id"] = qid
    entry["nationality"] = author["nationality"]
    for key in ("born", "died"):
        if life.get(key) is not None:
            entry[key] = life[key]
    entry["books"] = author["books"]
    return entry


def update(data, found, lives):
    """Set the found ids and the lives; return what happened."""
    report = Counter()
    used = {author.get("wikidata_id") for author in data["authors"]}
    for index, author in enumerate(data["authors"]):
        qid = author.get("wikidata_id")
        if not qid and index in found and found[index] not in used:
            qid = found[index]
            used.add(qid)
            report["Wikidata id found"] += 1
        life = lives.get(qid, {})
        # A death before the birth is a Wikidata error: keep neither
        if "born" in life and "died" in life and life["died"] < life["born"]:
            life = {}
            report["inconsistent life skipped"] += 1
        report["with a birth year" if "born" in life else "without birth year"] += 1
        data["authors"][index] = _with_life(author, qid, life)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--catalogue", type=Path, default=editor.CATALOGUE_PATH)
    parser.add_argument("--dry-run", action="store_true", help="report without writing the catalogue")
    args = parser.parse_args(argv)

    data = editor.load_catalogue(args.catalogue)
    found = find_authors(data)
    ids = {author["wikidata_id"] for author in data["authors"] if author.get("wikidata_id")} | set(found.values())
    report = update(data, found, fetch_lives(ids))
    print(dict(report))
    if not args.dry_run:
        editor.save_catalogue(data, args.catalogue)
        print(f"catalogue written to {args.catalogue}")


if __name__ == "__main__":
    main()
