# Changelog

Toutes les évolutions notables de `faker-literature` sont documentées dans ce fichier.

Le format s'inspire de [Keep a Changelog](https://keepachangelog.com/fr-FR/1.1.0/) et les versions suivent [Semantic Versioning](https://semver.org/lang/fr/).

## [Non publié]

### Modifié

- `literary_work()` accepte les filtres de `book()` ; le message d'erreur d'un tirage sans résultat nomme tous les filtres (`No writer found for genre='nope', nationality='American'`).
- `nationality()` tire chaque auteur une fois, quel que soit son nombre de livres (auparavant, les auteurs prolifiques pesaient davantage).
- `all_authors()` et `writer()` séparent les co-auteurs d'un livre (« A, B ») au lieu de les renvoyer ensemble.
- Python 3.10 ou plus est requis (Faker et TinyDB n'acceptent plus les versions antérieures, et Python 3.8 / 3.9 ne sont plus maintenus) ; Python 3.13 et 3.14 sont pris en charge.
- Le paquet est décrit par `pyproject.toml`, qui remplace `setup.py` et `requirements.txt` ; la version est définie une seule fois (`faker_literature.__version__`).

### Ajouté (provider)

- Prix littéraires : 186 œuvres ont reçu l'un des 84 prix enregistrés par Wikidata (vocabulaire `awards` du catalogue, rempli par `tools/literature_editor/update_awards.py`). Filtre `award` sur toutes les méthodes de tirage (`book(award="goncourt")`, `"*"` pour tout livre primé), `award()`, `books_by_award()`, `all_awards()`, et les prix dans `writer_profile()`.
- `writer_profile(name=None, **filtres)` : fiche d'un écrivain (années de naissance et de mort, nationalité, livres par ordre chronologique, genres principaux). Les années viennent de Wikidata pour 991 des 1 006 auteurs (`tools/literature_editor/update_authors.py`), qui relie aussi 89 auteurs de plus à Wikidata. Champs `writer_born` et `writer_died` dans le schéma ; un test vérifie qu'aucun livre ne paraît avant les 12 ans de son auteur ni plus de 60 ans après sa mort.
- Filtres communs à `book()`, `title()`, `writer()`, `genre()`, `publication_year()`, `pages()` et `publisher()` : `genre`, `nationality`, `author`, `after`, `before` et `century` (`century=19` pour 1801-1900, `-5` pour 500-401 av. J.-C.), combinés par « et ». Classe `BookFilter` exportée.
- `popular=True` : tirage pondéré par le carré de la popularité des œuvres, leur nombre d'articles Wikipédia : le dixième le plus connu du catalogue fait environ les trois quarts des tirages. Champ `popularity` dans le schéma ; les livres qui n'en ont pas comptent pour la médiane. Le script `tools/literature_editor/update_popularity.py` remplit la popularité du catalogue et retrouve sur Wikidata les livres saisis à la main ; l'importeur et l'éditeur la renseignent pour les livres qu'ils ajoutent.
- `books_sample(n, **filtres)` : n livres différents, tirés sans remise (`fake.unique.book()` ne peut pas fonctionner).
- `edition(**filtres)` : édition cohérente d'une œuvre (éditeur de la locale ou de l'œuvre, année d'édition, format poche / broché / relié, pages et prix selon le format, ISBN-13 valide dont le préfixe est propre à l'éditeur).
- `citation(style, book=None, **filtres)` : référence bibliographique APA, MLA ou Chicago (particules, initiales, co-auteurs, années av. J.-C.).
- `LiteratureProvider.register(fake, fallback_locale=None)` : ajoute le provider à chaque locale d'un `Faker` multi-locale, ce que `add_provider()` ne permet pas ; `fallback_locale` (par exemple `"en_US"`) permet d'accepter les locales non prises en charge.
- `writer(nationality=LiteratureProvider.ANY_NATIONALITY)` (ou `"*"`) : écrivain de n'importe quelle nationalité.
- Le filtre `nationality` ignore la casse, comme `genre` ; `books_by_author()` ignore la casse, les accents et la ponctuation, et trouve un co-auteur.
- Les listes dans lesquelles les valeurs sont tirées sont calculées une fois par locale et mises en cache jusqu'à la prochaine modification du catalogue : `writer()`, `title()`, `genre()`, `pages()`... sont 5 à 18 fois plus rapides.

