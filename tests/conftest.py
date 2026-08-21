import random
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from alex_machina.model import ERA_MODERN, Draw  # noqa: E402


def make_draw(day: date, balls, chance, *, ranks=None, sequence=1) -> Draw:
    return Draw(
        draw_id=f"{day.isoformat()}#{sequence}",
        date=day,
        weekday="samedi",
        era=ERA_MODERN,
        balls=tuple(sorted(balls)),
        chance=chance,
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
