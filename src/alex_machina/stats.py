"""Statistiques descriptives et tests d'uniformite sur l'historique.

Tout ici est purement descriptif. Rien dans ce module n'est predictif : le test
du khi-deux sert meme exactement au contraire, mesurer a quel point les tirages
sont indiscernables d'un tirage parfaitement uniforme.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from .model import BALL_MAX, BALL_MIN, CHANCE_MAX, CHANCE_MIN, Draw

# --------------------------------------------------------------------------
# Fonctions speciales (evite une dependance a SciPy)
# --------------------------------------------------------------------------


def _gamma_p_series(a: float, x: float) -> float:
    """Gamma incomplete regularisee inferieure, par developpement en serie."""
    total = term = 1.0 / a
    for n in range(1, 1000):
        term *= x / (a + n)
        total += term
        if abs(term) < abs(total) * 1e-15:
            break
    return total * math.exp(-x + a * math.log(x) - math.lgamma(a))


def _gamma_q_continued(a: float, x: float) -> float:
    """Gamma incomplete regularisee superieure, par fraction continue."""
    tiny = 1e-300
    b = x + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / b
    h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-15:
            break
    return h * math.exp(-x + a * math.log(x) - math.lgamma(a))


def chi2_sf(statistic: float, dof: int) -> float:
    """P(X2 > statistic) pour ``dof`` degres de liberte."""
    if statistic <= 0 or dof <= 0:
        return 1.0
    a, x = dof / 2.0, statistic / 2.0
    if x < a + 1.0:
        return max(0.0, min(1.0, 1.0 - _gamma_p_series(a, x)))
    return max(0.0, min(1.0, _gamma_q_continued(a, x)))


@dataclass(frozen=True)
class ChiSquareResult:
    statistic: float
    dof: int
    p_value: float
    n: int

    @property
    def verdict(self) -> str:
        if self.p_value < 0.01:
            return "ecart significatif a l'uniformite (p < 1 %)"
        if self.p_value < 0.05:
            return "ecart modere a l'uniformite (p < 5 %)"
        return "compatible avec un tirage parfaitement uniforme"


def chi_square_uniform(counts: Sequence[int]) -> ChiSquareResult:
    """Test d'adequation a la loi uniforme sur des effectifs observes."""
    total = sum(counts)
    k = len(counts)
    if total == 0 or k < 2:
        return ChiSquareResult(0.0, 0, 1.0, 0)
    expected = total / k
    statistic = sum((c - expected) ** 2 / expected for c in counts)
    dof = k - 1
    return ChiSquareResult(statistic, dof, chi2_sf(statistic, dof), total)


# --------------------------------------------------------------------------
# Frequences et ecarts
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class NumberStats:
    """Photographie d'un numero a la fin de la periode analysee."""

    number: int
    count: int
    expected: float
    #: Nombre de tirages depuis la derniere sortie (0 = sorti au dernier tirage).
    gap: int
    max_gap: int
    mean_gap: float
    last_seen: date | None

    @property
    def deviation(self) -> float:
        """Ecart relatif a l'effectif attendu, en pourcentage."""
        return 0.0 if not self.expected else 100.0 * (self.count - self.expected) / self.expected

    @property
    def gap_ratio(self) -> float:
        """Retard actuel rapporte au retard moyen (> 1 = en retard)."""
        return 0.0 if not self.mean_gap else self.gap / self.mean_gap


