"""Séparation des ères, tirages exceptionnels, et rigueur du test multiple."""

from datetime import date, timedelta

import pytest
from conftest import make_draw

from alex_machina import charts, db
from alex_machina.backtest import StrategyResult, _holm, run
from alex_machina.ingest import parse_csv
from alex_machina.model import (
    ERA_LEGACY,
    ERA_MODERN,
    KIND_REGULAR,
    KIND_SPECIAL,
    balls_drawn,
    expected_repeat,
    next_draw_date,
    next_friday_13,
)
from alex_machina.sources import ALL_ARCHIVES, ARCHIVES, SPECIAL_ARCHIVES

MODERN_CSV = (
    "annee_numero_de_tirage;jour_de_tirage;date_de_tirage;date_de_forclusion;"
    "boule_1;boule_2;boule_3;boule_4;boule_5;numero_chance;"
    "nombre_de_gagnant_au_rang1;rapport_du_rang1;\n"
    "26099;VENDREDI;13/03/2026;12/06/2026;16;17;40;48;49;5;0;13000000;\n"
)


# --------------------------------------------------------------------------
# Les deux ères ne se mélangent jamais
# --------------------------------------------------------------------------


def test_balls_drawn_per_era():
    assert balls_drawn(ERA_MODERN) == 5
    assert balls_drawn(ERA_LEGACY) == 6


def test_expected_repeat_depends_on_the_era():
    """k²/n : mélanger les deux ères produirait une valeur de référence fausse."""
    assert expected_repeat(ERA_MODERN) == pytest.approx(25 / 49, abs=1e-9)
    assert expected_repeat(ERA_LEGACY) == pytest.approx(36 / 49, abs=1e-9)
    assert expected_repeat(ERA_LEGACY) > expected_repeat(ERA_MODERN)


def test_load_draws_filters_by_era_and_kind(tmp_path, synthetic_draws):
    conn = db.connect(tmp_path / "t.sqlite")
    special = make_draw(date(2026, 3, 13), [16, 17, 40, 48, 49], 5, kind=KIND_SPECIAL)
    db.upsert_draws(conn, [*synthetic_draws, special])

    reguliers = db.load_draws(conn)
    assert len(reguliers) == len(synthetic_draws)
    assert all(d.kind == KIND_REGULAR for d in reguliers)

    tous = db.load_draws(conn, kind=None)
    assert len(tous) == len(synthetic_draws) + 1
    assert db.count_draws(conn, kind=KIND_SPECIAL) == 1


# --------------------------------------------------------------------------
# Tirages exceptionnels
# --------------------------------------------------------------------------


def test_special_archives_are_declared_and_distinct():
    assert len(SPECIAL_ARCHIVES) == 6
    assert all(a.kind == KIND_SPECIAL for a in SPECIAL_ARCHIVES)
    assert all(a.kind == KIND_REGULAR for a in ARCHIVES)
    assert len({a.name for a in ALL_ARCHIVES}) == len(ALL_ARCHIVES)
    assert len({a.api_suffix for a in ALL_ARCHIVES}) == len(ALL_ARCHIVES)


def test_parse_csv_propagates_the_kind():
    (draw,) = parse_csv(MODERN_CSV, source="superloto", kind=KIND_SPECIAL)
    assert draw.kind == KIND_SPECIAL
    assert not draw.is_regular
    assert draw.date == date(2026, 3, 13)


def test_next_friday_13_finds_the_super_loto_slot():
    # Le 13 mars 2026 est un vendredi ; le suivant est le 13 novembre 2026.
    assert next_friday_13(date(2026, 3, 1)) == date(2026, 3, 13)
    assert next_friday_13(date(2026, 3, 13)) == date(2026, 11, 13)
    for offset in range(0, 500, 7):
        found = next_friday_13(date(2026, 1, 1) + timedelta(days=offset), horizon_days=500)
        assert found is None or (found.day == 13 and found.weekday() == 4)


def test_next_friday_13_returns_none_beyond_the_horizon():
    assert next_friday_13(date(2026, 3, 13), horizon_days=30) is None


def test_a_special_draw_never_replaces_a_regular_one():
    """Les tirages exceptionnels s'ajoutent au calendrier, ils ne s'y substituent pas."""
    friday = date(2026, 3, 13)
    assert friday.weekday() not in (0, 2, 5)
    # Le prochain tirage régulier reste calculé sur le calendrier ordinaire.
    assert next_draw_date(date(2026, 3, 12)) == date(2026, 3, 14)


