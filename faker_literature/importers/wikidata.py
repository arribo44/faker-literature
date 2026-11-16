"""Import well-known literary works from Wikidata (CC0).

The import runs in two steps because the public SPARQL endpoint times out
when sorting every literary work: a first query lists the works with at least
``min_sitelinks`` Wikipedia articles, which are ranked locally, then their
details are fetched in small batches.
"""

import json
import time
import urllib.parse
import urllib.request

from faker_literature.matching import YEAR_TOLERANCE, DuplicateIndex
from faker_literature.store import MAX_PAGES, load_vocabulary, validate_book


SOURCE = "wikidata"
ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "faker-literature (https://github.com/arribo44/faker-literature)"
TIMEOUT = 90
MAX_RESPONSE_BYTES = 20 * 1024 * 1024
BATCH_SIZE = 100
MAX_LIMIT = 5000

CANDIDATES_QUERY = """
SELECT ?work ?links WHERE {
  ?work wdt:P31 wd:Q7725634 ;
        wikibase:sitelinks ?links .
  FILTER(?links >= %(min_sitelinks)d)
}
"""

DETAILS_QUERY = """
SELECT ?work ?titleFr ?titleEn ?author ?writerFr ?writerEn ?date ?inception ?pages
       ?genreFr ?genreEn ?country ?demonymFr ?demonymEn ?publisherFr ?publisherEn
WHERE {
  VALUES ?work { %(works)s }
  ?work wdt:P50 ?author .
  OPTIONAL { ?work wdt:P577 ?date }
  OPTIONAL { ?work wdt:P571 ?inception }
  FILTER(BOUND(?date) || BOUND(?inception))
  ?work rdfs:label ?titleFr . FILTER(LANG(?titleFr) = "fr")
  ?work rdfs:label ?titleEn . FILTER(LANG(?titleEn) = "en")
  # Names identical in every language are now stored once, as "mul" labels
  OPTIONAL { ?author rdfs:label ?authorFr . FILTER(LANG(?authorFr) = "fr") }
  OPTIONAL { ?author rdfs:label ?authorEn . FILTER(LANG(?authorEn) = "en") }
  OPTIONAL { ?author rdfs:label ?authorMul . FILTER(LANG(?authorMul) = "mul") }
  BIND(COALESCE(?authorFr, ?authorMul) AS ?writerFr)
  BIND(COALESCE(?authorEn, ?authorMul) AS ?writerEn)
  FILTER(BOUND(?writerFr) && BOUND(?writerEn))
  OPTIONAL {
    ?work wdt:P136 ?genre .
    ?genre rdfs:label ?genreFr . FILTER(LANG(?genreFr) = "fr")
    ?genre rdfs:label ?genreEn . FILTER(LANG(?genreEn) = "en")
  }
  OPTIONAL {
    ?author wdt:P27 ?country .
    ?country wdt:P1549 ?demonymFr . FILTER(LANG(?demonymFr) = "fr")
    ?country wdt:P1549 ?demonymEn . FILTER(LANG(?demonymEn) = "en")
  }
  OPTIONAL { ?work wdt:P1104 ?pages }
  OPTIONAL {
    ?work wdt:P123 ?publisher .
    ?publisher rdfs:label ?publisherFr . FILTER(LANG(?publisherFr) = "fr")
    ?publisher rdfs:label ?publisherEn . FILTER(LANG(?publisherEn) = "en")
  }
}
"""


