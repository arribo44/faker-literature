"""Wikidata lookups and edits of the bundled ``literature.json`` catalogue."""

import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from faker_literature.importers.wikidata import (
    DATES_PATTERN,
    _entity_id,
    _parse_year,
    choose_nationality,
    known_nationalities,
    run_query,
)
from faker_literature.matching import DuplicateIndex, name_key, sort_key, title_key
from faker_literature.matching import names as _names
from faker_literature.store import LOCALES, MAX_PAGES, validate_book
from faker_literature.vocabulary import GenreVocabulary

CATALOGUE_PATH = ROOT / "faker_literature" / "DATAS" / "literature.json"
MAX_WORKS = 300
LANGUAGES = {"http://www.wikidata.org/entity/Q150": "fr_FR", "http://www.wikidata.org/entity/Q1860": "en_US"}

QID_PATTERN = re.compile(
    r"(?:https?://(?:www\.|m\.)?wikidata\.org/(?:wiki|entity)/)?(Q[1-9][0-9]{0,11})",
    re.IGNORECASE,
)

AUTHOR_QUERY = """
SELECT ?nameFr ?nameEn ?nameMul ?descFr ?country ?demonymFr ?demonymEn ?birthCountry WHERE {
  BIND(wd:%(qid)s AS ?author)
  OPTIONAL { ?author rdfs:label ?nameFr . FILTER(LANG(?nameFr) = "fr") }
  OPTIONAL { ?author rdfs:label ?nameEn . FILTER(LANG(?nameEn) = "en") }
  OPTIONAL { ?author rdfs:label ?nameMul . FILTER(LANG(?nameMul) = "mul") }
  OPTIONAL { ?author schema:description ?descFr . FILTER(LANG(?descFr) = "fr") }
  OPTIONAL {
    ?author wdt:P27 ?country .
    OPTIONAL { ?country wdt:P1549 ?demonymFr . FILTER(LANG(?demonymFr) = "fr") }
    OPTIONAL { ?country wdt:P1549 ?demonymEn . FILTER(LANG(?demonymEn) = "en") }
  }
  OPTIONAL { ?author wdt:P19/wdt:P17 ?birthCountry }
}
"""

WORKS_QUERY = """
SELECT ?work ?links ?titleFr ?titleEn ?titleMul ?typeFr ?date ?datePrecision ?inception ?inceptionPrecision
       ?pages ?genreFr ?genreEn ?publisherFr ?publisherEn WHERE {
  ?work wdt:P50 wd:%(qid)s ;
        wikibase:sitelinks ?links .
  FILTER NOT EXISTS { ?work wdt:P31 wd:Q13442814 }
  OPTIONAL { ?work rdfs:label ?titleFr . FILTER(LANG(?titleFr) = "fr") }
  OPTIONAL { ?work rdfs:label ?titleEn . FILTER(LANG(?titleEn) = "en") }
  OPTIONAL { ?work rdfs:label ?titleMul . FILTER(LANG(?titleMul) = "mul") }
  OPTIONAL { ?work wdt:P31 ?type . ?type rdfs:label ?typeFr . FILTER(LANG(?typeFr) = "fr") }
  %(dates)s
  OPTIONAL { ?work wdt:P1104 ?pages }
  OPTIONAL {
    ?work wdt:P136 ?genre .
    ?genre rdfs:label ?genreFr . FILTER(LANG(?genreFr) = "fr")
    ?genre rdfs:label ?genreEn . FILTER(LANG(?genreEn) = "en")
  }
  OPTIONAL {
    ?work wdt:P123 ?publisher .
    ?publisher rdfs:label ?publisherFr . FILTER(LANG(?publisherFr) = "fr")
    ?publisher rdfs:label ?publisherEn . FILTER(LANG(?publisherEn) = "en")
  }
}
"""

# "Influenced by" (P737) may point to people, works or movements
INFLUENCES_QUERY = """
SELECT ?influence ?nameFr ?nameEn ?nameMul ?descFr ?human WHERE {
  wd:%(qid)s wdt:P737 ?influence .
  OPTIONAL { ?influence rdfs:label ?nameFr . FILTER(LANG(?nameFr) = "fr") }
  OPTIONAL { ?influence rdfs:label ?nameEn . FILTER(LANG(?nameEn) = "en") }
  OPTIONAL { ?influence rdfs:label ?nameMul . FILTER(LANG(?nameMul) = "mul") }
  OPTIONAL { ?influence schema:description ?descFr . FILTER(LANG(?descFr) = "fr") }
  BIND(EXISTS { ?influence wdt:P31 wd:Q5 } AS ?human)
}
"""

