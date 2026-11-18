import copy
import json

import editor
import pytest


def _cells(**values):
    return {key: {"type": "literal", "value": value} for key, value in values.items()}


WORK = "http://www.wikidata.org/entity/Q100"
FRENCH = "http://www.wikidata.org/entity/Q150"
ENGLISH = "http://www.wikidata.org/entity/Q1860"


@pytest.fixture
def catalogue():
    return copy.deepcopy(editor.load_catalogue())


def _author(**overrides):
    author = {
        "wikidata_id": "Q999999",
        "name": {"fr_FR": "Murasaki Shikibu", "en_US": "Murasaki Shikibu"},
        "nationality": {"fr_FR": "japonais", "en_US": "Japanese"},
    }
    author.update(overrides)
    return author


def _book(**overrides):
    book = {
        "wikidata_id": "Q193375",
        "title": {"fr_FR": "Le Dit du Genji", "en_US": "The Tale of Genji"},
        "year": "1008",
        "genre": {"fr_FR": "roman, classique", "en_US": "novel, classic"},
        "pages": {"fr_FR": "1400", "en_US": ""},
        "publisher": {"fr_FR": "Verdier", "en_US": ""},
    }
    book.update(overrides)
    return book


@pytest.mark.parametrize("text", ["Q535", "q535", " Q535 ", "https://www.wikidata.org/wiki/Q535",
                                  "http://www.wikidata.org/entity/Q535"])
def test_parse_qid_accepts_ids_and_urls(text):
    assert editor.parse_qid(text) == "Q535"


@pytest.mark.parametrize("text", ["", "Victor Hugo", "Q0", "P31", "Q535 } DELETE", "https://evil.example/wiki/Q535"])
def test_parse_qid_rejects_anything_else(text):
    with pytest.raises(ValueError):
        editor.parse_qid(text)


def test_parse_author_picks_one_country_and_falls_back_on_the_other_name():
    rows = [
        _cells(nameEn="Victor Hugo", country="http://www.wikidata.org/entity/Q142",
               demonymFr="Française", demonymEn="French"),
        _cells(country="http://www.wikidata.org/entity/Q142", demonymFr="Français", demonymEn="French"),
    ]

    author = editor.parse_author("Q535", rows)

    assert author["name"] == {"fr_FR": "Victor Hugo", "en_US": "Victor Hugo"}
    assert author["nationality"] == {"fr_FR": "français", "en_US": "French"}


def test_parse_works_uses_localized_editions_then_work_values():
    rows = [
        _cells(work=WORK, links="40", titleFr="Les Misérables", titleEn="Les Misérables", typeFr="roman",
               date="1862-04-03T00:00:00Z", genreFr="roman historique", genreEn="historical novel", pages="1500",
               publisherFr="A. Lacroix", publisherEn="A. Lacroix"),
        _cells(work="http://www.wikidata.org/entity/Q101", links="2", titleFr="Poème obscur"),
        _cells(work="http://www.wikidata.org/entity/Q102", links="99"),
    ]
    editions = [
        _cells(work=WORK, lang=FRENCH, pages="1900", publisherFr="Gallimard"),
        _cells(work=WORK, lang=ENGLISH, publisherEn="Penguin Classics"),
    ]

    works = editor.parse_works(rows, editions)

    assert [work["wikidata_id"] for work in works] == ["Q100", "Q101"]
    best = works[0]
    assert best["year"] == 1862
    assert best["pages"] == {"fr_FR": 1900, "en_US": 1500}
    assert best["publisher"] == {"fr_FR": "Gallimard", "en_US": "Penguin Classics"}
    assert best["genre"] == {"fr_FR": ["roman historique"], "en_US": ["historical novel"]}
    assert works[1]["year"] is None


