"""Filling the series of the bundled books, without network."""

import update_series

ENTITY = "http://www.wikidata.org/entity/"


def _row(work, series, type_, position=None, **labels):
    row = {"work": {"value": ENTITY + work}, "series": {"value": ENTITY + series}, "type": {"value": type_}}
    row.update({key: {"value": value} for key, value in labels.items()})
    if position is not None:
        row["position"] = {"value": position}
    return row


def test_only_series_of_books_and_recurring_characters_are_kept():
    keep = ["novel series", "literary trilogy", "literary dylogy", "heptalogy", "literary cycle",
            "fictional human", "literary character"]
    leave = ["editorial collection", "magazine", "media franchise", "television series", "miniseries",
             "comic strip series", "television character", "mythology", "fictional country"]
    assert all(update_series.is_book_series([label]) for label in keep)
    assert not any(update_series.is_book_series([label]) for label in leave)
    # One series-like class is enough: "Voyages extraordinaires" is also an editorial collection
    assert update_series.is_book_series(["editorial collection", "book series"])


def test_series_are_grouped_with_their_rank():
    works, labels = update_series.parse_series([
        _row("Q1", "Q6027", "book series", "9", fr="Les Rougon-Macquart", en="Les Rougon-Macquart"),
        # Same statement seen through another class label: the rank is kept
        _row("Q1", "Q6027", "literary cycle", fr="Les Rougon-Macquart", en="Les Rougon-Macquart"),
        _row("Q2", "Q6027", "book series", "3.2", fr="Les Rougon-Macquart", en="Les Rougon-Macquart"),
        _row("Q2", "Q462", "media franchise", "1", en="Star Wars"),
    ])

    assert works == {"Q1": [{"id": "Q6027", "position": 9}], "Q2": [{"id": "Q6027"}]}
    assert labels == {"Q6027": {"fr_FR": "Les Rougon-Macquart", "en_US": "Les Rougon-Macquart"}}


def test_names_fall_back_on_the_multilingual_then_the_english_label():
    _, labels = update_series.parse_series([
        _row("Q1", "Q8337", "novel series", mul="Harry Potter"),
        _row("Q2", "Q21997237", "book series", en="Wallander novels"),
        _row("Q3", "Q122441953", "book series", en="canon of Hercule Poirot"),
        _row("Q4", "Q5", "literary trilogy", en="Foundation Trilogy"),
        _row("Q5", "Q6", "novel series"),  # no name at all
    ])

    assert labels == {
        "Q8337": {"fr_FR": "Harry Potter", "en_US": "Harry Potter"},
        "Q21997237": {"fr_FR": "Wallander", "en_US": "Wallander novels"},
        "Q122441953": {"fr_FR": "Hercule Poirot", "en_US": "Hercule Poirot"},
        "Q5": {"fr_FR": "Foundation Trilogy", "en_US": "Foundation Trilogy"},
    }


def test_update_writes_the_vocabulary_after_the_awards_and_series_after_the_awards():
    data = {"genres": {}, "awards": {"Q9": {}}, "publishers": {}, "authors": [{"books": [
        {"year": 1, "genre": ["novel"], "awards": ["Q9"], "title": {}, "wikidata_id": "Q1"},
        {"year": 2, "genre": ["novel"], "title": {}, "wikidata_id": "Q2"},
        {"year": 3, "genre": ["novel"], "series": [{"id": "Q7"}], "title": {}},
    ]}], "series": {"Q7": {}}}
    labels = {"Q6027": {"fr_FR": "Les Rougon-Macquart", "en_US": "Les Rougon-Macquart"},
              "Q8337": {"fr_FR": "Harry Potter", "en_US": "Harry Potter"}}

    report = update_series.update(data, {"Q1": [{"id": "Q6027", "position": 2}, {"id": "Q8337"}]}, labels)

    first, second, third = data["authors"][0]["books"]
    assert list(data) == ["genres", "awards", "series", "publishers", "authors"]
    assert list(data["series"]) == ["Q6027", "Q8337"]
    assert list(first) == ["year", "genre", "awards", "series", "title", "wikidata_id"]
    assert first["series"] == [{"id": "Q8337"}, {"id": "Q6027", "position": 2}]  # sorted by English name
    assert "series" not in second and "series" not in third
    assert report == {"books in a series": 1, "books without series": 2, "ranks": 1, "series": 2}