def run_query(query):
    """POST ``query`` to the Wikidata endpoint and return the result bindings."""
    request = urllib.request.Request(
        ENDPOINT,
        data=urllib.parse.urlencode({"query": query}).encode("utf-8"),
        headers={
            "Accept": "application/sparql-results+json",
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        body = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise ValueError(f"Wikidata response larger than {MAX_RESPONSE_BYTES} bytes")
    return json.loads(body.decode("utf-8"))["results"]["bindings"]


def _entity_id(uri):
    entity = uri.rsplit("/", 1)[-1]
    if not (entity.startswith("Q") and entity[1:].isdigit()):
        raise ValueError(f"Unexpected Wikidata entity {uri!r}")
    return entity


def _parse_year(value):
    """Extract the year of an ``xsd:dateTime`` such as ``-0800-01-01T00:00:00Z``."""
    try:
        return int(value[:value.index("-", 1)])
    except ValueError:
        return None


EN_ADJECTIVE_SUFFIXES = ("ish", "ian", "an", "ese", "ch", "ic", "i")


def _pick_demonym(values, locale):
    """Choose one demonym among the gendered / plural forms Wikidata lists.

    French keeps the shortest form (masculine singular, e.g. ``français``);
    English prefers singular adjectives (``British`` over ``Briton``).
    """
    shortest = lambda value: (len(value), value)
    if locale == "en_US":
        singular = [value for value in values if not value.endswith("s")] or list(values)
        adjectives = [value for value in singular if value.lower().endswith(EN_ADJECTIVE_SUFFIXES)]
        return min(adjectives or singular, key=shortest).capitalize()
    return min(values, key=shortest).lower()


def map_genres(labels, vocabulary):
    """Return the vocabulary ids of the ``(French, English)`` genre labels.

    Wikidata genres are matched on their French label, then on their English
    one; genres missing from the vocabulary are dropped, so that imported
    books only use genres with a single, known translation.
    """
    ids = []
    for fr, en in labels:
        genre_id = vocabulary.match(fr, "fr_FR") or vocabulary.match(en, "en_US")
        if genre_id and genre_id not in ids:
            ids.append(genre_id)
    return ids


def parse_bindings(bindings, vocabulary=None):
    """Group SPARQL rows by work and return catalogue records.

    Genres are mapped onto ``vocabulary`` (by default the bundled one).  Works
    lacking a known genre, a nationality or a usable date are left out.
    """
    vocabulary = vocabulary or load_vocabulary()
    works = {}
    for row in bindings:
        value = {key: cell["value"] for key, cell in row.items()}
        work = works.setdefault(_entity_id(value["work"]), {
            "title": {"fr_FR": value["titleFr"], "en_US": value["titleEn"]},
            "writers": {},
            "years": set(),
            "inceptions": set(),
            "pages": set(),
            "genres": {},
            "demonyms": {},
            "publisher": None,
        })
        work["writers"].setdefault(value["author"], (value["writerFr"], value["writerEn"]))
        for key, years in (("date", work["years"]), ("inception", work["inceptions"])):
            year = _parse_year(value[key]) if key in value else None
            if year is not None:
                years.add(year)
        # Page counts contain typos such as 940512: keep plausible ones
        if value.get("pages", "").isdigit() and 0 < int(value["pages"]) <= MAX_PAGES:
            work["pages"].add(int(value["pages"]))
        if "genreFr" in value:
            work["genres"].setdefault(value["genreFr"], value["genreEn"])
        if "demonymFr" in value:
            fr, en = work["demonyms"].setdefault(_entity_id(value["country"]), (set(), set()))
            fr.add(value["demonymFr"])
            en.add(value["demonymEn"])
        if "publisherFr" in value and work["publisher"] is None:
            work["publisher"] = {"fr_FR": value["publisherFr"], "en_US": value["publisherEn"]}

    records = []
    for entity, work in works.items():
        # Publication date first, creation date only when it is missing
        years = work["years"] or work["inceptions"]
        genres = map_genres(work["genres"].items(), vocabulary)
        if not (genres and work["demonyms"] and years):
            continue
        # Several citizenships: the lowest Q-id is usually the best known country
        demonyms_fr, demonyms_en = work["demonyms"][min(work["demonyms"], key=lambda q: int(q[1:]))]
        writers = list(work["writers"].values())
        pages = min(work["pages"]) if work["pages"] else None
        records.append({
            "wikidata_id": entity,
            "writer": {
                "fr_FR": ", ".join(fr for fr, _ in writers),
                "en_US": ", ".join(en for _, en in writers),
            },
            "nationality": {
                "fr_FR": _pick_demonym(demonyms_fr, "fr_FR"),
                "en_US": _pick_demonym(demonyms_en, "en_US"),
            },
            "title": work["title"],
            "genre": vocabulary.resolve(genres),
            "year": min(years),
            "pages": None if pages is None else {"fr_FR": pages, "en_US": pages},
            "publisher": work["publisher"],
        })
    return records


def exclude_known(records, known_books):
    """Drop records already present in ``known_books``.

    A record is known when it has the same Wikidata id as a known book, or
    the same title (ignoring case, accents and a leading article) within
    ``YEAR_TOLERANCE`` years.
    """
    index = DuplicateIndex(known_books, year_tolerance=YEAR_TOLERANCE)
    return [record for record in records if record not in index]


def fetch_works(limit=500, min_sitelinks=30, pause=1.0, log=print, vocabulary=None):
    """Fetch up to ``limit`` of the most linked literary works and return valid records."""
    limit = max(1, min(int(limit), MAX_LIMIT))
    min_sitelinks = max(0, int(min_sitelinks))

    candidates = run_query(CANDIDATES_QUERY % {"min_sitelinks": min_sitelinks})
    ranked = sorted(candidates, key=lambda row: -int(row["links"]["value"]))
    entities = list(dict.fromkeys(_entity_id(row["work"]["value"]) for row in ranked))
    log(f"{len(entities)} candidate works with >= {min_sitelinks} sitelinks")

    records = []
    for start in range(0, len(entities), BATCH_SIZE):
        if len(records) >= limit:
            break
        batch = entities[start:start + BATCH_SIZE]
        if start:
            time.sleep(pause)
        rows = run_query(DETAILS_QUERY % {"works": " ".join("wd:" + entity for entity in batch)})
        records.extend(parse_bindings(rows, vocabulary))
        log(f"  batch {start // BATCH_SIZE + 1}: {len(records)} usable works so far")

    valid = []
    for record in records[:limit]:
        try:
            validate_book(dict(record, source=SOURCE))
        except ValueError as error:
            log(f"  skipped {record['wikidata_id']}: {error}")
            continue
        valid.append(record)
    return valid


def import_into(store, limit=500, min_sitelinks=30, log=print):
    """Fetch works from Wikidata and replace the store's ``wikidata`` books with them."""
    builtin = [book for book in store.books.all() if book["source"] != SOURCE]
    vocabulary = load_vocabulary()
    records = exclude_known(fetch_works(limit, min_sitelinks, log=log, vocabulary=vocabulary), builtin)
    return store.replace_source(SOURCE, records)

