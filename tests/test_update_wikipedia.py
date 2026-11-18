"""Page counts and publishers from the infoboxes of Wikipedia articles, without network."""

import update_wikipedia

FRENCH_ARTICLE = """{{Infobox Livre
 | auteur             = [[Henning Mankell]]
 | titre_orig         = Mannen som log
 | langue             = [[Suédois]]
 | éditeur_orig       = Ordfront förlag
 | titre              = L’Homme qui souriait
 | éditeur            = [[Éditions du Seuil]]<ref>{{Lien web|titre=Notice}}</ref>
 | dateparution       = {{Date|4|février|2005|en littérature}}
 | pages              = 361 <!-- édition française -->
 | suivant            = [[Le Guerrier solitaire]]
}}
'''''L’Homme qui souriait''''' est un roman policier."""

ENGLISH_ARTICLE = """{{Short description|Novel}}
{{Infobox book
| name = Shutter Island
| language = English
| publisher = [[William Morrow and Company|William Morrow]]
| pages = 369
}}"""


def test_parse_the_french_edition_of_a_translation():
    assert update_wikipedia.parse_infobox(FRENCH_ARTICLE, "fr_FR") == {
        "publisher": "Éditions du Seuil", "publisher_link": "Éditions du Seuil", "pages": 361,
        "title": "L’Homme qui souriait", "translation": True, "language": "Suédois"}


def test_parse_the_original_english_edition():
    infobox = update_wikipedia.parse_infobox(ENGLISH_ARTICLE, "en_US")
    assert infobox["publisher"] == "William Morrow" and infobox["publisher_link"] == "William Morrow and Company"
    assert infobox["pages"] == 369 and infobox["language"] == "English" and not infobox["translation"]
    assert update_wikipedia.parse_infobox("No infobox here", "en_US") is None


def test_clean_and_pages():
    assert update_wikipedia.clean("[[Fayard (maison d'édition)|Fayard]], puis [[Le Livre de poche]]") == (
        "Fayard, puis Le Livre de poche")
    assert update_wikipedia.clean("{{Lang|en|texte=Mannen}}<br />''roman''") == "Mannen roman"
    assert update_wikipedia.pages_of("2 vol. (420 et 380)") is None
    assert update_wikipedia.pages_of("361 <!-- édition française -->") == 361
    assert update_wikipedia.pages_of("8") is None


def _catalogue(language_article=FRENCH_ARTICLE, **book):
    book = {"year": 1994, "genre": ["novel"], "title": {"fr_FR": "L'Homme qui souriait", "en_US": "The Man Who Smiled"},
            "pages": None, "publisher": {"fr_FR": "ordfront", "en_US": "ordfront"}, "wikidata_id": "Q1", **book}
    data = {"genres": {}, "publishers": {
        "ordfront": {"name": "Ordfront", "country": "SE"},
        "le-seuil": {"name": "Le Seuil", "aliases": ["Éditions du Seuil"], "country": "FR"},
    }, "authors": [{"name": "Henning Mankell", "books": [book]}]}
    cache = {"links": {"Q1": {"fr_FR": "L'Homme qui souriait"}}, "fr": {"L'Homme qui souriait": language_article},
             "en": {}}
    return data, cache


def test_the_french_infobox_replaces_the_original_publisher_and_fills_the_pages():
    data, cache = _catalogue()

    report = update_wikipedia.update(data, cache)

    book = data["authors"][0]["books"][0]
    assert book["publisher"] == {"fr_FR": "le-seuil", "en_US": "ordfront"}
    assert book["pages"] == {"fr_FR": 361, "en_US": None}
    assert report["publisher[fr_FR] replaced"] == report["pages[fr_FR] filled"] == 1


def test_an_infobox_lacking_a_needed_value_is_left_to_the_bnf():
    data, cache = _catalogue(FRENCH_ARTICLE.replace("361", ""))

    report = update_wikipedia.update(data, cache)

    assert data["authors"][0]["books"][0]["publisher"]["fr_FR"] == "ordfront"
    assert report["fr_FR: infobox incomplete"] == 1