def _number_stats(
    sequences: Sequence[tuple[date, Sequence[int]]],
    universe: range,
    picks_per_draw: float,
) -> list[NumberStats]:
    n_draws = len(sequences)
    counts: Counter = Counter()
    last_index: dict[int, int] = {}
    last_date: dict[int, date] = {}
    gaps: dict[int, list[int]] = defaultdict(list)

    for index, (drawn_on, numbers) in enumerate(sequences):
        for number in numbers:
            counts[number] += 1
            if number in last_index:
                gaps[number].append(index - last_index[number])
            last_index[number] = index
            last_date[number] = drawn_on

    expected = n_draws * picks_per_draw / len(universe) if n_draws else 0.0
    result: list[NumberStats] = []
    for number in universe:
        history = gaps.get(number, [])
        current = n_draws - 1 - last_index[number] if number in last_index else n_draws
        result.append(NumberStats(
            number=number,
            count=counts.get(number, 0),
            expected=expected,
            gap=current,
            max_gap=max(history + [current]) if (history or current) else 0,
            mean_gap=sum(history) / len(history) if history else float(n_draws or 1),
            last_seen=last_date.get(number),
        ))
    return result


def ball_stats(draws: Sequence[Draw]) -> list[NumberStats]:
    """Statistiques par boule (1 a 49) sur les tirages fournis."""
    sequences = [(d.date, d.balls) for d in draws]
    picks = sum(len(d.balls) for d in draws) / len(draws) if draws else 5.0
    return _number_stats(sequences, range(BALL_MIN, BALL_MAX + 1), picks)


def chance_stats(draws: Sequence[Draw]) -> list[NumberStats]:
    """Statistiques par numero chance (1 a 10)."""
    sequences = [(d.date, (d.chance,)) for d in draws if d.chance is not None]
    return _number_stats(sequences, range(CHANCE_MIN, CHANCE_MAX + 1), 1.0)


# --------------------------------------------------------------------------
# Forme des combinaisons
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ShapeStats:
    """Profil geometrique moyen d'une combinaison gagnante."""

    mean_sum: float
    sum_p10: int
    sum_p90: int
    mean_odd: float
    mean_low: float
    mean_consecutive: float
    mean_spread: float
    sum_histogram: dict[int, int]


def consecutive_pairs(balls: Sequence[int]) -> int:
    """Nombre de couples de numeros qui se suivent (12-13 compte pour un)."""
    ordered = sorted(balls)
    return sum(1 for a, b in zip(ordered, ordered[1:], strict=False) if b - a == 1)


def _percentile(values: Sequence[int], q: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
    return ordered[index]


def shape_stats(draws: Sequence[Draw]) -> ShapeStats:
    if not draws:
        return ShapeStats(0.0, 0, 0, 0.0, 0.0, 0.0, 0.0, {})
    sums = [sum(d.balls) for d in draws]
    midpoint = (BALL_MAX + 1) // 2
    histogram = Counter((s // 10) * 10 for s in sums)
    return ShapeStats(
        mean_sum=sum(sums) / len(sums),
        sum_p10=_percentile(sums, 0.10),
        sum_p90=_percentile(sums, 0.90),
        mean_odd=sum(sum(1 for b in d.balls if b % 2) for d in draws) / len(draws),
        mean_low=sum(sum(1 for b in d.balls if b <= midpoint) for d in draws) / len(draws),
        mean_consecutive=sum(consecutive_pairs(d.balls) for d in draws) / len(draws),
        mean_spread=sum(max(d.balls) - min(d.balls) for d in draws) / len(draws),
        sum_histogram=dict(sorted(histogram.items())),
    )


def pair_counts(draws: Sequence[Draw]) -> Counter:
    """Effectifs de co-occurrence pour chaque paire de boules."""
    counter: Counter = Counter()
    for draw in draws:
        ordered = sorted(draw.balls)
        for i, a in enumerate(ordered):
            for b in ordered[i + 1:]:
                counter[(a, b)] += 1
    return counter


def repeat_rate(draws: Sequence[Draw]) -> float:
    """Nombre moyen de boules repetees d'un tirage au suivant."""
    if len(draws) < 2:
        return 0.0
    repeats = [
        len(set(current.balls) & set(previous.balls))
        for previous, current in zip(draws, draws[1:], strict=False)
    ]
    return sum(repeats) / len(repeats)


def weekday_counts(draws: Sequence[Draw]) -> dict[str, int]:
    return dict(Counter(d.weekday for d in draws))
