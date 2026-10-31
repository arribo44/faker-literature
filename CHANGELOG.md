# Changelog

Toutes les évolutions notables de `faker-literature` sont documentées dans ce fichier.

Le format s'inspire de [Keep a Changelog](https://keepachangelog.com/fr-FR/1.1.0/) et les versions suivent [Semantic Versioning](https://semver.org/lang/fr/).

## [0.2.1] - 2026-10-31

### Ajouté

- Fichier `LICENSE` (MIT), inclus dans les distributions.

## [0.2.0] - 2026-10-31

### Ajouté

- Couche de stockage `BookStore` (TinyDB) avec validation des enregistrements et gestion de plusieurs sources de données.
- Importeur Wikidata : `python -m faker_literature import-wikidata`.
- `LiteratureProvider.use_database(path)` et `default_db_path()` pour utiliser un catalogue persistant enrichi.
- Noms d'auteurs localisables (`{"fr_FR": "Homère", "en_US": "Homer"}`).
- Repli des locales régionales sur leur langue (`fr_CA` → `fr_FR`, `en_GB` → `en_US`).

### Corrigé

- Les livres ajoutés à `literature.json` étaient ignorés tant que l'ancienne base TinyDB existait.
- Le provider n'écrit plus dans son dossier d'installation : le catalogue par défaut est en mémoire.
- Modifier le résultat de `book()` ne modifie plus le catalogue partagé.
- Les méthodes de génération sont environ 8 fois plus rapides (catalogue localisé mis en cache).

## [0.1.0] - 2026-08-29

### Ajoute

- Creation du provider Faker `LiteratureProvider`.
- Support des locales `fr_FR` et `en_US`.
- Generation d'ecrivains, titres, genres, annees de publication, nombres de pages et editeurs.
- Ajout de `book()` et `literary_work()` pour produire une notice litteraire coherente.
- Ajout de l'alias `author()` pour `writer()`.
- Packaging PyPI avec `setup.py`.
- Tests automatises et documentation d'utilisation.

[0.2.1]: https://github.com/arribo44/faker-literature/releases/tag/v0.2.1
[0.2.0]: https://github.com/arribo44/faker-literature/releases/tag/v0.2.0
[0.1.0]: https://github.com/arribo44/faker-literature/releases/tag/v0.1.0
