"""Backtest « walk-forward » : le module qui dit la vérité.

Le principe est celui d'une simulation honnête. Pour chaque tirage historique,
on ne montre à la stratégie que les tirages qui le précèdent, on lui fait
produire une grille, puis on compte ce qu'elle aurait réellement gagné. Aucune
information future ne fuit vers le passé.

Le résultat attendu — et systématiquement observé — est qu'aucune stratégie ne
se distingue du hasard pur au-delà du bruit d'échantillonnage. C'est le cœur du
projet : le démontrer plutôt que l'affirmer.

La comparaison au hasard prend deux précautions, sans lesquelles ce module
fabriquerait de faux signaux :

* **appariement** — les grilles jouées sur un même tirage partagent la même
  cible et ne sont donc pas indépendantes. On agrège d'abord par tirage, puis on
  teste la différence appariée avec le témoin. Traiter les grilles comme
  indépendantes gonflerait artificiellement le nombre d'observations ;
* **tests multiples** — trois stratégies comparées au témoin, c'est trois chances
  de tomber sur un p < 0,05 par pur hasard. La correction de Holm-Bonferroni s'en
  charge.
"""

from __future__ import annotations

import math
import random
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

from .model import BALLS_DRAWN, GRID_PRICE, Draw, rank_of
from .predictors import (
    ALL_BALLS,
    ALL_CHANCES,
    DEFAULT_WINDOW,
    STRATEGIES,
    Strategy,
    _chance_weights,
    _shape_penalty,
    _weighted_sample,
)
from .stats import shape_stats


def normal_sf(z: float) -> float:
    """Probabilité de queue supérieure de la loi normale centrée réduite."""
    return 0.5 * math.erfc(z / math.sqrt(2.0))


@dataclass
class StrategyResult:
    """Bilan d'une stratégie sur l'ensemble de la période testée."""

    key: str
    label: str
    grids: int = 0
    matches: list[int] = field(default_factory=list, repr=False)
    #: Une observation par tirage : la moyenne des grilles jouées sur ce tirage.
    #: C'est l'unité statistique valide, la grille ne l'étant pas.
    per_draw: list[float] = field(default_factory=list, repr=False)
    chance_hits: int = 0
    rank_hits: Counter = field(default_factory=Counter)
    winnings: float = 0.0
    #: Comparaison appariée au hasard pur, renseignée après coup.
    z_score: float = 0.0
    p_value: float = 1.0
    #: p-value corrigée de la multiplicité des tests (Holm-Bonferroni).
    p_value_holm: float = 1.0

    @property
    def stake(self) -> float:
        return self.grids * GRID_PRICE

    @property
    def mean_matches(self) -> float:
        return sum(self.matches) / len(self.matches) if self.matches else 0.0

    @property
    def match_histogram(self) -> dict[int, int]:
        histogram = Counter(self.matches)
        return {k: histogram.get(k, 0) for k in range(BALLS_DRAWN + 1)}

    @property
    def winning_grids(self) -> int:
        return sum(self.rank_hits.values())

    @property
    def hit_rate(self) -> float:
        return self.winning_grids / self.grids if self.grids else 0.0

    @property
    def roi(self) -> float:
        """Retour sur mise, en pourcentage (-100 % = tout perdu)."""
        return 100.0 * (self.winnings - self.stake) / self.stake if self.stake else 0.0

    @property
    def verdict(self) -> str:
        if self.p_value_holm >= 0.05:
            return "indiscernable du hasard"
        return "écart au hasard résistant à la correction de Holm"


@dataclass
class BacktestReport:
    first_date: str
    last_date: str
    draws_tested: int
    repeats: int
    results: list[StrategyResult]

    @property
    def best_by_roi(self) -> StrategyResult:
        return max(self.results, key=lambda r: r.roi)

    @property
    def any_significant(self) -> bool:
        """Une stratégie survit-elle à la correction pour tests multiples ?"""
        return any(r.p_value_holm < 0.05 for r in self.results if r.key != "uniforme")


def _sample_grid(
    strategy: Strategy,
    weights: dict[int, float],
    profile,
    rng: random.Random,
) -> tuple[int, ...]:
    best: tuple[int, ...] = ()
    best_score = math.inf
    for _ in range(max(1, strategy.candidates)):
        candidate = _weighted_sample(ALL_BALLS, weights, BALLS_DRAWN, rng)
        score = _shape_penalty(candidate, profile) if profile is not None else 0.0
        if score < best_score:
            best, best_score = candidate, score
    return best


