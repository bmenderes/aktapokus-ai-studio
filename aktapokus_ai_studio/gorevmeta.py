"""Gorev (konusma) bilgileri: sabitleme, arsivleme, okunmadi isareti, ozel ad.

Kullanici klasorunde saklanir (`~/.aktapokus/gorev-meta.json`, AKTAPOKUS_GOREV_META ile degistirilir), proje kimligine gore. Proje klasorunden ASLA
okunmaz: klonlanan bir depo, gorev listesini gizleyemez/yeniden adlandiramaz. Gorev kayitlarinin kendisi (.aktapokus/kayit) degismez."""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path

KAYIT_ORTAMI = "AKTAPOKUS_GOREV_META"
KIMLIK_DESENI = re.compile(r"[0-9a-zA-Z_-]{1,64}")
PROJE_DESENI = re.compile(r"[0-9a-f]{10}")
BOOL_ALANLAR = ("sabit", "arsiv", "okunmadi")
AZAMI_AD = 120
AZAMI_GOREV = 2000
_kilit = threading.Lock()


class GorevMetaHatasi(Exception):
    pass


def dosya_yolu() -> Path:
    ortam = os.environ.get(KAYIT_ORTAMI)
    return Path(ortam) if ortam else Path.home() / ".aktapokus" / "gorev-meta.json"


def _yukle() -> dict:
    try:
        veri = json.loads(dosya_yolu().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return veri if isinstance(veri, dict) else {}


def _yaz(veri: dict) -> None:
    yol = dosya_yolu()
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_suffix(".tmp")
    gecici.write_text(json.dumps(veri, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(gecici, yol)


def proje_icin(proje: str) -> dict:
    """{gorev_kimligi: {sabit, arsiv, okunmadi, ad}} (yalniz dolu alanlar)."""
    p = _yukle().get(proje)
    if not isinstance(p, dict):
        return {}
    sonuc = {}
    for gid, m in p.items():
        if isinstance(gid, str) and KIMLIK_DESENI.fullmatch(gid) and isinstance(m, dict):
            temiz = {k: True for k in BOOL_ALANLAR if m.get(k) is True}
            if isinstance(m.get("ad"), str) and m["ad"].strip() and len(m["ad"]) <= AZAMI_AD and "\n" not in m["ad"]:
                temiz["ad"] = m["ad"].strip()
            if temiz:
                sonuc[gid] = temiz
    return sonuc


def ayarla(proje: object, gorev: object, **alanlar) -> dict:
    if not isinstance(proje, str) or not PROJE_DESENI.fullmatch(proje):
        raise GorevMetaHatasi("Gecersiz proje kimligi")
    if not isinstance(gorev, str) or not KIMLIK_DESENI.fullmatch(gorev):
        raise GorevMetaHatasi("Gecersiz gorev kimligi")
    bilinmeyen = set(alanlar) - {*BOOL_ALANLAR, "ad"}
    if bilinmeyen or not alanlar:
        raise GorevMetaHatasi("Gecerli alanlar: sabit, arsiv, okunmadi, ad")
    for k in BOOL_ALANLAR:
        if k in alanlar and not isinstance(alanlar[k], bool):
            raise GorevMetaHatasi(f"'{k}' true/false olmali")
    if "ad" in alanlar:
        ad = alanlar["ad"]
        if not isinstance(ad, str) or len(ad.strip()) > AZAMI_AD or any(c in ad for c in "\n\r\x00"):
            raise GorevMetaHatasi(f"'ad' tek satirlik, en cok {AZAMI_AD} karakterlik metin olmali (bos = varsayilan ad)")
        alanlar["ad"] = ad.strip()
    with _kilit:
        veri = _yukle()
        p = veri.setdefault(proje, {})
        if not isinstance(p, dict):
            p = veri[proje] = {}
        if gorev not in p and len(p) >= AZAMI_GOREV:
            raise GorevMetaHatasi(f"Bir projede en cok {AZAMI_GOREV} gorev bilgisi tutulur")
        m = p.setdefault(gorev, {})
        for k, v in alanlar.items():
            if v in (False, ""):
                m.pop(k, None)
            else:
                m[k] = v
        sonuc = dict(m)
        if not m:
            del p[gorev]
        if not p:
            veri.pop(proje, None)
        _yaz(veri)
        return sonuc


def sil(proje: str, gorev: str) -> None:
    with _kilit:
        veri = _yukle()
        p = veri.get(proje)
        if isinstance(p, dict) and gorev in p:
            del p[gorev]
            if not p:
                veri.pop(proje, None)
            _yaz(veri)
