"""Fill page counts and publishers from the infoboxes of the French and English Wikipedia articles of each work.

The French article of a work ("Infobox Livre") describes its French edition:
the first one for a French work, the French translation for another one,
whose original edition goes in the ``*_orig`` parameters.  Its ``éditeur``
and ``pages`` thus give the ``fr_FR`` publisher and page count of one real
edition, and its ``titre`` the French title of a work flagged
``title_untranslated``.  The English article ("Infobox book") describes the
original edition: it gives the ``en_US`` values of works written in English
only.

A book gets the values of an infobox only when they cover every value it
needs (missing, or a publisher of another language than the locale's), so
that its page count and publisher describe one edition; the others are left
to ``update_bnf.py``, to run afterwards.  The values typed by hand
(``pages_estimated``, ``publisher_estimated``) are left alone, except a
foreign French publisher typed by hand, as in ``update_bnf.py``.  Facts only
(publisher, number of pages, title) are taken from the articles.

Usage::

    python tools/literature_editor/update_wikipedia.py [--dry-run] [--cache FILE] [--collect]
    python tools/literature_editor/update_wikipedia.py --cache FILE --propose-titles PROPOSALS.json

``--cache`` keeps the articles read from Wikipedia in FILE; ``--collect``
only fills it.  The proposed titles are reviewed and applied as those of
``update_bnf.py`` (``update_bnf.py --apply-titles``).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import editor
import update_bnf
import update_editions

from faker_literature.importers.wikidata import run_query
from faker_literature.matching import title_key
from faker_literature.store import LOCALES, MAX_PAGES
from faker_literature.vocabulary import PublisherVocabulary

USER_AGENT = "faker-literature-tools/0.4 (catalogue maintenance)"
BATCH_SIZE = 20
PAUSE = 2.0
ATTEMPTS = 6
MIN_PAGES = 10
WIKIS = {"fr_FR": "fr", "en_US": "en"}
INFOBOXES = {"fr_FR": re.compile(r"\{\{\s*Infobox\s+Livre\b", re.IGNORECASE),
             "en_US": re.compile(r"\{\{\s*Infobox\s+book\b", re.IGNORECASE)}
COUNTRIES = {"fr_FR": update_bnf.FRANCOPHONE, "en_US": {"US", "GB", "CA", "AU", "IE", "NZ", "IN", "ZA"}}
FRENCH = re.compile(r"fran[cç]ais|french", re.IGNORECASE)
ENGLISH = re.compile(r"anglais|english", re.IGNORECASE)

# The Wikidata item of the article a publisher links to: its labels, classes and country
PUBLISHER_ITEMS_QUERY = """
SELECT ?article ?item ?fr ?en ?class ?country WHERE {
  VALUES ?article { %s }
  ?article schema:about ?item .
  OPTIONAL { ?item rdfs:label ?fr . FILTER(LANG(?fr) = "fr") }
  OPTIONAL { ?item rdfs:label ?en . FILTER(LANG(?en) = "en") }
  OPTIONAL { ?item wdt:P31 ?class }
  OPTIONAL { { ?item wdt:P17/wdt:P297 ?country } UNION { ?item wdt:P159/wdt:P17/wdt:P297 ?country } }
}
"""

SITELINKS_QUERY = """
SELECT ?work ?site ?article WHERE {
  VALUES ?work { %s }
  VALUES ?site { <https://fr.wikipedia.org/> <https://en.wikipedia.org/> }
  ?article schema:about ?work ; schema:isPartOf ?site .
}
"""


# Wikitext

def template(text, start):
    """Return the template of ``text`` starting at ``start`` (``{{...}}``, nested templates included)."""
    depth, index = 0, start
    while index < len(text) - 1:
        pair = text[index:index + 2]
        if pair == "{{":
            depth, index = depth + 1, index + 2
        elif pair == "}}":
            depth, index = depth - 1, index + 2
            if depth == 0:
                return text[start:index]
        else:
            index += 1
    return text[start:]


def parameters(infobox):
    """Return the ``{name: raw value}`` of a template, split on its top-level ``|``."""
    body, depth, parts, current = infobox[2:-2], 0, [], []
    index = 0
    while index < len(body):
        pair = body[index:index + 2]
        if pair in ("{{", "[["):
            depth, current, index = depth + 1, current + [pair], index + 2
            continue
        if pair in ("}}", "]]"):
            depth, current, index = max(depth - 1, 0), current + [pair], index + 2
            continue
        if body[index] == "|" and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(body[index])
        index += 1
    parts.append("".join(current))
    values = {}
    for part in parts[1:]:
        if "=" in part:
            name, value = part.split("=", 1)
            values[name.strip().casefold()] = value.strip()
    return values


def _template_text(match):
    name, *arguments = [part.strip() for part in match.group(1).split("|")]
    name = name.casefold()
    if name in ("lang", "langue", "lang-en", "lang-fr", "nobr", "nowrap", "small", "smallcaps", "abbr"):
        named = [argument.split("=", 1)[1] for argument in arguments if argument.startswith("texte=")]
        positional = [argument for argument in arguments if "=" not in argument]
        return named[0] if named else positional[-1] if positional else ""
    if name in ("date", "date-", "date de publication", "start date", "publication date"):
        return " ".join(argument for argument in arguments if "=" not in argument)
    return ""


def clean(value):
    """Return the text of a wikitext value: links, templates, comments and tags removed."""
    value = re.sub(r"<!--.*?-->", "", value, flags=re.DOTALL)
    value = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", value, flags=re.DOTALL | re.IGNORECASE)
    value = re.sub(r"<br\s*/?>", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"<[^>]+>", "", value)
    for _ in range(3):
        value = re.sub(r"\{\{([^{}]*)\}\}", _template_text, value)
    value = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", value)
    value = re.sub(r"\[https?://\S+\s*([^\]]*)\]", r"\1", value)
    value = value.replace("''", "")
    return re.sub(r"\s+", " ", value).strip(" ,;")


def _link_target(value):
    """The article a value links to ("Fayard (maison d'édition)"), without its disambiguation."""
    match = re.search(r"\[\[([^|\]]+)", value)
    return re.sub(r"\s*\([^)]*\)$", "", match.group(1)).strip() if match else None


def pages_of(value):
    match = re.search(r"\b(\d{2,5})\b", clean(value))
    if not match or re.search(r"\b[2-9]\s*(?:vol|tomes?)\b", clean(value), re.IGNORECASE):
        return None
    pages = int(match.group(1))
    return pages if MIN_PAGES <= pages <= MAX_PAGES else None


def parse_infobox(wikitext, locale):
    """Return ``{"publisher", "pages", "title", "translation", "language"}`` of an article's infobox, or ``None``."""
    match = INFOBOXES[locale].search(wikitext or "")
    if not match:
        return None
    values = parameters(template(wikitext, match.start()))
    publisher_field = "éditeur" if locale == "fr_FR" else "publisher"
    raw_publisher = values.get(publisher_field, "")
    publisher = clean(raw_publisher)
    # A list of publishers ("Gallimard, puis Folio"): the first one
    publisher = re.split(r"\s*(?:,|;| puis | then | / )\s*", publisher)[0] if publisher else ""
    return {
        "publisher": publisher or None,
        "publisher_link": _link_target(raw_publisher),
        "pages": pages_of(values.get("pages", "")),
        "title": clean(values.get("titre", "")) if locale == "fr_FR" else None,
        # The French article of a translation describes the original edition in *_orig parameters
        "translation": any(name.endswith("_orig") and clean(value) for name, value in values.items()),
        "language": clean(values.get("langue" if locale == "fr_FR" else "language", "")),
    }


# Fetching

def fetch_sitelinks(work_ids):
    """Return ``{work: {"fr_FR": article, "en_US": article}}``."""
    links = {}
    for start in range(0, len(work_ids), 200):
        batch = " ".join("wd:" + work for work in work_ids[start:start + 200])
        for row in run_query(SITELINKS_QUERY % batch):
            work = row["work"]["value"].rsplit("/", 1)[-1]
            locale = "fr_FR" if "fr.wikipedia" in row["site"]["value"] else "en_US"
            title = urllib.parse.unquote(row["article"]["value"].rsplit("/wiki/", 1)[1]).replace("_", " ")
            links.setdefault(work, {})[locale] = title
        time.sleep(1)
    return links


def fetch_articles(titles, wiki, sleep=time.sleep, log=print):
    """Return ``{title: wikitext}`` of the articles of ``wiki`` ("fr", "en"), redirects followed."""
    articles = {}
    for start in range(0, len(titles), BATCH_SIZE):
        data = urllib.parse.urlencode({
            "action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main", "format": "json",
            "formatversion": "2", "redirects": "1", "maxlag": "5", "titles": "|".join(titles[start:start + BATCH_SIZE]),
        }).encode()
        request = urllib.request.Request(f"https://{wiki}.wikipedia.org/w/api.php", data=data,
                                         headers={"User-Agent": USER_AGENT})
        for attempt in range(ATTEMPTS):
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    answer = json.load(response)
                break
            except urllib.error.HTTPError as error:
                if error.code not in (429, 500, 502, 503, 504) or attempt == ATTEMPTS - 1:
                    raise
                retry_after = error.headers.get("Retry-After", "") if error.headers else ""
                sleep(int(retry_after) if retry_after.isdigit() else 10 * 2 ** attempt)
        redirects = {redirect["to"]: redirect["from"] for redirect in answer["query"].get("redirects", [])}
        for page in answer["query"]["pages"]:
            if "revisions" in page:
                articles[redirects.get(page["title"], page["title"])] = page["revisions"][0]["slots"]["main"]["content"]
        if start and start % 200 == 0:
            log(f"  {wiki}: {start} / {len(titles)}")
        sleep(PAUSE)
    return articles


def collect(data, cache, log=print, sleep=time.sleep):
    """Fill ``cache`` (``{"links": ..., "fr": {...}, "en": {...}}``) with the articles of the catalogue's works."""
    ids = sorted({book["wikidata_id"] for author in data["authors"] for book in author["books"]
                  if "wikidata_id" in book})
    if "links" not in cache:
        cache["links"] = fetch_sitelinks(ids)
    for locale, wiki in WIKIS.items():
        known = cache.setdefault(wiki, {})
        titles = sorted({links[locale] for links in cache["links"].values() if locale in links} - set(known))
        log(f"{len(titles)} {wiki}.wikipedia articles to read")
        known.update(fetch_articles(titles, wiki, sleep=sleep, log=log))
    items = cache.setdefault("publisher_items", {})
    wanted = sorted({f"{wiki}:{infobox['publisher_link']}" for locale, wiki in WIKIS.items()
                     for infobox in (parse_infobox(text, locale) for text in cache[wiki].values())
                     if infobox and infobox["publisher_link"]} - set(items))
    log(f"{len(wanted)} publisher articles to look up on Wikidata")
    items.update(fetch_publisher_items(wanted, sleep=sleep))


def _article_url(key):
    wiki, title = key.split(":", 1)
    return f"https://{wiki}.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'), safe='')}"


def fetch_publisher_items(keys, sleep=time.sleep):
    """Return ``{"fr:Éditions du Seuil": {"id", "labels", "classes", "countries"}}`` for publisher articles."""
    by_url = {_article_url(key): key for key in keys}
    items = {}
    urls = sorted(by_url)
    for start in range(0, len(urls), 50):
        rows = run_query(PUBLISHER_ITEMS_QUERY % " ".join(f"<{url}>" for url in urls[start:start + 50]))
        for row in rows:
            item = items.setdefault(by_url[row["article"]["value"]], {
                "id": row["item"]["value"].rsplit("/", 1)[-1], "labels": {}, "classes": [], "countries": []})
            for language in ("fr", "en"):
                if language in row:
                    item["labels"].setdefault(language, row[language]["value"])
            for field, key in (("classes", "class"), ("countries", "country")):
                value = row.get(key, {}).get("value", "").rsplit("/", 1)[-1]
                if value and value not in item[field]:
                    item[field].append(value)
        sleep(1)
    return items


def publisher_of_item(item, locale, publishers):
    """Return the vocabulary id of the publishing house ``item``, adding it when unknown; ``None`` otherwise.

    Known publishers are found by Wikidata id, then by name; an unknown one is
    added only when it is a publishing house, an imprint or the like
    (``update_editions.PUBLISHER_CLASSES``), with its country.
    """
    vocabulary = publishers.vocabulary
    for publisher_id, publisher in vocabulary.publishers.items():
        if publisher.get("wikidata_id") == item["id"]:
            return publisher_id
    labels = [item["labels"][language] for language in (("fr", "en") if locale == "fr_FR" else ("en", "fr"))
              if language in item["labels"]]
    for label in labels:
        known = publishers.resolve(label)
        if known:
            return known
    if not labels or not set(item["classes"]) & update_editions.PUBLISHER_CLASSES:
        return None
    country = item["countries"][0] if len(item["countries"]) == 1 else None
    publisher_id = vocabulary.add(labels[0], country=country, wikidata_id=item["id"])
    publishers._register(publisher_id, labels[0], country)
    publishers.added.append(publisher_id)
    return publisher_id


# Updating the catalogue

def needs(book, vocabulary, locale):
    """Return the fields of ``book`` an infobox may fill or correct in ``locale``."""
    if locale == "fr_FR":
        return update_bnf.needs(book, vocabulary)
    if book.get("pages_estimated") and book.get("publisher_estimated"):
        return set()
    needed = set()
    pages, publisher = (book.get("pages") or {}).get(locale), (book.get("publisher") or {}).get(locale)
    if pages is None and not book.get("pages_estimated"):
        needed.add("pages")
    if not book.get("publisher_estimated"):
        if publisher is None:
            needed.add("publisher")
        elif not vocabulary.publishes_in(vocabulary.name(publisher, locale), locale):
            # The publisher of the original edition ("Olympia Press", in Paris and in English, is not one)
            needed.add("publisher")
            if not book.get("pages_estimated") and pages == (book.get("pages") or {}).get("fr_FR"):
                needed.add("pages")
    return needed


def describes_edition(infobox, locale, publisher_id, vocabulary):
    """Whether the infobox values are those of an edition in the locale's language."""
    country = vocabulary.publishers[publisher_id].get("country") if publisher_id else None
    if country is not None and country not in COUNTRIES[locale]:
        return False
    if locale == "fr_FR":
        return infobox["translation"] or bool(FRENCH.search(infobox["language"])) or country in COUNTRIES[locale]
    # The English article describes the original edition: an English one for a work written in English only
    return bool(ENGLISH.search(infobox["language"]))


def update(data, cache):
    """Fill or correct the pages and publishers from the cached infoboxes; return what happened."""
    report = Counter()
    vocabulary = PublisherVocabulary(data["publishers"])
    publishers = update_bnf.BnfPublishers(vocabulary)
    for author in data["authors"]:
        for book in author["books"]:
            links = cache.get("links", {}).get(book.get("wikidata_id"), {})
            for locale, wiki in WIKIS.items():
                article = links.get(locale)
                needed = needs(book, vocabulary, locale)
                if not needed or article not in cache.get(wiki, {}):
                    continue
                infobox = parse_infobox(cache[wiki][article], locale)
                if infobox is None:
                    continue
                publisher_id = None
                if infobox["publisher"]:
                    link = infobox["publisher_link"]
                    item = cache.get("publisher_items", {}).get(f"{wiki}:{link}") if link else None
                    # The article the infobox links to first: "Hachette Livre" is the Hachette of the vocabulary
                    publisher_id = ((publisher_of_item(item, locale, publishers) if item else None)
                                    or publishers.resolve(infobox["publisher"])
                                    or (publishers.resolve(link) if link else None))
                    name = vocabulary.publishers[publisher_id]["name"] if publisher_id else None
                    if isinstance(name, str) and update_bnf.loose_key(name) in update_bnf.LARGE_PRINT_PUBLISHERS:
                        publisher_id = None  # a large-print edition
                    if publisher_id is None:
                        # Not linked, or not a publishing house: its country, thus its language, is unknown
                        report[f"{locale}: unknown publisher"] += 1
                values = {"pages": infobox["pages"], "publisher": publisher_id}
                if any(values[field] is None for field in needed):
                    report[f"{locale}: infobox incomplete"] += 1
                    continue
                if not describes_edition(infobox, locale, publisher_id, vocabulary):
                    report[f"{locale}: infobox of another edition"] += 1
                    continue
                for field in needed:
                    current = book.get(field) or {other: None for other in LOCALES}
                    previous = current.get(locale)
                    current[locale] = values[field]
                    book[field] = current
                    report[f"{field}[{locale}] {'filled' if previous is None else 'replaced'}"] += 1
    dropped = editor.prune_publishers(data)
    report["publishers dropped"] += len(set(dropped) - set(publishers.added))
    report["publishers added"] = len([publisher_id for publisher_id in publishers.added if publisher_id not in dropped])
    return report


def propose_titles(data, cache):
    """Return the French titles of the French articles for the books whose French title is the English one."""
    proposals = []
    for author in data["authors"]:
        for book in author["books"]:
            article = cache.get("links", {}).get(book.get("wikidata_id"), {}).get("fr_FR")
            if not update_bnf.lacks_french_title(book) or article not in cache.get("fr", {}):
                continue
            infobox = parse_infobox(cache["fr"][article], "fr_FR")
            title = infobox and infobox["title"]
            if not title or title_key(title) == title_key(book["title"]["en_US"]) or not infobox["translation"]:
                continue
            proposals.append({"wikidata_id": book["wikidata_id"], "author": update_bnf._names(author)[-1],
                              "en_US": book["title"]["en_US"], "fr_FR": title.replace("’", "'"),
                              "source": f"https://fr.wikipedia.org/wiki/{article.replace(' ', '_')}"})
    return proposals


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--catalogue", type=Path, default=editor.CATALOGUE_PATH)
    parser.add_argument("--dry-run", action="store_true", help="report without writing the catalogue")
    parser.add_argument("--cache", type=Path, help="JSON file keeping the articles read from Wikipedia")
    parser.add_argument("--collect", action="store_true", help="only read Wikipedia into the cache")
    parser.add_argument("--propose-titles", type=Path, metavar="FILE",
                        help="write the French titles found for the books without one, for review")
    args = parser.parse_args(argv)

    data = editor.load_catalogue(args.catalogue)
    cache = json.loads(args.cache.read_text(encoding="utf-8")) if args.cache and args.cache.exists() else {}
    if args.propose_titles:
        proposals = propose_titles(data, cache)
        args.propose_titles.write_text(json.dumps(proposals, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{len(proposals)} French titles proposed in {args.propose_titles}")
        return
    try:
        collect(data, cache)
    finally:
        if args.cache:
            args.cache.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    if args.collect:
        return
    report = update(data, cache)
    for key, count in sorted(report.items()):
        print(f"{key}: {count}")
    if not args.dry_run:
        editor.save_catalogue(data, args.catalogue)
        print(f"catalogue written to {args.catalogue}")


if __name__ == "__main__":
    main()
