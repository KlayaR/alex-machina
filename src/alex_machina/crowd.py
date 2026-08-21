"""Modèle de « foule » : la seule vraie optimisation possible au Loto.

On ne peut rien faire pour gagner plus souvent. En revanche, les rangs de gain
du Loto sont à répartition : la cagnotte d'un rang est partagée entre tous ses
gagnants. Or les joueurs ne choisissent pas leurs numéros au hasard — ils jouent
massivement des dates de naissance, ce qui sur-représente les numéros 1 à 31, et
plus encore 1 à 12.

Ce module le vérifie sur données réelles : on régresse le nombre de gagnants
observé à un rang donné sur la composition de la combinaison tirée, en
neutralisant le volume de grilles vendues. Si le biais existe, il apparaît dans
les coefficients — et il devient alors possible de construire des grilles qui,
à probabilité de gain rigoureusement identique, rapportent davantage quand elles
sortent, parce qu'on les partage avec moins de monde.

Deux modèles distincts, parce que deux biais distincts :

* :func:`fit` mesure le biais sur les **cinq boules**, via le rang « 3 numéros » ;
* :func:`fit_chance` mesure le biais sur le **numéro chance**, via le rang
  « n° chance seul » rapporté au rang « 2 numéros » — lequel ne dépend pas du
  numéro chance et sert donc de témoin de volume parfaitement propre.

Le second est le plus violent des deux : quand le 7 sort, il y a moitié plus de
gagnants à se partager la cagnotte que lorsque c'est le 1 ou le 10.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass

from .model import BALL_MAX, BALL_MIN, BALLS_DRAWN, CHANCE_MAX, CHANCE_MIN, Draw
from .stats import consecutive_pairs, shape_stats

#: Rang servant de réponse au modèle des boules : « 3 numéros », assez fréquent
#: pour être peu bruité et indépendant du numéro chance.
RESPONSE_RANK = 6
#: Témoin de volume du modèle des boules : « n° chance seul », qui ne dépend pas
#: des boules tirées. Il dépend en revanche du numéro chance, d'où la correction
#: appliquée par :meth:`ChanceModel.log_popularity`.
VOLUME_RANK = 9

#: Rang servant de réponse au modèle du numéro chance : « n° chance seul ».
CHANCE_RESPONSE_RANK = 9
#: Témoin de volume du modèle du numéro chance : « 2 numéros », qui ne dépend
#: pas du numéro chance tiré.
CHANCE_VOLUME_RANK = 8

FEATURE_LABELS = (
    "constante",
    "log(volume de grilles jouées)",
    "numéros ≤ 31 (biais date de naissance)",
    "numéros ≤ 12 (biais mois de naissance)",
    "paires de numéros consécutifs",
    "somme de la combinaison (centrée)",
)


# --------------------------------------------------------------------------
# Moindres carrés ordinaires, sans dépendance externe
# --------------------------------------------------------------------------


def _solve(matrix: list[list[float]], vector: list[float]) -> tuple[list[float], list[list[float]]]:
    """Résout un système linéaire et renvoie aussi l'inverse de la matrice.

    Élimination de Gauss-Jordan avec pivot partiel ; les matrices en jeu font au
    plus six colonnes, la stabilité numérique n'est pas un enjeu ici.
    """
    size = len(matrix)
    augmented = [row[:] + [1.0 if i == j else 0.0 for j in range(size)] + [vector[i]]
                 for i, row in enumerate(matrix)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda r: abs(augmented[r][column]))
        if abs(augmented[pivot][column]) < 1e-12:
            raise ValueError("matrice singulière : variables colinéaires")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [value / divisor for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            if factor:
                augmented[row] = [
                    value - factor * pivot_value
                    for value, pivot_value in zip(augmented[row], augmented[column], strict=True)
                ]
    solution = [augmented[i][-1] for i in range(size)]
    inverse = [augmented[i][size:size * 2] for i in range(size)]
    return solution, inverse


@dataclass(frozen=True)
class Coefficient:
    name: str
    value: float
    standard_error: float

    @property
    def t_stat(self) -> float:
        return self.value / self.standard_error if self.standard_error else 0.0

    @property
    def significant(self) -> bool:
        return abs(self.t_stat) > 2.0

    @property
    def effect_percent(self) -> float:
        """Effet multiplicatif d'une unité, en pourcentage de gagnants en plus."""
        return 100.0 * (math.exp(self.value) - 1.0)


