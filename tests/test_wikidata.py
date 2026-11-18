import email.message
import http.client
import json
import urllib.error
import urllib.request

import pytest

from faker_literature.importers import wikidata
from faker_literature.store import BookStore, validate_book


def _row(work="Q1", **values):
    defaults = {
        "work": f"http://www.wikidata.org/entity/{work}",
        # A work absent from the catalogue
        "titleFr": "Le Portrait imaginaire",
        "titleEn": "The Imaginary Portrait",
        "author": "http://www.wikidata.org/entity/Q30875",
        "writerFr": "Oscar Wilde",
        "writerEn": "Oscar Wilde",
        "date": "1890-06-20T00:00:00Z",
        "genreFr": "roman gothique",
        "genreEn": "Gothic novel",
        "country": "http://www.wikidata.org/entity/Q145",
        "demonymFr": "Britannique",
        "demonymEn": "British",
    }
    defaults.update(values)
    return {key: {"type": "literal", "value": value} for key, value in defaults.items()}


def test_rows_are_grouped_into_one_valid_record():
    rows = [
        _row(demonymEn="Britons"),
        _row(demonymFr="Britanniques", genreFr="roman philosophique", genreEn="philosophical novel"),
        _row(date="1891-01-01T00:00:00Z", pages="254"),
        _row(country="http://www.wikidata.org/entity/Q27", demonymFr="Irlandais", demonymEn="Irish"),
    ]

    [record] = wikidata.parse_bindings(rows)

    assert record["wikidata_id"] == "Q1"
    assert record["year"] == 1890
    assert record["pages"] == {"fr_FR": 254, "en_US": 254}
    assert record["nationality"] == {"fr_FR": "irlandais", "en_US": "Irish"}
    assert record["genre"] == {
        "fr_FR": ["roman gothique", "roman philosophique"],
        "en_US": ["gothic novel", "philosophical novel"],
    }
    validate_book(dict(record, source="wikidata"))


def test_negative_years_are_parsed():
    # The endpoint follows XSD 1.1 (year 0 = 1 BC): 37 BC comes as -0036
    [record] = wikidata.parse_bindings([_row(date="-0036-01-01T00:00:00Z", datePrecision="9")])

    assert record["year"] == -37


@pytest.mark.parametrize("value, precision, year", [
    ("1890-06-20T00:00:00Z", "11", 1890),
    ("1950-01-01T00:00:00Z", "8", 1950),
    ("0001-01-01T00:00:00Z", "9", 1),
    ("0000-01-01T00:00:00Z", "9", -1),
    ("-0800-01-01T00:00:00Z", "7", None),
    ("1500-01-01T00:00:00Z", "6", None),
    ("1890-06-20T00:00:00Z", None, 1890),
    ("garbage", "9", None),
])
def test_parse_year_handles_precision_and_bc_years(value, precision, year):
    assert wikidata._parse_year(value, precision) == year


def test_imprecise_dates_give_way_to_precise_ones():
    rows = [_row(date="1800-01-01T00:00:00Z", datePrecision="7"), _row(date="1890-06-20T00:00:00Z", datePrecision="11")]
    [record] = wikidata.parse_bindings(rows)
    assert record["year"] == 1890

    # Only a century: no usable year, the work is left out
    assert wikidata.parse_bindings([_row(date="1800-01-01T00:00:00Z", datePrecision="7")]) == []


class _Response:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def read(self, size):
        return self.body


def _http_error(code, retry_after=None):
    headers = email.message.Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return urllib.error.HTTPError(wikidata.ENDPOINT, code, "error", headers, None)


def test_busy_endpoint_is_retried_with_back_off(monkeypatch):
    answers = iter([_http_error(429, "7"), urllib.error.URLError("reset"), http.client.IncompleteRead(b""),
                    _Response(b'{"results": {"bindings": [{"x": {"value": "1"}}]}}')])

    def urlopen(request, timeout):
        answer = next(answers)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    delays = []

    assert wikidata.run_query("SELECT", sleep=delays.append) == [{"x": {"value": "1"}}]
    # Retry-After first, then 2 ** attempt
    assert delays == [7, 4, 8]


