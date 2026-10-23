"""Tanimla eklenen CLI'lar: yeni bir kod ajani CLI'i icin kod yazmak yerine bir TANIM verilir.

Tanimlar kullanici duzeyinde saklanir (`~/.aktapokus/clilar.json`, AKTAPOKUS_CLILAR ile degistirilir); tum projelerde gecerlidir.
Bir tanim sunlari soyler: hangi program (mutlak yol), istem nasil verilir (stdin ya da arguman), model/izin bayraklari ve cikti
nasil okunur (duz metin, tek JSON, satir satir JSON + noktali yollar). Genel `TanimliCalistirici` bunu calistirir.

Guvenlik: tanim, kullanicinin makinesinde keyfi program calistirmak demektir. Bu yuzden program yolu MUTLAK ve var olan bir dosya
olmali, .cmd/.bat/.ps1 sarmalayicilari reddedilir (cmd.exe istemi yorumlardi), kabuk kullanilmaz, istem arguman olarak verilecekse
'-' ile baslayamaz, ve tanim adi 'opencode' ile baslayamaz (o ad koruyucu kapsami demektir; ozel CLI'lar koruyucusuzdur)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .runners import (
    AZAMI_ISTEM_UZUNLUGU,
    Calistirici,
    CalistiriciHatasi,
    CalistirmaSonucu,
    _metin,
    _stdinli_calistir,
    _alt_surec_ortami,
    claude_bul,
    codex_bul,
    opencode_bul,
)

KAYIT_ORTAMI = "AKTAPOKUS_CLILAR"
YERLESIK = ("opencode", "opencode-sunucu", "claude", "codex")
AD_DESENI = re.compile(r"^[a-z0-9][a-z0-9_-]{0,30}$")
YASAK_UZANTILAR = {".cmd", ".bat", ".ps1", ".vbs"}
CIKTI_BICIMLERI = ("metin", "json", "jsonl")
ISTEM_YERI = "{istem}"


class TanimHatasi(Exception):
    pass


@dataclass(frozen=True)
class CliTanim:
    ad: str
    komut: tuple[str, ...]  # [program (mutlak yol), sabit argumanlar...]; istem=arguman ise tam olarak bir '{istem}' ogesi icerir
    gorunen_ad: str = ""
    istem: str = "stdin"  # "stdin" | "arguman"
    model_bayragi: str | None = None  # ornek "--model"
    onayli_args: tuple[str, ...] = ()  # dosya DEGISTIRMEYE izinli calisma icin eklenen argumanlar
    salt_okunur_args: tuple[str, ...] = ()  # onay verilmediginde eklenenler
    cikti: str = "metin"
    metin_yolu: str | None = None  # json/jsonl: yanit metninin noktali yolu, ornek "result" ya da "item.text"
    hata_yolu: str | None = None  # bu yol doluysa (true/metin) calisma BASARISIZ sayilir
    girdi_yolu: str | None = None
    cikti_yolu: str | None = None
    onbellek_yolu: str | None = None
    modeller: tuple[str, ...] = ()  # arayuzde onerilen model adlari
    aciklama: str = ""

    def sozluk(self) -> dict:
        return {
            "ad": self.ad, "gorunen_ad": self.gorunen_ad, "komut": list(self.komut), "istem": self.istem,
            "model_bayragi": self.model_bayragi, "onayli_args": list(self.onayli_args),
            "salt_okunur_args": list(self.salt_okunur_args), "cikti": self.cikti, "metin_yolu": self.metin_yolu,
            "hata_yolu": self.hata_yolu, "girdi_yolu": self.girdi_yolu, "cikti_yolu": self.cikti_yolu,
            "onbellek_yolu": self.onbellek_yolu, "modeller": list(self.modeller), "aciklama": self.aciklama,
        }


def _metin_listesi(veri: dict, ad: str) -> tuple[str, ...]:
    ham = veri.get(ad, [])
    if not isinstance(ham, list) or not all(isinstance(x, str) for x in ham):
        raise TanimHatasi(f"'{ad}' metinlerden olusan bir liste olmali")
    return tuple(ham)


def _istege_bagli_metin(veri: dict, ad: str) -> str | None:
    deger = veri.get(ad)
    if deger is None or deger == "":
        return None
    if not isinstance(deger, str) or not deger.strip():
        raise TanimHatasi(f"'{ad}' bos olmayan metin ya da bos olmali")
    return deger.strip()


def tanim_coz(veri: object) -> CliTanim:
    if not isinstance(veri, dict):
        raise TanimHatasi("Tanim bir nesne olmali")
    ad = veri.get("ad")
    if not isinstance(ad, str) or not AD_DESENI.match(ad):
        raise TanimHatasi("'ad' kucuk harf/rakam/-/_ icermeli ve 31 karakteri gecmemeli (ornek: aider)")
    if ad in YERLESIK or ad.startswith("opencode"):
        raise TanimHatasi(f"'{ad}' ayrilmis bir ad (yerlesik CLI'lar ve 'opencode' ile baslayanlar kullanilamaz)")
    komut = _metin_listesi(veri, "komut")
    if not komut:
        raise TanimHatasi("'komut' en az programin yolunu icermeli")
    program = Path(komut[0])
    if not program.is_absolute():
        raise TanimHatasi("Program yolu MUTLAK olmali (ornek: C:\\Tools\\aider.exe)")
    if program.suffix.lower() in YASAK_UZANTILAR:
        raise TanimHatasi(f"{program.suffix} sarmalayicilari desteklenmez (cmd.exe istemi yorumlar); gercek .exe dosyasini verin")
    if not program.is_file():
        raise TanimHatasi(f"Program bulunamadi: {program}")
    istem = veri.get("istem", "stdin")
    if istem not in ("stdin", "arguman"):
        raise TanimHatasi("'istem' 'stdin' ya da 'arguman' olmali")
    sayi = sum(1 for a in komut[1:] if a == ISTEM_YERI)
    if istem == "arguman" and sayi != 1:
        raise TanimHatasi(f"istem='arguman' ise 'komut' tam olarak bir tane {ISTEM_YERI} ogesi icermeli")
    if istem == "stdin" and sayi:
        raise TanimHatasi(f"istem='stdin' iken komutta {ISTEM_YERI} olamaz")
    cikti = veri.get("cikti", "metin")
    if cikti not in CIKTI_BICIMLERI:
        raise TanimHatasi(f"'cikti' {', '.join(CIKTI_BICIMLERI)} den biri olmali")
    metin_yolu = _istege_bagli_metin(veri, "metin_yolu")
    if cikti != "metin" and not metin_yolu:
        raise TanimHatasi("json/jsonl ciktisi icin 'metin_yolu' gerekli (yanit metni hangi alanda?)")
    gorunen = veri.get("gorunen_ad") or ad
    if not isinstance(gorunen, str):
        raise TanimHatasi("'gorunen_ad' metin olmali")
    aciklama = veri.get("aciklama") or ""
    if not isinstance(aciklama, str):
        raise TanimHatasi("'aciklama' metin olmali")
    return CliTanim(
        ad=ad, komut=komut, gorunen_ad=gorunen.strip() or ad, istem=istem,
        model_bayragi=_istege_bagli_metin(veri, "model_bayragi"),
        onayli_args=_metin_listesi(veri, "onayli_args"), salt_okunur_args=_metin_listesi(veri, "salt_okunur_args"),
        cikti=cikti, metin_yolu=metin_yolu, hata_yolu=_istege_bagli_metin(veri, "hata_yolu"),
        girdi_yolu=_istege_bagli_metin(veri, "girdi_yolu"), cikti_yolu=_istege_bagli_metin(veri, "cikti_yolu"),
        onbellek_yolu=_istege_bagli_metin(veri, "onbellek_yolu"), modeller=_metin_listesi(veri, "modeller"),
        aciklama=aciklama.strip(),
    )


# ---- kayit defteri ----------------------------------------------------------------------------------------------------

def kayit_yolu() -> Path:
    ortam = os.environ.get(KAYIT_ORTAMI)
    return Path(ortam) if ortam else Path.home() / ".aktapokus" / "clilar.json"


def yukle() -> dict[str, CliTanim]:
    """Gecerli tanimlar. Bozuk ya da gecersiz (ornegin programi silinmis) tanimlar atlanir; hepsini birden bozmaz."""
    yol = kayit_yolu()
    try:
        ham = json.loads(yol.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    tanimlar: dict[str, CliTanim] = {}
    for oge in ham.get("clilar", []) if isinstance(ham, dict) else []:
        try:
            t = tanim_coz(oge)
        except TanimHatasi:
            continue
        tanimlar[t.ad] = t
    return tanimlar


def _yaz(tanimlar: dict[str, CliTanim]) -> None:
    yol = kayit_yolu()
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_suffix(".tmp")
    gecici.write_text(json.dumps({"surum": 1, "clilar": [t.sozluk() for t in tanimlar.values()]}, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(gecici, yol)


def kaydet(tanim: CliTanim) -> None:
    tanimlar = yukle()
    tanimlar[tanim.ad] = tanim
    _yaz(tanimlar)


def sil(ad: str) -> bool:
    tanimlar = yukle()
    if ad not in tanimlar:
        return False
    del tanimlar[ad]
    _yaz(tanimlar)
    return True


def bilinen_adlar() -> list[str]:
    return [*YERLESIK, *yukle().keys()]


def listele() -> list[dict]:
    """Arayuz icin: yerlesik ve eklenen tum CLI'lar, kurulu olup olmadiklariyla."""
    yerlesik = [
        ("opencode", "OpenCode (CLI)", opencode_bul(), ["opencode/deepseek-v4.1-flash-free"], "Koruyuculu (klasor disi ve gizli dosya engeli)"),
        ("opencode-sunucu", "OpenCode (sunucu)", opencode_bul(), ["opencode/deepseek-v4.1-flash-free"], "Koruyuculu, canli ilerleme"),
        ("codex", "Codex", codex_bul(), [], "Klasor disi yazma engelli; gizli dosyalari OKUYABILIR"),
        ("claude", "Claude Code", claude_bul(), ["haiku", "sonnet", "opus"], "Klasor disi yazma ve gizli dosya okuma engelli; komut calistiramaz"),
    ]
    cikti = [
        {"ad": ad, "gorunen_ad": g, "yerlesik": True, "kurulu": bool(yol), "modeller": m, "aciklama": a}
        for ad, g, yol, m, a in yerlesik
    ]
    for t in yukle().values():
        cikti.append({
            "ad": t.ad, "gorunen_ad": t.gorunen_ad, "yerlesik": False, "kurulu": Path(t.komut[0]).is_file(),
            "modeller": list(t.modeller), "aciklama": t.aciklama or "Ozel CLI (koruyucusuz)", "tanim": t.sozluk(),
        })
    return cikti


