"""Filling the literary awards of the bundled books, without network."""

import update_awards


def _row(work, award, fr, en):
    entity = "http://www.wikidata.org/entity/"
    return {"work": {"value": entity + work}, "award": {"value": entity + award},
            "fr": {"value": fr}, "en": {"value": en}}


def test_awards_are_grouped_and_lists_left_out():
    works, labels = update_awards.parse_awards([
        _row("Q1", "Q187300", "prix Goncourt", "Prix Goncourt"),
        _row("Q1", "Q187300", "prix Goncourt", "Prix Goncourt"),
        _row("Q1", "Q671613", "Les cent meilleurs romans", "Modern Library 100 Best Novels"),
        _row("Q2", "Q255032", "prix Hugo du meilleur roman", "Hugo Award for Best Novel"),
    ])

    assert works == {"Q1": ["Q187300"], "Q2": ["Q255032"]}
    assert labels["Q187300"] == {"fr_FR": "prix Goncourt", "en_US": "Prix Goncourt"} and "Q671613" not in labels


def test_update_writes_the_vocabulary_after_the_genres_and_awards_after_the_genre():
    data = {"genres": {}, "authors": [{"name": "A", "books": [
        {"year": 1, "genre": ["novel"], "title": {}, "wikidata_id": "Q1"},
        {"year": 2, "genre": ["novel"], "awards": ["Q9"], "title": {}, "wikidata_id": "Q2"},
    ]}], "awards": {"Q9": {}}}
    labels = {"Q255032": {"fr_FR": "prix Hugo", "en_US": "Hugo Award"},
              "Q187300": {"fr_FR": "prix Goncourt", "en_US": "Prix Goncourt"}}

    report = update_awards.update(data, {"Q1": ["Q255032", "Q187300"]}, labels)

    assert list(data) == ["genres", "awards", "authors"]
    assert list(data["awards"]) == ["Q187300", "Q255032"]
    first, second = data["authors"][0]["books"]
    assert list(first) == ["year", "genre", "awards", "title", "wikidata_id"]
    assert first["awards"] == ["Q255032", "Q187300"]  # sorted by English label
    assert "awards" not in second
    assert report == {"books with an award": 1, "books without award": 1, "awards": 2}
