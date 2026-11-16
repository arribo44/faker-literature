"""The Goodreads import, without network: reading the export, matching, writing the catalogue."""

import copy

import editor
import import_goodreads as goodreads
import pytest

from faker_literature.vocabulary import GenreVocabulary

HEADER = ("bookID,title,authors,average_rating,isbn,isbn13,language_code,  num_pages,ratings_count,"
          "text_reviews_count,publication_date,publisher\n")


def _line(book_id, title, authors, ratings):
    return f'{book_id},"{title}",{authors},4.0,0,0,eng,300,{ratings},10,1/1/2000,Publisher\n'


@pytest.fixture
def catalogue():
    data = copy.deepcopy(editor.load_catalogue())
    goodreads.extend_vocabulary(data["genres"])
    return data


@pytest.mark.parametrize("title, expected", [
    ("Harry Potter and the Half-Blood Prince (Harry Potter  #6)", "Harry Potter and the Half-Blood Prince"),
    ("The Paradox of Choice: Why More Is Less", "The Paradox of Choice"),
    ("  Congo ", "Congo"),
])
def test_series_and_subtitles_are_dropped(title, expected):
    assert goodreads.clean_title(title) == expected


def test_candidates_are_popular_works_most_rated_first(tmp_path):
    export = tmp_path / "books.csv"
    export.write_text(HEADER + "".join([
        _line(1, "Congo", "Michael Crichton", 5000),
        _line(2, "Congo (Paperback edition)", "Michael Crichton/Someone Else", 9000),  # same work
        _line(3, "Sphere", "Michael Crichton", 1000),
        _line(4, "Obscure", "Nobody", 999),                                              # too few ratings
        _line(5, "The Complete Works", "William Shakespeare", 90000),                   # not a work
        "6,Broken,Sam Bass Warner, Jr./Sam B. Warner,4.0,0,0,eng,1,5000,1,1/1/2000,P\n",  # extra column
        _line(7, "Hamlet", "William Shakespeare", 7000),
        _line(8, "Bradbury Stories: 100 of His Most Celebrated Tales", "Ray Bradbury", 9000),  # an anthology
    ]), encoding="utf-8")

    candidates = goodreads.read_candidates(export, per_author=1)

    assert [(book["id"], book["title"]) for book in candidates] == [("2", "Congo"), ("7", "Hamlet")]
    assert candidates[0]["authors"] == ["Michael Crichton", "Someone Else"]
    assert len(goodreads.read_candidates(export)) == 3


def test_vocabulary_is_extended_once_and_unused_new_genres_are_dropped(catalogue):
    vocabulary = GenreVocabulary(catalogue["genres"])
    assert vocabulary.match("historical fiction", "en_US") == "historical-novel"
    assert vocabulary.match("young adult fiction", "en_US") == "young-adult"

    assert goodreads.extend_vocabulary(catalogue["genres"]) == []
    assert catalogue["genres"]["crime"]["aliases"]["en_US"].count("crime literature") == 1

    genres = {key: value for key, value in catalogue["genres"].items() if key not in goodreads.NEW_GENRES}
    assert sorted(goodreads.extend_vocabulary(genres)) == sorted(goodreads.NEW_GENRES)
    data = {"genres": genres, "authors": [{"books": [{"genre": ["novel", "novella"]}]}]}
    goodreads.drop_unused_genres(data, list(goodreads.NEW_GENRES))
    assert "novella" in genres and "young-adult" not in genres


def _record(wikidata_id="Q100", **overrides):
    record = {
        "wikidata_id": wikidata_id,
        "writer": {"fr_FR": "Zed Fictional", "en_US": "Zed Fictional"},
        "nationality": {"fr_FR": "américain", "en_US": "American"},
        "title": {"fr_FR": "Congo", "en_US": "Congo"},
        "title_untranslated": True,
        "genre": {"fr_FR": ["thriller", "science-fiction"], "en_US": ["thriller", "science fiction"]},
        "year": 1980,
        "pages": None,
        "publisher": {"fr_FR": None, "en_US": "Knopf"},
    }
    record.update(overrides)
    return record


def _entry(catalogue, qid):
    return next(author for author in catalogue["authors"] if author.get("wikidata_id") == qid)


def test_records_are_added_with_their_untranslated_title_flag(catalogue):
    skipped = goodreads.add_records(catalogue, [_record()], {"Q100": "Q999999"}, log=lambda message: None)

    assert not skipped
    [book] = _entry(catalogue, "Q999999")["books"]
    assert list(book) == ["year", "genre", "title", "title_untranslated", "pages", "publisher", "wikidata_id"]
    assert book["genre"] == ["thriller", "science-fiction"]
    assert book["publisher"] == {"fr_FR": None, "en_US": "Knopf"}


def test_duplicates_co_written_works_and_prolific_authors_are_skipped(catalogue):
    hugo = next(author for author in catalogue["authors"] if author["name"] == "Victor Hugo")
    misérables = next(book for book in hugo["books"] if book["title"]["fr_FR"] == "Les Misérables")
    records = [
        _record("Q1"), _record("Q1"),                                       # the same work twice
        _record("Q2", title=misérables["title"], year=misérables["year"]),  # already in the catalogue
        _record("Q3", writer={"fr_FR": "A, B", "en_US": "A, B"}),
        *[_record(f"Q{n}", title={"fr_FR": f"T{n}", "en_US": f"T{n}"}) for n in range(10, 16)],
    ]
    authors = {record["wikidata_id"]: "Q999999" for record in records}

    skipped = goodreads.add_records(catalogue, records, authors, max_per_author=3, log=lambda message: None)

    assert len(_entry(catalogue, "Q999999")["books"]) == 3
    assert skipped == {"already in the catalogue": 2, "several authors": 1, "author already has enough books": 4}


def test_known_authors_keep_their_name_and_nationality(catalogue):
    zola = next(author for author in catalogue["authors"] if author["name"] == "Émile Zola")
    record = _record(writer={"fr_FR": "Emile Zola", "en_US": "Emile Zola"},
                     nationality={"fr_FR": "italien", "en_US": "Italian"}, title={"fr_FR": "Inédit", "en_US": "Inédit"})

    goodreads.add_records(catalogue, [record], {"Q100": zola.get("wikidata_id", "Q504")},
                          max_per_author=100, log=lambda message: None)

    assert zola["nationality"]["en_US"] == "French"
    assert "Inédit" in [book["title"]["fr_FR"] for book in zola["books"]]
