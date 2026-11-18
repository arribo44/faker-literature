"""Drop the publishers of the bundled books that work in another language than their locale's.

Without an edition in a locale's language, the importers used to give that
locale the publisher of the original edition: "Bradbury and Evans" for the
French edition of *David Copperfield*, "Gallimard" for the English one of a
French novel.  Such a publisher (one whose ``country`` in the ``publishers``
vocabulary is of another language, see ``PublisherVocabulary.publishes_in``)
is removed from that locale, and so is the page count when it is a copy of
the other locale's, which then described the same, original edition.

Works never translated into French keep their original publisher in
``fr_FR``: their original edition is the only one.  ``update_editions.py``,
``update_wikipedia.py``, ``update_openlibrary.py`` and ``update_bnf.py`` fill
the emptied values from real editions.

Usage::

    python tools/literature_editor/drop_foreign_publishers.py [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import editor

from faker_literature.store import LOCALES
from faker_literature.vocabulary import PublisherVocabulary


def _other(locale):
    return next(other for other in LOCALES if other != locale)


def drop_foreign_publishers(data):
    """Remove the foreign publishers (and copied page counts) of every book in place; return what happened."""
    vocabulary = PublisherVocabulary(data.get("publishers", {}))
    report = Counter()
    for author in data["authors"]:
        for book in author["books"]:
            publisher = book.get("publisher") or {}
            pages = book.get("pages") or {}
            # Compared with the values as they were: both locales may describe the same foreign edition
            original_publisher, original_pages = dict(publisher), dict(pages)
            for locale in LOCALES:
                publisher_id = original_publisher.get(locale)
                if not publisher_id or (locale == "fr_FR" and book.get("title_untranslated")):
                    continue
                if vocabulary.publishes_in(vocabulary.name(publisher_id, locale), locale):
                    continue
                publisher[locale] = None
                report[f"{locale} publishers dropped"] += 1
                other = _other(locale)
                if original_pages.get(locale) is not None and original_pages.get(locale) == original_pages.get(other) \
                        and original_publisher.get(other) == publisher_id:
                    pages[locale] = None
                    report[f"{locale} page counts dropped"] += 1
            # A book without any value has none (null), and the flags qualify values that may be gone
            if book.get("publisher") is not None and not any(book["publisher"].values()):
                book["publisher"] = None
                book.pop("publisher_estimated", None)
            if book.get("pages") is not None and all(value is None for value in book["pages"].values()):
                book["pages"] = None
                book.pop("pages_estimated", None)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--catalogue", type=Path, default=editor.CATALOGUE_PATH)
    parser.add_argument("--dry-run", action="store_true", help="report without writing the catalogue")
    args = parser.parse_args(argv)

    data = editor.load_catalogue(args.catalogue)
    report = drop_foreign_publishers(data)
    print(dict(report))
    if not args.dry_run:
        editor.save_catalogue(data, args.catalogue)
        print(f"catalogue written to {args.catalogue}")


if __name__ == "__main__":
    main()
