"""Import well-known literary works from Wikidata (CC0).

The import runs in two steps because the public SPARQL endpoint times out
when sorting every literary work: a first query lists the works with at least
``min_sitelinks`` Wikipedia articles, which are ranked locally, then their
details are fetched in small batches.
"""

from __future__ import annotations

import http.client
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from faker_literature.matching import YEAR_TOLERANCE, DuplicateIndex, name_key
from faker_literature.store import (
    MAX_PAGES,
    BookStore,
    Record,
    load_builtin_books,
    load_vocabulary,
    pick,
    validate_book,
)
from faker_literature.vocabulary import GenreVocabulary

# One SPARQL result row: {variable: {"type": ..., "value": ...}}
Binding = dict[str, dict[str, str]]
Log = Callable[[str], object]


SOURCE = "wikidata"
ENDPOINT = "https://query.wikidata.org/sparql"
SEARCH_API = "https://www.wikidata.org/w/api.php"
SEARCH_RESULTS = 5
USER_AGENT = "faker-literature (https://github.com/arribo44/faker-literature)"
TIMEOUT = 90
MAX_RESPONSE_BYTES = 20 * 1024 * 1024
BATCH_SIZE = 100
MAX_LIMIT = 5000

# Overloaded or rate-limited endpoint: retried, with an exponential back-off
RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 4
MAX_RETRY_DELAY = 60

# Dates of a precision coarser than a decade ("8th century BC") give no usable year
MIN_DATE_PRECISION = 8

# Well-known novels, plays or poems are "literary works" (Q7725634), their form being given by P7937:
# querying "novel" (Q8261) and the like as well finds no work with 30 sitelinks or more
CANDIDATES_QUERY = """
SELECT ?work ?links WHERE {
  ?work wdt:P31 wd:Q7725634 ;
        wikibase:sitelinks ?links .
  FILTER(?links >= %(min_sitelinks)d)
}
"""

# Publication (P577) and creation (P571) dates with their precision, deprecated statements left out
DATES_PATTERN = """
  OPTIONAL {
    ?work p:P577 ?dateStatement .
    ?dateStatement psv:P577 [ wikibase:timeValue ?date ; wikibase:timePrecision ?datePrecision ] ;
                   wikibase:rank ?dateRank .
    FILTER(?dateRank != wikibase:DeprecatedRank)
  }
  OPTIONAL {
    ?work p:P571 ?inceptionStatement .
    ?inceptionStatement psv:P571 [ wikibase:timeValue ?inception ; wikibase:timePrecision ?inceptionPrecision ] ;
                        wikibase:rank ?inceptionRank .
    FILTER(?inceptionRank != wikibase:DeprecatedRank)
  }
"""

DETAILS_QUERY = """
SELECT ?work ?links ?titleFr ?titleEn ?author ?writerFr ?writerEn ?date ?datePrecision ?inception ?inceptionPrecision
       ?pages ?genreFr ?genreEn ?formFr ?formEn ?country ?demonymFr ?demonymEn ?birthCountry ?publisherFr ?publisherEn
WHERE {
  VALUES ?work { %(works)s }
  ?work wdt:P50 ?author ;
        wikibase:sitelinks ?links .
  %(dates)s
  FILTER(BOUND(?date) || BOUND(?inception))
  ?work rdfs:label ?titleEn . FILTER(LANG(?titleEn) = "en")
  # Works never translated into French have no French title
  OPTIONAL { ?work rdfs:label ?titleFr . FILTER(LANG(?titleFr) = "fr") }
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
  # The form of the work (novel, play...) stands in for missing genres
  OPTIONAL {
    ?work wdt:P7937 ?form .
    ?form rdfs:label ?formFr . FILTER(LANG(?formFr) = "fr")
    ?form rdfs:label ?formEn . FILTER(LANG(?formEn) = "en")
  }
  OPTIONAL {
    ?author wdt:P27 ?country .
    ?country wdt:P1549 ?demonymFr . FILTER(LANG(?demonymFr) = "fr")
    ?country wdt:P1549 ?demonymEn . FILTER(LANG(?demonymEn) = "en")
  }
  # Several citizenships: the one of the country of birth wins
  OPTIONAL { ?author wdt:P19/wdt:P17 ?birthCountry }
  OPTIONAL { ?work wdt:P1104 ?pages }
  OPTIONAL {
    ?work wdt:P123 ?publisher .
    ?publisher rdfs:label ?publisherFr . FILTER(LANG(?publisherFr) = "fr")
    ?publisher rdfs:label ?publisherEn . FILTER(LANG(?publisherEn) = "en")
  }
}
"""


