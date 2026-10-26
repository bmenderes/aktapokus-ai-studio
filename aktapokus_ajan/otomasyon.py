"""Otomasyonlar: kayitli gorev sablonlari (ve ilerleyen asamalarda zamanlama/tetikleyici/zincir). Tasarim: docs/otomasyon-tasarimi.md

Temel ilkeler:
- Bir otomasyon YALNIZCA plan uretir; plan yine kullanici onayini bekler (burada onaysiz calistirma yolu YOKTUR).
- Tanimlar yalniz kullanici klasorunde (`~/.aktapokus/otomasyonlar.json`) tutulur; proje klasorunden ASLA okunmaz (klonlanan bir depo kendi
  otomasyonunu getiremez).
- Telegram yalniz KAYITLI otomasyon adlarini calistirabilir; tanimlayamaz, duzenleyemez."""

from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path

KAYIT_ORTAMI = "AKTAPOKUS_OTOMASYON"
AD_DESENI = re.compile(r"^[a-z0-9][a-z0-9_-]{0,30}$")
AZAMI_OTOMASYON = 20
AZAMI_GOREV = 4000
AZAMI_GECMIS = 500
TURLER = ("sablon", "zamanli")  # sonraki asamalarda: olay, zincir
AZAMI_ARALIK_DK = 7 * 24 * 60
EN_KISA_ARALIK_DK = 5
SAAT_DESENI = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
ZAMAN_BICIMI = "%Y-%m-%d %H:%M:%S"
DEGISKENLER = ("tarih", "saat", "proje", "dal")
_kilit = threading.Lock()
_durum_kilit = threading.RLock()


class OtomasyonHatasi(Exception):
    pass


@dataclass(frozen=True)
class Otomasyon:
    ad: str
    proje: str  # proje kimligi (projeler.proje_kimligi)
    gorev: str
    tur: str = "sablon"
    acik: bool = True  # kapaliysa Telegram/otomatik tetikleme calismaz (arayuzden elle 'Simdi calistir' her zaman calisir)
    aciklama: str = ""
    olusturma: str = field(default_factory=lambda: time.strftime(ZAMAN_BICIMI))
    zamanlama: dict | None = None  # yalniz tur == "zamanli": {tur: aralik|gunluk|haftalik, dakika | saat | saat+gunler(0=pazartesi)}

    def sozluk(self) -> dict:
        return {"ad": self.ad, "proje": self.proje, "gorev": self.gorev, "tur": self.tur, "acik": self.acik, "aciklama": self.aciklama, "olusturma": self.olusturma, "zamanlama": self.zamanlama}


def dosya_yolu() -> Path:
    ortam = os.environ.get(KAYIT_ORTAMI)
    return Path(ortam) if ortam else Path.home() / ".aktapokus" / "otomasyonlar.json"


def gecmis_yolu() -> Path:
    return dosya_yolu().with_name("otomasyon-gecmisi.jsonl")


def coz(veri: object, eski: Otomasyon | None = None) -> Otomasyon:
    if not isinstance(veri, dict):
        raise OtomasyonHatasi("Tanim bir nesne olmali")
    ad = veri.get("ad")
    if not isinstance(ad, str) or not AD_DESENI.fullmatch(ad):
        raise OtomasyonHatasi("'ad' kucuk harf/rakam/-/_ icermeli ve 31 karakteri gecmemeli (ornek: haftalik-rapor)")
    tur = veri.get("tur", "sablon")
    if tur not in TURLER:
        raise OtomasyonHatasi(f"'tur' su degerlerden biri olmali: {', '.join(TURLER)}")
    proje = veri.get("proje")
    if not isinstance(proje, str) or not re.fullmatch(r"[0-9a-f]{10}", proje):
        raise OtomasyonHatasi("'proje' bir proje kimligi olmali")
    gorev = veri.get("gorev")
    if not isinstance(gorev, str) or not gorev.strip() or len(gorev) > AZAMI_GOREV or "\x00" in gorev:
        raise OtomasyonHatasi(f"'gorev' bos olmayan metin olmali (en cok {AZAMI_GOREV} karakter)")
    acik = veri.get("acik", True)
    if not isinstance(acik, bool):
        raise OtomasyonHatasi("'acik' true/false olmali")
    aciklama = veri.get("aciklama") or ""
    if not isinstance(aciklama, str) or len(aciklama) > 300 or "\n" in aciklama:
        raise OtomasyonHatasi("'aciklama' en cok 300 karakterlik tek satir olmali")
    zamanlama = _zamanlama_coz(veri.get("zamanlama")) if tur == "zamanli" else None
    if tur != "zamanli" and veri.get("zamanlama") is not None:
        raise OtomasyonHatasi("Zamanlama yalniz 'zamanli' turde olur")
    ek = {"olusturma": eski.olusturma} if eski else {}
    return Otomasyon(ad=ad, proje=proje, gorev=gorev.strip(), tur=tur, acik=acik, aciklama=aciklama.strip(), zamanlama=zamanlama, **ek)


