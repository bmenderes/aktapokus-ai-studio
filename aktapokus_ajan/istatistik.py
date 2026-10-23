"""Istatistik: gorev kayitlarindan (<proje>/.aktapokus/kayit/*.json) token harcamasi, model/calistirici/rol dokumu, hata siniflari ve
model degistirme onerileri. Yalniz OKUR; yeni veri toplamaz, hicbir sey gondermez.

Sinir: abonelik kotalarinin (Claude Pro, ChatGPT/Codex) KALAN miktari CLI'lardan guvenilir okunamiyor (dogrulanmadi). Bu modul yalniz
harcanan token'i ve limite TAKILMA anini (hata metninden) gorur."""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

AYAR_KLASORU = ".aktapokus"
KAYIT_KLASORU = "kayit"
AZAMI_KAYIT = 2000  # klasor basina okunacak en yeni kayit sayisi
LIMIT_PENCERESI_SA = 48  # bu kadar saat icindeki limit hatalari 'guncel sorun' sayilir

# Siralama onemli: ilk eslesen sinif kazanir. Desenler kucuk harfe cevrilmis metne uygulanir.
HATA_SINIFLARI: list[tuple[str, re.Pattern]] = [
    ("limit", re.compile(r"rate.?limit|usage limit|limit reached|limit exceeded|quota|\b429\b|too many requests|resource.?exhausted|credit|billing|exceeded your|kota|capacity|overloaded|try again later|daily limit")),
    ("kimlik", re.compile(r"\b401\b|\b403\b|unauthori[sz]ed|forbidden|api.?key|invalid.*(key|token)|not logged in|authentication|login|permission denied|kimlik")),
    ("zaman_asimi", re.compile(r"zaman asimi|timed? ?out|timeout")),
    ("butce", re.compile(r"butce|budget")),
]
SINIF_ADLARI = {"limit": "limit/kota", "kimlik": "anahtar/giriş", "zaman_asimi": "zaman aşımı", "butce": "bütçe", "diger": "diğer"}


def hata_sinifi(metin: str | None) -> str | None:
    if not metin:
        return None
    kucuk = str(metin).lower()
    for ad, desen in HATA_SINIFLARI:
        if desen.search(kucuk):
            return ad
    return "diger"


def telegram_ayar_yolu() -> Path:
    ortam = os.environ.get("AKTAPOKUS_TELEGRAM_AYAR")
    return Path(ortam) if ortam else Path.home() / ".aktapokus" / "telegram.json"


def bilinen_klasorler(mevcut: Path | None = None) -> list[Path]:
    """Taranacak proje klasorleri: acik proje + Telegram proje koklerinin DOGRUDAN alt klasorleri (gizli olanlar ve nokta ile baslayanlar haric)."""
    sonuc: list[Path] = []
    gorulen: set[str] = set()

    def ekle(p: Path) -> None:
        anahtar = str(p).lower()
        if anahtar not in gorulen and (p / AYAR_KLASORU / KAYIT_KLASORU).is_dir():
            gorulen.add(anahtar)
            sonuc.append(p)

    if mevcut:
        ekle(Path(mevcut))
    try:
        ham = json.loads(telegram_ayar_yolu().read_text(encoding="utf-8"))
        kokler = [Path(str(k)) for k in ham.get("kokler", [])]
        gizli = {str(g).lower() for g in ham.get("gizli", [])}
    except (OSError, ValueError, TypeError, AttributeError):
        kokler, gizli = [], set()
    for kok in kokler:
        try:
            for alt in sorted(kok.iterdir()):
                if alt.is_dir() and not alt.name.startswith(".") and alt.name.lower() not in gizli:
                    ekle(alt)
        except OSError:
            continue
    return sonuc