def _retry_delay(error: urllib.error.HTTPError, attempt: int) -> float:
    """Seconds to wait before the next attempt: ``Retry-After`` when given, else 2, 4, 8..."""
    retry_after = error.headers.get("Retry-After", "") if error.headers else ""
    delay = int(retry_after) if retry_after.isdigit() else 2 ** attempt
    return float(min(delay, MAX_RETRY_DELAY))


def run_query(
    query: str, attempts: int = MAX_ATTEMPTS, sleep: Callable[[float], object] = time.sleep
) -> list[Binding]:
    """POST ``query`` to the Wikidata endpoint and return the result bindings.

    Network errors, timeouts and the "busy" answers of the endpoint (429, 5xx)
    are retried up to ``attempts`` times; other errors are raised at once.
    """
    for attempt in range(1, attempts + 1):
        try:
            return _post_query(query)
        except urllib.error.HTTPError as error:
            if error.code not in RETRY_STATUSES or attempt == attempts:
                raise
            delay = _retry_delay(error, attempt)
        # IncompleteRead (an HTTPException): the endpoint cut a response at its 60 s limit
        except (urllib.error.URLError, http.client.HTTPException, TimeoutError, ConnectionError):
            if attempt == attempts:
                raise
            delay = float(min(2 ** attempt, MAX_RETRY_DELAY))
        sleep(delay)
    raise ValueError("attempts must be at least 1")


def _post_query(query: str) -> list[Binding]:
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
    bindings: list[Binding] = json.loads(body.decode("utf-8"))["results"]["bindings"]
    return bindings


def _entity_id(uri: str) -> str:
    entity = uri.rsplit("/", 1)[-1]
    if not (entity.startswith("Q") and entity[1:].isdigit()):
        raise ValueError(f"Unexpected Wikidata entity {uri!r}")
    return entity


def _parse_year(value: str, precision: str | None = None) -> int | None:
    """Return the historical year of a SPARQL ``xsd:dateTime`` such as ``-0036-01-01T00:00:00Z``.

    The Wikidata endpoint follows XSD 1.1, where year 0 is 1 BC: the Georgics,
    stored as 37 BC, come as ``-0036``.  Years are returned without year 0,
    negative for BC (-37).  ``None`` when the date is malformed or coarser than
    a decade (``precision`` 9 = year, 8 = decade, 7 = century).
    """
    if precision is not None and not (precision.isdigit() and int(precision) >= MIN_DATE_PRECISION):
        return None
    try:
        year = int(value[:value.index("-", 1)])
    except ValueError:
        return None
    return year - 1 if year <= 0 else year


EN_ADJECTIVE_SUFFIXES = ("ish", "ian", "an", "ese", "ch", "ic", "i")

# Citizenship -> (French demonyms, English demonyms) listed by Wikidata
Demonyms = dict[str, tuple[set[str], set[str]]]


def _capitalize(value: str) -> str:
    """Upper-case the first letter only: "South African", not "South african"."""
    return value[:1].upper() + value[1:]


def _pick_demonym(values: Iterable[str], locale: str) -> str:
    """Choose one demonym among the gendered / plural forms Wikidata lists.

    French keeps the shortest form (masculine singular, e.g. ``français``);
    English prefers singular adjectives (``British`` over ``Briton``).
    """
    def shortest(value: str) -> tuple[int, str]:
        return len(value), value

    values = list(values)
    if locale == "en_US":
        singular = [value for value in values if not value.endswith("s")] or list(values)
        adjectives = [value for value in singular if value.lower().endswith(EN_ADJECTIVE_SUFFIXES)]
        return _capitalize(min(adjectives or singular, key=shortest))
    return min(values, key=shortest).lower()


