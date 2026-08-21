import json
from datetime import datetime, timezone

import pytest

from alex_machina import db, odds, report, stats
from alex_machina.backtest import run
from alex_machina.model import next_draw_date
from alex_machina.predictors import STRATEGIES, predict_all


def test_database_roundtrip(tmp_path, synthetic_draws):
    conn = db.connect(tmp_path / "test.sqlite")
    added, updated = db.upsert_draws(conn, synthetic_draws)
    assert (added, updated) == (len(synthetic_draws), 0)

    # Réinsérer les mêmes tirages ne doit rien dupliquer.
    added, updated = db.upsert_draws(conn, synthetic_draws)
    assert (added, updated) == (0, len(synthetic_draws))
    assert db.count_draws(conn) == len(synthetic_draws)

    loaded = db.load_draws(conn, with_payouts=True)
    assert [d.balls for d in loaded] == [d.balls for d in synthetic_draws]
    assert loaded[-1].date == max(d.date for d in synthetic_draws)
    assert loaded[0].ranks[1] == synthetic_draws[0].ranks[1]


def test_load_draws_is_chronological_even_with_a_limit(tmp_path, synthetic_draws):
    conn = db.connect(tmp_path / "test.sqlite")
    db.upsert_draws(conn, synthetic_draws)
    recent = db.load_draws(conn, limit=10)
    assert len(recent) == 10
    assert recent == sorted(recent, key=lambda d: d.date)
    assert recent[-1].date == synthetic_draws[-1].date


def test_meta_and_csv_export(tmp_path, synthetic_draws):
    conn = db.connect(tmp_path / "test.sqlite")
    db.upsert_draws(conn, synthetic_draws)
    db.set_meta(conn, "cle", "valeur")
    assert db.get_meta(conn, "cle") == "valeur"
    assert db.get_meta(conn, "absente", "repli") == "repli"

    path = db.export_csv(synthetic_draws, tmp_path / "tirages.csv")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == ",".join(db.CSV_HEADER)
    assert len(lines) == len(synthetic_draws) + 1

    # Le CSV versé dans le dépôt doit permettre de tout reconstruire,
    # rapports compris : c'est lui qui fait foi, pas la base SQLite.
    restored = db.import_csv(path)
    assert [d.draw_id for d in restored] == [d.draw_id for d in synthetic_draws]
    assert [d.balls for d in restored] == [d.balls for d in synthetic_draws]
    assert [d.chance for d in restored] == [d.chance for d in synthetic_draws]
    assert restored[0].ranks == synthetic_draws[0].ranks


def test_backtest_stays_close_to_theory(synthetic_draws):
    result = run(synthetic_draws, window=60, warmup=300, repeats=2)
    assert result.draws_tested == 60
    assert len(result.results) == len(STRATEGIES)
    for strategy in result.results:
        assert strategy.grids == 60 * 2
        # Espérance théorique : 0,5102 bon numéro par grille, quoi qu'il arrive.
        assert strategy.mean_matches == pytest.approx(0.51, abs=0.25)
        assert strategy.roi < 0 or strategy.winnings >= 0


def test_backtest_refuses_a_history_that_is_too_short(synthetic_draws):
    with pytest.raises(ValueError):
        run(synthetic_draws[:10], window=10, warmup=300)


def test_report_builds_valid_html_and_json(synthetic_draws):
    draws = synthetic_draws
    ball = stats.ball_stats(draws)
    chance = stats.chance_stats(draws)
    backtest_report = run(draws, window=30, warmup=300, repeats=1)
    generated_at = datetime.now(timezone.utc)
    target = next_draw_date(draws[-1].date)
    predictions = predict_all(draws, seed="t")

    html = report.build_html(
        predictions=predictions, target_date=target, seed="t", last_draw=draws[-1],
        draws=draws, ball_chi=stats.chi_square_uniform([s.count for s in ball]),
        chance_chi=stats.chi_square_uniform([s.count for s in chance]),
        ball_stats_=ball, chance_stats_=chance, shape=stats.shape_stats(draws),
        repeat=stats.repeat_rate(draws), backtest_report=backtest_report,
        crowd_model=None, contrarian=[], economics=odds.economics(draws),
        generated_at=generated_at,
    )
    assert html.startswith("<!doctype html>")
    assert html.count("<section") == html.count("</section>")
    assert "Alex" in html and "joueurs-info-service.fr" in html

    payload = report.build_json(
        predictions=predictions, target_date=target, last_draw=draws[-1],
        ball_stats_=ball, ball_chi=stats.chi_square_uniform([s.count for s in ball]),
        backtest_report=backtest_report, contrarian=[],
        economics=odds.economics(draws), total_draws=len(draws),
        generated_at=generated_at,
    )
    encoded = json.loads(json.dumps(payload, ensure_ascii=False))
    assert encoded["prochain_tirage"] == target.isoformat()
    assert len(encoded["predictions"]) == len(STRATEGIES)
    assert len(encoded["frequences"]) == 49


def test_report_writes_both_files(tmp_path):
    index, feed = report.write(tmp_path, "<!doctype html><html></html>", {"a": 1})
    assert index.read_text(encoding="utf-8").startswith("<!doctype html>")
    assert json.loads(feed.read_text(encoding="utf-8")) == {"a": 1}
