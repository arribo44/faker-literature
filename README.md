# Faker Literature Provider

`faker-literature` is an additional [Faker](https://faker.readthedocs.io/) provider for generating literature-related test data. The first release supports `fr_FR` and `en_US`, with well-known French and English-language authors and works.

## Installation

```bash
pip install faker-literature
```

## Usage

```python
from faker import Faker
from faker_literature import LiteratureProvider

fake = Faker("fr_FR")
fake.add_provider(LiteratureProvider)

print(fake.writer())
print(fake.title())
print(fake.genre())
print(fake.publication_year())
print(fake.pages())
print(fake.publisher())
print(fake.book())
```

`book()` returns one coherent dictionary containing `writer`, `title`, `genre`, `year`, `pages`, and `publisher`. `author()` is an alias for `writer()`, and `literary_work()` is an alias for `book()`.

Supported locales are `fr_FR` and `en_US`. Using another locale raises `ValueError` so unsupported data is not silently mixed into a dataset.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[test]"
pytest
python -m build
```

## Publishing on PyPI

After checking the generated distributions with `twine check dist/*`, upload them with:

```bash
twine upload dist/*
```