# French and English editions give localized page counts and publishers
EDITIONS_QUERY = """
SELECT ?work ?lang ?pages ?publisherFr ?publisherEn WHERE {
  ?work wdt:P50 wd:%(qid)s ;
        wdt:P747 ?edition .
  ?edition wdt:P407 ?lang .
  VALUES ?lang { wd:Q150 wd:Q1860 }
  OPTIONAL { ?edition wdt:P1104 ?pages }
  OPTIONAL {
    ?edition wdt:P123 ?publisher .
    OPTIONAL { ?publisher rdfs:label ?publisherFr . FILTER(LANG(?publisherFr) = "fr") }
    OPTIONAL { ?publisher rdfs:label ?publisherEn . FILTER(LANG(?publisherEn) = "en") }
  }
}
"""


def parse_qid(text):
    """Return the ``Q...`` identifier in ``text`` (bare id or Wikidata URL)."""
    match = QID_PATTERN.fullmatch((text or "").strip())
    if not match:
        raise ValueError("Identifiant Wikidata invalide : attendu Q suivi de chiffres (ex. Q535) ou une URL Wikidata.")
    return match.group(1).upper()


def _valid_pages(text):
    """Wikidata page counts contain typos such as 940512: keep plausible ones."""
    return bool(text) and text.isdigit() and 0 < int(text) <= MAX_PAGES


def _values(rows):
    return [{key: cell["value"] for key, cell in row.items()} for row in rows]


# Wikidata

def parse_author(qid, rows, nationalities=None):
    """Merge the author rows into names and a suggested nationality.

    The nationality follows the importer rules (country of birth among several
    citizenships, translations already used in ``nationalities``, by default
    those of the bundled catalogue).
    """
    author = {"wikidata_id": qid, "name": {"fr_FR": "", "en_US": ""}, "description": "",
              "nationality": {"fr_FR": "", "en_US": ""}}
    demonyms, birth_countries = {}, set()
    for value in _values(rows):
        # Names identical in every language are now stored once, as "mul" labels
        author["name"]["fr_FR"] = author["name"]["fr_FR"] or value.get("nameFr") or value.get("nameMul", "")
        author["name"]["en_US"] = author["name"]["en_US"] or value.get("nameEn") or value.get("nameMul", "")
        author["description"] = author["description"] or value.get("descFr", "")
        if "demonymFr" in value and "demonymEn" in value:
            fr, en = demonyms.setdefault(_entity_id(value["country"]), (set(), set()))
            fr.add(value["demonymFr"])
            en.add(value["demonymEn"])
        if "birthCountry" in value:
            birth_countries.add(_entity_id(value["birthCountry"]))
    if demonyms:
        known = known_nationalities() if nationalities is None else nationalities
        author["nationality"] = choose_nationality(demonyms, birth_countries, known)
    if not (author["name"]["fr_FR"] or author["name"]["en_US"]):
        raise ValueError(f"Aucun élément Wikidata nommé {qid} en français ou en anglais.")
    author["name"]["fr_FR"] = author["name"]["fr_FR"] or author["name"]["en_US"]
    author["name"]["en_US"] = author["name"]["en_US"] or author["name"]["fr_FR"]
    return author


def parse_influences(rows):
    """Return the people and other items an author was influenced by, sorted by name."""
    influences = {}
    for value in _values(rows):
        entity = _entity_id(value["influence"])
        name = value.get("nameFr") or value.get("nameMul") or value.get("nameEn") or entity
        influences.setdefault(entity, {
            "wikidata_id": entity,
            "name": name,
            "description": value.get("descFr", ""),
            "person": value.get("human") == "true",
        })
    return sorted(influences.values(), key=lambda influence: _sort_name(influence["name"]))


