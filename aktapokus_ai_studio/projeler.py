"""Bilinen projeler kayit defteri: `~/.aktapokus/projeler.json` (AKTAPOKUS_PROJELER ile degistirilir).

Bir klasor ARAYUZDEN ya da Telegram'dan secildiginde otomatik eklenir/guncellenir; en son kullanilan en ustte. Arayuzdeki ortam cipi ve
"son projeler" listesi bunu kullanir. Kayit defterinden SILMEK klasore dokunmaz (yalniz listeyi unutur). Bu defter, ileride cok projeli
calisma (ayni anda birkac proje) icin projenin kalici kimligidir: kimlik, normallestirilmis yolun ozetidir."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

KAYIT_ORTAMI = "AKTAPOKUS_PROJELER"
AZAMI_PROJE = 60


def kayit_yolu() -> Path:
    ortam = os.environ.get(KAYIT_ORTAMI)
    return Path(ortam) if ortam else Path.home() / ".aktapokus" / "projeler.json"


def _normal(yol: str | Path) -> str:
    try:
        return str(Path(yol).expanduser().resolve())
    except OSError:
        return str(yol)


def proje_kimligi(yol: str | Path) -> str:
    normal = _normal(yol)
    if os.name == "nt":  # Windows'ta C:\Proje ile c:\proje ayni klasor; Linux/Mac'te farkli olabilir
        normal = normal.lower()
    return hashlib.sha1(normal.encode("utf-8")).hexdigest()[:10]


def _oku() -> list[dict]:
    try:
        ham = json.loads(kayit_yolu().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    sonuc: list[dict] = []
    gorulen: set[str] = set()
    for oge in ham.get("projeler", []) if isinstance(ham, dict) else []:
        if not isinstance(oge, dict) or not isinstance(oge.get("yol"), str) or not oge["yol"].strip():
            continue
        kimlik = proje_kimligi(oge["yol"])
        if kimlik in gorulen:
            continue
        gorulen.add(kimlik)
        son = oge.get("son")
        sonuc.append({"id": kimlik, "ad": str(oge.get("ad") or Path(oge["yol"]).name), "yol": oge["yol"], "son": float(son) if isinstance(son, (int, float)) else 0.0})
    sonuc.sort(key=lambda p: -p["son"])
    return sonuc


def _yaz(projeler: list[dict]) -> None:
    yol = kayit_yolu()
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_suffix(".tmp")
    gecici.write_text(json.dumps({"surum": 1, "projeler": [{"ad": p["ad"], "yol": p["yol"], "son": p["son"]} for p in projeler]}, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(gecici, yol)


def listele() -> list[dict]:
    """En son kullanilan en ustte. 'var': klasor hala diskte mi."""
    return [{**p, "var": Path(p["yol"]).is_dir()} for p in _oku()]


def ekle_veya_guncelle(yol: str | Path, simdi: float | None = None) -> dict:
    """Projeyi ekler (ya da 'son kullanim' zamanini yeniler). Kayit defteri bozuksa yeniden kurulur; en eski girdiler AZAMI_PROJE'yi asinca silinir."""
    normal = _normal(yol)
    kimlik = proje_kimligi(normal)
    projeler = [p for p in _oku() if p["id"] != kimlik]
    yeni = {"id": kimlik, "ad": Path(normal).name or normal, "yol": normal, "son": simdi if simdi is not None else time.time()}
    projeler.insert(0, yeni)
    projeler.sort(key=lambda p: -p["son"])
    _yaz(projeler[:AZAMI_PROJE])
    return yeni


def sil(kimlik: str) -> bool:
    """Yalniz listeden unutur; klasore DOKUNMAZ."""
    projeler = _oku()
    kalan = [p for p in projeler if p["id"] != kimlik]
    if len(kalan) == len(projeler):
        return False
    _yaz(kalan)
    return True
