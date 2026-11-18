"""French page counts and publishers from the BnF catalogue, without network."""

import pytest
import update_bnf

from faker_literature.vocabulary import PublisherVocabulary


@pytest.mark.parametrize("extent, pages", [
    ("286 p.", 286),
    ("1 vol. (377 p.)", 377),
    ("1 volume 385 p", 385),
    ("XXVI-1364 p.", 1364),
    ("359 p.-[4] p. de cartes", 359),
    ("2 vol., 603 p.-[16] p. de pl. en coul.", None),  # several volumes
    ("[83] p.", None),  # unnumbered pages
    ("8 p.", None),  # a leaflet
    ("", None),
])
def test_parse_pages(extent, pages):
    assert update_bnf.parse_pages(extent) == pages


def _field(tag, **subfields):
    codes = "".join(f'<mx:subfield code="{code}">{value}</mx:subfield>' for code, value in subfields.items())
    return f'<mx:datafield tag="{tag}">{codes}</mx:datafield>'


def _record(*fields, identifier="FRBNF1"):
    return f'<mx:record><mx:controlfield tag="001">{identifier}</mx:controlfield>{"".join(fields)}</mx:record>'


def _answer(*records):
    return ('<srw:searchRetrieveResponse xmlns:srw="http://www.loc.gov/zing/srw/" '
            'xmlns:mx="info:lc/xmlns/marcxchange-v2">' + "".join(records) + "</srw:searchRetrieveResponse>")


def test_parse_records_reads_the_publication_of_old_and_new_records():
    old = _record(_field("101", a="fre"), _field("200", a="Shutter Island"), _field("700", a="Lehane"),
                  _field("210", a="Paris", c="Payot et Rivages", d="2003"), _field("215", a="286 p."))
    new = _record(_field("101", a="fre"), _field("200", a="Shutter Island"),
                  _field("214", a="Paris", c="Éditions Payot &amp; Rivages", d="impr. 2014"),
                  _field("215", a="1 vol. (392 p.)"), _field("225", a="Rivages-noir"), identifier="FRBNF2")

    first, second = update_bnf.parse_records(_answer(old, new))

    assert first == {"id": "FRBNF1", "languages": ["fre"], "titles": ["Shutter Island"], "original_titles": [],
                     "authors": ["Lehane"],
                     "publishers": ["Payot et Rivages"], "places": ["Paris"], "year": 2003, "pages": 286,
                     "extent": "286 p.", "collections": []}
    assert second["publishers"] == ["Éditions Payot & Rivages"] and second["year"] == 2014
    assert second["pages"] == 392 and second["collections"] == ["Rivages-noir"]


def _edition(publisher, year, pages=300, title="Persuasion", languages=("fre",), collections=(), extent=""):
    return {"id": "FRBNF", "languages": list(languages), "titles": [title], "authors": ["Austen"],
            "publishers": [publisher] if publisher else [], "places": ["Paris"], "year": year, "pages": pages,
            "extent": extent, "collections": list(collections)}


def test_matches_needs_a_french_text_of_the_same_title_in_ordinary_print():
    assert update_bnf.matches(_edition("Gallimard", 2011, title="La Persuasion"), "Persuasion")
    assert not update_bnf.matches(_edition("Gallimard", 2011, title="Raison et sentiments"), "Persuasion")
    assert not update_bnf.matches(_edition("Penguin", 2011, languages=("eng",)), "Persuasion")
    assert not update_bnf.matches(_edition("Libra", 2011, collections=["Grands caractères"]), "Persuasion")


def test_loose_key_ignores_editions_and_et():
    assert update_bnf.loose_key("Payot et Rivages") == update_bnf.loose_key("Éditions Payot & Rivages")
    assert update_bnf.loose_key("Éd. du Seuil") == update_bnf.loose_key("Éditions du Seuil")
    assert update_bnf.loose_key("Presses pocket") == "pocket"


