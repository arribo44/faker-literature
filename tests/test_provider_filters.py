"""Filters, multi-locale registration and cached pools of the provider."""

from collections import Counter

import pytest
from faker import Faker

from faker_literature import BookFilter, LiteratureProvider


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
        # Build the cached pool of novels before the catalogue changes
        assert fake.books_sample(1, genre="novel")

        store.replace_source("test", [{
            "writer": "Zed Newcomer", "nationality": {"fr_FR": "américain", "en_US": "American"},
            "title": {"fr_FR": "Nouveau", "en_US": "New"}, "genre": {"fr_FR": ["roman"], "en_US": ["novel"]},
            "year": 2020,
        }])

        assert "Zed Newcomer" in fake.all_authors()
        # Every novel, drawn without replacement from the refreshed pool
        all_novels = fake.books_sample(len(fake.books_by_genre("novel")), genre="NOVEL")
        assert "New" in {book["title"] for book in all_novels}
        assert fake.title(genre="novel", author="zed newcomer") == "New"
    finally:
        LiteratureProvider.use_database(None)


def test_returned_lists_do_not_expose_the_cache(fake_en):
    fake_en.all_genres().append("CORROMPU")
    fake_en.all_authors().clear()

    assert "CORROMPU" not in fake_en.all_genres()
    assert fake_en.all_authors()


# Filters shared by every drawing method

def test_filters_combine_on_every_drawing_method(fake_en):
    provider = LiteratureProvider(fake_en)
    french_19th = [book for book in provider.books if book["nationality"] == "French" and 1801 <= book["year"] <= 1900]

    for _ in range(30):
        book = fake_en.book(nationality="french", century=19)
        assert book in french_19th
    assert fake_en.title(nationality="French", century=19) in {book["title"] for book in french_19th}
    assert fake_en.publisher(nationality="French", century=19) in {book["publisher"] for book in french_19th}
    assert fake_en.publication_year(nationality="French", century=19) in range(1801, 1901)
    assert fake_en.genre(nationality="French", century=19) in {g for book in french_19th for g in book["genre"]}
    assert fake_en.writer(nationality="French", century=19) in {book["writer"] for book in french_19th}
    assert fake_en.pages(after=1990, before=1999) in {book["pages"] for book in provider.books
                                                      if 1990 <= book["year"] <= 1999}


def test_author_filter_and_year_bounds(fake_en):
    assert {fake_en.title(author="victor HUGO") for _ in range(50)} <= {
        book["title"] for book in fake_en.books_by_author("Victor Hugo")}
    assert fake_en.book(before=-500)["year"] <= -500
    assert fake_en.book(after=2000, genre="science fiction")["year"] >= 2000


@pytest.mark.parametrize("century, first, last", [(19, 1801, 1900), (1, 1, 100), (-1, -100, -1), (-5, -500, -401)])
def test_centuries(century, first, last):
    book_filter = BookFilter(century=century)
    assert (book_filter.after, book_filter.before) == (first, last)


def test_impossible_filters_raise(fake_en):
    with pytest.raises(ValueError, match="No book found for nationality='Zealander', after=2000"):
        fake_en.book(nationality="Zealander", after=2000)
    with pytest.raises(ValueError, match="century 0"):
        fake_en.book(century=0)


# Popularity

@pytest.fixture
def ranked(tmp_path):
    """Two books of one nationality: one famous, one obscure."""
    store = LiteratureProvider.use_database(tmp_path / "db.json")
    base = {"nationality": {"fr_FR": "zélandais", "en_US": "Zealander"},
            "genre": {"fr_FR": ["roman"], "en_US": ["novel"]}, "year": 2001}
    store.replace_source("test", [
        dict(base, writer="Famous Author", title={"fr_FR": "Célèbre", "en_US": "Famous"}, popularity=900),
        dict(base, writer="Obscure Author", title={"fr_FR": "Obscur", "en_US": "Obscure"}, popularity=1),
    ])
    yield
    LiteratureProvider.use_database(None)


def test_popular_books_are_drawn_more_often(ranked, fake_en):
    plain = Counter(fake_en.title(nationality="Zealander") for _ in range(1000))
    popular = Counter(fake_en.title(nationality="Zealander", popular=True) for _ in range(1000))

    assert 400 < plain["Famous"] < 600
    assert popular["Famous"] > 980
    assert Counter(fake_en.writer(nationality="Zealander", popular=True) for _ in range(200))["Famous Author"] > 190


def test_popularity_stays_internal(ranked, fake_en):
    assert "popularity" not in fake_en.book(nationality="Zealander")
    assert "popularity" not in fake_en.books_sample(1, nationality="Zealander")[0]
    assert any("popularity" in book for book in LiteratureProvider(fake_en).books_flat)


def test_books_without_popularity_get_the_median():
    fake = Faker("en_US")
    fake.add_provider(LiteratureProvider)
    provider = LiteratureProvider(fake)
    books = [{"popularity": 10}, {"popularity": 30}, {"popularity": None}, {}]

    median = provider._weights([{}])[0]
    assert provider._weights(books) == [100, 900, median, median]


# Sampling without replacement

