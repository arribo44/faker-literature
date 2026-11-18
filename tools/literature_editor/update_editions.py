"""Fill the page counts and publishers of the bundled books from their French and English editions on Wikidata.

For each book with a ``wikidata_id``, the editions of its work (P747, or
items whose P629 is the work) in French (Q150) or English (Q1860) give real
page counts (P1104) and publishers (P123) for the matching locale:

* a missing value is filled from an edition in the locale's language, the
  page count and the publisher coming from the same edition when it has both
  (the earliest such edition: usually the first translation);
* a value of a work written in another language that matches no edition in
  the locale's language came from the original edition ("G. P. Putnam's Sons"
  for the French edition of an American novel): it is replaced by the values
  of an edition in the locale's language, when there is one.

The page counts and publishers typed by hand (``pages_estimated``,
``publisher_estimated``) are left alone: they describe a usual, current
edition, where the editions found on Wikidata are often old or unusual ones.

Publishers are mapped onto the ``publishers`` vocabulary by Wikidata id, then
by name; an unknown publisher is added to it with its country, provided that
it is a publishing house, an imprint or the like (Wikidata also gives people,
websites, collections and magazines as publishers of editions).  Publishers
no longer used by any book leave the vocabulary.

Usage::

    python tools/literature_editor/update_editions.py [--dry-run] [--rows FILE]

``--rows`` keeps the Wikidata answers in FILE, so that a second run (after
``--dry-run``) does not query Wikidata again.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import editor

from faker_literature.importers.wikidata import _parse_year, run_query
from faker_literature.store import LOCALES, MAX_PAGES
from faker_literature.vocabulary import PublisherVocabulary

BATCH_SIZE = 60
PAUSE = 1.0
# Fewer pages is a typo or a leaflet, not an edition of the work
MIN_PAGES = 10
LANGUAGES = {"Q150": "fr_FR", "Q1860": "en_US"}
# What a new publisher must be an instance of: publishing house, imprint, book publisher, university press,
# small press, open-access publisher, publishing group, book sales club, printing company.  Wikidata also
# files people, websites (Gallica), collections and magazines as publishers of editions.
PUBLISHER_CLASSES = {"Q2085381", "Q2608849", "Q1320047", "Q479716", "Q1661080", "Q45400320", "Q8869", "Q998421",
                     "Q6500733"}

EDITIONS_QUERY = """
SELECT ?work ?edition ?lang ?pages ?publisher ?date WHERE {
  VALUES ?work { %s }
  { ?work wdt:P747 ?edition } UNION { ?edition wdt:P629 ?work }
  ?edition wdt:P407 ?lang .
  VALUES ?lang { wd:Q150 wd:Q1860 }
  OPTIONAL { ?edition wdt:P1104 ?pages }
  OPTIONAL { ?edition wdt:P123 ?publisher }
  OPTIONAL { ?edition wdt:P577 ?date }
}
"""

WORK_LANGUAGES_QUERY = """
SELECT ?work ?lang WHERE {
  VALUES ?work { %s }
  ?work wdt:P407 ?lang .
}
"""

PUBLISHERS_QUERY = """
SELECT ?publisher ?fr ?en ?mul ?class ?country WHERE {
  VALUES ?publisher { %s }
  OPTIONAL { ?publisher rdfs:label ?fr . FILTER(LANG(?fr) = "fr") }
  OPTIONAL { ?publisher rdfs:label ?en . FILTER(LANG(?en) = "en") }
  OPTIONAL { ?publisher rdfs:label ?mul . FILTER(LANG(?mul) = "mul") }
  OPTIONAL { ?publisher wdt:P31 ?class }
  OPTIONAL { { ?publisher wdt:P17/wdt:P297 ?country } UNION { ?publisher wdt:P159/wdt:P17/wdt:P297 ?country } }
}
"""


def _id(cell):
    return cell["value"].rsplit("/", 1)[-1]


def _batches(values, size=BATCH_SIZE):
    for start in range(0, len(values), size):
        yield values[start:start + size]


# Wikidata answers

def parse_editions(rows):
    """Return ``{(work, locale): {edition: {"pages": int | None, "publishers": [ids], "year": int | None}}}``."""
    editions = {}
    for row in rows:
        locale = LANGUAGES.get(_id(row["lang"]))
        if locale is None:
            continue
        edition = editions.setdefault((_id(row["work"]), locale), {}).setdefault(
            _id(row["edition"]), {"pages": None, "publishers": [], "year": None})
        pages = row.get("pages", {}).get("value", "")
        if pages.isdigit() and MIN_PAGES <= int(pages) <= MAX_PAGES:
            # Several counts (volumes, typos): the smallest one, as the importer does
            edition["pages"] = min(int(pages), edition["pages"] or MAX_PAGES)
        if "publisher" in row and row["publisher"]["type"] == "uri":
            publisher = _id(row["publisher"])
            if publisher.startswith("Q") and publisher not in edition["publishers"]:
                edition["publishers"].append(publisher)
        year = _parse_year(row["date"]["value"]) if "date" in row else None
        if year is not None:
            edition["year"] = year if edition["year"] is None else min(edition["year"], year)
    return editions


def parse_work_languages(rows):
    """Return ``{work: {locale, ...}}``: the catalogue locales written in the work's original language."""
    languages = {}
    for row in rows:
        locale = LANGUAGES.get(_id(row["lang"]))
        languages.setdefault(_id(row["work"]), set())
        if locale:
            languages[_id(row["work"])].add(locale)
    return languages


