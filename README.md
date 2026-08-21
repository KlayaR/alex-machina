# Alex Machina

> *Deus ex machina* : la divinité qui descend des cintres pour dénouer l'intrigue.
> Ici, la machine descend, annonce cinq numéros, et explique posément pourquoi
> vous ne devriez pas l'écouter.

Alex Machina analyse l'intégralité de l'histoire du Loto français — **7 655 tirages
depuis le 19 mai 1976** — produit des grilles pour le prochain tirage selon sept
méthodes différentes, puis démontre, chiffres à l'appui, qu'aucune de ces sept
méthodes ne bat le tirage au sort le plus bête.

**[→ Tableau de bord, mis à jour après chaque tirage](https://klayar.github.io/alex-machina/)**

---

## Pourquoi une application qui se contredit elle-même

Prédire un tirage du Loto est impossible, et pas « difficile » : impossible. Les
1 906 884 combinaisons ont rigoureusement la même probabilité, à chaque tirage,
indépendamment de tout ce qui a précédé. Le projet part de là et en fait son sujet :

1. **Il implémente sérieusement** les intuitions que tout le monde a — numéros
   chauds, retardataires, numéros qui « sortent ensemble », momentum.
2. **Il les teste honnêtement**, en rejouant chaque tirage passé avec les seules
   données disponibles à l'époque, aux rapports réellement versés ce jour-là.
3. **Il publie le résultat**, y compris quand il est humiliant pour l'algorithme.

Et une fois cela posé, il fait la seule chose qui marche vraiment : optimiser non
pas la probabilité de gagner, mais le **montant** gagné quand on gagne.

## Ce que ça sait faire

| | |
|---|---|
| **Sept oracles** | Hasard pur, chauds, froids, retardataires, compagnons de route, momentum, et l'ensemble « Alex Machina » qui combine tout. Grilles reproductibles à la graine près. |
| **Backtest walk-forward** | Rejoue les 400 derniers tirages sans jamais laisser fuir d'information future. Compare chaque stratégie au hasard pur par un test de Welch. |
| **Test du khi-deux** | Mesure l'uniformité réelle des 49 boules et des 10 numéros chance. Fonction de répartition du χ² implémentée à la main, sans SciPy. |
| **Modèle de foule** | Régression du nombre de gagnants sur la composition de la combinaison tirée. Prouve le biais « date de naissance » et en tire des grilles à contre-courant. |
| **Économie de la grille** | Espérance de gain calculée sur les rapports réels de la FDJ, rang par rang. Taux de retour effectif, perte moyenne, temps d'attente du jackpot. |
| **Rejouer sa grille fétiche** | `check` rejoue vos cinq numéros sur tout l'historique et vous dit exactement ce qu'ils auraient coûté. |
| **Mise à jour automatique** | GitHub Actions relance tout après chaque tirage (lundi, mercredi, samedi), commite les nouvelles données et republie le tableau de bord. |
| **Jeu de données ouvert** | `data/tirages.csv` : 50 ans de tirages avec les gagnants et rapports des 9 rangs, en CSV brut. |

## Démarrage

Aucune dépendance à installer : le projet n'utilise que la bibliothèque standard
de Python (3.10 ou plus récent).

```bash
git clone https://github.com/KlayaR/alex-machina.git
```

```bash
cd alex-machina && python -m alex_machina update --full
```

La base se reconstruit en une seconde à partir des archives officielles FDJ. Ensuite :

```bash
python -m alex_machina predict
```

```
Grilles pour le tirage du samedi 22 août 2026
─────────────────────────────────────────────
  Hasard pur             01-04-30-36-40 + 9
  Numéros chauds         05-08-23-32-47 + 7
  Numéros froids         20-21-22-35-41 + 7
  Retardataires          16-17-36-40-46 + 8
  Compagnons de route    26-29-30-33-34 + 1
  Momentum               05-12-22-26-32 + 7
  Alex Machina           10-17-23-34-41 + 1
```

### Les autres commandes

```bash
python -m alex_machina stats
```

Fréquences, retards, tests d'uniformité, forme des combinaisons gagnantes.

```bash
python -m alex_machina backtest --window 400 --repeats 3
```

Le moment de vérité. Compte une quinzaine de secondes.

```bash
python -m alex_machina crowd
```

Le biais des joueurs, et les grilles construites pour l'éviter.

```bash
python -m alex_machina check 3 12 21 27 34 --chance 7 --since 2019-11-04
```

Ce que votre grille fétiche aurait rapporté. Préparez-vous.

```bash
python -m alex_machina build
```

Régénère `docs/index.html` et `docs/data/latest.json`.

## Ce que dit le backtest

Sur les 400 derniers tirages, trois grilles par stratégie et par tirage, aux
rapports officiels de chaque jour :

| Stratégie | Bons numéros / grille | Retour sur mise | vs hasard pur |
|---|---:|---:|---:|
| Hasard pur | 0,5300 | −72,5 % | *témoin* |
| Numéros chauds | 0,5058 | −70,7 % | p = 0,36 |
| Numéros froids | 0,5267 | −67,7 % | p = 0,90 |
| Retardataires | 0,5083 | −58,6 % | p = 0,41 |
| Compagnons de route | 0,5067 | −71,8 % | p = 0,37 |
| Momentum | 0,4975 | −70,9 % | p = 0,22 |
| Alex Machina | 0,4925 | −74,1 % | p = 0,15 |

L'espérance théorique est de **0,5102 bon numéro par grille**, quelle que soit la
méthode. Toutes les stratégies s'y collent, aucune ne s'en écarte
significativement, et l'ordre du classement change à chaque nouveau tirage. C'est
la signature du bruit, pas du talent.

## Le seul avantage qui existe vraiment

Les rangs du Loto sont à **répartition** : la cagnotte d'un rang est partagée
entre tous ses gagnants. Or les joueurs ne tirent pas au hasard — ils jouent des
dates de naissance, ce qui sur-représente massivement les numéros 1 à 31.

Alex Machina le vérifie sur les données de la FDJ, en régressant le nombre de
gagnants au rang « 3 numéros » sur la composition de la combinaison tirée, en
neutralisant le volume de grilles vendues (1 480 tirages, R² = 0,66) :

| Variable | Coefficient | t | Effet par unité |
|---|---:|---:|---:|
| log(volume de grilles jouées) | 0,6160 | 36,3 | +85,2 % |
| **numéros ≤ 31** (biais date de naissance) | **0,1479** | **13,9** | **+15,9 %** |
| numéros ≤ 12 (biais mois de naissance) | 0,0502 | 5,0 | +5,2 % |
| paires de numéros consécutifs | −0,0375 | −4,4 | −3,7 % |

Chaque numéro tiré inférieur ou égal à 31 augmente de près de 16 % le nombre de
gagnants à ce rang. Le biais n'est pas une légende : il est massif et mesurable.

**Ce que ça change, et ce que ça ne change pas.** Une grille composée de numéros
élevés n'a strictement aucune chance supplémentaire de sortir. Mais quand elle
sort, elle est partagée avec beaucoup moins de monde — de l'ordre de **+55 % sur
le montant perçu** aux rangs à répartition. L'espérance de gain reste
franchement négative ; elle l'est simplement un peu moins.

## Ce que coûte une grille

Espérance calculée sur les rapports réellement versés, 2 797 tirages depuis 2008 :

- Mise : **2,20 €**
- Espérance de gain : **1,09 €**
- Perte moyenne par grille : **1,11 €**
- Taux de retour effectif : **49,4 %**

Une chance sur 19 068 840 de décrocher le rang 1. À trois grilles par semaine, il
faudrait en moyenne **122 236 ans** pour y arriver.

## Les données

Cinq archives CSV officielles couvrent l'intégralité de l'histoire du jeu. Elles
sont récupérées via l'API publique `sto.api.fdj.fr`, celle qu'utilise le site
fdj.fr, avec repli sur le miroir CDN `media.fdj.fr`.

| Archive | Période | Règles |
|---|---|---|
| `loto` | 19/05/1976 → 04/10/2008 | 6 numéros sur 49 + complémentaire |
| `nouveau_loto` | 06/10/2008 → 04/03/2017 | 5 numéros sur 49 + n° chance sur 10 |
| `loto2017` | 06/03/2017 → 25/02/2019 | idem |
| `loto_201902` | 27/02/2019 → 02/11/2019 | idem |
| `loto_201911` | 06/11/2019 → aujourd'hui | idem, trois tirages par semaine |

Le format a changé quatre fois (31 → 26 → 35 → 50 colonnes, dates en `YYYYMMDD`
puis en `JJ/MM/AAAA`, jours abrégés puis en toutes lettres). Le parseur travaille
par nom de colonne, jamais par position.

Par défaut, toutes les analyses portent sur l'ère actuelle — le jeu de 1976
n'avait ni les mêmes règles ni les mêmes probabilités. `--all-eras` inclut tout.

Le résultat consolidé est versionné dans **`data/tirages.csv`** : une ligne par
tirage, les cinq (ou six) numéros, le numéro chance, et le nombre de gagnants et
le rapport pour chacun des neuf rangs. La base SQLite, elle, est un artefact
local reconstructible et n'est pas versionnée.

## Comment la mise à jour se déclenche

Le workflow [`tirage.yml`](.github/workflows/tirage.yml) tourne le soir de chaque
tirage (21 h UTC, lundi/mercredi/samedi) et repasse le lendemain matin en
rattrapage, parce que la FDJ republie ses CSV avec un délai variable. Il :

1. récupère les archives et détecte les tirages inédits ;
2. reconstruit statistiques, backtest, modèle de foule et prédictions ;
3. commite `data/tirages.csv` et `docs/` **seulement s'il y a du nouveau** ;
4. republie le tableau de bord sur GitHub Pages.

Si la FDJ est injoignable, l'étape de récupération échoue visiblement mais le
site est tout de même reconstruit depuis le CSV versionné.

## Structure

```
src/alex_machina/
  sources.py      téléchargement des archives FDJ (API + repli CDN)
  ingest.py       parsing des quatre formats de CSV historiques
  model.py        Draw, rangs de gain, calendrier des tirages
  db.py           SQLite + export/import du jeu de données CSV
  stats.py        fréquences, écarts, khi-deux, forme des combinaisons
  predictors.py   les sept stratégies et l'échantillonnage pondéré
  backtest.py     simulation walk-forward et test de Welch
  crowd.py        moindres carrés maison, biais des joueurs, grilles à contre-courant
  odds.py         probabilités exactes et espérance empirique
  charts.py       SVG écrit à la main, sans dépendance
  report.py       tableau de bord statique + flux JSON
  cli.py          interface en ligne de commande
```

## Développement

```bash
pip install -e ".[dev]" && pytest
```

71 tests, dont deux d'intégration qui vérifient que la FDJ n'a pas changé ses URL
(désactivés par défaut, `ALEX_MACHINA_NETWORK_TESTS=1` pour les activer).

## Avertissement

Ce projet est un objet pédagogique. Il ne fournit aucun moyen d'augmenter vos
chances de gagner au Loto, pour l'excellente raison qu'il n'en existe aucun.

Le jeu comporte des risques : endettement, isolement, dépendance. Interdit aux
mineurs. Pour en parler : **09 74 75 13 13** (appel non surtaxé) ou
[joueurs-info-service.fr](https://www.joueurs-info-service.fr).

## Licence

MIT. Les données de tirage sont publiées par la Française des Jeux ; ce dépôt
n'est ni affilié à la FDJ, ni approuvé par elle.