def known_nationalities(books: Iterable[Mapping[str, Any]] | None = None) -> dict[str, str]:
    """Return the ``{English: French}`` nationalities of ``books`` (by default the bundled catalogue)."""
    if books is None:
        books = load_builtin_books()[0]
    return {book["nationality"]["en_US"]: book["nationality"]["fr_FR"] for book in books}


def choose_nationality(
    demonyms: Demonyms, birth_countries: Iterable[str] = (), known: Mapping[str, str] | None = None
) -> dict[str, str] | None:
    """Return the ``{locale: demonym}`` nationality of an author, ``None`` without citizenship.

    Among several citizenships, the one of the country of birth wins (P. G.
    Wodehouse, born in England, later American, is British); otherwise the
    lowest Q-id, usually the best known country.  The translations already
    used in ``known`` (``{English: French}``) are preferred, so that a
    nationality keeps a single translation ("British" is "britannique", not
    "anglais").
    """
    if not demonyms:
        return None
    born = [country for country in demonyms if country in set(birth_countries)]
    country = min(born or demonyms, key=lambda q: int(q[1:]))
    fr_values, en_values = demonyms[country]
    known = known or {}
    english = sorted(en for en in map(_capitalize, en_values) if en in known)
    if english:
        return {"fr_FR": known[english[0]], "en_US": english[0]}
    by_french = {fr: en for en, fr in known.items()}
    french = sorted(fr for fr in (value.lower() for value in fr_values) if fr in by_french)
    if french:
        return {"fr_FR": french[0], "en_US": by_french[french[0]]}
    return {"fr_FR": _pick_demonym(fr_values, "fr_FR"), "en_US": _pick_demonym(en_values, "en_US")}


def map_genres(labels: Iterable[tuple[str, str]], vocabulary: GenreVocabulary) -> list[str]:
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


