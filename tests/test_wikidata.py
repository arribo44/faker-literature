from faker_literature.importers import wikidata
from faker_literature.store import BookStore, validate_book


def _row(work="Q1", **values):
    defaults = {
        "work": f"http://www.wikidata.org/entity/{work}",
        "titleFr": "Le Portrait de Dorian Gray",
        "titleEn": "The Picture of Dorian Gray",
        "author": "http://www.wikidata.org/entity/Q30875",
        "writerFr": "Oscar Wilde",
        "writerEn": "Oscar Wilde",
        "date": "1890-06-20T00:00:00Z",
        "genreFr": "roman gothique",
        "genreEn": "Gothic novel",
        "country": "http://www.wikidata.org/entity/Q145",
        "demonymFr": "Britannique",
        "demonymEn": "British",
    }
    defaults.update(values)
    return {key: {"type": "literal", "value": value} for key, value in defaults.items()}


def test_rows_are_grouped_into_one_valid_record():
    rows = [
        _row(demonymEn="Britons"),
        _row(demonymFr="Britanniques", genreFr="roman philosophique", genreEn="philosophical novel"),
        _row(date="1891-01-01T00:00:00Z", pages="254"),
        _row(country="http://www.wikidata.org/entity/Q27", demonymFr="Irlandais", demonymEn="Irish"),
    ]

    [record] = wikidata.parse_bindings(rows)

    assert record["wikidata_id"] == "Q1"
    assert record["year"] == 1890
    assert record["pages"] == {"fr_FR": 254, "en_US": 254}
    assert record["nationality"] == {"fr_FR": "irlandais", "en_US": "Irish"}
    assert record["genre"] == {
        "fr_FR": ["roman gothique", "roman philosophique"],
        "en_US": ["Gothic novel", "philosophical novel"],
    }
    validate_book(dict(record, source="wikidata"))


def test_negative_years_are_parsed():
    [record] = wikidata.parse_bindings([_row(date="-0800-01-01T00:00:00Z")])

    assert record["year"] == -800


def test_works_without_genre_or_nationality_are_skipped():
    no_genre = _row(work="Q1")
    del no_genre["genreFr"], no_genre["genreEn"]
    no_nationality = _row(work="Q2")
    del no_nationality["country"], no_nationality["demonymFr"], no_nationality["demonymEn"]

    assert wikidata.parse_bindings([no_genre, no_nationality]) == []


def test_co_authors_are_joined():
    rows = [
        _row(),
        _row(author="http://www.wikidata.org/entity/Q2", writerFr="Ami", writerEn="Friend"),
    ]

    [record] = wikidata.parse_bindings(rows)

    assert record["writer"] == {"fr_FR": "Oscar Wilde, Ami", "en_US": "Oscar Wilde, Friend"}


def test_works_already_in_the_catalogue_are_excluded():
    store = BookStore()
    known = store.books.all()
    hugo = next(book for book in known if book["title"]["fr_FR"] == "Les Misérables")
    duplicate = dict(wikidata.parse_bindings([_row()])[0], title=hugo["title"], year=hugo["year"] + 1)
    new = wikidata.parse_bindings([_row()])[0]

    assert wikidata.exclude_known([duplicate, new], known) == [new]


def test_import_replaces_previous_wikidata_books(monkeypatch):
    responses = iter([
        [{"work": {"value": "http://www.wikidata.org/entity/Q1"}, "links": {"value": "50"}}],
        [_row()],
    ])
    monkeypatch.setattr(wikidata, "run_query", lambda query: next(responses))
    store = BookStore()
    store.replace_source("wikidata", [])

    count = wikidata.import_into(store, limit=10, log=lambda message: None)

    assert count == 1
    assert store.sources()["wikidata"] == 1
