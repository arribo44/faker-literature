# Revue du catalogue

Page web locale qui présente `literature.json` sous forme de tableaux, les données incohérentes d'abord, avec des filtres en listes déroulantes. Elle ne modifie rien : elle aide à repérer ce que les outils de `tools/literature_editor/` ou une correction à la main doivent traiter.

## Lancement

À la racine du dépôt :

```bash
python -m http.server
```

puis ouvrez <http://localhost:8000/tools/catalogue_review/>. La page lit le catalogue à chaque chargement : rechargez-la après une mise à jour. Ouverte directement depuis le disque (`file://`), elle propose de choisir le fichier `literature.json`.

## Anomalies

Les règles reprennent celles de `tests/test_catalogue.py` ; gardez-les en accord.

| Gravité | Anomalie | Signification |
|---|---|---|
| Incohérence | Éditeur fr / en d'une autre langue | L'éditeur vient d'un pays d'une autre langue que la locale : en général l'éditeur de l'édition originale. Les livres jamais traduits en français et les éditeurs anglophones installés à Paris (Olympia Press, Obelisk Press, Shakespeare and Company) ne comptent pas. |
| Incohérence | Année hors de la vie de l'auteur | Parution avant ses 12 ans ou plus de 60 ans après sa mort. |
| Incohérence | Pages fr / en très différentes | Un nombre de pages fait plus du double de l'autre : édition abrégée, intégrale, en plusieurs volumes ? |
| Incohérence | Titre fr en anglais | Le titre français est le titre anglais, sans le marqueur `title_untranslated`. |
| À compléter | Pages / éditeur fr ou en manquants | Aucune valeur dans cette locale. |
| À compléter | Titre « non traduit » à vérifier | Marqué jamais traduit : beaucoup l'ont été, sous un titre que Wikidata ignorait (`update_bnf.py --titles`). |
| À compléter | Éditeur sans pays | Sa langue ne peut pas être vérifiée. |
| À savoir | Pages / éditeur estimés, sans Wikidata, sans popularité | Valeurs saisies à la main, livres que les outils ne peuvent pas compléter. |

Les lignes sont triées par gravité (une incohérence pèse plus que tous les manques), puis par popularité : les livres les plus connus, qui sortent le plus souvent avec `popular=True`, d'abord. Les cases du résumé filtrent le tableau sur une anomalie ; survolez-les pour leur explication.

## Filtres

- **Livres** : anomalie ou gravité, source des valeurs (saisies à la main ou Wikidata), nationalité de l'auteur, genre, siècle de parution, éditeur, recherche (auteur, titre, identifiant Wikidata), tri.
- **Éditeurs** : anomalie (sans pays, utilisé dans une locale d'une autre langue, sans identifiant Wikidata), pays, locale d'usage, recherche (nom, alias, identifiant), tri.

Le bouton « Exporter en CSV » enregistre les lignes filtrées (séparateur `;`, lisible par un tableur).
