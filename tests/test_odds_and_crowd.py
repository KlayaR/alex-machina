import math
import random
from datetime import date, timedelta

import pytest
from conftest import make_draw

from alex_machina import crowd
from alex_machina.model import GRID_PRICE
from alex_machina.odds import (
    economics,
    grids_for_certainty,
    match_probability,
    rank_probability,
    win_probability,
)


def test_match_probabilities_sum_to_one():
    assert sum(match_probability(k) for k in range(6)) == pytest.approx(1.0)


def test_jackpot_odds_are_one_in_19_068_840():
    assert 1 / rank_probability(1) == pytest.approx(19_068_840, rel=1e-9)


def test_rank_probabilities_are_mutually_exclusive():
    total = sum(rank_probability(r) for r in range(1, 10))
    assert total == pytest.approx(win_probability())
    assert total < 1.0
    # Une grille sur six environ rapporte quelque chose.
    assert 1 / total == pytest.approx(6, abs=0.5)


def test_expected_value_is_below_the_ticket_price(synthetic_draws):
    result = economics(synthetic_draws)
    assert result.expected_value < GRID_PRICE
    assert 0 < result.house_edge < 100
    assert result.loss_per_grid == pytest.approx(GRID_PRICE - result.expected_value)


def test_grids_for_certainty_is_consistent_with_the_probability():
    probability = rank_probability(1)
    grids = grids_for_certainty(probability, 0.5)
    assert (1 - probability) ** grids == pytest.approx(0.5, abs=1e-6)


def test_ols_recovers_known_coefficients():
    # y = 1 + 2*x1 - 3*x2, sans bruit : la régression doit tomber pile dessus.
    rows = [[1.0, x1, x2] for x1 in range(1, 6) for x2 in range(1, 6)]
    target = [1.0 + 2 * row[1] - 3 * row[2] for row in rows]
    width = 3
    xtx = [[sum(r[i] * r[j] for r in rows) for j in range(width)] for i in range(width)]
    xty = [sum(r[i] * y for r, y in zip(rows, target, strict=True)) for i in range(width)]
    beta, _ = crowd._solve(xtx, xty)
    assert beta == pytest.approx([1.0, 2.0, -3.0], abs=1e-9)


def _draws_with_planted_date_bias(effect: float = 0.20, n: int = 400):
    """Fabrique un historique où les numéros ≤ 31 attirent vraiment la foule."""
    rng = random.Random(7)
    start = date(2020, 1, 1)
    draws = []
    for index in range(n):
        balls = rng.sample(range(1, 50), 5)
        volume = rng.randint(300_000, 500_000)
        low = sum(1 for b in balls if b <= 31)
        winners = math.exp(math.log(volume) * 0.6 + effect * low)
        ranks = {
            crowd.RESPONSE_RANK: (max(1, int(winners)), 12.0),
            crowd.VOLUME_RANK: (volume, 2.2),
        }
        draws.append(make_draw(start + timedelta(days=index * 2), balls, 1, ranks=ranks))
    return draws


def test_crowd_model_detects_a_planted_bias():
    model = crowd.fit(_draws_with_planted_date_bias(effect=0.20))
    assert model.date_bias.value == pytest.approx(0.20, abs=0.02)
    assert model.date_bias.significant
    assert model.r_squared > 0.9


def test_crowd_model_finds_nothing_when_there_is_nothing():
    model = crowd.fit(_draws_with_planted_date_bias(effect=0.0))
    assert not model.date_bias.significant


def test_contrarian_grids_avoid_low_numbers():
    draws = _draws_with_planted_date_bias(effect=0.20)
    model = crowd.fit(draws)
    grids = crowd.contrarian_grids(model, draws, count=4, candidates=4000, seed=1)
    assert len(grids) == 4
    for grid in grids:
        assert len(set(grid.balls)) == 5
        assert grid.payout_multiplier > 1.0
        # Une grille moyenne contient 3,2 numéros ≤ 31 ; celles-ci doivent faire mieux.
        assert sum(1 for b in grid.balls if b <= 31) <= 2


def test_contrarian_grids_are_not_near_duplicates():
    draws = _draws_with_planted_date_bias(effect=0.20)
    grids = crowd.contrarian_grids(crowd.fit(draws), draws, count=5, candidates=6000, seed=2)
    for i, first in enumerate(grids):
        for second in grids[i + 1:]:
            assert len(set(first.balls) & set(second.balls)) <= 2