@dataclass
class CrowdModel:
    """Régression ajustée du nombre de gagnants sur la forme de la combinaison."""

    coefficients: list[Coefficient]
    observations: int
    r_squared: float
    response_rank: int
    period: str
    #: Vrai si le témoin de volume a été corrigé de la popularité du n° chance.
    chance_corrected: bool = False

    @property
    def date_bias(self) -> Coefficient:
        return self.coefficients[2]

    @property
    def is_credible(self) -> bool:
        return self.observations >= 200 and self.date_bias.significant

    def score(self, balls: Sequence[int]) -> float:
        """Nombre relatif de co-gagnants attendu (1 = grille moyenne)."""
        features = grid_features(balls)
        reference = _reference_features()
        exponent = sum(
            coefficient.value * (feature - baseline)
            for coefficient, feature, baseline in zip(
                self.coefficients[2:], features, reference, strict=True
            )
        )
        return math.exp(exponent)

    def payout_multiplier(self, balls: Sequence[int]) -> float:
        """Gain relatif attendu quand la grille sort (1 = grille moyenne)."""
        score = self.score(balls)
        return 1.0 / score if score else 1.0


def grid_features(balls: Sequence[int]) -> tuple[float, ...]:
    """Variables explicatives d'une combinaison (hors constante et volume)."""
    ordered = sorted(balls)
    return (
        float(sum(1 for b in ordered if b <= 31)),
        float(sum(1 for b in ordered if b <= 12)),
        float(consecutive_pairs(ordered)),
        (sum(ordered) - 125.0) / 25.0,
    )


def _reference_features() -> tuple[float, ...]:
    """Valeurs moyennes des variables pour une combinaison tirée au hasard."""
    adjacent_pairs = (BALL_MAX - 1) * math.comb(BALL_MAX - 2, BALLS_DRAWN - 2) / math.comb(
        BALL_MAX, BALLS_DRAWN
    )
    return (
        BALLS_DRAWN * 31 / BALL_MAX,
        BALLS_DRAWN * 12 / BALL_MAX,
        adjacent_pairs,
        0.0,
    )


def fit(
    draws: Sequence[Draw],
    *,
    response_rank: int = RESPONSE_RANK,
    volume_rank: int = VOLUME_RANK,
    chance_model: ChanceModel | None = None,
) -> CrowdModel:
    """Ajuste le modèle des boules sur les tirages ayant les effectifs voulus.

    ``chance_model`` corrige le témoin de volume : le nombre de gagnants au rang
    « n° chance seul » dépend du numéro chance tiré autant que du nombre de
    grilles jouées. Sans cette correction, le régresseur est entaché d'une
    erreur de mesure qui atténue *tous* les coefficients — le biais des dates de
    naissance est alors sous-estimé, pas surestimé.
    """
    rows: list[list[float]] = []
    response: list[float] = []
    used: list[Draw] = []

    for draw in draws:
        winners = draw.ranks.get(response_rank, (0, 0.0))[0]
        volume = draw.ranks.get(volume_rank, (0, 0.0))[0]
        if winners <= 0 or volume <= 0:
            continue
        log_volume = math.log(volume)
        if chance_model is not None and draw.chance is not None:
            log_volume -= chance_model.log_popularity(draw.chance)
        rows.append([1.0, log_volume, *grid_features(draw.balls)])
        response.append(math.log(winners))
        used.append(draw)

    if len(rows) < 50:
        raise ValueError("pas assez de tirages avec effectifs de gagnants exploitables")

    width = len(rows[0])
    xtx = [[sum(row[i] * row[j] for row in rows) for j in range(width)] for i in range(width)]
    xty = [sum(row[i] * y for row, y in zip(rows, response, strict=True)) for i in range(width)]
    beta, inverse = _solve(xtx, xty)

    fitted = [sum(b * value for b, value in zip(beta, row, strict=True)) for row in rows]
    residuals = [y - f for y, f in zip(response, fitted, strict=True)]
    mean_response = sum(response) / len(response)
    rss = sum(r * r for r in residuals)
    tss = sum((y - mean_response) ** 2 for y in response)
    sigma2 = rss / max(1, len(rows) - width)

    coefficients = [
        Coefficient(FEATURE_LABELS[i], beta[i], math.sqrt(max(sigma2 * inverse[i][i], 0.0)))
        for i in range(width)
    ]
    return CrowdModel(
        coefficients=coefficients,
        observations=len(rows),
        r_squared=1.0 - rss / tss if tss else 0.0,
        response_rank=response_rank,
        period=f"{used[0].date.isoformat()} → {used[-1].date.isoformat()}",
        chance_corrected=chance_model is not None,
    )