def test_add_book_creates_a_sorted_author(catalogue):
    message, created = editor.add_book(catalogue, _author(), _book())

    assert created
    assert "Murasaki Shikibu" in message
    names = [editor._sort_name(entry["name"]) for entry in catalogue["authors"]]
    index = next(i for i, entry in enumerate(catalogue["authors"]) if entry.get("wikidata_id") == "Q999999")
    assert names[index - 1] <= names[index] <= names[index + 1]
    book = catalogue["authors"][index]["books"][0]
    assert book["year"] == 1008
    assert book["genre"] == ["novel", "classic"]
    assert book["pages"] == {"fr_FR": 1400, "en_US": None}
    # Publishers are ids of the publishers vocabulary: an unknown one is added
    assert book["publisher"] == {"fr_FR": "verdier", "en_US": None}
    assert catalogue["publishers"]["verdier"] == {"name": "Verdier"}
    assert "Nouvel(s) éditeur(s) : Verdier." in message
    assert "pages_estimated" not in book and "publisher_estimated" not in book


def test_add_book_maps_publishers_onto_the_vocabulary(catalogue):
    before = dict(catalogue["publishers"])
    message, _ = editor.add_book(catalogue, _author(), _book(
        publisher={"fr_FR": "Éditions Gallimard", "en_US": "penguin classics"}))

    book = next(entry for entry in catalogue["authors"] if entry.get("wikidata_id") == "Q999999")["books"][0]
    assert book["publisher"] == {"fr_FR": "gallimard", "en_US": "penguin-classics"}
    assert catalogue["publishers"] == before
    assert "éditeur" not in message


def test_a_refused_book_adds_no_publisher(catalogue):
    with pytest.raises(ValueError):
        editor.add_book(catalogue, _author(), _book(year="", publisher={"fr_FR": "Verdier", "en_US": ""}))
    assert "verdier" not in catalogue["publishers"]


def test_annotate_suggests_the_catalogue_name_of_a_publisher(catalogue):
    works = [{"title": {"fr_FR": "X", "en_US": "X"}, "year": 2000, "wikidata_id": "Q1",
              "publisher": {"fr_FR": "Éditions Gallimard", "en_US": "Unknown House"}}]
    editor.annotate(catalogue, {"wikidata_id": "Q999999", "name": {"fr_FR": "Y", "en_US": "Y"}}, works)
    assert works[0]["publisher"] == {"fr_FR": "Gallimard", "en_US": "Unknown House"}


def test_catalogue_info_lists_the_publishers_of_the_vocabulary(catalogue):
    info = editor.catalogue_info(catalogue)
    assert "Gallimard" in info["publisher"]["fr_FR"]
    assert "Université d'Adélaïde" in info["publisher"]["fr_FR"]
    assert "University of Adelaide" in info["publisher"]["en_US"]
    assert "Éditions Gallimard" not in info["publisher"]["fr_FR"]


def test_values_typed_without_wikidata_are_flagged_as_estimates(catalogue):
    editor.add_book(catalogue, _author(), _book(wikidata_id=""))
    editor.add_book(catalogue, _author(), _book(wikidata_id="", year="1010", pages={"fr_FR": "", "en_US": ""},
                                                title={"fr_FR": "Journal", "en_US": "Diary"}))

    genji, diary = next(entry for entry in catalogue["authors"] if entry.get("wikidata_id") == "Q999999")["books"]
    assert list(genji) == ["year", "genre", "title", "pages", "pages_estimated", "publisher", "publisher_estimated"]
    assert genji["pages_estimated"] is genji["publisher_estimated"] is True
    # Nothing to qualify without a page count
    assert diary["pages"] is None and "pages_estimated" not in diary and diary["publisher_estimated"] is True


