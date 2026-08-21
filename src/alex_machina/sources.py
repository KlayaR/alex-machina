"""Téléchargement des archives officielles de résultats FDJ.

La FDJ publie l'historique complet du Loto sous forme d'archives ZIP contenant
un CSV (séparateur ``;``, encodage latin-1). Les archives sont découpées par
« ère » de règles du jeu. Seule la dernière est mise à jour après chaque tirage.

Deux points d'accès existent pour le même fichier :

* l'API ``sto.api.fdj.fr`` — celle qu'utilise le site fdj.fr, tenue à jour ;
* le miroir CDN ``media.fdj.fr`` — parfois figé plusieurs mois en arrière.

On interroge donc l'API en premier et le CDN en repli.
"""

from __future__ import annotations

import hashlib
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

API_BASE = "https://www.sto.api.fdj.fr/anonymous/service-draw-info/v3/documentations"
API_PREFIX = "1a2b3c4d-9876-4562-b3fc-2c963f66"
CDN_BASE = "https://media.fdj.fr/static-draws/csv/loto"

USER_AGENT = "alex-machina/0.1 (+https://github.com/KlayaR/alex-machina)"


@dataclass(frozen=True)
class Archive:
    """Une archive d'historique FDJ."""

    name: str
    api_suffix: str
    era: str
    period: str
    live: bool = False

    @property
    def api_url(self) -> str:
        return f"{API_BASE}/{API_PREFIX}{self.api_suffix}"

    @property
    def cdn_url(self) -> str:
        return f"{CDN_BASE}/{self.name}.zip"


#: Les cinq archives couvrant l'intégralité de l'histoire du Loto français.
#: ``live=True`` marque celle qui reçoit les nouveaux tirages.
ARCHIVES: tuple[Archive, ...] = (
    Archive("loto", "afl6", "6/49", "1976-05-19 → 2008-10-04"),
    Archive("nouveau_loto", "afm6", "5/49", "2008-10-06 → 2017-03-04"),
    Archive("loto2017", "afn6", "5/49", "2017-03-06 → 2019-02-25"),
    Archive("loto_201902", "afo6", "5/49", "2019-02-27 → 2019-11-02"),
    Archive("loto_201911", "afp6", "5/49", "2019-11-06 → aujourd'hui", live=True),
)

LIVE_ARCHIVE = ARCHIVES[-1]


class FetchError(RuntimeError):
    """Impossible de récupérer une archive depuis toutes les sources connues."""


def _get(url: str, timeout: float = 60.0) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def download(archive: Archive, *, retries: int = 3, timeout: float = 60.0) -> bytes:
    """Renvoie le ZIP brut, en essayant l'API puis le miroir CDN."""
    errors: list[str] = []
    for url in (archive.api_url, archive.cdn_url):
        for attempt in range(retries):
            try:
                payload = _get(url, timeout=timeout)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                errors.append(f"{url} (essai {attempt + 1}): {exc}")
                time.sleep(1.5 * (attempt + 1))
                continue
            if payload[:2] != b"PK":
                errors.append(f"{url}: réponse non-ZIP ({len(payload)} octets)")
                break
            return payload
    raise FetchError(f"archive {archive.name} indisponible :\n  " + "\n  ".join(errors))


def extract_csv(payload: bytes) -> str:
    """Extrait l'unique CSV d'une archive et le décode en latin-1."""
    with zipfile.ZipFile(BytesIO(payload)) as bundle:
        names = [n for n in bundle.namelist() if n.lower().endswith(".csv")]
        if not names:
            raise FetchError("archive sans fichier CSV")
        return bundle.read(names[0]).decode("latin-1")


def fetch(archive: Archive, *, cache_dir: Path | None = None) -> str:
    """Télécharge et décode une archive, avec cache disque optionnel.

    Le cache sert au développement local et aux tests ; le job de mise à jour
    passe outre pour l'archive vivante afin de toujours voir le dernier tirage.
    """
    payload = download(archive)
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(payload).hexdigest()[:12]
        (cache_dir / f"{archive.name}-{digest}.zip").write_bytes(payload)
    return extract_csv(payload)
