"""Gorev ekleri: resim/dosya yukleme (/api/ek), yalniz yuklenmis eklerin goreve eklenmesi, sinirlar, uzaktan (telefon) yukleme."""

import http.client
import json
from pathlib import Path

import pytest

from aktapokus_ai_studio import uzak
from aktapokus_ai_studio.arayuz import EK_AZAMI, EK_SAYI, UygulamaHatasi
from aktapokus_ai_studio.config import ayar_yukle
from test_uzak import ac, ortam, sunucu  # noqa: F401  (pytest fixture'lari)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def yukle(port, ad, veri, token, adres="127.0.0.1", host=None):
    c = http.client.HTTPConnection(adres, port, timeout=10)
    c.request("POST", "/api/ek?ad=" + (ad if ad is None else __import__("urllib.parse").parse.quote(ad)), body=veri,
              headers={"X-Aktapokus-Token": token, "Content-Type": "application/octet-stream", "Host": host or f"{adres}:{port}"})
    r = c.getresponse()
    ham = r.read()
    c.close()
    return r.status, json.loads(ham)


def test_yukleme_projenin_ekler_klasorune_yazar(sunucu):
    app, sv, yerel, proje = sunucu
    st, d = yukle(sv.port, "Ekran Görüntüsü.png", PNG, app.token)
    assert st == 200 and d["boyut"] == len(PNG) and d["ad"] == "Ekran Görüntüsü.png"
    assert d["yol"].startswith(".aktapokus/ekler/") and d["yol"].endswith("/Ekran Görüntüsü.png")
    assert (proje / d["yol"]).read_bytes() == PNG
    # git'e/anlik goruntuye girmez: .aktapokus altinda
    assert (proje / ".aktapokus" / "ekler").is_dir()


def test_ad_temizlenir_yol_gezintisi_olmaz(sunucu):
    app, sv, yerel, proje = sunucu
    for kotu in ("..\\..\\evil.png", "../../evil.png", "/etc/x.png", "C:\\Windows\\evil.png", "a<b>:c?.png"):
        st, d = yukle(sv.port, kotu, PNG, app.token)
        assert st == 200, kotu
        assert (proje / d["yol"]).resolve().is_relative_to((proje / ".aktapokus" / "ekler").resolve()), kotu
        assert "/" not in d["ad"] and "\\" not in d["ad"] and ".." not in d["ad"] and d["ad"].endswith(".png")
    assert not (proje.parent / "evil.png").exists() and not (proje / "evil.png").exists()


def test_izinsiz_tur_bos_ve_buyuk_reddedilir(sunucu):
    app, sv, yerel, proje = sunucu
    assert yukle(sv.port, "calistir.exe", b"MZ", app.token)[0] == 415
    assert yukle(sv.port, "betik.bat", b"echo", app.token)[0] == 415
    assert yukle(sv.port, "uzantisiz", b"x", app.token)[0] == 415
    st, d = yukle(sv.port, "bos.png", b"", app.token)
    assert st == 400
    with pytest.raises(UygulamaHatasi) as h:
        app.ek_kaydet("buyuk.png", b"x" * (EK_AZAMI + 1))
    assert h.value.kod == 413
    assert yukle(sv.port, "x.png", PNG, "yanlis-token")[0] == 401


def test_gorev_yalniz_yuklenmis_ekleri_metne_ekler(sunucu):
    app, sv, yerel, proje = sunucu
    e1 = yukle(sv.port, "hata.png", PNG, app.token)[1]["yol"]
    e2 = yukle(sv.port, "log.txt", b"satir", app.token)[1]["yol"]
    plan = app.gorev_olustur("Bu hatayi coz", otomatik_onay_izni=False, ekler=[e1, e2])
    assert plan["gorev"].startswith("Bu hatayi coz") and "Ekli dosyalar" in plan["gorev"] and f"- {e1}" in plan["gorev"] and f"- {e2}" in plan["gorev"]
    app.reddet(plan["kosu"])
    # eksiz gorev degismez
    d = app.gorev_olustur("Duz gorev", otomatik_onay_izni=False)
    assert d["gorev"] == "Duz gorev"
    app.reddet(d["kosu"])


@pytest.mark.parametrize("kotu", [
    ["../a.png"], ["C:/Windows/system.ini"], [".aktapokus/ekler/20260101-000000-abcdef/yok.png"], [".aktapokus/DURUM.md"], ["a.txt"],
    [".aktapokus/ekler/../../a.txt"], [5], "metin",
])
def test_gorev_gecersiz_ek_yolunu_reddeder(sunucu, kotu):
    app, sv, yerel, proje = sunucu
    with pytest.raises(UygulamaHatasi):
        app.gorev_olustur("x", otomatik_onay_izni=False, ekler=kotu)
    assert app._oturum().kosu is None or app._oturum().kosu.durum not in ("plan", "calisiyor")  # reddedilen gorev baslamaz


def test_gorev_en_fazla_ek_sayisi_kadar_ek(sunucu):
    app, sv, yerel, proje = sunucu
    yollar = [yukle(sv.port, f"d{i}.txt", b"x", app.token)[1]["yol"] for i in range(EK_SAYI + 1)]
    with pytest.raises(UygulamaHatasi):
        app.gorev_olustur("x", otomatik_onay_izni=False, ekler=yollar)
    plan = app.gorev_olustur("x", otomatik_onay_izni=False, ekler=yollar[:EK_SAYI])
    assert plan["gorev"].count("\n- ") == EK_SAYI
    app.reddet(plan["kosu"])


