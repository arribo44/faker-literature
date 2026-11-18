import pytest

from faker_literature.vocabulary import GenreVocabulary, PublisherVocabulary, slugify


def _vocabulary():
    return GenreVocabulary({
        "crime": {"fr_FR": "polar", "en_US": "crime",
                  "aliases": {"fr_FR": ["police"], "en_US": ["crime fiction"]}},
        "fantasy": {"fr_FR": "fantasy", "en_US": "fantasy"},
        "novel": {"fr_FR": "roman", "en_US": "novel"},
    })


@pytest.mark.parametrize("label, locale, expected", [
    ("polar", "fr_FR", "crime"),
    ("POLICE", "fr_FR", "crime"),
    ("Crime-Fiction", "en_US", "crime"),
    ("fantasy", "en_US", "fantasy"),
    # A label of the other language is found too
    ("novel", "fr_FR", "novel"),
    ("roman", "en_US", "novel"),
    ("inconnu", "fr_FR", None),
    ("", "fr_FR", None),
])
def test_match_uses_labels_and_aliases(label, locale, expected):
    assert _vocabulary().match(label, locale) == expected


def test_resolve_returns_the_labels_of_each_locale():
    assert _vocabulary().resolve(["novel", "crime"]) == {"fr_FR": ["roman", "polar"], "en_US": ["novel", "crime"]}
    with pytest.raises(ValueError, match="unknown genre ids"):
        _vocabulary().resolve(["nope"])


def test_add_creates_a_unique_id():
    vocabulary = _vocabulary()
    vocabulary.genres["noir-novel"] = {"fr_FR": "roman dur", "en_US": "hardboiled"}

    assert vocabulary.add("roman noir", "noir novel") == "noir-novel-2"
    assert vocabulary.match("roman noir", "fr_FR") == "noir-novel-2"


def test_add_refuses_a_label_of_another_genre():
    with pytest.raises(ValueError, match="already used by novel"):
        _vocabulary().add("nouvelle", "Novel!")


@pytest.mark.parametrize("genres, message", [
    ({"crime": {"fr_FR": "polar", "en_US": "crime"},
      "noir": {"fr_FR": "Polar", "en_US": "noir"}}, "already used by crime"),
    ({"crime": {"fr_FR": "polar", "en_US": "crime", "aliases": {"en_US": ["noir"]}},
      "noir": {"fr_FR": "noir", "en_US": "noir"}}, "already used by crime"),
    ({"Crime": {"fr_FR": "polar", "en_US": "crime"}}, "genre id"),
    ({"crime": {"fr_FR": "polar", "en_US": " "}}, "non-empty"),
])
def test_ambiguous_or_malformed_vocabularies_are_rejected(genres, message):
    with pytest.raises(ValueError, match=message):
        GenreVocabulary(genres)


def test_slugify():
    assert slugify("children's literature") == "children-s-literature"
    assert slugify("Épopée") == "epopee"


def test_slugify_transliterates_letters_without_accent():
    assert slugify("Yapı Kredi Yayınları") == "yapi-kredi-yayinlari"
    assert slugify("Gyldendal Norsk Forlag ØÆ") == "gyldendal-norsk-forlag-oae"


def _publishers():
    return PublisherVocabulary({
        "gallimard": {"name": "Gallimard", "aliases": ["Éditions Gallimard"], "country": "FR"},
        "the-russian-messenger": {"name": {"fr_FR": "Le Messager russe", "en_US": "The Russian Messenger"}},
    })


@pytest.mark.parametrize("label, expected", [
    ("Gallimard", "gallimard"),
    ("éditions gallimard", "gallimard"),
    ("Le Messager russe", "the-russian-messenger"),
    ("The Russian Messenger", "the-russian-messenger"),
    ("Galimard", None),
    ("", None),
    (None, None),
])
def test_publisher_match_uses_names_and_aliases(label, expected):
    assert _publishers().match(label) == expected


def test_publisher_names_are_localized_when_needed():
    vocabulary = _publishers()
    assert vocabulary.resolve({"fr_FR": "the-russian-messenger", "en_US": "gallimard"}) == {
        "fr_FR": "Le Messager russe", "en_US": "Gallimard"}
    assert vocabulary.resolve({"fr_FR": None, "en_US": "the-russian-messenger"}) == {
        "fr_FR": None, "en_US": "The Russian Messenger"}
    assert vocabulary.resolve(None) is None
    assert vocabulary.names("fr_FR") == ["Gallimard", "Le Messager russe"]
    assert vocabulary.canonical("Éditions Gallimard", "en_US") == "Gallimard"
    assert vocabulary.canonical("Verdier", "fr_FR") == "Verdier"
    with pytest.raises(ValueError, match="unknown publisher"):
        vocabulary.resolve({"fr_FR": "nope", "en_US": None})


def test_publisher_add_and_ensure():
    vocabulary = _publishers()
    assert vocabulary.ensure("ÉDITIONS GALLIMARD") == ("gallimard", False)
    assert vocabulary.ensure("Verdier") == ("verdier", True)
    assert vocabulary.publishers["verdier"] == {"name": "Verdier"}
    assert vocabulary.match("verdier") == "verdier"
    # Another spelling of a known name is refused, an id already taken gets a suffix
    with pytest.raises(ValueError, match="already used by verdier"):
        vocabulary.add("Verdier!")
    vocabulary.publishers["verdier-house"] = {"name": "Maison Verdier"}
    assert vocabulary.add("Verdier House", country="FR", wikidata_id="Q1") == "verdier-house-2"
    assert vocabulary.publishers["verdier-house-2"] == {"name": "Verdier House", "country": "FR", "wikidata_id": "Q1"}


@pytest.mark.parametrize("publishers, message", [
    ({"Bad Id": {"name": "X"}}, "lower-case"),
    ({"x": {"name": "X", "city": "Paris"}}, "unknown fields"),
    ({"x": {"name": " X"}}, "surrounding spaces"),
    ({"x": {"name": ""}}, "non-empty"),
    ({"x": {}}, "non-empty"),
    ({"x": {"name": {"fr_FR": "X"}}}, "exactly the locales"),
    ({"x": {"name": "X", "aliases": "Y"}}, "aliases must be a list"),
    ({"x": {"name": "X", "country": "France"}}, "ISO 3166"),
    ({"x": {"name": "X", "wikidata_id": "P123"}}, "wikidata_id"),
    ({"x": {"name": "X"}, "y": {"name": "Z", "aliases": ["x"]}}, "already used by x"),
])
def test_invalid_publishers_are_refused(publishers, message):
    with pytest.raises(ValueError, match=message):
        PublisherVocabulary(publishers)