def _zamanlama_coz(z: object) -> dict:
    if not isinstance(z, dict):
        raise OtomasyonHatasi("'zamanlama' bir nesne olmali")
    tur = z.get("tur")
    if tur == "aralik":
        dk = z.get("dakika")
        if isinstance(dk, bool) or not isinstance(dk, int) or not EN_KISA_ARALIK_DK <= dk <= AZAMI_ARALIK_DK:
            raise OtomasyonHatasi(f"Aralik {EN_KISA_ARALIK_DK}-{AZAMI_ARALIK_DK} dakika arasinda olmali (en kisa {EN_KISA_ARALIK_DK} dakika)")
        return {"tur": "aralik", "dakika": dk}
    if tur in ("gunluk", "haftalik"):
        saat = z.get("saat")
        if not isinstance(saat, str) or not SAAT_DESENI.fullmatch(saat):
            raise OtomasyonHatasi("'saat' SS:DD bicimde olmali (ornek: 09:30)")
        if tur == "gunluk":
            return {"tur": "gunluk", "saat": saat}
        gunler = z.get("gunler")
        if not isinstance(gunler, list) or not gunler or any(isinstance(g, bool) or not isinstance(g, int) or not 0 <= g <= 6 for g in gunler):
            raise OtomasyonHatasi("'gunler' 0 (pazartesi) - 6 (pazar) arasi sayilardan olusan bos olmayan liste olmali")
        return {"tur": "haftalik", "saat": saat, "gunler": sorted(set(gunler))}
    raise OtomasyonHatasi("Zamanlama turu aralik, gunluk ya da haftalik olmali")


def sonraki(z: dict, ref: datetime) -> datetime:
    """`ref`ten SONRAKI ilk planli an (yerel saat)."""
    if z["tur"] == "aralik":
        return ref + timedelta(minutes=z["dakika"])
    ss, dd = (int(x) for x in z["saat"].split(":"))
    for gun in range(0, 8):
        aday = (ref + timedelta(days=gun)).replace(hour=ss, minute=dd, second=0, microsecond=0)
        if aday > ref and (z["tur"] == "gunluk" or aday.weekday() in z["gunler"]):
            return aday
    raise OtomasyonHatasi("Zamanlama hesaplanamadi")  # ulasilamaz: gunler bos olamaz


