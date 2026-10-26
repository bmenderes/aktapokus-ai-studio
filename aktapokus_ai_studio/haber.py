"""Aktapokus haberi: Claude Code'a (kanca/hook ile) ya da terminale, Aktapokus'ta NE OLDUGUNU kisa bir ozet olarak verir.

- Calisan/plan/karar bekleyen gorevler: ~/.aktapokus/canli.json (uygulama calisiyorsa)
- Biten gorevler: kayitli projelerin .aktapokus/kayit/*.json dosyalari
Kanca modunda her Claude Code oturumu icin yalniz son bildirimden BERI olan yeni olaylar verilir; yeni bir sey yoksa HICBIR SEY yazilmaz (baglam sismez).
Hicbir sey yazmaz/degistirmez (yalniz kendi 'son bildirim' isaretini ~/.aktapokus/haber-durum.json'a yazar). Sir/dosya icerigi bildirilmez: gorev metni ve yanit ozeti kisaltilir."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from . import canli, projeler

DURUM_ORTAMI = "AKTAPOKUS_HABER_DURUM"
VARSAYILAN_PENCERE_DK = 30
AZAMI_SATIR = 8
AZAMI_OTURUM = 40
HATA_DURUMLARI = ("hata", "basarisiz", "dogrulama_basarisiz", "butce_asildi", "iptal")


def durum_yolu() -> Path:
    ortam = os.environ.get(DURUM_ORTAMI)
    return Path(ortam) if ortam else Path.home() / ".aktapokus" / "haber-durum.json"


def _kisa(m: object, n: int) -> str:
    return " ".join(str(m or "").split())[:n]


def _surec_canli(pid: object) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    from .uygulama import surec_canli_mi

    return surec_canli_mi(pid)


def _canli_satirlari(simdi: float) -> list[str]:
    v = canli.oku()
    if not v or not _surec_canli(v.get("pid")) or simdi - float(v.get("guncelleme") or 0) > 300:
        return []
    etiket = {"plan": "PLAN ONAYI BEKLIYOR", "calisiyor": "CALISIYOR", "karar-bekliyor": "KARAR BEKLIYOR (korunsun mu / geri al)"}
    satirlar = []
    for d in (v.get("projeler") or {}).values():
        if not isinstance(d, dict) or d.get("durum") not in etiket:
            continue
        gecen = int(simdi - float(d.get("baslangic") or simdi))
        ek = []
        if d.get("rol"):
            ek.append(f"{d['rol']} adimi" + (f" ({d['model']})" if d.get("model") else ""))
        if d.get("son_arac"):
            ek.append("son arac: " + _kisa(d["son_arac"], 80))
        satirlar.append(f"[{_kisa(d.get('ad'), 30)}] {etiket[d['durum']]}: \"{_kisa(d.get('gorev'), 90)}\" - {gecen} sn" + (" - " + ", ".join(ek) if ek else ""))
    return satirlar


def _biten_satirlari(son: float, simdi: float) -> list[tuple[float, str]]:
    sonuc: list[tuple[float, str]] = []
    try:
        liste = projeler.listele()
    except Exception:
        return []
    for p in liste:
        if not p.get("var"):
            continue
        klasor = Path(p["yol"]) / ".aktapokus" / "kayit"
        try:
            girdiler = [e for e in os.scandir(klasor) if e.name.endswith(".json") and e.is_file() and e.stat().st_mtime > son]
        except OSError:
            continue
        for e in girdiler:
            try:
                k = json.loads(Path(e.path).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            adimlar = [a for a in (k.get("adimlar") or []) if isinstance(a, dict)]
            durum = str(k.get("durum"))
            yanit = _kisa(adimlar[-1].get("metin") if adimlar else "", 160)
            dosyalar = list((k.get("degisen") or {}).keys())
            isaret = "UYARI " if durum in HATA_DURUMLARI else ""
            satir = (f"{isaret}[{_kisa(p.get('ad'), 30)}] BITTI {str(k.get('zaman', ''))[11:16]} - {durum} - {int(k.get('token_toplam') or 0) // 1000}k token: \"{_kisa(k.get('gorev'), 70)}\""
                     + (f" - degisen: {', '.join(_kisa(x, 40) for x in dosyalar[:3])}" + (f" (+{len(dosyalar) - 3})" if len(dosyalar) > 3 else "") if dosyalar else "")
                     + (f" - yanit: {yanit}" if yanit else ""))
            sonuc.append((e.stat().st_mtime, satir))
    sonuc.sort()
    return sonuc


def _parmak(simdi: float) -> str:
    """Calisan gorevlerin durum parmak izi (proje, durum, gorev, rol, adim): ayni durum tekrar tekrar bildirilmesin diye."""
    v = canli.oku()
    if not v or not _surec_canli(v.get("pid")) or simdi - float(v.get("guncelleme") or 0) > 300:
        return ""
    return json.dumps(sorted([k, d.get("durum"), d.get("gorev"), d.get("rol"), d.get("adim")] for k, d in (v.get("projeler") or {}).items()
                             if isinstance(d, dict) and d.get("durum") in ("plan", "calisiyor", "karar-bekliyor")), ensure_ascii=False)


def ozet(son: float | None, simdi: float | None = None, pencere_dk: int = VARSAYILAN_PENCERE_DK, canli_goster: bool = True) -> tuple[str, float]:
    """(metin, yeni_isaret). `son`: bu oturuma en son bildirim zamani (None: son `pencere_dk` dakika). Yeni bir sey yoksa metin ''."""
    simdi = simdi or time.time()
    alt = simdi - pencere_dk * 60
    baslangic = max(son or alt, alt)
    canli_satirlar = _canli_satirlari(simdi) if canli_goster else []
    biten = [s for _, s in _biten_satirlari(baslangic, simdi)]
    toplam = len(canli_satirlar) + len(biten)
    if not toplam:
        return "", simdi
    kalan = max(0, AZAMI_SATIR - len(canli_satirlar[:AZAMI_SATIR]))
    satirlar = canli_satirlar[:AZAMI_SATIR] + (biten[-kalan:] if kalan else [])
    fazla = toplam - len(satirlar)
    metin = ("Aktapokus durumu (kullanicinin yerel arayuzunde olanlar; ayrinti: <proje>/.aktapokus/kayit/<id>.json ya da `aktapokus haber --hepsi`):\n"
             + "\n".join("- " + s for s in satirlar) + (f"\n(+{fazla} eski satir)" if fazla else ""))
    return metin, simdi


def _durum_oku() -> dict:
    try:
        v = json.loads(durum_yolu().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return v if isinstance(v, dict) else {}


def kanca(oturum: object, simdi: float | None = None) -> str:
    """Claude Code UserPromptSubmit kancasi: bu oturuma YENI olanlari verir ve bildirim zamanini kaydeder. Yeni bir sey yoksa ''."""
    simdi = simdi or time.time()
    anahtar = oturum if isinstance(oturum, str) and 0 < len(oturum) <= 80 else "-"
    durum = _durum_oku()
    oturumlar = durum.get("oturumlar") if isinstance(durum.get("oturumlar"), dict) else {}
    onceki = oturumlar.get(anahtar) if isinstance(oturumlar.get(anahtar), dict) else {}
    parmak = _parmak(simdi)
    metin, isaret = ozet(float(onceki.get("zaman") or 0) or None, simdi, canli_goster=parmak != onceki.get("parmak"))
    oturumlar[anahtar] = {"zaman": isaret, "parmak": parmak}
    if len(oturumlar) > AZAMI_OTURUM:
        for k in sorted(oturumlar, key=lambda x: oturumlar[x].get("zaman", 0))[: len(oturumlar) - AZAMI_OTURUM]:
            del oturumlar[k]
    try:
        yol = durum_yolu()
        yol.parent.mkdir(parents=True, exist_ok=True)
        gecici = yol.with_suffix(".tmp")
        gecici.write_text(json.dumps({"oturumlar": oturumlar}), encoding="utf-8")
        os.replace(gecici, yol)
    except OSError:
        pass
    return metin
