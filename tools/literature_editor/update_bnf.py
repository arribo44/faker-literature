"""Fill the French page counts and publishers of the bundled books from the catalogue of the BnF.

The general catalogue of the Bibliothèque nationale de France (SRU API,
https://catalogue.bnf.fr/api) describes the French editions of most works.
Its records are reused under the Licence Ouverte / Open Licence (Etalab 2.0),
which requires citing the source: "Bibliothèque nationale de France, catalogue
général".

For each book whose French title is a translation (not ``title_untranslated``)
and whose ``fr_FR`` page count or publisher is missing, or whose ``fr_FR``
publisher is that of the original, foreign edition, the printed texts in French
(UNIMARC 101 $a ``fre``) found by the surname of its author and having the
same title (ignoring case, accents, punctuation and a leading article) are read.
The publisher of most of these editions is the usual French publisher of the
work; its earliest edition with a single volume gives the page count, so that
the page count and the publisher describe one real edition.  Large-print
editions are left out.

The page counts and publishers typed by hand (``pages_estimated``,
``publisher_estimated``) are left alone, except a French publisher typed by
hand that is a foreign one (the publisher of the original edition): a real
French publisher replaces it, and the flag stays for the English value.  Publishers are mapped onto the
``publishers`` vocabulary (names, aliases, and the abbreviations of the BnF
listed in ``BNF_NAMES``); an unknown publisher is added to it.

Books whose French title is the English one (flagged ``title_untranslated``,
or not) have no French title to look up: with ``--titles``, their French
translations are looked up by their original title (UNIMARC 454 $t) instead.
``--propose-titles FILE`` writes the French titles found, for review: the
most frequent title of the translations, with French
capitals ("L'Architecture du bonheur").  ``--apply-titles FILE`` gives the
books the reviewed titles (delete a wrong proposal, or correct its
``fr_FR``) and drops their flag; their French page count and publisher then
come from the same translations.

Usage::

    python tools/literature_editor/update_bnf.py [--dry-run] [--cache FILE] [--collect] [--limit N] [--titles]
    python tools/literature_editor/update_bnf.py --cache FILE --propose-titles PROPOSALS.json
    python tools/literature_editor/update_bnf.py --cache FILE --apply-titles PROPOSALS.json [--dry-run]

``--cache`` keeps the editions read from the BnF in FILE, so that a second run
does not query it again; ``--collect`` only fills the cache.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import editor

from faker_literature.matching import name_key, title_key
from faker_literature.store import MAX_PAGES
from faker_literature.vocabulary import PublisherVocabulary

ENDPOINT = "https://catalogue.bnf.fr/api/SRU"
USER_AGENT = "faker-literature-tools/0.4 (catalogue maintenance)"
MAX_RECORDS = 50
PAUSE = 1.0
TIMEOUT = 90
ATTEMPTS = 4
MIN_PAGES = 10
MARC = "{info:lc/xmlns/marcxchange-v2}"
FRANCOPHONE = {"FR", "BE", "CH", "CA", "LU", "MC"}
SOURCE = "Bibliothèque nationale de France, catalogue général"

# Places of publication of the French editions, and their country
PLACES = {
    **dict.fromkeys([
        "paris", "lyon", "arles", "vanves", "evreux", "grenoble", "neuillysurseine", "vauvert", "lunel", "marseille",
        "charentonlepont", "nantes", "versailles", "tours", "montrouge", "laseynesurmer", "levalloisperret", "pantin",
        "bagneux", "forbach", "lemans", "rennes", "toulouse", "toulon", "cergy", "poitiers", "besancon", "evry",
        "nice", "elbeuf", "cenon", "sadirac", "montdemarsan", "chamonix", "saintmartinduvar", "issylesmoulineaux",
        "rueilmalmaison", "saintjulienengenevois", "bordeaux", "lille", "strasbourg", "montpellier", "rouen",
        "nancy", "dijon", "angers", "clermontferrand", "limoges", "caen", "reims", "metz", "avignon",
        "aixenprovence", "latourdaigues", "saintlaurentduvar", "carrieressurseine", "boulognebillancourt",
        "malakoff", "ivrysurseine", "vincennes", "lagnysurmarne", "auverssuroise", "champignysurmarne",
        "saintquentinfallavier", "lafleche", "lambersart", "orleans", "amiens", "brest", "laval", "lorient", "quimper",
    ], "FR"),
    **dict.fromkeys(["bruxelles", "brussels", "verviers", "alleur", "tournai", "liege", "namur",
                     "louvainlaneuve", "mons", "charleroi", "gand"], "BE"),
    **dict.fromkeys(["geneve", "lausanne", "neuchatel", "vevey", "fribourg", "sion"], "CH"),
    **dict.fromkeys(["montreal", "quebec", "outremont"], "CA"),
    "monaco": "MC", "luxembourg": "LU",
}
# "Montréal (Québec)", "Alleur (Belgique)": the country in brackets
PLACE_COUNTRIES = {"quebec": "CA", "canada": "CA", "belgique": "BE", "suisse": "CH", "france": "FR"}
# Large print, audio and braille editions do not describe the usual book
LARGE_PRINT = re.compile(r"grands?\s+caract|gros\s+caract|large|braille|audio", re.IGNORECASE)
# "2 vol." and more: the page count of one volume is not that of the work
VOLUMES = re.compile(r"\b([2-9]|[1-9][0-9])\s*vol", re.IGNORECASE)
# "286 p.", "1 vol. (377 p.)", "XXVI-1364 p.", "359 p.-[4] p. de cartes": the main page count
PAGES = re.compile(r"(?:^|[\s(,-])(\d{2,5})\s*p\b")
YEAR = re.compile(r"\b(1[4-9]\d\d|20\d\d)\b")

# Names of the BnF, by loose key (see ``loose_key``), and the name of the publisher they stand for; initials
# ("R. Laffont", "A. Michel") are handled by ``BnfPublishers`` without being listed here
BNF_NAMES = {
    "uniongeneralededitions": "10/18", "uniongeneraleded": "10/18", "uge": "10/18",
    "garnierflammarion": "GF Flammarion",
    "pkj": "Pocket jeunesse", "pocketjeunessepkj": "Pocket jeunesse",
    "nationale": "Imprimerie nationale", "imprimerienationale": "Imprimerie nationale",
    "bernardgrasset": "Grasset",
    "bookkinginternational": "Bookking international",
    "bodbooksondemand": "Books on Demand", "booksondemand": "Books on Demand",
    # The first name of Gallimard, kept by the BnF for its editions of 1911-1919
    "nouvellerevuefrancaise": "Gallimard",
}
# Publishers of large-print editions, left out like the large-print collections
LARGE_PRINT_PUBLISHERS = {"avuedoeil", "voirdepres", "loupe", "feryane", "libradiffusio", "pointdeux",
                          "universalmusicfrance"}
# Book clubs and cheap or on-demand reprints: the usual publisher of a work is the one they reprint
SECONDARY_PUBLISHERS = {
    "franceloisirs", "legrandlivredumois", "grandlivredumois", "rombaldi", "famot", "rencontre", "noyelles",
    "cercledubibliophile", "clubfrancaisdulivre", "editoservice", "selectiondureadersdigest", "clubdulivre",
    "clubdulivredumois", "cerclenouveaudulivre", "clubdesamisdulivre", "livredeparis", "fabbri", "maxilivres",
    "bookkinginternational", "booksondemand", "noyellesfranceloisirs", "cultureartloisirs", "editionspeciale",
    "hachettecollections",
}


# The BnF catalogue

def _query(title, surname):
    def words(text):
        return " ".join(re.findall(r"\w+", text))
    return (f'bib.title all "{words(title)}" and bib.author all "{words(surname)}" '
            f'and bib.doctype any "a" and bib.language any "fre"')


def search(title, surname, sleep=time.sleep):
    """Return the UNIMARC XML of the French printed texts called ``title`` by an author called ``surname``."""
    params = urllib.parse.urlencode({
        "version": "1.2", "operation": "searchRetrieve", "recordSchema": "unimarcxchange",
        "maximumRecords": MAX_RECORDS, "query": _query(title, surname),
    })
    request = urllib.request.Request(f"{ENDPOINT}?{params}", headers={"User-Agent": USER_AGENT})
    for attempt in range(1, ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                return response.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == ATTEMPTS:
                raise
            sleep(2 ** attempt)
    raise AssertionError("unreachable")


def _subfields(record, tag, code):
    return [(subfield.text or "").strip() for field in record.iter(f"{MARC}datafield") if field.get("tag") == tag
            for subfield in field.iter(f"{MARC}subfield") if subfield.get("code") == code]


def parse_pages(extent):
    """Return the page count of a UNIMARC 215 $a such as ``1 vol. (377 p.)``, or ``None``."""
    if not extent or VOLUMES.search(extent):
        return None
    match = PAGES.search(extent)
    if not match:
        return None
    pages = int(match.group(1))
    return pages if MIN_PAGES <= pages <= MAX_PAGES else None


def parse_records(xml):
    """Return the editions described by an SRU answer, as plain dictionaries."""
    editions = []
    root = ET.fromstring(xml)
    for record in root.iter(f"{MARC}record"):
        publication = "210" if _subfields(record, "210", "c") else "214"
        dates = _subfields(record, publication, "d")
        year = YEAR.search(" ".join(dates))
        editions.append({
            "id": next((field.text for field in record.iter(f"{MARC}controlfield") if field.get("tag") == "001"), None),
            "languages": _subfields(record, "101", "a"),
            "titles": _subfields(record, "200", "a"),
            "original_titles": _subfields(record, "454", "t"),
            "authors": _subfields(record, "700", "a") + _subfields(record, "701", "a"),
            "publishers": _subfields(record, publication, "c"),
            "places": _subfields(record, publication, "a"),
            "year": int(year.group(1)) if year else None,
            "pages": parse_pages(" ".join(_subfields(record, "215", "a"))),
            "extent": " ".join(_subfields(record, "215", "a") + _subfields(record, "215", "c")),
            "collections": _subfields(record, "225", "a"),
        })
    return editions


# Matching the editions of a book

def surname(name):
    """Return the last word of an author name, the one the BnF files authors under ("Lehane")."""
    words = re.findall(r"[\w'-]+", name)
    return words[-1] if words else name


def matches(edition, title):
    """Whether ``edition``, found by its author, is a French edition of the work called ``title``.

    The search already asks for the author: its index knows the forms of the
    name that the record itself may not show ("Pouchkine" for "Puškin").
    """
    if "fre" not in edition["languages"]:
        return False
    if not any(title_key(candidate) == title_key(title) for candidate in edition["titles"][:1]):
        return False
    return _ordinary_print(edition)


def matches_original(edition, original_title):
    """Whether ``edition``, found by its author, is a French translation of the work called ``original_title``.

    Bilingual editions are left out: their title may be the original one.
    """
    if set(edition["languages"]) != {"fre"}:
        return False
    if not any(title_key(candidate) == title_key(original_title) for candidate in edition.get("original_titles", [])):
        return False
    return _ordinary_print(edition)


# Only a definite article gives a capital to the noun that follows ("Une saison en enfer")
FRENCH_ARTICLE = re.compile(r"^(?:(le|la|les)\s+|(l'))(\S)", re.IGNORECASE)


def french_title(title):
    """Return a BnF title ("l'architecture du bonheur") with the capitals of French titles.

    The first word takes a capital, and so does the noun after a leading
    definite article ("L'Architecture du bonheur", "Le Vol du corbeau"); the
    BnF keeps the capitals of proper nouns.  Apostrophes are straight, as in
    the catalogue.
    """
    title = re.sub(r"\s+", " ", title).replace("’", "'")
    # "Grand'-Rue (Main street)", "Robert le Rouge, ou ..., par l'auteur de ..., traduit de l'anglais"
    title = re.sub(r"\s*[(\[][^)\]]*[)\]]", "", title)
    title = re.split(r"\s*,?\s+(?:par l'auteur|traduit|trad\.|traduction)\b", title, maxsplit=1)[0]
    title = title.strip(" .,;:/")
    if not title:
        return title
    title = title[0].upper() + title[1:]
    match = FRENCH_ARTICLE.match(title)
    if match:
        article = match.group(1) or match.group(2)
        start = match.end() - 1
        title = article[0].upper() + article[1:] + title[len(article):start] + title[start].upper() + title[start + 1:]
    return title


def _ordinary_print(edition):
    """Whether ``edition`` is neither in large print, nor in braille, nor an audio book."""
    texts = " ".join(edition["collections"]) + " " + edition["extent"]
    publishers = {loose_key(name) for name in edition["publishers"]}
    return not LARGE_PRINT.search(texts) and not publishers & LARGE_PRINT_PUBLISHERS


NAME_NOISE = re.compile(
    r"^(?:les |la |le |l')?(?:éditions |editions |éd\. |ed\. |éd |librairie |presses |impr\. )?"
    r"(?:du |de la |des |de l')?"
    r"|(?:,? (?:éditeur|éditeurs|éd\.|éditions|editions|inc\.?|ltd\.?|sa|s\.a\.))+$",
    re.IGNORECASE)
# Leading initials of given names: "R. ", "J.-C. ", "Ch. ", but not "Éd." (éditions)
INITIALS = re.compile(r"^(?:(?![ÉE]d\.)[A-ZÉ][a-z]?\.(?:-[A-ZÉ]\.)?\s*)+(?=\S)")
# "(impr. de Chantenay)", quotes: not part of the name
NAME_EXTRAS = re.compile(r"\s*\([^)]*\)|[\"«»]")


def clean_name(name):
    """Return a publisher name without "Éditions", "éditeur", a leading article or "du" ("Éd. du Seuil" -> "Seuil")."""
    name = NAME_EXTRAS.sub("", name).strip(" ,;:[]").replace(" et ", " & ")
    previous = None
    while previous != name:
        previous, name = name, NAME_NOISE.sub("", name.strip()).strip()
    return name


def loose_key(name):
    """Compare publisher names regardless of "Éditions", "éditeur", "et" / "&" ("Payot et Rivages")."""
    return name_key(clean_name(name))


def initials_key(name):
    """``"r|laffont"`` for "Robert Laffont" and for "R. Laffont": initials of the given names, and the surname."""
    words = clean_name(name).replace(".", ". ").replace("-", " ").split()
    if len(words) < 2:
        return None
    return "".join(word[0] for word in words[:-1]).casefold() + "|" + name_key(words[-1])


class BnfPublishers:
    """Map the publisher names of the BnF onto the ``publishers`` vocabulary, adding the unknown ones.

    A name is looked up as it is, by :func:`loose_key`, through ``BNF_NAMES``,
    by its initials ("R. Laffont" is Robert Laffont), and without its
    initials ("E. Flammarion" is Flammarion).
    """

    def __init__(self, vocabulary: PublisherVocabulary):
        self.vocabulary = vocabulary
        self.by_loose = {}
        self.by_initials = {}
        self.by_surname = {}
        for publisher_id, publisher in vocabulary.publishers.items():
            name = publisher["name"]
            for label in [*(name.values() if isinstance(name, dict) else [name]), *publisher.get("aliases", [])]:
                self._register(publisher_id, label, publisher.get("country"))
        self.added = []

    def _register(self, publisher_id, label, country):
        # Prefer the francophone publisher of a name (Pocket rather than Pocket Books)
        for index, key in ((self.by_loose, loose_key(label)), (self.by_initials, initials_key(label)),
                           (self.by_surname, self._surname(label))):
            if key and (key not in index or country in FRANCOPHONE):
                index[key] = publisher_id

    @staticmethod
    def canonical(name):
        """Return the name a BnF name stands for: listed in ``BNF_NAMES``, or without its initials."""
        name = NAME_EXTRAS.sub("", name).strip(" ,;:[]")
        if loose_key(name) in BNF_NAMES:
            return BNF_NAMES[loose_key(name)]
        return INITIALS.sub("", name) if INITIALS.match(name) else name

    def key(self, name):
        """Group the spellings of an unknown publisher ("A. Hatier", "Hatier")."""
        return loose_key(self.canonical(name))

    @staticmethod
    def _surname(name):
        """The surname of a publisher named after a person ("Fernand Aubier" -> "aubier"), else ``None``.

        Only a first name followed by a surname, both capitalized, qualifies:
        "Mango jeunesse" or "Hachette littératures" do not.
        """
        words = clean_name(name).split()
        if len(words) == 2 and all(word[:1].isupper() for word in words) and re.fullmatch(r"[^\W\d_]{3,}(-[^\W\d_]+)?",
                                                                                         words[0]):
            return name_key(words[1])
        return None

    def resolve(self, name, create=False, country=None):
        """Return the vocabulary id of the publisher ``name``, adding it with ``create``."""
        name = NAME_EXTRAS.sub("", name).strip(" ,;:[]")
        # "[s.n.]": no publisher named; "Paris": the place given as the publisher
        if not name or name.casefold() in {"s.n.", "sn"} or name_key(name) in PLACES:
            return None
        canonical = self.canonical(name)
        known = (self.vocabulary.match(name) or self.by_loose.get(loose_key(name))
                 or (self.by_initials.get(initials_key(name)) if INITIALS.match(name) else None)
                 or self.vocabulary.match(canonical) or self.by_loose.get(loose_key(canonical))
                 # "Fernand Aubier" is Aubier, "Pauvert" is Jean-Jacques Pauvert
                 or self.by_loose.get(self._surname(canonical)) or self.by_surname.get(loose_key(canonical)))
        if known or not create:
            return known
        display = re.sub(r"^[ÉéEe]d\.\s*", "Éditions ", canonical)
        display = re.sub(r"\s+[ÉéEe]d\.$", "", display)
        display = display[:1].upper() + display[1:]
        publisher_id = self.vocabulary.add(display, country=country)
        self._register(publisher_id, display, country)
        self.added.append(publisher_id)
        return publisher_id


def place_country(place):
    """Return the country of a place of publication ("Paris", "72-La Flèche", "Montréal (Québec)"), or ``None``."""
    place = place.strip("[](), ")
    if not place or place.casefold().startswith(("impr.", "s.l", "s. l")):
        return None  # a place of printing, or no place
    bracket = re.search(r"\(([^)]*)\)", place)
    if bracket and name_key(bracket.group(1)) in PLACE_COUNTRIES:
        return PLACE_COUNTRIES[name_key(bracket.group(1))]
    if re.match(r"\d{2}-", place):
        return "FR"  # "72-La Flèche": a French département number
    return PLACES.get(name_key(re.sub(r"\s*\(.*", "", place)))


def _country(editions):
    """The country of most places of publication of ``editions``, or ``None``."""
    countries = Counter(country for edition in editions for place in edition["places"]
                        if (country := place_country(place)))
    return countries.most_common(1)[0][0] if countries else None


def plausible(editions, reference=None):
    """Leave out the adaptations: editions with less than half the pages of the work.

    The reference is the English page count of the work when known, or else
    the median page count of ``editions`` (from three of them).  Comics,
    abridged editions for children and opera librettos are much shorter.
    """
    counts = sorted(edition["pages"] for edition in editions if edition["pages"])
    if reference is None and len(counts) >= 3:
        reference = counts[len(counts) // 2]
    if not reference:
        return list(editions)
    return [edition for edition in editions if edition["pages"] is None or edition["pages"] >= reference / 2]


def choose(editions, publishers):
    """Return ``(publisher id, edition)`` of the usual French publisher of a work, or ``None``.

    The usual publisher has the most editions (the earliest one wins a tie),
    book clubs and cheap reprints coming after the publishers they reprint;
    its earliest single-volume edition with a page count is returned, or else
    its earliest edition.
    """
    by_publisher = {}
    for edition in editions:
        name = next((name for name in edition["publishers"] if name.strip()), None)
        if not name:
            continue
        key = publishers.resolve(name) or "new:" + publishers.key(name)
        by_publisher.setdefault(key, []).append(edition)
    if not by_publisher:
        return None

    def earliest(group):
        return min(edition["year"] or 10**4 for edition in group)

    def secondary(key):
        return publishers.key(by_publisher[key][0]["publishers"][0]) in SECONDARY_PUBLISHERS

    key = min(by_publisher, key=lambda key: (secondary(key), -len(by_publisher[key]), earliest(by_publisher[key]), key))
    group = sorted(by_publisher[key], key=lambda edition: (edition["pages"] is None, edition["year"] or 10**4))
    edition = group[0]
    publisher_id = key if not key.startswith("new:") else publishers.resolve(
        edition["publishers"][0], create=True, country=_country(group))
    return publisher_id, edition


# Updating the catalogue

def needs(book, vocabulary):
    """Return the fields of ``book`` that the BnF may fill or correct (``{"pages", "publisher"}``)."""
    if book.get("title_untranslated"):
        return set()
    needed = set()
    pages = (book.get("pages") or {}).get("fr_FR")
    publisher = (book.get("publisher") or {}).get("fr_FR")
    if pages is None and not book.get("pages_estimated"):
        needed.add("pages")
    foreign = publisher is not None and vocabulary.publishers[publisher].get("country") not in FRANCOPHONE | {None}
    if not book.get("publisher_estimated"):
        if publisher is None:
            needed.add("publisher")
        elif foreign:
            # The publisher of the original edition: its page count is likely that of the original too
            needed.add("publisher")
            if not book.get("pages_estimated") and pages == (book.get("pages") or {}).get("en_US"):
                needed.add("pages")
    elif foreign and book.get("wikidata_id"):
        # A foreign publisher typed by hand for the French edition ("Harper & Brothers" for Le Meilleur des
        # mondes) is wrong whatever the edition: a real French one replaces it
        needed.add("publisher")
    return needed


def lacks_french_title(book):
    """Whether the French title of ``book`` is its English one: flagged ``title_untranslated``, or not yet."""
    return bool(book.get("title_untranslated")) or book["title"]["fr_FR"] == book["title"]["en_US"]


def original_key(author, book):
    """Cache key of the translations of a book found by its original title."""
    return "original:" + book_key(author, book)


def book_key(author, book):
    return book.get("wikidata_id") or f"{name_key(author['name'])}|{title_key(book['title']['fr_FR'])}"


def _names(author):
    name = author["name"]
    return list(name.values()) if isinstance(name, dict) else [name]


def collect(data, cache, limit=None, titles=False, log=print, sleep=time.sleep):
    """Read from the BnF the editions of the books that need them, into ``cache``; return the count read.

    With ``titles``, the books without French title are looked up by their
    original (English) title instead, under :func:`original_key`.
    """
    vocabulary = PublisherVocabulary(data["publishers"])
    todo = []
    for author in data["authors"]:
        for book in author["books"]:
            if titles and lacks_french_title(book):
                if original_key(author, book) not in cache and original_key(author, book) not in todo:
                    todo.append((author, book, original_key(author, book), book["title"]["en_US"]))
            elif needs(book, vocabulary) and book_key(author, book) not in cache:
                todo.append((author, book, book_key(author, book), book["title"]["fr_FR"]))
    todo = todo[:limit] if limit is not None else todo
    log(f"{len(todo)} books to look up at the BnF")
    for count, (author, _book, key, title) in enumerate(todo, 1):
        name = _names(author)[0]
        try:
            cache[key] = parse_records(search(title, surname(name), sleep=sleep))
        except (urllib.error.URLError, TimeoutError, ConnectionError, ET.ParseError) as error:
            log(f"  {name} / {title}: {error}")
        if count % 50 == 0:
            log(f"  {count} / {len(todo)}")
        sleep(PAUSE)
    return len(todo)


def _set(book, field, value):
    current = book.get(field) or {"fr_FR": None, "en_US": None}
    current["fr_FR"] = value
    book[field] = current


def update(data, cache):
    """Fill the ``fr_FR`` pages and publishers from the cached BnF editions; return what happened."""
    report = Counter()
    vocabulary = PublisherVocabulary(data["publishers"])
    publishers = BnfPublishers(vocabulary)
    for author in data["authors"]:
        for book in author["books"]:
            needed = needs(book, vocabulary)
            if not needed:
                continue
            english_pages = (book.get("pages") or {}).get("en_US") if not book.get("pages_estimated") else None
            if book_key(author, book) in cache:
                editions = [edition for edition in cache[book_key(author, book)]
                            if matches(edition, book["title"]["fr_FR"])]
            elif original_key(author, book) in cache:
                # A book given its French title by --apply-titles: the translations found by its original title
                editions = [edition for edition in cache[original_key(author, book)]
                            if matches_original(edition, book["title"]["en_US"])]
            else:
                continue
            editions = plausible(editions, english_pages)
            chosen = choose(editions, publishers) if editions else None
            if chosen is None:
                report["no French edition found"] += 1
                continue
            publisher_id, edition = chosen
            for field, value in (("publisher", publisher_id), ("pages", edition["pages"])):
                if field in needed and value is not None:
                    previous = (book.get(field) or {}).get("fr_FR")
                    _set(book, field, value)
                    report[f"{field}[fr_FR] {'filled' if previous is None else 'replaced'}"] += 1
                    if book.get(f"{field}_estimated"):
                        # The flag stays: the English value typed by hand is still unchecked
                        report[f"{field}[fr_FR] estimate replaced"] += 1
    used = {value for author in data["authors"] for book in author["books"]
            for value in (book.get("publisher") or {}).values() if value}
    for publisher_id in sorted(set(data["publishers"]) - used):
        del data["publishers"][publisher_id]
        report["publishers dropped"] += publisher_id not in publishers.added
    editor._with_vocabulary(data, "publishers", data["publishers"])
    report["publishers added"] = len([publisher_id for publisher_id in publishers.added if publisher_id in used])
    return report


# French titles of the books flagged as untranslated

def propose_titles(data, cache):
    """Return the French titles found for the books whose French title is the English one, for review.

    Each proposal gives the most frequent title of the translations (by
    :func:`title_key`), the number of translations found, and the other
    titles they bear.  A title already used by another book of the author is
    not proposed.
    """
    proposals = []
    for author in data["authors"]:
        for book in author["books"]:
            if not lacks_french_title(book) or original_key(author, book) not in cache:
                continue
            translations = [edition for edition in cache[original_key(author, book)]
                            if matches_original(edition, book["title"]["en_US"]) and edition["titles"]]
            if not translations:
                continue
            spellings = {}
            for edition in translations:
                spellings.setdefault(title_key(edition["titles"][0]), []).append(edition["titles"][0])
            key = max(spellings, key=lambda key: (len(spellings[key]), -min(
                edition["year"] or 10**4 for edition in translations if title_key(edition["titles"][0]) == key)))
            title = french_title(Counter(spellings[key]).most_common(1)[0][0])
            others = {title_key(other["title"]["fr_FR"]) for other in author["books"] if other is not book}
            if title_key(title) in others or title_key(title) == title_key(book["title"]["en_US"]):
                continue
            proposals.append({
                "wikidata_id": book.get("wikidata_id"),
                "author": _names(author)[-1],
                "en_US": book["title"]["en_US"],
                "fr_FR": title,
                "translations": len(translations),
                "other_titles": sorted({french_title(spelling) for other, values in spellings.items()
                                        if other != key for spelling in values}),
            })
    return proposals


def apply_titles(data, proposals):
    """Give the books of the reviewed ``proposals`` their French title; return the count of books changed."""
    wanted = {proposal["wikidata_id"]: proposal for proposal in proposals if proposal.get("fr_FR")}
    changed = 0
    for author in data["authors"]:
        for book in author["books"]:
            proposal = wanted.get(book.get("wikidata_id"))
            if proposal is None or not lacks_french_title(book):
                continue
            if proposal["en_US"] != book["title"]["en_US"]:
                raise ValueError(f"{proposal['wikidata_id']}: proposal for {proposal['en_US']!r}, "
                                 f"catalogue title {book['title']['en_US']!r}")
            book["title"]["fr_FR"] = proposal["fr_FR"].strip()
            book.pop("title_untranslated", None)
            changed += 1
    return changed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--catalogue", type=Path, default=editor.CATALOGUE_PATH)
    parser.add_argument("--dry-run", action="store_true", help="report without writing the catalogue")
    parser.add_argument("--cache", type=Path, help="JSON file keeping the editions read from the BnF")
    parser.add_argument("--collect", action="store_true", help="only read the BnF into the cache")
    parser.add_argument("--limit", type=int, help="look up LIMIT books at most")
    parser.add_argument("--titles", action="store_true",
                        help="also look the books without French title up by their original title")
    parser.add_argument("--propose-titles", type=Path, metavar="FILE",
                        help="write the French titles found for the books without one, for review")
    parser.add_argument("--apply-titles", type=Path, metavar="FILE", help="give the books the reviewed titles")
    args = parser.parse_args(argv)

    data = editor.load_catalogue(args.catalogue)
    cache = json.loads(args.cache.read_text(encoding="utf-8")) if args.cache and args.cache.exists() else {}
    if args.propose_titles:
        proposals = propose_titles(data, cache)
        args.propose_titles.write_text(json.dumps(proposals, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{len(proposals)} French titles proposed in {args.propose_titles}")
        return
    report = Counter()
    if args.apply_titles:
        report["titles applied"] = apply_titles(data, json.loads(args.apply_titles.read_text(encoding="utf-8")))
    else:
        try:
            collect(data, cache, args.limit, args.titles)
        finally:
            if args.cache:
                args.cache.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        if args.collect:
            return
    report.update(update(data, cache))
    for key, count in sorted(report.items()):
        print(f"{key}: {count}")
    if not args.dry_run:
        editor.save_catalogue(data, args.catalogue)
        print(f"catalogue written to {args.catalogue}")


if __name__ == "__main__":
    main()