def test_add_book_appends_to_an_existing_author_by_year(catalogue):
    author = _author(wikidata_id="Q535", name={"fr_FR": "Victor Hugo", "en_US": "Victor Hugo"},
                     nationality={"fr_FR": "ignoré", "en_US": "ignored"})
    book = _book(wikidata_id="Q1", title={"fr_FR": "Les Orientales", "en_US": "Les Orientales"}, year="1829")

    _, created = editor.add_book(catalogue, author, book)

    assert not created
    hugo = next(entry for entry in catalogue["authors"] if entry["name"] == "Victor Hugo")
    assert hugo["wikidata_id"] == "Q535"
    assert hugo["nationality"]["fr_FR"] == "français"
    years = [book["year"] for book in hugo["books"]]
    assert years == sorted(years) and 1829 in years


def test_add_book_rejects_duplicates_and_invalid_books(catalogue):
    editor.add_book(catalogue, _author(), _book())

    with pytest.raises(ValueError, match="déjà"):
        editor.add_book(catalogue, _author(), _book(wikidata_id="Q2"))
    with pytest.raises(ValueError, match="Année manquante"):
        editor.add_book(catalogue, _author(),
                        _book(wikidata_id="Q3", title={"fr_FR": "A", "en_US": "B"}, year="vers 1000"))
    with pytest.raises(ValueError, match=r"Titre \(anglais\) : champ obligatoire"):
        editor.add_book(catalogue, _author(), _book(wikidata_id="Q4", title={"fr_FR": "Seulement FR", "en_US": ""}))


def test_localized_names_are_kept_only_when_they_differ(catalogue):
    editor.add_book(catalogue, _author(wikidata_id="Q9333", name={"fr_FR": "Lao-Tseu", "en_US": "Laozi"}),
                    _book(title={"fr_FR": "Tao-tö-king", "en_US": "Tao Te Ching"}, year="-400"))

    laozi = next(entry for entry in catalogue["authors"] if entry.get("wikidata_id") == "Q9333")
    assert laozi["name"] == {"fr_FR": "Lao-Tseu", "en_US": "Laozi"}


def test_existing_author_is_matched_by_any_localized_name(catalogue):
    # The catalogue spells him "Homère" and already holds the Odyssey
    with pytest.raises(ValueError, match="déjà"):
        editor.add_book(catalogue, _author(wikidata_id="Q6691", name={"fr_FR": "Homer", "en_US": "Homère"}),
                        _book(wikidata_id="Q35160", title={"fr_FR": "L'Odyssée", "en_US": "The Odyssey"}))


def test_save_catalogue_keeps_the_bundled_layout(tmp_path):
    path = tmp_path / "literature.json"
    original = editor.CATALOGUE_PATH.read_text(encoding="utf-8")

    editor.save_catalogue(json.loads(original), path)

    assert path.read_text(encoding="utf-8") == original
    assert [p.name for p in tmp_path.iterdir()] == ["literature.json"]


def test_annotate_flags_known_works(catalogue):
    author = {"wikidata_id": "Q535", "name": {"fr_FR": "Victor Hugo", "en_US": "Victor Hugo"}}
    works = [
        {"wikidata_id": "Q180736", "title": {"fr_FR": "Les Misérables", "en_US": "Les Misérables"}},
        {"wikidata_id": "Q1", "title": {"fr_FR": "Inédit", "en_US": "Unpublished"}},
    ]

    existing = editor.annotate(catalogue, author, works)

    assert existing["books"] >= 1
    assert [work["in_catalogue"] for work in works] == [True, False]


def test_multilingual_labels_fill_missing_names_and_titles():
    author = editor.parse_author("Q535", [_cells(nameMul="Victor Hugo")])
    works = editor.parse_works([_cells(work=WORK, links="5", titleMul="Hernani",
                                       titleFr="Hernani ou l'Honneur castillan", inception="1829-01-01T00:00:00Z",
                                       date="1830-02-25T00:00:00Z", pages="940512")], [])

    assert author["name"] == {"fr_FR": "Victor Hugo", "en_US": "Victor Hugo"}
    assert works[0]["title"] == {"fr_FR": "Hernani ou l'Honneur castillan", "en_US": "Hernani"}
    assert works[0]["year"] == 1830
    assert works[0]["pages"] == {"fr_FR": None, "en_US": None}