def parse_works(rows, edition_rows):
    """Group work and edition rows into editable book proposals, best known first."""
    works = {}
    for value in _values(rows):
        if not ({"titleFr", "titleEn", "titleMul"} & set(value)):
            continue
        work = works.setdefault(_entity_id(value["work"]), {
            "links": int(value["links"]),
            "title": {"fr_FR": value.get("titleFr") or value.get("titleMul", ""),
                      "en_US": value.get("titleEn") or value.get("titleMul", "")},
            "types": [], "years": set(), "inceptions": set(), "pages": set(), "genres": {}, "publisher": None,
        })
        if value.get("typeFr") and value["typeFr"] not in work["types"]:
            work["types"].append(value["typeFr"])
        for key, years in (("date", work["years"]), ("inception", work["inceptions"])):
            year = _parse_year(value[key], value.get(key + "Precision")) if key in value else None
            if year is not None:
                years.add(year)
        if _valid_pages(value.get("pages")):
            work["pages"].add(int(value["pages"]))
        if "genreFr" in value:
            work["genres"].setdefault(value["genreFr"], value["genreEn"])
        if "publisherFr" in value and work["publisher"] is None:
            work["publisher"] = {"fr_FR": value["publisherFr"], "en_US": value["publisherEn"]}

    editions = {}
    for value in _values(edition_rows):
        locale = LANGUAGES.get(value["lang"])
        edition = editions.setdefault((_entity_id(value["work"]), locale), {"pages": None, "publisher": None})
        if edition["pages"] is None and _valid_pages(value.get("pages")):
            edition["pages"] = int(value["pages"])
        own = "publisherFr" if locale == "fr_FR" else "publisherEn"
        label = value.get(own) or value.get("publisherEn") or value.get("publisherFr")
        if edition["publisher"] is None and label:
            edition["publisher"] = label

    proposals = []
    for entity, work in works.items():
        pages, publisher = {}, {}
        for locale in LOCALES:
            edition = editions.get((entity, locale), {})
            pages[locale] = edition.get("pages") or (min(work["pages"]) if work["pages"] else None)
            publisher[locale] = edition.get("publisher") or (work["publisher"] or {}).get(locale, "")
        proposals.append({
            "wikidata_id": entity,
            "links": work["links"],
            "type": ", ".join(work["types"]),
            "title": work["title"],
            # Publication date first, creation date only when it is missing
            "year": min(work["years"] or work["inceptions"]) if work["years"] or work["inceptions"] else None,
            "genre": {"fr_FR": list(work["genres"]), "en_US": list(work["genres"].values())},
            "pages": pages,
            "publisher": publisher,
        })
    proposals.sort(key=lambda proposal: (-proposal["links"], proposal["title"]["fr_FR"] or proposal["title"]["en_US"]))
    return proposals


def fetch_author(qid):
    """Return ``(author, works, total)`` for the Wikidata author ``qid``."""
    qid = parse_qid(qid)
    author = parse_author(qid, run_query(AUTHOR_QUERY % {"qid": qid}))
    author["influences"] = parse_influences(run_query(INFLUENCES_QUERY % {"qid": qid}))
    works = parse_works(run_query(WORKS_QUERY % {"qid": qid, "dates": DATES_PATTERN}),
                        run_query(EDITIONS_QUERY % {"qid": qid}))
    return author, works[:MAX_WORKS], len(works)


# Catalogue

def load_catalogue(path=None):
    with open(path or CATALOGUE_PATH, encoding="utf-8") as file:
        return json.load(file)


def save_catalogue(data, path=None):
    """Write ``data`` atomically, in the same layout as the bundled file."""
    path = Path(path or CATALOGUE_PATH)
    content = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    # mkstemp creates the file readable by its owner only: keep the permissions of the original
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".literature-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(content)
        os.chmod(temp, mode)
        os.replace(temp, path)
    except BaseException:
        os.unlink(temp)
        raise


# Shared with the importer and the store (kept under these names for the tests)
_sort_name = sort_key
_name_key = name_key
_title_key = title_key


def find_author(data, qid, names):
    """Return the catalogue entry for ``qid``, matched by id or else by name.

    The name fallback only considers entries without a Wikidata id (or with
    the same one): two homonyms with different ids are different authors.
    ``qid`` may be ``None`` when the id is unknown.
    """
    wanted = {_name_key(name) for name in names if name}
    if qid is not None:
        for entry in data["authors"]:
            if entry.get("wikidata_id") == qid:
                return entry
    for entry in data["authors"]:
        if qid is not None and entry.get("wikidata_id") not in (None, qid):
            continue
        if {_name_key(name) for name in _names(entry["name"])} & wanted:
            return entry
    return None


def _is_known(book, entry_books):
    """Same Wikidata id or same normalized title, whatever the year (one author's books)."""
    return book in DuplicateIndex(entry_books)


def catalogue_info(data):
    """Return the values already used in the catalogue, to suggest consistent ones."""
    info = {"authors": len(data["authors"]), "books": 0}
    for field in ("nationality", "publisher"):
        info[field] = {locale: set() for locale in LOCALES}
    for entry in data["authors"]:
        info["books"] += len(entry["books"])
        for locale in LOCALES:
            info["nationality"][locale].add(entry["nationality"][locale])
        for book in entry["books"]:
            for locale in LOCALES:
                if book.get("publisher") and book["publisher"].get(locale):
                    info["publisher"][locale].add(book["publisher"][locale])
    for field in ("nationality", "publisher"):
        info[field] = {locale: sorted(values, key=str.casefold) for locale, values in info[field].items()}
    vocabulary = GenreVocabulary(data["genres"])
    info["genre"] = {locale: vocabulary.labels(locale) for locale in LOCALES}
    info["genre_pairs"] = [{locale: genre[locale] for locale in LOCALES} for genre in data["genres"].values()]
    return info


