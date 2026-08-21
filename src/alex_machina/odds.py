"""Probabilités exactes et espérance de gain mesurée sur données réelles.

Les probabilités sont de la combinatoire pure, sans approximation. L'espérance
de gain, elle, est estimée à partir des rapports réellement versés par la FDJ
sur la période analysée : c'est la seule façon honnête de chiffrer ce que coûte
une grille, les rangs 1 à 8 étant à répartition (parimutuel) et non à gain fixe.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from .model import BALL_MAX, BALLS_DRAWN, CHANCE_MAX, GRID_PRICE, RANK_LABELS, Draw


def _combinations(n: int, k: int) -> int:
    return math.comb(n, k)


def match_probability(k: int) -> float:
    """Probabilité d'avoir exactement ``k`` bons numéros sur les 5 tirés."""
    total = _combinations(BALL_MAX, BALLS_DRAWN)
    favourable = _combinations(BALLS_DRAWN, k) * _combinations(
        BALL_MAX - BALLS_DRAWN, BALLS_DRAWN - k
    )
    return favourable / total


def rank_probability(rank: int) -> float:
    """Probabilité exacte d'atteindre un rang de gain donné, pour une grille simple."""
    chance = 1.0 / CHANCE_MAX
    table = {
        1: match_probability(5) * chance,
        2: match_probability(5) * (1 - chance),
        3: match_probability(4) * chance,
        4: match_probability(4) * (1 - chance),
        5: match_probability(3) * chance,
        6: match_probability(3) * (1 - chance),
        7: match_probability(2) * chance,
        8: match_probability(2) * (1 - chance),
        9: (match_probability(1) + match_probability(0)) * chance,
    }
    return table[rank]


def win_probability() -> float:
    """Probabilité de gagner quelque chose, ne serait-ce que le remboursement."""
    return sum(rank_probability(r) for r in RANK_LABELS)


@dataclass(frozen=True)
class RankEconomics:
    rank: int
    label: str
    probability: float
    #: Une chance sur ``odds``.
    odds: float
    mean_payout: float
    median_payout: float
    contribution: float


@dataclass(frozen=True)
class Economics:
    """Décomposition complète de l'espérance de gain d'une grille simple."""

    rows: list[RankEconomics]
    draws_used: int
    period: str

    @property
    def expected_value(self) -> float:
        return sum(row.contribution for row in self.rows)

    @property
    def house_edge(self) -> float:
        """Part de la mise qui ne revient pas au joueur, en pourcentage."""
        return 100.0 * (GRID_PRICE - self.expected_value) / GRID_PRICE

    @property
    def loss_per_grid(self) -> float:
        return GRID_PRICE - self.expected_value


def _median(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def economics(draws: Sequence[Draw]) -> Economics:
    """Espérance de gain empirique, calculée sur les rapports réels des tirages."""
    rows: list[RankEconomics] = []
    usable = [d for d in draws if d.ranks]
    for rank, label in RANK_LABELS.items():
        payouts = [d.ranks[rank][1] for d in usable if rank in d.ranks and d.ranks[rank][1] > 0]
        mean = sum(payouts) / len(payouts) if payouts else 0.0
        probability = rank_probability(rank)
        rows.append(RankEconomics(
            rank=rank,
            label=label,
            probability=probability,
            odds=1.0 / probability if probability else math.inf,
            mean_payout=mean,
            median_payout=_median(payouts),
            contribution=probability * mean,
        ))
    period = (
        f"{usable[0].date.isoformat()} → {usable[-1].date.isoformat()}"
        if usable else "aucune donnée"
    )
    return Economics(rows=rows, draws_used=len(usable), period=period)


def grids_for_certainty(probability: float, confidence: float = 0.5) -> float:
    """Nombre de grilles nécessaires pour atteindre ``confidence`` de gagner au moins une fois."""
    if probability <= 0 or probability >= 1:
        return math.inf
    return math.log(1 - confidence) / math.log(1 - probability)


def years_of_playing(probability: float, grids_per_week: int = 3) -> float:
    """Durée moyenne d'attente, en années, à raison de N grilles par semaine."""
    if probability <= 0:
        return math.inf
    return 1.0 / probability / grids_per_week / 52.0
