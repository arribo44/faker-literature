# Import Goodreads

Ajoute au catalogue livré (`faker_literature/DATAS/literature.json`) les œuvres d'un export Goodreads (`books.csv`, le jeu « Goodreads-books » de Kaggle), en passant par Wikidata.

```bash
python tools/goodreads_import/import_goodreads.py data/goodreads/books.csv
python tools/goodreads_import/import_goodreads.py data/goodreads/books.csv --limit 200 --dry-run
```

L'export ne donne qu'un titre anglais, la date d'une édition, et ni genre ni nationalité. Il sert seulement de **liste d'œuvres à chercher** ; tout ce qui est écrit dans le catalogue vient de Wikidata (licence CC0) :

1. **Sélection** : livres notés par au moins 1 000 lecteurs (`--min-ratings`), sans coffrets, intégrales ni guides de lecture. Les éditions d'une même œuvre sont fusionnées et la série est retirée du titre (« (Harry Potter #6) »). On garde au plus 10 œuvres par auteur, les plus notées d'abord.
2. **Recherche** : chaque titre est cherché sur Wikidata parmi les éléments qui ont un auteur (P50). Le premier résultat dont un auteur porte le nom d'un des auteurs Goodreads est retenu, sans tenir compte des accents, de la casse ni de la ponctuation. Une édition mène à l'œuvre dont elle est l'édition (P629).
3. **Détails** : la requête de l'importeur Wikidata donne les titres, l'année de première parution, les genres (ou à défaut la forme : roman, pièce…), la nationalité, les pages et l'éditeur.
4. **Ajout** : par les règles de l'éditeur local (même auteur reconnu par identifiant ou par nom, livre déjà présent refusé, genres ramenés au vocabulaire).

Règles propres à cet import :

- **Titre non traduit** : une œuvre sans titre français sur Wikidata (souvent jamais traduite) garde son titre original dans les deux langues, signalé par `"title_untranslated": true`.
- **Plafond par auteur** : un auteur n'a pas plus de 5 livres au catalogue (`--max-per-author`), pour que les auteurs prolifiques ne dominent pas le tirage. Les livres déjà présents ne sont jamais retirés.
- **Co-auteurs** : les œuvres à plusieurs auteurs sont laissées de côté.
- **Vocabulaire** : quelques alias de genres Wikidata sont ajoutés (« historical fiction » → roman historique…), ainsi que des genres nouveaux (non-fiction, jeunes adultes, uchronie, novella…), gardés seulement si un livre les utilise.
- **Données de l'export** : les pages et l'éditeur de l'export ne sont pas repris. La licence du jeu Kaggle n'étant pas vérifiée, l'export et le cache restent dans `data/goodreads/`, exclu de Git.

Les recherches et les réponses de Wikidata sont gardées dans `<export>.cache.json` : un import interrompu reprend où il s'était arrêté. Comptez de 30 minutes à une heure pour l'export complet, presque entièrement en recherches, espacées pour ne pas surcharger Wikidata.