def test_an_article_describing_a_foreign_edition_is_left_out():
    # No *_orig parameters and a Swedish publisher: the infobox describes the original edition
    article = "{{Infobox Livre\n| langue = Suédois\n| éditeur = Ordfront\n| pages = 300\n}}"
    data, cache = _catalogue(article)

    update_wikipedia.update(data, cache)

    assert data["authors"][0]["books"][0]["pages"] is None


def test_english_infoboxes_serve_works_written_in_english_only():
    data, cache = _catalogue(publisher={"fr_FR": "le-seuil", "en_US": None}, pages={"fr_FR": 361, "en_US": None})
    cache["links"]["Q1"]["en_US"] = "The Man Who Smiled"
    cache["en"]["The Man Who Smiled"] = ENGLISH_ARTICLE.replace("English", "Swedish")
    update_wikipedia.update(data, cache)
    assert data["authors"][0]["books"][0]["pages"]["en_US"] is None

    cache["en"]["The Man Who Smiled"] = ENGLISH_ARTICLE
    data["publishers"]["morrow"] = {"name": "William Morrow and Company", "aliases": ["William Morrow"],
                                    "country": "US"}
    update_wikipedia.update(data, cache)
    book = data["authors"][0]["books"][0]
    assert book["pages"]["en_US"] == 369 and book["publisher"]["en_US"] == "morrow"


def test_french_titles_are_proposed_for_english_titles():
    data, cache = _catalogue(title={"fr_FR": "The Man Who Smiled", "en_US": "The Man Who Smiled"},
                             title_untranslated=True)
    [proposal] = update_wikipedia.propose_titles(data, cache)
    assert proposal["fr_FR"] == "L'Homme qui souriait" and proposal["wikidata_id"] == "Q1"
    assert proposal["source"] == "https://fr.wikipedia.org/wiki/L'Homme_qui_souriait"


def test_publishers_are_resolved_through_the_wikidata_item_of_their_article():
    data, cache = _catalogue(FRENCH_ARTICLE.replace("[[Éditions du Seuil]]", "[[Hachette Livre|Hachette]]"))
    data["publishers"]["hachette"] = {"name": "Hachette", "country": "FR", "wikidata_id": "Q1"}
    cache["publisher_items"] = {"fr:Hachette Livre": {"id": "Q1", "labels": {"fr": "Hachette Livre"},
                                                     "classes": ["Q2085381"], "countries": ["FR"]}}
    update_wikipedia.update(data, cache)
    assert data["authors"][0]["books"][0]["publisher"]["fr_FR"] == "hachette"


def test_an_unknown_publishing_house_is_added_with_its_country_and_others_are_left_out():
    article = FRENCH_ARTICLE.replace("[[Éditions du Seuil]]", "[[Éditions Zulma|Zulma]]")
    data, cache = _catalogue(article)
    cache["publisher_items"] = {"fr:Éditions Zulma": {"id": "Q42", "labels": {"fr": "Éditions Zulma"},
                                                     "classes": ["Q2085381"], "countries": ["FR"]}}
    update_wikipedia.update(data, cache)
    assert data["publishers"]["editions-zulma"] == {"name": "Éditions Zulma", "country": "FR", "wikidata_id": "Q42"}

    # A person given as the publisher: its language cannot be told
    data, cache = _catalogue(article)
    cache["publisher_items"] = {"fr:Éditions Zulma": {"id": "Q42", "labels": {"fr": "Zulma"},
                                                     "classes": ["Q5"], "countries": []}}
    report = update_wikipedia.update(data, cache)
    assert data["authors"][0]["books"][0]["publisher"]["fr_FR"] == "ordfront"
    assert report["fr_FR: unknown publisher"] == 1
