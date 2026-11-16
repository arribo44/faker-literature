"""Command-line entry point for the faker-literature provider.

Run the demo with:       python -m faker_literature
Import from Wikidata:    python -m faker_literature import-wikidata --limit 500
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from faker import Faker

from faker_literature import LiteratureProvider, __version__, default_db_path
from faker_literature.store import PathLike


def _section(title: str) -> None:
    print(f"\n--- {title} ---")


def demo(db_path: PathLike | None = None) -> None:
    if db_path is not None:
        LiteratureProvider.use_database(db_path)
    fake = Faker("en_US")
    fake.add_provider(LiteratureProvider)

    print("=" * 60)
    print("faker-literature demo  (locale: en_US)")
    print("=" * 60)

    # 1. A single coherent book record
    _section("book() -> one coherent record")
    print(json.dumps(fake.book(), ensure_ascii=False, indent=2))

    # 2. Individual accessors (each call is independent / random)
    _section("Individual accessors (independent random draws)")
    print(f"writer()          -> {fake.writer()}   (default: locale nationality)")
    print(f"title()           -> {fake.title()}")
    print(f"genre()           -> {fake.genre()}")
    print(f"publication_year()-> {fake.publication_year()}")
    print(f"pages()           -> {fake.pages()}")
    print(f"publisher()       -> {fake.publisher()}")
    print(f"nationality()     -> {fake.nationality()}")

    # 3. Aliases
    _section("Aliases")
    print(f"author()          -> {fake.author()}   (alias of writer())")
    print(f"literary_work()   -> {fake.literary_work()}   (alias of book())")

    # 4. Filtered writers and titles
    _section("Filtered writers & titles")
    print(f"writer(nationality='British')        -> {fake.writer(nationality='British')}")
    print(f"writer(genre='horror')              -> {fake.writer(genre='horror')}")
    print("writer(nationality='American', genre='horror')")
    print(f"                                    -> {fake.writer(nationality='American', genre='horror')}")
    print(f"title(genre='horror')               -> {fake.title(genre='horror')}")
    print(f"title(genre='science fiction')      -> {fake.title(genre='science fiction')}")

    # 5. Locale switch: fr_FR
    _section("Locale switch: fr_FR")
    fake_fr = Faker("fr_FR")
    fake_fr.add_provider(LiteratureProvider)
    print(json.dumps(fake_fr.book(), ensure_ascii=False, indent=2))
    print(f"writer()           -> {fake_fr.writer()}   (default: 'francais')")
    print(f"writer(nationality='britannique') -> {fake_fr.writer(nationality='britannique')}")
    print(f"writer(genre='roman policier')    -> {fake_fr.writer(genre='roman policier')}")
    print(f"title(genre='roman policier')     -> {fake_fr.title(genre='roman policier')}")

    # 6. Advanced queries
    _section("books_by_author('Agatha Christie')")
    for book in fake.books_by_author("Agatha Christie"):
        print(f"  - {book['title']} ({book['year']})")

    _section("books_by_genre('horror')")
    for book in fake.books_by_genre("horror"):
        print(f"  - {book['writer']}: {book['title']} ({book['year']})")

    _section("books_by_year_range(1940, 1960)")
    for book in fake.books_by_year_range(1940, 1960):
        print(f"  - {book['year']} | {book['writer']}: {book['title']}")

    # 7. Catalogue overview
    _section("Catalogue overview")
    authors = fake.all_authors()
    genres = fake.all_genres()
    nationalities = fake.all_nationalities()
    print(f"all_authors()      -> {len(authors)} authors, e.g. {authors[:3]}")
    print(f"all_genres()       -> {len(genres)} genres: {genres}")
    print(f"all_nationalities()-> {nationalities}")

    print("\n" + "=" * 60)
    print("End of demo")
    print("=" * 60)


def import_wikidata(db_path: PathLike, limit: int, min_sitelinks: int) -> None:
    from faker_literature.importers import wikidata

    store = LiteratureProvider.use_database(db_path)
    count = wikidata.import_into(store, limit=limit, min_sitelinks=min_sitelinks)
    print(f"Imported {count} works from Wikidata into {store.path}")
    print(f"Books per source: {store.sources()}")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="faker-literature", description="Demo and catalogue tools of faker-literature."
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--db", metavar="PATH",
        help="persistent catalogue to use (the demo uses the bundled one by default)",
    )
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("demo", help="show sample generated data (default)")
    importer = commands.add_parser("import-wikidata", help="add well-known works from Wikidata")
    importer.add_argument("--limit", type=int, default=500, help="maximum number of works (default: 500)")
    importer.add_argument(
        "--min-sitelinks", type=int, default=30,
        help="minimum number of Wikipedia articles about a work (default: 30)",
    )
    args = parser.parse_args(argv)

    if args.command == "import-wikidata":
        import_wikidata(args.db or default_db_path(), args.limit, args.min_sitelinks)
    else:
        demo(args.db)


if __name__ == "__main__":
    main()
