"""Proje altinda kalici, adli sohbetler (alt sohbetler dahil): `<proje>/.aktapokus/sohbetler.json`.

Sohbet = gorev kayitlarindaki `sohbet` alani. Bu dosya yalniz sohbetin KENDI bilgisini tutar (kimlik, ust sohbet, ad, aktif olan);
eski kayitlar (alansiz) `baglam.py` icinde zaman araligiyla eslenir, kayitlara dokunulmaz."""

from __future__ import annotations

import json
import os
import re
import secrets
import threading
import time
from pathlib import Path

from .config import AYAR_KLASORU

DOSYA = "sohbetler.json"
KIMLIK = re.compile(r"[0-9a-z-]{1,40}")
AZAMI_AD = 80
AZAMI_SOHBET = 500
_kilit = threading.RLock()


def _yol(klasor: str | Path) -> Path:
    return Path(klasor) / AYAR_KLASORU / DOSYA


def oku(klasor: str | Path) -> dict:
    """{"aktif": id|None, "liste": [{"id", "zaman", "ust"?, "ad"?}]} (bozuk/eksik dosya = bos)."""
    try:
        v = json.loads(_yol(klasor).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        v = {}
    v = v if isinstance(v, dict) else {}
    liste, gorulen = [], set()
    for s in v.get("liste") if isinstance(v.get("liste"), list) else []:
        if not isinstance(s, dict) or not isinstance(s.get("id"), str) or not KIMLIK.fullmatch(s["id"]) or s["id"] in gorulen:
            continue
        gorulen.add(s["id"])
        ust = s.get("ust") if isinstance(s.get("ust"), str) and KIMLIK.fullmatch(s["ust"]) else None
        ad = s.get("ad") if isinstance(s.get("ad"), str) and s["ad"].strip() and "\n" not in s["ad"] else None
        liste.append({"id": s["id"], "zaman": str(s.get("zaman") or ""), **({"ust": ust} if ust else {}), **({"ad": ad.strip()[:AZAMI_AD]} if ad else {})})
    aktif = v.get("aktif") if isinstance(v.get("aktif"), str) and KIMLIK.fullmatch(v["aktif"]) else None
    return {"aktif": aktif, "liste": liste}


def _yaz(klasor: str | Path, veri: dict) -> None:
    yol = _yol(klasor)
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_suffix(".tmp")
    gecici.write_text(json.dumps(veri, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(gecici, yol)


def yeni_kimlik() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)


def ac(klasor: str | Path, ust: str | None = None) -> str:
    """Yeni sohbet acar ve aktif yapar; kimligini doner. `ust`: alt sohbetin ebeveyni (gecerliligini cagiran denetler)."""
    with _kilit:
        v = oku(klasor)
        if len(v["liste"]) >= AZAMI_SOHBET:
            raise ValueError("Cok fazla sohbet")
        kimlik = yeni_kimlik()
        v["liste"].append({"id": kimlik, "zaman": time.strftime("%Y-%m-%d %H:%M:%S"), **({"ust": ust} if ust else {})})
        v["aktif"] = kimlik
        _yaz(klasor, v)
        return kimlik


def aktif_yap(klasor: str | Path, kimlik: str) -> None:
    with _kilit:
        v = oku(klasor)
        v["aktif"] = kimlik
        _yaz(klasor, v)


def ayarla(klasor: str | Path, kimlik: str, ad: str | None = None, ust: str | None = None) -> None:
    """Sohbet kaydini olusturur/gunceller (eski, kayitlardan turetilen sohbetler de ilk adlandirmada buraya yazilir). ad='' -> otomatik ad."""
    if not KIMLIK.fullmatch(kimlik):
        raise ValueError("Gecersiz sohbet kimligi")
    with _kilit:
        v = oku(klasor)
        s = next((x for x in v["liste"] if x["id"] == kimlik), None)
        if s is None:
            s = {"id": kimlik, "zaman": ""}
            v["liste"].append(s)
        if ad is not None:
            ad = " ".join(ad.split())[:AZAMI_AD]
            if ad:
                s["ad"] = ad
            else:
                s.pop("ad", None)
        if ust is not None:
            if ust and (ust == kimlik or _dongu_mu(v["liste"], kimlik, ust)):
                raise ValueError("Sohbet kendi altina tasinamaz")
            if ust:
                s["ust"] = ust
            else:
                s.pop("ust", None)
        _yaz(klasor, v)


def _dongu_mu(liste: list[dict], kimlik: str, ust: str) -> bool:
    ebeveyn = {s["id"]: s.get("ust") for s in liste}
    gez = ust
    for _ in range(len(liste) + 1):
        if gez == kimlik:
            return True
        gez = ebeveyn.get(gez)
        if not gez:
            return False
    return True


def baslik_uret(gorev: str) -> str:
    """Ilk istemden kisa baslik: ek listesi atilir, ilk satir, en fazla 40 karakter."""
    metin = str(gorev or "").split("\n\nEkli dosyalar")[0]
    satir = next((" ".join(s.split()) for s in metin.splitlines() if s.strip()), "")
    return satir if len(satir) <= 40 else satir[:40].rstrip() + "…"
