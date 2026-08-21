"""Interface en ligne de commande d'Alex Machina."""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from . import crowd, db, ingest, odds, report, stats
from .backtest import run as run_backtest
from .model import GRID_PRICE, RANK_LABELS, format_date, next_draw_date, rank_of
from .predictors import STRATEGIES, STRATEGY_BY_KEY, predict, predict_all
from .sources import ARCHIVES, LIVE_ARCHIVE


def _console() -> None:
    """Force l'UTF-8 en sortie : la console Windows est en cp1252 par défaut."""
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError):
            stream.reconfigure(encoding="utf-8")


def _fmt(value: float, digits: int = 0) -> str:
    return f"{value:,.{digits}f}".replace(",", " ").replace(".", ",")


def _rule(title: str) -> None:
    print(f"\n\033[1m{title}\033[0m")
    print("─" * min(len(title) + 8, 72))


def _dataset_path(args: argparse.Namespace) -> Path:
    """Le jeu de données versionné, à côté de la base."""
    return Path(args.db).parent / "tirages.csv"


def _load(args: argparse.Namespace, *, payouts: bool = False):
    conn = db.connect(args.db)
    if db.count_draws(conn) == 0:
        dataset = _dataset_path(args)
        if not dataset.exists():
            raise SystemExit(
                "Base vide. Lancez d'abord :  python -m alex_machina update --full"
            )
        db.upsert_draws(conn, db.import_csv(dataset))
    draws = db.load_draws(conn, era=None if args.all_eras else "5/49", with_payouts=payouts)
    return conn, draws


# --------------------------------------------------------------------------
# Commandes
# --------------------------------------------------------------------------


