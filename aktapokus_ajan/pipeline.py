"""Rol hatti: gorevi sirayla rollere dagitir (ornegin kodcu -> test), dogrulama basarisizsa duzeltme dongusu,
token butcesi, git anlik goruntusu, fark gosterimi, onay ve geri alma."""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from . import baglam as baglam_modulu, guard, snapshot
from .config import AYAR_KLASORU, Ayar, Rol
from .klasor import guvenli_klasor
from .runners import Calistirici, CalistirmaSonucu

KAYIT_KLASORU = "kayit"
GENEL_KURAL = (
    "KURALLAR: Yalnizca calisma klasoru icindeki dosyalari degistir. Klasor disina yazma, "
    "ag uzerinden veri gonderme, .env ve anahtar/parola dosyalarini okuma ya da yazma. "
    "Emin degilsen dur ve belirt. Onceki calismalarin ozeti: .aktapokus/DURUM.md (varsa once oku)."
)
AZAMI_ONCEKI_CIKTI = 6000
_SONUC = re.compile(r"SONU[ÇC]\s*:\s*(BA[ŞS]ARILI|BA[ŞS]ARISIZ)", re.IGNORECASE)


class HatHatasi(Exception):
    pass


@dataclass
class AdimKaydi:
    sira: int
    rol: str
    calistirici: str
    model: str | None
    ok: bool
    metin: str
    token_girdi: int
    token_cikti: int
    token_onbellek: int
    sure_sn: float
    hata: str | None = None
    dogrulama: str | None = None  # basarili | basarisiz | belirsiz


@dataclass
class HatSonucu:
    durum: str  # onaylandi | geri_alindi | degisiklik_yok | basarisiz | butce_asildi | dogrulama_basarisiz
    adimlar: list[AdimKaydi] = field(default_factory=list)
    token_toplam: int = 0
    degisen: dict[str, str] = field(default_factory=dict)
    fark_ozeti: str = ""
    korundu: bool = False
    mesaj: str = ""
    kayit_yolu: Path | None = None
    once: str = ""
    sonra: str = ""


def dogrulama_sonucu(metin: str) -> bool | None:
    """Metindeki SONUC: BASARILI/BASARISIZ satirinin SONUNCUSUNU okur. Bulunamazsa None."""
    bulunan = _SONUC.findall(metin)
    if not bulunan:
        return None
    return bulunan[-1].upper().startswith("BAŞARILI") or bulunan[-1].upper().startswith("BASARILI")


def _kisalt(metin: str, sinir: int = AZAMI_ONCEKI_CIKTI) -> str:
    if len(metin) <= sinir:
        return metin
    yarim = sinir // 2
    return f"{metin[:yarim]}\n... [{len(metin) - sinir} karakter atlandi] ...\n{metin[-yarim:]}"


def istem_olustur(rol: Rol, gorev: str, onceki: str | None, duzeltme_notu: str | None) -> str:
    parcalar = [GENEL_KURAL, f"ROLUN: {rol.ad}. {rol.talimat}", f"GOREV:\n{gorev}"]
    if duzeltme_notu:
        parcalar.append(
            "ONCEKI DENEME DOGRULAMADAN GECMEDI. Test bulgulari asagida; sorunlari gider:\n" + _kisalt(duzeltme_notu)
        )
    elif onceki:
        parcalar.append("ONCEKI ADIMIN CIKTISI:\n" + _kisalt(onceki))
    return "\n\n".join(parcalar)


def _yeni_kayit_kimligi() -> str:
    """Kimlikler OLUSTURMA SIRASIYLA siralanir (son_kayit/geri-al dosya adi sirasina dayanir): milisaniye eklenir; rastgele ek yalniz cakismayi onler."""
    t = time.time()
    return time.strftime("%Y%m%d-%H%M%S", time.localtime(t)) + f"-{int(t * 1000) % 1000:03d}-" + uuid.uuid4().hex[:4]


def _kayit_klasoru(klasor: Path) -> Path:
    return klasor / AYAR_KLASORU / KAYIT_KLASORU