def test_api_gorev_ekleri_alir(sunucu):
    app, sv, yerel, proje = sunucu
    if ayar_yukle(proje).otomatik_onay:
        pytest.skip("otomatik onay acik: gercek calistirici baslardi")
    yol = yukle(sv.port, "tasarim.png", PNG, app.token)[1]["yol"]
    st, d = yerel("POST", "/api/gorev", {"gorev": "Ekrana bak", "ekler": [yol]})
    assert st == 200 and f"- {yol}" in d["gorev"]
    app.reddet(d["kosu"])
    st, d = yerel("POST", "/api/gorev", {"gorev": "Ikinci", "ekler": ["../kotu.png"]})
    assert st == 400 and "Gecersiz ek yolu" in d["hata"]


def test_telefon_uzak_baglantidan_yukleme_calisir_yonetim_kapaliyken(sunucu):
    app, sv, yerel, proje = sunucu
    port, _ = ac(yerel)
    anahtar = uzak.oku().anahtar
    st, d = yukle(port, "foto.jpg", PNG, anahtar, adres="127.0.0.2")
    assert st == 200 and (proje / d["yol"]).read_bytes() == PNG
    assert yukle(port, "foto.jpg", PNG, "yanlis", adres="127.0.0.2")[0] == 401


def test_arayuz_ek_ozellikleri_baglidir():
    html = (Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "web" / "index.html").read_text(encoding="utf-8")
    for parca in ('id="ekDugme"', 'id="ekSec"', 'id="ekler"', '"paste"', '"drop"', "/api/ek?ad=", "ekler:ekYollar", "URL.createObjectURL"):
        assert parca in html, parca
    kaynak = (Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "arayuz.py").read_text(encoding="utf-8")
    assert "img-src 'self' data: blob:" in kaynak  # kucuk resim onizlemesi
    assert "https://" not in html


def _oku(port, yol, token, adres="127.0.0.1"):
    import urllib.parse

    c = http.client.HTTPConnection(adres, port, timeout=10)
    c.request("GET", "/api/ek?yol=" + urllib.parse.quote(yol), headers={"X-Aktapokus-Token": token, "Host": f"{adres}:{port}"})
    r = c.getresponse()
    govde = r.read()
    c.close()
    return r.status, r.getheader("Content-Type"), govde


def test_yuklenen_resim_konusmada_gosterilsin_diye_geri_okunur_yalniz_ekler(sunucu):
    app, sv, yerel, proje = sunucu
    yol = yukle(sv.port, "foto.png", PNG, app.token)[1]["yol"]
    st, tur, govde = _oku(sv.port, yol, app.token)
    assert st == 200 and tur == "image/png" and govde == PNG
    assert _oku(sv.port, yol, "yanlis")[0] == 401
    for kotu in ("a.txt", ".aktapokus/DURUM.md", "../a.txt", ".aktapokus/ekler/20260101-000000-abcdef/yok.png", ".aktapokus/ekler/../../a.txt"):
        assert _oku(sv.port, kotu, app.token)[0] in (400, 404), kotu
    gizli = proje / ".aktapokus" / "gizli.txt"
    gizli.write_text("sir", encoding="utf-8")
    assert _oku(sv.port, ".aktapokus/gizli.txt", app.token)[0] == 400  # ekler disindaki .aktapokus dosyalari okunamaz


def test_yeni_konusma_siniri_yazar_claude_oturumunu_sifirlar_ve_gruplarda_gorunur(sunucu):
    from aktapokus_ai_studio.runners import ClaudeCodeCalistirici

    app, sv, yerel, proje = sunucu
    oturum = ClaudeCodeCalistirici._oturum_yolu(proje)
    oturum.parent.mkdir(parents=True, exist_ok=True)
    oturum.write_text('{"oturum": "x", "zaman": 1}', encoding="utf-8")
    g = yerel("GET", "/api/proje-gruplari")[1]["projeler"]
    assert [x["konusma_basi"] for x in g if x["secili"]] == [None]
    st, d = yerel("POST", "/api/yeni-konusma", {})
    assert st == 200 and len(d["zaman"]) == 19 and not oturum.exists()
    g = yerel("GET", "/api/proje-gruplari")[1]["projeler"]
    assert [x["konusma_basi"] for x in g if x["secili"]] == [d["zaman"]]
    (proje / ".aktapokus" / "konusma-basi.json").write_text('{"zaman": "bozuk"}', encoding="utf-8")
    assert [x["konusma_basi"] for x in yerel("GET", "/api/proje-gruplari")[1]["projeler"] if x["secili"]] == [None]  # bozuk kayit yok sayilir


def test_arayuz_resim_gorunumu_ve_surekli_konusma_baglidir():
    html = (Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "web" / "index.html").read_text(encoding="utf-8")
    for parca in ("ek-kart", "kullaniciKutusu", "resimBuyut", "/api/ek?yol=", "konusmaYukle", "konusmaYoksaYukle", "yeniKonusma", 'class:"ayrac"', "/api/yeni-konusma", "S.sseHazir"):
        assert parca in html, parca
    assert '$("#yeniGorev").onclick=yeniKonusma' in html


def test_cad_dosyalari_eklenebilir_calistirilabilirler_yine_reddedilir(sunucu):
    app, sv, yerel, proje = sunucu
    for uz in ("sldprt", "sldasm", "slddrw", "step", "stp", "iges", "igs", "stl", "dxf", "dwg", "SLDASM"):
        st, d = yukle(sv.port, f"parca.{uz}", b"\x00CAD", app.token)
        assert st == 200 and (proje / d["yol"]).read_bytes() == b"\x00CAD", uz
    st, d = yukle(sv.port, "calistir.exe", b"MZ", app.token)
    assert st == 415 and "CAD" in d["hata"] and "sldasm" in d["hata"]  # hata mesaji CAD turlerini de sayar