def cmd_update(args: argparse.Namespace) -> int:
    archives = ARCHIVES if args.full else (LIVE_ARCHIVE,)
    _rule("Mise à jour depuis les archives officielles FDJ")
    conn = db.connect(args.db)

    # Base absente ou vide : on l'amorce avec le jeu de données du dépôt, pour
    # que le reste fonctionne même si la FDJ est injoignable.
    dataset = _dataset_path(args)
    if db.count_draws(conn) == 0 and dataset.exists():
        seeded, _ = db.upsert_draws(conn, db.import_csv(dataset))
        print(f"  Base amorcée depuis {dataset} ({seeded} tirages).")

    before = db.count_draws(conn)
    previous = db.latest_draw(conn)

    fetched = []
    for archive in archives:
        print(f"  · {archive.name:<16} {archive.period}", end="", flush=True)
        draws = ingest.load_archive(archive)
        fetched.extend(draws)
        print(f"  → {len(draws)} tirages")

    added, updated = db.upsert_draws(conn, fetched)
    total = db.count_draws(conn)
    latest = db.latest_draw(conn)
    db.set_meta(conn, "derniere_mise_a_jour", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    db.set_meta(conn, "dernier_tirage", latest.date.isoformat() if latest else "")
    db.export_csv(db.load_draws(conn, era=None, with_payouts=True), _dataset_path(args))

    print(f"\n  {added} nouveau(x), {updated} mis à jour, {total} au total "
          f"(base {before} → {total}).")
    if latest:
        print(f"  Dernier tirage connu : {format_date(latest.date)} — {latest.combination}")
    if previous and latest and latest.date > previous.date:
        print(f"  ✦ Nouveau tirage détecté depuis la dernière exécution "
              f"({previous.date} → {latest.date}).")
    return 0


def cmd_predict(args: argparse.Namespace) -> int:
    conn, draws = _load(args)
    target = next_draw_date(draws[-1].date)
    seed = args.seed or target.isoformat()

    _rule(f"Grilles pour le tirage du {format_date(target)}")
    selection = (
        [STRATEGY_BY_KEY[args.strategy]] if args.strategy else list(STRATEGIES)
    )
    predictions = [predict(s, draws, seed=seed) for s in selection]

    if args.json:
        print(json.dumps([
            {"strategie": p.strategy, "boules": list(p.balls), "chance": p.chance}
            for p in predictions
        ], ensure_ascii=False, indent=2))
        return 0

    for prediction in predictions:
        print(f"  {prediction.label:<22} {prediction.combination}")
    print(f"\n  Graine : {seed} · {len(draws)} tirages d'historique")
    print("  Chacune de ces grilles a une chance sur 19 068 840 de décrocher le rang 1,")
    print("  exactement comme n'importe quelle autre combinaison. Voir « backtest ».")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    conn, draws = _load(args)
    ball = stats.ball_stats(draws)
    chance = stats.chance_stats(draws)
    chi = stats.chi_square_uniform([s.count for s in ball])
    chance_chi = stats.chi_square_uniform([s.count for s in chance])
    shape = stats.shape_stats(draws)

    _rule(f"Statistiques sur {len(draws)} tirages "
          f"({draws[0].date} → {draws[-1].date})")

    print("\n  Numéros les plus sortis")
    for s in sorted(ball, key=lambda s: -s.count)[:args.top]:
        print(f"    {s.number:>2}  {s.count:>4} sorties  ({s.deviation:+.1f} % vs attendu)")

    print("\n  Numéros les plus en retard")
    for s in sorted(ball, key=lambda s: -s.gap)[:args.top]:
        print(f"    {s.number:>2}  {s.gap:>4} tirages sans sortir  "
              f"(moyenne {s.mean_gap:.1f}, record {s.max_gap})")

    print("\n  Test d'uniformité (khi-deux)")
    print(f"    Boules  : X² = {chi.statistic:.1f} · ddl {chi.dof} · p = {chi.p_value:.3f}")
    print(f"              → {chi.verdict}")
    print(f"    Chance  : X² = {chance_chi.statistic:.1f} · ddl {chance_chi.dof} "
          f"· p = {chance_chi.p_value:.3f}")

    print("\n  Forme des combinaisons gagnantes")
    print(f"    Somme moyenne      {shape.mean_sum:.1f}  (80 % entre {shape.sum_p10} et {shape.sum_p90})")
    print(f"    Impairs / tirage   {shape.mean_odd:.2f}")
    print(f"    Numéros ≤ 25       {shape.mean_low:.2f}")
    print(f"    Paires consécutives {shape.mean_consecutive:.2f}")
    print(f"    Report d'un tirage sur l'autre  {stats.repeat_rate(draws):.2f} numéro "
          f"(théorie : 0,51)")
    return 0


def cmd_backtest(args: argparse.Namespace) -> int:
    conn, draws = _load(args, payouts=True)
    _rule(f"Backtest sur les {args.window} derniers tirages "
          f"× {args.repeats} grilles par stratégie")
    print("  Calcul en cours, chaque stratégie ne voit que le passé…\n")
    result = run_backtest(draws, window=args.window, repeats=args.repeats)

    header = f"  {'Stratégie':<22}{'Bons n°':>9}{'Gagnantes':>11}{'Mise':>10}{'Gains':>10}{'Retour':>9}{'vs hasard':>11}"
    print(header)
    print("  " + "─" * (len(header) - 2))
    for r in result.results:
        marker = "témoin" if r.key == "uniforme" else f"p={r.p_value:.2f}"
        print(f"  {r.label:<22}{r.mean_matches:>9.4f}{100 * r.hit_rate:>10.1f}%"
              f"{_fmt(r.stake):>10}{_fmt(r.winnings):>10}{r.roi:>8.1f}%{marker:>11}")

    print(f"\n  Période : {result.first_date} → {result.last_date}")
    if result.any_significant:
        print("  Une stratégie s'écarte du hasard à 5 % — sur sept tests simultanés,")
        print("  c'est le résultat le plus banal qui soit. Relancez sur une autre fenêtre.")
    else:
        print("  Aucune stratégie ne se distingue du hasard pur. Comme prévu.")
    return 0


def cmd_crowd(args: argparse.Namespace) -> int:
    conn, draws = _load(args, payouts=True)
    _rule("Modèle de foule — le seul avantage réel")
    model = crowd.fit(draws)
    print(f"  {model.observations} tirages exploitables ({model.period}), "
          f"R² = {model.r_squared:.3f}\n")
    print(f"  {'Variable':<44}{'Coef.':>9}{'t':>8}{'Effet':>10}")
    print("  " + "─" * 69)
    for coefficient in model.coefficients[1:]:
        star = " *" if coefficient.significant else ""
        print(f"  {coefficient.name:<44}{coefficient.value:>9.4f}"
              f"{coefficient.t_stat:>8.1f}{coefficient.effect_percent:>9.1f} %{star}")

    print("\n  Grilles à contre-courant "
          "(probabilité identique, gain partagé plus rarement) :")
    for grid in crowd.contrarian_grids(model, draws, count=args.grids, seed=args.seed or 0):
        print(f"    {grid.combination}   co-gagnants ×{grid.crowd_score:.2f}  "
              f"→ gain estimé +{grid.gain_percent:.0f} %")
    return 0


def cmd_odds(args: argparse.Namespace) -> int:
    conn, draws = _load(args, payouts=True)
    economics = odds.economics(draws)
    _rule("Économie d'une grille simple")
    print(f"  {'Rang':<26}{'Probabilité':>18}{'Rapport moyen':>16}{'Apport':>10}")
    print("  " + "─" * 68)
    for row in economics.rows:
        print(f"  {row.label:<26}{'1 sur ' + _fmt(row.odds):>18}"
              f"{_fmt(row.mean_payout, 2) + ' €':>16}{_fmt(row.contribution, 3) + ' €':>10}")
    print(f"\n  Mise               {_fmt(GRID_PRICE, 2)} €")
    print(f"  Espérance de gain  {_fmt(economics.expected_value, 2)} €")
    print(f"  Perte moyenne      {_fmt(economics.loss_per_grid, 2)} € par grille")
    print(f"  Taux de retour     {_fmt(100 - economics.house_edge, 1)} %")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """Rejoue une grille sur tout l'historique disponible."""
    balls = tuple(sorted(args.numbers))
    if len(set(balls)) != 5 or not all(1 <= b <= 49 for b in balls):
        raise SystemExit("Il faut cinq numéros distincts entre 1 et 49.")
    if not 1 <= args.chance <= 10:
        raise SystemExit("Le numéro chance va de 1 à 10.")

    conn, draws = _load(args, payouts=True)
    if args.since:
        limit = date.fromisoformat(args.since)
        draws = [d for d in draws if d.date >= limit]

    _rule(f"Votre grille {'-'.join(f'{b:02d}' for b in balls)} + {args.chance} "
          f"rejouée sur {len(draws)} tirages")

    winnings = 0.0
    hits: dict[int, int] = {}
    best: tuple[int, object] | None = None
    for draw in draws:
        matched, chance_hit = draw.matches(balls, args.chance)
        rank = rank_of(matched, chance_hit)
        if rank is None:
            continue
        hits[rank] = hits.get(rank, 0) + 1
        winnings += draw.ranks.get(rank, (0, 0.0))[1]
        if best is None or rank < best[0]:
            best = (rank, draw)

    stake = len(draws) * GRID_PRICE
    for rank in sorted(hits):
        print(f"  {RANK_LABELS[rank]:<26}{hits[rank]:>5} fois")
    if not hits:
        print("  Aucun gain. Pas même le remboursement.")
    print(f"\n  Misé   {_fmt(stake, 2)} €")
    print(f"  Gagné  {_fmt(winnings, 2)} €")
    print(f"  Bilan  {_fmt(winnings - stake, 2)} €  "
          f"({100 * (winnings - stake) / stake:.1f} % de retour)")
    if best:
        rank, draw = best
        print(f"\n  Meilleur résultat : {RANK_LABELS[rank]} le {format_date(draw.date)}")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    conn, draws = _load(args, payouts=True)
    generated_at = datetime.now(timezone.utc)
    target = next_draw_date(draws[-1].date)
    seed = args.seed or target.isoformat()

    _rule("Construction du tableau de bord")
    print("  · prédictions", end="", flush=True)
    predictions = predict_all(draws, seed=seed)
    print(" ✓")

    print("  · statistiques", end="", flush=True)
    ball_stats_ = stats.ball_stats(draws)
    chance_stats_ = stats.chance_stats(draws)
    ball_chi = stats.chi_square_uniform([s.count for s in ball_stats_])
    chance_chi = stats.chi_square_uniform([s.count for s in chance_stats_])
    shape = stats.shape_stats(draws)
    repeat = stats.repeat_rate(draws)
    print(" ✓")

    print(f"  · backtest ({args.window} tirages)", end="", flush=True)
    backtest_report = run_backtest(draws, window=args.window, repeats=args.repeats)
    print(" ✓")

    print("  · modèle de foule", end="", flush=True)
    try:
        model = crowd.fit(draws)
        contrarian = crowd.contrarian_grids(model, draws, count=6, seed=seed)
    except ValueError as error:
        print(f" ⚠ ignoré ({error})")
        model, contrarian = None, []
    else:
        print(" ✓")

    economics = odds.economics(draws)

    html = report.build_html(
        predictions=predictions, target_date=target, seed=seed,
        last_draw=draws[-1], draws=draws, ball_chi=ball_chi, chance_chi=chance_chi,
        ball_stats_=ball_stats_, chance_stats_=chance_stats_, shape=shape,
        repeat=repeat, backtest_report=backtest_report, crowd_model=model,
        contrarian=contrarian, economics=economics, generated_at=generated_at,
    )
    payload = report.build_json(
        predictions=predictions, target_date=target, last_draw=draws[-1],
        ball_stats_=ball_stats_, ball_chi=ball_chi, backtest_report=backtest_report,
        contrarian=contrarian, economics=economics, total_draws=len(draws),
        generated_at=generated_at,
    )
    index, feed = report.write(args.output, html, payload)
    print(f"\n  {index}  ({index.stat().st_size // 1024} Ko)")
    print(f"  {feed}")
    return 0


# --------------------------------------------------------------------------
# Analyseur d'arguments
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alex-machina",
        description="Analyse l'historique du Loto français et démontre "
                    "qu'aucune prédiction ne tient la route.",
    )
    parser.add_argument("--db", default="data/loto.sqlite", help="chemin de la base SQLite")
    parser.add_argument("--all-eras", action="store_true",
                        help="inclure l'ère 6/49 (1976-2008) dans les analyses")
    subparsers = parser.add_subparsers(dest="command", required=True)

    update = subparsers.add_parser("update", help="télécharger les derniers tirages")
    update.add_argument("--full", action="store_true",
                        help="recharger tout l'historique depuis 1976")
    update.set_defaults(func=cmd_update)

    predict_cmd = subparsers.add_parser("predict", help="générer les grilles du prochain tirage")
    predict_cmd.add_argument("--strategy", choices=[s.key for s in STRATEGIES])
    predict_cmd.add_argument("--seed", help="graine (par défaut : la date du prochain tirage)")
    predict_cmd.add_argument("--json", action="store_true")
    predict_cmd.set_defaults(func=cmd_predict)

    stats_cmd = subparsers.add_parser("stats", help="fréquences, retards, tests d'uniformité")
    stats_cmd.add_argument("--top", type=int, default=8)
    stats_cmd.set_defaults(func=cmd_stats)

    backtest_cmd = subparsers.add_parser("backtest", help="rejouer les stratégies sur le passé")
    backtest_cmd.add_argument("--window", type=int, default=400)
    backtest_cmd.add_argument("--repeats", type=int, default=3)
    backtest_cmd.set_defaults(func=cmd_backtest)

    crowd_cmd = subparsers.add_parser("crowd", help="biais des joueurs et grilles à contre-courant")
    crowd_cmd.add_argument("--grids", type=int, default=5)
    crowd_cmd.add_argument("--seed")
    crowd_cmd.set_defaults(func=cmd_crowd)

    odds_cmd = subparsers.add_parser("odds", help="probabilités et espérance de gain réelle")
    odds_cmd.set_defaults(func=cmd_odds)

    check = subparsers.add_parser("check", help="rejouer votre grille sur tout l'historique")
    check.add_argument("numbers", type=int, nargs=5, metavar="N")
    check.add_argument("--chance", type=int, required=True)
    check.add_argument("--since", help="date ISO de début (ex. 2019-11-04)")
    check.set_defaults(func=cmd_check)

    build = subparsers.add_parser("build", help="construire le tableau de bord statique")
    build.add_argument("--output", default="docs")
    build.add_argument("--window", type=int, default=400)
    build.add_argument("--repeats", type=int, default=3)
    build.add_argument("--seed")
    build.set_defaults(func=cmd_build)

    return parser


def main(argv: list[str] | None = None) -> int:
    _console()
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
