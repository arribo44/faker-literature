"""Consistency checks of the bundled catalogue (``literature.json``).

The schema validation of ``store.validate_book`` checks each record alone;
these tests check that the records agree with each other and with the genre
vocabulary, so that filters such as ``books_by_genre`` see every matching book
in both locales.
"""

import json
import re
from collections import Counter, defaultdict

import editor
import pytest

from faker_literature.matching import name_key
from faker_literature.store import BUILTIN_DATA, LOCALES, load_builtin_books, validate_book
from faker_literature.vocabulary import GenreVocabulary, PublisherVocabulary

QID = re.compile(r"Q[1-9][0-9]*")

# Genre names that are proper nouns and keep their capital letter
CAPITALIZED_GENRES = {"Bildungsroman", "Jewish American"}


@pytest.fixture(scope="module")
def catalogue():
    return json.loads(BUILTIN_DATA.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def books(catalogue):
    return [(author, book) for author in catalogue["authors"] for book in author["books"]]


def _label(author, book):
    name = author["name"] if isinstance(author["name"], str) else author["name"]["fr_FR"]
    return f"{name} — {book['title']['fr_FR']} ({book['year']})"


def _one_to_one(pairs):
    """Return the values translated in more than one way, in either direction."""
    translations = {locale: defaultdict(set) for locale in LOCALES}
    for fr, en in pairs:
        translations["fr_FR"][fr].add(en)
        translations["en_US"][en].add(fr)
    return {value: sorted(others) for table in translations.values()
            for value, others in table.items() if len(others) > 1}


def test_every_record_follows_the_schema():
    records, _ = load_builtin_books()
    for record in records:
        validate_book(record)


def test_genre_vocabulary_is_unambiguous(catalogue):
    # Raises if a label or alias names two genres in a locale, or an id is malformed
    vocabulary = GenreVocabulary(catalogue["genres"])
    assert len(vocabulary.labels("fr_FR")) == len(vocabulary.labels("en_US")) == len(catalogue["genres"])


def test_each_genre_has_a_single_translation(catalogue):
    pairs = [(genre["fr_FR"], genre["en_US"]) for genre in catalogue["genres"].values()]
    assert _one_to_one(pairs) == {}


def test_books_refer_to_known_genres_once(catalogue, books):
    wrong = [_label(author, book) for author, book in books
             if not book["genre"] or len(set(book["genre"])) != len(book["genre"])
             or not set(book["genre"]) <= set(catalogue["genres"])]
    assert not wrong


def test_every_genre_is_used(catalogue, books):
    used = {genre_id for _, book in books for genre_id in book["genre"]}
    assert sorted(set(catalogue["genres"]) - used) == []


def test_genres_are_sorted_by_id(catalogue):
    assert list(catalogue["genres"]) == sorted(catalogue["genres"])


# Words that do not tell a publisher from another ("Éditions Gallimard", "Hodder & Stoughton Limited")
PUBLISHER_NOISE = re.compile(
    r"^(?:les |the )?(?:éditions |editions |editorial |editora )?"
    r"|(?:,? (?:inc\.?|ltd\.?|limited|publishing|publishers|publications|company|co\.?|group|corporation"
    r"|verlag|éditeur|books|press|& sons|sons))+$", re.IGNORECASE)
# Distinct publishers whose names differ by such words only
DISTINCT_PUBLISHERS = [
    {"bantam-books", "bantam-press"},  # American and British imprints of Bantam
    {"dial-books", "dial-press"},  # children's imprint of Penguin, adult imprint of Random House
    {"walker-books", "walker-company"},  # British children's publisher, American publisher
    {"orion-publishing-group", "the-orion-press"},  # British group, American publisher of the 1960s
    {"penguin-books", "penguin-group"},  # the imprint and its parent group
    {"pocket", "pocket-books"},  # French and American paperback publishers
]


def _publisher_key(name):
    name = name.replace(" and ", " & ")
    previous = None
    while previous != name:
        previous, name = name, PUBLISHER_NOISE.sub("", name).strip()
    return name_key(name)


def test_publisher_vocabulary_is_unambiguous(catalogue):
    # Raises if a name or alias belongs to two publishers, or an id, country or Wikidata id is malformed
    vocabulary = PublisherVocabulary(catalogue["publishers"])
    assert len(vocabulary.names("fr_FR")) == len(catalogue["publishers"])


def test_publisher_names_are_not_variants_of_each_other(catalogue):
    # "Little, Brown" and "Little, Brown and Company" are one publisher, with an alias
    owners = defaultdict(set)
    for publisher_id, publisher in catalogue["publishers"].items():
        name = publisher["name"]
        for label in [*(name.values() if isinstance(name, dict) else [name]), *publisher.get("aliases", [])]:
            owners[_publisher_key(label)].add(publisher_id)
    variants = [ids for ids in owners.values() if len(ids) > 1 and ids not in DISTINCT_PUBLISHERS]
    assert not variants


def test_publisher_wikidata_ids_are_unique(catalogue):
    ids = Counter(publisher["wikidata_id"] for publisher in catalogue["publishers"].values()
                  if "wikidata_id" in publisher)
    assert [qid for qid, count in ids.items() if count > 1] == []


def test_books_refer_to_known_publishers(catalogue, books):
    wrong = [_label(author, book) for author, book in books if book.get("publisher") is not None and (
        set(book["publisher"]) != set(LOCALES)
        or not all(value is None or value in catalogue["publishers"] for value in book["publisher"].values())
        or not any(book["publisher"].values()))]
    assert not wrong


def test_every_publisher_is_used(catalogue, books):
    used = {value for _, book in books for value in (book.get("publisher") or {}).values() if value}
    assert sorted(set(catalogue["publishers"]) - used) == []


def test_publishers_are_sorted_by_id(catalogue):
    assert list(catalogue["publishers"]) == sorted(catalogue["publishers"])


def test_aliases_do_not_repeat_the_name(catalogue):
    wrong = []
    for publisher_id, publisher in catalogue["publishers"].items():
        name = publisher["name"]
        names = {name_key(label) for label in (name.values() if isinstance(name, dict) else [name])}
        aliases = [name_key(alias) for alias in publisher.get("aliases", [])]
        if len(set(aliases)) != len(aliases) or names & set(aliases):
            wrong.append(publisher_id)
    assert not wrong


# Countries whose publishers publish in the language of each locale
LOCALE_COUNTRIES = {
    "fr_FR": {"FR", "BE", "CH", "CA", "LU", "MC"},
    "en_US": {"US", "GB", "CA", "AU", "IE", "NZ", "IN", "ZA"},
}
# Publishers working in the language of a locale from another country
LOCALE_PUBLISHERS = {
    "en_US": {
        "olympia-press",  # Paris, in English: Lolita, Naked Lunch
        "obelisk-press",  # Paris, in English: Tropic of Cancer
        "shakespeare-and-company",  # Paris, in English: Ulysses
    },
}
# Books whose publisher is not of the locale's language, at most: a ratchet, lowered as the catalogue is
# corrected (tools/literature_editor/update_editions.py and update_bnf.py), so that it never gets worse
MAX_FOREIGN_PUBLISHERS = {"fr_FR": 84, "en_US": 64}


def _foreign_publishers(catalogue, books, locale):
    """Return the books whose ``locale`` publisher is from a country of another language."""
    foreign = []
    for author, book in books:
        publisher_id = (book.get("publisher") or {}).get(locale)
        if not publisher_id or publisher_id in LOCALE_PUBLISHERS.get(locale, ()):
            continue
        # A work never translated into French has no French edition: its original one stands in
        if locale == "fr_FR" and book.get("title_untranslated"):
            continue
        country = catalogue["publishers"][publisher_id].get("country")
        if country is not None and country not in LOCALE_COUNTRIES[locale]:
            foreign.append(f"{_label(author, book)}: {publisher_id} ({country})")
    return foreign


@pytest.mark.parametrize("locale", LOCALES)
def test_publishers_publish_in_the_language_of_their_locale(catalogue, books, locale):
    # "Alfred A. Knopf" as the French publisher of an American novel is the publisher of its original edition
    foreign = _foreign_publishers(catalogue, books, locale)
    assert len(foreign) <= MAX_FOREIGN_PUBLISHERS[locale], (
        f"{len(foreign)} {locale} publishers of another language (at most {MAX_FOREIGN_PUBLISHERS[locale]}): "
        + "; ".join(foreign[:20]))


def test_publishers_have_a_country(catalogue):
    # Without one, the language of a publisher cannot be checked
    assert len([publisher_id for publisher_id, publisher in catalogue["publishers"].items()
                if "country" not in publisher]) <= 33


@pytest.mark.parametrize("field", ["pages", "publisher"])
def test_values_typed_by_hand_are_flagged_as_estimates(books, field):
    # Books added from Wikidata carry its page counts and publishers; the others were typed by hand
    flag = f"{field}_estimated"
    unflagged = [_label(author, book) for author, book in books
                 if "wikidata_id" not in book and book.get(field) and book.get(flag) is not True]
    wrongly_flagged = [_label(author, book) for author, book in books
                       if flag in book and (book[flag] is not True or not book.get(field))]
    assert not unflagged
    assert not wrongly_flagged


def test_untranslated_titles_are_flagged_wikidata_works(books):
    # Only books checked on Wikidata, whose French title is the original one, carry the flag
    wrongly_flagged = [_label(author, book) for author, book in books if "title_untranslated" in book and (
        book["title_untranslated"] is not True or "wikidata_id" not in book
        or book["title"]["fr_FR"] != book["title"]["en_US"])]
    assert not wrongly_flagged


def test_each_nationality_has_a_single_translation(catalogue):
    pairs = [(author["nationality"]["fr_FR"], author["nationality"]["en_US"]) for author in catalogue["authors"]]
    assert _one_to_one(pairs) == {}


def test_genres_are_not_nationalities(catalogue):
    # Compared within each locale: the French genre "roman" is not the English nationality "Roman"
    nationalities = {(locale, value.casefold()) for author in catalogue["authors"]
                     for locale, value in author["nationality"].items()}
    wrong = {genre[locale] for genre in catalogue["genres"].values() for locale in LOCALES
             if (locale, genre[locale].casefold()) in nationalities}
    assert not wrong


def test_genres_and_french_nationalities_are_lower_case(catalogue):
    labels = {genre[locale] for genre in catalogue["genres"].values() for locale in LOCALES}
    assert {label for label in labels if label[:1].isupper()} <= CAPITALIZED_GENRES
    assert not [author["nationality"]["fr_FR"] for author in catalogue["authors"]
                if author["nationality"]["fr_FR"] != author["nationality"]["fr_FR"].lower()]


def test_text_has_no_stray_spaces(catalogue, books):
    def texts(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for item in value.values():
                yield from texts(item)
        elif isinstance(value, list):
            for item in value:
                yield from texts(item)

    stray = {text for author, book in books for text in texts([author["name"], author["nationality"], book])
             if text != text.strip() or "  " in text}
    stray |= {text for text in texts(catalogue["genres"]) if text != text.strip() or "  " in text}
    assert not stray


def test_authors_are_sorted_by_name(catalogue):
    keys = [editor._sort_name(author["name"]) for author in catalogue["authors"]]
    assert keys == sorted(keys)


def test_books_of_an_author_are_sorted_by_year(catalogue):
    unsorted = [author["name"] for author in catalogue["authors"]
                if [book["year"] for book in author["books"]] != sorted(book["year"] for book in author["books"])]
    assert not unsorted


def test_wikidata_ids_are_well_formed_and_unique(catalogue, books):
    authors = [author["wikidata_id"] for author in catalogue["authors"] if "wikidata_id" in author]
    works = [book["wikidata_id"] for _, book in books if "wikidata_id" in book]
    assert all(QID.fullmatch(qid) for qid in authors + works)
    assert [qid for qid, count in Counter(authors).items() if count > 1] == []
    assert [qid for qid, count in Counter(works).items() if count > 1] == []


def test_author_names_are_unique(catalogue):
    # Each author counts once per name, even when both locales spell it alike
    keys = Counter(key for author in catalogue["authors"]
                   for key in {editor._name_key(name) for name in editor._names(author["name"])})
    assert [key for key, count in keys.items() if count > 1] == []


def test_an_author_has_no_duplicate_title(catalogue):
    duplicates = []
    for author in catalogue["authors"]:
        for locale in LOCALES:
            keys = Counter(editor._title_key(book["title"][locale]) for book in author["books"])
            duplicates += [(author["name"], key) for key, count in keys.items() if count > 1]
    assert not duplicates


# Books written at least at this age, and published at most this long after the author's death
MIN_AGE = 12
MAX_POSTHUMOUS_YEARS = 60


def test_books_fit_the_life_of_their_author(books):
    too_early = [_label(author, book) for author, book in books
                 if "born" in author and book["year"] < author["born"] + MIN_AGE]
    too_late = [_label(author, book) for author, book in books
                if "died" in author and book["year"] > author["died"] + MAX_POSTHUMOUS_YEARS]
    assert not too_early
    assert not too_late


def test_lives_are_consistent(catalogue):
    wrong = [author["name"] for author in catalogue["authors"]
             if ("died" in author and ("born" not in author or author["died"] <= author["born"]))
             or any(not isinstance(author.get(key, 0), int) for key in ("born", "died"))]
    assert not wrong


def test_awards_vocabulary_is_used_and_unambiguous(catalogue, books):
    vocabulary = catalogue["awards"]
    used = [award for _, book in books for award in book.get("awards", [])]
    assert set(used) == set(vocabulary)
    assert all(len(book["awards"]) == len(set(book["awards"])) and book["awards"]
               for _, book in books if "awards" in book)
    assert all("wikidata_id" in book for _, book in books if "awards" in book)
    pairs = [(award["fr_FR"], award["en_US"]) for award in vocabulary.values()]
    assert _one_to_one(pairs) == {}
