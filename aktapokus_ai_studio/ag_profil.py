"""Kayitli IP profilleri (NetSetMan benzeri): bir adaptor icin sabit IP ya da DHCP ayarini adla saklar, tek tikla uygular.
Dosya: ~/.aktapokus/ag-profiller.json (AKTAPOKUS_AG_PROFILLER ile degisir)."""
from __future__ import annotations

import ipaddress
import json
import os
from pathlib import Path

from . import ag_araci

ORTAM = "AKTAPOKUS_AG_PROFILLER"


def yol() -> Path:
    ortam = os.environ.get(ORTAM)
    return Path(ortam) if ortam else Path.home() / ".aktapokus" / "ag-profiller.json"


def yukle() -> list[dict]:
    try:
        veri = json.loads(yol().read_text(encoding="utf-8"))
        return [p for p in veri if isinstance(p, dict) and isinstance(p.get("ad"), str)]
    except (OSError, ValueError, TypeError):
        return []


def _yaz(profiller: list[dict]) -> None:
    y = yol()
    y.parent.mkdir(parents=True, exist_ok=True)
    gecici = y.with_suffix(".tmp")
    gecici.write_text(json.dumps(profiller, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(gecici, y)


def _adres(v: object, ad: str, bos_olur: bool = False) -> str | None:
    if bos_olur and v in (None, ""):
        return None
    try:
        return str(ipaddress.IPv4Address(str(v).strip()))
    except ValueError:
        raise ag_araci.AgHatasi(f"{ad} gecersiz") from None


def kaydet(veri: object) -> list[dict]:
    if not isinstance(veri, dict):
        raise ag_araci.AgHatasi("Profil gecersiz")
    ad = str(veri.get("ad") or "").strip()[:60]
    adaptor = str(veri.get("adaptor") or "").strip()[:100]
    if not ad or not adaptor:
        raise ag_araci.AgHatasi("Profil adi ve adaptor gerekli")
    p = {"ad": ad, "adaptor": adaptor, "dhcp": bool(veri.get("dhcp"))}
    if not p["dhcp"]:
        p["ip"], p["maske"] = _adres(veri.get("ip"), "IP"), _adres(veri.get("maske"), "Alt ag maskesi")
        try:
            ipaddress.IPv4Network(f"0.0.0.0/{p['maske']}")
        except ValueError:
            raise ag_araci.AgHatasi("Alt ag maskesi gecersiz") from None
        p["gecit"] = _adres(veri.get("gecit"), "Ag gecidi", True)
    profiller = [x for x in yukle() if x["ad"] != ad] + [p]
    _yaz(profiller)
    return profiller


def sil(ad: object) -> list[dict]:
    profiller = [x for x in yukle() if x["ad"] != ad]
    _yaz(profiller)
    return profiller


def uygula(ad: object) -> None:
    p = next((x for x in yukle() if x["ad"] == ad), None)
    if p is None:
        raise ag_araci.AgHatasi("Boyle bir profil yok")
    if p.get("dhcp"):
        ag_araci.adaptor_dhcp_yap(p["adaptor"])
    else:
        ag_araci.adaptor_ip_ata(p["adaptor"], p["ip"], p["maske"], p.get("gecit"))
