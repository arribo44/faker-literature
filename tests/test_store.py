import json

import pytest
from faker import Faker

from faker_literature import LiteratureProvider
from faker_literature.store import BUILTIN_DATA, BookStore, validate_book


@pytest.fixture
def bundled_copy(tmp_path):
    path = tmp_path / "literature.json"
    path.write_bytes(BUILTIN_DATA.read_bytes())
    return path


@pytest.fixture
def reset_store():
    yield
    LiteratureProvider.use_database(None)


def _imported_book(**overrides):
    book = {
        "writer": {"fr_FR": "Homère", "en_US": "Homer"},
        "nationality": {"fr_FR": "grec", "en_US": "Greek"},
        "title": {"fr_FR": "L'Odyssée", "en_US": "The Odyssey"},
        "genre": {"fr_FR": ["épopée"], "en_US": ["epic"]},
        "year": -700,
        "pages": None,
        "publisher": None,
    }
    book.update(overrides)
    return book


def test_default_store_stays_in_memory():
    LiteratureProvider(Faker("fr_FR"))

    assert LiteratureProvider._get_store().path is None


def test_builtin_books_are_resynced_when_the_bundled_json_changes(tmp_path, bundled_copy):
    db_path = tmp_path / "db.json"
    store = BookStore(db_path, builtin_path=bundled_copy)
    initial = store.sources()["builtin"]
    store.replace_source("wikidata", [_imported_book()])
    store.close()

    data = json.loads(bundled_copy.read_text(encoding="utf-8"))
    data["authors"][0]["books"].pop()
    bundled_copy.write_text(json.dumps(data), encoding="utf-8")

    reopened = BookStore(db_path, builtin_path=bundled_copy)
    assert reopened.sources() == {"builtin": initial - 1, "wikidata": 1}


def test_replace_source_is_idempotent():
    store = BookStore()

    store.replace_source("wikidata", [_imported_book()])
    store.replace_source("wikidata", [_imported_book(), _imported_book(year=-750)])

    assert store.sources()["wikidata"] == 2


def test_invalid_record_leaves_the_store_unchanged():
    store = BookStore()
    before = store.sources()

    with pytest.raises(ValueError, match="year"):
        store.replace_source("wikidata", [_imported_book(), _imported_book(year="ancient")])

    assert store.sources() == before


@pytest.mark.parametrize("overrides, message", [
    ({"title": {"fr_FR": "Seulement en français"}}, "missing locales"),
    ({"genre": {"fr_FR": [], "en_US": []}}, "genres"),
    ({"pages": {"fr_FR": -3, "en_US": 10}}, "page count"),
    ({"publisher": {"fr_FR": "x" * 1000, "en_US": "x"}}, "longer than"),
    ({"year": True}, "year"),
])
def test_validate_book_rejects_malformed_records(overrides, message):
    with pytest.raises(ValueError, match=message):
        validate_book(dict(_imported_book(**overrides), source="test"))


def test_book_cannot_modify_the_shared_catalogue():
    fake = Faker("fr_FR")
    fake.add_provider(LiteratureProvider)

    for _ in range(20):
        book = fake.book()
        book["genre"].append("CORROMPU")

    assert all("CORROMPU" not in book["genre"] for book in LiteratureProvider(fake).books)


def test_regional_locales_fall_back_on_their_language():
    assert LiteratureProvider(Faker("fr_CA")).provider_locale == "fr_FR"
    assert LiteratureProvider(Faker("en_GB")).provider_locale == "en_US"


def test_imported_books_are_generated_with_localized_names(tmp_path, reset_store):
    store = LiteratureProvider.use_database(tmp_path / "db.json")
    store.replace_source("wikidata", [_imported_book()])

    fake_en = Faker("en_US")
    fake_en.add_provider(LiteratureProvider)
    fake_fr = Faker("fr_FR")
    fake_fr.add_provider(LiteratureProvider)

    assert "The Odyssey" in [book["title"] for book in fake_en.books_by_author("Homer")]
    assert "L'Odyssée" in [book["title"] for book in fake_fr.books_by_author("Homère")]
    assert "Greek" in fake_en.all_nationalities()
    assert fake_en.pages() is not None
