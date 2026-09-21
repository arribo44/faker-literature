"""Command-line demo for the faker-literature provider.

Run with:  python -m faker_literature
"""

import json

from faker import Faker

from faker_literature import LiteratureProvider


def _section(title):
    print(f"\n--- {title} ---")


def main():
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
    print(f"writer(nationality='American', genre='horror')")
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


if __name__ == "__main__":
    main()