def parse_bindings(
    bindings: Iterable[Binding],
    vocabulary: GenreVocabulary | None = None,
    nationalities: Mapping[str, str] | None = None,
    untranslated_titles: bool = False,
) -> list[Record]:
    """Group SPARQL rows by work and return catalogue records.

    Genres are mapped onto ``vocabulary`` (by default the bundled one); a work
    without a known genre falls back on its form (novel, play...).
    Nationalities use the translations of ``nationalities`` (``{English:
    French}``, by default those of the bundled catalogue).  Works lacking a
    known genre or form, a nationality or a usable date are left out, and so
    are works without a French title unless ``untranslated_titles`` is true:
    their French title is then the English one, flagged by
    ``"title_untranslated": true``.
    """
    vocabulary = vocabulary or load_vocabulary()
    if nationalities is None:
        nationalities = known_nationalities()
    works: dict[str, dict[str, Any]] = {}
    for row in bindings:
        value = {key: cell["value"] for key, cell in row.items()}
        work = works.setdefault(_entity_id(value["work"]), {
            "title": {"fr_FR": value.get("titleFr"), "en_US": value["titleEn"]},
            "writers": {},
            "years": set(),
            "inceptions": set(),
            "pages": set(),
            "genres": {},
            "forms": {},
            "demonyms": {},
            "birth_countries": set(),
            "links": int(value["links"]) if value.get("links", "").isdigit() else 0,
            "publisher": None,
        })
        work["writers"].setdefault(value["author"], (value["writerFr"], value["writerEn"]))
        for key, years in (("date", work["years"]), ("inception", work["inceptions"])):
            year = _parse_year(value[key], value.get(key + "Precision")) if key in value else None
            if year is not None:
                years.add(year)
        # Page counts contain typos such as 940512: keep plausible ones
        if value.get("pages", "").isdigit() and 0 < int(value["pages"]) <= MAX_PAGES:
            work["pages"].add(int(value["pages"]))
        if "genreFr" in value:
            work["genres"].setdefault(value["genreFr"], value["genreEn"])
        if "formFr" in value:
            work["forms"].setdefault(value["formFr"], value["formEn"])
        if "demonymFr" in value:
            fr, en = work["demonyms"].setdefault(_entity_id(value["country"]), (set(), set()))
            fr.add(value["demonymFr"])
            en.add(value["demonymEn"])
        if "birthCountry" in value:
            work["birth_countries"].add(_entity_id(value["birthCountry"]))
        if "publisherFr" in value and work["publisher"] is None:
            work["publisher"] = {"fr_FR": value["publisherFr"], "en_US": value["publisherEn"]}

    records: list[Record] = []
    for entity, work in works.items():
        # Publication date first, creation date only when it is missing
        years = work["years"] or work["inceptions"]
        genres = map_genres(work["genres"].items(), vocabulary) or map_genres(work["forms"].items(), vocabulary)
        title = work["title"]
        # A French label that is the English title plus its subtitle is no translation either
        untranslated = title["fr_FR"] is None or title["fr_FR"].startswith(title["en_US"] + ":")
        if untranslated:
            if not untranslated_titles:
                continue
            title = {"fr_FR": title["en_US"], "en_US": title["en_US"]}
        nationality = choose_nationality(work["demonyms"], work["birth_countries"], nationalities)
        if not (genres and nationality and years):
            continue
        writers = list(work["writers"].values())
        pages = min(work["pages"]) if work["pages"] else None
        record: Record = {
            "wikidata_id": entity,
            "writer": {
                "fr_FR": ", ".join(fr for fr, _ in writers),
                "en_US": ", ".join(en for _, en in writers),
            },
            "nationality": nationality,
            "title": title,
            "genre": vocabulary.resolve(genres),
            "year": min(years),
            "pages": None if pages is None else {"fr_FR": pages, "en_US": pages},
            "publisher": work["publisher"],
        }
        if untranslated:
            record["title_untranslated"] = True
        # How well known the work is: its number of Wikipedia articles
        if work["links"]:
            record["popularity"] = work["links"]
        records.append(record)
    return records


# Finding a work from its title and author

# Items found by a search, or the work they are an edition of (P629), with the names of their authors
ITEM_AUTHORS_QUERY = """
SELECT ?item ?work ?author ?name WHERE {
  VALUES ?item { %s }
  # An edition leads to its work; an edition without one (P31 Q3331189) is no work
  { ?item wdt:P50 ?author . FILTER NOT EXISTS { ?item wdt:P629 [] } FILTER NOT EXISTS { ?item wdt:P31 wd:Q3331189 }
    BIND(?item AS ?work) }
  UNION { ?item wdt:P629 ?work . ?work wdt:P50 ?author . }
  { ?author rdfs:label ?name . FILTER(LANG(?name) IN ("en", "mul", "fr")) }
  UNION { ?author skos:altLabel ?name . FILTER(LANG(?name) IN ("en", "mul")) }
}
"""

# {item: (work, {author: {name keys}})}
ItemAuthors = dict[str, tuple[str, dict[str, set[str]]]]


def search_items(
    text: str, limit: int = SEARCH_RESULTS, attempts: int = MAX_ATTEMPTS, sleep: Callable[[float], object] = time.sleep
) -> list[str]:
    """Return the ids of the items whose label matches ``text`` and that have an author (P50)."""
    params = {"action": "query", "list": "search", "srsearch": f"{text} haswbstatement:P50",
              "srlimit": limit, "srnamespace": 0, "format": "json"}
    request = urllib.request.Request(f"{SEARCH_API}?{urllib.parse.urlencode(params)}",
                                     headers={"User-Agent": USER_AGENT})
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                payload = json.loads(response.read(MAX_RESPONSE_BYTES).decode("utf-8"))
            # A busy API answers {"error": {...}} with HTTP 200
            if "query" not in payload:
                raise ValueError(f"Wikidata search failed: {payload.get('error', payload)}")
            return [str(hit["title"]) for hit in payload["query"]["search"]]
        except (OSError, ValueError, http.client.HTTPException):
            if attempt == attempts:
                raise
            sleep(float(min(2 ** attempt, MAX_RETRY_DELAY)))
    raise ValueError("attempts must be at least 1")


