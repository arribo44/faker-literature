"""Filling the English page counts and publishers from Open Library, without network."""

import update_openlibrary as ol

from faker_literature.vocabulary import PublisherVocabulary


def _vocabulary():
    return PublisherVocabulary({
        "gallimard": {"name": "Gallimard", "country": "FR"},
        "little-brown": {"name": "Little, Brown", "country": "US"},
        "knopf": {"name": "Alfred A. Knopf", "aliases": ["Knopf"], "country": "US"},
        "kodansha": {"name": "Kodansha", "country": "JP"},
    })


def _edition(year, pages, publisher, places=("New York",), languages=("eng",), title="A Novel", form="", key=None):
    return {"key": key or f"/books/OL{year}{pages}M", "title": title, "languages": list(languages), "pages": pages,
            "publishers": [publisher], "places": list(places), "year": year, "format": form}


def test_places_of_publication_give_english_speaking_countries():
    assert ol.place_country("New York") == "US"
    assert ol.place_country("Cambridge, Mass.") == "US"
    assert ol.place_country("Cambridge") == "GB"
    assert ol.place_country("Harmondsworth, Middlesex, England") == "GB"
    assert ol.place_country("Toronto") == "CA"
    assert ol.place_country("Paris") is None and ol.place_country("Tokyo") is None


def test_simplify_keeps_the_fields_of_an_edition():
    edition = ol.simplify({
        "key": "/books/OL1M", "title": "Kokoro", "subtitle": "a novel", "languages": [{"key": "/languages/eng"}],
        "number_of_pages": 248, "publishers": ["H. Regnery Co."], "publish_places": ["Chicago"],
        "publish_date": "c1957", "physical_format": "Hardcover"})

    assert edition == {"key": "/books/OL1M", "title": "Kokoro a novel", "languages": ["eng"], "pages": 248,
                       "publishers": ["H. Regnery Co."], "places": ["Chicago"], "year": 1957, "format": "Hardcover"}


def test_unusual_editions_are_left_out():
    assert ol.usable(_edition(1960, 300, "Knopf"), 1957)
    assert not ol.usable(_edition(1950, 300, "Knopf"), 1957)  # older than the work: a wrong date
    assert not ol.usable(_edition(1960, 300, "Knopf", languages=("fre",)), 1957)
    assert not ol.usable(_edition(1960, None, "Knopf"), 1957)
    assert not ol.usable(_edition(1960, 300, "Knopf", form="Audio CD"), 1957)
    assert not ol.usable(_edition(1960, 300, "Knopf", title="Kokoro (Large Print)"), 1957)
    assert not ol.usable(_edition(1960, 300, "CreateSpace Independent Publishing Platform"), 1957)
    assert not ol.usable(_edition(1960, 300, "Book-of-the-Month Club"), 1957)


def test_publishers_are_matched_and_english_ones_added():
    vocabulary = _vocabulary()
    publishers = ol.OpenLibraryPublishers(vocabulary)

    assert publishers.resolve("Little, Brown and Co.") == "little-brown"
    assert publishers.resolve("Knopf, Inc.") == "knopf"
    # A publisher of another language is refused, whatever its place
    assert publishers.resolve("Gallimard", ["New York"]) is None
    assert publishers.resolve("Kodansha International", ["Tokyo"]) is None
    # Unknown: added only with an English-speaking place, without its corporate suffix
    assert publishers.resolve("Grove Press, Inc.", ["New York, N.Y."]) == "grove-press"
    assert vocabulary.publishers["grove-press"] == {"name": "Grove Press", "country": "US"}
    assert publishers.resolve("Grove Press") == "grove-press"
    assert publishers.resolve("Unknown House", []) is None
    assert publishers.added == ["grove-press"]


