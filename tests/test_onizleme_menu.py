"""Onizleme tarayici menusu: yalniz yerel adresler, ekran goruntusu (sahte tarayici), varsayilan tarayicida ac, veri temizleme, uzak politika."""

import base64
import http.client
import re

import pytest

from aktapokus_ai_studio import ekran
from test_konusma import api  # noqa: F401  (pytest fixture)
from test_uzak import ac, sunucu as uzak_sunucu, uzak_istek, ortam  # noqa: F401

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


class SahtePopen:
    komutlar: list = []

    def __init__(self, komut, **kw):
        SahtePopen.komutlar.append(komut)
        hedef = next(a for a in komut if a.startswith("--screenshot="))[len("--screenshot="):]
        open(hedef, "wb").write(PNG)

    def poll(self):
        return 0

    def kill(self):
        pass


@pytest.mark.parametrize("url,gecerli", [
    ("http://127.0.0.1:5000/", True), ("http://localhost:3000/a/b.html", True), ("https://localhost/", True),
    ("http://evil.com/", False), ("http://127.0.0.1.evil.com/", False), ("file:///C:/x", False), ("http://localhost:80@evil.com/", False),
    ("http://127.0.0.1:5000/ x", False), (None, False), ("javascript:alert(1)", False),
])
def test_yerel_adres_denetimi(url, gecerli):
    assert ekran.yerel_mi(url) is gecerli


def test_goruntu_al_tarayiciyi_boyutla_calistirir_ve_png_dondurur(monkeypatch):
    SahtePopen.komutlar = []
    monkeypatch.setattr(ekran.subprocess, "Popen", SahtePopen)
    veri = ekran.goruntu_al("http://127.0.0.1:5000/", 375, 812, "tarayici.exe", zaman_asimi_sn=5)
    assert veri == PNG
    k = SahtePopen.komutlar[0]
    assert "--window-size=375,812" in k and k[-1] == "http://127.0.0.1:5000/" and "--headless=new" in k
    with pytest.raises(ekran.EkranHatasi):
        ekran.goruntu_al("http://evil.com/", 100, 100, "t.exe")
    with pytest.raises(ekran.EkranHatasi):
        ekran.goruntu_al("http://127.0.0.1/", 100, 100, None)


def test_goruntu_al_zaman_asiminda_hata_verir(monkeypatch):
    class Bos(SahtePopen):
        def __init__(self, komut, **kw):
            pass

    monkeypatch.setattr(ekran.subprocess, "Popen", Bos)
    with pytest.raises(ekran.EkranHatasi):
        ekran.goruntu_al("http://127.0.0.1:5000/", 300, 300, "t.exe", zaman_asimi_sn=1)


def test_uc_noktalar(api, monkeypatch):
    app, istek, proje = api
    SahtePopen.komutlar = []
    monkeypatch.setattr(ekran.subprocess, "Popen", SahtePopen)
    monkeypatch.setattr("aktapokus_ai_studio.uygulama.tarayici_bul", lambda: "t.exe")
    st, d = istek("POST", "/api/onizleme-ekran", {"url": "http://127.0.0.1:5000/", "genislik": 768, "yukseklik": 1024})
    assert st == 200 and base64.b64decode(d["png"]) == PNG
    assert istek("POST", "/api/onizleme-ekran", {"url": "http://evil.com/"})[0] == 400
    assert istek("POST", "/api/onizleme-ekran", {"url": "http://127.0.0.1:5000/", "genislik": "abc"})[0] == 400
    acilan = []
    import webbrowser
    monkeypatch.setattr(webbrowser, "open", lambda u: acilan.append(u) or True)
    assert istek("POST", "/api/onizleme-ac", {"url": "http://localhost:3000/"})[0] == 200 and acilan == ["http://localhost:3000/"]
    assert istek("POST", "/api/onizleme-ac", {"url": "https://evil.com/"})[0] == 400 and len(acilan) == 1


def test_onizleme_temizle_site_verisini_siler(api):
    app, istek, proje = api
    sv = app and None
    st, d = istek("GET", "/api/onizleme")
    port = int(re.search(r":(\d+)/", d["url"]).group(1))
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    c.request("GET", "/__temizle")
    r = c.getresponse()
    assert r.status == 200 and "storage" in r.getheader("Clear-Site-Data") and r.read() == b"temizlendi"


def test_uzaktan_onizleme_menusu_kapali(uzak_sunucu):
    app, sv, yerel, proje = uzak_sunucu
    port, _ = ac(yerel)
    for yol in ("/api/onizleme-ac", "/api/onizleme-ekran"):
        st, d = uzak_istek(port, "POST", yol, {"url": "http://127.0.0.1:1/"})
        assert st == 403 and "uzaktan kapali" in d["hata"], yol


def test_arayuz_onizleme_menusu_baglidir():
    from pathlib import Path

    html = (Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "web" / "index.html").read_text(encoding="utf-8")
    for parca in ("onizMenusu", 'id="onizMenu"', "/api/onizleme-ekran", "/api/onizleme-ac", "/__temizle", "onizOtoAc", "onizOtoDogrula", 'onizTercih("otoac",true)', 'onizTercih("otodogrula",false)'):
        assert parca in html, parca


def _onizleme_get(istek, yol):
    st, d = istek("GET", "/api/onizleme")
    port = int(re.search(r":(\d+)/", d["url"]).group(1))
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    c.request("GET", yol)
    r = c.getresponse()
    return r.status, r.getheader("Location"), r.read().decode("utf-8", "replace")


def test_onizleme_kokte_index_yoksa_alt_klasordeki_sayfayi_acar(api):
    app, istek, proje = api
    for f in list(proje.glob("index.html")):
        f.unlink()
    assert _onizleme_get(istek, "/")[0] == 404  # hic sayfa yok
    (proje / "site" / "haberler").mkdir(parents=True)
    (proje / "site" / "haberler" / "index.html").write_text("<h1>H</h1>", encoding="utf-8")
    (proje / ".gizli").mkdir()
    (proje / ".gizli" / "index.html").write_text("gizli", encoding="utf-8")
    st, konum, _ = _onizleme_get(istek, "/")  # tek aday: oraya yonlendirir (goreli baglantilar calissin diye sonda /)
    assert st == 302 and konum == "/site/haberler/"
    st, _, govde = _onizleme_get(istek, "/site/haberler/")
    assert st == 200 and govde == "<h1>H</h1>"


def test_onizleme_birden_cok_sayfa_varsa_secenekleri_listeler(api):
    app, istek, proje = api
    for f in list(proje.glob("index.html")):
        f.unlink()
    for ad in ("a.github.io/haberler", "b.github.io/haberler"):
        (proje / ad).mkdir(parents=True)
        (proje / ad / "index.html").write_text("x", encoding="utf-8")
    (proje / "a&b").mkdir()
    (proje / "a&b" / "index.html").write_text("x", encoding="utf-8")
    st, konum, govde = _onizleme_get(istek, "/")
    assert st == 200 and konum is None and 'href="/a.github.io/haberler/"' in govde and 'href="/b.github.io/haberler/"' in govde
    assert "a&b<" not in govde and "a&amp;b" in govde  # klasor adi kacislanir
    (proje / "index.html").write_text("<h1>kok</h1>", encoding="utf-8")
    assert _onizleme_get(istek, "/")[2] == "<h1>kok</h1>"  # kokte index.html varsa eskisi gibi
