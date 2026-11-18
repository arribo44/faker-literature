"""Filling page counts and publishers from the editions of each work, without network."""

import update_editions

ENTITY = "http://www.wikidata.org/entity/"
FRENCH, ENGLISH = "Q150", "Q1860"


def _uri(qid):
    return {"type": "uri", "value": ENTITY + qid}


def _edition(work, edition, lang, pages=None, publisher=None, date=None):
    row = {"work": _uri(work), "edition": _uri(edition), "lang": _uri(lang)}
    if pages is not None:
        row["pages"] = {"type": "literal", "value": str(pages)}
    if publisher is not None:
        row["publisher"] = _uri(publisher)
    if date is not None:
        row["date"] = {"type": "literal", "value": date}
    return row


def _publisher(qid, fr=None, en=None, classes=("Q2085381",), country=None):
    rows = []
    for cls in classes or (None,):
        row = {"publisher": _uri(qid)}
        if fr:
            row["fr"] = {"value": fr}
        if en:
            row["en"] = {"value": en}
        if cls:
            row["class"] = _uri(cls)
        if country:
            row["country"] = {"value": country}
        rows.append(row)
    return rows


def test_parse_editions_keeps_plausible_page_counts_and_the_earliest_date():
    editions = update_editions.parse_editions([
        _edition("Q1", "Q10", FRENCH, pages=320, publisher="Q100", date="1990-01-01T00:00:00Z"),
        _edition("Q1", "Q10", FRENCH, pages=940512, publisher="Q101", date="1985-01-01T00:00:00Z"),
        _edition("Q1", "Q11", ENGLISH, pages=4),
        _edition("Q1", "Q12", "Q188", pages=200),  # German: not a catalogue locale
    ])

    assert editions == {
        ("Q1", "fr_FR"): {"Q10": {"pages": 320, "publishers": ["Q100", "Q101"], "year": 1985}},
        ("Q1", "en_US"): {"Q11": {"pages": None, "publishers": [], "year": None}},
    }


def test_choose_prefers_complete_then_earliest_editions():
    old_pages = {"id": "Q1", "pages": 300, "publisher": None, "year": 1900}
    complete = {"id": "Q2", "pages": 280, "publisher": "gallimard", "year": 1990}
    earlier_complete = {"id": "Q3", "pages": 260, "publisher": "plon", "year": 1950}

    assert update_editions.choose([old_pages, complete, earlier_complete], {"pages", "publisher"}) is earlier_complete
    assert update_editions.choose([old_pages, complete], {"pages"}) is old_pages
    assert update_editions.choose([old_pages], {"publisher"}) is None


def _data(**book):
    book = {"year": 1950, "genre": ["novel"], "title": {"fr_FR": "T", "en_US": "T"},
            "pages": None, "publisher": None, "wikidata_id": "Q1", **book}
    return {"genres": {}, "publishers": {
        "gallimard": {"name": "Gallimard", "aliases": ["Éditions Gallimard"], "country": "FR"},
        "knopf": {"name": "Alfred A. Knopf", "country": "US", "wikidata_id": "Q200"},
        "unused": {"name": "Unused House"},
    }, "authors": [{"name": "A", "books": [book]}]}


def _run(data, edition_rows, publisher_rows=(), languages=()):
    rows = [row for publisher in publisher_rows for row in publisher]
    return update_editions.update(
        data, update_editions.parse_editions(edition_rows),
        {"Q1": set(languages)}, update_editions.parse_publishers(rows))


def test_missing_values_come_from_one_edition_of_the_locale_language():
    data = _data(publisher={"fr_FR": None, "en_US": "knopf"})
    report = _run(data, [
        _edition("Q1", "Q10", FRENCH, pages=320, publisher="Q100", date="1960"),
        _edition("Q1", "Q11", FRENCH, pages=300, date="1955"),
        _edition("Q1", "Q12", ENGLISH, pages=280, publisher="Q200"),
    ], [_publisher("Q100", fr="Éditions Gallimard")], languages={"en_US"})

    book = data["authors"][0]["books"][0]
    # The French edition giving both values, matched by name onto the vocabulary
    assert book["pages"] == {"fr_FR": 320, "en_US": 280}
    assert book["publisher"] == {"fr_FR": "gallimard", "en_US": "knopf"}
    assert report["pages[fr_FR] filled"] == report["publisher[fr_FR] filled"] == 1
    # Publishers no longer used leave the vocabulary
    assert list(data["publishers"]) == ["gallimard", "knopf"]


def test_values_of_the_original_edition_are_replaced_in_the_other_locale_only():
    data = _data(pages={"fr_FR": 400, "en_US": 400}, publisher={"fr_FR": "knopf", "en_US": "knopf"})
    report = _run(data, [
        _edition("Q1", "Q10", FRENCH, pages=448, publisher="Q300"),
        _edition("Q1", "Q12", ENGLISH, pages=380, publisher="Q301"),
    ], [_publisher("Q300", fr="Éditions Denoël", country="FR"),
        _publisher("Q301", en="Vintage", country="US")], languages={"en_US"})

    book = data["authors"][0]["books"][0]
    # An American novel: its English values are those of the original edition, and stay
    assert book["pages"] == {"fr_FR": 448, "en_US": 400}
    assert book["publisher"] == {"fr_FR": "editions-denoel", "en_US": "knopf"}
    assert data["publishers"]["editions-denoel"] == {"name": "Éditions Denoël", "country": "FR",
                                                     "wikidata_id": "Q300"}
    assert "vintage" not in data["publishers"]  # added for an edition left unused, then dropped
    assert report["publisher[fr_FR] replaced"] == 1 and report["publishers added"] == 1


def test_values_typed_by_hand_are_left_alone():
    data = _data(pages={"fr_FR": 400, "en_US": 380}, pages_estimated=True,
                 publisher={"fr_FR": "gallimard", "en_US": "knopf"}, publisher_estimated=True)
    before = dict(data["authors"][0]["books"][0])

    _run(data, [_edition("Q1", "Q10", FRENCH, pages=120, publisher="Q200")])

    assert data["authors"][0]["books"][0] == before


def test_people_websites_and_collections_are_not_added_as_publishers():
    data = _data()
    _run(data, [
        _edition("Q1", "Q10", FRENCH, publisher="Q400"),
        _edition("Q1", "Q11", FRENCH, publisher="Q401"),
        _edition("Q1", "Q12", ENGLISH, publisher="Q402"),
    ], [_publisher("Q400", fr="Gallica", classes=("Q212805",)),
        _publisher("Q401", fr="Ailleurs et Demain", classes=("Q20655472",)),
        # A person whose name is that of a known publisher still maps onto it
        _publisher("Q402", en="Éditions Gallimard", classes=("Q5",))])

    assert data["authors"][0]["books"][0]["publisher"] == {"fr_FR": None, "en_US": "gallimard"}
    assert set(data["publishers"]) == {"gallimard"}
