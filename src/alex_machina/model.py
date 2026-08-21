"""Modèle de données commun et règles du jeu."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

BALL_MIN = 1
BALL_MAX = 49
BALLS_DRAWN = 5
CHANCE_MIN = 1
CHANCE_MAX = 10

#: Ère courante : 5 boules sur 49 + 1 numéro chance sur 10 (depuis le 06/10/2008).
ERA_MODERN = "5/49"
#: Ère historique : 6 boules sur 49 + 1 complémentaire (19/05/1976 → 04/10/2008).
ERA_LEGACY = "6/49"
ERAS = (ERA_MODERN, ERA_LEGACY)

#: Nombre de boules tirées selon l'ère. Mélanger les deux dans une même
#: statistique produit des chiffres qui ne veulent rien dire : toutes les
#: analyses portent sur une seule ère à la fois.
BALLS_BY_ERA = {ERA_MODERN: 5, ERA_LEGACY: 6}

#: Tirage du calendrier régulier (lundi, mercredi, samedi).
KIND_REGULAR = "regulier"
#: Super Loto, Grand Loto, Loto de Noël : tirages en supplément du calendrier,
#: avec leurs propres cagnottes et leurs propres volumes de jeu.
KIND_SPECIAL = "exceptionnel"


def balls_drawn(era: str) -> int:
    return BALLS_BY_ERA.get(era, BALLS_DRAWN)


def expected_repeat(era: str) -> float:
    """Nombre moyen de boules reportées d'un tirage au suivant, en théorie.

    Pour k boules tirées parmi n, l'espérance vaut k²/n : 0,51 en 5/49 et 0,73
    en 6/49. C'est la valeur de référence à laquelle comparer l'observation.
    """
    k = balls_drawn(era)
    return k * k / BALL_MAX

#: Prix d'une grille simple, en euros.
GRID_PRICE = 2.20

#: Libellé des neuf rangs de gain du Loto actuel.
RANK_LABELS: dict[int, str] = {
    1: "5 numéros + n° chance",
    2: "5 numéros",
    3: "4 numéros + n° chance",
    4: "4 numéros",
    5: "3 numéros + n° chance",
    6: "3 numéros",
    7: "2 numéros + n° chance",
    8: "2 numéros",
    9: "n° chance seul",
}


#: Jours de tirage depuis novembre 2019 : lundi, mercredi et samedi.
DRAW_WEEKDAYS = (0, 2, 5)

WEEKDAY_NAMES = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")

MONTH_NAMES = (
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
)


def next_draw_date(after: date) -> date:
    """Prochain tirage régulier strictement postérieur à ``after``.

    Les tirages exceptionnels (Super Loto, Grand Loto, Loto de Noël) s'ajoutent
    au calendrier sans jamais le remplacer : sur les 71 tirages exceptionnels
    de l'ère actuelle, aucun n'est tombé un lundi, un mercredi ou un samedi.
    Cette fonction reste donc exacte, mais un tirage exceptionnel peut
    s'intercaler avant la date qu'elle renvoie — voir :func:`next_friday_13`.
    """
    day = after + timedelta(days=1)
    while day.weekday() not in DRAW_WEEKDAYS:
        day += timedelta(days=1)
    return day


def next_friday_13(after: date, *, horizon_days: int = 400) -> date | None:
    """Prochain vendredi 13 après ``after``, ou ``None`` au-delà de l'horizon.

    Ce n'est pas une règle officielle mais une régularité solide : depuis
    juillet 2019, les treize vendredis 13 ont tous donné lieu à un Super Loto.
    Les autres tirages exceptionnels (Halloween, Noël, Saint-Valentin) ne sont
    annoncés qu'au coup par coup et restent, eux, imprévisibles.
    """
    day = after + timedelta(days=1)
    for _ in range(horizon_days):
        if day.day == 13 and day.weekday() == 4:
            return day
        day += timedelta(days=1)
    return None


def format_date(value: date) -> str:
    """Date en toutes lettres, à la française."""
    return f"{WEEKDAY_NAMES[value.weekday()]} {value.day} {MONTH_NAMES[value.month - 1]} {value.year}"


def rank_of(matches: int, chance_hit: bool) -> int | None:
    """Rang de gain pour ``matches`` bons numéros et le n° chance ou non.

    Renvoie ``None`` pour une grille perdante.
    """
    if matches == 5:
        return 1 if chance_hit else 2
    if matches == 4:
        return 3 if chance_hit else 4
    if matches == 3:
        return 5 if chance_hit else 6
    if matches == 2:
        return 7 if chance_hit else 8
    return 9 if chance_hit else None


@dataclass(frozen=True)
class Draw:
    """Un tirage normalisé, toutes ères confondues."""

    draw_id: str
    date: date
    weekday: str
    era: str
    balls: tuple[int, ...]
    chance: int | None = None
    complementaire: int | None = None
    #: ``KIND_REGULAR`` ou ``KIND_SPECIAL``.
    kind: str = KIND_REGULAR
    fdj_id: str = ""
    source: str = ""
    #: rang → (nombre de gagnants, rapport en euros)
    ranks: dict[int, tuple[int, float]] = field(default_factory=dict, compare=False)

    @property
    def is_modern(self) -> bool:
        return self.era == ERA_MODERN

    @property
    def is_regular(self) -> bool:
        return self.kind == KIND_REGULAR

    @property
    def combination(self) -> str:
        core = "-".join(f"{b:02d}" for b in self.balls)
        return f"{core}+{self.chance}" if self.chance is not None else core

    def matches(self, grid: tuple[int, ...], chance: int | None = None) -> tuple[int, bool]:
        """Compte les numéros communs avec ``grid`` et teste le n° chance."""
        hits = len(set(grid) & set(self.balls))
        return hits, chance is not None and chance == self.chance