def _publishers():
    return update_bnf.BnfPublishers(PublisherVocabulary({
        "gallimard": {"name": "Gallimard", "country": "FR"},
        "payot-rivages": {"name": "Payot & Rivages", "country": "FR"},
        "pocket": {"name": "Pocket", "country": "FR"},
        "pocket-books": {"name": "Pocket Books", "country": "US"},
    }))


def test_bnf_names_map_onto_the_vocabulary():
    publishers = _publishers()
    assert publishers.resolve("Payot et Rivages") == "payot-rivages"
    assert publishers.resolve("Presses pocket") == "pocket"  # the French Pocket, not Pocket Books
    assert publishers.resolve("[s.n.]") is None
    assert publishers.resolve("Éd. Archipoche") is None
    assert publishers.resolve("Éd. Archipoche", create=True, country="FR") == "editions-archipoche"
    assert publishers.vocabulary.publishers["editions-archipoche"] == {"name": "Éditions Archipoche",
                                                                       "country": "FR"}


def test_choose_takes_the_publisher_of_most_editions_and_its_earliest_paginated_one():
    publishers = _publishers()
    editions = [
        _edition("Archipoche", 2011), _edition("Hachette", 1882),
        _edition("Gallimard", 2011, pages=None), _edition("Gallimard", 2015, pages=420),
        _edition("Éditions Gallimard", 2018, pages=410),
        # Book clubs reprint more than anybody, and come last
        _edition("France loisirs", 1990), _edition("France loisirs", 1991), _edition("France loisirs", 1992),
        _edition("France loisirs", 1993),
    ]

    publisher_id, edition = update_bnf.choose(editions, publishers)

    assert publisher_id == "gallimard" and edition["year"] == 2015 and edition["pages"] == 420
    # An unknown publisher is added when chosen
    publisher_id, edition = update_bnf.choose([_edition("Archipoche", 2011)], publishers)
    assert publisher_id == "archipoche" and publishers.added == ["archipoche"]


def _catalogue(**book):
    book = {"year": 1817, "genre": ["novel"], "title": {"fr_FR": "Persuasion", "en_US": "Persuasion"},
            "pages": {"fr_FR": 250, "en_US": 250}, "publisher": {"fr_FR": "murray", "en_US": "murray"},
            "wikidata_id": "Q1", **book}
    return {"genres": {}, "publishers": {
        "murray": {"name": "John Murray", "country": "GB"},
        "gallimard": {"name": "Gallimard", "country": "FR"},
    }, "authors": [{"name": "Jane Austen", "books": [book]}]}


def test_needs():
    vocabulary = PublisherVocabulary(_catalogue()["publishers"])
    # A British publisher in French, with the page count of the original edition
    assert update_bnf.needs(_catalogue()["authors"][0]["books"][0], vocabulary) == {"pages", "publisher"}
    assert update_bnf.needs({"pages": {"fr_FR": 300, "en_US": 250}, "publisher": {"fr_FR": "murray"}},
                            vocabulary) == {"publisher"}
    assert update_bnf.needs({"pages": None, "publisher": {"fr_FR": "gallimard"}}, vocabulary) == {"pages"}
    assert update_bnf.needs({"title_untranslated": True, "pages": None, "publisher": None}, vocabulary) == set()
    assert update_bnf.needs({"pages": {"fr_FR": 300}, "pages_estimated": True,
                             "publisher": {"fr_FR": "murray"}, "publisher_estimated": True}, vocabulary) == set()


def test_update_writes_the_french_values_of_one_edition():
    data = _catalogue()
    cache = {"Q1": [_edition("Gallimard", 2011, pages=420, title="Persuasion"),
                    _edition("Penguin", 1990, languages=("eng",))]}

    report = update_bnf.update(data, cache)

    book = data["authors"][0]["books"][0]
    assert book["pages"] == {"fr_FR": 420, "en_US": 250}
    assert book["publisher"] == {"fr_FR": "gallimard", "en_US": "murray"}
    assert report["publisher[fr_FR] replaced"] == report["pages[fr_FR] replaced"] == 1


