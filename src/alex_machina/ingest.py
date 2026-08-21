"""Analyse des CSV FDJ et normalisation en objets :class:`Draw`.

Le format des fichiers a changé quatre fois depuis 1976 : nombre de colonnes
(31 → 26 → 35 → 50), format de date (``YYYYMMDD`` puis ``JJ/MM/AAAA``), libellé
des jours (``SA`` puis ``SAMEDI``), et jusqu'aux règles du jeu. Le parseur
travaille donc par nom de colonne et non par position.
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime

from .model import ERA_LEGACY, ERA_MODERN, Draw
from .sources import ARCHIVES, Archive, fetch

_WEEKDAYS = {
    "LU": "lundi", "MA": "mardi", "ME": "mercredi", "JE": "jeudi",
    "VE": "vendredi", "SA": "samedi", "DI": "dimanche",
}


def _clean(value: str | None) -> str:
    return (value or "").replace("\u00a0", " ").strip()


def _parse_int(value: str | None) -> int | None:
    text = _clean(value).replace(" ", "")
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _parse_money(value: str | None) -> float:
    """Convertit un rapport FDJ (« 73969,4 », « 22 000 000 ») en flottant."""
    text = _clean(value).replace(" ", "").replace(",", ".")
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _parse_date(value: str) -> date:
    text = _clean(value)
    for fmt in ("%d/%m/%Y", "%Y%m%d", "%d/%m/%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"date de tirage illisible : {value!r}")


def _parse_weekday(value: str, fallback: date) -> str:
    text = _clean(value).lower()
    if len(text) >= 4:
        return text
    if text[:2].upper() in _WEEKDAYS:
        return _WEEKDAYS[text[:2].upper()]
    return ("lundi", "mardi", "mercredi", "jeudi",
            "vendredi", "samedi", "dimanche")[fallback.weekday()]


def parse_csv(text: str, *, source: str = "") -> list[Draw]:
    """Transforme le contenu d'un CSV FDJ en tirages normalisés."""
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    draws: list[Draw] = []
    for row in reader:
        row = {(k or "").strip(): v for k, v in row.items()}
        raw_date = _clean(row.get("date_de_tirage"))
        if not raw_date:
            continue
        drawn_on = _parse_date(raw_date)

        balls = [_parse_int(row.get(f"boule_{i}")) for i in range(1, 7)]
        balls = [b for b in balls if b is not None]
        if len(balls) < 5:
            continue

        chance = _parse_int(row.get("numero_chance"))
        complementaire = _parse_int(row.get("boule_complementaire"))
        era = ERA_LEGACY if len(balls) == 6 else ERA_MODERN

        # Avant 2008 deux tirages pouvaient partager la même date.
        sequence = _parse_int(row.get("1er_ou_2eme_tirage")) or 1
        draw_id = f"{drawn_on.isoformat()}#{sequence}"

        ranks: dict[int, tuple[int, float]] = {}
        for rank in range(1, 10):
            winners = _parse_int(row.get(f"nombre_de_gagnant_au_rang{rank}"))
            payout = _parse_money(row.get(f"rapport_du_rang{rank}"))
            if winners is not None:
                ranks[rank] = (winners, payout)

        draws.append(Draw(
            draw_id=draw_id,
            date=drawn_on,
            weekday=_parse_weekday(row.get("jour_de_tirage", ""), drawn_on),
            era=era,
            balls=tuple(sorted(balls)),
            chance=chance,
            complementaire=complementaire,
            fdj_id=_clean(row.get("annee_numero_de_tirage")),
            source=source,
            ranks=ranks,
        ))
    return draws


def load_archive(archive: Archive) -> list[Draw]:
    """Télécharge puis analyse une archive."""
    return parse_csv(fetch(archive), source=archive.name)


def load_all(archives: tuple[Archive, ...] = ARCHIVES) -> list[Draw]:
    """Charge plusieurs archives et déduplique par identifiant de tirage."""
    seen: dict[str, Draw] = {}
    for archive in archives:
        for draw in load_archive(archive):
            seen[draw.draw_id] = draw
    return sorted(seen.values(), key=lambda d: (d.date, d.draw_id))