# --------------------------------------------------------------------------
# Le biais du numéro chance
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ChanceEffect:
    """Popularité d'un numéro chance, relative au numéro chance moyen."""

    number: int
    log_effect: float
    standard_error: float

    @property
    def t_stat(self) -> float:
        return self.log_effect / self.standard_error if self.standard_error else 0.0

    @property
    def significant(self) -> bool:
        return abs(self.t_stat) > 2.0

    @property
    def popularity(self) -> float:
        """Nombre relatif de co-gagnants (1 = numéro chance moyen)."""
        return math.exp(self.log_effect)

    @property
    def effect_percent(self) -> float:
        return 100.0 * (self.popularity - 1.0)

    @property
    def payout_multiplier(self) -> float:
        return 1.0 / self.popularity if self.popularity else 1.0


@dataclass
class ChanceModel:
    """Popularité mesurée de chacun des dix numéros chance."""

    effects: list[ChanceEffect]
    observations: int
    r_squared: float
    period: str

    def _by_number(self, number: int) -> ChanceEffect | None:
        return next((e for e in self.effects if e.number == number), None)

    def log_popularity(self, number: int) -> float:
        effect = self._by_number(number)
        return effect.log_effect if effect else 0.0

    def popularity(self, number: int) -> float:
        return math.exp(self.log_popularity(number))

    def payout_multiplier(self, number: int) -> float:
        value = self.popularity(number)
        return 1.0 / value if value else 1.0

    @property
    def most_popular(self) -> ChanceEffect:
        return max(self.effects, key=lambda e: e.log_effect)

    @property
    def least_popular(self) -> ChanceEffect:
        return min(self.effects, key=lambda e: e.log_effect)

    @property
    def spread_percent(self) -> float:
        """Écart de gain entre le meilleur et le pire numéro chance à jouer."""
        return 100.0 * (self.most_popular.popularity / self.least_popular.popularity - 1.0)

    @property
    def is_credible(self) -> bool:
        return self.observations >= 200 and self.least_popular.significant


def fit_chance(
    draws: Sequence[Draw],
    *,
    response_rank: int = CHANCE_RESPONSE_RANK,
    volume_rank: int = CHANCE_VOLUME_RANK,
) -> ChanceModel:
    """Mesure la popularité de chaque numéro chance, volume de jeu neutralisé.

    Modèle : ``log(gagnants au rang « n° chance seul »)`` régressé sur
    ``log(gagnants au rang « 2 numéros »)`` et dix indicatrices, une par numéro
    chance, sans constante. Le rang témoin ne dépendant pas du numéro chance,
    tout écart entre indicatrices ne peut venir que des joueurs eux-mêmes.

    Les effets sont ensuite recentrés sur leur propre moyenne, avec des erreurs
    types calculées sur le contraste — et non sur le niveau brut, qui n'aurait
    aucune interprétation.
    """
    numbers = list(range(CHANCE_MIN, CHANCE_MAX + 1))
    rows: list[list[float]] = []
    response: list[float] = []
    used: list[Draw] = []

    for draw in draws:
        if draw.chance not in numbers:
            continue
        winners = draw.ranks.get(response_rank, (0, 0.0))[0]
        volume = draw.ranks.get(volume_rank, (0, 0.0))[0]
        if winners <= 0 or volume <= 0:
            continue
        dummies = [1.0 if draw.chance == n else 0.0 for n in numbers]
        rows.append([math.log(volume), *dummies])
        response.append(math.log(winners))
        used.append(draw)

    if len(rows) < 100:
        raise ValueError("pas assez de tirages pour mesurer le biais du numero chance")

    width = len(rows[0])
    xtx = [[sum(r[i] * r[j] for r in rows) for j in range(width)] for i in range(width)]
    xty = [sum(r[i] * y for r, y in zip(rows, response, strict=True)) for i in range(width)]
    beta, inverse = _solve(xtx, xty)

    fitted = [sum(b * v for b, v in zip(beta, row, strict=True)) for row in rows]
    residuals = [y - f for y, f in zip(response, fitted, strict=True)]
    mean_response = sum(response) / len(response)
    rss = sum(r * r for r in residuals)
    tss = sum((y - mean_response) ** 2 for y in response)
    sigma2 = rss / max(1, len(rows) - width)

    levels = beta[1:]
    grand_mean = sum(levels) / len(levels)
    effects: list[ChanceEffect] = []
    for index, number in enumerate(numbers):
        # Contraste « ce numéro contre la moyenne des dix » : var = sigma2 v'(X'X)^-1 v
        contrast = [0.0] * width
        for j in range(len(numbers)):
            contrast[1 + j] = (1.0 if j == index else 0.0) - 1.0 / len(numbers)
        variance = sigma2 * sum(
            contrast[i] * inverse[i][j] * contrast[j]
            for i in range(width) for j in range(width)
            if contrast[i] and contrast[j]
        )
        effects.append(ChanceEffect(
            number=number,
            log_effect=levels[index] - grand_mean,
            standard_error=math.sqrt(max(variance, 0.0)),
        ))

    return ChanceModel(
        effects=effects,
        observations=len(rows),
        r_squared=1.0 - rss / tss if tss else 0.0,
        period=f"{used[0].date.isoformat()} → {used[-1].date.isoformat()}",
    )