def calistir_hat(
    klasor: str | Path,
    gorev: str,
    ayar: Ayar,
    calistirici_uret: Callable[[str], Calistirici],
    onay: Callable[[str], bool],
    bildir: Callable[[str], None] = lambda _m: None,
    olay: Callable[[dict], None] = lambda _e: None,
    iptal: threading.Event | None = None,
) -> HatSonucu:
    """olay: yapisal ilerleme olaylari (arayuz icin); iptal: ayarlanirsa bir sonraki adimdan once durur."""
    if not gorev.strip():
        raise HatHatasi("Gorev bos olamaz")
    klasor = guvenli_klasor(klasor)
    if not snapshot.hazir_mi(klasor):
        raise HatHatasi(
            f"{klasor} icin geri alma hazir degil (git deposu degil ve golge yedek kurulmamis): once klasoru arayuzden ya da 'aktapokus ac {klasor}' ile acin."
        )
    sira = ayar.rol_sirasi()
    if any(r.calistirici.startswith("opencode") for r in sira):
        eksik = guard.dogrula(klasor)
        if eksik:
            raise HatHatasi(
                "Koruyucu (klasor siniri / .env engeli) etkin degil: " + "; ".join(eksik) +
                f". Kurmak icin: aktapokus ac \"{klasor}\""
            )
    korumasiz = [r for r in sira if not r.calistirici.startswith("opencode")]
    if korumasiz:
        bildir("UYARI: " + ", ".join(sorted({r.calistirici for r in korumasiz})) + " rolleri icin OpenCode koruyucusu (klasor disi okuma/.env engeli) uygulanmaz.")
        riskli = [r for r in korumasiz if not r.okuma_riski_kabul]
        hassas = guard.hassas_dosyalar(klasor) if riskli else []
        if hassas:
            raise HatHatasi(
                "Bu klasorde gizli/hassas dosyalar var (" + ", ".join(hassas[:5]) + ("..." if len(hassas) > 5 else "") + ") ve "
                + ", ".join(sorted({r.calistirici for r in riskli})) + " rolu bunlari OKUYUP modele/buluta gonderebilir (koruyucusu yok). "
                "Cozum: dosyalari proje disina tasiyin, ya da bu rolleri OpenCode ile calistirin, ya da riski bilerek kabul edip "
                "rolde \"okuma_riski_kabul\": true yazin."
            )
    if ayar.baglam:  # ajanin degisikligi sayilmasin diye anlik goruntuden ONCE
        try:
            degisen_baglam = {d: s for d, s in baglam_modulu.guncelle(klasor, ayar).items() if s != "ayni"}
            if degisen_baglam:
                bildir("Ortak baglam guncellendi: " + ", ".join(f"{d} ({s})" for d, s in degisen_baglam.items()))
        except OSError as hata:
            bildir(f"UYARI: ortak baglam dosyalari yazilamadi ({hata}); devam ediliyor.")
    kimlik = _yeni_kayit_kimligi()
    once = snapshot.anlik_goruntu(klasor, f"aktapokus {kimlik} oncesi")
    sonuc = HatSonucu(durum="", once=once)
    olay({"tur": "basladi", "kimlik": kimlik, "once": once, "butce": ayar.butce_token})
    idx = 0
    duzeltme = 0
    onceki: str | None = None
    duzeltme_notu: str | None = None
    belirsiz = False
    durum = ""
    while idx < len(sira):
        rol = sira[idx]
        if iptal is not None and iptal.is_set():
            durum, sonuc.mesaj = "iptal", "Kullanici durdurdu."
            break
        istem = istem_olustur(rol, gorev, onceki, duzeltme_notu if idx == 0 else None)
        bildir(f"-> {rol.ad} ({rol.calistirici}/{rol.model or 'varsayilan model'}) calisiyor...")
        olay({"tur": "adim-basladi", "sira": len(sonuc.adimlar) + 1, "rol": rol.ad, "calistirici": rol.calistirici, "model": rol.model})
        try:
            r: CalistirmaSonucu = calistirici_uret(rol.calistirici).calistir(
                istem, klasor, model=rol.model, agent=rol.agent, zaman_asimi_sn=ayar.zaman_asimi_sn, onayli=True
            )
        except Exception as hata:  # calistirici bulunamadi/istem gecersiz vb.
            r = CalistirmaSonucu(False, hata=f"{type(hata).__name__}: {hata}")
        sonuc.token_toplam += r.token_yeni
        adim = AdimKaydi(
            sira=len(sonuc.adimlar) + 1,
            rol=rol.ad,
            calistirici=rol.calistirici,
            model=rol.model,
            ok=r.ok,
            metin=r.metin,
            token_girdi=r.token_girdi,
            token_cikti=r.token_cikti,
            token_onbellek=r.token_onbellek,
            sure_sn=round(r.sure_sn, 1),
            hata=r.hata,
        )
        sonuc.adimlar.append(adim)
        olay({"tur": "adim-bitti", "sira": adim.sira, "rol": rol.ad, "ok": r.ok, "hata": r.hata, "token_girdi": r.token_girdi, "token_cikti": r.token_cikti, "token_toplam": sonuc.token_toplam, "sure_sn": adim.sure_sn, "metin": _kisalt(r.metin, 1500)})
        if not r.ok:
            if iptal is not None and iptal.is_set():
                durum, sonuc.mesaj = "iptal", "Kullanici durdurdu."
            else:
                durum, sonuc.mesaj = "basarisiz", f"{rol.ad} adimi basarisiz: {r.hata}"
            break
        if sonuc.token_toplam > ayar.butce_token:
            durum = "butce_asildi"
            sonuc.mesaj = f"Token butcesi asildi ({sonuc.token_toplam} > {ayar.butce_token}); durduruldu."
            break
        if rol.dogrulama:
            d = dogrulama_sonucu(r.metin)
            adim.dogrulama = {True: "basarili", False: "basarisiz", None: "belirsiz"}[d]
            olay({"tur": "dogrulama", "sira": adim.sira, "sonuc": adim.dogrulama})
            if d is False:
                if duzeltme < ayar.azami_duzeltme:
                    duzeltme += 1
                    duzeltme_notu = r.metin
                    bildir(f"   dogrulama basarisiz; duzeltme {duzeltme}/{ayar.azami_duzeltme}")
                    olay({"tur": "duzeltme", "no": duzeltme, "azami": ayar.azami_duzeltme})
                    idx = 0
                    continue
                durum = "dogrulama_basarisiz"
                sonuc.mesaj = f"Dogrulama {ayar.azami_duzeltme} duzeltmeden sonra da basarisiz."
                break
            if d is None:
                belirsiz = True
        onceki = r.metin
        duzeltme_notu = None
        idx += 1
    sonra = snapshot.anlik_goruntu(klasor, f"aktapokus {kimlik} sonrasi")
    sonuc.sonra = sonra
    sonuc.degisen = snapshot.degisenler(klasor, once, sonra)
    sonuc.fark_ozeti = snapshot.fark_ozeti(klasor, once, sonra) if sonuc.degisen else ""
    if not durum:
        durum = "tamam"
        if belirsiz:
            sonuc.mesaj = "Dogrulama sonucu belirsiz (SONUC satiri yok); degisiklikleri kendiniz kontrol edin."
    if not sonuc.degisen:
        sonuc.durum = "degisiklik_yok" if durum == "tamam" else durum
        if durum == "tamam":
            sonuc.mesaj = (
                "Klasorde hicbir dosya degismedi. Ajan bir sey yaptigini soylese bile, calisma klasoru disinda "
                "calismis olabilir; ciktiyi ve kaydi kontrol edin."
            )
    else:
        bildir("Degisen dosyalar:\n" + sonuc.fark_ozeti)
        uyari = "" if durum == "tamam" else f" (UYARI: {durum})"
        olay({"tur": "fark", "degisen": sonuc.degisen, "ozet": sonuc.fark_ozeti, "once": once, "sonra": sonra, "durum": durum, "mesaj": sonuc.mesaj})
        if onay(f"Degisiklikler korunsun mu?{uyari}"):
            sonuc.korundu = True
            sonuc.durum = "onaylandi" if durum == "tamam" else durum
        else:
            snapshot.geri_yukle(klasor, once, sonra)
            sonuc.durum = "geri_alindi" if durum == "tamam" else durum
    sonuc.kayit_yolu = _kayit_yaz(klasor, kimlik, gorev, ayar, sonuc)
    olay({"tur": "bitti", "durum": sonuc.durum, "mesaj": sonuc.mesaj, "korundu": sonuc.korundu, "token_toplam": sonuc.token_toplam, "degisen": sonuc.degisen})
    return sonuc


