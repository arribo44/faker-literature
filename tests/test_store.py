import json
import multiprocessing
import os
import stat
import sys

import pytest
from faker import Faker

from faker_literature import LiteratureProvider
from faker_literature._storage import FileLock
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
    ({"wikidata_id": "Q12 OR 1=1"}, "wikidata_id"),
    ({"wikidata_id": 42}, "wikidata_id"),
    ({"isbn": {"nested": "value"}}, "extra fields hold"),
    ({"isbn": "x" * 1000}, "longer than"),
    ({"bad name": 1}, "extra field names"),
    ({"score": float("nan")}, "finite"),
    ({"pages_estimated": "yes"}, "pages_estimated"),
    ({"pages_estimated": True}, "no page count"),
    ({f"field{i}": i for i in range(21)}, "extra fields"),
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


def test_imported_books_added_later_to_the_bundled_catalogue_are_dropped(tmp_path, bundled_copy):
    original = bundled_copy.read_text(encoding="utf-8")
    data = json.loads(original)
    hugo = next(author for author in data["authors"] if author["name"] == "Victor Hugo")
    miserables = next(book for book in hugo["books"] if book["title"]["fr_FR"] == "Les Misérables")
    hugo["books"].remove(miserables)
    bundled_copy.write_text(json.dumps(data), encoding="utf-8")

    db_path = tmp_path / "db.json"
    store = BookStore(db_path, builtin_path=bundled_copy)
    # Imported from Wikidata before the bundled catalogue had it
    store.replace_source("wikidata", [_imported_book(), _imported_book(
        writer="Victor Hugo", nationality={"fr_FR": "français", "en_US": "French"},
        title={"fr_FR": "Les Miserables", "en_US": "Les Misérables"}, year=miserables["year"] + 1,
    )])
    store.close()

    bundled_copy.write_text(original, encoding="utf-8")
    reopened = BookStore(db_path, builtin_path=bundled_copy)

    assert reopened.sources()["wikidata"] == 1
    assert reopened.removed_duplicates == 1


def test_scalar_extra_fields_are_accepted():
    validate_book(dict(_imported_book(isbn="978-2-07-036024-5", copies=3, rating=4.5, lent=False, note=None),
                       wikidata_id="Q35160", source="test"))


def test_damaged_database_is_reported(tmp_path):
    db_path = tmp_path / "db.json"
    db_path.write_text('{"books": {"1": {"title": ', encoding="utf-8")

    with pytest.raises(ValueError, match="corrupted database"):
        BookStore(db_path)


def test_records_edited_by_hand_are_validated_on_opening(tmp_path):
    db_path = tmp_path / "db.json"
    BookStore(db_path).replace_source("wikidata", [_imported_book()])
    data = json.loads(db_path.read_text(encoding="utf-8"))
    imported = next(record for record in data["books"].values() if record["source"] == "wikidata")
    imported["year"] = "an 1000"
    db_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match=r"invalid record #\d+ \(year"):
        BookStore(db_path)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
def test_database_permissions_are_kept(tmp_path):
    db_path = tmp_path / "db.json"
    store = BookStore(db_path)
    os.chmod(db_path, 0o640)

    store.replace_source("wikidata", [_imported_book()])

    assert stat.S_IMODE(db_path.stat().st_mode) == 0o640
    assert not [path.name for path in tmp_path.iterdir() if path.suffix == ".tmp"]


def _replace_repeatedly(db_path, source, rounds):
    store = BookStore(db_path)
    for round_ in range(rounds):
        store.replace_source(source, [_imported_book(year=-700 - round_)])


def test_concurrent_processes_do_not_lose_updates(tmp_path):
    db_path = tmp_path / "db.json"
    BookStore(db_path).close()
    context = multiprocessing.get_context("spawn")
    workers = [context.Process(target=_replace_repeatedly, args=(db_path, source, 8)) for source in ("a", "b", "c")]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(60)

    assert [worker.exitcode for worker in workers] == [0, 0, 0]
    sources = BookStore(db_path).sources()
    assert (sources["a"], sources["b"], sources["c"]) == (1, 1, 1)


def test_file_lock_is_reentrant_and_exclusive(tmp_path):
    lock = FileLock(tmp_path / "db.json.lock")
    with lock, lock:
        context = multiprocessing.get_context("spawn")
        worker = context.Process(target=_hold, args=(tmp_path / "db.json.lock",))
        worker.start()
        worker.join(0.5)
        # Still waiting for the lock held here
        assert worker.is_alive()
    worker.join(10)
    assert worker.exitcode == 0


def _hold(path):
    with FileLock(path):
        pass