def test_genre_errors_are_explained_in_french(catalogue):
    with pytest.raises(ValueError, match=r"Genres : au moins un genre"):
        editor.add_book(catalogue, _author(), _book(genre={"fr_FR": " , ", "en_US": ""}))


def test_known_genres_are_stored_by_id_from_either_language(catalogue):
    editor.add_book(catalogue, _author(), _book(genre={"fr_FR": "", "en_US": "crime fiction, Novel"}))

    entry = editor.find_author(catalogue, "Q999999", [])
    assert entry["books"][0]["genre"] == ["crime", "novel"]


def test_unknown_genres_need_a_translation(catalogue):
    before = copy.deepcopy(catalogue)

    with pytest.raises(ValueError, match="traduction en anglais"):
        editor.add_book(catalogue, _author(), _book(genre={"fr_FR": "roman, monogatari", "en_US": "novel"}))
    assert catalogue == before


def test_rejected_book_adds_no_genre(catalogue):
    before = copy.deepcopy(catalogue)

    with pytest.raises(ValueError, match="Année"):
        editor.add_book(catalogue, _author(), _book(year="", genre={"fr_FR": "monogatari", "en_US": "monogatari"}))
    assert catalogue == before


def test_genre_without_letters_is_refused(catalogue):
    with pytest.raises(ValueError, match="ne peut pas devenir un nouveau genre"):
        editor.add_book(catalogue, _author(), _book(genre={"fr_FR": "?", "en_US": "?"}))


def test_wikidata_genres_are_replaced_by_catalogue_labels(catalogue):
    author = {"wikidata_id": "Q999999", "name": {"fr_FR": "Murasaki Shikibu", "en_US": "Murasaki Shikibu"}}
    works = [{"title": {"fr_FR": "Inédit", "en_US": "Unpublished"},
              "genre": {"fr_FR": ["fiction gothique", "monogatari"], "en_US": ["gothic fiction", "monogatari"]}}]

    editor.annotate(catalogue, author, works)

    assert works[0]["genre"] == {"fr_FR": ["roman gothique", "monogatari"], "en_US": ["gothic novel", "monogatari"]}


def test_parse_influences_separates_people_from_works():
    rows = [
        _cells(influence="http://www.wikidata.org/entity/Q905", nameMul="Franz Kafka", descFr="écrivain", human="true"),
        _cells(influence="http://www.wikidata.org/entity/Q905", nameFr="Franz Kafka", human="true"),
        _cells(influence="http://www.wikidata.org/entity/Q3587963", nameFr="Élise ou la vraie vie", human="false"),
        _cells(influence="http://www.wikidata.org/entity/Q7197", nameEn="Simone de Beauvoir", human="true"),
    ]

    influences = editor.parse_influences(rows)

    assert [influence["name"] for influence in influences] == [
        "Élise ou la vraie vie", "Franz Kafka", "Simone de Beauvoir",
    ]
    assert [influence["person"] for influence in influences] == [False, True, True]
    assert influences[1]["description"] == "écrivain"


def test_annotate_flags_influences_already_in_the_catalogue(catalogue):
    author = {
        "wikidata_id": "Q134798", "name": {"fr_FR": "Haruki Murakami", "en_US": "Haruki Murakami"},
        "influences": [
            {"wikidata_id": "Q79904", "name": "J.D. Salinger", "person": True},
            {"wikidata_id": "Q1", "name": "Inconnu", "person": True},
            {"wikidata_id": "Q2", "name": "Victor Hugo", "person": False},
        ],
    }

    editor.annotate(catalogue, author, [])

    assert [influence["in_catalogue"] for influence in author["influences"]] == [True, False, False]


