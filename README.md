# Alex Machina

> *Deus ex machina* : la divinité qui descend des cintres pour dénouer l'intrigue.
> Ici, la machine descend, annonce cinq numéros, et explique posément pourquoi
> vous ne devriez pas l'écouter.

Alex Machina analyse l'intégralité de l'histoire du Loto français — **7 769 tirages
depuis le 19 mai 1976**, tirages exceptionnels compris — produit des grilles pour
le prochain tirage selon quatre méthodes différentes, puis démontre, chiffres à
l'appui, qu'aucune ne bat le tirage au sort le plus bête.

Puis il fait la seule chose qui marche réellement : optimiser non pas la
probabilité de gagner, mais le **montant** gagné quand on gagne.

**[→ Tableau de bord, mis à jour après chaque tirage](https://klayar.github.io/alex-machina/)**

---

## Pourquoi une application qui se contredit elle-même

Prédire un tirage du Loto est impossible, et pas « difficile » : impossible. Les
1 906 884 combinaisons ont rigoureusement la même probabilité, à chaque tirage,
indépendamment de tout ce qui a précédé. Le projet part de là et en fait son sujet :

1. **Il implémente sérieusement** les intuitions que tout le monde a — numéros
   chauds, retardataires, numéros qui « sortent ensemble ».
2. **Il les teste honnêtement**, en rejouant chaque tirage passé avec les seules
   données disponibles à l'époque, aux rapports réellement versés ce jour-là.
3. **Il publie le résultat**, y compris quand il est humiliant pour l'algorithme.

## Ce que ça sait faire

| | |
|---|---|
| **Quatre oracles** | Hasard pur (le témoin), numéros chauds, retardataires, et l'ensemble « Alex Machina ». Chacun choisit son numéro chance selon la même logique que ses boules. Grilles reproductibles à la graine près. |
| **Backtest walk-forward** | Rejoue les 400 derniers tirages sans jamais laisser fuir d'information future. Comparaison **appariée** au hasard pur, p-values corrigées par **Holm-Bonferroni**. |
| **Test du khi-deux** | Mesure l'uniformité réelle des 49 boules et des 10 numéros chance. Fonction de répartition du χ² implémentée à la main, sans SciPy. |
| **Biais du numéro chance** | Le plus fort des deux biais mesurés, et le plus simple à jouer. Jouer le 1 plutôt que le 7 rapporte **98 % de plus** aux rangs concernés, à probabilité rigoureusement identique. |
| **Biais des dates de naissance** | Régression du nombre de gagnants sur la composition de la combinaison tirée. Chaque numéro ≤ 31 attire 17 % de co-gagnants en plus (t = 23). |
| **Économie de la grille** | Espérance de gain calculée sur les rapports réellement versés par la FDJ, rang par rang. Taux de retour effectif, perte moyenne, temps d'attente du jackpot. |
| **Rejouer sa grille fétiche** | `check` rejoue vos cinq numéros sur tout l'historique et vous dit exactement ce qu'ils auraient coûté. |
| **Deux ères, jamais mélangées** | Le 6/49 d'avant 2008 et le 5/49 actuel n'ont ni les mêmes probabilités ni les mêmes valeurs de référence. Les analyses portent sur une ère à la fois. |
| **Tirages exceptionnels** | Super Loto, Grand Loto, Loto de Noël : 114 tirages, ingérés et identifiés à part de leur propre calendrier. |
| **Mise à jour automatique** | GitHub Actions relance tout après chaque tirage, commite les nouvelles données et republie le tableau de bord. |
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
  Numéros chauds         05-09-24-33-48 + 7
  Retardataires          16-17-36-40-46 + 8
  Alex Machina           09-11-24-36-43 + 2
```

### Les autres commandes

```bash
python -m alex_machina stats
```

Fréquences, retards, tests d'uniformité, forme des combinaisons gagnantes.
`--era 6/49` bascule sur l'ancien jeu, `--avec-exceptionnels` ajoute les Super Loto.

```bash
python -m alex_machina backtest --window 400 --repeats 3
```

Le moment de vérité. Compte une dizaine de secondes.

```bash
python -m alex_machina crowd
```

Les deux biais des joueurs, et les grilles construites pour les éviter.

```bash
python -m alex_machina check 3 12 21 27 34 --chance 7 --since 2019-11-04
```

Ce que votre grille fétiche aurait rapporté. Préparez-vous.

```bash
python -m alex_machina build
```

Régénère `docs/index.html` et `docs/data/latest.json`.

## Ce que dit le backtest

Sur les 400 derniers tirages (31/01/2024 → 19/08/2026), trois grilles par
stratégie et par tirage, aux rapports officiels de chaque jour :

| Stratégie | Bons numéros / grille | Retour sur mise | p (Holm) |
|---|---:|---:|---:|
| Hasard pur | 0,5300 | −72,5 % | *témoin* |
| Numéros chauds | 0,4950 | −69,0 % | 0,63 |
| Retardataires | 0,5083 | −58,6 % | 0,63 |
| Alex Machina | 0,4967 | −72,2 % | 0,63 |

L'espérance théorique est de **0,5102 bon numéro par grille**, quelle que soit la
méthode. Toutes s'y collent, aucune ne s'en écarte, et l'ordre du classement
change à chaque nouveau tirage.

Deux précautions, sans lesquelles ce backtest fabriquerait de faux signaux.
**L'appariement** : trois grilles jouées sur le même tirage partagent la même
cible et ne font pas trois observations indépendantes, donc on agrège par tirage
avant de comparer. **La correction de Holm-Bonferroni** : trois stratégies
comparées au témoin, ce sont trois occasions de tomber sur un p < 0,05 par pur
hasard.

## Le seul avantage qui existe vraiment

Les rangs du Loto sont à **répartition** : la cagnotte d'un rang est partagée
entre tous ses gagnants. Or les joueurs ne tirent pas au hasard. Deux biais,
mesurés séparément sur les données de la FDJ.

### Le numéro chance : +98 % entre le meilleur et le pire

On régresse le nombre de gagnants au rang « n° chance seul » sur le nombre de
gagnants au rang « 2 numéros » — lequel ne dépend pas du numéro chance et mesure
donc le seul volume de grilles vendues. Tout écart restant vient des joueurs.
1 480 tirages, R² = 0,80.

| N° chance | Co-gagnants vs moyenne | t | Gain si vous le jouez |
|---:|---:|---:|---:|
| **1** | **−24,3 %** | −25,3 | **+32,1 %** |
| 10 | −20,1 % | −21,3 | +25,1 % |
| 2 | −13,0 % | −13,4 | +15,0 % |
| … | | | |
| 3 | +8,1 % | 7,4 | −7,5 % |
| 5 | +19,4 % | 16,8 | −16,3 % |
| **7** | **+49,8 %** | **37,7** | **−33,3 %** |

Quand le 7 sort, il y a moitié plus de gagnants à se partager la cagnotte que
pour un numéro chance moyen. Jouer le 1 plutôt que le 7 ne change **rien** à vos
chances de gagner, mais rapporte 98 % de plus quand ça tombe.

### Les cinq boules : le biais des dates de naissance

Même méthode, sur le rang « 3 numéros », à volume constant. 1 480 tirages,
R² = 0,86.

| Variable | Coefficient | t | Effet par unité |
|---|---:|---:|---:|
| log(volume de grilles jouées) | 0,9751 | 73,6 | — |
| **numéros ≤ 31** (date de naissance) | **0,1576** | **23,2** | **+17,1 %** |
| numéros ≤ 12 (mois de naissance) | 0,0545 | 8,5 | +5,6 % |
| paires de numéros consécutifs | −0,0490 | −9,1 | −4,8 % |
| somme de la combinaison (centrée) | −0,0179 | −2,3 | −1,8 % |

Le coefficient sur le volume vaut 0,975, à un cheveu de la valeur 1 que la
théorie impose — c'est le signe que le modèle est correctement spécifié. Il
valait 0,62 tant que le témoin de volume n'était pas corrigé de la popularité du
numéro chance : cette erreur de mesure atténuait tous les coefficients et faisait
**sous-estimer** le biais des dates de naissance, pas l'inverse.

**Ce que ça change, et ce que ça ne change pas.** Une grille de numéros élevés
avec un numéro chance impopulaire n'a strictement aucune chance supplémentaire de
sortir. Mais quand elle sort, elle est partagée avec beaucoup moins de monde :
de l'ordre de **+59 %** aux rangs qui ne dépendent que des boules, et **+110 %**
à ceux qui font aussi intervenir le numéro chance. L'espérance de gain reste
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

Onze archives CSV officielles couvrent l'intégralité de l'histoire du jeu. Elles
sont récupérées via l'API publique `sto.api.fdj.fr`, celle qu'utilise le site
fdj.fr, avec repli sur le miroir CDN `media.fdj.fr` — lequel peut avoir plusieurs
années de retard, d'où l'ordre.

**Calendrier régulier** (lundi, mercredi, samedi) :

| Archive | Période | Règles |
|---|---|---|
| `loto` | 19/05/1976 → 04/10/2008 | 6 numéros sur 49 + complémentaire |
| `nouveau_loto` | 06/10/2008 → 04/03/2017 | 5 numéros sur 49 + n° chance sur 10 |
| `loto2017` | 06/03/2017 → 25/02/2019 | idem |
| `loto_201902` | 27/02/2019 → 02/11/2019 | idem |
| `loto_201911` | 06/11/2019 → aujourd'hui | idem, trois tirages par semaine |

**Tirages exceptionnels** : `sloto`, `nouveau_superloto`, `superloto2017`,
`lotonoel2017`, `superloto_201907`, `grandloto_201912` — 114 tirages au total.
Ils s'ajoutent au calendrier sans jamais le remplacer : sur les 71 tirages
exceptionnels de l'ère actuelle, **aucun** n'est tombé un lundi, un mercredi ou
un samedi. Ils sont stockés à part, parce que leurs cagnottes et leurs volumes de
jeu ne sont pas comparables à ceux d'un tirage ordinaire.

Le format a changé quatre fois (31 → 26 → 35 → 50 colonnes, dates en `YYYYMMDD`
puis en `JJ/MM/AAAA`, jours abrégés puis en toutes lettres). Le parseur travaille
par nom de colonne, jamais par position.

Le résultat consolidé est versionné dans **`data/tirages.csv`** : une ligne par
tirage, les numéros, le numéro chance, le type de tirage, et le nombre de
gagnants et le rapport pour chacun des neuf rangs. La base SQLite, elle, est un
artefact local reconstructible et n'est pas versionnée.

## Ce que ça ne sait pas faire

- **Annoncer un tirage exceptionnel.** La FDJ ne publie pas de calendrier
  exploitable, et l'API des tirages à venir renvoie une réponse vide. Le
  tableau de bord signale les vendredis 13 — les treize derniers depuis 2019 ont
  tous eu un Super Loto — mais les autres (Halloween, Noël, Saint-Valentin) sont
  annoncés au coup par coup et restent imprévisibles.
- **Détecter un petit avantage.** Le backtest porte sur 400 tirages ; il écarterait
  sans peine une méthode qui gagnerait 20 % de plus que le hasard, pas une qui en
  gagnerait 2 %. L'absence de preuve n'est pas la preuve de l'absence — même si,
  ici, la théorie tranche déjà la question.
- **Prédire quoi que ce soit.** C'est le sujet du projet, pas une limite.

## Comment la mise à jour se déclenche

Le workflow [`tirage.yml`](.github/workflows/tirage.yml) tourne le soir de chaque
tirage (21 h UTC, lundi/mercredi/samedi) et repasse le lendemain matin en
rattrapage, parce que la FDJ republie ses CSV avec un délai variable. Il :

1. récupère les onze archives et détecte les tirages inédits ;
2. reconstruit statistiques, backtest, modèles de foule et prédictions ;
3. commite `data/tirages.csv` et `docs/` **seulement s'il y a du nouveau** ;
4. republie le tableau de bord sur GitHub Pages.

Si la FDJ est injoignable, l'étape de récupération échoue visiblement mais le
site est tout de même reconstruit depuis le CSV versionné.

## Structure

```
src/alex_machina/
  sources.py      téléchargement des archives FDJ (API + repli CDN)
  ingest.py       parsing des quatre formats de CSV historiques
  model.py        Draw, rangs de gain, ères, calendrier des tirages
  db.py           SQLite + export/import du jeu de données CSV
  stats.py        fréquences, écarts, khi-deux, forme des combinaisons
  predictors.py   les quatre stratégies et l'échantillonnage pondéré
  backtest.py     simulation walk-forward, test apparié, correction de Holm
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

89 tests, dont deux d'intégration qui vérifient que la FDJ n'a pas changé ses URL
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
