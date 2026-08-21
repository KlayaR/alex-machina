import pytest

from alex_machina.predictors import STRATEGIES, predict, predict_all


@pytest.mark.parametrize("strategy", STRATEGIES, ids=lambda s: s.key)
def test_every_strategy_produces_a_playable_grid(strategy, synthetic_draws):
    prediction = predict(strategy, synthetic_draws, seed="test")
    assert len(set(prediction.balls)) == 5
    assert all(1 <= ball <= 49 for ball in prediction.balls)
    assert list(prediction.balls) == sorted(prediction.balls)
    assert 1 <= prediction.chance <= 10


@pytest.mark.parametrize("strategy", STRATEGIES, ids=lambda s: s.key)
def test_predictions_are_reproducible(strategy, synthetic_draws):
    first = predict(strategy, synthetic_draws, seed="graine")
    second = predict(strategy, synthetic_draws, seed="graine")
    assert first.balls == second.balls
    assert first.chance == second.chance


def test_different_seeds_give_different_grids(synthetic_draws):
    grids = {
        predict(STRATEGIES[0], synthetic_draws, seed=str(seed)).balls
        for seed in range(20)
    }
    assert len(grids) > 15


def test_hot_strategy_favours_frequent_numbers(synthetic_draws):
    from alex_machina.predictors import weights_hot
    from alex_machina.stats import ball_stats

    weights = weights_hot(synthetic_draws)
    counts = {s.number: s.count for s in ball_stats(synthetic_draws[-300:])}
    hottest = max(counts, key=counts.get)
    coldest = min(counts, key=counts.get)
    assert weights[hottest] > weights[coldest]


def test_overdue_strategy_favours_late_numbers(synthetic_draws):
    from alex_machina.predictors import weights_overdue
    from alex_machina.stats import ball_stats

    weights = weights_overdue(synthetic_draws)
    gaps = {s.number: s.gap for s in ball_stats(synthetic_draws)}
    latest = max(gaps, key=gaps.get)
    recent = min(gaps, key=gaps.get)
    assert weights[latest] > weights[recent]


def test_predict_all_returns_one_grid_per_strategy(synthetic_draws):
    predictions = predict_all(synthetic_draws, seed="x")
    assert len(predictions) == len(STRATEGIES)
    assert {p.strategy for p in predictions} == {s.key for s in STRATEGIES}