def test_author_names_match_regardless_of_spacing_and_punctuation(catalogue):
    entry = editor.find_author(catalogue, "Q79904", ["J. D. Salinger"])

    assert entry is not None and entry["name"] == "J.D. Salinger"
    assert editor.find_author(catalogue, None, ["h.p. LOVECRAFT"])["name"] == "H. P. Lovecraft"
    assert editor.find_author(catalogue, None, ["Emile Zola"])["name"] == "Émile Zola"


def test_homonyms_with_another_wikidata_id_are_different_authors(catalogue):
    # Lovecraft is Q169566 in the catalogue: an other Q-id with the same name is someone else
    assert editor.find_author(catalogue, "Q1", ["H. P. Lovecraft"]) is None
    assert editor.find_author(catalogue, "Q169566", ["H. P. Lovecraft"])["name"] == "H. P. Lovecraft"


def test_homonym_gets_its_own_entry(catalogue):
    before = len(catalogue["authors"])
    homonym = _author(wikidata_id="Q1", name={"fr_FR": "Émile Zola", "en_US": "Émile Zola"})

    _, created = editor.add_book(catalogue, homonym, _book())

    assert created and len(catalogue["authors"]) == before + 1


@pytest.mark.parametrize("title, key", [
    ("L'Iliade", "iliade"),
    ("l’Odyssée", "odyssee"),
    ("The Iliad", "iliad"),
    ("A Study in Scarlet", "studyinscarlet"),
    ("Les Misérables", "miserables"),
    ("Anna Karénine", "annakarenine"),
    ("Theogony", "theogony"),
    ("Lettres persanes", "lettrespersanes"),
    ("Antigone", "antigone"),
    ("Une", "une"),
])
def test_title_key_only_removes_whole_leading_articles(title, key):
    assert editor._title_key(title) == key


def test_titles_differing_by_an_article_are_duplicates(catalogue):
    homer = _author(wikidata_id="Q6691", name={"fr_FR": "Homère", "en_US": "Homer"})

    for title_fr, title_en in (("Iliade", "Iliad"), ("l’Odyssée", "Odyssey")):
        with pytest.raises(ValueError, match="déjà"):
            editor.add_book(catalogue, homer, _book(wikidata_id="Q9", title={"fr_FR": title_fr, "en_US": title_en}))


def test_french_nationality_and_genres_are_lower_cased(catalogue):
    message, _ = editor.add_book(catalogue, _author(nationality={"fr_FR": "Japonais", "en_US": "Japanese"}),
                                 _book(genre={"fr_FR": "Roman, roman, Journal intime", "en_US": "Novel, pillow book"}))

    entry = editor.find_author(catalogue, "Q999999", [])
    assert entry["nationality"]["fr_FR"] == "japonais"
    assert entry["books"][0]["genre"] == ["novel", "pillow-book"]
    assert catalogue["genres"]["pillow-book"] == {"fr_FR": "journal intime", "en_US": "pillow book"}
    assert "Nouveau(x) genre(s) : journal intime / pillow book" in message
    assert list(catalogue["genres"]) == sorted(catalogue["genres"])


def test_popularity_sent_by_the_page_is_kept_for_wikidata_works(catalogue):
    editor.add_book(catalogue, _author(), _book(popularity=42))
    editor.add_book(catalogue, _author(), _book(wikidata_id="", year="1010", popularity=42,
                                                title={"fr_FR": "Journal", "en_US": "Diary"}))
    editor.add_book(catalogue, _author(), _book(wikidata_id="Q5", year="1011", popularity="42",
                                                title={"fr_FR": "Poèmes", "en_US": "Poems"}))

    entry = next(entry for entry in catalogue["authors"] if entry.get("wikidata_id") == "Q999999")
    genji, diary, poems = entry["books"]
    assert genji["popularity"] == 42 and list(genji)[-2:] == ["popularity", "wikidata_id"]
    # Without a Wikidata work, or with a malformed value, nothing is kept
    assert "popularity" not in diary and "popularity" not in poems
