"""Tests d'intégration : ils sortent sur le réseau, donc ils sont optionnels.

Lancer avec ``ALEX_MACHINA_NETWORK_TESTS=1 pytest`` pour vérifier que la FDJ
n'a pas changé ses URL ni le format de ses fichiers.
"""

import os
from datetime import date

import pytest

from alex_machina.ingest import parse_csv
from alex_machina.sources import ARCHIVES, LIVE_ARCHIVE, download, extract_csv

pytestmark = pytest.mark.skipif(
    not os.environ.get("ALEX_MACHINA_NETWORK_TESTS"),
    reason="test réseau désactivé (ALEX_MACHINA_NETWORK_TESTS=1 pour l'activer)",
)


def test_every_archive_url_still_serves_a_zip():
    for archive in ARCHIVES:
        payload = download(archive)
        assert payload[:2] == b"PK", archive.name
        assert extract_csv(payload).startswith("annee_numero_de_tirage")


def test_live_archive_is_actually_up_to_date():
    draws = parse_csv(extract_csv(download(LIVE_ARCHIVE)))
    assert len(draws) > 1000
    latest = max(d.date for d in draws)
    # Trois tirages par semaine : au-delà de dix jours, la source a décroché.
    assert (date.today() - latest).days < 10, f"dernier tirage publié : {latest}"
