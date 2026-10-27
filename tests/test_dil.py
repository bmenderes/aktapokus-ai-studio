"""Arayuz dili (Turkce + Ingilizce): dil dosyalari, sunum, sozluk tutarliligi, motorun baglantisi. Yeni dil = web/diller/<kod>.json + dizin.json satiri."""

import json
import re
from pathlib import Path

import pytest

from test_pwa import _ham_get
from test_uzak import ac, ortam, sunucu  # noqa: F401  (pytest fixture'lari)

WEB = Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "web"
DILLER = WEB / "diller"
HTML = (WEB / "index.html").read_text(encoding="utf-8")


def _dizin():
    return json.loads((DILLER / "dizin.json").read_text(encoding="utf-8"))


def test_dizin_turkce_kaynak_ve_her_dilin_dosyasi_var():
    d = _dizin()
    assert d[0]["kod"] == "tr" and "en" in {x["kod"] for x in d}
    for x in d:
        assert x["ad"] and x["yerel"]
        if x["kod"] != "tr":  # Turkce kaynak dil: dosyasi yok
            assert (DILLER / f"{x['kod']}.json").is_file(), x["kod"]


@pytest.mark.parametrize("kod", [x["kod"] for x in _dizin() if x["kod"] != "tr"])
def test_dil_dosyasi_gecerli_ve_sozluk_tutarli(kod):
    p = json.loads((DILLER / f"{kod}.json").read_text(encoding="utf-8"))
    assert p["kod"] == kod and p["ad"] and p["yerel"] and len(p["tam"]) > 500
    for tr, ceviri in p["tam"].items():
        assert isinstance(ceviri, str) and ceviri.strip(), tr
        # parcalar yan yana birlestirilir: bastaki/sondaki bosluk ve satir sonlari korunmali
        assert (tr[:1].isspace()) == (ceviri[:1].isspace()), repr(tr)
        assert (tr[-1:].isspace()) == (ceviri[-1:].isspace()), repr(tr)
        assert tr.count("\n") == ceviri.count("\n"), repr(tr)
        # degisken yer tutuculari ({tarih} gibi) ve komutlar (`claude auth login`) cevirilmez
        for yer in re.findall(r"\{[a-z]+\}", tr) + re.findall(r"`[^`]+`", tr):
            assert yer in ceviri, (tr, yer)
    for desen, degisim in p.get("desen", []):
        re.compile(desen)
    # sozlugun gercek yuzey metinlerini kapsamasi
    for tr in ("Kaydet", "Gönder", "Görevler", "Ayarlar", "Onayla", "Reddet", "Korunsun", "Geri al", "Hep onayla", "Planı otomatik onayla"):
        assert tr in p["tam"] and p["tam"][tr], tr
    assert not any(c in p["tam"]["Kaydet"] for c in "çğıöşü")  # ceviri Turkce kalmamis


def test_dil_dosyalari_belirtecsiz_servis_edilir_gecersiz_adlar_reddedilir(sunucu):
    app, sv, yerel, proje = sunucu
    port, _ = ac(yerel)
    for adres, h, p in (("127.0.0.1", f"127.0.0.1:{sv.port}", sv.port), ("127.0.0.2", f"127.0.0.2:{port}", port)):
        st, ct, govde = _ham_get(p, "/diller/dizin.json", h, adres)
        assert st == 200 and ct.startswith("application/json") and json.loads(govde)[0]["kod"] == "tr"
        st, ct, govde = _ham_get(p, "/diller/en.json", h, adres)
        assert st == 200 and json.loads(govde)["kod"] == "en"
        for kotu in ("/diller/xx.json", "/diller/..%2findex.json", "/diller/../index.html", "/diller/en.json/../../index.html", "/diller/EN.json", "/diller/en.js"):
            assert _ham_get(p, kotu, h, adres)[0] in (403, 404), kotu


def test_arayuz_dil_motoru_ve_secici_baglidir():
    for parca in ("function dilCevir", "function dilYukle", "function dilSecici", "function dilTara", "dilEksik", "new MutationObserver", "window.confirm=", "window.alert=", "window.prompt=",
                  "await dilSecici(h)", "--bos-metin", "[data-dil-yok]", "DIL.yerel"):
        assert parca in HTML, parca
    assert 'toLocaleString("tr-TR")' not in HTML and "toLocaleString(DIL.yerel)" in HTML  # sayi/tarih bicimi secilen dile uyar
    assert "https://" not in HTML and "cdn" not in HTML
    # model/kullanici metni, kod ve terminal cevrilmez
    for atla in (".md", ".kullanici", "pre", "code", "#trmGovde"):
        assert atla in re.search(r'DIL_ATLA="([^"]+)"', HTML).group(1)