@pytest.mark.parametrize("error, calls", [(_http_error(400), 1), (_http_error(503), 3)])
def test_client_errors_are_not_retried_and_attempts_are_bounded(monkeypatch, error, calls):
    count = []

    def urlopen(request, timeout):
        count.append(1)
        raise error

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)

    with pytest.raises(urllib.error.HTTPError):
        wikidata.run_query("SELECT", attempts=3, sleep=lambda delay: None)
    assert len(count) == calls


def test_works_without_genre_or_nationality_are_skipped():
    no_genre = _row(work="Q1")
    del no_genre["genreFr"], no_genre["genreEn"]
    no_nationality = _row(work="Q2")
    del no_nationality["country"], no_nationality["demonymFr"], no_nationality["demonymEn"]

    assert wikidata.parse_bindings([no_genre, no_nationality]) == []


def test_co_authors_are_joined():
    rows = [
        _row(),
        _row(author="http://www.wikidata.org/entity/Q2", writerFr="Ami", writerEn="Friend"),
    ]

    [record] = wikidata.parse_bindings(rows)

    assert record["writer"] == {"fr_FR": "Oscar Wilde, Ami", "en_US": "Oscar Wilde, Friend"}


def test_works_already_in_the_catalogue_are_excluded():
    store = BookStore()
    known = store.books.all()
    hugo = next(book for book in known if book["title"]["fr_FR"] == "Les Misérables")
    duplicate = dict(wikidata.parse_bindings([_row()])[0], title=hugo["title"], year=hugo["year"] + 1)
    new = wikidata.parse_bindings([_row()])[0]

    assert wikidata.exclude_known([duplicate, new], known) == [new]


def test_import_replaces_previous_wikidata_books(monkeypatch):
    responses = iter([
        [{"work": {"value": "http://www.wikidata.org/entity/Q1"}, "links": {"value": "50"}}],
        [_row()],
    ])
    monkeypatch.setattr(wikidata, "run_query", lambda query: next(responses))
    store = BookStore()
    store.replace_source("wikidata", [])

    count = wikidata.import_into(store, limit=10, log=lambda message: None)

    assert count == 1
    assert store.sources()["wikidata"] == 1


def test_publication_date_wins_over_creation_date():
    [record] = wikidata.parse_bindings([_row(date="1869-04-01T00:00:00Z", inception="1860-01-01T00:00:00Z")])
    assert record["year"] == 1869

    no_publication = _row(inception="1860-01-01T00:00:00Z")
    del no_publication["date"]
    [record] = wikidata.parse_bindings([no_publication])
    assert record["year"] == 1860


def test_implausible_page_counts_are_ignored():
    [record] = wikidata.parse_bindings([_row(pages="940512")])

    assert record["pages"] is None


def test_genres_are_mapped_onto_the_vocabulary():
    rows = [
        _row(genreFr="fiction gothique", genreEn="gothic fiction"),
        _row(genreFr="genre inconnu", genreEn="crime fiction"),
        _row(genreFr="genre inconnu", genreEn="unknown genre"),
    ]

    [record] = wikidata.parse_bindings(rows)

    assert record["genre"] == {"fr_FR": ["roman gothique", "polar"], "en_US": ["gothic novel", "crime"]}


def test_works_with_only_unknown_genres_are_skipped():
    assert wikidata.parse_bindings([_row(genreFr="genre inconnu", genreEn="unknown genre")]) == []


def test_known_works_are_matched_by_wikidata_id_or_normalized_title():
    known = [{"wikidata_id": "Q8275", "title": {"fr_FR": "L'Iliade", "en_US": "Iliad"}, "year": -800}]
    record = wikidata.parse_bindings([_row()])[0]
    same_id = dict(record, wikidata_id="Q8275")
    same_title = dict(record, title={"fr_FR": "Iliade", "en_US": "The Iliad"}, year=-799)
    other_year = dict(same_title, year=-500)

    assert wikidata.exclude_known([same_id, same_title, other_year], known) == [other_year]


