import pytest
from faker import Faker

from faker_literature import LiteratureProvider


@pytest.mark.parametrize("locale", ["fr_FR", "en_US"])
def test_scalar_methods_use_the_selected_catalogue(locale):
    fake = Faker(locale)
    fake.add_provider(LiteratureProvider)
    provider = LiteratureProvider(fake)

    assert fake.writer() in [book["writer"] for book in provider.books]
    assert fake.author() in [book["writer"] for book in provider.books]
    assert fake.title() in [book["title"] for book in provider.books]
    assert fake.genre() in [
        genre
        for book in provider.books
        for genre in (book["genre"] if isinstance(book["genre"], list) else [book["genre"]])
    ]
    assert fake.publication_year() in [book["year"] for book in provider.books]
    assert fake.pages() in [book["pages"] for book in provider.books]
    assert fake.publisher() in [book["publisher"] for book in provider.books]


def test_catalogues_share_the_same_works_across_locales():
    fr_books = LiteratureProvider(Faker("fr_FR")).books
    en_books = LiteratureProvider(Faker("en_US")).books

    # Author names may be translated (Homère / Homer): compare the works themselves
    assert len(fr_books) == len(en_books)
    assert sorted(book["year"] for book in fr_books) == sorted(book["year"] for book in en_books)
    assert len({book["writer"] for book in fr_books}) == len({book["writer"] for book in en_books})


def test_book_genre_can_be_a_list():
    fake = Faker("fr_FR")
    fake.add_provider(LiteratureProvider)

    book = fake.book()

    assert isinstance(book["genre"], list)
    assert book["genre"]


def test_book_is_coherent_and_is_not_a_shared_record():
    fake = Faker("fr_FR")
    fake.add_provider(LiteratureProvider)

    book = fake.book()

    assert set(book) == {"writer", "nationality", "title", "genre", "year", "pages", "publisher"}
    assert book in LiteratureProvider(fake).books
    book["title"] = "changed"
    assert fake.book()["title"] != "changed"


def test_literary_work_alias_returns_a_book():
    fake = Faker("en_US")
    fake.add_provider(LiteratureProvider)

    assert set(fake.literary_work()) == {"writer", "nationality", "title", "genre", "year", "pages", "publisher"}


def test_science_fiction_authors_are_present():
    authors = {
        "Isaac Asimov",
        "Philip K. Dick",
        "William Gibson",
        "Arthur C. Clarke",
        "Ray Bradbury",
        "Ursula K. Le Guin",
        "George Orwell",
        "Aldous Huxley",
        "Kurt Vonnegut",
        "Octavia E. Butler",
        "Dan Simmons",
        "Neal Stephenson",
        "Margaret Atwood",
        "Joanna Russ",
        "Connie Willis",
        "Vonda N. McIntyre",
        "C.J. Cherryh",
        "Jules Verne",
        "Jean-Claude Dunyach",
        "Robert Merle",
        "Pierre Boulle",
        "Alain Damasio",
        "Michel Houellebecq",
        "J.G. Ballard",
        "Milan Kundera",
        "Italo Calvino",
        "Primo Levi",
        "Niccolò Machiavelli",
        "Dante Alighieri",
        "Charles Baudelaire",
        "Honoré de Balzac",
        "Pablo Neruda",
        "Jorge Luis Borges",
        "Stephen King",
        "H. P. Lovecraft",
        "J. R. R. Tolkien",
        "M. R. Carey",
        "Clive Barker",
        "Anne Rice",
        "Neil Gaiman",
        "J.D. Salinger",
        "Mark Twain",
        "Herman Melville",
        "Edgar Allan Poe",
        "William Faulkner",
        "Annie Ernaux",
        "David Foenkinos",
        "Leïla Slimani",
        "Claude Lévi-Strauss",
        "Philippe Descola",
        "Delphine de Vigan",
        "Julie Otsuka",
        "Douglas Kennedy",
        "J.K. Rowling",
    }
    writers = {book["writer"] for book in LiteratureProvider(Faker("fr_FR")).books}

    assert authors.issubset(writers)


def test_unsupported_locale_is_rejected():
    with pytest.raises(ValueError, match="Unsupported locale"):
        Faker("de_DE").add_provider(LiteratureProvider)


