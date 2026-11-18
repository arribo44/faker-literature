"""Fill the English page counts and publishers of the bundled books from the editions of Open Library.

Open Library (https://openlibrary.org, Internet Archive) describes the
English editions of most works.  The Internet Archive asserts no rights over
its catalogue data; only bibliographic facts are reused (publisher and number
of pages of an edition).

For each book whose ``en_US`` page count or publisher is missing, or whose
``en_US`` publisher works in another language (that of the original edition),
the Open Library work given by Wikidata (P648) is read, with its editions.
The earliest English edition that has both a page count and a publisher, and
is not older than the work, gives the values, so that the page count and the
publisher describe one real edition (usually the first edition of a work
written in English, the first translation of another one).  When a book only
lacks its page count, the edition must be one of its publisher's.

Large-print, audio and electronic editions, abridged versions, study guides
and on-demand reprints are left out.  A publisher unknown to the vocabulary
is added only when its place of publication is in an English-speaking country
(its ``country``).  The values typed by hand (``pages_estimated``,
``publisher_estimated``) are left alone.

Open Library asks API users not to bulk-download its data: the script reads
one work per second, identifies itself, and keeps what it read in a cache
(``--cache``), so that it is read only once.

Usage::

    python tools/literature_editor/update_openlibrary.py [--dry-run] [--cache FILE] [--limit N]
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import editor
import update_wikipedia

from faker_literature.importers.wikidata import _entity_id, run_query
from faker_literature.matching import name_key
from faker_literature.store import LOCALES, MAX_PAGES
from faker_literature.vocabulary import PUBLISHING_COUNTRIES, PublisherVocabulary, publisher_key

LOCALE = "en_US"
API = "https://openlibrary.org"
USER_AGENT = "faker-literature-catalogue-tools/1.0 (+https://github.com/arribo44/faker-literature)"
PAUSE = 1.0
ATTEMPTS = 5
EDITIONS_PER_PAGE = 500
MAX_EDITION_PAGES = 4
WIKIDATA_BATCH = 200
MIN_PAGES = 10
SOURCE = "Open Library"

OPEN_LIBRARY_QUERY = "SELECT ?work ?ol WHERE { VALUES ?work { %s } ?work wdt:P648 ?ol }"
OPEN_LIBRARY_WORK = re.compile(r"OL[1-9][0-9]*W")

# Editions that do not describe the usual book
OTHER_FORMATS = re.compile(r"audio|cassette|\bcd\b|mp3|e-?book|electronic|kindle|epub|large print|braille|microform",
                           re.IGNORECASE)
OTHER_TITLES = re.compile(r"large print|abridged|condensed|retold|adapted|graphic novel|study guide|summary|"
                          r"sparknotes|cliffs ?notes|notes on|workbook|coloring|colouring|teacher|readers? guide",
                          re.IGNORECASE)
# On-demand reprints, large-print and audio publishers: not the usual publisher of a work
REPRINT_PUBLISHERS = {
    "createspace", "createspaceindependentpublishingplatform", "independentlypublished", "lulu", "lulucom",
    "kessinger", "kessingerpublishing", "bibliolife", "nabupress", "forgottenbooks", "generalbooks",
    "bibliobazaar", "dodopress", "echolibrary", "tredition", "digireads", "digireadscom", "readaclassic",
    "booksondemand", "bookjungle", "wildsidepress", "aegitas", "indypublish", "1stworldlibrary", "quillpen",
    "thorndikepress", "ghall", "gkhall", "chivers", "chiverspress", "isis", "isislargeprint", "wheelerpublishing",
    "ulverscroft", "centerpoint", "centerpointlargeprint", "largeprintpress", "beelerlargeprint",
    "recordedbooks", "booksontape", "brillianceaudio", "blackstoneaudio", "audible", "audiblestudios",
    "dreamscapemedia", "tantoraudio", "randomhouseaudio", "highbridge", "naxosaudiobooks", "listeninglibrary",
    "harperaudio", "simonschusteraudio", "macmillanaudio", "hachetteaudio", "penguinaudio",
}
BOOK_CLUB = re.compile(r"book\W*(?:of\W*the\W*month\W*)?club|literary guild|reader'?s digest|^bca$|"
                       r"book club associates", re.IGNORECASE)
# Words that do not tell publishers apart: "Little, Brown and Co." is Little, Brown
CORPORATE_SUFFIX = re.compile(r"(?:[,\s]+(?:&|and)?\s*(?:inc|incorporated|co|company|corp|corporation|ltd|limited|"
                              r"llc|plc|pub|publishers?|publishing(?:\s+(?:company|co|group|house))?)\.?)+$",
                              re.IGNORECASE)
# What follows a publisher's name: "Knopf; [distributed by Random House]", "Harper, an imprint of HarperCollins"
NAME_TAIL = re.compile(r"\s*(?:[;\[/]|,\s*an imprint of|:\s*distributed).*$", re.IGNORECASE)
# Imprint statements of old books, not publishers' names: "Printed for Walker and Edwards"
IMPRINT_STATEMENT = re.compile(r"^(?:printed|published|sold|for)\b|\d", re.IGNORECASE)
MAX_NEW_NAME = 40
# Words of a publisher's name that are not those of its founder: "Henry Holt and Company" is Henry Holt
NAME_WORDS = re.compile(r"[^\W\d_][\w'’-]*")
NOT_NAME_WORDS = {"and", "company", "co", "inc", "sons", "son", "books", "press", "publishing", "publishers",
                  "ltd", "limited", "corporation", "group", "pub"}
# Least similarity of two keys of at least that length for a typo ("Farrar Strauss Giroux")
TYPO_SIMILARITY, TYPO_MIN_LENGTH = 0.9, 10

# Places of publication of the English editions, and their country
ENGLISH_PLACES = {
    **dict.fromkeys([
        "newyork", "nyc", "boston", "philadelphia", "chicago", "gardencity", "sanfrancisco", "losangeles",
        "newhaven", "princeton", "indianapolis", "washington", "seattle", "minneapolis", "bloomington",
        "englewoodcliffs", "westport", "baltimore", "austin", "berkeley", "nashville", "grandrapids", "denver",
        "neworleans", "lincoln", "norman", "atlanta", "kansascity", "stpaul", "evanston", "hoboken",
        "upper saddle river".replace(" ", ""), "mineola", "cambridgemass", "stamford", "pittsburgh", "cleveland",
        "detroit", "providence", "durham", "chapelhill", "ithaca", "columbus", "portland", "sandiego", "dallas",
        "houston", "usa", "us", "unitedstates", "unitedstatesofamerica", "ny", "mass", "calif", "nj", "conn", "ill",
    ], "US"),
    **dict.fromkeys([
        "london", "edinburgh", "glasgow", "oxford", "cambridge", "harmondsworth", "middlesex", "manchester",
        "birmingham", "leeds", "liverpool", "bristol", "brighton", "basingstoke", "harlow", "sevenoaks",
        "england", "uk", "unitedkingdom", "greatbritain", "scotland", "wales", "gb",
    ], "GB"),
    **dict.fromkeys(["toronto", "vancouver", "ottawa", "canada"], "CA"),
    **dict.fromkeys(["sydney", "melbourne", "brisbane", "adelaide", "perth", "australia"], "AU"),
    **dict.fromkeys(["dublin", "cork", "ireland"], "IE"),
    **dict.fromkeys(["auckland", "wellington", "newzealand"], "NZ"),
    **dict.fromkeys(["newdelhi", "delhi", "bombay", "mumbai", "calcutta", "kolkata", "madras", "chennai", "india"],
                    "IN"),
    **dict.fromkeys(["capetown", "johannesburg", "southafrica"], "ZA"),
}


def place_country(place):
    """Return the English-speaking country of a place of publication ("New York, N.Y.", "London"), or ``None``.

    The place is read part by part ("Cambridge, Mass." is in the United
    States); a place of another country gives ``None``.
    """
    parts = [name_key(part) for part in re.split(r"[,;:()\[\]]", place) if name_key(part)]
    if len(parts) > 1 and parts[-1] in ENGLISH_PLACES:
        return ENGLISH_PLACES[parts[-1]]  # the state or the country
    for part in parts:
        if part in ENGLISH_PLACES:
            return ENGLISH_PLACES[part]
    return None


def _year(text):
    years = [int(year) for year in re.findall(r"(?<![0-9])(1[0-9]{3}|20[0-9]{2})(?![0-9])", text or "")]
    return min(years) if years else None


def simplify(entry):
    """Keep what the script needs of an Open Library edition."""
    pages = entry.get("number_of_pages")
    return {
        "key": entry.get("key", ""),
        "title": " ".join(filter(None, [entry.get("title"), entry.get("subtitle"), entry.get("edition_name")])),
        "languages": [language.get("key", "").rsplit("/", 1)[-1] for language in entry.get("languages", [])],
        "pages": pages if isinstance(pages, int) else None,
        "publishers": [name for name in entry.get("publishers", []) if isinstance(name, str)],
        "places": [place for place in entry.get("publish_places", []) if isinstance(place, str)],
        "year": _year(entry.get("publish_date")),
        "format": entry.get("physical_format") or "",
    }


def usable(edition, work_year):
    """Whether ``edition`` is a usual English edition with a page count and a publisher, not older than the work."""
    if "eng" not in edition["languages"] or not edition["publishers"] or edition["year"] is None:
        return False
    if edition["pages"] is None or not MIN_PAGES <= edition["pages"] <= MAX_PAGES:
        return False
    if edition["year"] < work_year or OTHER_FORMATS.search(edition["format"]) or OTHER_TITLES.search(edition["title"]):
        return False
    publisher = edition["publishers"][0]
    return name_key(publisher) not in REPRINT_PUBLISHERS and not BOOK_CLUB.search(publisher)


class OpenLibraryPublishers:
    """Map the publisher names of Open Library onto the ``publishers`` vocabulary, adding English-speaking ones."""

    def __init__(self, vocabulary: PublisherVocabulary):
        self.vocabulary = vocabulary
        self.by_key = {}
        # Founders' names: "h|holt" for Henry Holt and Company, "holt" for its surname alone
        self.by_initials, self.by_surname = {}, {}
        for publisher_id, publisher in sorted(vocabulary.publishers.items()):
            name = publisher["name"]
            for label in [*(name.values() if isinstance(name, dict) else [name]), *publisher.get("aliases", [])]:
                self._register(publisher_id, label, publisher.get("country"))
        self.added = []

    def _register(self, publisher_id, label, country):
        # Of the publishers sharing a key ("Pocket", "Pocket Books"), prefer an English-speaking one
        known = self.by_key.get(self.key(label))
        english = PUBLISHING_COUNTRIES[LOCALE]
        if known is None or (country in english
                             and self.vocabulary.publishers[known].get("country") not in english):
            self.by_key[self.key(label)] = publisher_id
        founder = self.founder(label)
        if founder:
            initials, surname = founder
            for index, key in ((self.by_initials, f"{initials}|{surname}"), (self.by_surname, surname)):
                # A key shared by two publishers ("Lippincott") names none of them
                index[key] = publisher_id if index.get(key, publisher_id) == publisher_id else None

    @staticmethod
    def founder(name):
        """Return ``(initials, surname)`` of a publisher named after a person ("Henry Holt and Company"), or ``None``.

        Only names whose words before the surname are capitalized given names
        or initials qualify: "W. W. Norton & Company" gives ``("ww", "norton")``,
        "Grove Press" ``None``.
        """
        words = NAME_WORDS.findall(name)
        while words and words[-1].casefold() in NOT_NAME_WORDS:
            words.pop()
        if len(words) < 2 or any(word.casefold() in NOT_NAME_WORDS for word in words):
            return None
        given, surname = words[:-1], words[-1]
        if not all(word[:1].isupper() for word in words) or len(given) > 3:
            return None
        return "".join(word[0] for word in given).casefold(), name_key(surname)

    @staticmethod
    def clean(name):
        """The publisher's name alone ("Knopf; [distributed by Random House" -> "Knopf")."""
        return NAME_TAIL.sub("", name).strip(" ,;:[]")

    @staticmethod
    def display(name):
        """The name without its corporate suffix and stray punctuation ("Little, Brown and Co." -> "Little, Brown")."""
        name = name.strip(" ,;:[]")
        return CORPORATE_SUFFIX.sub("", name).strip(" ,;:") or name

    @staticmethod
    def key(name):
        """"Chatto and Windus" and "Chatto & Windus", "Bantam" and "Bantam Books" are one publisher."""
        return publisher_key(name)

    def resolve(self, name, places=()):
        """Return the vocabulary id of the publisher ``name``, adding it when its place is English-speaking.

        A known publisher of another language than English gives ``None``.
        """
        name = self.clean(name)
        if not name:
            return None
        known = self.known(name)
        if known:
            return known if self.vocabulary.publishes_in(self.vocabulary.name(known, LOCALE), LOCALE) else None
        countries = Counter(country for place in places if (country := place_country(place)))
        display = self.display(name)
        if not countries or IMPRINT_STATEMENT.search(display) or len(display) > MAX_NEW_NAME:
            return None
        country = countries.most_common(1)[0][0]
        if self.vocabulary.match(display):
            return self.vocabulary.match(display)
        publisher_id = self.vocabulary.add(display, country=country)
        self._register(publisher_id, display, country)
        self.added.append(publisher_id)
        return publisher_id


    def known(self, name):
        """Return the id of a known publisher called ``name``, or ``None``.

        Tried in turn: its name or alias, the words that do not tell
        publishers apart ("Little, Brown and Co."), the initials of its
        founder ("J. Cape" is Jonathan Cape), his surname alone ("Norton"),
        and a typo ("Farrar Strauss Giroux").
        """
        known = self.vocabulary.match(name) or self.by_key.get(self.key(self.display(name)))
        if known:
            return known
        words = NAME_WORDS.findall(self.display(name))
        while len(words) > 1 and words[-1].casefold() in NOT_NAME_WORDS:
            words.pop()  # "G. Routledge & Sons"
        if len(words) >= 2 and all(len(word) == 1 for word in words[:-1]):
            known = self.by_initials.get("".join(words[:-1]).casefold() + "|" + name_key(words[-1]))
        elif len(words) == 1:
            known = self.by_surname.get(name_key(words[0]))
            if known is None and name_key(words[0]) in self.by_surname:
                return None  # the surname of several publishers: none of them
        if known:
            return known
        key = self.key(name)
        if len(key) >= TYPO_MIN_LENGTH:
            close = difflib.get_close_matches(key, [k for k in self.by_key if len(k) >= TYPO_MIN_LENGTH], n=1,
                                              cutoff=TYPO_SIMILARITY)
            if close:
                return self.by_key[close[0]]
        return None


