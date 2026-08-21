from datetime import date, timedelta

import pytest

from alex_machina.model import DRAW_WEEKDAYS, format_date, next_draw_date, rank_of


@pytest.mark.parametrize(
    ("matches", "chance", "expected"),
    [
        (5, True, 1), (5, False, 2),
        (4, True, 3), (4, False, 4),
        (3, True, 5), (3, False, 6),
        (2, True, 7), (2, False, 8),
        (1, True, 9), (0, True, 9),
        (1, False, None), (0, False, None),
    ],
)
def test_rank_of(matches, chance, expected):
    assert rank_of(matches, chance) == expected


def test_next_draw_date_skips_non_draw_days():
    # Jeudi 20 août 2026 → le prochain tirage est le samedi 22.
    assert next_draw_date(date(2026, 8, 20)) == date(2026, 8, 22)
    # Samedi → lundi.
    assert next_draw_date(date(2026, 8, 22)) == date(2026, 8, 24)
    # Lundi → mercredi.
    assert next_draw_date(date(2026, 8, 24)) == date(2026, 8, 26)


def test_next_draw_date_is_strictly_posterior():
    for offset in range(14):
        day = date(2026, 8, 1) + timedelta(days=offset)
        following = next_draw_date(day)
        assert following > day
        assert following.weekday() in DRAW_WEEKDAYS


def test_format_date_is_french():
    assert format_date(date(2026, 8, 22)) == "samedi 22 août 2026"


def test_draw_matches(synthetic_draws):
    draw = synthetic_draws[0]
    hits, chance_hit = draw.matches(draw.balls, draw.chance)
    assert (hits, chance_hit) == (5, True)
    hits, chance_hit = draw.matches(draw.balls, (draw.chance % 10) + 1)
    assert (hits, chance_hit) == (5, False)