# ---- calistirma -------------------------------------------------------------------------------------------------------

def yol_al(veri: object, yol: str | None):
    """'a.b.0.c' gibi noktali yoldan deger; yoksa None."""
    if not yol:
        return None
    for parca in yol.split("."):
        if isinstance(veri, dict):
            veri = veri.get(parca)
        elif isinstance(veri, list) and parca.isdigit() and int(parca) < len(veri):
            veri = veri[int(parca)]
        else:
            return None
    return veri


def _tam(deger) -> int:
    return int(deger) if isinstance(deger, (int, float)) and not isinstance(deger, bool) else 0


def cikti_coz(tanim: CliTanim, cikti: str) -> CalistirmaSonucu:
    if tanim.cikti == "metin":
        return CalistirmaSonucu(ok=True, metin=cikti.strip())
    nesneler: list[object] = []
    if tanim.cikti == "json":
        try:
            nesneler = [json.loads(cikti)]
        except json.JSONDecodeError:
            return CalistirmaSonucu(False, hata=f"{tanim.gorunen_ad} ciktisi JSON degil: {cikti.strip()[:200]}")
    else:
        for satir in cikti.splitlines():
            satir = satir.strip()
            if satir.startswith("{"):
                try:
                    nesneler.append(json.loads(satir))
                except json.JSONDecodeError:
                    continue

    def son(yol):  # jsonl: her alan icin sonuncu dolu deger
        for n in reversed(nesneler):
            d = yol_al(n, yol)
            if d is not None:
                return d
        return None

    metin = son(tanim.metin_yolu)
    hata_degeri = son(tanim.hata_yolu)
    hata_var = bool(hata_degeri) and hata_degeri not in ("false", "0")
    metin_s = metin if isinstance(metin, str) else ("" if metin is None else json.dumps(metin, ensure_ascii=False))
    return CalistirmaSonucu(
        ok=not hata_var, metin=metin_s.strip(),
        token_girdi=_tam(son(tanim.girdi_yolu)), token_cikti=_tam(son(tanim.cikti_yolu)), token_onbellek=_tam(son(tanim.onbellek_yolu)),
        hata=(metin_s.strip() or str(hata_degeri))[:300] if hata_var else None,
    )


