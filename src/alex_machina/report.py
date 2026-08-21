"""Construction du tableau de bord statique et du flux JSON.

Sortie : un unique ``docs/index.html`` autonome (aucun CDN, aucun script de
rendu) et un ``docs/data/latest.json`` lisible par une machine. GitHub Pages
sert le premier, n'importe quel script consomme le second.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date, datetime
from html import escape
from pathlib import Path

from . import charts
from .backtest import BacktestReport
from .crowd import ChanceModel, ContrarianGrid, CrowdModel
from .model import GRID_PRICE, RANK_LABELS, Draw, format_date, next_friday_13
from .odds import Economics, grids_for_certainty, rank_probability, years_of_playing
from .predictors import Prediction
from .stats import ChiSquareResult, NumberStats, ShapeStats

DISCLAIMER = (
    "Aucun de ces chiffres ne permet de prédire quoi que ce soit. Un tirage du "
    "Loto est indépendant de tous les précédents : les 1 906 884 combinaisons "
    "ont exactement la même probabilité, à chaque tirage, pour toujours. Ce "
    "site existe pour le montrer, pas pour le contourner."
)


def _fmt(value: float, digits: int = 0) -> str:
    return f"{value:,.{digits}f}".replace(",", " ").replace(".", ",")


def _typography(html: str) -> str:
    """Colle les guillemets français à ce qu'ils encadrent.

    Sans espace insécable, un navigateur étroit renvoie joyeusement le guillemet
    fermant à la ligne suivante, tout seul. La règle ne s'applique qu'aux
    guillemets : les deux-points et les pourcentages apparaissent aussi dans les
    URL et les attributs, où une substitution ferait des dégâts.
    """
    narrow = " "
    return html.replace("« ", "«" + narrow).replace(" »", narrow + "»")


def _balls_html(balls: Sequence[int], chance: int | None = None) -> str:
    parts = [f'<span class="ball">{b:02d}</span>' for b in balls]
    if chance is not None:
        parts.append('<span class="plus">+</span>')
        parts.append(f'<span class="ball ball-chance">{chance}</span>')
    return f'<div class="balls">{"".join(parts)}</div>'


CSS = """
:root {
  color-scheme: light dark;
  --bg: #f6f5f3;
  --surface: #ffffff;
  --surface-alt: #efedea;
  --border: #ddd9d3;
  --text: #1c1b19;
  --muted: #6b6862;
  --accent: #4c3bcf;
  --accent-soft: #e8e5fb;
  --chance: #c8102e;
  --positive: #1f8a5f;
  --negative: #c0492c;
  --shadow: 0 1px 2px rgba(28,27,25,.06), 0 8px 24px rgba(28,27,25,.05);
  --radius: 14px;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #14131a;
    --surface: #1d1c24;
    --surface-alt: #26242f;
    --border: #33313c;
    --text: #eceaf2;
    --muted: #9c98a8;
    --accent: #a99bff;
    --accent-soft: #2b2740;
    --chance: #ff7a8a;
    --positive: #5ad2a0;
    --negative: #ff8f6b;
    --shadow: 0 1px 2px rgba(0,0,0,.4), 0 8px 28px rgba(0,0,0,.35);
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font: 16px/1.6 ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  -webkit-font-smoothing: antialiased;
}
.wrap { max-width: 1080px; margin: 0 auto; padding: 0 20px 80px; }
header.hero { padding: 56px 0 28px; }
.eyebrow { font-size: .78rem; letter-spacing: .14em; text-transform: uppercase; color: var(--muted); margin: 0 0 10px; }
h1 { font-size: clamp(2.1rem, 5vw, 3.1rem); line-height: 1.06; margin: 0 0 12px; letter-spacing: -.02em; }
h1 .machina { color: var(--accent); }
.lede { font-size: 1.12rem; color: var(--muted); max-width: 62ch; margin: 0; }
.notice {
  margin: 28px 0 0; padding: 16px 18px; border-radius: var(--radius);
  background: var(--accent-soft); border: 1px solid var(--border);
  font-size: .93rem; color: var(--text);
}
.notice strong { color: var(--accent); }
section { margin-top: 56px; }
h2 { font-size: 1.5rem; margin: 0 0 6px; letter-spacing: -.01em; }
h2 .num { color: var(--muted); font-variant-numeric: tabular-nums; margin-right: 10px; font-weight: 400; }
.sub { color: var(--muted); margin: 0 0 22px; max-width: 70ch; }
.card {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 22px; box-shadow: var(--shadow);
}
.grid { display: grid; gap: 16px; }
.grid-2 { grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); }
.grid-3 { grid-template-columns: repeat(auto-fit, minmax(252px, 1fr)); }
.grid-predictions { grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); }
.balls { display: flex; gap: 6px; flex-wrap: wrap; margin: 14px 0 10px; }
.ball {
  display: grid; place-items: center; width: 36px; height: 36px; border-radius: 50%;
  background: var(--surface-alt); border: 1px solid var(--border);
  font-weight: 600; font-variant-numeric: tabular-nums; font-size: .95rem;
}
.ball-chance { background: var(--chance); border-color: var(--chance); color: #fff; }
.plus { display: grid; place-items: center; height: 36px; color: var(--muted); font-size: 1.1rem; }
.pred-title { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
.pred-title h3 { margin: 0; font-size: .98rem; }
.tag { font-size: .72rem; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); white-space: nowrap; }
.pred-why { font-size: .88rem; color: var(--muted); margin: 0; }
.stat { display: flex; flex-direction: column; gap: 2px; }
.stat .value { font-size: 1.9rem; font-weight: 650; letter-spacing: -.02em; font-variant-numeric: tabular-nums; }
.stat .label { font-size: .84rem; color: var(--muted); }
.chart { width: 100%; height: auto; display: block; margin: 8px 0 4px; overflow: visible; }
.chart-fixed { width: auto; max-width: none; height: auto; }
.bar { fill: var(--accent); opacity: .82; }
.bar-strong { fill: var(--chance); opacity: 1; }
.bar-positive { fill: var(--positive); }
.bar-negative { fill: var(--negative); }
.chart-ref { stroke: var(--muted); stroke-width: 1; stroke-dasharray: 4 4; opacity: .7; }
.chart-ref-label, .chart-axis {
  fill: var(--muted); font-size: 13px; font-family: inherit;
}
.chart-label, .chart-value { fill: var(--text); font-size: 12px; font-family: inherit; }
.chart-label { fill: var(--muted); }
.spark-line { fill: none; stroke: var(--accent); stroke-width: 1.6; }
table { width: 100%; border-collapse: collapse; font-size: .9rem; }
.scroll-x { overflow-x: auto; }
th, td { padding: 9px 10px; text-align: right; border-bottom: 1px solid var(--border); white-space: nowrap; }
th:first-child, td:first-child { text-align: left; white-space: normal; }
thead th { color: var(--muted); font-weight: 500; font-size: .8rem; text-transform: uppercase; letter-spacing: .05em; }
tbody tr:last-child td { border-bottom: none; }
td.num, th.num { font-variant-numeric: tabular-nums; }
.pos { color: var(--positive); } .neg { color: var(--negative); }
.verdict {
  border-left: 3px solid var(--accent); padding: 4px 0 4px 18px; margin: 20px 0 0;
  font-size: 1.05rem;
}
footer { margin-top: 72px; padding-top: 24px; border-top: 1px solid var(--border); color: var(--muted); font-size: .86rem; }
footer a { color: var(--accent); }
.mono { font-variant-numeric: tabular-nums; }
"""


def _special_notice(last: date, target: date) -> str:
    """Encart signalant un Super Loto qui s'intercale avant le tirage régulier."""
    friday = next_friday_13(last)
    if not friday or friday >= target:
        return ""
    return (
        '<div class="notice" style="margin:0 0 22px">'
        f'<strong>Un Super Loto s\'intercale le {escape(format_date(friday))}.</strong> '
        "Les tirages exceptionnels s'ajoutent au calendrier sans le remplacer, et "
        "depuis 2019 les treize vendredis 13 en ont tous eu un. Les grilles "
        "ci-dessous valent pour lui exactement autant que pour le tirage régulier : "
        "mêmes 49 boules, même machine, mêmes probabilités.</div>"
    )


def _section_predictions(
    predictions: Sequence[Prediction],
    target: date,
    seed: str,
    last_date: date,
) -> str:
    cards = []
    for prediction in predictions:
        cards.append(
            '<article class="card">'
            f'<div class="pred-title"><h3>{escape(prediction.label)}</h3>'
            f'<span class="tag">{escape(prediction.strategy)}</span></div>'
            f'{_balls_html(prediction.balls, prediction.chance)}'
            f'<p class="pred-why">{escape(prediction.rationale)}</p>'
            '</article>'
        )
    return f"""
<section id="predictions">
  <h2><span class="num">01</span>Les grilles du prochain tirage</h2>
  <p class="sub">Quatre méthodes, quatre grilles pour le tirage du
  <strong>{escape(format_date(target))}</strong>. Elles sont reproductibles :
  même historique, même graine <code>{escape(seed)}</code>, mêmes numéros. Et
  toutes ont exactement la même probabilité de sortir — une sur 19 068 840.
  Chaque méthode choisit son numéro chance selon sa propre logique, la même que
  pour les boules ; il n'y en a que dix, alors deux grilles peuvent parfaitement
  tomber sur le même.</p>
  {_special_notice(last_date, target)}
  <div class="grid grid-predictions">{''.join(cards)}</div>
</section>"""


def _section_last_draw(draw: Draw, previous: Sequence[Draw]) -> str:
    rows = []
    for rank, label in RANK_LABELS.items():
        winners, payout = draw.ranks.get(rank, (0, 0.0))
        rows.append(
            f"<tr><td>{escape(label)}</td>"
            f'<td class="num">{_fmt(winners)}</td>'
            f'<td class="num">{_fmt(payout, 2)} €</td></tr>'
        )
    jackpots = [d.ranks.get(1, (0, 0.0))[1] for d in previous[-60:] if d.ranks]
    spark = charts.sparkline(jackpots) if len(jackpots) > 5 else ""
    winners_total = sum(winners for winners, _ in draw.ranks.values())
    redistributed = sum(winners * payout for winners, payout in draw.ranks.values())
    return f"""
<section id="dernier">
  <h2><span class="num">02</span>Le dernier tirage</h2>
  <p class="sub">Résultat officiel du {escape(format_date(draw.date))}, tel que publié par la FDJ.</p>
  <div class="grid grid-2">
    <div class="card">
      {_balls_html(draw.balls, draw.chance)}
      <div class="scroll-x"><table>
        <thead><tr><th>Rang</th><th class="num">Gagnants</th><th class="num">Rapport</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table></div>
    </div>
    <div class="card">
      <div class="stat"><span class="value">{_fmt(draw.ranks.get(1, (0, 0.0))[1])} €</span>
      <span class="label">cagnotte du rang 1 à ce tirage</span></div>
      {spark}
      <p class="pred-why">Évolution du rang 1 sur les {len(jackpots)} derniers tirages.
      Les paliers correspondent aux jackpots remportés, qui remettent la cagnotte à zéro.</p>
      <div class="grid grid-2" style="margin-top:18px">
        <div class="stat"><span class="value mono">{_fmt(winners_total)}</span>
          <span class="label">gagnants, tous rangs confondus</span></div>
        <div class="stat"><span class="value mono">{_fmt(redistributed)} €</span>
          <span class="label">redistribués sur ce seul tirage</span></div>
      </div>
    </div>
  </div>
</section>"""


def _section_randomness(
    ball_chi: ChiSquareResult,
    chance_chi: ChiSquareResult,
    balls: Sequence[NumberStats],
    shape: ShapeStats,
    repeat: float,
    n_draws: int,
) -> str:
    hottest = sorted(balls, key=lambda s: -s.count)[:3]
    coldest = sorted(balls, key=lambda s: s.count)[:3]
    data = [(str(s.number), float(s.count)) for s in balls]
    expected = balls[0].expected if balls else 0.0
    highlight = {str(s.number) for s in hottest} | {str(s.number) for s in coldest}
    return f"""
<section id="hasard">
  <h2><span class="num">03</span>Le verdict du khi-deux</h2>
  <p class="sub">Si une boule sortait vraiment plus souvent qu'une autre, un test
  d'adéquation à la loi uniforme le détecterait. Voici ce test, sur les
  {_fmt(n_draws)} tirages de l'ère actuelle.</p>
  <div class="card">
    {charts.bar_chart(data, expected=expected, height=220, highlight=sorted(highlight), unit=" sorties")}
    <p class="pred-why">Nombre de sorties par numéro. En pointillé, l'effectif attendu
    si le tirage est parfaitement uniforme. Les écarts que l'œil croit voir sont
    du bruit : c'est précisément ce que le test mesure.</p>
    <div class="grid grid-3" style="margin-top:18px">
      <div class="stat"><span class="value mono">{_fmt(ball_chi.statistic, 1)}</span>
        <span class="label">X² observé sur les 49 boules ({ball_chi.dof} degrés de liberté)</span></div>
      <div class="stat"><span class="value mono">{_fmt(100 * ball_chi.p_value, 1)} %</span>
        <span class="label">probabilité d'observer un tel écart si tout est uniforme</span></div>
      <div class="stat"><span class="value mono">{_fmt(100 * chance_chi.p_value, 1)} %</span>
        <span class="label">même test sur les 10 numéros chance</span></div>
    </div>
    <p class="verdict">Boules : <strong>{escape(ball_chi.verdict)}</strong>.
    Autrement dit, le numéro le plus « chaud » de l'histoire n'a rien de chaud.</p>
  </div>
  <div class="grid grid-2" style="margin-top:16px">
    <div class="card">
      <h3 style="margin-top:0;font-size:1rem">Ce qui ressemble à un signal</h3>
      <p class="pred-why">Les plus sortis : {escape(', '.join(f'{s.number} ({s.count})' for s in hottest))}.
      Les moins sortis : {escape(', '.join(f'{s.number} ({s.count})' for s in coldest))}.
      L'écart entre les deux extrêmes est du même ordre que celui qu'on obtient en
      lançant une pièce équilibrée assez longtemps.</p>
    </div>
    <div class="card">
      <h3 style="margin-top:0;font-size:1rem">La forme d'un tirage typique</h3>
      <p class="pred-why">Somme moyenne des cinq numéros : <strong>{_fmt(shape.mean_sum, 1)}</strong>
      (80 % des tirages entre {shape.sum_p10} et {shape.sum_p90}).
      En moyenne {_fmt(shape.mean_odd, 2)} numéros impairs, {_fmt(shape.mean_low, 2)} numéros
      inférieurs à 25, et {_fmt(shape.mean_consecutive, 2)} paire de numéros qui se suivent.
      Un tirage partage en moyenne <strong>{_fmt(repeat, 2)}</strong> numéro avec le
      précédent — la théorie prédit 0,51.</p>
      {charts.histogram(shape.sum_histogram, height=140)}
    </div>
  </div>
</section>"""


def _section_gaps(balls: Sequence[NumberStats], chances: Sequence[NumberStats]) -> str:
    late = sorted(balls, key=lambda s: -s.gap)[:10]
    rows = "".join(
        f'<tr><td class="num">{s.number}</td>'
        f'<td class="num">{s.gap}</td><td class="num">{_fmt(s.mean_gap, 1)}</td>'
        f'<td class="num">{s.max_gap}</td>'
        f'<td class="num">{s.last_seen.isoformat() if s.last_seen else "jamais"}</td></tr>'
        for s in late
    )
    chance_data = [(str(s.number), float(s.count)) for s in chances]
    return f"""
<section id="retards">
  <h2><span class="num">04</span>Les retardataires</h2>
  <p class="sub">Les numéros qu'on n'a pas vus depuis longtemps. Ils ne sont pas
  « dus » : la boule 17 ne sait pas qu'elle est absente depuis trente tirages.</p>
  <div class="grid grid-2">
    <div class="card scroll-x">
      <table>
        <thead><tr><th class="num">N°</th><th class="num">Retard</th><th class="num">Retard moyen</th>
        <th class="num">Record</th><th class="num">Dernière sortie</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
    <div class="card">
      <h3 style="margin-top:0;font-size:1rem">Numéros chance</h3>
      {charts.bar_chart(chance_data, expected=chances[0].expected if chances else None,
                        height=190, bar_width=26, gap=8, label_every=1, unit=" sorties")}
      <p class="pred-why">Dix numéros seulement, donc des effectifs plus gros et des
      écarts relatifs plus petits. Là encore, rien qui sorte du bruit.</p>
    </div>
  </div>
</section>"""


def _section_backtest(report: BacktestReport) -> str:
    rows = []
    for result in report.results:
        roi_class = "pos" if result.roi > 0 else "neg"
        significance = (
            "témoin" if result.key == "uniforme"
            else f"p = {_fmt(result.p_value_holm, 2)}"
        )
        rows.append(
            f"<tr><td>{escape(result.label)}</td>"
            f'<td class="num">{_fmt(result.mean_matches, 4)}</td>'
            f'<td class="num">{_fmt(100 * result.hit_rate, 1)} %</td>'
            f'<td class="num">{_fmt(result.stake, 0)} €</td>'
            f'<td class="num">{_fmt(result.winnings, 0)} €</td>'
            f'<td class="num {roi_class}">{_fmt(result.roi, 1)} %</td>'
            f'<td class="num">{significance}</td></tr>'
        )
    roi_data = [(r.label, r.roi) for r in report.results]
    verdict = (
        "Aucune stratégie ne se distingue statistiquement du hasard pur."
        if not report.any_significant
        else "Une stratégie s'écarte du hasard sur cette période, correction de "
             "Holm comprise. Relancez sur une autre fenêtre : l'écart ne tiendra pas."
    )
    return f"""
<section id="backtest">
  <h2><span class="num">05</span>Le backtest qui démolit tout</h2>
  <p class="sub">On rejoue les {report.draws_tested} derniers tirages
  ({escape(report.first_date)} → {escape(report.last_date)}). Pour chacun, chaque
  stratégie ne voit que le passé, produit {report.repeats} grilles, et on compte
  ce qu'elle aurait réellement gagné aux rapports officiels du jour. La
  comparaison au hasard est <strong>appariée tirage par tirage</strong> — trois
  grilles jouées sur la même cible ne sont pas trois observations indépendantes —
  et les p-values sont corrigées par <strong>Holm-Bonferroni</strong>, parce que
  trois comparaisons offrent trois occasions de crier au signal.</p>
  <div class="card">
    <div class="scroll-x"><table>
      <thead><tr><th>Stratégie</th><th class="num">Bons numéros / grille</th>
      <th class="num">Grilles gagnantes</th><th class="num">Mise</th>
      <th class="num">Gains</th><th class="num">Retour</th><th class="num">vs hasard</th></tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table></div>
    <p class="verdict">{escape(verdict)} L'espérance théorique est de 0,5102 bon
    numéro par grille, quelle que soit la méthode employée pour la remplir.</p>
  </div>
  <div class="card" style="margin-top:16px">
    <h3 style="margin-top:0;font-size:1rem">Retour sur mise, par stratégie</h3>
    <div class="scroll-x">{charts.diverging_bar_chart(roi_data)}</div>
    <p class="pred-why">Toutes négatives, toutes du même ordre. L'ordre du classement
    change à chaque nouveau tirage : c'est la signature du bruit, pas du talent.</p>
  </div>
</section>"""


def _section_crowd(
    model: CrowdModel,
    grids: Sequence[ContrarianGrid],
    chance_model: ChanceModel | None,
) -> str:
    rows = "".join(
        f"<tr><td>{escape(c.name)}</td>"
        f'<td class="num">{_fmt(c.value, 4)}</td>'
        f'<td class="num">{_fmt(c.t_stat, 1)}</td>'
        f'<td class="num">{"+" if c.effect_percent >= 0 else ""}{_fmt(c.effect_percent, 1)} %</td>'
        f'<td>{"oui" if c.significant else "non"}</td></tr>'
        for c in model.coefficients[1:]
    )
    cards = "".join(
        '<article class="card">'
        f'{_balls_html(grid.balls, grid.chance)}'
        f'<div class="stat"><span class="value mono pos">+{_fmt(grid.gain_percent_with_chance, 0)} %</span>'
        '<span class="label">de gain estimé aux rangs avec n° chance</span></div>'
        f'<p class="pred-why">+{_fmt(grid.gain_percent, 0)} % aux rangs qui ne '
        'dépendent que des cinq boules. Probabilité de sortie strictement inchangée.</p>'
        '</article>'
        for grid in grids
    )
    bias = model.date_bias
    chance_block = _chance_card(chance_model) if chance_model else ""
    corrected = (
        "Le témoin de volume est corrigé de la popularité du numéro chance tiré ; "
        "sans cette correction, l'erreur de mesure atténue tous les coefficients."
        if model.chance_corrected else ""
    )
    return f"""
<section id="foule">
  <h2><span class="num">06</span>Le seul avantage qui existe vraiment</h2>
  <p class="sub">On ne peut pas gagner plus souvent. On peut en revanche gagner
  plus <em>quand</em> on gagne, parce que les rangs du Loto sont à répartition et
  que les joueurs, eux, ne tirent pas au hasard. Deux biais, mesurés séparément.</p>
  {chance_block}
  <div class="card" style="margin-top:16px">
    <h3 style="margin-top:0;font-size:1rem">Les cinq boules : le biais des dates de naissance</h3>
    <p class="pred-why">Régression du nombre de gagnants au rang « {escape(RANK_LABELS[model.response_rank])} »
    sur la composition de la combinaison tirée, à volume de grilles vendues constant.
    {_fmt(model.observations)} tirages, {escape(model.period)}, R² = {_fmt(model.r_squared, 3)}.
    {escape(corrected)}</p>
    <div class="scroll-x"><table>
      <thead><tr><th>Variable</th><th class="num">Coefficient</th><th class="num">t</th>
      <th class="num">Effet par unité</th><th>Significatif</th></tr></thead>
      <tbody>{rows}</tbody>
    </table></div>
    <p class="verdict">Chaque numéro tiré inférieur ou égal à 31 augmente de
    <strong>{_fmt(bias.effect_percent, 1)} %</strong> le nombre de gagnants à ce rang
    (t = {_fmt(bias.t_stat, 1)}). Le biais des dates de naissance n'est pas une légende :
    il est massif, et il est mesurable.</p>
  </div>
  <h3 style="margin:26px 0 4px;font-size:1.05rem">Grilles à contre-courant</h3>
  <p class="sub">Mêmes chances de sortir que n'importe quelle autre combinaison,
  mais choisies pour être partagées avec le moins de monde possible — numéro
  chance compris.</p>
  <div class="grid grid-3">{cards}</div>
</section>"""


def _chance_card(model: ChanceModel) -> str:
    """Le biais du numéro chance : le plus fort des deux, et le plus simple à jouer."""
    rows = "".join(
        f'<tr><td class="num">{effect.number}</td>'
        f'<td class="num">{"+" if effect.effect_percent >= 0 else ""}'
        f'{_fmt(effect.effect_percent, 1)} %</td>'
        f'<td class="num">{_fmt(effect.t_stat, 1)}</td>'
        f'<td class="num {"pos" if effect.payout_multiplier > 1 else "neg"}">'
        f'{"+" if effect.payout_multiplier >= 1 else ""}'
        f'{_fmt(100 * (effect.payout_multiplier - 1), 1)} %</td></tr>'
        for effect in sorted(model.effects, key=lambda e: e.log_effect)
    )
    chart = charts.diverging_bar_chart(
        [(f"n° {e.number}", e.effect_percent)
         for e in sorted(model.effects, key=lambda e: e.log_effect)],
        positive_is_good=False,
    )
    best, worst = model.least_popular, model.most_popular
    return f"""
  <div class="card">
    <h3 style="margin-top:0;font-size:1rem">Le numéro chance : le biais le plus violent</h3>
    <p class="pred-why">Nombre de gagnants au rang « n° chance seul », rapporté au
    rang « 2 numéros » — lequel ne dépend pas du numéro chance et mesure donc le
    seul volume de grilles jouées. Tout écart restant vient des joueurs.
    {_fmt(model.observations)} tirages, {escape(model.period)}, R² = {_fmt(model.r_squared, 3)}.</p>
    <div class="grid grid-2">
      <div class="scroll-x"><table>
        <thead><tr><th class="num">N°</th><th class="num">Co-gagnants</th>
        <th class="num">t</th><th class="num">Gain si vous le jouez</th></tr></thead>
        <tbody>{rows}</tbody>
      </table></div>
      <div class="scroll-x">{chart}</div>
    </div>
    <p class="verdict">Quand le <strong>{worst.number}</strong> sort, il y a
    <strong>{_fmt(worst.effect_percent, 0)} %</strong> de gagnants en plus qu'un numéro
    chance moyen (t = {_fmt(worst.t_stat, 1)}) ; quand c'est le
    <strong>{best.number}</strong>, il y en a {_fmt(abs(best.effect_percent), 0)} % de moins.
    Jouer le {best.number} plutôt que le {worst.number} ne change strictement rien à
    vos chances de gagner, mais rapporte <strong>{_fmt(model.spread_percent, 0)} %</strong>
    de plus quand ça tombe. C'est la ligne la plus rentable de tout ce site.</p>
  </div>"""


def _section_economics(economics: Economics) -> str:
    rows = "".join(
        f"<tr><td>{escape(row.label)}</td>"
        f'<td class="num">1 sur {_fmt(row.odds)}</td>'
        f'<td class="num">{_fmt(row.mean_payout, 2)} €</td>'
        f'<td class="num">{_fmt(row.contribution, 4)} €</td></tr>'
        for row in economics.rows
    )
    jackpot_odds = 1 / rank_probability(1)
    return f"""
<section id="economie">
  <h2><span class="num">07</span>Ce que coûte vraiment une grille</h2>
  <p class="sub">Espérance de gain calculée non pas sur des règles théoriques mais
  sur les rapports réellement versés par la FDJ, tirage par tirage
  ({escape(economics.period)}, {_fmt(economics.draws_used)} tirages).</p>
  <div class="card">
    <div class="scroll-x"><table>
      <thead><tr><th>Rang</th><th class="num">Probabilité</th>
      <th class="num">Rapport moyen</th><th class="num">Apport à l'espérance</th></tr></thead>
      <tbody>{rows}</tbody>
    </table></div>
    <div class="grid grid-3" style="margin-top:20px">
      <div class="stat"><span class="value mono">{_fmt(economics.expected_value, 2)} €</span>
        <span class="label">espérance de gain pour {_fmt(GRID_PRICE, 2)} € misés</span></div>
      <div class="stat"><span class="value mono neg">−{_fmt(economics.loss_per_grid, 2)} €</span>
        <span class="label">perte moyenne par grille jouée</span></div>
      <div class="stat"><span class="value mono">{_fmt(economics.house_edge, 1)} %</span>
        <span class="label">part de la mise qui ne revient jamais aux joueurs</span></div>
    </div>
    <p class="verdict">Une chance sur {_fmt(jackpot_odds)} de décrocher le rang 1.
    À trois grilles par semaine, il faudrait en moyenne
    <strong>{_fmt(years_of_playing(rank_probability(1)))} ans</strong> pour l'atteindre,
    et il faudrait jouer {_fmt(grids_for_certainty(rank_probability(1)))} grilles pour
    avoir une chance sur deux d'y arriver au moins une fois.</p>
  </div>
</section>"""


def build_html(
    *,
    predictions: Sequence[Prediction],
    target_date: date,
    seed: str,
    last_draw: Draw,
    draws: Sequence[Draw],
    ball_chi: ChiSquareResult,
    chance_chi: ChiSquareResult,
    ball_stats_: Sequence[NumberStats],
    chance_stats_: Sequence[NumberStats],
    shape: ShapeStats,
    repeat: float,
    backtest_report: BacktestReport,
    crowd_model: CrowdModel | None,
    chance_model: ChanceModel | None,
    contrarian: Sequence[ContrarianGrid],
    economics: Economics,
    generated_at: datetime,
) -> str:
    crowd_section = (
        _section_crowd(crowd_model, contrarian, chance_model) if crowd_model else ""
    )
    stamp = generated_at.strftime("%d/%m/%Y à %H:%M UTC")
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Alex Machina — l'oracle honnête du Loto</title>
<meta name="description" content="Analyse statistique complète de l'historique du Loto français, prédictions assumées comme inutiles, et démonstration chiffrée qu'aucune méthode ne bat le hasard.">
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header class="hero">
  <p class="eyebrow">Loto français · {_fmt(len(draws))} tirages analysés</p>
  <h1>Alex <span class="machina">Machina</span></h1>
  <p class="lede">Une machine qui prédit les numéros du Loto, et qui démontre
  méthodiquement, sur cinquante ans de données officielles, que sa propre
  prédiction ne vaut rien.</p>
  <div class="notice"><strong>À lire avant tout le reste.</strong> {escape(DISCLAIMER)}</div>
</header>
{_section_predictions(predictions, target_date, seed, last_draw.date)}
{_section_last_draw(last_draw, draws)}
{_section_randomness(ball_chi, chance_chi, ball_stats_, shape, repeat, len(draws))}
{_section_gaps(ball_stats_, chance_stats_)}
{_section_backtest(backtest_report)}
{crowd_section}
{_section_economics(economics)}
<footer>
  <p>Mis à jour automatiquement le {stamp}, après chaque tirage, à partir des
  archives officielles de la Française des Jeux.
  Code source et méthode : <a href="https://github.com/KlayaR/alex-machina">github.com/KlayaR/alex-machina</a>.
  Données brutes : <a href="data/latest.json">latest.json</a>.</p>
  <p>Le jeu comporte des risques : endettement, isolement, dépendance.
  Interdit aux mineurs. Pour en parler : <strong>09 74 75 13 13</strong> (appel non surtaxé)
  ou <a href="https://www.joueurs-info-service.fr">joueurs-info-service.fr</a>.</p>
</footer>
</div>
</body>
</html>
"""


def build_json(
    *,
    predictions: Sequence[Prediction],
    target_date: date,
    last_draw: Draw,
    ball_stats_: Sequence[NumberStats],
    ball_chi: ChiSquareResult,
    backtest_report: BacktestReport,
    contrarian: Sequence[ContrarianGrid],
    economics: Economics,
    total_draws: int,
    generated_at: datetime,
    chance_model: ChanceModel | None = None,
) -> dict:
    """Flux machine, volontairement plat et stable."""
    return {
        "genere_le": generated_at.isoformat(timespec="seconds"),
        "avertissement": DISCLAIMER,
        "tirages_analyses": total_draws,
        "dernier_tirage": {
            "date": last_draw.date.isoformat(),
            "jour": last_draw.weekday,
            "boules": list(last_draw.balls),
            "chance": last_draw.chance,
            "rapports": {str(k): {"gagnants": v[0], "rapport": v[1]}
                         for k, v in sorted(last_draw.ranks.items())},
        },
        "prochain_tirage": target_date.isoformat(),
        "predictions": [
            {
                "strategie": p.strategy,
                "libelle": p.label,
                "boules": list(p.balls),
                "chance": p.chance,
                "probabilite_rang1": rank_probability(1),
            }
            for p in predictions
        ],
        "grilles_contre_courant": [
            {
                "boules": list(g.balls),
                "chance": g.chance,
                "co_gagnants_relatifs": round(g.crowd_score, 4),
                "gain_relatif": round(g.payout_multiplier, 4),
                "gain_relatif_avec_chance": round(g.payout_multiplier_with_chance, 4),
            }
            for g in contrarian
        ],
        "biais_numero_chance": None if chance_model is None else {
            "tirages": chance_model.observations,
            "periode": chance_model.period,
            "numeros": [
                {
                    "numero": e.number,
                    "co_gagnants_relatifs": round(e.popularity, 4),
                    "effet_pct": round(e.effect_percent, 2),
                    "t": round(e.t_stat, 2),
                    "gain_si_joue_pct": round(100 * (e.payout_multiplier - 1), 2),
                }
                for e in sorted(chance_model.effects, key=lambda e: e.log_effect)
            ],
        },
        "uniformite": {
            "khi2": round(ball_chi.statistic, 3),
            "ddl": ball_chi.dof,
            "p_value": round(ball_chi.p_value, 4),
            "verdict": ball_chi.verdict,
        },
        "frequences": {str(s.number): s.count for s in ball_stats_},
        "retards": {str(s.number): s.gap for s in ball_stats_},
        "backtest": {
            "periode": [backtest_report.first_date, backtest_report.last_date],
            "tirages": backtest_report.draws_tested,
            "resultats": [
                {
                    "strategie": r.key,
                    "grilles": r.grids,
                    "bons_numeros_moyens": round(r.mean_matches, 4),
                    "taux_grilles_gagnantes": round(r.hit_rate, 4),
                    "retour_sur_mise_pct": round(r.roi, 2),
                    "p_value_vs_hasard": round(r.p_value, 4),
                    "p_value_holm": round(r.p_value_holm, 4),
                }
                for r in backtest_report.results
            ],
        },
        "economie": {
            "prix_grille": GRID_PRICE,
            "esperance_gain": round(economics.expected_value, 4),
            "perte_moyenne": round(economics.loss_per_grid, 4),
            "taux_de_retour_pct": round(100 - economics.house_edge, 2),
        },
    }


def write(output_dir: Path | str, html: str, payload: dict) -> tuple[Path, Path]:
    output_dir = Path(output_dir)
    (output_dir / "data").mkdir(parents=True, exist_ok=True)
    index = output_dir / "index.html"
    feed = output_dir / "data" / "latest.json"
    index.write_text(_typography(html), encoding="utf-8")
    feed.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return index, feed