def parse_item_authors(rows: Iterable[Binding]) -> ItemAuthors:
    """Return ``{item: (work, {author: {name keys}})}`` from the rows of ``ITEM_AUTHORS_QUERY``."""
    items: ItemAuthors = {}
    for row in rows:
        item = _entity_id(row["item"]["value"])
        _, authors = items.setdefault(item, (_entity_id(row["work"]["value"]), {}))
        authors.setdefault(_entity_id(row["author"]["value"]), set()).add(name_key(row["name"]["value"]))
    return items


def match_work(author_names: Iterable[str], hits: Iterable[str], items: ItemAuthors) -> tuple[str, str] | None:
    """Return ``(work, author)`` for the first search hit written by one of ``author_names``.

    Names are compared ignoring case, accents and punctuation.
    """
    wanted = {name_key(name) for name in author_names}
    for item in hits:
        if item not in items:
            continue
        work, authors = items[item]
        for author, names in authors.items():
            if names & wanted:
                return work, author
    return None


def exclude_known(records: Iterable[Record], known_books: Iterable[Mapping[str, Any]]) -> list[Record]:
    """Drop records already present in ``known_books``.

    A record is known when it has the same Wikidata id as a known book, or
    the same title (ignoring case, accents and a leading article) within
    ``YEAR_TOLERANCE`` years.
    """
    index = DuplicateIndex(known_books, year_tolerance=YEAR_TOLERANCE)
    return [record for record in records if record not in index]


def align_authors(records: Iterable[Record], known_books: Iterable[Mapping[str, Any]]) -> list[Record]:
    """Give the authors already in ``known_books`` their known name and nationality.

    Authors are matched on their English name, ignoring case, accents and
    punctuation, so that an author keeps a single nationality.
    """
    known = {name_key(pick(book["writer"], "en_US")): book for book in known_books}
    aligned = []
    for record in records:
        book = known.get(name_key(pick(record["writer"], "en_US")))
        aligned.append(record if book is None else dict(record, writer=book["writer"],
                                                         nationality=book["nationality"]))
    return aligned


def fetch_works(
    limit: int = 500,
    min_sitelinks: int = 30,
    pause: float = 1.0,
    log: Log = print,
    vocabulary: GenreVocabulary | None = None,
) -> list[Record]:
    """Fetch up to ``limit`` of the most linked literary works and return valid records."""
    limit = max(1, min(int(limit), MAX_LIMIT))
    min_sitelinks = max(0, int(min_sitelinks))

    candidates = run_query(CANDIDATES_QUERY % {"min_sitelinks": min_sitelinks})
    ranked = sorted(candidates, key=lambda row: -int(row["links"]["value"]))
    entities = list(dict.fromkeys(_entity_id(row["work"]["value"]) for row in ranked))
    log(f"{len(entities)} candidate works with >= {min_sitelinks} sitelinks")

    records: list[Record] = []
    for start in range(0, len(entities), BATCH_SIZE):
        if len(records) >= limit:
            break
        batch = entities[start:start + BATCH_SIZE]
        if start:
            time.sleep(pause)
        works = " ".join("wd:" + entity for entity in batch)
        rows = run_query(DETAILS_QUERY % {"works": works, "dates": DATES_PATTERN})
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


def import_into(store: BookStore, limit: int = 500, min_sitelinks: int = 30, log: Log = print) -> int:
    """Fetch works from Wikidata and replace the store's ``wikidata`` books with them."""
    builtin = [book for book in store.books.all() if book["source"] != SOURCE]
    vocabulary = load_vocabulary()
    records = exclude_known(fetch_works(limit, min_sitelinks, log=log, vocabulary=vocabulary), builtin)
    records = align_authors(records, builtin)
    return store.replace_source(SOURCE, records)