def parse_publishers(rows):
    """Return ``{publisher: {"labels": {"fr": ..., "en": ..., "mul": ...}, "classes": set, "countries": Counter}}``."""
    publishers = {}
    for row in rows:
        publisher = publishers.setdefault(_id(row["publisher"]), {"labels": {}, "classes": set(),
                                                                   "countries": Counter()})
        for language in ("fr", "en", "mul"):
            if language in row:
                publisher["labels"].setdefault(language, row[language]["value"])
        if "class" in row:
            publisher["classes"].add(_id(row["class"]))
        if "country" in row:
            publisher["countries"][row["country"]["value"]] += 1
    return publishers


def fetch(work_ids, log=print):
    """Return the raw Wikidata rows ``{"editions": [...], "languages": [...], "publishers": [...]}``."""
    rows = {"editions": [], "languages": [], "publishers": []}
    for batch in _batches(work_ids):
        works = " ".join("wd:" + work for work in batch)
        rows["editions"] += run_query(EDITIONS_QUERY % works)
        rows["languages"] += run_query(WORK_LANGUAGES_QUERY % works)
        time.sleep(PAUSE)
    publishers = sorted({_id(row["publisher"]) for row in rows["editions"]
                         if "publisher" in row and _id(row["publisher"]).startswith("Q")})
    log(f"{len(rows['editions'])} edition rows, {len(publishers)} publishers")
    for batch in _batches(publishers, 200):
        rows["publishers"] += run_query(PUBLISHERS_QUERY % " ".join("wd:" + publisher for publisher in batch))
        time.sleep(PAUSE)
    return rows


# Publishers

class PublisherResolver:
    """Map Wikidata publishers onto the ``publishers`` vocabulary, adding the unknown publishing houses."""

    def __init__(self, vocabulary: PublisherVocabulary, info):
        self.vocabulary = vocabulary
        self.info = info
        self.by_wikidata = {publisher["wikidata_id"]: publisher_id
                            for publisher_id, publisher in vocabulary.publishers.items() if "wikidata_id" in publisher}
        self.added = []

    def _is_publisher(self, qid):
        info = self.info.get(qid)
        return info is not None and bool(info["labels"]) and bool(info["classes"] & PUBLISHER_CLASSES)

    def resolve(self, qid, locale):
        """Return the vocabulary id of the Wikidata publisher ``qid``, or ``None``."""
        if qid in self.by_wikidata:
            return self.by_wikidata[qid]
        info = self.info.get(qid)
        if info is None:
            return None
        own = "fr" if locale == "fr_FR" else "en"
        labels = [info["labels"][language] for language in (own, "mul", "en", "fr") if language in info["labels"]]
        for label in labels:
            publisher_id = self.vocabulary.match(label)
            if publisher_id:
                return publisher_id
        if not self._is_publisher(qid):
            return None
        country = info["countries"].most_common(1)[0][0] if info["countries"] else None
        publisher_id = self.vocabulary.add(labels[0], country=country, wikidata_id=qid)
        self.by_wikidata[qid] = publisher_id
        self.added.append(publisher_id)
        return publisher_id


# Updating the catalogue

def _edition_publisher(edition, locale, resolver):
    """Return the vocabulary id of the first usable publisher of ``edition``, or ``None``."""
    for qid in edition["publishers"]:
        publisher_id = resolver.resolve(qid, locale)
        if publisher_id:
            return publisher_id
    return None