def test_books_without_french_edition_are_left_alone():
    data = _catalogue()
    report = update_bnf.update(data, {"Q1": [_edition("Gallimard", 2011, title="Emma")]})

    assert data["authors"][0]["books"][0]["publisher"]["fr_FR"] == "murray"
    assert report["no French edition found"] == 1 and "publisher[fr_FR] replaced" not in report


# Books without French title

@pytest.mark.parametrize("bnf, title", [
    ("l'architecture du bonheur", "L'Architecture du bonheur"),
    ("Le vol du corbeau", "Le Vol du corbeau"),
    ("les fourmis.", "Les Fourmis"),
    ("L’écume des jours", "L'Écume des jours"),
    ("une saison en enfer", "Une saison en enfer"),  # an indefinite article: only the first word
    ("Des souris et des hommes", "Des souris et des hommes"),
    ("bande de menteurs", "Bande de menteurs"),
    ("La vie devant soi", "La Vie devant soi"),
])
def test_french_title(bnf, title):
    assert update_bnf.french_title(bnf) == title


def test_parse_records_reads_the_original_title():
    record = _record(_field("101", a="fre", c="eng"), _field("200", a="L'architecture du bonheur"),
                     _field("454", t="The architecture of happiness"))
    [edition] = update_bnf.parse_records(_answer(record))
    assert edition["original_titles"] == ["The architecture of happiness"]


def _translation(title, original="The Architecture of Happiness", year=2007, publisher="Mercure de France",
                 pages=280, languages=("fre",)):
    return dict(_edition(publisher, year, pages=pages, title=title, languages=languages),
                original_titles=[original])


def test_matches_original_needs_a_french_only_translation_of_that_title():
    assert update_bnf.matches_original(_translation("L'architecture du bonheur"), "The architecture of happiness")
    original = "The Architecture of Happiness"
    assert not update_bnf.matches_original(_translation("Howl", languages=("fre", "eng")), original)
    assert not update_bnf.matches_original(_translation("X", original="Status Anxiety"), original)
    # Records cached before the original titles were read
    old = _edition("Gallimard", 2000)
    assert not update_bnf.matches_original(old, "Persuasion")


def _untranslated():
    book = {"year": 2006, "genre": ["essay"], "title_untranslated": True,
            "title": {"fr_FR": "The Architecture of Happiness", "en_US": "The Architecture of Happiness"},
            "pages": None, "publisher": None, "wikidata_id": "Q7"}
    return {"genres": {}, "publishers": {"mercure": {"name": "Mercure de France", "country": "FR"}},
            "authors": [{"name": "Alain de Botton", "books": [book]}]}


def test_proposals_give_the_most_frequent_title_of_the_translations():
    data = _untranslated()
    cache = {"original:Q7": [
        _translation("L'architecture du bonheur", year=2007),
        _translation("L'architecture du bonheur", year=2009),
        _translation("Architecture et bonheur", year=2006),
        _translation("Du bonheur", original="Status Anxiety"),
    ]}

    [proposal] = update_bnf.propose_titles(data, cache)

    assert proposal == {"wikidata_id": "Q7", "author": "Alain de Botton",
                        "en_US": "The Architecture of Happiness", "fr_FR": "L'Architecture du bonheur",
                        "translations": 3, "other_titles": ["Architecture et bonheur"]}


def test_reviewed_titles_are_applied_then_the_translations_give_pages_and_publisher():
    data = _untranslated()
    cache = {"original:Q7": [_translation("L'architecture du bonheur", pages=280)]}
    proposals = update_bnf.propose_titles(data, cache)

    assert update_bnf.apply_titles(data, proposals) == 1
    report = update_bnf.update(data, cache)

    book = data["authors"][0]["books"][0]
    assert book["title"] == {"fr_FR": "L'Architecture du bonheur", "en_US": "The Architecture of Happiness"}
    assert "title_untranslated" not in book
    assert book["pages"]["fr_FR"] == 280 and book["publisher"]["fr_FR"] == "mercure"
    assert report["pages[fr_FR] filled"] == 1