### Outillage

- Commande `faker-literature` (avec `--version`), équivalente à `python -m faker_literature`.
- Annotations de type sur tout le paquet, vérifiées par mypy en mode strict, et fichier `py.typed`.
- Extra `dev` (`pip install -e ".[dev]"`) : tests, ruff, mypy, build et twine.
- Intégration continue GitHub Actions : ruff, mypy, tests de Python 3.10 à 3.14 sous Linux et sous Windows, construction du paquet vérifiée par `twine check` et installée depuis la wheel.
- L'archive source contient l'éditeur du catalogue, ce qui permet d'y lancer toute la suite de tests.

### Sécurité

- Éditeur : l'API exige un cookie de session (`HttpOnly`, `SameSite=Strict`) posé par la page, qu'aucun autre site ne peut joindre à ses requêtes.
- Éditeur : l'enregistrement de `literature.json` conserve ses droits d'accès (il passait en `600`), et une erreur survenant après le début d'une réponse ne produit plus de seconde réponse.
- Base persistante : écriture atomique (fichier temporaire renommé) et verrou inter-processus (`<base>.lock`), pour qu'aucune mise à jour ne soit perdue ni aucun fichier lu à moitié écrit quand plusieurs processus la partagent. Ses droits d'accès sont conservés.
- Base persistante : chaque enregistrement est revalidé à l'ouverture ; une base endommagée ou modifiée à la main est signalée par une `ValueError`.
- Schéma : `wikidata_id` doit être un identifiant Wikidata, et les champs supplémentaires sont limités (20 au plus, noms identifiants, valeurs scalaires de 300 caractères au plus).

### Ajouté