def run(
    draws: Sequence[Draw],
    *,
    strategies: Sequence[Strategy] = STRATEGIES,
    window: int = 400,
    warmup: int = DEFAULT_WINDOW,
    repeats: int = 3,
) -> BacktestReport:
    """Rejoue les ``window`` derniers tirages, ``repeats`` grilles par stratégie.

    ``warmup`` est le nombre minimum de tirages d'historique exigé avant de
    commencer à jouer : sans lui, les premières grilles seraient calculées sur
    un échantillon dérisoire.
    """
    if len(draws) <= warmup + 1:
        raise ValueError("historique trop court pour un backtest")

    start = max(warmup, len(draws) - window)
    results = {s.key: StrategyResult(s.key, s.label) for s in strategies}

    for index in range(start, len(draws)):
        history = draws[:index]
        target = draws[index]
        for strategy in strategies:
            weights = strategy.weigh(history)
            chance_weights = _chance_weights(history, strategy.chance_mode)
            profile = (
                shape_stats(history[-DEFAULT_WINDOW:] or history)
                if strategy.candidates > 1 else None
            )
            rng = random.Random(f"{strategy.key}:{target.date.isoformat()}")
            result = results[strategy.key]
            draw_matches: list[int] = []
            for _ in range(repeats):
                grid = _sample_grid(strategy, weights, profile, rng)
                chance = _weighted_sample(ALL_CHANCES, chance_weights, 1, rng)[0]
                hits, chance_hit = target.matches(grid, chance)
                result.grids += 1
                result.matches.append(hits)
                draw_matches.append(hits)
                result.chance_hits += int(chance_hit)
                rank = rank_of(hits, chance_hit)
                if rank is not None:
                    result.rank_hits[rank] += 1
                    result.winnings += target.ranks.get(rank, (0, 0.0))[1]
            result.per_draw.append(sum(draw_matches) / len(draw_matches))

    ordered = [results[s.key] for s in strategies]
    _compare_to_random(ordered)
    return BacktestReport(
        first_date=draws[start].date.isoformat(),
        last_date=draws[-1].date.isoformat(),
        draws_tested=len(draws) - start,
        repeats=repeats,
        results=ordered,
    )


def _variance(values: Sequence[int], mean: float) -> float:
    if len(values) < 2:
        return 0.0
    return sum((v - mean) ** 2 for v in values) / (len(values) - 1)


def _compare_to_random(results: Sequence[StrategyResult]) -> None:
    """Test apparié de chaque stratégie contre le témoin « hasard pur ».

    On compare tirage par tirage — même cible, même jour — puis on corrige les
    p-values de la multiplicité des comparaisons. L'approximation normale de la
    loi de Student est employée ; elle est excellente au-delà de cent tirages,
    ce que le rodage impose de toute façon.
    """
    baseline = next((r for r in results if r.key == "uniforme"), None)
    if baseline is None or len(baseline.per_draw) < 2:
        return

    tested: list[StrategyResult] = []
    for result in results:
        if result is baseline or len(result.per_draw) != len(baseline.per_draw):
            continue
        differences = [
            mine - theirs
            for mine, theirs in zip(result.per_draw, baseline.per_draw, strict=True)
        ]
        mean = sum(differences) / len(differences)
        variance = _variance(differences, mean)
        standard_error = math.sqrt(variance / len(differences)) if variance else 0.0
        if standard_error == 0:
            result.z_score, result.p_value = 0.0, 1.0
        else:
            result.z_score = mean / standard_error
            result.p_value = 2.0 * normal_sf(abs(result.z_score))
        tested.append(result)

    _holm(tested)


def _holm(results: Sequence[StrategyResult]) -> None:
    """Correction de Holm-Bonferroni, appliquée en place.

    Les p-values sont triées par ordre croissant et multipliées par le nombre de
    tests restants ; la suite est ensuite rendue monotone. Plus puissante que
    Bonferroni simple, et tout aussi rigoureuse.
    """
    ordered = sorted(results, key=lambda r: r.p_value)
    total = len(ordered)
    running = 0.0
    for rank, result in enumerate(ordered):
        adjusted = (total - rank) * result.p_value
        running = max(running, min(1.0, adjusted))
        result.p_value_holm = running