def test_a_proposal_for_another_title_is_refused():
    with pytest.raises(ValueError, match="catalogue title"):
        update_bnf.apply_titles(_untranslated(), [{"wikidata_id": "Q7", "en_US": "Status Anxiety",
                                                  "fr_FR": "Du bonheur"}])


def test_collect_looks_untranslated_books_up_by_their_original_title(monkeypatch):
    searched = []
    monkeypatch.setattr(update_bnf, "search", lambda title, name, sleep: searched.append((title, name)) or _answer())
    cache = {}

    update_bnf.collect(_untranslated(), cache, log=lambda message: None, sleep=lambda seconds: None)
    assert searched == [] and cache == {}  # without --titles, nothing to look up

    update_bnf.collect(_untranslated(), cache, titles=True, log=lambda message: None, sleep=lambda seconds: None)
    assert searched == [("The Architecture of Happiness", "Botton")]
    assert cache == {"original:Q7": []}


def test_a_foreign_french_publisher_typed_by_hand_is_replaced():
    data = _catalogue(pages={"fr_FR": 250, "en_US": 240}, pages_estimated=True, publisher_estimated=True)
    vocabulary = PublisherVocabulary(data["publishers"])
    assert update_bnf.needs(data["authors"][0]["books"][0], vocabulary) == {"publisher"}

    report = update_bnf.update(data, {"Q1": [_edition("Gallimard", 2011, pages=420)]})

    book = data["authors"][0]["books"][0]
    assert book["publisher"] == {"fr_FR": "gallimard", "en_US": "murray"}
    assert book["pages"] == {"fr_FR": 250, "en_US": 240}  # the estimate is not that of this edition
    assert book["publisher_estimated"] is True and report["publisher[fr_FR] estimate replaced"] == 1
    # A French publisher typed by hand stays
    book["publisher"]["fr_FR"] = "gallimard"
    assert update_bnf.needs(book, vocabulary) == set()


def test_english_titles_left_without_flag_are_looked_up_too():
    data = _untranslated()
    del data["authors"][0]["books"][0]["title_untranslated"]
    cache = {"original:Q7": [_translation("L'architecture du bonheur")]}

    [proposal] = update_bnf.propose_titles(data, cache)
    assert update_bnf.apply_titles(data, [proposal]) == 1
    assert data["authors"][0]["books"][0]["title"]["fr_FR"] == "L'Architecture du bonheur"


def test_a_title_that_is_the_same_in_french_is_not_proposed():
    data = _untranslated()
    data["authors"][0]["books"][0]["title"] = {"fr_FR": "Dune", "en_US": "Dune"}
    cache = {"original:Q7": [_translation("Dune", original="Dune")]}
    assert update_bnf.propose_titles(data, cache) == []


def test_adaptations_much_shorter_than_the_work_are_left_out():
    comics = _edition("Glénat", 2010, pages=56)
    novels = [_edition("Gallimard", 1990, pages=420), _edition("Pocket", 2000, pages=380), _edition("Archipoche", 2011)]
    # Against the median page count of the editions found
    assert update_bnf.plausible([comics, *novels]) == novels
    # Against the English page count, when known
    assert update_bnf.plausible([comics, novels[0]], reference=400) == [novels[0]]
    assert update_bnf.plausible([comics]) == [comics]  # nothing to compare with


def test_french_title_drops_original_titles_and_statements_of_responsibility():
    assert update_bnf.french_title("Grand'-Rue (Main street)") == "Grand'-Rue"
    assert update_bnf.french_title("Robert le Rouge, ou Les montagnards écossais , par l'auteur des Puritains, "
                                   "traduit de l'anglais") == "Robert le Rouge, ou Les montagnards écossais"
