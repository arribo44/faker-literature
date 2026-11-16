# Changelog

Toutes les évolutions notables de `faker-literature` sont documentées dans ce fichier.

Le format s'inspire de [Keep a Changelog](https://keepachangelog.com/fr-FR/1.1.0/) et les versions suivent [Semantic Versioning](https://semver.org/lang/fr/).

## [Non publié]

### Ajouté

- Vocabulaire contrôlé des genres : `literature.json` définit chaque genre une seule fois, sous `genres`, avec un libellé par langue et des alias ; les livres y font référence par identifiant. Le format des enregistrements du `BookStore` et les résultats du provider sont inchangés.
- Module `faker_literature.matching` : normalisation des noms et des titres et détection des doublons, communes à l'éditeur, à l'importeur et au stockage.
- Éditeur : les genres saisis ou proposés par Wikidata sont ramenés au vocabulaire (un genre connu peut n'être saisi que dans une langue) ; un genre inconnu saisi dans les deux langues est ajouté au vocabulaire. Un clic sur un genre du panneau l'ajoute avec sa traduction.
- Tests de cohérence du catalogue (`tests/test_catalogue.py`) : traduction unique de chaque genre et de chaque nationalité, pas de nationalité utilisée comme genre, casse, espaces parasites, tri des auteurs et des livres, unicité des identifiants Wikidata, des noms d'auteurs et des titres.

### Corrigé

- Catalogue : un genre n'a plus qu'une traduction par langue, ce qui permet aux filtres par genre de trouver tous les livres concernés (« fantastique » ≠ « fantasy », « polar » / « crime », « roman » / « novel », « roman d'aventures »…). Faux genres supprimés (« américain », « capitaine Alatriste », « guerre du Péloponnèse ») et coquille « historie des idées » corrigée.
- Catalogue : titre français de *Skulls in the Stars* (« Des crânes dans les étoiles »), éditeurs erronés corrigés ou retirés (Project Gutenberg, Gustave Simon…), espace parasite dans « Grove Press », auteurs et livres remis dans l'ordre.
- Éditeur : la détection des doublons ne coupe plus le début des titres commençant comme un article (« Anna Karénine », « Theogony », « Lettres persanes »).
- Éditeur : un homonyme ayant un autre identifiant Wikidata n'est plus confondu avec l'auteur déjà présent au catalogue.
- Importeur Wikidata : les genres sont ramenés au vocabulaire du catalogue (les genres inconnus sont ignorés), et les œuvres déjà présentes sont aussi reconnues par leur identifiant Wikidata et par leur titre normalisé (accents, ponctuation, article initial).
- Base persistante : quand le catalogue intégré est mis à jour, les livres importés qu'il contient désormais sont supprimés au lieu de faire doublon.

## [0.3.0] - 2026-10-31

### Ajouté

- Catalogue enrichi : 190 auteurs et 518 livres (contre 164 et 425), notamment des philosophes (Aristote, Descartes, Kant, Rousseau, Sartre, Spinoza…), des classiques latins et anglais (Virgile, Ovide, Chaucer, Milton) et de nouvelles œuvres de Shakespeare, Lovecraft, Eco, Hugo et Verne.
- Éditeur web local du catalogue (`tools/literature_editor/`) : recherche des œuvres d'un auteur par son identifiant Wikidata et ajout dans `literature.json`.
- Éditeur : section « Influencé par » (propriété P737) avec recherche en un clic, message OK / KO après chaque ajout, navigation Précédent / Suivant entre auteurs.

### Corrigé

- Catalogue : doublons supprimés (deux copies de l'Iliade et de l'Odyssée, et « La Pendule de Foucault » remplacée par « Le Pendule de Foucault », 1988), années corrigées, nationalités harmonisées (24 au lieu de 31, toutes en minuscules en français) et genres fusionnés (223 au lieu de 265), dont la traduction erronée « hermétiquement » devenue « mystère en chambre close ».
- Éditeur : détection des doublons insensible aux articles et à la ponctuation des noms (« L'Iliade » = « Iliade », « J. D. Salinger » = « J.D. Salinger »).
- Importeur Wikidata : les auteurs dont le nom n'existe que sous forme de libellé multilingue (`mul`), comme Victor Hugo, étaient ignorés.
- Importeur Wikidata : la date de publication est préférée à la date de création, et les nombres de pages aberrants sont ignorés.

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

[0.3.0]: https://github.com/arribo44/faker-literature/releases/tag/v0.3.0
[0.2.1]: https://github.com/arribo44/faker-literature/releases/tag/v0.2.1
[0.2.0]: https://github.com/arribo44/faker-literature/releases/tag/v0.2.0
[0.1.0]: https://github.com/arribo44/faker-literature/releases/tag/v0.1.0
