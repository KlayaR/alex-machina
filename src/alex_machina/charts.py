"""Graphiques SVG écrits à la main, sans aucune dépendance.

Le tableau de bord est un fichier HTML unique servi par GitHub Pages : pas de
CDN, pas de bundler, pas de JavaScript de rendu. Les graphiques sont donc du SVG
généré côté Python, qui hérite des couleurs de la page via ``currentColor`` et
les variables CSS — ce qui les rend automatiquement lisibles en thème clair
comme en thème sombre.
"""

from __future__ import annotations

import html
from collections.abc import Sequence


def _escape(text: object) -> str:
    return html.escape(str(text), quote=True)


def _format(value: float, digits: int = 0) -> str:
    return f"{value:,.{digits}f}".replace(",", " ").replace(".", ",")


def bar_chart(
    data: Sequence[tuple[str, float]],
    *,
    expected: float | None = None,
    height: int = 200,
    bar_width: int = 14,
    gap: int = 3,
    label_every: int = 5,
    highlight: Sequence[str] = (),
    value_digits: int = 0,
    unit: str = "",
) -> str:
    """Diagramme en barres verticales avec ligne de référence optionnelle."""
    if not data:
        return ""
    highlighted = set(highlight)
    top, bottom, left = 14, 26, 8
    plot_height = height - top - bottom
    width = left * 2 + len(data) * (bar_width + gap) - gap
    ceiling = max(max(value for _, value in data), expected or 0) * 1.08 or 1.0

    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="xMidYMid meet" role="img">'
    ]
    if expected is not None:
        y = top + plot_height * (1 - expected / ceiling)
        parts.append(
            f'<line class="chart-ref" x1="{left}" x2="{width - left}" y1="{y:.1f}" y2="{y:.1f}"/>'
            f'<text class="chart-ref-label" x="{width - left}" y="{y - 4:.1f}" '
            f'text-anchor="end">attendu : {_format(expected, 1)}</text>'
        )
    for index, (label, value) in enumerate(data):
        bar_height = max(1.0, plot_height * value / ceiling)
        x = left + index * (bar_width + gap)
        y = top + plot_height - bar_height
        css = "bar bar-strong" if label in highlighted else "bar"
        parts.append(
            f'<rect class="{css}" x="{x}" y="{y:.1f}" width="{bar_width}" '
            f'height="{bar_height:.1f}" rx="2">'
            f'<title>{_escape(label)} : {_format(value, value_digits)}{_escape(unit)}</title>'
            f'</rect>'
        )
        if index % label_every == 0 or label in highlighted:
            parts.append(
                f'<text class="chart-axis" x="{x + bar_width / 2:.1f}" '
                f'y="{height - 8}" text-anchor="middle">{_escape(label)}</text>'
            )
    parts.append("</svg>")
    return "".join(parts)


def diverging_bar_chart(
    data: Sequence[tuple[str, float]],
    *,
    height: int = 220,
    row_height: int = 28,
    unit: str = " %",
    digits: int = 1,
    positive_is_good: bool = True,
) -> str:
    """Barres horizontales signées, à largeur fixe.

    Contrairement aux barres verticales, ce graphique porte des libellés et des
    valeurs qu'il faut pouvoir lire. Il ne se laisse donc pas réduire : sur un
    écran étroit il défile horizontalement dans son conteneur, exactement comme
    un tableau trop large.
    """
    if not data:
        return ""
    label_width, value_width, padding = 132, 74, 8
    plot_width = 340
    width = label_width + plot_width + value_width
    height = padding * 2 + row_height * len(data)
    span = max(abs(value) for _, value in data) or 1.0

    # Quand toutes les valeurs vont dans le même sens, inutile de gaspiller la
    # moitié du graphique : l'origine se cale sur le bord concerné.
    values = [value for _, value in data]
    if all(v >= 0 for v in values):
        zero, usable = label_width, plot_width
    elif all(v <= 0 for v in values):
        zero, usable = label_width + plot_width, plot_width
    else:
        zero, usable = label_width + plot_width / 2, plot_width / 2

    parts = [
        f'<svg class="chart chart-fixed" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img">',
        f'<line class="chart-ref" x1="{zero}" x2="{zero}" y1="{padding}" '
        f'y2="{height - padding}"/>',
    ]
    for index, (label, value) in enumerate(data):
        y = padding + index * row_height
        length = usable * abs(value) / span
        x = zero if value >= 0 else zero - length
        # Le signe ne dit pas si c'est une bonne nouvelle : plus de co-gagnants,
        # c'est un chiffre positif et un moins bon gain.
        favourable = (value >= 0) == positive_is_good
        css = "bar bar-positive" if favourable else "bar bar-negative"
        parts.append(
            f'<text class="chart-label" x="{label_width - 10}" y="{y + row_height / 2 + 4:.1f}" '
            f'text-anchor="end">{_escape(label)}</text>'
            f'<rect class="{css}" x="{x:.1f}" y="{y + 5:.1f}" width="{max(length, 1):.1f}" '
            f'height="{row_height - 12}" rx="2"/>'
            f'<text class="chart-value" x="{width - 10}" y="{y + row_height / 2 + 4:.1f}" '
            f'text-anchor="end">{_format(value, digits)}{_escape(unit)}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def histogram(buckets: dict[int, int], *, label_suffix: str = "", height: int = 160) -> str:
    """Histogramme simple à partir d'un dictionnaire ``valeur → effectif``."""
    data = [(f"{key}{label_suffix}", float(value)) for key, value in sorted(buckets.items())]
    return bar_chart(data, height=height, bar_width=18, gap=4, label_every=2)


def sparkline(values: Sequence[float], *, width: int = 320, height: int = 48) -> str:
    """Courbe compacte, sans axes, pour montrer une tendance."""
    if len(values) < 2:
        return ""
    low, high = min(values), max(values)
    span = (high - low) or 1.0
    step = width / (len(values) - 1)
    points = " ".join(
        f"{index * step:.1f},{height - (value - low) / span * (height - 6) - 3:.1f}"
        for index, value in enumerate(values)
    )
    return (
        f'<svg class="chart sparkline" viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="none" role="img">'
        f'<polyline class="spark-line" points="{points}"/></svg>'
    )