def test_short_typed_and_composite_names_find_the_known_publisher():
    publishers = ol.OpenLibraryPublishers(PublisherVocabulary({
        "jonathan-cape": {"name": "Jonathan Cape", "country": "GB"},
        "henry-holt": {"name": "Henry Holt and Company", "country": "US"},
        "norton": {"name": "W. W. Norton & Company", "country": "US"},
        "routledge": {"name": "George Routledge & Sons", "country": "GB"},
        "fsg": {"name": "Farrar, Straus and Giroux", "country": "US"},
        "knopf": {"name": "Alfred A. Knopf", "aliases": ["Knopf"], "country": "US"},
        "dell": {"name": "Dell Publishing", "country": "US"},
        "lippincott-a": {"name": "J. B. Lippincott & Co.", "country": "US"},
        "lippincott-b": {"name": "Joshua Lippincott", "country": "US"},
    }))

    assert publishers.resolve("J. Cape") == "jonathan-cape"  # initials of the founder
    assert publishers.resolve("H. Holt") == "henry-holt"
    assert publishers.resolve("G. Routledge & sons") == "routledge"
    assert publishers.resolve("Cape") == "jonathan-cape"  # his surname alone
    assert publishers.resolve("Norton") == "norton"
    assert publishers.resolve("Lippincott", ["Philadelphia"]) == "lippincott"  # shared surname: a new one
    assert publishers.resolve("Farrar Strauss Giroux") == "fsg"  # a typo
    assert publishers.resolve("Dell Pub.") == "dell"
    assert publishers.resolve("Knopf; [distributed by Random House") == "knopf"


def test_imprint_statements_do_not_become_publishers():
    publishers = ol.OpenLibraryPublishers(_vocabulary())

    assert publishers.resolve("Printed for Walker and Edwards", ["London"]) is None
    assert publishers.resolve("published for the proprietors, by W. Simpkin and R. Marshall", ["London"]) is None
    assert publishers.resolve("Sold by J. Smith, 66 Pall-Mall", ["London"]) is None
    assert publishers.added == []


def _data(book):
    return {"publishers": dict(_vocabulary().publishers), "authors": [{"name": "A", "books": [book]}]}


def test_the_earliest_english_edition_gives_pages_and_publisher_together():
    book = {"year": 1957, "title": {"fr_FR": "Le Roman", "en_US": "The Novel"}, "wikidata_id": "Q1",
            "pages": {"fr_FR": 320, "en_US": 280}, "publisher": {"fr_FR": "gallimard", "en_US": None}}
    data = _data(book)
    cache = {"works": {"Q1": ["OL1W"]}, "editions": {"OL1W": [
        _edition(1975, 350, "Penguin Books", places=["Harmondsworth"]),
        _edition(1960, 300, "Knopf"),
        _edition(1958, 290, "Knopf", languages=("fre",)),
    ]}}

    report = ol.update(data, cache)

    assert book["publisher"] == {"fr_FR": "gallimard", "en_US": "knopf"}
    assert book["pages"] == {"fr_FR": 320, "en_US": 300}  # the page count of the same edition
    assert report["publisher[en_US] filled"] == 1 and report["pages[en_US] replaced"] == 1
    # Penguin Books was not used: not added to the vocabulary
    assert "penguin-books" not in data["publishers"]


def test_a_missing_page_count_comes_from_an_edition_of_the_same_publisher():
    book = {"year": 1957, "title": {"fr_FR": "R", "en_US": "R"}, "wikidata_id": "Q1",
            "pages": None, "publisher": {"fr_FR": "gallimard", "en_US": "little-brown"}}
    data = _data(book)
    cache = {"works": {"Q1": ["OL1W"]}, "editions": {"OL1W": [
        _edition(1960, 300, "Knopf"), _edition(1970, 310, "Little, Brown & Company", places=["Boston"])]}}

    ol.update(data, cache)

    assert book["pages"] == {"fr_FR": None, "en_US": 310}


def test_estimates_typed_by_hand_are_left_alone():
    book = {"year": 1957, "title": {"fr_FR": "R", "en_US": "R"}, "wikidata_id": "Q1",
            "pages": {"fr_FR": 100, "en_US": 90}, "pages_estimated": True,
            "publisher": {"fr_FR": "gallimard", "en_US": "knopf"}, "publisher_estimated": True}
    data = _data(book)

    report = ol.update(data, {"works": {"Q1": ["OL1W"]}, "editions": {"OL1W": [_edition(1960, 300, "Knopf")]}})

    assert book["pages"]["en_US"] == 90 and book["publisher"]["en_US"] == "knopf"
    assert not [key for key in report if key.endswith(("filled", "replaced"))]
