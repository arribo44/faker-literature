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

from faker_literature.store import BUILTIN_DATA, LOCALES, load_builtin_books, validate_book
from faker_literature.vocabulary import GenreVocabulary

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