def _request(url, sleep=time.sleep):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    for attempt in range(ATTEMPTS):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            if error.code not in (429, 500, 502, 503, 504) or attempt == ATTEMPTS - 1:
                raise
            retry_after = error.headers.get("Retry-After", "") if error.headers else ""
            sleep(int(retry_after) if retry_after.isdigit() else 10 * 2 ** attempt)
    return None


def fetch_editions(work, sleep=time.sleep):
    """Return the simplified editions of the Open Library work ``work`` ("OL45804W")."""
    editions, url = [], f"{API}/works/{work}/editions.json?limit={EDITIONS_PER_PAGE}"
    for _ in range(MAX_EDITION_PAGES):
        answer = _request(url, sleep)
        sleep(PAUSE)
        if not answer:
            break
        editions += [simplify(entry) for entry in answer.get("entries", [])]
        following = (answer.get("links") or {}).get("next")
        if not following:
            break
        url = urllib.parse.urljoin(API, following)
    return editions


def targets(data):
    """Return the books whose English values Open Library may fill, with what they need."""
    vocabulary = PublisherVocabulary(data["publishers"])
    found = []
    for author in data["authors"]:
        for book in author["books"]:
            needed = update_wikipedia.needs(book, vocabulary, LOCALE)
            if needed and book.get("wikidata_id"):
                found.append((book, needed))
    return found