UK, USA, NORWAY = "Q145", "Q30", "Q20"


def test_country_of_birth_wins_among_several_citizenships():
    demonyms = {UK: ({"britannique"}, {"British"}), USA: ({"américain"}, {"American"})}

    # P. G. Wodehouse, born in England, American citizen later on
    assert wikidata.choose_nationality(demonyms, {UK}, {})["en_US"] == "British"
    # Without a country of birth among the citizenships: the lowest Q-id
    assert wikidata.choose_nationality(demonyms, {NORWAY}, {})["en_US"] == "American"
    assert wikidata.choose_nationality({}, {UK}) is None


def test_translations_already_in_the_catalogue_are_preferred():
    known = wikidata.known_nationalities()
    assert known["British"] == "britannique"
    uk = {UK: ({"anglais", "britannique", "Britanniques"}, {"British", "Briton", "English"})}

    assert wikidata.choose_nationality(uk, (), known) == {"fr_FR": "britannique", "en_US": "British"}
    # Matched on the French demonym when the English one is new
    norway = {NORWAY: ({"norvégien", "Norvégienne"}, {"Norse"})}
    assert wikidata.choose_nationality(norway, (), {"Norwegian": "norvégien"}) == {
        "fr_FR": "norvégien", "en_US": "Norwegian"}


def test_unknown_nationalities_are_capitalized_on_their_first_letter_only():
    demonyms = {"Q258": ({"sud-africain", "sud-africaine"}, {"South African", "South Africans"})}

    # str.capitalize() gave "South african"
    assert wikidata.choose_nationality(demonyms, (), {}) == {"fr_FR": "sud-africain", "en_US": "South African"}
    assert wikidata._pick_demonym(["south African"], "en_US") == "South African"


def test_birth_country_is_read_from_the_rows():
    rows = [
        _row(country="http://www.wikidata.org/entity/Q30", demonymFr="Américain", demonymEn="American",
             birthCountry="http://www.wikidata.org/entity/Q145"),
        _row(birthCountry="http://www.wikidata.org/entity/Q145"),
    ]

    [record] = wikidata.parse_bindings(rows)

    assert record["nationality"] == {"fr_FR": "britannique", "en_US": "British"}


def test_authors_already_in_the_catalogue_keep_their_name_and_nationality():
    known = [{"writer": "Milan Kundera", "nationality": {"fr_FR": "tchèque", "en_US": "Czech"}}]
    record = dict(wikidata.parse_bindings([_row(writerFr="milan kundera", writerEn="Milan  Kundera",
                                                demonymFr="Français", demonymEn="French")])[0])
    other = wikidata.parse_bindings([_row(work="Q2")])[0]

    kundera, wilde = wikidata.align_authors([record, other], known)

    assert kundera["writer"] == "Milan Kundera"
    assert kundera["nationality"] == {"fr_FR": "tchèque", "en_US": "Czech"}
    assert wilde == other


def test_publishers_known_to_the_catalogue_get_their_catalogue_name():
    gallimard = {"publisher": {"fr_FR": "Éditions Gallimard", "en_US": "Gallimard"}, "title": "A"}
    unknown = {"publisher": {"fr_FR": "Maison inconnue", "en_US": "Unknown House"}, "title": "B"}
    none = {"publisher": None, "title": "C"}

    aligned = wikidata.align_publishers([gallimard, unknown, none])

    # Gallimard, a French publisher, published the original edition, not an English one
    assert aligned[0]["publisher"] == {"fr_FR": "Gallimard", "en_US": None}
    assert aligned[1:] == [unknown, none]
    assert gallimard["publisher"]["fr_FR"] == "Éditions Gallimard"  # records are not modified in place


