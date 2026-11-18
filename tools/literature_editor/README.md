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
- Les éditeurs sont enregistrés par leur identifiant dans le vocabulaire `publishers`, en tête du fichier. Chaque éditeur saisi est cherché parmi les noms et les alias du vocabulaire, sans tenir compte de la casse, des accents ni de la ponctuation : « Éditions Gallimard » donne `gallimard`. Les propositions de Wikidata sont remplacées par le nom du catalogue quand l'éditeur est connu. Un éditeur inconnu devient un nouvel éditeur du vocabulaire, sans pays ni identifiant Wikidata (à compléter à la main), et le message de confirmation le signale. Si c'est une autre graphie d'un éditeur déjà présent, ajoutez-la plutôt à ses `aliases`.
- Un livre enregistré sans identifiant Wikidata reçoit `"pages_estimated": true` et `"publisher_estimated": true` (s'il a des pages et un éditeur) : ces valeurs saisies à la main ne sont vérifiées par aucune source.
- Un livre déjà présent (même identifiant, ou même titre pour le même auteur, sans tenir compte d'un article initial : « L'Iliade » = « Iliade ») est refusé.
- Un auteur est reconnu par son identifiant Wikidata, ou à défaut par son nom, sans tenir compte des accents, de la casse, des espaces ni de la ponctuation (« J. D. Salinger » = « J.D. Salinger »). Cela évite de créer des doublons. Un homonyme qui a un autre identifiant Wikidata est un auteur différent.
- Le fichier garde exactement sa mise en forme (indentation de 2 espaces, caractères accentués lisibles), donc `git diff` ne montre que les ajouts. L'écriture est atomique : un fichier temporaire est remplacé d'un seul coup, ce qui évite tout fichier à moitié écrit.

- Un livre ajouté depuis Wikidata reçoit sa popularité (`popularity`), son nombre d'articles Wikipédia, qui sert au tirage `popular=True` du provider.

Relisez les ajouts avec `git diff faker_literature/DATAS/literature.json`, puis lancez `pytest` avant de commiter.

## Mettre à jour la popularité

```bash
python tools/literature_editor/update_popularity.py [--dry-run]
```

Le script remplace la popularité de chaque livre qui a un identifiant Wikidata par le nombre actuel d'articles Wikipédia de l'œuvre. Il cherche aussi sur Wikidata les livres qui n'ont pas d'identifiant, par titre anglais puis français, et leur donne celui de la première œuvre trouvée du même auteur, sauf si un autre livre du catalogue l'a déjà. Comptez une dizaine de minutes.

## Sécurité

- Le serveur n'écoute que sur `127.0.0.1` : il est inaccessible depuis le réseau.
- Il refuse les requêtes dont l'en-tête `Host` ou `Origin` ne correspond pas à sa propre adresse. Une page web ouverte dans un autre onglet ne peut donc pas écrire dans le catalogue, même par rebinding DNS.
- Les appels à l'API exigent un cookie de session, tiré au hasard à chaque démarrage du serveur et posé par la page elle-même (`HttpOnly`, `SameSite=Strict`). Le navigateur ne l'envoie jamais avec une requête déclenchée par un autre site (image, formulaire, script) : une autre page ne peut donc pas non plus lancer de recherches Wikidata en votre nom. Après un redémarrage du serveur, rechargez la page.
- Les écritures n'acceptent que du JSON, limité à 64 Ko, et chaque livre est validé avec le schéma du paquet avant d'être enregistré. Le fichier garde ses droits d'accès d'origine.
- Les textes venant de Wikidata sont insérés dans la page comme texte, jamais comme HTML. Une politique de sécurité du contenu (CSP) bloque en plus tout script externe.

## Mettre à jour la vie des auteurs

```bash
python tools/literature_editor/update_authors.py [--dry-run]
```

Le script relie à Wikidata les auteurs qui n'ont pas d'identifiant, par l'auteur (P50) de leurs livres dont le nom correspond, puis renseigne `born` et `died` (années, négatives av. J.-C.) pour chaque auteur, quand Wikidata les donne à l'année ou à la décennie près. Lancez-le après avoir ajouté des auteurs avec l'éditeur.

## Mettre à jour les prix littéraires

```bash
python tools/literature_editor/update_awards.py [--dry-run]
```

Le script remplace les prix de chaque livre qui a un identifiant Wikidata par les prix littéraires que son œuvre a reçus (P166, prix rattachés à « prix littéraire »), enregistrés par identifiant dans le vocabulaire `awards`, en tête du fichier. Les prix sans libellé français et anglais, et les palmarès que Wikidata classe parmi les prix (« Modern Library 100 Best Novels »…), sont écartés.

## Mettre à jour les séries

```bash
python tools/literature_editor/update_series.py [--dry-run]
```

Le script remplace les séries de chaque livre qui a un identifiant Wikidata par les séries auxquelles son œuvre appartient (P179), avec son rang dans la série quand Wikidata le donne (qualificatif P1545, nombre entier). Les séries sont enregistrées par identifiant dans le vocabulaire `series`, en tête du fichier, après les prix.

Wikidata range aussi sous P179 des collections d'éditeur, des revues, des franchises de films ou des séries télévisées : seules sont gardées les séries et les cycles de livres (trilogies, sagas…) et les personnages récurrents (Maigret, Adam Dalgliesh : la série de romans qui leur est consacrée). Le nom français d'une série est son libellé français, sinon son libellé multilingue (`mul`), sinon son nom anglais sans les mots qui la décrivent (« Wallander novels » → « Wallander », « canon of Hercule Poirot » → « Hercule Poirot »).

## Compléter les pages et les éditeurs

```bash
python tools/literature_editor/update_editions.py [--dry-run] [--rows FICHIER]
```

Le script cherche les éditions françaises et anglaises de chaque œuvre (P747, ou P629 de l'édition, avec la langue P407) et en tire, pour la locale de même langue, le nombre de pages (P1104) et l'éditeur (P123) :

- une valeur manquante est prise dans une édition de la langue de la locale. Le nombre de pages et l'éditeur viennent d'une même édition quand elle donne les deux, la plus ancienne (en général la première traduction) ;
- pour une œuvre écrite dans une autre langue, une valeur qui ne correspond à aucune édition de la langue de la locale venait de l'édition originale (G. P. Putnam's Sons pour l'édition française d'un roman américain) : elle est remplacée par celle d'une édition de cette langue, s'il y en a une ;
- les valeurs saisies à la main (`pages_estimated`, `publisher_estimated`) ne sont pas modifiées : elles décrivent une édition courante, quand les éditions de Wikidata sont souvent anciennes ou inhabituelles.

Les éditeurs sont ramenés au vocabulaire `publishers` par identifiant Wikidata, puis par nom. Un éditeur inconnu y est ajouté avec son pays, s'il s'agit bien d'une maison d'édition, d'une marque éditoriale, de presses universitaires ou d'un club de livres : Wikidata donne aussi pour éditeurs des personnes, des sites (Gallica), des collections et des revues. Les éditeurs qui ne servent plus à aucun livre sont retirés du vocabulaire. Lancez ensuite `pytest` : `tests/test_catalogue.py` signale un nouvel éditeur dont le nom ne serait qu'une variante d'un éditeur existant.

`--rows` garde les réponses de Wikidata dans un fichier, pour qu'un second passage (après `--dry-run`) ne l'interroge pas de nouveau.

## Compléter les pages et les éditeurs avec Wikipédia

```bash
python tools/literature_editor/update_wikipedia.py [--dry-run] [--cache FICHIER] [--collect]
python tools/literature_editor/update_wikipedia.py --cache FICHIER --propose-titles titres.json
```

L'infobox de l'article français d'une œuvre (« Infobox Livre ») décrit son édition française : la première pour une œuvre française, la traduction pour une autre, dont l'édition originale figure dans les paramètres `*_orig`. Son `éditeur` et ses `pages` donnent donc ceux d'une édition française réelle, et son `titre` le titre français d'un livre resté en anglais. L'infobox de l'article anglais (« Infobox book ») décrit l'édition originale : elle ne sert qu'aux œuvres écrites en anglais.

- Un livre ne reçoit les valeurs d'une infobox que si elles couvrent toutes celles qui lui manquent (pages et éditeur ensemble), pour qu'elles décrivent une même édition ; les autres sont laissés à `update_bnf.py`, à lancer ensuite.
- L'éditeur est retrouvé par l'article vers lequel pointe l'infobox, via son élément Wikidata : un éditeur connu sous un autre nom (« Hachette Livre ») est reconnu par son identifiant ; un éditeur inconnu n'est ajouté que si c'est une maison d'édition, avec son pays. Un éditeur sans lien, ou dont la langue ne peut être établie, est écarté.
- Les règles sur les valeurs saisies à la main sont celles de `update_bnf.py`.

Wikipédia limite le débit de son API : la collecte lit 20 articles par requête, avec des pauses, et reprend après un refus (429).

## Compléter les pages et les éditeurs français avec la BnF

```bash
python tools/literature_editor/update_bnf.py [--dry-run] [--cache FICHIER] [--collect] [--limit N]
```

Wikidata décrit peu d'éditions françaises. Ce script interroge le catalogue général de la Bibliothèque nationale de France (API SRU, `https://catalogue.bnf.fr/api/SRU`) pour les livres dont le titre français est une traduction (pas `title_untranslated`) et dont le nombre de pages ou l'éditeur en français manque, ou dont l'éditeur français n'est que celui de l'édition originale (éditeur d'un pays non francophone).

