"""Le modèle du numéro chance, et la correction qu'il apporte au modèle des boules."""

import pytest

from alex_machina import crowd


def test_chance_model_recovers_a_planted_bias(biased_draws):
    model = crowd.fit_chance(biased_draws)
    effects = {e.number: e for e in model.effects}

    # Le 7 est le plus joué, le 1 le moins : c'est ce qu'on a fabriqué.
    assert model.most_popular.number == 7
    assert model.least_popular.number == 1
    assert effects[7].significant and effects[1].significant

    # Les effets sont recentrés sur leur moyenne, donc ils s'annulent entre eux.
    assert sum(e.log_effect for e in model.effects) == pytest.approx(0.0, abs=1e-9)

    # L'écart planté entre le 7 et le 1 vaut 0,65 en log, soit environ +92 %.
    ecart = effects[7].log_effect - effects[1].log_effect
    assert ecart == pytest.approx(0.65, abs=0.05)


def test_chance_model_finds_nothing_on_unbiased_history(unbiased_draws):
    """Sur un historique sans biais planté, le modèle ne doit rien inventer.

    Le seuil est mis à |t| > 4 et non 2 : avec dix numéros testés, un |t| > 2
    isolé arrive une fois sur deux par pur hasard, et le test serait instable.
    Un |t| > 4 sur du bruit, lui, ne se produit pratiquement jamais.
    """
    model = crowd.fit_chance(unbiased_draws)
    assert max(abs(e.t_stat) for e in model.effects) < 4.0
    assert model.spread_percent < 15.0


def test_payout_multiplier_is_the_inverse_of_popularity(biased_draws):
    model = crowd.fit_chance(biased_draws)
    for effect in model.effects:
        assert effect.payout_multiplier == pytest.approx(1.0 / effect.popularity)
    # Jouer le moins populaire rapporte plus que la moyenne, par construction.
    assert model.least_popular.payout_multiplier > 1.0
    assert model.most_popular.payout_multiplier < 1.0


def test_correcting_the_volume_proxy_removes_the_attenuation(biased_draws):
    """Sans correction, le témoin de volume est bruité et atténue les coefficients.

    Le nombre de gagnants au rang « n° chance seul » sert de témoin du volume de
    grilles vendues, mais il dépend aussi du numéro chance tiré. Cette erreur de
    mesure tire le coefficient du volume vers le bas — il devrait valoir 1 — et
    entraîne tous les autres avec lui.
    """
    chance_model = crowd.fit_chance(biased_draws)
    brut = crowd.fit(biased_draws)
    corrige = crowd.fit(biased_draws, chance_model=chance_model)

    assert not brut.chance_corrected
    assert corrige.chance_corrected

    volume_brut = brut.coefficients[1].value
    volume_corrige = corrige.coefficients[1].value
    assert abs(volume_corrige - 1.0) < abs(volume_brut - 1.0)
    assert corrige.r_squared > brut.r_squared

    # Le biais des dates de naissance vaut 0,20 par construction : la version
    # corrigee doit s'en approcher davantage que la version brute.
    assert abs(corrige.date_bias.value - 0.20) < abs(brut.date_bias.value - 0.20)
    assert corrige.date_bias.t_stat > brut.date_bias.t_stat


def test_contrarian_grids_play_the_least_popular_chance(biased_draws):
    chance_model = crowd.fit_chance(biased_draws)
    model = crowd.fit(biased_draws, chance_model=chance_model)
    grids = crowd.contrarian_grids(
        model, biased_draws, count=3, candidates=6000, seed=1, chance_model=chance_model
    )
    assert len(grids) == 3
    # La meilleure grille prend le numéro chance le moins joué.
    assert grids[0].chance == chance_model.least_popular.number
    # Aucune ne joue le plus populaire.
    assert all(g.chance != chance_model.most_popular.number for g in grids)
    for grid in grids:
        assert grid.payout_multiplier_with_chance > grid.payout_multiplier > 1.0


def test_contrarian_grids_without_a_chance_model_stay_neutral(biased_draws):
    model = crowd.fit(biased_draws)
    grids = crowd.contrarian_grids(model, biased_draws, count=2, candidates=4000, seed=3)
    for grid in grids:
        assert grid.chance_score == 1.0
        assert grid.payout_multiplier_with_chance == pytest.approx(grid.payout_multiplier)


def test_fit_chance_refuses_a_history_that_is_too_short(biased_draws):
    with pytest.raises(ValueError):
        crowd.fit_chance(biased_draws[:50])
