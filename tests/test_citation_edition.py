"""Bibliographic references and fake editions."""

import datetime

import pytest
from faker import Faker

from faker_literature import LiteratureProvider
from faker_literature.citation import format_citation, initials, split_name
from faker_literature.edition import is_valid_isbn13, isbn13_check_digit, make_isbn13, publisher_code


@pytest.fixture(params=["fr_FR", "en_US"])
def fake(request):
    fake = Faker(request.param)
    fake.add_provider(LiteratureProvider)
    fake.seed_instance(5)
    return fake


HOBBIT = {"writer": "J.R.R. Tolkien", "title": "The Hobbit", "year": 1937, "publisher": "Allen & Unwin"}
TWO = {"writer": "Michael Dorris, Louise Erdrich", "title": "The Crown of Columbus", "year": 1991,
       "publisher": "HarperCollins"}
ODYSSEY = {"writer": "Homer", "title": "Odyssey?", "year": -800, "publisher": None}


@pytest.mark.parametrize("book, style, locale, expected", [
    (HOBBIT, "apa", "en_US", "Tolkien, J. R. R. (1937). The Hobbit. Allen & Unwin."),
    (HOBBIT, "MLA", "en_US", "Tolkien, J.R.R. The Hobbit. Allen & Unwin, 1937."),
    (TWO, "apa", "en_US", "Dorris, M., & Erdrich, L. (1991). The Crown of Columbus. HarperCollins."),
    (TWO, "apa", "fr_FR", "Dorris, M. et Erdrich, L. (1991). The Crown of Columbus. HarperCollins."),
    (TWO, "chicago", "en_US", "Dorris, Michael, and Louise Erdrich. The Crown of Columbus. HarperCollins, 1991."),
    (dict(TWO, writer="A Alpha, B Beta, C Gamma"), "mla", "en_US", "Alpha, A, et al. The Crown of Columbus. "
                                                                   "HarperCollins, 1991."),
    (ODYSSEY, "apa", "en_US", "Homer (800 BC). Odyssey?"),
    (ODYSSEY, "chicago", "fr_FR", "Homer. Odyssey? 800 av. J.-C."),
])
def test_citation_styles(book, style, locale, expected):
    assert format_citation(book, style, locale) == expected


def test_names_are_split_and_abbreviated():
    assert split_name("Honoré de Balzac") == ("Honoré", "de", "Balzac")
    assert split_name("Voltaire") == ("", "", "Voltaire")
    assert initials("Jean-Paul") == "J.-P." and initials("J.K.") == "J. K."
    assert format_citation({"writer": "Honoré de Balzac", "title": "Le Père Goriot", "year": 1835,
                            "publisher": None}, "mla", "fr_FR") == "Balzac, Honoré de. Le Père Goriot. 1835."


def test_provider_citations(fake):
    book = fake.book(author="Victor Hugo")
    assert fake.citation("apa", book=book).startswith(f"Hugo, V. ({book['year']}). {book['title']}")
    assert fake.citation("chicago", author="Victor Hugo").startswith("Hugo, Victor. ")
    with pytest.raises(ValueError, match="Unknown citation style"):
        fake.citation("harvard")
    with pytest.raises(TypeError, match="either a book or filters"):
        fake.citation(book=book, genre="novel")


def test_isbn13():
    assert isbn13_check_digit("978030640615") == "7"  # 978-0-306-40615-7
    assert is_valid_isbn13("978-0-306-40615-7") and not is_valid_isbn13("978-0-306-40615-8")
    isbn = make_isbn13("Gallimard", "fr_FR", 42)
    assert is_valid_isbn13(isbn) and isbn.startswith("978-2-") and isbn.split("-")[3] == "0042"
    # One publisher, one prefix
    assert publisher_code("Gallimard", "fr_FR") == publisher_code("Gallimard", "fr_FR")
    assert make_isbn13("Penguin", "en_US", 1)[:5] in ("978-0", "978-1")


def test_editions_are_coherent(fake):
    locale = LiteratureProvider(fake).provider_locale
    work_titles = {book["title"] for book in LiteratureProvider(fake).books}
    for _ in range(200):
        edition = fake.edition()
        assert edition["title"] in work_titles
        # Older works are reissued from 1950 on
        assert max(edition["year"], 1950) <= edition["edition_year"] <= datetime.date.today().year
        assert edition["pages"] > 0 and edition["price"] > 0
        assert edition["currency"] == ("EUR" if locale == "fr_FR" else "USD")
        assert is_valid_isbn13(edition["isbn"])
        assert "popularity" not in edition


def test_edition_filters_and_formats(fake):
    edition = fake.edition(author="Victor Hugo", popular=True)
    assert edition["writer"] == "Victor Hugo"
    formats = {fake.edition()["format"] for _ in range(100)}
    assert formats in ({"poche", "broché", "relié"}, {"mass market paperback", "paperback", "hardcover"})
