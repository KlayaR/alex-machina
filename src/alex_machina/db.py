"""Persistance SQLite de l'historique des tirages.

La base est un artefact local, reconstructible en une seconde : c'est le CSV
exporté à côté d'elle qui fait foi et qui est versionné dans le dépôt. Un
binaire de quatre mégaoctets réécrit trois fois par semaine ferait gonfler
l'historique Git sans rien apporter ; un CSV texte se diffe ligne à ligne.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Sequence
from datetime import date, datetime, timezone
from pathlib import Path

from .model import ERA_MODERN, KIND_REGULAR, Draw

DEFAULT_DB = Path("data/loto.sqlite")

SCHEMA = """
CREATE TABLE IF NOT EXISTS draws (
    draw_id        TEXT PRIMARY KEY,
    date           TEXT NOT NULL,
    weekday        TEXT NOT NULL,
    era            TEXT NOT NULL,
    balls          TEXT NOT NULL,
    b1 INTEGER, b2 INTEGER, b3 INTEGER, b4 INTEGER, b5 INTEGER, b6 INTEGER,
    chance         INTEGER,
    complementaire INTEGER,
    kind           TEXT NOT NULL DEFAULT 'regulier',
    fdj_id         TEXT,
    source         TEXT,
    ingested_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS draws_date ON draws(date);
CREATE INDEX IF NOT EXISTS draws_era ON draws(era, kind, date);

CREATE TABLE IF NOT EXISTS payouts (
    draw_id TEXT NOT NULL REFERENCES draws(draw_id) ON DELETE CASCADE,
    rank    INTEGER NOT NULL,
    winners INTEGER NOT NULL,
    payout  REAL NOT NULL,
    PRIMARY KEY (draw_id, rank)
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def connect(path: Path | str = DEFAULT_DB) -> sqlite3.Connection:
    """Ouvre (et crée au besoin) la base, schéma appliqué."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Ajoute les colonnes apparues apres coup, sur une base deja peuplee."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(draws)")}
    if "kind" not in columns:
        conn.execute("ALTER TABLE draws ADD COLUMN kind TEXT NOT NULL DEFAULT 'regulier'")
        conn.commit()


def upsert_draws(conn: sqlite3.Connection, draws: Iterable[Draw]) -> tuple[int, int]:
    """Insère ou met à jour des tirages. Renvoie ``(nouveaux, mis à jour)``."""
    known = {row[0] for row in conn.execute("SELECT draw_id FROM draws")}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    added = updated = 0
    for draw in draws:
        balls = list(draw.balls) + [None] * (6 - len(draw.balls))
        conn.execute(
            """INSERT INTO draws (draw_id, date, weekday, era, balls,
                   b1, b2, b3, b4, b5, b6, chance, complementaire,
                   kind, fdj_id, source, ingested_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(draw_id) DO UPDATE SET
                   balls=excluded.balls, chance=excluded.chance,
                   complementaire=excluded.complementaire,
                   b1=excluded.b1, b2=excluded.b2, b3=excluded.b3,
                   b4=excluded.b4, b5=excluded.b5, b6=excluded.b6,
                   kind=excluded.kind, source=excluded.source""",
            (draw.draw_id, draw.date.isoformat(), draw.weekday, draw.era,
             draw.combination, *balls, draw.chance, draw.complementaire,
             draw.kind, draw.fdj_id, draw.source, now),
        )
        if draw.draw_id in known:
            updated += 1
        else:
            added += 1
        # Un tirage corrige peut perdre des rangs : on retire ceux qui ont
        # disparu de la source plutot que de laisser trainer d'anciennes valeurs.
        if draw.ranks:
            marks = ",".join("?" * len(draw.ranks))
            conn.execute(
                f"DELETE FROM payouts WHERE draw_id = ? AND rank NOT IN ({marks})",
                (draw.draw_id, *sorted(draw.ranks)),
            )
        for rank, (winners, payout) in draw.ranks.items():
            conn.execute(
                """INSERT INTO payouts (draw_id, rank, winners, payout)
                   VALUES (?,?,?,?)
                   ON CONFLICT(draw_id, rank) DO UPDATE SET
                       winners=excluded.winners, payout=excluded.payout""",
                (draw.draw_id, rank, winners, payout),
            )
    conn.commit()
    return added, updated


def _row_to_draw(row: sqlite3.Row, ranks: dict[int, tuple[int, float]]) -> Draw:
    balls = tuple(b for b in (row[f"b{i}"] for i in range(1, 7)) if b is not None)
    return Draw(
        draw_id=row["draw_id"],
        date=date.fromisoformat(row["date"]),
        weekday=row["weekday"],
        era=row["era"],
        balls=balls,
        chance=row["chance"],
        complementaire=row["complementaire"],
        kind=row["kind"] or KIND_REGULAR,
        fdj_id=row["fdj_id"] or "",
        source=row["source"] or "",
        ranks=ranks,
    )


def load_draws(
    conn: sqlite3.Connection,
    *,
    era: str | None = ERA_MODERN,
    kind: str | None = KIND_REGULAR,
    since: date | None = None,
    limit: int | None = None,
    with_payouts: bool = False,
) -> list[Draw]:
    """Charge les tirages, du plus ancien au plus récent.

    ``era=None`` renvoie toutes les ères — à n'utiliser que pour l'export, pas
    pour une statistique : un 6/49 et un 5/49 ne se moyennent pas. De même,
    ``kind`` vaut par défaut ``KIND_REGULAR`` car les tirages exceptionnels ont
    leurs propres cagnottes et leurs propres volumes de jeu ; ``kind=None`` les
    inclut, ce qui n'a de sens que pour les fréquences de sortie des boules.

    ``limit`` garde les N plus récents tout en conservant l'ordre chronologique.
    """
    query = "SELECT * FROM draws WHERE 1=1"
    params: list[object] = []
    if era:
        query += " AND era = ?"
        params.append(era)
    if kind:
        query += " AND kind = ?"
        params.append(kind)
    if since:
        query += " AND date >= ?"
        params.append(since.isoformat())
    query += " ORDER BY date DESC, draw_id DESC"
    if limit:
        query += f" LIMIT {int(limit)}"
    rows = list(conn.execute(query, params))

    payouts: dict[str, dict[int, tuple[int, float]]] = {}
    if with_payouts and rows:
        marks = ",".join("?" * len(rows))
        ids = [r["draw_id"] for r in rows]
        for p in conn.execute(
            f"SELECT draw_id, rank, winners, payout FROM payouts WHERE draw_id IN ({marks})",
            ids,
        ):
            payouts.setdefault(p["draw_id"], {})[p["rank"]] = (p["winners"], p["payout"])

    draws = [_row_to_draw(r, payouts.get(r["draw_id"], {})) for r in rows]
    draws.reverse()
    return draws


def latest_draw(
    conn: sqlite3.Connection,
    *,
    era: str | None = ERA_MODERN,
    kind: str | None = KIND_REGULAR,
) -> Draw | None:
    draws = load_draws(conn, era=era, kind=kind, limit=1, with_payouts=True)
    return draws[-1] if draws else None


def count_draws(
    conn: sqlite3.Connection,
    *,
    era: str | None = None,
    kind: str | None = None,
) -> int:
    query = "SELECT COUNT(*) FROM draws WHERE 1=1"
    params: list[object] = []
    if era:
        query += " AND era = ?"
        params.append(era)
    if kind:
        query += " AND kind = ?"
        params.append(kind)
    return conn.execute(query, params).fetchone()[0]


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()


def get_meta(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


#: En-tête du jeu de données versionné dans le dépôt.
CSV_HEADER = (
    ["date", "n", "jour", "ere", "type", "boules", "chance", "complementaire", "id_fdj"]
    + [f"rang{rank}_{field}" for rank in range(1, 10) for field in ("gagnants", "rapport")]
)


def export_csv(draws: Sequence[Draw], path: Path | str) -> Path:
    """Écrit le jeu de données complet en CSV, lisible et diffable.

    C'est ce fichier — et non la base SQLite, quatre mégaoctets de binaire — qui
    est versionné : il se relit sans outil, se diffe ligne à ligne, et permet de
    reconstruire la base même si la FDJ retirait ses archives demain.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [",".join(CSV_HEADER)]
    for draw in draws:
        row = [
            draw.date.isoformat(),
            draw.draw_id.rsplit("#", 1)[-1],
            draw.weekday,
            draw.era,
            draw.kind,
            "-".join(str(b) for b in draw.balls),
            "" if draw.chance is None else str(draw.chance),
            "" if draw.complementaire is None else str(draw.complementaire),
            draw.fdj_id,
        ]
        for rank in range(1, 10):
            winners, payout = draw.ranks.get(rank, ("", ""))
            row.append(str(winners))
            row.append(f"{payout:.2f}" if payout != "" else "")
        lines.append(",".join(row))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def import_csv(path: Path | str) -> list[Draw]:
    """Relit le jeu de données versionné. Le pendant exact d':func:`export_csv`."""
    import csv as csv_module

    draws: list[Draw] = []
    with Path(path).open(encoding="utf-8", newline="") as handle:
        for row in csv_module.DictReader(handle):
            drawn_on = date.fromisoformat(row["date"])
            ranks: dict[int, tuple[int, float]] = {}
            for rank in range(1, 10):
                winners = row.get(f"rang{rank}_gagnants", "")
                payout = row.get(f"rang{rank}_rapport", "")
                if winners not in ("", None):
                    ranks[rank] = (int(winners), float(payout or 0.0))
            draws.append(Draw(
                draw_id=f"{row['date']}#{row.get('n') or 1}",
                date=drawn_on,
                weekday=row["jour"],
                era=row["ere"],
                balls=tuple(int(b) for b in row["boules"].split("-")),
                chance=int(row["chance"]) if row["chance"] else None,
                complementaire=int(row["complementaire"]) if row["complementaire"] else None,
                kind=row.get("type") or KIND_REGULAR,
                fdj_id=row.get("id_fdj") or "",
                source="tirages.csv",
                ranks=ranks,
            ))
    return draws
