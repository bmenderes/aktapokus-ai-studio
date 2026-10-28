"""Otomasyon is akisi (gorsel tuval) modeli: dugumler + oklar. Tasarim: docs/otomasyon-akis-tasarimi.md

Ilk dilim: tetikleyici (elle | zamanlayici) -> gorev -> bildirim (Telegram). Akis YALNIZ veridir; calistirma yolu otomasyon_calistir'dir ve
plan onayi HER ZAMAN istenir: dugum ayarlarinda onay/otomatik onay alani YOKTUR (bilinmeyen alanlar kayitta dusurulur)."""

from __future__ import annotations

import re
from typing import Callable

from . import github, web_getir, yayin

AZAMI_DUGUM = 12
AZAMI_OK = 16
AZAMI_METIN = 4000
AZAMI_BILDIRIM = 500
KIMLIK_DESENI = re.compile(r"^[a-z0-9][a-z0-9_-]{0,19}$")
TETIKLEYICILER = ("elle", "zamanlayici")
TURLER = TETIKLEYICILER + ("web", "gorev", "yayinla", "bildirim")
KOORDINAT_SINIRI = 20000


class AkisHatasi(ValueError):
    pass


def _sayi(v: object, ad: str) -> int:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or abs(v) > KOORDINAT_SINIRI:
        raise AkisHatasi(f"Dugum konumu ({ad}) gecersiz")
    return int(v)


def _metin(ayar: dict, anahtar: str, azami: int, zorunlu: bool) -> str:
    m = ayar.get(anahtar)
    if m is None and not zorunlu:
        return ""
    if not isinstance(m, str) or "\x00" in m or len(m) > azami or (zorunlu and not m.strip()):
        raise AkisHatasi(f"'{anahtar}' {'bos olmayan ' if zorunlu else ''}metin olmali (en cok {azami} karakter)")
    return m.strip()


MOTORLAR = ("opencode-sunucu", "claude", "codex", "gemini", "mistral")  # config.OTOMASYON_MOTORLARI ile ayni (dairesel ice aktarma olmasin diye kopya; test eslesmeyi denetler)


def _model(m: object) -> dict:
    """Gorev dugumunun istege bagli model secimi: {calistirici, model|None}. Yoksa gorev projenin rol ayariyla calisir."""
    if not isinstance(m, dict) or m.get("calistirici") not in MOTORLAR:
        raise AkisHatasi(f"Model secimi icin calistirici su degerlerden biri olmali: {', '.join(MOTORLAR)}")
    ad = m.get("model")
    if ad is not None and (not isinstance(ad, str) or not ad.strip() or len(ad) > 120 or any(ord(c) < 32 for c in ad)):
        raise AkisHatasi("Model adi gecersiz")
    return {"calistirici": m["calistirici"], "model": ad.strip() if ad else None}


def gorev_modeli(akis: dict | None) -> tuple[str, str | None] | None:
    """Akistaki gorev dugumunun model secimi (calistirici, model) ya da None (projenin rol ayari)."""
    for d in (akis or {}).get("dugumler", []):
        if d.get("tur") == "gorev" and d.get("ayar", {}).get("model"):
            m = d["ayar"]["model"]
            return m["calistirici"], m.get("model")
    return None


