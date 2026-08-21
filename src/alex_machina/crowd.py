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
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass

from .model import BALL_MAX, BALL_MIN, BALLS_DRAWN, Draw
from .stats import consecutive_pairs, shape_stats

#: Rang servant de réponse : « 3 numéros », assez fréquent pour être peu bruité.
RESPONSE_RANK = 6
#: Rang servant de témoin de volume : « n° chance seul », indépendant des boules.
VOLUME_RANK = 9

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
) -> CrowdModel:
    """Ajuste le modèle sur les tirages disposant des effectifs de gagnants."""
    rows: list[list[float]] = []
    response: list[float] = []
    used: list[Draw] = []

    for draw in draws:
        winners = draw.ranks.get(response_rank, (0, 0.0))[0]
        volume = draw.ranks.get(volume_rank, (0, 0.0))[0]
        if winners <= 0 or volume <= 0:
            continue
        rows.append([1.0, math.log(volume), *grid_features(draw.balls)])
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
    )


# --------------------------------------------------------------------------
# Génération de grilles à contre-courant
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ContrarianGrid:
    balls: tuple[int, ...]
    chance: int
    crowd_score: float
    payout_multiplier: float

    @property
    def combination(self) -> str:
        return "-".join(f"{b:02d}" for b in self.balls) + f" + {self.chance}"

    @property
    def gain_percent(self) -> float:
        return 100.0 * (self.payout_multiplier - 1.0)


def contrarian_grids(
    model: CrowdModel,
    draws: Sequence[Draw],
    *,
    count: int = 5,
    candidates: int = 40000,
    seed: int | str = 0,
    realistic: bool = True,
) -> list[ContrarianGrid]:
    """Grilles minimisant le nombre attendu de co-gagnants.

    ``realistic=True`` contraint la somme des numéros à rester dans la plage
    centrale observée historiquement : sans cette contrainte l'optimum est la
    grille 45-46-47-48-49, imbattable sur le papier mais si extrême qu'elle
    finit elle-même par attirer les joueurs contrariants.
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

    selected: list[ContrarianGrid] = []
    for score, grid in pool:
        # On évite de proposer cinq quasi-clones de la même grille.
        if any(len(set(grid) & set(existing.balls)) > 2 for existing in selected):
            continue
        selected.append(ContrarianGrid(
            balls=grid,
            chance=rng.randint(1, 10),
            crowd_score=score,
            payout_multiplier=1.0 / score if score else 1.0,
        ))
        if len(selected) >= count:
            break
    return selected
