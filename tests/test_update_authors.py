"""Filling the lives of the bundled authors, without network."""

import update_authors


def _row(author, prop, time, precision="11"):
    return {"author": {"value": f"http://www.wikidata.org/entity/{author}"}, "property": {"value": prop},
            "time": {"value": time}, "precision": {"value": precision}}


def test_lives_keep_the_earliest_precise_years():
    lives = update_authors.parse_lives([
        _row("Q1", "born", "1802-02-26T00:00:00Z"),
        _row("Q1", "born", "1803-01-01T00:00:00Z"),
        _row("Q1", "died", "1885-05-22T00:00:00Z"),
        _row("Q2", "born", "-0427-01-01T00:00:00Z", "9"),   # 428 BC (XSD year 0 is 1 BC)
        _row("Q3", "born", "1500-01-01T00:00:00Z", "7"),    # century: too vague
    ])

    assert lives == {"Q1": {"born": 1802, "died": 1885}, "Q2": {"born": -428}}


def test_update_sets_ids_and_lives_in_key_order():
    data = {"authors": [
        {"name": "Victor Hugo", "wikidata_id": "Q535", "nationality": {}, "books": []},
        {"name": "Found Later", "nationality": {}, "books": []},
        {"name": "Same Id", "nationality": {}, "books": []},
        {"name": "Broken", "wikidata_id": "Q9", "nationality": {}, "books": []},
    ]}
    lives = {"Q535": {"born": 1802, "died": 1885}, "Q7": {"born": 1950}, "Q9": {"born": 1900, "died": 1800}}

    report = update_authors.update(data, {1: "Q7", 2: "Q535"}, lives)

    hugo, found, same, broken = data["authors"]
    assert list(hugo) == ["name", "wikidata_id", "nationality", "born", "died", "books"]
    assert (found["wikidata_id"], found["born"], "died" in found) == ("Q7", 1950, False)
    # An id already used by another author is not given twice
    assert "wikidata_id" not in same and "born" not in same
    assert "born" not in broken
    assert report["Wikidata id found"] == 1 and report["inconsistent life skipped"] == 1
