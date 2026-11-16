"""Filters, multi-locale registration and cached pools of the provider."""

from collections import Counter

import pytest
from faker import Faker

from faker_literature import LiteratureProvider


@pytest.fixture
def fake_en():
    fake = Faker("en_US")
    fake.add_provider(LiteratureProvider)
    fake.seed_instance(4)
    return fake


@pytest.fixture
def co_written(tmp_path):
    """A persistent catalogue holding one book written by two authors."""
    store = LiteratureProvider.use_database(tmp_path / "db.json")
    store.replace_source("test", [{
        "writer": "Ann Alpha, Bob Beta",
        "nationality": {"fr_FR": "zélandais", "en_US": "Zealander"},
        "title": {"fr_FR": "Écrit à deux", "en_US": "Written Together"},
        "genre": {"fr_FR": ["roman"], "en_US": ["novel"]},
        "year": 2001,
    }])
    yield store
    LiteratureProvider.use_database(None)


# F6: consistent filters

def test_nationality_filter_ignores_case(fake_en):
    provider = LiteratureProvider(fake_en)
    british = {book["writer"] for book in provider.books if book["nationality"] == "British"}

    assert fake_en.writer(nationality="BRITISH") in british
    assert fake_en.writer(nationality="british", genre="HORROR") in british


def test_any_nationality_draws_writers_of_every_nationality(fake_en):
    provider = LiteratureProvider(fake_en)
    nationality_of = {book["writer"]: book["nationality"] for book in provider.books}

    drawn = {nationality_of[fake_en.writer(nationality=LiteratureProvider.ANY_NATIONALITY)] for _ in range(300)}

    assert len(drawn) > 5
    assert fake_en.writer(nationality="*", genre="horror") in nationality_of


def test_books_by_author_ignores_case_accents_and_punctuation():
    fake = Faker("fr_FR")
    fake.add_provider(LiteratureProvider)

    zola = fake.books_by_author("Émile Zola")
    assert zola and fake.books_by_author("emile ZOLA") == zola
    assert fake.books_by_author("j d salinger") == fake.books_by_author("J.D. Salinger") != []


def test_co_authors_are_found_and_drawn_separately(co_written):
    fake = Faker("en_US")
    fake.add_provider(LiteratureProvider)

    assert [book["title"] for book in fake.books_by_author("bob beta")] == ["Written Together"]
    assert {"Ann Alpha", "Bob Beta"} <= set(fake.all_authors())
    assert "Ann Alpha, Bob Beta" not in fake.all_authors()
    assert {fake.writer(nationality="Zealander") for _ in range(50)} == {"Ann Alpha", "Bob Beta"}


def test_nationality_counts_each_author_once(fake_en):
    provider = LiteratureProvider(fake_en)
    by_author = {book["writer"]: book["nationality"] for book in provider.books}
    expected = Counter(by_author.values())["American"] / len(by_author)

    draws = Counter(fake_en.nationality() for _ in range(4000))

    assert abs(draws["American"] / 4000 - expected) < 0.04


# F7: several locales

def test_register_adds_the_provider_to_every_locale():
    fake = Faker(["fr_FR", "en_US"])
    LiteratureProvider.register(fake)

    fr_titles = {book["title"] for book in LiteratureProvider(fake["fr_FR"]).books}
    en_titles = {book["title"] for book in LiteratureProvider(fake["en_US"]).books}
    assert fake["fr_FR"].book()["title"] in fr_titles
    assert fake["en_US"].title() in en_titles
    assert fake.book()["title"] in fr_titles | en_titles


def test_register_works_with_a_single_locale():
    fake = Faker("fr_FR")
    LiteratureProvider.register(fake)

    assert fake.writer() in LiteratureProvider(fake).all_authors()


def test_unsupported_locale_is_refused_unless_a_fallback_is_given():
    fake = Faker(["de_DE", "fr_FR"])
    with pytest.raises(ValueError, match="fallback_locale"):
        LiteratureProvider.register(fake)
    # Nothing was added, not even to the supported locale
    assert not hasattr(fake["fr_FR"], "book")

    LiteratureProvider.register(fake, fallback_locale="en_US")
    en_titles = {book["title"] for book in LiteratureProvider(Faker("en_US")).books}
    assert fake["de_DE"].title() in en_titles


# F8: cached pools

def test_pools_are_refreshed_when_the_catalogue_changes(tmp_path):
    store = LiteratureProvider.use_database(tmp_path / "db.json")
    try:
        fake = Faker("en_US")
        fake.add_provider(LiteratureProvider)
        before = fake.all_authors()
        assert "Zed Newcomer" not in before

        store.replace_source("test", [{
            "writer": "Zed Newcomer", "nationality": {"fr_FR": "américain", "en_US": "American"},
            "title": {"fr_FR": "Nouveau", "en_US": "New"}, "genre": {"fr_FR": ["roman"], "en_US": ["novel"]},
            "year": 2020,
        }])

        assert "Zed Newcomer" in fake.all_authors()
        assert "New" in {fake.title(genre="NOVEL") for _ in range(2000)}
    finally:
        LiteratureProvider.use_database(None)


def test_returned_lists_do_not_expose_the_cache(fake_en):
    fake_en.all_genres().append("CORROMPU")
    fake_en.all_authors().clear()

    assert "CORROMPU" not in fake_en.all_genres()
    assert fake_en.all_authors()
