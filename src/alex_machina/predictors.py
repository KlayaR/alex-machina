"""Les « oracles » : sept façons de fabriquer une grille à partir de l'historique.

Aucune de ces stratégies n'a de pouvoir prédictif, et le module
:mod:`alex_machina.backtest` est là pour le démontrer chiffres en main. Elles
formalisent en revanche proprement les intuitions que tout le monde a sur le
Loto (« les numéros chauds », « les retardataires », « les numéros qui sortent
ensemble »), ce qui permet de les tester au lieu d'y croire.

Chaque stratégie produit un vecteur de poids sur les 49 boules ; le tirage de la
grille se fait ensuite par échantillonnage pondéré sans remise, avec une graine
déterministe — deux exécutions sur le même historique donnent la même grille.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from .model import BALL_MAX, BALL_MIN, BALLS_DRAWN, CHANCE_MAX, CHANCE_MIN, Draw
from .stats import ShapeStats, ball_stats, chance_stats, pair_counts, shape_stats

ALL_BALLS = tuple(range(BALL_MIN, BALL_MAX + 1))
ALL_CHANCES = tuple(range(CHANCE_MIN, CHANCE_MAX + 1))

#: Fenêtre par défaut : environ deux ans de tirages à raison de trois par semaine.
DEFAULT_WINDOW = 300


@dataclass(frozen=True)
class Prediction:
    """Une grille proposée par une stratégie."""

    strategy: str
    label: str
    balls: tuple[int, ...]
    chance: int
    rationale: str
    weights: dict[int, float] = field(default_factory=dict, repr=False)

    @property
    def combination(self) -> str:
        return "-".join(f"{b:02d}" for b in self.balls) + f" + {self.chance}"


def _weighted_sample(
    population: Sequence[int],
    weights: dict[int, float],
    k: int,
    rng: random.Random,
) -> tuple[int, ...]:
    """Échantillonnage pondéré sans remise (méthode de la roulette répétée)."""
    remaining = list(population)
    picked: list[int] = []
    for _ in range(min(k, len(remaining))):
        total = sum(max(weights.get(n, 0.0), 1e-9) for n in remaining)
        threshold = rng.random() * total
        cumulative = 0.0
        chosen = remaining[-1]
        for number in remaining:
            cumulative += max(weights.get(number, 0.0), 1e-9)
            if cumulative >= threshold:
                chosen = number
                break
        picked.append(chosen)
        remaining.remove(chosen)
    return tuple(sorted(picked))


def _normalise(raw: dict[int, float]) -> dict[int, float]:
    """Ramène des poids bruts à une moyenne de 1, en restant strictement positifs."""
    if not raw:
        return {}
    floor = min(raw.values())
    shifted = {n: v - floor + 0.05 for n, v in raw.items()}
    mean = sum(shifted.values()) / len(shifted)
    return {n: v / mean for n, v in shifted.items()} if mean else shifted


# --------------------------------------------------------------------------
# Vecteurs de poids
# --------------------------------------------------------------------------


def weights_uniform(draws: Sequence[Draw]) -> dict[int, float]:
    """Le témoin honnête : chaque boule a exactement la même chance."""
    return {n: 1.0 for n in ALL_BALLS}


def weights_hot(draws: Sequence[Draw], window: int = DEFAULT_WINDOW) -> dict[int, float]:
    """Favorise les numéros les plus sortis sur la fenêtre récente."""
    recent = draws[-window:]
    return _normalise({s.number: float(s.count) for s in ball_stats(recent)})


def weights_cold(draws: Sequence[Draw], window: int = DEFAULT_WINDOW) -> dict[int, float]:
    """L'inverse exact : parie sur un « rattrapage » des numéros peu sortis."""
    recent = draws[-window:]
    stats = ball_stats(recent)
    ceiling = max((s.count for s in stats), default=0) + 1
    return _normalise({s.number: float(ceiling - s.count) for s in stats})


def weights_overdue(draws: Sequence[Draw]) -> dict[int, float]:
    """Pondère par le retard relatif : écart actuel divisé par l'écart moyen."""
    return _normalise({s.number: s.gap_ratio for s in ball_stats(draws)})


def weights_companion(draws: Sequence[Draw], window: int = DEFAULT_WINDOW) -> dict[int, float]:
    """Poids par affinité avec les boules du dernier tirage (co-occurrences)."""
    if not draws:
        return weights_uniform(draws)
    pairs = pair_counts(draws[-window:])
    last = set(draws[-1].balls)
    raw: dict[int, float] = {}
    for number in ALL_BALLS:
        raw[number] = float(sum(
            pairs.get((min(number, other), max(number, other)), 0)
            for other in last if other != number
        ))
    return _normalise(raw)


def weights_momentum(draws: Sequence[Draw], window: int = DEFAULT_WINDOW) -> dict[int, float]:
    """Fréquences pondérées par récence : un tirage vieux compte moitié moins.

    Demi-vie fixée à 60 tirages, soit environ cinq mois de Loto.
    """
    recent = draws[-window:]
    half_life = 60.0
    raw = {n: 0.0 for n in ALL_BALLS}
    total = len(recent)
    for index, draw in enumerate(recent):
        age = total - 1 - index
        weight = math.exp(-math.log(2) * age / half_life)
        for ball in draw.balls:
            if ball in raw:
                raw[ball] += weight
    return _normalise(raw)


