"""Filling the popularity of the bundled books, without network."""

import update_popularity


def _catalogue():
    return {"authors": [
        {"name": "Victor Hugo", "books": [
            {"year": 1862, "title": {"fr_FR": "Les Misérables", "en_US": "Les Misérables"}, "wikidata_id": "Q180736"},
            {"year": 1831, "title": {"fr_FR": "Notre-Dame de Paris", "en_US": "The Hunchback of Notre-Dame"},
             "pages": None},
        ]},
        {"name": "Somebody", "books": [
            {"year": 2000, "title": {"fr_FR": "Copie", "en_US": "Copy"}},
            {"year": 2001, "title": {"fr_FR": "Introuvable", "en_US": "Not Found"}},
        ]},
    ]}


def test_found_works_get_their_id_and_every_known_work_its_popularity():
    data = _catalogue()
    # Notre-Dame found; "Copy" found too, but its work is already the Misérables one
    works = {(0, 1): "Q160476", (1, 0): "Q180736"}
    counts = {"Q180736": 120, "Q160476": 90}

    report = update_popularity.update(data, works, counts)

    miserables, notre_dame = data["authors"][0]["books"]
    assert miserables["popularity"] == 120
    assert list(notre_dame) == ["year", "title", "pages", "popularity", "wikidata_id"]
    assert notre_dame["wikidata_id"] == "Q160476" and notre_dame["popularity"] == 90
    copy, not_found = data["authors"][1]["books"]
    assert "wikidata_id" not in copy and "popularity" not in copy and "popularity" not in not_found
    assert report == {"Wikidata id found": 1, "found, but the work is already in the catalogue": 1,
                      "popularity set": 2, "no popularity": 2}


def test_popularity_and_id_stay_last_when_updated():
    book = {"year": 1, "popularity": 3, "wikidata_id": "Q1", "title": "T"}

    assert list(update_popularity._with(book, popularity=5)) == ["year", "title", "popularity", "wikidata_id"]
    assert update_popularity._with(book, popularity=5)["popularity"] == 5