def collect(data, cache, limit=None, log=print, sleep=time.sleep):
    """Fill ``cache`` (``{"works": {qid: [OL…W]}, "editions": {OL…W: [...]}}``) for the books to complete."""
    ids = sorted({book["wikidata_id"] for book, _ in targets(data)})
    works = cache.setdefault("works", {})
    missing = [qid for qid in ids if qid not in works]
    for start in range(0, len(missing), WIKIDATA_BATCH):
        batch = missing[start:start + WIKIDATA_BATCH]
        rows = run_query(OPEN_LIBRARY_QUERY % " ".join("wd:" + qid for qid in batch))
        for qid in batch:
            works[qid] = []
        for row in rows:
            value = row["ol"]["value"]
            if OPEN_LIBRARY_WORK.fullmatch(value):
                works[_entity_id(row["work"]["value"])].append(value)
    editions = cache.setdefault("editions", {})
    wanted = sorted({work for qid in ids for work in works.get(qid, [])} - set(editions))
    if limit is not None:
        wanted = wanted[:limit]
    log(f"{len(wanted)} Open Library works to read")
    for index, work in enumerate(wanted, 1):
        editions[work] = fetch_editions(work, sleep)
        if index % 50 == 0:
            log(f"  {index} / {len(wanted)}")
    return cache