def coz(akis: object, zamanlama_coz: Callable[[object], dict]) -> dict:
    """Akisi dogrular ve temizlenmis kopyasini + turetilmis alanlari doner: {dugumler, oklar, tur, zamanlama, gorev}."""
    if not isinstance(akis, dict):
        raise AkisHatasi("'akis' bir nesne olmali")
    ham_d, ham_o = akis.get("dugumler"), akis.get("oklar", [])
    if not isinstance(ham_d, list) or not ham_d or len(ham_d) > AZAMI_DUGUM:
        raise AkisHatasi(f"Akis 1-{AZAMI_DUGUM} dugum icermeli")
    if not isinstance(ham_o, list) or len(ham_o) > AZAMI_OK:
        raise AkisHatasi(f"En cok {AZAMI_OK} ok olabilir")
    dugumler: dict[str, dict] = {}
    for d in ham_d:
        if not isinstance(d, dict):
            raise AkisHatasi("Dugum bir nesne olmali")
        kimlik, tur = d.get("id"), d.get("tur")
        if not isinstance(kimlik, str) or not KIMLIK_DESENI.fullmatch(kimlik) or kimlik in dugumler:
            raise AkisHatasi("Dugum kimligi gecersiz ya da tekrarli")
        if tur not in TURLER:
            raise AkisHatasi(f"Dugum turu su degerlerden biri olmali: {', '.join(TURLER)}")
        ayar = d.get("ayar") if isinstance(d.get("ayar"), dict) else {}
        if tur == "gorev":
            temiz = {"gorev": _metin(ayar, "gorev", AZAMI_METIN, True)}
            if ayar.get("model") is not None:
                temiz["model"] = _model(ayar["model"])
        elif tur == "web":
            try:
                temiz = {"adresler": web_getir.adres_listesi(ayar.get("adresler"))}
            except web_getir.WebHatasi as hata:
                raise AkisHatasi(str(hata)) from None
        elif tur == "yayinla":
            depo = ayar.get("depo")
            if not isinstance(depo, str) or not github.DEPO_DESENI.fullmatch(depo.strip()):
                raise AkisHatasi("Yayinla icin hedef depo 'sahip/ad' biciminde olmali (ornek: aktapokus/aktapokus.github.io)")
            try:
                temiz = {"depo": depo.strip(), "kaynak": yayin.kaynak_goreli(ayar.get("kaynak")), "hedef_yol": yayin.hedef_yol_dogrula(ayar.get("hedef_yol"))}
            except yayin.YayinHatasi as hata:
                raise AkisHatasi(str(hata)) from None
        elif tur == "bildirim":
            temiz = {"metin": _metin(ayar, "metin", AZAMI_BILDIRIM, True)}
        elif tur == "zamanlayici":
            temiz = {"zamanlama": zamanlama_coz(ayar.get("zamanlama"))}
        else:
            temiz = {}
        dugumler[kimlik] = {"id": kimlik, "tur": tur, "x": _sayi(d.get("x", 0), "x"), "y": _sayi(d.get("y", 0), "y"), "ayar": temiz}
    tetik = [d for d in dugumler.values() if d["tur"] in TETIKLEYICILER]
    gorevler = [d for d in dugumler.values() if d["tur"] == "gorev"]
    if len(tetik) != 1:
        raise AkisHatasi("Akista tam olarak bir tetikleyici olmali")
    if len(gorevler) != 1:
        raise AkisHatasi("Akista tam olarak bir gorev dugumu olmali")
    web = [d for d in dugumler.values() if d["tur"] == "web"]
    if len(web) > 1:
        raise AkisHatasi("Akista en cok bir web getir dugumu olabilir")
    yay = [d for d in dugumler.values() if d["tur"] == "yayinla"]
    if len(yay) > 1:
        raise AkisHatasi("Akista en cok bir yayinla dugumu olabilir")
    oklar: list[dict] = []
    for o in ham_o:
        if not isinstance(o, dict) or o.get("kaynak") not in dugumler or o.get("hedef") not in dugumler:
            raise AkisHatasi("Ok bilinen iki dugumu baglamali")
        k, h = dugumler[o["kaynak"]]["tur"], dugumler[o["hedef"]]["tur"]
        gecerli = (k in TETIKLEYICILER and h == "web") or (k == "web" and h == "gorev") or (k in TETIKLEYICILER and h == "gorev" and not web) or (k == "gorev" and h in ("bildirim", "yayinla"))
        if not gecerli:
            raise AkisHatasi("Ok yalniz tetikleyici -> (web getir) -> gorev ve gorev -> (yayinla | bildirim) yonunde olabilir")
        if any(x["kaynak"] == o["kaynak"] and x["hedef"] == o["hedef"] for x in oklar):
            raise AkisHatasi("Ayni ok iki kez cizilemez")
        oklar.append({"kaynak": o["kaynak"], "hedef": o["hedef"]})
    var = lambda k, h: any(o["kaynak"] == k["id"] and o["hedef"] == h["id"] for o in oklar)  # noqa: E731
    if web:
        if not (var(tetik[0], web[0]) and var(web[0], gorevler[0])):
            raise AkisHatasi("Tetikleyici web getir dugumune, o da gorev dugumune baglanmali")
    elif not var(tetik[0], gorevler[0]):
        raise AkisHatasi("Tetikleyici gorev dugumune baglanmali")
    if yay and not var(gorevler[0], yay[0]):
        raise AkisHatasi("Gorev dugumu yayinla dugumune baglanmali")
    z = tetik[0]["ayar"].get("zamanlama")
    return {"dugumler": list(dugumler.values()), "oklar": oklar, "tur": "zamanli" if z else "sablon", "zamanlama": z, "gorev": gorevler[0]["ayar"]["gorev"]}


def sablondan_akis(gorev: str, zamanlama: dict | None) -> dict:
    """Akissiz (eski) sablonu tuvalde gostermek icin: tetikleyici -> gorev. Kayda yazilmaz; kullanici kaydedince akis olur."""
    tetik = {"id": "t1", "tur": "zamanlayici" if zamanlama else "elle", "x": 40, "y": 60, "ayar": {"zamanlama": zamanlama} if zamanlama else {}}
    return {"dugumler": [tetik, {"id": "g1", "tur": "gorev", "x": 300, "y": 60, "ayar": {"gorev": gorev}}], "oklar": [{"kaynak": "t1", "hedef": "g1"}]}


def web_adresleri(akis: dict | None) -> list[str]:
    """Akistaki web getir dugumunun adresleri (yoksa bos liste)."""
    return next((list(d["ayar"]["adresler"]) for d in (akis or {}).get("dugumler", []) if d.get("tur") == "web"), [])


def yayin_ayari(akis: dict | None) -> dict | None:
    """Akistaki yayinla dugumunun ayari ({depo, kaynak, hedef_yol}) ya da None."""
    return next((dict(d["ayar"]) for d in (akis or {}).get("dugumler", []) if d.get("tur") == "yayinla"), None)


def bildirim_metinleri(akis: dict | None) -> list[str]:
    """Gorev dugumune bagli bildirim dugumlerinin metinleri (akis sirasiyla)."""
    if not akis:
        return []
    dugumler = {d["id"]: d for d in akis.get("dugumler", [])}
    gorev = next((d["id"] for d in dugumler.values() if d["tur"] == "gorev"), None)
    bagli = {o["hedef"] for o in akis.get("oklar", []) if o["kaynak"] == gorev}
    return [d["ayar"]["metin"] for d in dugumler.values() if d["tur"] == "bildirim" and d["id"] in bagli]
