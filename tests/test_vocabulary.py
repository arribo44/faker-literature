import pytest

from faker_literature.vocabulary import GenreVocabulary, slugify


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
    ({"crime": {"fr_FR": "polar", "en_US": "crime"}, "noir": {"fr_FR": "Polar", "en_US": "noir"}}, "already used by crime"),
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