def _kayit_yaz(klasor: Path, kimlik: str, gorev: str, ayar: Ayar, sonuc: HatSonucu) -> Path:
    klasoru = _kayit_klasoru(klasor)
    klasoru.mkdir(parents=True, exist_ok=True)
    kayit = {
        "id": kimlik,
        "zaman": time.strftime("%Y-%m-%d %H:%M:%S"),
        "gorev": gorev,
        "akis": list(ayar.akis),
        "durum": sonuc.durum,
        "korundu": sonuc.korundu,
        "mesaj": sonuc.mesaj,
        "token_toplam": sonuc.token_toplam,
        "butce_token": ayar.butce_token,
        "once": sonuc.once,
        "sonra": sonuc.sonra,
        "degisen": sonuc.degisen,
        "adimlar": [{**asdict(a), "metin": a.metin[:2000]} for a in sonuc.adimlar],
        "geri_alindi_sonradan": False,
    }
    yol = klasoru / f"{kimlik}.json"
    yol.write_text(json.dumps(kayit, ensure_ascii=False, indent=2), encoding="utf-8")
    return yol


def son_kayit(klasor: str | Path) -> dict | None:
    klasoru = _kayit_klasoru(Path(klasor))
    dosyalar = sorted(klasoru.glob("*.json")) if klasoru.is_dir() else []
    if not dosyalar:
        return None
    kayit = json.loads(dosyalar[-1].read_text(encoding="utf-8"))
    kayit["_yol"] = str(dosyalar[-1])
    return kayit


