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
    """Prochain jour de tirage strictement postérieur à ``after``.

    Ne tient pas compte des tirages exceptionnels (Grand Loto, vendredi 13),
    qui s'ajoutent au calendrier régulier sans jamais le remplacer.
    """
    day = after + timedelta(days=1)
    while day.weekday() not in DRAW_WEEKDAYS:
        day += timedelta(days=1)
    return day


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
    fdj_id: str = ""
    source: str = ""
    #: rang → (nombre de gagnants, rapport en euros)
    ranks: dict[int, tuple[int, float]] = field(default_factory=dict, compare=False)

    @property
    def is_modern(self) -> bool:
        return self.era == ERA_MODERN

    @property
    def combination(self) -> str:
        core = "-".join(f"{b:02d}" for b in self.balls)
        return f"{core}+{self.chance}" if self.chance is not None else core

    def matches(self, grid: tuple[int, ...], chance: int | None = None) -> tuple[int, bool]:
        """Compte les numéros communs avec ``grid`` et teste le n° chance."""
        hits = len(set(grid) & set(self.balls))
        return hits, chance is not None and chance == self.chance
