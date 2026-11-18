"""Dropping the publishers that work in another language than their locale's."""

import drop_foreign_publishers

PUBLISHERS = {
    "gallimard": {"name": "Gallimard", "country": "FR"},
    "knopf": {"name": "Alfred A. Knopf", "country": "US"},
    "kodansha": {"name": "Kodansha", "country": "JP"},
    "maison": {"name": "Maison sans pays"},
}


def _catalogue(*books):
    return {"publishers": PUBLISHERS, "authors": [{"name": "A", "books": list(books)}]}


def test_the_publisher_of_the_original_edition_leaves_the_other_locale():
    copied = {"title": {"fr_FR": "Un roman", "en_US": "A Novel"},
              "pages": {"fr_FR": 300, "en_US": 300}, "publisher": {"fr_FR": "knopf", "en_US": "knopf"}}
    translated = {"title": {"fr_FR": "Le Roman", "en_US": "The Novel"},
                  "pages": {"fr_FR": 320, "en_US": 290}, "publisher": {"fr_FR": "knopf", "en_US": "knopf"}}
    data = _catalogue(copied, translated)

    report = drop_foreign_publishers.drop_foreign_publishers(data)

    # The French page count was that of the American edition too, unless it differs
    assert copied["publisher"] == {"fr_FR": None, "en_US": "knopf"} and copied["pages"] == {"fr_FR": None, "en_US": 300}
    assert translated["pages"] == {"fr_FR": 320, "en_US": 290}
    assert report == {"fr_FR publishers dropped": 2, "fr_FR page counts dropped": 1}


def test_a_book_left_without_publisher_has_none_and_loses_its_flags():
    japanese = {"title": {"fr_FR": "Kokoro", "en_US": "Kokoro"}, "pages": {"fr_FR": 250, "en_US": 250},
                "pages_estimated": True, "publisher": {"fr_FR": "kodansha", "en_US": "kodansha"},
                "publisher_estimated": True}
    data = _catalogue(japanese)

    drop_foreign_publishers.drop_foreign_publishers(data)

    # Both locales described the Japanese edition
    assert japanese["publisher"] is None and "publisher_estimated" not in japanese
    assert japanese["pages"] is None and "pages_estimated" not in japanese


def test_untranslated_works_and_publishers_without_country_are_kept():
    untranslated = {"title": {"fr_FR": "Kokoro", "en_US": "Kokoro"}, "title_untranslated": True,
                    "pages": None, "publisher": {"fr_FR": "knopf", "en_US": "knopf"}}
    unknown = {"title": {"fr_FR": "B", "en_US": "B"}, "pages": None,
               "publisher": {"fr_FR": "maison", "en_US": "gallimard"}}
    data = _catalogue(untranslated, unknown)

    drop_foreign_publishers.drop_foreign_publishers(data)

    assert untranslated["publisher"] == {"fr_FR": "knopf", "en_US": "knopf"}
    assert unknown["publisher"] == {"fr_FR": "maison", "en_US": None}