def test_books_sample_draws_distinct_books(fake_en):
    sample = fake_en.books_sample(50, nationality="*")
    assert len({(book["writer"], book["title"]) for book in sample}) == 50

    french = fake_en.books_sample(5, nationality="French", century=19, popular=True)
    assert len({book["title"] for book in french}) == 5 and all(book["nationality"] == "French" for book in french)
    assert fake_en.books_sample(0) == []


def test_books_sample_is_reproducible_and_bounded(fake_en, ranked):
    fake_en.seed_instance(9)
    first = fake_en.books_sample(2, nationality="Zealander")
    fake_en.seed_instance(9)
    assert fake_en.books_sample(2, nationality="Zealander") == first
    with pytest.raises(ValueError, match="Cannot draw 3 books: 2 match"):
        fake_en.books_sample(3, nationality="Zealander")


# Writer profiles

def test_writer_profile_by_name(fake_en):
    hugo = fake_en.writer_profile("victor HUGO")

    assert (hugo["name"], hugo["nationality"], hugo["born"], hugo["died"]) == ("Victor Hugo", "French", 1802, 1885)
    years = [book["year"] for book in hugo["books"]]
    assert years == sorted(years) and {"title": "Les Misérables", "year": 1862} in hugo["books"]
    assert 0 < len(hugo["genres"]) <= 5
    assert all(hugo["born"] + 12 <= year for year in years)


def test_writer_profile_drawn_with_filters_and_living_writers(fake_en, co_written):
    profile = fake_en.writer_profile(nationality="Zealander")
    assert profile["name"] in ("Ann Alpha", "Bob Beta")
    assert profile["born"] is None and profile["died"] is None
    assert [book["title"] for book in profile["books"]] == ["Written Together"]
    with pytest.raises(ValueError, match="No writer named"):
        fake_en.writer_profile("Nobody At All")
    with pytest.raises(TypeError):
        fake_en.writer_profile("Victor Hugo", genre="novel")


def test_life_years_stay_out_of_book(fake_en):
    assert not {"writer_born", "writer_died", "popularity"} & set(fake_en.book())
    raw = next(book for book in LiteratureProvider(fake_en).books_flat if book["title"]["en_US"] == "Les Misérables")
    assert (raw["writer_born"], raw["writer_died"]) == (1802, 1885)


# Literary awards

def test_award_filter_and_queries(fake_en):
    goncourt = fake_en.books_by_award("GONCOURT")
    assert goncourt and all(any("goncourt" in award.lower() for award in book_awards(fake_en, book))
                            for book in goncourt)
    assert "awards" not in goncourt[0]
    assert fake_en.book(award="Hugo Award")["title"] in {book["title"] for book in fake_en.books_by_award("hugo")}
    awarded = {book["title"] for book in fake_en.books_by_award("*")}
    assert {fake_en.title(award="*") for _ in range(50)} <= awarded
    assert len(awarded) < len(LiteratureProvider(fake_en).books)
    with pytest.raises(ValueError, match="award='nope'"):
        fake_en.book(award="nope")


def book_awards(fake, book):
    raw = next(record for record in LiteratureProvider(fake).books_flat if record["title"]["en_US"] == book["title"])
    return raw["awards"]["en_US"]


def test_award_draws_and_lists(fake_en):
    awards = fake_en.all_awards()
    assert awards == sorted(awards, key=str.casefold) and "Prix Goncourt" in awards
    assert {fake_en.award() for _ in range(50)} <= set(awards)
    assert fake_en.award(nationality="French", century=20) in awards
    le_guin = fake_en.writer_profile("Ursula K. Le Guin")
    assert "Hugo Award for Best Novel" in le_guin["awards"]


# Series

def test_series_filter_and_draws(fake_en):
    harry_potter = {book["title"] for book in fake_en.books_in_series("harry potter")}
    assert fake_en.book(series="HARRY")["title"] in harry_potter
    assert "series" not in fake_en.book(series="*")
    assert fake_en.writer(series="harry potter", nationality="*") == "J.K. Rowling"
    assert {fake_en.title(series="rougon") for _ in range(20)} <= {
        book["title"] for book in fake_en.books_in_series("Les Rougon-Macquart")}
    with pytest.raises(ValueError, match="series='no such series'"):
        fake_en.book(series="no such series")
    series = fake_en.all_series()
    assert series == sorted(series, key=str.casefold) and "Discworld" in series
    assert {fake_en.series() for _ in range(50)} <= set(series)
    assert fake_en.series(nationality="French", century=19) in series
    assert "Les Rougon-Macquart" in fake_en.writer_profile("Émile Zola")["series"]


def test_books_in_series_follow_the_reading_order():
    fake = Faker("fr_FR")
    fake.add_provider(LiteratureProvider)

    rougon = fake.books_in_series("les rougon macquart")

    positions = [book["position"] for book in rougon]
    assert positions[:2] == [1, 7] and positions == sorted(positions)
    assert rougon[0]["title"] == "La Fortune des Rougon" and rougon[0]["writer"] == "Émile Zola"
    assert fake.books_in_series("Harry Potter")[-1]["title"] == "Harry Potter et les Reliques de la Mort"


def test_books_in_series_rejects_unknown_and_ambiguous_names(fake_en):
    with pytest.raises(ValueError, match="No series named"):
        fake_en.books_in_series("no such series")
    with pytest.raises(ValueError, match="names several series"):
        fake_en.books_in_series("trilogy")