- Catalogue : 1 737 livres ajoutés depuis Wikidata (2 255 livres, 1 006 auteurs, 56 nationalités), choisis parmi les livres les plus notés d'un export Goodreads par le nouvel outil `tools/goodreads_import`. L'export ne sert que de liste d'œuvres à chercher : titres, année, genres, nationalité, pages et éditeur viennent de Wikidata (CC0). Au plus 5 livres par auteur, œuvres à plusieurs auteurs écartées.
- Schéma : `title_untranslated` signale une œuvre jamais traduite en français, dont le titre français est le titre original.
- Vocabulaire : genres non-fiction, jeunes adultes, uchronie, high fantasy, science fantasy, recueil de nouvelles et novella ; alias pour les libellés Wikidata courants (« historical fiction », « crime literature »…).
- Importeur Wikidata : la forme de l'œuvre (roman, pièce…) remplace le genre quand aucun genre connu n'est donné ; `parse_bindings(untranslated_titles=True)` garde les œuvres sans titre français.
- Vocabulaire contrôlé des genres : `literature.json` définit chaque genre une seule fois, sous `genres`, avec un libellé par langue et des alias ; les livres y font référence par identifiant. Le format des enregistrements du `BookStore` et les résultats du provider sont inchangés.
- Module `faker_literature.matching` : normalisation des noms et des titres et détection des doublons, communes à l'éditeur, à l'importeur et au stockage.
- Éditeur : les genres saisis ou proposés par Wikidata sont ramenés au vocabulaire (un genre connu peut n'être saisi que dans une langue) ; un genre inconnu saisi dans les deux langues est ajouté au vocabulaire. Un clic sur un genre du panneau l'ajoute avec sa traduction.
- Tests de cohérence du catalogue (`tests/test_catalogue.py`) : traduction unique de chaque genre et de chaque nationalité, pas de nationalité utilisée comme genre, casse, espaces parasites, tri des auteurs et des livres, unicité des identifiants Wikidata, des noms d'auteurs et des titres.

### Corrigé

- Catalogue : 77 années de première parution corrigées d'après Wikidata maintenant que les livres saisis à la main y sont reliés (*Le Procès* 1925 et non 1915, *Ça* 1986, *Coraline* 2002, *La Vie devant soi* et *La Promesse de l'aube* inversées…). Les dates antiques et celles où Wikidata donne visiblement une date d'édition sont gardées. Titres corrigés : *La Femme gelée* (Ernaux), *J'avoue que j'ai vécu* (Neruda, 1974), *Les Jolies Choses* (Despentes, 1998). Quatre titres français qui n'étaient que le titre anglais avec son sous-titre sont marqués non traduits.
- README : la section « Multiple Locales at Once », qui décrivait l'ancienne boucle sur `add_provider()`, est remplacée par `register()` (section « Several Locales at Once »).
- Recherche d'une œuvre sur Wikidata (import Goodreads, popularité) : une édition qui a son propre auteur ne passe plus pour l'œuvre ; les éditions sans œuvre de rattachement sont ignorées. Sept identifiants du catalogue corrigés (*Divine Comédie*, *Les Fiancés*, *Les Contemplations*, *Feu pâle*…).
- Import Goodreads : les anthologies (« collected », « best of », « 100 of his… ») sont écartées ; un titre français qui n'est que le titre anglais avec son sous-titre compte comme non traduit.
- Importeur Wikidata et éditeur : nationalité d'un auteur qui a plusieurs citoyennetés. Celle du pays de naissance l'emporte au lieu du plus petit identifiant Wikidata (P. G. Wodehouse et Roald Dahl étaient américain et norvégien, ils sont britanniques). Les traductions déjà utilisées par le catalogue sont reprises (« British » donnait parfois « anglais » au lieu de « britannique »), un auteur déjà présent garde sa nationalité, et les gentilés anglais ne sont plus mis en minuscules après la première lettre (« South african »).
- Catalogue : les nombres de pages des 422 livres saisis à la main sont des estimations de la longueur habituelle de l'œuvre, et non ceux d'une édition précise ; ils sont désormais signalés par `"pages_estimated": true` et documentés comme tels. Les livres ajoutés depuis Wikidata gardent les valeurs de leurs éditions.
- Catalogue : les éditeurs de ces mêmes 422 livres, plausibles mais non vérifiés (et pas forcément ceux de l'édition dont vient le nombre de pages), sont signalés par `"publisher_estimated": true`. L'éditeur local pose les deux marqueurs sur un livre saisi sans identifiant Wikidata.
- Catalogue : un genre n'a plus qu'une traduction par langue, ce qui permet aux filtres par genre de trouver tous les livres concernés (« fantastique » ≠ « fantasy », « polar » / « crime », « roman » / « novel », « roman d'aventures »…). Faux genres supprimés (« américain », « capitaine Alatriste », « guerre du Péloponnèse ») et coquille « historie des idées » corrigée.
- Catalogue : titre français de *Skulls in the Stars* (« Des crânes dans les étoiles »), éditeurs erronés corrigés ou retirés (Project Gutenberg, Gustave Simon…), espace parasite dans « Grove Press », auteurs et livres remis dans l'ordre.
- Éditeur : la détection des doublons ne coupe plus le début des titres commençant comme un article (« Anna Karénine », « Theogony », « Lettres persanes »).
- Éditeur : un homonyme ayant un autre identifiant Wikidata n'est plus confondu avec l'auteur déjà présent au catalogue.
- Importeur Wikidata et éditeur : les années av. J.-C. étaient décalées d'un an (le service SPARQL compte 1 av. J.-C. comme l'année 0) ; les dates moins précises que la décennie (« VIIIe siècle av. J.-C. ») ne donnent plus d'année trompeuse. Catalogue corrigé en conséquence : *Timée* (-360), *Bucoliques* (-41), *Géorgiques* (-37), *Énéide* (-19).
- Importeur Wikidata et éditeur : nouvelles tentatives, avec un délai croissant (ou celui de `Retry-After`), quand le service est saturé (429, 5xx), coupe une réponse ou que le réseau échoue.
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