def choose(editions, needed):
    """Return the edition to take ``needed`` (``{"pages", "publisher"}``) from, or ``None``.

    Editions giving every needed value come first, then those giving more of
    them; the earliest one wins (usually the first edition in that language).
    """
    candidates = [edition for edition in editions if any(edition[field] is not None for field in needed)]
    if not candidates:
        return None
    return min(candidates, key=lambda edition: (
        -sum(edition[field] is not None for field in needed),
        edition["year"] if edition["year"] is not None else 10**4,
        int(edition["id"][1:]),
    ))


def _candidates(work_editions, locale, resolver):
    candidates = []
    for qid, edition in work_editions.items():
        pages, publisher = edition["pages"], _edition_publisher(edition, locale, resolver)
        if pages is not None or publisher is not None:
            candidates.append({"id": qid, "pages": pages, "publisher": publisher, "year": edition["year"]})
    return candidates


def _set(book, field, locale, value):
    current = book.get(field) or {other: None for other in LOCALES}
    current[locale] = value
    book[field] = current


def update_book(book, work_editions, original_locales, resolver, report):
    """Fill or correct the page counts and publishers of ``book``; ``work_editions`` is ``{locale: {...}}``."""
    candidates = {locale: _candidates(work_editions.get(locale, {}), locale, resolver) for locale in LOCALES}

    for locale in LOCALES:
        if not candidates[locale]:
            continue
        needed = set()
        for field in ("pages", "publisher"):
            if book.get(f"{field}_estimated"):  # typed by hand: left alone
                continue
            value = (book.get(field) or {}).get(locale)
            known = {edition[field] for edition in candidates[locale]}
            if value is None:
                needed.add(field)
            elif locale not in original_locales and value not in known and known - {None}:
                # A value of the original edition, while editions in the locale's language exist
                needed.add(field)
        if not needed:
            continue
        edition = choose(candidates[locale], needed)
        if edition is None:
            continue
        for field in needed:
            if edition[field] is None:
                continue
            previous = (book.get(field) or {}).get(locale)
            _set(book, field, locale, edition[field])
            report[f"{field}[{locale}] {'filled' if previous is None else 'replaced'}"] += 1


def update(data, editions, languages, publishers):
    """Update every book of ``data`` with a ``wikidata_id``; return what happened."""
    report = Counter()
    vocabulary_data = data.setdefault("publishers", {})
    resolver = PublisherResolver(PublisherVocabulary(vocabulary_data), publishers)
    for author in data["authors"]:
        for book in author["books"]:
            work = book.get("wikidata_id")
            if not work:
                continue
            work_editions = {locale: editions.get((work, locale), {}) for locale in LOCALES}
            update_book(book, work_editions, languages.get(work, set()), resolver, report)
    # Publishers no longer used (replaced by those of real editions) leave the vocabulary
    used = {publisher_id for author in data["authors"] for book in author["books"]
            for publisher_id in (book.get("publisher") or {}).values() if publisher_id}
    unused = sorted(set(vocabulary_data) - used)
    for publisher_id in unused:
        del vocabulary_data[publisher_id]
    editor._with_vocabulary(data, "publishers", vocabulary_data)
    report["publishers added"] = len([publisher_id for publisher_id in resolver.added if publisher_id in used])
    report["publishers dropped"] = len(set(unused) - set(resolver.added))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--catalogue", type=Path, default=editor.CATALOGUE_PATH)
    parser.add_argument("--dry-run", action="store_true", help="report without writing the catalogue")
    parser.add_argument("--rows", type=Path, help="JSON file keeping the Wikidata answers between runs")
    args = parser.parse_args(argv)

    data = editor.load_catalogue(args.catalogue)
    if args.rows and args.rows.exists():
        rows = json.loads(args.rows.read_text(encoding="utf-8"))
    else:
        ids = sorted({book["wikidata_id"] for author in data["authors"] for book in author["books"]
                      if "wikidata_id" in book})
        rows = fetch(ids)
        if args.rows:
            args.rows.write_text(json.dumps(rows), encoding="utf-8")
    report = update(data, parse_editions(rows["editions"]), parse_work_languages(rows["languages"]),
                    parse_publishers(rows["publishers"]))
    for key, count in sorted(report.items()):
        print(f"{key}: {count}")
    if not args.dry_run:
        editor.save_catalogue(data, args.catalogue)
        print(f"catalogue written to {args.catalogue}")


if __name__ == "__main__":
    main()