class TanimliCalistirici(Calistirici):
    """Bir `CliTanim`'i calistirir. Kabuk yok; istem stdin'den (UTF-8 bayt) ya da tek bir arguman olarak gider."""

    def __init__(self, tanim: CliTanim):
        self.tanim = tanim
        self.ad = tanim.ad

    def komut(self, istem: str, model: str | None, onayli: bool) -> list[str]:
        t = self.tanim
        if not Path(t.komut[0]).is_file():
            raise CalistiriciHatasi(f"{t.gorunen_ad}: program bulunamadi ({t.komut[0]})")
        komut = list(t.komut)
        komut += list(t.onayli_args if onayli else t.salt_okunur_args)
        if model:
            if not t.model_bayragi:
                raise CalistiriciHatasi(f"{t.gorunen_ad} model secimini desteklemiyor (tanimda model_bayragi yok); rolde 'model'i bos birakin")
            if model.startswith("-"):
                raise CalistiriciHatasi("Model adi '-' ile baslayamaz")
            komut += [t.model_bayragi, model]
        if t.istem == "arguman":
            if len(istem) > AZAMI_ISTEM_UZUNLUGU:
                raise CalistiriciHatasi(f"Istem cok uzun ({len(istem)} karakter, sinir {AZAMI_ISTEM_UZUNLUGU})")
            if istem.lstrip().startswith("-"):
                raise CalistiriciHatasi("Istem '-' ile baslayamaz (secenek sanilirdi)")
            komut = [istem if a == ISTEM_YERI else a for a in komut]
        return komut

    def calistir(self, istem, klasor, model=None, agent=None, zaman_asimi_sn=900, onayli=True):
        if not istem.strip():
            raise CalistiriciHatasi("Bos istem gonderilemez")
        if len(istem) > 1_000_000:
            raise CalistiriciHatasi("Istem cok uzun (1 milyon karakter siniri)")
        komut = self.komut(istem, model, onayli)
        baslangic = time.monotonic()
        try:
            if self.tanim.istem == "stdin":
                islem = _stdinli_calistir(komut, istem, Path(klasor), zaman_asimi_sn)
            else:
                islem = subprocess.run(
                    komut, cwd=str(klasor), env=_alt_surec_ortami(Path(klasor)), capture_output=True,
                    stdin=subprocess.DEVNULL, timeout=zaman_asimi_sn,
                )
                islem.stdout, islem.stderr = _metin(islem.stdout), _metin(islem.stderr)
        except subprocess.TimeoutExpired:
            return CalistirmaSonucu(False, hata=f"Zaman asimi ({zaman_asimi_sn} sn)", sure_sn=time.monotonic() - baslangic)
        except OSError as hata:
            return CalistirmaSonucu(False, hata=f"{self.tanim.gorunen_ad} baslatilamadi: {hata}", sure_sn=time.monotonic() - baslangic)
        sonuc = cikti_coz(self.tanim, islem.stdout)
        sonuc.sure_sn = time.monotonic() - baslangic
        if islem.returncode != 0 and sonuc.ok:
            sonuc.ok = False
            sonuc.hata = f"{self.tanim.gorunen_ad} cikis kodu {islem.returncode}: {(islem.stderr or islem.stdout).strip()[-300:]}"
        return sonuc


__all__ = ["CliTanim", "TanimHatasi", "TanimliCalistirici", "tanim_coz", "yukle", "kaydet", "sil", "listele", "bilinen_adlar", "cikti_coz", "yol_al"]