@pytest.mark.parametrize("locale", ["fr_FR", "en_US"])
def test_nationality_is_localized_and_consistent(locale):
    fake = Faker(locale)
    fake.add_provider(LiteratureProvider)
    provider = LiteratureProvider(fake)

    assert fake.nationality() in provider.all_nationalities()
    assert set(fake.book()) >= {"nationality", "writer"}
    for book in provider.books:
        assert book["nationality"] in provider.all_nationalities()

    other = "en_US" if locale == "fr_FR" else "fr_FR"
    other_provider = LiteratureProvider(Faker(other))
    assert provider.all_nationalities() != other_provider.all_nationalities()
    # Same authors in both locales, even when their names are translated (Aristote / Aristotle)
    assert len({b["writer"] for b in provider.books}) == len({b["writer"] for b in other_provider.books})


def test_writer_defaults_to_locale_nationality():
    fake_fr = Faker("fr_FR")
    fake_fr.add_provider(LiteratureProvider)
    provider_fr = LiteratureProvider(fake_fr)
    fr_nationality = LiteratureProvider.LOCALE_DEFAULT_NATIONALITY["fr_FR"]
    fr_writers = {b["writer"] for b in provider_fr.books if b["nationality"] == fr_nationality}
    for _ in range(20):
        assert fake_fr.writer() in fr_writers

    fake_en = Faker("en_US")
    fake_en.add_provider(LiteratureProvider)
    provider_en = LiteratureProvider(fake_en)
    en_nationality = LiteratureProvider.LOCALE_DEFAULT_NATIONALITY["en_US"]
    en_writers = {b["writer"] for b in provider_en.books if b["nationality"] == en_nationality}
    for _ in range(20):
        assert fake_en.writer() in en_writers


def test_writer_with_explicit_nationality():
    fake = Faker("fr_FR")
    fake.add_provider(LiteratureProvider)
    provider = LiteratureProvider(fake)

    british_writers = {b["writer"] for b in provider.books if b["nationality"] == "britannique"}
    assert british_writers
    for _ in range(20):
        assert fake.writer(nationality="britannique") in british_writers


def test_writer_with_genre():
    fake = Faker("en_US")
    fake.add_provider(LiteratureProvider)
    provider = LiteratureProvider(fake)

    horror_writers = {
        b["writer"] for b in provider.books
        if isinstance(b["genre"], list) and "horror" in [g.lower() for g in b["genre"]]
    }
    assert horror_writers
    for _ in range(20):
        assert fake.writer(genre="horror") in horror_writers


def test_writer_with_nationality_and_genre():
    fake = Faker("en_US")
    fake.add_provider(LiteratureProvider)
    provider = LiteratureProvider(fake)

    american_horror_writers = {
        b["writer"] for b in provider.books
        if b["nationality"] == "American"
        and isinstance(b["genre"], list) and "horror" in [g.lower() for g in b["genre"]]
    }
    assert american_horror_writers
    for _ in range(20):
        assert fake.writer(nationality="American", genre="horror") in american_horror_writers


def test_title_with_genre():
    fake = Faker("en_US")
    fake.add_provider(LiteratureProvider)
    provider = LiteratureProvider(fake)

    horror_titles = {
        b["title"] for b in provider.books
        if isinstance(b["genre"], list) and "horror" in [g.lower() for g in b["genre"]]
    }
    assert horror_titles
    for _ in range(20):
        assert fake.title(genre="horror") in horror_titles


def test_writer_no_match_raises():
    fake = Faker("en_US")
    fake.add_provider(LiteratureProvider)

    with pytest.raises(ValueError, match="No writer found"):
        fake.writer(nationality="American", genre="nonexistent_genre")


def test_title_no_match_raises():
    fake = Faker("en_US")
    fake.add_provider(LiteratureProvider)

    with pytest.raises(ValueError, match="No title found"):
        fake.title(genre="nonexistent_genre")


def test_author_alias_accepts_parameters():
    fake = Faker("en_US")
    fake.add_provider(LiteratureProvider)
    provider = LiteratureProvider(fake)

    british_writers = {b["writer"] for b in provider.books if b["nationality"] == "British"}
    assert british_writers
    assert fake.author(nationality="British") in british_writers