def test_publishers_of_another_language_are_dropped_from_the_locale():
    knopf = {"publisher": {"fr_FR": "Knopf", "en_US": "Alfred A. Knopf"}, "title": "A"}
    kodansha = {"publisher": {"fr_FR": "Kōdansha", "en_US": "Kodansha"}, "title": "B"}
    olympia = {"publisher": {"fr_FR": "Olympia Press", "en_US": "Olympia Press"}, "title": "C"}

    aligned = wikidata.align_publishers([knopf, kodansha, olympia])

    assert aligned[0]["publisher"] == {"fr_FR": None, "en_US": "Alfred A. Knopf"}
    assert aligned[1]["publisher"] is None  # Japanese: neither French nor English
    # A Paris publisher of books in English
    assert aligned[2]["publisher"] == {"fr_FR": "Olympia Press", "en_US": "Olympia Press"}


def test_works_without_french_title_are_kept_only_on_request():
    row = _row(titleEn="Franny and Zooey")
    del row["titleFr"]

    assert wikidata.parse_bindings([row]) == []
    [record] = wikidata.parse_bindings([row], untranslated_titles=True)
    assert record["title"] == {"fr_FR": "Franny and Zooey", "en_US": "Franny and Zooey"}
    assert record["title_untranslated"] is True
    validate_book(dict(record, source="wikidata"))
    assert "title_untranslated" not in wikidata.parse_bindings([_row()], untranslated_titles=True)[0]


def test_the_form_of_the_work_stands_in_for_missing_genres():
    no_genre = _row(formFr="roman", formEn="novel")
    del no_genre["genreFr"], no_genre["genreEn"]
    unknown_genre = _row(work="Q2", genreFr="genre inconnu", genreEn="unknown genre", formFr="roman", formEn="novel")
    known_genre = _row(work="Q3", formFr="roman", formEn="novel")

    records = {record["wikidata_id"]: record["genre"]["en_US"] for record in wikidata.parse_bindings(
        [no_genre, unknown_genre, known_genre])}

    assert records == {"Q1": ["novel"], "Q2": ["novel"], "Q3": ["gothic novel"]}


def _author_row(item, work, author, name):
    entity = "http://www.wikidata.org/entity/"
    return {"item": {"value": entity + item}, "work": {"value": entity + work},
            "author": {"value": entity + author}, "name": {"value": name}}


def test_the_first_hit_written_by_one_of_the_authors_wins():
    items = wikidata.parse_item_authors([
        _author_row("Q1", "Q1", "Q10", "Somebody Else"),
        _author_row("Q2", "Q20", "Q30", "Michael Crichton"),  # an edition of the work Q20
        _author_row("Q3", "Q3", "Q30", "Michael Crichton"),
    ])
    authors = ["Michael  Crichton", "Illustrator"]

    assert wikidata.match_work(authors, ["Q1", "Q2", "Q3"], items) == ("Q20", "Q30")
    assert wikidata.match_work(authors, ["Q1", "Q404"], items) is None


def test_search_retries_when_the_api_answers_an_error(monkeypatch):
    answers = iter([{"error": {"code": "ratelimited"}},
                    {"query": {"search": [{"title": "Q46887"}, {"title": "Q1"}]}}])
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda request, timeout: _Response(json.dumps(next(answers)).encode()))

    assert wikidata.search_items("Harry Potter", sleep=lambda delay: None) == ["Q46887", "Q1"]


def test_work_popularity_is_its_number_of_wikipedia_articles():
    [record] = wikidata.parse_bindings([_row(links="57")])
    assert record["popularity"] == 57
    assert "popularity" not in wikidata.parse_bindings([_row()])[0]


def test_english_title_with_subtitle_as_french_label_is_untranslated():
    row = _row(titleFr="Breaking the Spell: Religion as a Natural Phenomenon", titleEn="Breaking the Spell")

    assert wikidata.parse_bindings([row]) == []
    [record] = wikidata.parse_bindings([row], untranslated_titles=True)
    assert record["title"] == {"fr_FR": "Breaking the Spell", "en_US": "Breaking the Spell"}
    assert record["title_untranslated"] is True
