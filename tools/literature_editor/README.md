# Éditeur du catalogue

Petite application web locale pour enrichir `faker_literature/DATAS/literature.json` (le catalogue livré avec le paquet) à partir de Wikidata.

## Lancement

Depuis la racine du projet :

```bash
.venv/bin/python tools/literature_editor/server.py
```

La page s'ouvre dans le navigateur à l'adresse <http://127.0.0.1:8765/>. `Ctrl+C` arrête le serveur.

| Option | Effet |
|--------|-------|
| `--port 9000` | Utilise un autre port |
| `--no-browser` | N'ouvre pas le navigateur automatiquement |
| `--catalogue chemin.json` | Modifie un autre fichier, par exemple une copie pour essayer sans risque |

Aucune dépendance supplémentaire n'est nécessaire, mais il faut un accès à `query.wikidata.org`.

## Utilisation

1. **Saisir l'identifiant Wikidata de l'auteur** : `Q134798`, ou l'URL `https://www.wikidata.org/wiki/Q134798`. Si vous ne le connaissez pas, tapez le nom et suivez le lien « Cherchez l'auteur sur Wikidata ». L'adresse `http://127.0.0.1:8765/?id=Q134798` lance directement la recherche, ce qui permet de garder un auteur en favori.
2. **Vérifier l'auteur** :
   - s'il est déjà dans le catalogue (badge « au catalogue »), ses livres lui seront ajoutés et son nom comme sa nationalité ne changent pas ;
   - sinon, il sera créé au premier ajout. Choisissez de préférence une nationalité déjà utilisée : la liste s'affiche quand vous tapez dans le champ.
3. **Explorer ses influences** : la section « Influencé par » liste les auteurs qui l'ont influencé, d'après la propriété P737 de Wikidata. Le badge « au catalogue » signale ceux déjà présents. Un clic sur l'identifiant d'un auteur (Q…) lance sa recherche, et le bouton « Précédent » du navigateur ramène à l'auteur d'avant. Les autres influences (œuvres, mouvements) sont listées à part, avec un simple lien vers Wikidata.
4. **Parcourir ses œuvres** : elles sont triées de la plus connue à la moins connue, et seules les 300 premières sont affichées. Vous pouvez les filtrer par titre, masquer celles déjà au catalogue, ou n'afficher que les fiches complètes. Le badge « à compléter » signale un champ obligatoire manquant.
5. **Ouvrir une œuvre** pour vérifier et corriger ses informations. Les champs marqués d'une `*` sont obligatoires : titres en français et en anglais, année, genres. Les genres proposés par Wikidata sont remplacés par ceux du catalogue quand ils y figurent déjà (« crime fiction » devient « polar » / « crime »). Le panneau « Genres déjà utilisés » ajoute d'un clic un genre existant, avec sa traduction, à la dernière œuvre dont vous avez sélectionné un champ « genres ».
6. **Cliquer sur « Ajouter au catalogue »**. Le livre est validé, puis enregistré dans `literature.json`. Le résultat s'affiche sous le bouton : **✓ OK** avec le nombre total de livres, ou **✗ KO** avec la raison (champ manquant, année invalide, doublon…). Le terminal du serveur indique aussi `enregistré` ou `refusé` à chaque clic.

## D'où viennent les données

| Champ | Source Wikidata |
|-------|-----------------|
| Titres | Libellés français et anglais de l'œuvre (ou libellé multilingue `mul`) |
| Année | Date de publication (P577), sinon date de création (P571) |
| Genres | Genre (P136), libellés français et anglais, ramenés au vocabulaire du catalogue quand c'est possible |
| Pages | Édition en français / en anglais (P747 + P1104), sinon l'œuvre elle-même |
| Éditeur | Éditeur de l'édition française / anglaise, sinon celui de l'œuvre |
| Nationalité | Gentilé (P1549) du pays de citoyenneté (P27) de l'auteur |

Wikidata est souvent incomplet, en particulier pour les pages et les éditeurs. Ces champs sont facultatifs. Les valeurs aberrantes (plus de 100 000 pages) sont ignorées.

## Ce qui est écrit dans le fichier

- Le livre est inséré chez son auteur dans l'ordre chronologique. Un nouvel auteur est inséré dans l'ordre alphabétique, sans tenir compte des accents.
- L'identifiant Wikidata est enregistré sur l'auteur et sur le livre (`wikidata_id`), ce qui permet de détecter les doublons.
- Les genres sont enregistrés par leur identifiant dans le vocabulaire `genres`, en tête du fichier. Chaque genre saisi est cherché dans ce vocabulaire (libellés et alias, en français ou en anglais, sans tenir compte de la casse ni des accents) : un genre connu peut donc n'être saisi que dans une langue. Un genre inconnu devient un nouveau genre du vocabulaire, à condition d'être saisi dans les deux langues, à la même position : le n-ième genre inconnu en français est apparié au n-ième genre inconnu en anglais. Le message de confirmation signale les genres créés.
- Un livre déjà présent (même identifiant, ou même titre pour le même auteur, sans tenir compte d'un article initial : « L'Iliade » = « Iliade ») est refusé.
- Un auteur est reconnu par son identifiant Wikidata, ou à défaut par son nom, sans tenir compte des accents, de la casse, des espaces ni de la ponctuation (« J. D. Salinger » = « J.D. Salinger »). Cela évite de créer des doublons. Un homonyme qui a un autre identifiant Wikidata est un auteur différent.
- Le fichier garde exactement sa mise en forme (indentation de 2 espaces, caractères accentués lisibles), donc `git diff` ne montre que les ajouts. L'écriture est atomique : un fichier temporaire est remplacé d'un seul coup, ce qui évite tout fichier à moitié écrit.

Relisez les ajouts avec `git diff faker_literature/DATAS/literature.json`, puis lancez `pytest` avant de commiter.

## Sécurité

- Le serveur n'écoute que sur `127.0.0.1` : il est inaccessible depuis le réseau.
- Il refuse les requêtes dont l'en-tête `Host` ou `Origin` ne correspond pas à sa propre adresse. Une page web ouverte dans un autre onglet ne peut donc pas écrire dans le catalogue, même par rebinding DNS.
- Les écritures n'acceptent que du JSON, limité à 64 Ko, et chaque livre est validé avec le schéma du paquet avant d'être enregistré.
- Les textes venant de Wikidata sont insérés dans la page comme texte, jamais comme HTML. Une politique de sécurité du contenu (CSP) bloque en plus tout script externe.
