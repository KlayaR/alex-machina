"""Le parseur doit avaler les quatre formats de CSV publiés depuis 1976."""

from datetime import date

from alex_machina.ingest import parse_csv
from alex_machina.model import ERA_LEGACY, ERA_MODERN

LEGACY = (
    "annee_numero_de_tirage;1er_ou_2eme_tirage;jour_de_tirage;date_de_tirage;"
    "date_de_forclusion;boule_1;boule_2;boule_3;boule_4;boule_5;boule_6;"
    "boule_complementaire;nombre_de_gagnant_au_rang1;rapport_du_rang1;\n"
    "2008080;2;SA;20081004;20081204;33;32;42;16;15;49;37;3;1 234 567,89;\n"
)

MODERN = (
    "annee_numero_de_tirage;jour_de_tirage;date_de_tirage;date_de_forclusion;"
    "boule_1;boule_2;boule_3;boule_4;boule_5;numero_chance;"
    "combinaison_gagnante_en_ordre_croissant;nombre_de_gagnant_au_rang1;"
    "rapport_du_rang1;nombre_de_gagnant_au_rang6;rapport_du_rang6;\n"
    "26099;MERCREDI;19/08/2026;18/11/2026;14;21;26;18;44;7;"
    "14-18-21-26-44+7;0;2000000;15710;16,00;\n"
)


def test_parses_legacy_era():
    (draw,) = parse_csv(LEGACY, source="loto")
    assert draw.era == ERA_LEGACY
    assert draw.date == date(2008, 10, 4)
    assert draw.weekday == "samedi"
    assert draw.balls == (15, 16, 32, 33, 42, 49)
    assert draw.complementaire == 37
    assert draw.chance is None
    # Deux tirages pouvaient avoir lieu le même jour : la clé doit les distinguer.
    assert draw.draw_id == "2008-10-04#2"
    assert draw.ranks[1] == (3, 1234567.89)


def test_parses_modern_era():
    (draw,) = parse_csv(MODERN, source="loto_201911")
    assert draw.era == ERA_MODERN
    assert draw.date == date(2026, 8, 19)
    assert draw.balls == (14, 18, 21, 26, 44)
    assert draw.chance == 7
    assert draw.combination == "14-18-21-26-44+7"
    assert draw.ranks[6] == (15710, 16.0)
    assert draw.draw_id == "2026-08-19#1"


def test_skips_rows_without_a_date():
    text = MODERN + ";;;;;;;;;;;;;;\n"
    assert len(parse_csv(text)) == 1


def test_money_parsing_handles_spaces_and_commas():
    (draw,) = parse_csv(LEGACY)
    assert draw.ranks[1][1] == 1234567.89
