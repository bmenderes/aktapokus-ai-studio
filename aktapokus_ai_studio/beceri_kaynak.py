"""Cevrimici beceri kaynagi: bir GitHub deposundaki `<klasor>/SKILL.md` becerilerini listeler, onizletir ve `beceriler` klasorune indirir.

Guvenlik: yalniz iki SABIT host (api.github.com, raw.githubusercontent.com; kullanici adres veremez, yonlendirme izlenmez), kaynak
`sahip/depo[/yol]` desenine uymali, yanit boyutu sinirli. Beceri metni GUVENILMEYEN veridir (modele talimat olarak gider): bu modul
yalniz getirir; kullanici icerigi onizleyip onaylamadan arayuz indirme istegi gondermez. Yalniz SKILL.md alinir (scripts/ vb. alinmaz)."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request

from . import beceriler

ONERILEN = (
    {"kaynak": "anthropics/skills", "ad": "Anthropic resmi beceri deposu"},
)
KAYNAK_DESENI = re.compile(r"^([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))/([A-Za-z0-9._-]{1,100})((?:/(?!\.)[A-Za-z0-9._-]{1,100}){0,6})$")
YOL_DESENI = re.compile(r"^(?:(?!\.)[A-Za-z0-9._-]{1,100}/){0,7}([a-z0-9]+(?:-[a-z0-9]+)*)/SKILL\.md$")
AZAMI_YANIT = 2_000_000  # tree yaniti
AZAMI_LISTE = 500
ZAMAN_ASIMI = 15


class _Yonlendirme(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):  # sabit host disina gitmeyi onler
        return None


_ACICI = urllib.request.build_opener(_Yonlendirme)


def kaynak_coz(kaynak: object) -> tuple[str, str, str]:
    """'sahip/depo' ya da 'sahip/depo/alt/yol' -> (sahip, depo, onek). Onek '' ya da 'alt/yol/'."""
    if not isinstance(kaynak, str):
        raise beceriler.BeceriHatasi("Kaynak 'sahip/depo' biciminde olmali (ornek: anthropics/skills)")
    m = KAYNAK_DESENI.fullmatch(kaynak.strip().strip("/"))
    if not m or ".." in kaynak:
        raise beceriler.BeceriHatasi("Kaynak 'sahip/depo' biciminde olmali (ornek: anthropics/skills)")
    sahip, depo, alt = m.group(1), m.group(2), m.group(3).strip("/")
    return sahip, depo, (alt + "/" if alt else "")


def _al(url: str, azami: int) -> bytes:
    u = urllib.parse.urlsplit(url)
    if u.scheme != "https" or u.hostname not in ("api.github.com", "raw.githubusercontent.com"):
        raise beceriler.BeceriHatasi("Yalniz GitHub adreslerine baglanilir")
    r = urllib.request.Request(url, headers={"User-Agent": "aktapokus-ai-studio", "Accept": "application/vnd.github+json"})
    try:
        with _ACICI.open(r, timeout=ZAMAN_ASIMI) as y:
            veri = y.read(azami + 1)
    except urllib.error.HTTPError as hata:
        if hata.code == 404:
            raise beceriler.BeceriHatasi("Depo ya da dosya bulunamadi (ozel depo olabilir; yalniz herkese acik depolar okunur)") from None
        if hata.code in (403, 429):
            raise beceriler.BeceriHatasi("GitHub istek siniri doldu (girissiz saatte ~60 istek); biraz sonra deneyin") from None
        raise beceriler.BeceriHatasi(f"GitHub yaniti hatali (HTTP {hata.code})") from None
    except (urllib.error.URLError, OSError, TimeoutError) as hata:
        raise beceriler.BeceriHatasi(f"GitHub'a ulasilamadi ({type(hata).__name__}); internet baglantinizi denetleyin") from None
    if len(veri) > azami:
        raise beceriler.BeceriHatasi("Yanit cok buyuk, reddedildi")
    return veri


def listele(kaynak: object) -> dict:
    sahip, depo, onek = kaynak_coz(kaynak)
    veri = _al(f"https://api.github.com/repos/{sahip}/{depo}/git/trees/HEAD?recursive=1", AZAMI_YANIT)
    try:
        yanit = json.loads(veri.decode("utf-8"))
        agac = yanit["tree"]
    except (ValueError, KeyError, TypeError):
        raise beceriler.BeceriHatasi("GitHub yaniti okunamadi") from None
    yollar = [o.get("path", "") for o in agac if isinstance(o, dict) and o.get("type") == "blob"]
    kurulu = {b.kimlik for b in beceriler.listele()}
    sonuc = []
    for y in yollar:
        m = YOL_DESENI.fullmatch(y)
        if not m or not y.startswith(onek):
            continue
        klasor = y[: -len("SKILL.md")]
        sonuc.append({"kimlik": m.group(1), "yol": y, "ek_dosya": any(p.startswith(klasor) and p != y for p in yollar), "kurulu": m.group(1) in kurulu})
    sonuc.sort(key=lambda s: s["kimlik"])
    return {"kaynak": f"{sahip}/{depo}" + ("/" + onek.rstrip("/") if onek else ""), "beceriler": sonuc[:AZAMI_LISTE], "kesildi": len(sonuc) > AZAMI_LISTE or bool(yanit.get("truncated"))}


def getir(kaynak: object, yol: object) -> beceriler.Beceri:
    """Uzaktaki SKILL.md'yi indirir ve cozer (diske YAZMAZ)."""
    sahip, depo, _ = kaynak_coz(kaynak)
    if not isinstance(yol, str) or not (m := YOL_DESENI.fullmatch(yol)):
        raise beceriler.BeceriHatasi("Gecersiz beceri yolu")
    ham = _al(f"https://raw.githubusercontent.com/{sahip}/{depo}/HEAD/{urllib.parse.quote(yol)}", beceriler.AZAMI_GOVDE + 20_000)
    try:
        metin = ham.decode("utf-8")
    except UnicodeDecodeError:
        raise beceriler.BeceriHatasi("Dosya UTF-8 metin degil") from None
    return beceriler.coz(m.group(1), metin)


def indir(kaynak: object, yol: object, uzerine_yaz: object = False) -> dict:
    b = getir(kaynak, yol)
    if not uzerine_yaz and any(x.kimlik == b.kimlik for x in beceriler.listele()):
        raise beceriler.BeceriHatasi(f"'{b.kimlik}' zaten kurulu; uzerine yazmak icin onay gerekir")
    if not b.aciklama.strip():
        raise beceriler.BeceriHatasi("Becerinin aciklamasi yok (model bu beceriyi goremez); indirilmedi")
    return beceriler.olustur(b.kimlik, b.ad, b.aciklama, b.govde, b.otomatik).ozet()