def test_csv_roundtrip_preserves_the_kind(tmp_path, synthetic_draws):
    special = make_draw(date(2026, 3, 13), [16, 17, 40, 48, 49], 5,
                        ranks={9: (100, 2.2)}, kind=KIND_SPECIAL)
    path = db.export_csv([*synthetic_draws, special], tmp_path / "tirages.csv")
    restored = db.import_csv(path)
    assert restored[-1].kind == KIND_SPECIAL
    assert restored[0].kind == KIND_REGULAR
    assert restored[-1].fdj_id == "test"


def test_upsert_drops_ranks_that_disappeared(tmp_path):
    """Un tirage corrigé ne doit pas garder d'anciens rangs fantômes."""
    conn = db.connect(tmp_path / "t.sqlite")
    day = date(2026, 3, 16)
    db.upsert_draws(conn, [make_draw(day, [1, 2, 3, 4, 5], 7,
                                     ranks={1: (1, 100.0), 6: (10, 12.0)})])
    assert set(db.load_draws(conn, with_payouts=True)[0].ranks) == {1, 6}

    db.upsert_draws(conn, [make_draw(day, [1, 2, 3, 4, 5], 7, ranks={1: (2, 200.0)})])
    reloaded = db.load_draws(conn, with_payouts=True)[0]
    assert set(reloaded.ranks) == {1}
    assert reloaded.ranks[1] == (2, 200.0)


# --------------------------------------------------------------------------
# Rigueur statistique du backtest
# --------------------------------------------------------------------------


def _result(key, p):
    result = StrategyResult(key, key)
    result.p_value = p
    return result


def test_holm_is_monotone_and_conservative():
    results = [_result("a", 0.01), _result("b", 0.04), _result("c", 0.20)]
    _holm(results)
    adjusted = [r.p_value_holm for r in results]
    # Chaque p-value est multipliée par le nombre de tests restants…
    assert adjusted[0] == pytest.approx(0.03)
    assert adjusted[1] == pytest.approx(0.08)
    assert adjusted[2] == pytest.approx(0.20)
    # …et la suite est rendue monotone, donc toujours ≥ la p-value brute.
    assert adjusted == sorted(adjusted)
    assert all(a >= r.p_value for a, r in zip(adjusted, results, strict=True))


def test_holm_never_exceeds_one():
    results = [_result("a", 0.5), _result("b", 0.9)]
    _holm(results)
    assert all(r.p_value_holm <= 1.0 for r in results)


def test_backtest_aggregates_one_observation_per_draw(synthetic_draws):
    """Trois grilles sur la même cible ne font pas trois observations."""
    report = run(synthetic_draws, window=40, warmup=300, repeats=3)
    for result in report.results:
        assert len(result.per_draw) == 40
        assert result.grids == 120
        assert result.p_value_holm >= result.p_value


def test_backtest_baseline_is_its_own_reference(synthetic_draws):
    report = run(synthetic_draws, window=40, warmup=300, repeats=1)
    baseline = next(r for r in report.results if r.key == "uniforme")
    assert baseline.z_score == 0.0
    assert baseline.p_value == 1.0


# --------------------------------------------------------------------------
# Lisibilité des graphiques
# --------------------------------------------------------------------------


def test_diverging_chart_is_fixed_width_so_it_can_scroll():
    svg = charts.diverging_bar_chart([("a", -10.0), ("b", -20.0)])
    assert 'class="chart chart-fixed"' in svg
    assert "width=" in svg.split(">")[0]


def test_diverging_chart_colours_follow_meaning_not_sign():
    """Plus de co-gagnants, c'est un chiffre positif et une mauvaise nouvelle."""
    good = charts.diverging_bar_chart([("a", 5.0)], positive_is_good=True)
    bad = charts.diverging_bar_chart([("a", 5.0)], positive_is_good=False)
    assert "bar-positive" in good and "bar-negative" not in good
    assert "bar-negative" in bad and "bar-positive" not in bad


def test_single_sign_chart_uses_the_full_width():
    """Quand tout est négatif, la moitié droite du graphique serait perdue."""
    negatives = charts.diverging_bar_chart([("a", -10.0), ("b", -20.0)])
    mixed = charts.diverging_bar_chart([("a", 10.0), ("b", -20.0)])
    assert negatives != mixed
