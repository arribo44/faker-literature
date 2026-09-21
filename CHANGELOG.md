# Changelog

Toutes les évolutions notables de `faker-literature` sont documentées dans ce fichier.

Le format s'inspire de [Keep a Changelog](https://keepachangelog.com/fr-FR/1.1.0/) et les versions suivent [Semantic Versioning](https://semver.org/lang/fr/).

## [0.1.0] - 2026-08-29

### Ajoute

- Creation du provider Faker `LiteratureProvider`.
- Support des locales `fr_FR` et `en_US`.
- Generation d'ecrivains, titres, genres, annees de publication, nombres de pages et editeurs.
- Ajout de `book()` et `literary_work()` pour produire une notice litteraire coherente.
- Ajout de l'alias `author()` pour `writer()`.
- Packaging PyPI avec `setup.py`.
- Tests automatises et documentation d'utilisation.

[0.1.0]: https://github.com/arribo44/faker-literature/releases/tag/v0.1.0