def yukle() -> dict[str, Otomasyon]:
    try:
        ham = json.loads(dosya_yolu().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    sonuc: dict[str, Otomasyon] = {}
    for oge in ham.get("otomasyonlar", []) if isinstance(ham, dict) else []:
        try:
            o = coz(oge)
        except OtomasyonHatasi:
            continue
        if isinstance(oge, dict) and isinstance(oge.get("olusturma"), str):
            o = replace(o, olusturma=oge["olusturma"])
        sonuc[o.ad] = o
    return sonuc


def _yaz(tanimlar: dict[str, Otomasyon]) -> None:
    yol = dosya_yolu()
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_suffix(".tmp")
    gecici.write_text(json.dumps({"surum": 1, "otomasyonlar": [o.sozluk() for o in tanimlar.values()]}, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(gecici, yol)


def kaydet(veri: object) -> Otomasyon:
    with _kilit:
        tanimlar = yukle()
        ad = veri.get("ad") if isinstance(veri, dict) else None
        o = coz(veri, eski=tanimlar.get(ad) if isinstance(ad, str) else None)
        if o.ad not in tanimlar and len(tanimlar) >= AZAMI_OTOMASYON:
            raise OtomasyonHatasi(f"En cok {AZAMI_OTOMASYON} otomasyon tanimlanabilir")
        eski = tanimlar.get(o.ad)
        tanimlar[o.ad] = o
        _yaz(tanimlar)
        if o.tur == "zamanli" and (eski is None or eski.zamanlama != o.zamanlama or eski.tur != o.tur or (o.acik and not eski.acik)):
            durum_yaz(o.ad, datetime.now())  # yeni/degisen/yeniden acilan zamanlama simdiden sayilir: gecmise donuk 'kacirildi' uretmez
        return o


def sil(ad: str) -> bool:
    with _kilit:
        tanimlar = yukle()
        if ad not in tanimlar:
            return False
        del tanimlar[ad]
        _yaz(tanimlar)
        durum_sil(ad)
        return True


def bul(ad: object) -> Otomasyon | None:
    return yukle().get(ad) if isinstance(ad, str) else None


def degiskenleri_doldur(metin: str, baglam: dict[str, str]) -> str:
    """{tarih} {saat} {proje} {dal} degiskenlerini doldurur; bilinmeyen {...} oldugu gibi kalir (format() hatalari/enjeksiyonu yok)."""
    return re.sub(r"\{(" + "|".join(DEGISKENLER) + r")\}", lambda m: baglam.get(m.group(1), m.group(0)), metin)


# ---- zamanlayici durumu: otomasyon basina "son degerlendirilen an" -----------------------------------------------------
def durum_yolu() -> Path:
    return dosya_yolu().with_name("otomasyon-durum.json")


def _durum_oku() -> dict:
    try:
        ham = json.loads(durum_yolu().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return ham if isinstance(ham, dict) else {}


def durum_oku(ad: str) -> datetime | None:
    deger = _durum_oku().get(ad)
    try:
        return datetime.strptime(deger, ZAMAN_BICIMI) if isinstance(deger, str) else None
    except ValueError:
        return None


def durum_yaz(ad: str, an: datetime) -> None:
    with _durum_kilit:
        veri = _durum_oku()
        veri[ad] = an.strftime(ZAMAN_BICIMI)
        yol = durum_yolu()
        yol.parent.mkdir(parents=True, exist_ok=True)
        gecici = yol.with_suffix(".tmp")
        gecici.write_text(json.dumps(veri, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(gecici, yol)


def durum_sil(ad: str) -> None:
    with _durum_kilit:
        veri = _durum_oku()
        if veri.pop(ad, None) is not None:
            durum_yolu().write_text(json.dumps(veri, ensure_ascii=False, indent=2), encoding="utf-8")


# ---- calisma gecmisi --------------------------------------------------------------------------------------------------
def gecmis_ekle(otomasyon: str, sonuc: str, neden: str = "", tetikleyen: str = "elle", gorev: str | None = None, proje: str | None = None, zaman: str | None = None) -> dict:
    """sonuc: plan-olustu | atlandi | hata | kacirildi. Dosya AZAMI_GECMIS satirla sinirlidir."""
    kayit = {"zaman": zaman or time.strftime(ZAMAN_BICIMI), "otomasyon": otomasyon, "sonuc": sonuc, "neden": neden[:300], "tetikleyen": tetikleyen, "gorev": gorev, "proje": proje}
    with _kilit:
        yol = gecmis_yolu()
        yol.parent.mkdir(parents=True, exist_ok=True)
        satirlar: list[str] = []
        try:
            satirlar = yol.read_text(encoding="utf-8").splitlines()
        except OSError:
            pass
        satirlar.append(json.dumps(kayit, ensure_ascii=False))
        yol.write_text("\n".join(satirlar[-AZAMI_GECMIS:]) + "\n", encoding="utf-8")
    return kayit


def gecmis_oku(adet: int = 30) -> list[dict]:
    try:
        satirlar = gecmis_yolu().read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    sinir = max(1, min(int(adet), AZAMI_GECMIS))
    sonuc = []
    for s in reversed(satirlar):  # bozuk satirlar atlanir ve 'adet' sayisindan YER ALMAZ
        try:
            k = json.loads(s)
        except json.JSONDecodeError:
            continue
        if isinstance(k, dict):
            sonuc.append(k)
            if len(sonuc) >= sinir:
                break
    return sonuc
