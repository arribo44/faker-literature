"""Consistency checks of the bundled catalogue (``literature.json``).

The schema validation of ``store.validate_book`` checks each record alone;
these tests check that the records agree with each other, so that filters such
as ``books_by_genre`` see every matching book in both locales.
"""

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pytest

from faker_literature.store import BUILTIN_DATA, LOCALES, load_builtin_books, validate_book

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "literature_editor"))

import editor  # noqa: E402


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


def test_genre_lists_are_aligned_between_locales(books):
    misaligned = [_label(author, book) for author, book in books
                  if len(book["genre"]["fr_FR"]) != len(book["genre"]["en_US"])]
    assert not misaligned


def test_each_genre_has_a_single_translation(books):
    pairs = [pair for _, book in books for pair in zip(book["genre"]["fr_FR"], book["genre"]["en_US"])]
    assert _one_to_one(pairs) == {}


def test_each_nationality_has_a_single_translation(catalogue):
    pairs = [(author["nationality"]["fr_FR"], author["nationality"]["en_US"]) for author in catalogue["authors"]]
    assert _one_to_one(pairs) == {}


def test_genres_are_not_nationalities(catalogue, books):
    # Compared within each locale: the French genre "roman" is not the English nationality "Roman"
    nationalities = {(locale, value.casefold()) for author in catalogue["authors"]
                     for locale, value in author["nationality"].items()}
    wrong = {genre for _, book in books for locale in LOCALES for genre in book["genre"][locale]
             if (locale, genre.casefold()) in nationalities}
    assert not wrong


def test_genres_and_french_nationalities_are_lower_case(catalogue, books):
    genres = {genre for _, book in books for locale in LOCALES for genre in book["genre"][locale]}
    assert {genre for genre in genres if genre[:1].isupper()} <= CAPITALIZED_GENRES
    assert not [author["nationality"]["fr_FR"] for author in catalogue["authors"]
                if author["nationality"]["fr_FR"] != author["nationality"]["fr_FR"].lower()]


def test_no_genre_appears_twice_in_a_book(books):
    repeated = [_label(author, book) for author, book in books for locale in LOCALES
                if len(set(book["genre"][locale])) != len(book["genre"][locale])]
    assert not repeated


def test_text_has_no_stray_spaces(books):
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