def geri_al(
    klasor: str | Path,
    onay: Callable[[str], bool],
    bildir: Callable[[str], None] = lambda _m: None,
) -> int:
    """Son calistirmanin ONCESINE doner. Arada sizin yaptiginiz degisiklikleri de geri alabilir; bu yuzden listeler ve onay ister."""
    klasor = guvenli_klasor(klasor)
    kayit = son_kayit(klasor)
    if kayit is None:
        raise HatHatasi("Geri alinacak calistirma kaydi yok")
    if kayit.get("geri_alindi_sonradan") or kayit["durum"] == "geri_alindi":
        raise HatHatasi("Son calistirma zaten geri alinmis")
    simdi = snapshot.anlik_goruntu(klasor, "aktapokus geri-al oncesi")
    farklar = snapshot.degisenler(klasor, kayit["once"], simdi)
    if not farklar:
        raise HatHatasi("Calistirma oncesiyle simdiki hal ayni; geri alinacak bir sey yok")
    bildir("Geri alinacak dosyalar (A=silinecek, M=eski haline, D=geri gelecek):")
    for yol, d in sorted(farklar.items()):
        bildir(f"  {d} {yol}")
    if not onay("Bu dosyalar calistirma oncesine dondurulsun mu? (Arada kendi yaptiginiz degisiklikler de gider)"):
        return 0
    sayi = snapshot.geri_yukle(klasor, kayit["once"], simdi)
    kayit_yolu = Path(kayit.pop("_yol"))
    kayit["geri_alindi_sonradan"] = True
    kayit_yolu.write_text(json.dumps(kayit, ensure_ascii=False, indent=2), encoding="utf-8")
    return sayi
