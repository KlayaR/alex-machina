import math
import random
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from alex_machina.model import ERA_MODERN, KIND_REGULAR, Draw  # noqa: E402


def make_draw(day: date, balls, chance, *, ranks=None, sequence=1, kind=KIND_REGULAR) -> Draw:
    return Draw(
        draw_id=f"{day.isoformat()}#{sequence}",
        date=day,
        weekday="samedi",
        era=ERA_MODERN,
        balls=tuple(sorted(balls)),
        chance=chance,
        kind=kind,
        fdj_id="test",
        source="test",
        ranks=ranks or {},
    )


@pytest.fixture
def synthetic_draws() -> list[Draw]:
    """500 tirages parfaitement uniformes, avec des rapports plausibles."""
    rng = random.Random(1234)
    start = date(2020, 1, 4)
    draws = []
    for index in range(500):
        balls = rng.sample(range(1, 50), 5)
        chance = rng.randint(1, 10)
        ranks = {
            1: (0, 3_000_000.0),
            2: (1, 90_000.0),
            3: (30, 1_200.0),
            4: (300, 250.0),
            5: (2_000, 30.0),
            6: (18_000, 12.0),
            7: (30_000, 10.0),
            8: (200_000, 4.5),
            9: (380_000, 2.2),
        }
        draws.append(make_draw(start + timedelta(days=index * 2), balls, chance, ranks=ranks))
    return draws


def _history(*, chance_bias, date_bias, seed, n=600) -> list[Draw]:
    """Fabrique un historique dont on connait exactement les biais."""
    rng = random.Random(seed)
    start = date(2019, 1, 5)
    draws = []
    for index in range(n):
        balls = rng.sample(range(1, 50), 5)
        chance = rng.randint(1, 10)
        volume = rng.randint(300_000, 600_000)
        low = sum(1 for b in balls if b <= 31)

        # Rang 8 : depend des boules mais jamais du numero chance.
        rank8 = volume / 16.0
        # Rang 6 : sensible au biais des dates de naissance.
        rank6 = math.exp(math.log(volume) + date_bias * low) / 250.0
        # Rang 9 : sensible au seul biais du numero chance.
        rank9 = volume / 10.8 * math.exp(chance_bias.get(chance, 0.0))

        draws.append(make_draw(
            start + timedelta(days=index * 2), balls, chance,
            ranks={
                6: (max(1, int(rank6)), 12.0),
                8: (max(1, int(rank8)), 4.5),
                9: (max(1, int(rank9)), 2.2),
            },
        ))
    return draws


@pytest.fixture
def unbiased_draws() -> list[Draw]:
    """Meme generateur, mais sans aucun biais a trouver."""
    return _history(chance_bias={}, date_bias=0.0, seed=99)


@pytest.fixture
def biased_draws() -> list[Draw]:
    """Historique fabriqué avec deux biais connus, à retrouver par régression.

    Les boules ≤ 31 attirent 20 % de co-gagnants en plus par numéro, et le
    numéro chance 7 en attire 50 % de plus que la moyenne. Ce sont les ordres de
    grandeur réellement observés chez la FDJ, ce qui rend le test représentatif.
    """
    return _history(
        chance_bias={7: 0.40, 5: 0.15, 1: -0.25, 10: -0.20},
        date_bias=0.20,
        seed=20260821,
    )