- La recherche demande les textes imprimés en français de l'auteur (par son nom de famille) ayant ce titre ; seules les notices dont le titre est le même (sans tenir compte de la casse, des accents, de la ponctuation ni d'un article initial) sont retenues. Les éditions en gros caractères, en braille ou sonores, et celles en plusieurs volumes pour le nombre de pages, sont écartées.
- L'éditeur qui a publié le plus d'éditions de l'œuvre est son éditeur français habituel ; les clubs de livres (France Loisirs, Le Grand Livre du mois, Rombaldi…), qui rééditent les autres, passent après. Sa plus ancienne édition paginée donne le nombre de pages : pages et éditeur décrivent une même édition réelle.
- Un éditeur français qui n'était que celui de l'édition originale est remplacé, ainsi que le nombre de pages s'il était le même qu'en anglais (celui de l'édition originale).
- Les valeurs saisies à la main (`pages_estimated`, `publisher_estimated`) ne sont pas modifiées.
- Les noms d'éditeurs de la BnF (« Payot et Rivages », « Presses pocket », « A. Michel ») sont ramenés au vocabulaire `publishers` par nom, par alias, en ignorant « Éditions », « éditeur » et « et » / « & », et par la table `BNF_NAMES` des abréviations. Un éditeur inconnu est ajouté au vocabulaire, avec le pays de son lieu de publication quand il est connu.

### Titres français des livres « non traduits »

Un livre marqué `title_untranslated` n'a pas de titre français à chercher. Pourtant, beaucoup ont été traduits : Wikidata n'en connaissait simplement pas le titre français. La BnF note le titre original des traductions (zone 454), ce qui permet de les retrouver :

```bash
# 1. Chercher les traductions par le titre original (anglais)
python tools/literature_editor/update_bnf.py --cache cache.json --collect --titles
# 2. Écrire les titres trouvés, à relire
python tools/literature_editor/update_bnf.py --cache cache.json --propose-titles titres.json
# 3. Après relecture : appliquer les titres, puis les pages et éditeurs de ces traductions
python tools/literature_editor/update_bnf.py --cache cache.json --apply-titles titres.json
```

Les propositions de `update_wikipedia.py --propose-titles` (le `titre` de l'infobox française) ont le même format. Le titre proposé par la BnF est le plus fréquent parmi les traductions en français seul (les éditions bilingues sont écartées), avec les majuscules de l'usage français : celle du premier mot, et celle du nom qui suit un article défini initial (« L'Architecture du bonheur », mais « Une saison en enfer »). Chaque proposition indique le nombre de traductions trouvées et leurs autres titres. Relisez le fichier : supprimez une proposition fausse, ou corrigez son `fr_FR`. Appliquer un titre retire le marqueur `title_untranslated` ; le nombre de pages et l'éditeur français viennent alors des mêmes traductions.

`--collect` remplit seulement le cache (`--cache`), sans toucher au catalogue : la collecte de plus d'un millier de livres prend une quarantaine de minutes, à raison d'une requête par seconde. Les passages suivants lisent le cache.

Les notices de la BnF sont réutilisées sous la [Licence Ouverte / Open Licence 2.0](https://www.etalab.gouv.fr/licence-ouverte-open-licence/), qui impose de citer la source : « Bibliothèque nationale de France, catalogue général ». La mention figure dans le README du paquet.