def weights_ensemble(draws: Sequence[Draw], window: int = DEFAULT_WINDOW) -> dict[int, float]:
    """Moyenne des quatre familles de signaux, chacune ramenée à la même échelle."""
    components = [
        weights_hot(draws, window),
        weights_overdue(draws),
        weights_companion(draws, window),
        weights_momentum(draws, window),
    ]
    return _normalise({
        n: sum(component.get(n, 1.0) for component in components) / len(components)
        for n in ALL_BALLS
    })


def _chance_weights(draws: Sequence[Draw], mode: str) -> dict[int, float]:
    stats = chance_stats(draws)
    if mode == "hot":
        return _normalise({s.number: float(s.count) for s in stats})
    if mode == "overdue":
        return _normalise({s.number: s.gap_ratio for s in stats})
    return {n: 1.0 for n in ALL_CHANCES}


# --------------------------------------------------------------------------
# Stratégies
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Strategy:
    key: str
    label: str
    description: str
    weigh: Callable[[Sequence[Draw]], dict[int, float]]
    chance_mode: str = "uniform"
    #: Nombre de grilles candidates tirées avant de garder la mieux « formée ».
    candidates: int = 1
    rationale: str = ""


def _shape_penalty(balls: Sequence[int], profile: ShapeStats) -> float:
    """Distance entre la forme d'une grille et la forme moyenne des tirages."""
    ordered = sorted(balls)
    midpoint = (BALL_MAX + 1) // 2
    odd = sum(1 for b in ordered if b % 2)
    low = sum(1 for b in ordered if b <= midpoint)
    consecutive = sum(1 for a, b in zip(ordered, ordered[1:], strict=False) if b - a == 1)
    spread = ordered[-1] - ordered[0]
    return (
        abs(sum(ordered) - profile.mean_sum) / 25.0
        + abs(odd - profile.mean_odd)
        + abs(low - profile.mean_low)
        + abs(consecutive - profile.mean_consecutive)
        + abs(spread - profile.mean_spread) / 10.0
    )


STRATEGIES: tuple[Strategy, ...] = (
    Strategy(
        "uniforme", "Hasard pur",
        "Cinq numéros au hasard. Le témoin scientifique : toute autre stratégie "
        "doit battre celle-ci pour valoir quoi que ce soit. Aucune n'y arrive.",
        weights_uniform, "uniform",
        rationale="Tirage uniforme, exactement comme la machine de la FDJ.",
    ),
    Strategy(
        "chauds", "Numéros chauds",
        "Favorise les numéros les plus sortis sur les 300 derniers tirages.",
        lambda d: weights_hot(d), "hot",
        rationale="Les numéros qui sortent le plus souvent ces deux dernières années.",
    ),
    Strategy(
        "froids", "Numéros froids",
        "L'exact opposé : privilégie les numéros les moins sortis récemment.",
        lambda d: weights_cold(d), "uniform",
        rationale="Les numéros les plus rares récemment, pour les partisans du rattrapage.",
    ),
    Strategy(
        "retards", "Retardataires",
        "Pondère par le retard relatif de chaque numéro (écart actuel / écart moyen).",
        weights_overdue, "overdue",
        rationale="Les numéros qui n'ont pas été vus depuis anormalement longtemps.",
    ),
    Strategy(
        "compagnons", "Compagnons de route",
        "Numéros qui sortent le plus souvent en compagnie de ceux du dernier tirage.",
        lambda d: weights_companion(d), "uniform",
        rationale="Affinités de co-occurrence avec la combinaison précédente.",
    ),
    Strategy(
        "momentum", "Momentum",
        "Fréquences pondérées par récence, avec une demi-vie de 60 tirages.",
        lambda d: weights_momentum(d), "hot",
        rationale="Fréquences récentes, le passé lointain comptant de moins en moins.",
    ),
    Strategy(
        "machina", "Alex Machina",
        "L'ensemble : moyenne des signaux chauds, retards, compagnons et momentum, "
        "puis sélection de la grille dont la forme (somme, parité, étalement) colle "
        "le mieux au profil historique des combinaisons gagnantes.",
        lambda d: weights_ensemble(d), "overdue", candidates=400,
        rationale="Consensus de tous les signaux, calibré sur la forme des tirages passés.",
    ),
)

STRATEGY_BY_KEY = {s.key: s for s in STRATEGIES}


def predict(
    strategy: Strategy,
    draws: Sequence[Draw],
    *,
    seed: int | str = 0,
) -> Prediction:
    """Fabrique une grille pour une stratégie donnée."""
    rng = random.Random(f"{strategy.key}:{seed}")
    weights = strategy.weigh(draws)
    chance_weights = _chance_weights(draws, strategy.chance_mode)
    profile = shape_stats(draws[-DEFAULT_WINDOW:] or draws) if strategy.candidates > 1 else None

    best: tuple[int, ...] = ()
    best_score = math.inf
    for _ in range(max(1, strategy.candidates)):
        candidate = _weighted_sample(ALL_BALLS, weights, BALLS_DRAWN, rng)
        score = _shape_penalty(candidate, profile) if profile is not None else 0.0
        if score < best_score:
            best, best_score = candidate, score

    chance = _weighted_sample(ALL_CHANCES, chance_weights, 1, rng)[0]
    return Prediction(
        strategy=strategy.key,
        label=strategy.label,
        balls=best,
        chance=chance,
        rationale=strategy.rationale,
        weights=weights,
    )


def predict_all(draws: Sequence[Draw], *, seed: int | str = 0) -> list[Prediction]:
    """Une grille par stratégie, toutes calculées sur le même historique."""
    return [predict(strategy, draws, seed=seed) for strategy in STRATEGIES]
