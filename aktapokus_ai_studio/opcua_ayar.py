"""OPC UA toplama ayari (kalici): uygulama yeniden acilinca toplama kaldigi yerden surer; kullanici Durdur'a basarsa devam etmez.
Dosya: ~/.aktapokus/opcua-toplama.json (AKTAPOKUS_OPCUA_TOPLAMA ile degisir). Sir icermez (adres + dugum kimlikleri)."""
from __future__ import annotations

import json
import os
from pathlib import Path

ORTAM = "AKTAPOKUS_OPCUA_TOPLAMA"
VARSAYILAN_SAKLAMA_GUN = 30


def yol() -> Path:
    ortam = os.environ.get(ORTAM)
    return Path(ortam) if ortam else Path.home() / ".aktapokus" / "opcua-toplama.json"


def oku() -> dict | None:
    """Gecerli ayar ya da None."""
    try:
        a = json.loads(yol().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if (not isinstance(a, dict) or not isinstance(a.get("adres"), str) or not a["adres"].startswith("opc.tcp://")
            or not isinstance(a.get("kimlikler"), list) or not a["kimlikler"] or not all(isinstance(k, str) for k in a["kimlikler"])):
        return None
    adlar = a.get("adlar") if isinstance(a.get("adlar"), dict) else {}
    gun = a.get("saklama_gun")
    return {"adres": a["adres"], "kimlikler": a["kimlikler"], "adlar": {str(k): str(v) for k, v in adlar.items()},
            "saklama_gun": gun if isinstance(gun, int) and not isinstance(gun, bool) and 0 <= gun <= 3650 else VARSAYILAN_SAKLAMA_GUN,
            "otomatik": a.get("otomatik") is True}


def yaz(adres: str, kimlikler: list[str], adlar: dict, saklama_gun: int, otomatik: bool) -> None:
    y = yol()
    y.parent.mkdir(parents=True, exist_ok=True)
    gecici = y.with_suffix(".tmp")
    gecici.write_text(json.dumps({"adres": adres, "kimlikler": kimlikler, "adlar": adlar, "saklama_gun": saklama_gun, "otomatik": otomatik}, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(gecici, y)


def otomatik_ayarla(acik: bool) -> None:
    a = oku()
    if a is not None:
        yaz(a["adres"], a["kimlikler"], a["adlar"], a["saklama_gun"], acik)