# --------------------------------------------------------------------------
# Génération de grilles à contre-courant
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ContrarianGrid:
    """Une grille choisie pour être partagée avec le moins de monde possible."""

    balls: tuple[int, ...]
    chance: int
    #: Co-gagnants relatifs dus aux cinq boules (1 = grille moyenne).
    crowd_score: float
    #: Co-gagnants relatifs dus au seul numéro chance (1 = numéro moyen).
    chance_score: float = 1.0

    @property
    def combination(self) -> str:
        return "-".join(f"{b:02d}" for b in self.balls) + f" + {self.chance}"

    @property
    def payout_multiplier(self) -> float:
        """Gain relatif aux rangs qui ne dépendent que des boules (2, 4, 6, 8)."""
        return 1.0 / self.crowd_score if self.crowd_score else 1.0

    @property
    def payout_multiplier_with_chance(self) -> float:
        """Gain relatif aux rangs qui font aussi intervenir le n° chance."""
        combined = self.crowd_score * self.chance_score
        return 1.0 / combined if combined else 1.0

    @property
    def gain_percent(self) -> float:
        return 100.0 * (self.payout_multiplier - 1.0)

    @property
    def gain_percent_with_chance(self) -> float:
        return 100.0 * (self.payout_multiplier_with_chance - 1.0)


def contrarian_grids(
    model: CrowdModel,
    draws: Sequence[Draw],
    *,
    count: int = 5,
    candidates: int = 40000,
    seed: int | str = 0,
    realistic: bool = True,
    chance_model: ChanceModel | None = None,
) -> list[ContrarianGrid]:
    """Grilles minimisant le nombre attendu de co-gagnants.

    ``realistic=True`` contraint la somme des numéros à rester dans la plage
    centrale observée historiquement : sans cette contrainte l'optimum est la
    grille 45-46-47-48-49, imbattable sur le papier mais si extrême qu'elle
    finit elle-même par attirer les joueurs contrariants.

    ``chance_model`` fait choisir le numéro chance le moins joué au lieu de le
    tirer au hasard — c'est, à lui seul, le gain le plus important.
    """
    profile = shape_stats(draws[-600:] or draws)
    rng = random.Random(f"contrarian:{seed}")
    universe = list(range(BALL_MIN, BALL_MAX + 1))
    pool: list[tuple[float, tuple[int, ...]]] = []

    for _ in range(candidates):
        grid = tuple(sorted(rng.sample(universe, BALLS_DRAWN)))
        if realistic:
            total = sum(grid)
            if not (profile.sum_p10 <= total <= profile.sum_p90):
                continue
            if consecutive_pairs(grid) > 1:
                continue
        pool.append((model.score(grid), grid))

    pool.sort(key=lambda item: item[0])

    # Les numéros chance les moins joués, du meilleur au moins bon. À défaut de
    # modèle, on retombe sur un tirage au sort.
    if chance_model is not None:
        ranked_chances = [e.number for e in sorted(chance_model.effects,
                                                   key=lambda e: e.log_effect)]
    else:
        ranked_chances = rng.sample(range(CHANCE_MIN, CHANCE_MAX + 1), CHANCE_MAX)

    selected: list[ContrarianGrid] = []
    for score, grid in pool:
        # On évite de proposer cinq quasi-clones de la même grille.
        if any(len(set(grid) & set(existing.balls)) > 2 for existing in selected):
            continue
        chance = ranked_chances[len(selected) % len(ranked_chances)]
        selected.append(ContrarianGrid(
            balls=grid,
            chance=chance,
            crowd_score=score,
            chance_score=chance_model.popularity(chance) if chance_model else 1.0,
        ))
        if len(selected) >= count:
            break
    return selected