def annotate(data, author, works):
    """Describe the matching catalogue author and flag works and influences already present."""
    for influence in author.get("influences", []):
        influence["in_catalogue"] = influence["person"] and find_author(
            data, influence["wikidata_id"], [influence["name"]]) is not None
    entry = find_author(data, author["wikidata_id"], author["name"].values())
    books = entry["books"] if entry else [book for item in data["authors"] for book in item["books"]]
    vocabulary = GenreVocabulary(data["genres"])
    for work in works:
        work["in_catalogue"] = _is_known(work, books)
        if "genre" in work:
            work["genre"] = suggest_genres(vocabulary, work["genre"])
    if entry is None:
        return None
    return {"name": entry["name"], "nationality": entry["nationality"], "books": len(entry["books"])}


def _clean_text(value):
    return value.strip() if isinstance(value, str) else ""


def _clean_localized(value, convert=_clean_text):
    value = value if isinstance(value, dict) else {}
    return {locale: convert(value.get(locale)) for locale in LOCALES}


def _clean_pages(value):
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    text = _clean_text(value) if isinstance(value, str) else ""
    return int(text) if text.isdigit() else None


def _clean_genres(value):
    if isinstance(value, str):
        value = value.split(",")
    if not isinstance(value, list):
        return []
    return [genre.strip() for genre in value if isinstance(genre, str) and genre.strip()]


def _lower_first(text):
    return text[:1].lower() + text[1:]


def suggest_genres(vocabulary, genre):
    """Replace the Wikidata genre labels by the catalogue ones when the genre is known.

    Unknown genres are kept as they are, so that the user can add them.
    """
    suggested = {locale: [] for locale in LOCALES}
    for fr, en in zip(genre["fr_FR"], genre["en_US"], strict=True):
        genre_id = vocabulary.match(fr, "fr_FR") or vocabulary.match(en, "en_US")
        labels = vocabulary.genres[genre_id] if genre_id else {"fr_FR": fr, "en_US": en}
        for locale in LOCALES:
            if labels[locale] not in suggested[locale]:
                suggested[locale].append(labels[locale])
    return suggested


def genre_ids(vocabulary, genre):
    """Return the ids of the genres typed in the page, adding the new ones to ``vocabulary``.

    Each label is looked up in the vocabulary (labels and aliases, in either
    language).  Unknown labels make new genres: the n-th unknown French label
    is paired with the n-th unknown English one, so both lists must contain
    as many of them.  Returns ``(ids, new genres as "fr / en")``.
    """
    ids, unknown = [], {locale: [] for locale in LOCALES}
    for locale in LOCALES:
        for label in genre[locale]:
            genre_id = vocabulary.match(label, locale)
            if genre_id is None:
                unknown[locale].append(label)
            elif genre_id not in ids:
                ids.append(genre_id)
    if len(unknown["fr_FR"]) != len(unknown["en_US"]):
        missing = "anglais" if len(unknown["fr_FR"]) > len(unknown["en_US"]) else "français"
        labels = ", ".join(f"« {label} »" for locale in LOCALES for label in unknown[locale])
        raise ValueError(f"Genres : {labels} absent(s) du vocabulaire. Pour créer un nouveau genre, "
                         f"donnez sa traduction en {missing} à la même position que dans l'autre liste.")
    new = []
    for fr, en in zip(unknown["fr_FR"], unknown["en_US"], strict=True):
        try:
            genre_id = vocabulary.add(fr, en)
        except ValueError as error:
            raise ValueError(f"Genres : « {fr} » / « {en} » ne peut pas devenir un nouveau genre ({error}).") from None
        if genre_id not in ids:
            ids.append(genre_id)
            new.append(f"{fr} / {en}")
    return ids, new


