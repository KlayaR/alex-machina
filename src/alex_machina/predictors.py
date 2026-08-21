"""Les « oracles » : quatre façons de fabriquer une grille à partir de l'historique.

Aucune de ces stratégies n'a de pouvoir prédictif, et le module
:mod:`alex_machina.backtest` est là pour le démontrer chiffres en main. Elles
formalisent en revanche proprement les intuitions que tout le monde a sur le
Loto (« les numéros chauds », « les retardataires », « les numéros qui sortent
ensemble »), ce qui permet de les tester au lieu d'y croire.

Chaque stratégie produit un vecteur de poids sur les 49 boules ; le tirage de la
grille se fait ensuite par échantillonnage pondéré sans remise, avec une graine
déterministe — deux exécutions sur le même historique donnent la même grille.

Règle intangible : **le numéro chance suit la même logique que les boules**. Une
stratégie « numéros chauds » qui tirerait son numéro chance au hasard ne serait
pas une stratégie, seulement un mélange incohérent de deux idées. Cela n'empêche
pas deux stratégies différentes de tomber sur le même numéro chance : il n'y en a
que dix, les collisions sont la règle plutôt que l'exception.

Les intuitions redondantes ont été fusionnées. « Numéros froids » et
« retardataires » disaient la même chose — des numéros qu'on n'a pas vus
récemment — avec deux mesures corrélées ; il n'en reste qu'une. De même,
« momentum » n'était qu'une version datée de « numéros chauds », et c'est
désormais la seule.
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
    """Favorise les numéros les plus sortis, le passé lointain comptant moins.

    Fréquences pondérées par récence, demi-vie de 60 tirages — soit environ cinq
    mois de Loto. Un simple comptage sur fenêtre fixe traiterait de la même façon
    un numéro sorti hier et un numéro sorti il y a deux ans.
    """
    recent = draws[-window:]
    half_life = 60.0
    raw = {n: 0.0 for n in ALL_BALLS}
    total = len(recent)
    for index, draw in enumerate(recent):
        weight = math.exp(-math.log(2) * (total - 1 - index) / half_life)
        for ball in draw.balls:
            if ball in raw:
                raw[ball] += weight
    return _normalise(raw)


def weights_cold(draws: Sequence[Draw], window: int = DEFAULT_WINDOW) -> dict[int, float]:
    """L'inverse de :func:`weights_hot`, conservé comme brique de comparaison.

    Plus utilisé par aucune stratégie : sa corrélation avec le retard mesuré par
    :func:`weights_overdue` est telle que les deux produisaient des grilles
    jumelles, présentées au lecteur comme deux méthodes distinctes.
    """
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


def weights_ensemble(draws: Sequence[Draw], window: int = DEFAULT_WINDOW) -> dict[int, float]:
    """Moyenne des trois familles de signaux, chacune ramenée à la même échelle."""
    components = [
        weights_hot(draws, window),
        weights_overdue(draws),
        weights_companion(draws, window),
    ]
    return _normalise({
        n: sum(component.get(n, 1.0) for component in components) / len(components)
        for n in ALL_BALLS
    })


def _chance_weights(draws: Sequence[Draw], mode: str) -> dict[int, float]:
    """Poids sur les dix numéros chance, selon la même logique que les boules.

    Le numéro chance n'est pas un ornement tiré à part : si une stratégie parie
    sur les numéros chauds, elle doit parier sur le numéro chance chaud. Sinon
    elle affiche une étiquette qui ne décrit pas ce qu'elle fait.
    """
    stats = chance_stats(draws)
    if mode == "hot":
        return _normalise({s.number: float(s.count) for s in stats})
    if mode == "overdue":
        return _normalise({s.number: s.gap_ratio for s in stats})
    if mode == "companion":
        # Le numéro chance sorti le plus souvent en même temps que les boules du
        # dernier tirage. À défaut de signal, cela revient aux fréquences.
        last = set(draws[-1].balls) if draws else set()
        raw = {n: 0.0 for n in ALL_CHANCES}
        for draw in draws[-DEFAULT_WINDOW:]:
            if draw.chance in raw and set(draw.balls) & last:
                raw[draw.chance] += len(set(draw.balls) & last)
        return _normalise(raw) if any(raw.values()) else {n: 1.0 for n in ALL_CHANCES}
    if mode == "ensemble":
        components = [
            _chance_weights(draws, "hot"),
            _chance_weights(draws, "overdue"),
            _chance_weights(draws, "companion"),
        ]
        return _normalise({
            n: sum(c.get(n, 1.0) for c in components) / len(components)
            for n in ALL_CHANCES
        })
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
        "Cinq numéros et un numéro chance au hasard. Le témoin scientifique : "
        "toute autre stratégie doit battre celle-ci pour valoir quoi que ce soit. "
        "Aucune n'y arrive.",
        weights_uniform, "uniform",
        rationale="Tirage uniforme, exactement comme la machine de la FDJ.",
    ),
    Strategy(
        "chauds", "Numéros chauds",
        "Les numéros qui sortent le plus, pondérés par récence : un tirage d'il y "
        "a cinq mois pèse moitié moins qu'un tirage d'hier. Numéro chance compris.",
        lambda d: weights_hot(d), "hot",
        rationale="Boules et numéro chance les plus sortis ces derniers mois.",
    ),
    Strategy(
        "retards", "Retardataires",
        "Les numéros qu'on n'a pas vus depuis anormalement longtemps, mesurés par "
        "leur écart actuel rapporté à leur écart moyen. C'est la seule version de "
        "l'idée du « rattrapage » : compter les absences ou compter les sorties "
        "rares donnait deux grilles jumelles.",
        weights_overdue, "overdue",
        rationale="Boules et numéro chance les plus en retard sur leur rythme habituel.",
    ),
    Strategy(
        "machina", "Alex Machina",
        "L'ensemble : moyenne des signaux chauds, retards et co-occurrences avec le "
        "dernier tirage, puis sélection de la grille dont la forme (somme, parité, "
        "étalement) colle le mieux au profil historique des combinaisons gagnantes.",
        lambda d: weights_ensemble(d), "ensemble", candidates=400,
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