def choose(book, needed, work_editions, publishers):
    """Return ``(pages, publisher id)`` of the edition that fills ``needed``, or ``None``."""
    current = (book.get("publisher") or {}).get(LOCALE)
    candidates = []
    for edition in work_editions:
        if not usable(edition, book["year"]):
            continue
        publisher_id = publishers.resolve(edition["publishers"][0], edition["places"])
        if publisher_id is None:
            continue
        # Only the page count is missing: it must describe an edition of the book's publisher
        if "publisher" not in needed and publisher_id != current:
            continue
        candidates.append((edition["year"], edition["key"], edition["pages"], publisher_id))
    if not candidates:
        return None
    _, _, pages, publisher_id = min(candidates)
    return pages, publisher_id


def update(data, cache):
    """Fill or correct the English pages and publishers from the cached editions; return what happened."""
    report = Counter()
    vocabulary = PublisherVocabulary(data["publishers"])
    publishers = OpenLibraryPublishers(vocabulary)
    for book, needed in targets(data):
        work_editions = [edition for work in cache.get("works", {}).get(book["wikidata_id"], [])
                         for edition in cache.get("editions", {}).get(work, [])]
        if not work_editions:
            report["no Open Library editions"] += 1
            continue
        chosen = choose(book, needed, work_editions, publishers)
        if chosen is None:
            report["no usable English edition"] += 1
            continue
        pages, publisher_id = chosen
        values = {"pages": pages, "publisher": publisher_id}
        # A new publisher comes with the page count of its edition, unless that count is an estimate
        fields = set(needed) | ({"pages"} if "publisher" in needed and not book.get("pages_estimated") else set())
        for field in sorted(fields):
            current = book.get(field) or {locale: None for locale in LOCALES}
            previous = current.get(LOCALE)
            if previous == values[field]:
                continue
            current[LOCALE] = values[field]
            book[field] = current
            report[f"{field}[{LOCALE}] {'filled' if previous is None else 'replaced'}"] += 1
    dropped = editor.prune_publishers(data)
    report["publishers added"] = len([publisher_id for publisher_id in publishers.added if publisher_id not in dropped])
    report["publishers dropped"] = len(set(dropped) - set(publishers.added))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--catalogue", type=Path, default=editor.CATALOGUE_PATH)
    parser.add_argument("--dry-run", action="store_true", help="report without writing the catalogue")
    parser.add_argument("--cache", type=Path, help="JSON file keeping the editions read from Open Library")
    parser.add_argument("--limit", type=int, help="read LIMIT Open Library works at most")
    args = parser.parse_args(argv)

    data = editor.load_catalogue(args.catalogue)
    cache = json.loads(args.cache.read_text(encoding="utf-8")) if args.cache and args.cache.exists() else {}
    try:
        collect(data, cache, args.limit)
    finally:
        if args.cache:
            args.cache.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    report = update(data, cache)
    print(dict(report))
    if not args.dry_run:
        editor.save_catalogue(data, args.catalogue)
        print(f"catalogue written to {args.catalogue}")


if __name__ == "__main__":
    main()