def build_book(raw):
    """Normalize a book submitted by the page into the catalogue layout."""
    year = raw.get("year")
    if isinstance(year, str) and re.fullmatch(r"-?[0-9]{1,4}", year.strip()):
        year = int(year)
    pages = _clean_localized(raw.get("pages"), _clean_pages)
    publisher = _clean_localized(raw.get("publisher"))
    genre = _clean_localized(raw.get("genre"), _clean_genres)
    # The catalogue writes French genres in lower case ("roman", not "Roman")
    genre["fr_FR"] = list(dict.fromkeys(_lower_first(item) for item in genre["fr_FR"]))
    wikidata_id = raw.get("wikidata_id")
    values = {
        "pages": pages if any(value is not None for value in pages.values()) else None,
        "publisher": ({locale: value or None for locale, value in publisher.items()}
                      if any(publisher.values()) else None),
    }
    book = {"year": year, "genre": genre, "title": _clean_localized(raw.get("title"))}
    for field, value in values.items():
        book[field] = value
        # Without a Wikidata source, the page counts and publishers typed by hand are not checked
        if value is not None and not wikidata_id:
            book[f"{field}_estimated"] = True
    if wikidata_id:
        book["wikidata_id"] = parse_qid(wikidata_id)
    return book


FIELD_LABELS = {
    "writer": "Nom de l'auteur", "nationality": "Nationalité de l'auteur", "title": "Titre",
    "genre": "Genres", "year": "Année", "pages": "Pages", "publisher": "Éditeur",
}
LANGUAGE_LABELS = {"fr_FR": "français", "en_US": "anglais"}


def explain_error(error):
    """Turn a schema validation message into a French sentence naming the field."""
    message = str(error)
    match = re.match(r"(\w+)(?:\[(\w+)\])?", message)
    field, locale = (match.group(1), match.group(2)) if match else ("", None)
    label = FIELD_LABELS.get(field)
    if label is None:
        return f"Fiche invalide : {message}"
    if locale in LANGUAGE_LABELS:
        label = f"{label} ({LANGUAGE_LABELS[locale]})"
    if field == "year":
        return f"{label} manquante ou invalide : un nombre entier est attendu (négatif pour une date av. J.-C.)."
    if field == "genre":
        return f"{label} : au moins un genre est requis (20 au maximum), séparés par des virgules."
    if field == "pages":
        return f"{label} : un nombre entier entre 1 et {MAX_PAGES} est attendu, ou laissez le champ vide."
    if "longer than" in message:
        return f"{label} : texte trop long (300 caractères au maximum)."
    return f"{label} : champ obligatoire manquant ou invalide."


def add_book(data, raw_author, raw_book):
    """Validate and insert a book, creating its author if needed.

    Returns ``(message, created_author)``.  Raises ``ValueError`` when the
    record is invalid or already present.
    """
    qid = parse_qid(raw_author.get("wikidata_id"))
    names = _clean_localized(raw_author.get("name"))
    nationality = _clean_localized(raw_author.get("nationality"))
    nationality["fr_FR"] = nationality["fr_FR"].lower()
    book = build_book(raw_book)
    entry = find_author(data, qid, names.values())
    created = entry is None
    # New genres go to a copy of the vocabulary until the book is accepted
    genres = dict(data["genres"])
    vocabulary = GenreVocabulary(genres)
    if not (book["genre"]["fr_FR"] or book["genre"]["en_US"]):
        raise ValueError("Genres : au moins un genre est requis, en français ou en anglais, séparés par des virgules.")
    book["genre"], new_genres = genre_ids(vocabulary, book["genre"])

    if created:
        name = names["fr_FR"] if names["fr_FR"] == names["en_US"] else names
        entry = {"name": name, "wikidata_id": qid, "nationality": nationality, "books": []}
    try:
        validate_book({"writer": entry["name"], "nationality": entry["nationality"], **book,
                       "genre": vocabulary.resolve(book["genre"]), "source": "builtin"})
    except ValueError as error:
        raise ValueError(explain_error(error)) from None
    if _is_known(book, entry["books"]):
        raise ValueError("Ce livre est déjà dans le catalogue pour cet auteur.")

    if created:
        position = next((index for index, other in enumerate(data["authors"])
                         if _sort_name(other["name"]) > _sort_name(entry["name"])), len(data["authors"]))
        data["authors"].insert(position, entry)
    else:
        entry.setdefault("wikidata_id", qid)
    position = next((index for index, other in enumerate(entry["books"]) if other["year"] > book["year"]),
                    len(entry["books"]))
    entry["books"].insert(position, book)
    data["genres"] = dict(sorted(genres.items()))

    title = book["title"]["fr_FR"]
    message = (f"« {title} » ajouté, avec le nouvel auteur {names['fr_FR']}." if created
               else f"« {title} » ajouté à {names['fr_FR']} ({len(entry['books'])} livres).")
    if new_genres:
        message += " Nouveau(x) genre(s) : " + ", ".join(new_genres) + "."
    return message, created
