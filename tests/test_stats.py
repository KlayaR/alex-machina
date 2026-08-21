from datetime import date, timedelta

import pytest
from conftest import make_draw

from alex_machina.stats import (
    ball_stats,
    chi2_sf,
    chi_square_uniform,
    consecutive_pairs,
    repeat_rate,
    shape_stats,
)


@pytest.mark.parametrize(
    ("statistic", "dof", "expected"),
    [
        (3.841, 1, 0.05),
        (11.070, 5, 0.05),
        (18.307, 10, 0.05),
        (67.505, 48, 0.0335),
        (0.0, 5, 1.0),
    ],
)
def test_chi2_survival_matches_published_tables(statistic, dof, expected):
    assert chi2_sf(statistic, dof) == pytest.approx(expected, abs=5e-3)


def test_uniform_history_passes_the_chi_square_test(synthetic_draws):
    result = chi_square_uniform([s.count for s in ball_stats(synthetic_draws)])
    assert result.dof == 48
    assert result.p_value > 0.01
    assert "uniforme" in result.verdict


def test_rigged_history_fails_the_chi_square_test():
    start = date(2020, 1, 1)
    # Le 7 sort à tous les tirages : impossible de passer inaperçu.
    draws = [
        make_draw(start + timedelta(days=i), [7, 11, 22, 33, 44], 3)
        for i in range(200)
    ]
    result = chi_square_uniform([s.count for s in ball_stats(draws)])
    assert result.p_value < 0.01


def test_gap_is_zero_for_a_number_drawn_last():
    start = date(2020, 1, 1)
    draws = [make_draw(start + timedelta(days=i), [1, 2, 3, 4, 5], 1) for i in range(3)]
    draws.append(make_draw(start + timedelta(days=9), [10, 11, 12, 13, 14], 2))
    stats = {s.number: s for s in ball_stats(draws)}
    assert stats[10].gap == 0
    assert stats[1].gap == 1
    assert stats[49].count == 0


def test_repeat_rate_of_identical_draws_is_five():
    start = date(2020, 1, 1)
    draws = [make_draw(start + timedelta(days=i), [1, 2, 3, 4, 5], 1) for i in range(10)]
    assert repeat_rate(draws) == 5.0


def test_repeat_rate_matches_theory_on_uniform_draws(synthetic_draws):
    # Espérance : 5 x 5 / 49 = 0,5102 numéro reporté d'un tirage au suivant.
    assert repeat_rate(synthetic_draws) == pytest.approx(0.51, abs=0.15)


@pytest.mark.parametrize(
    ("balls", "expected"),
    [([1, 2, 3, 10, 20], 2), ([1, 3, 5, 7, 9], 0), ([10, 11, 30, 31, 40], 2)],
)
def test_consecutive_pairs(balls, expected):
    assert consecutive_pairs(balls) == expected


def test_shape_stats_bracket_the_mean(synthetic_draws):
    shape = shape_stats(synthetic_draws)
    assert shape.sum_p10 < shape.mean_sum < shape.sum_p90
    # Moyenne théorique de la somme de 5 boules sur 49 : 5 x 25 = 125.
    assert shape.mean_sum == pytest.approx(125, abs=8)
