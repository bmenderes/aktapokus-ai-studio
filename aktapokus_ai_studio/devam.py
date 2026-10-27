"""Kapanista gorev kurtarma: calisan/bekleyen gorev ve kuyruk `<proje>/.aktapokus/devam.json`'a yazilir; uygulama acilinca 'yarim kaldi' sorulur.

Dosya yalniz kullanicinin kendi projesinde ve `.aktapokus/` altindadir (git'e/anlik goruntuye girmez). Burada hicbir sey CALISTIRILMAZ:
'devam' yeni bir PLAN uretir (onay yine istenir), 'geri al' dosyalari gorevden onceki anlik goruntuye dondurur, 'yok say' dosyayi siler."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from .config import AYAR_KLASORU

DOSYA = "devam.json"
AZAMI_GOREV = 20000
AZAMI_KUYRUK = 10
DURUMLAR = ("plan", "calisiyor", "karar-bekliyor")
COMMIT = re.compile(r"[0-9a-f]{40}")


def yol(klasor: str | Path) -> Path:
    return Path(klasor) / AYAR_KLASORU / DOSYA


def yaz(klasor: str | Path, kosu: dict | None, kuyruk: list[dict]) -> None:
    """kosu: {kimlik, gorev, durum, testsiz, once}; ikisi de bossa dosya silinir. Disk hatasi gorevi etkilemez."""
    hedef = yol(klasor)
    try:
        if not kosu and not kuyruk:
            hedef.unlink(missing_ok=True)
            return
        hedef.parent.mkdir(parents=True, exist_ok=True)
        veri = {"surum": 1, "zaman": time.strftime("%Y-%m-%d %H:%M:%S"), "kosu": kosu, "kuyruk": [{"gorev": k["gorev"], "testsiz": k.get("testsiz")} for k in kuyruk]}
        gecici = hedef.with_suffix(".tmp")
        gecici.write_text(json.dumps(veri, ensure_ascii=False), encoding="utf-8")
        os.replace(gecici, hedef)
    except OSError:
        pass


def sil(klasor: str | Path) -> None:
    try:
        yol(klasor).unlink(missing_ok=True)
    except OSError:
        pass


def _gorev(g: object) -> bool:
    return isinstance(g, str) and bool(g.strip()) and len(g) <= AZAMI_GOREV and "\x00" not in g


def oku(klasor: str | Path) -> dict | None:
    """Gecerli kayit ya da None. Bozuk/yabanci dosya yok sayilir; icerik DOGRULANIR (zehirli depo gorev metni dayatamaz: dosya `.aktapokus/`
    altinda ve yalniz kullanicinin onayiyla plana donusur)."""
    try:
        ham = json.loads(yol(klasor).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(ham, dict):
        return None
    kosu = ham.get("kosu")
    if kosu is not None:
        if not isinstance(kosu, dict) or kosu.get("durum") not in DURUMLAR or not _gorev(kosu.get("gorev")):
            return None
        once = kosu.get("once")
        kosu = {"kimlik": str(kosu.get("kimlik", ""))[:16], "gorev": kosu["gorev"].strip(), "durum": kosu["durum"], "testsiz": bool(kosu.get("testsiz")),
                "once": once if isinstance(once, str) and COMMIT.fullmatch(once) else None}
    kuyruk = [{"gorev": k["gorev"].strip(), "testsiz": k.get("testsiz") if isinstance(k.get("testsiz"), bool) else None}
              for k in ham.get("kuyruk", []) if isinstance(k, dict) and _gorev(k.get("gorev"))][:AZAMI_KUYRUK] if isinstance(ham.get("kuyruk", []), list) else []
    if not kosu and not kuyruk:
        return None
    return {"zaman": str(ham.get("zaman", ""))[:19], "kosu": kosu, "kuyruk": kuyruk}