def kayitlari_oku(klasorler: list[Path]) -> list[dict]:
    """Her klasorun en yeni kayitlari; bozuk dosyalar atlanir. Her kayda '_proje' (klasor adi) eklenir."""
    kayitlar: list[dict] = []
    for klasor in klasorler:
        yol = Path(klasor) / AYAR_KLASORU / KAYIT_KLASORU
        try:
            dosyalar = sorted(yol.glob("*.json"), reverse=True)[:AZAMI_KAYIT]
        except OSError:
            continue
        for d in dosyalar:
            try:
                k = json.loads(d.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(k, dict):
                k["_proje"] = Path(klasor).name
                kayitlar.append(k)
    return kayitlar


def _zaman(kayit: dict) -> datetime | None:
    try:
        return datetime.strptime(str(kayit.get("zaman")), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _int(deger) -> int:
    """Kayit elle bozulmus olabilir: sayi olmayan degerler 0 sayilir."""
    try:
        return max(0, int(deger or 0))
    except (TypeError, ValueError):
        return 0


def _float(deger) -> float:
    try:
        return max(0.0, float(deger or 0))
    except (TypeError, ValueError):
        return 0.0


def _bos() -> dict:
    return {"girdi": 0, "cikti": 0, "onbellek": 0, "adim": 0, "hata": 0, "sure_sn": 0.0}


def _topla(h: dict, a: dict) -> None:
    h["girdi"] += _int(a.get("token_girdi"))
    h["cikti"] += _int(a.get("token_cikti"))
    h["onbellek"] += _int(a.get("token_onbellek"))
    h["adim"] += 1
    h["hata"] += 0 if a.get("ok", True) else 1
    h["sure_sn"] += _float(a.get("sure_sn"))


def _bitir(h: dict) -> dict:
    h = dict(h)
    h["yeni"] = h["girdi"] + h["cikti"]  # butceye sayilan token (onbellek ayri)
    h["ort_sure_sn"] = round(h["sure_sn"] / h["adim"], 1) if h["adim"] else 0.0
    del h["sure_sn"]
    return h


def ozet(kayitlar: list[dict], simdi: datetime | None = None, gun_sayisi: int = 14) -> dict:
    simdi = simdi or datetime.now()
    bugun_basi = simdi.replace(hour=0, minute=0, second=0, microsecond=0)
    hafta_basi = bugun_basi - timedelta(days=6)
    toplam, bugun, hafta = _bos(), _bos(), _bos()
    modeller: dict[tuple, dict] = defaultdict(_bos)
    roller: dict[str, dict] = defaultdict(_bos)
    projeler: dict[str, dict] = defaultdict(_bos)
    gunluk: dict[str, int] = defaultdict(int)
    durumlar: dict[str, int] = defaultdict(int)
    hatalar: dict[str, int] = defaultdict(int)
    son_hatalar: list[dict] = []
    guncel_limit: dict[tuple, dict] = {}

    for k in sorted(kayitlar, key=lambda x: str(x.get("zaman"))):
        z = _zaman(k)
        durumlar[str(k.get("durum"))] += 1
        for a in k.get("adimlar") or []:
            if not isinstance(a, dict):
                continue
            anahtar = (str(a.get("calistirici")), a.get("model") or None)
            _topla(toplam, a)
            _topla(modeller[anahtar], a)
            _topla(roller[str(a.get("rol"))], a)
            _topla(projeler[k.get("_proje", "-")], a)
            yeni = _int(a.get("token_girdi")) + _int(a.get("token_cikti"))
            if z:
                if z >= bugun_basi:
                    _topla(bugun, a)
                if z >= hafta_basi:
                    _topla(hafta, a)
                gunluk[z.strftime("%Y-%m-%d")] += yeni
            sinif = hata_sinifi(a.get("hata")) if not a.get("ok", True) else None
            if sinif:
                hatalar[sinif] += 1
                son_hatalar.append({"zaman": k.get("zaman"), "proje": k.get("_proje", "-"), "calistirici": anahtar[0], "model": anahtar[1], "rol": a.get("rol"),
                                    "sinif": sinif, "mesaj": str(a.get("hata"))[:160]})
                if sinif == "limit" and z and simdi - z <= timedelta(hours=LIMIT_PENCERESI_SA):
                    guncel_limit[anahtar] = {"zaman": k.get("zaman"), "mesaj": str(a.get("hata"))[:160]}
        # hata ADIM metninde degil, gorev mesajinda olabilir (butce asildi vb.)
        if k.get("durum") == "butce_asildi":
            hatalar["butce"] += 1

    gunler = [(bugun_basi - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(gun_sayisi - 1, -1, -1)]
    return {
        "gorev_sayisi": len(kayitlar),
        "toplam": _bitir(toplam), "bugun": _bitir(bugun), "hafta": _bitir(hafta),
        "gunluk": [{"gun": g, "yeni": gunluk.get(g, 0)} for g in gunler],
        "modeller": sorted(({"calistirici": c, "model": m, **_bitir(v)} for (c, m), v in modeller.items()), key=lambda x: -x["yeni"]),
        "roller": sorted(({"rol": r, **_bitir(v)} for r, v in roller.items()), key=lambda x: -x["yeni"]),
        "projeler": sorted(({"proje": p, **_bitir(v)} for p, v in projeler.items()), key=lambda x: -x["yeni"]),
        "durumlar": dict(durumlar),
        "hatalar": {SINIF_ADLARI[s]: n for s, n in sorted(hatalar.items(), key=lambda x: -x[1])},
        "son_hatalar": son_hatalar[-8:][::-1],
        "_guncel_limit": [{"calistirici": c, "model": m, **v} for (c, m), v in guncel_limit.items()],
        "_bugun_basi": bugun_basi.strftime("%Y-%m-%d"),
    }


def oneriler(ozet_verisi: dict, roller: dict[str, dict] | None, adaylar: list[dict]) -> list[dict]:
    """roller: acik projenin {rol: {calistirici, model}}; adaylar: [{calistirici, model, ucretsiz?}] (kurulu/bagli secenekler).
    Her oneri 'uygula' alani tasiyabilir: {rol, calistirici, model}; arayuz bunu tek tikla ayara yazar."""
    cikti: list[dict] = []
    roller = roller or {}
    for sorun in ozet_verisi.get("_guncel_limit", []):
        c, m = sorun["calistirici"], sorun["model"]
        etkilenen = [r for r, x in roller.items() if x.get("calistirici") == c and (x.get("model") or None) == m]
        secenekler = [a for a in adaylar if not (a["calistirici"] == c and (a.get("model") or None) == m)]
        secenekler.sort(key=lambda a: (not a.get("ucretsiz"), a["calistirici"] != c))  # once ucretsizler, sonra ayni CLI
        ad = f"{c}" + (f" · {m}" if m else "")
        if not secenekler:
            cikti.append({"tur": "limit", "baslik": f"{ad} limite takıldı", "aciklama": f"{sorun['zaman']}: {sorun['mesaj']}. Geçilecek başka bir model yok; Ajanlar sekmesinden yeni bir model ekleyin."})
            continue
        for rol in etkilenen or [None]:
            for aday in secenekler[:2]:
                hedef = f"{aday['calistirici']}" + (f" · {aday['model']}" if aday.get("model") else "")
                oneri = {"tur": "limit", "baslik": f"{ad} limite takıldı",
                         "aciklama": f"{sorun['zaman']}: {sorun['mesaj']}" + (f" Rol '{rol}' için {hedef} denenebilir." if rol else f" {hedef} denenebilir."),
                         "etiket": f"{rol or 'rol'} → {hedef}" + (" (ücretsiz)" if aday.get("ucretsiz") else "")}
                if rol:
                    oneri["uygula"] = {"rol": rol, "calistirici": aday["calistirici"], "model": aday.get("model")}
                cikti.append(oneri)
    butce = ozet_verisi.get("durumlar", {}).get("butce_asildi", 0)
    if butce:
        cikti.append({"tur": "butce", "baslik": f"{butce} görev bütçeyi aştı", "aciklama": "Ajanlar sekmesinde ya da roller.json içinde butce_token değerini artırın ya da daha ucuz/ücretsiz bir model seçin."})
    kimlik = ozet_verisi.get("hatalar", {}).get(SINIF_ADLARI["kimlik"], 0)
    if kimlik:
        cikti.append({"tur": "kimlik", "baslik": f"{kimlik} adımda anahtar/giriş hatası", "aciklama": "İlgili CLI'a yeniden giriş yapın ya da Modeller bölümünde anahtarı yenileyin ('Anahtarı dene' ile sınayın)."})
    return cikti
