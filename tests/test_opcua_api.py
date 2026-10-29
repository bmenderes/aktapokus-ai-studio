"""OPC UA HTTP uclari: dogrulama, belirec, uzak politika ve (asyncua varsa) test sunucusuyla uctan uca."""

import pytest

from aktapokus_ai_studio import opcua, uzak
from aktapokus_ai_studio.arayuz import ArayuzSunucusu, Uygulama
from test_arayuz import Istemci
from test_opcua import _sunucuda


@pytest.fixture
def api(proje):
    app = Uygulama()
    sv = ArayuzSunucusu(app)
    sv.baslat()
    app.klasor_sec(str(proje))
    yield Istemci(sv)
    sv.kapat()


def test_belirec_ister(api):
    for yontem, yol in [("GET", "/api/opcua"), ("POST", "/api/opcua/agac"), ("POST", "/api/opcua/oku"), ("POST", "/api/opcua/abone")]:
        assert api(yontem, yol, {} if yontem == "POST" else None, token=None)[0] == 401, yol


def test_durum_kurulu_bilgisini_verir(api):
    st, d = api("GET", "/api/opcua")
    assert st == 200 and d["kurulu"] == opcua.kurulu() and d["test_adres"].startswith("opc.tcp://")


def test_gecersiz_girdiler_reddedilir(api):
    for yol, govde in [("agac", {}), ("agac", {"adres": "http://x"}), ("oku", {"adres": "opc.tcp://127.0.0.1:1"}),
                       ("abone", {"adres": "opc.tcp://127.0.0.1:1", "kimlikler": []}), ("abone", {"adres": "opc.tcp://127.0.0.1:1", "kimlikler": [1]})]:
        assert api("POST", "/api/opcua/" + yol, govde)[0] == 400, (yol, govde)


def test_uzak_yonetim_kapaliyken_yasak():
    a = uzak.Ayar()
    for yol in ("/api/opcua/agac", "/api/opcua/oku", "/api/opcua/abone"):
        assert uzak.politika("POST", yol, a), yol


def test_uctan_uca_test_sunucusuyla(api):
    pytest.importorskip("asyncua")

    def dene(s):
        st, d = api("POST", "/api/opcua/agac", {"adres": s.adres})
        assert st == 200
        test = next(n for n in d["agac"] if n["ad"] == "Test")
        sayac = next(c["kimlik"] for c in test["cocuklar"] if c["ad"] == "Sayac")
        st, d = api("POST", "/api/opcua/oku", {"adres": s.adres, "kimlik": sayac})
        assert st == 200 and isinstance(d["deger"], int)
        st, d = api("POST", "/api/opcua/abone", {"adres": s.adres, "kimlikler": [sayac], "sure": 1})
        assert st == 200 and len(d["olaylar"]) >= 2

    _sunucuda(dene)
    st, d = api("POST", "/api/opcua/oku", {"adres": "opc.tcp://127.0.0.1:1/x", "kimlik": "ns=2;i=1"})
    assert st == 502 and "hata" in d


def test_toplama_dogrulama_ve_durum(api):
    st, d = api("GET", "/api/opcua/toplama")
    assert st == 200 and d["calisiyor"] is False and d["kayit"] == 0
    for govde in ({}, {"adres": "http://x", "kimlikler": ["a"]}, {"adres": "opc.tcp://127.0.0.1:1", "kimlikler": []}):
        assert api("POST", "/api/opcua/topla", govde)[0] == 400, govde
    assert api("GET", "/api/opcua/veri")[1] == {"olcumler": []}
    assert api("POST", "/api/opcua/durdur", {})[0] == 200


def test_toplama_uctan_uca(api):
    pytest.importorskip("asyncua")
    import time

    def dene(s):
        kimlik = s.dugumler["Sayac"].nodeid.to_string()
        g = {"adres": s.adres, "kimlikler": [kimlik], "adlar": {kimlik: "Sayac"}}
        st, d = api("POST", "/api/opcua/topla", g)
        assert st == 200 and d["calisiyor"]
        assert api("POST", "/api/opcua/topla", g)[0] == 409
        for _ in range(100):
            if api("GET", "/api/opcua/toplama")[1]["yazilan"] >= 3:
                break
            time.sleep(0.1)
        st, d = api("POST", "/api/opcua/durdur", {})
        assert d["calisiyor"] is False and d["kayit"] >= 3
        st, d = api("GET", "/api/opcua/veri?n=2&kimlik=" + kimlik.replace(";", "%3B").replace("=", "%3D"))
        assert st == 200 and len(d["olcumler"]) == 2 and d["olcumler"][0]["ad"] == "Sayac"

    _sunucuda(dene)


def test_toplama_acilista_devam_eder_durdurulunca_etmez(api):
    pytest.importorskip("asyncua")
    import time

    from aktapokus_ai_studio import opcua_ayar

    def dene(s):
        kimlik = s.dugumler["Sayac"].nodeid.to_string()
        assert api("POST", "/api/opcua/topla", {"adres": s.adres, "kimlikler": [kimlik], "saklama_gun": 7})[0] == 200
        assert opcua_ayar.oku()["otomatik"] is True and opcua_ayar.oku()["saklama_gun"] == 7
        # uygulama yeniden aciliyor gibi: yeni Uygulama ayni ayari okuyup toplamayi surdurur
        yeni = Uygulama()
        yeni.opcua_devam()
        try:
            for _ in range(100):
                if yeni.opcua_toplama_durumu()["yazilan"] >= 2:
                    break
                time.sleep(0.1)
            assert yeni.opcua_toplama_durumu()["yazilan"] >= 2
        finally:
            yeni.opcua_durdur(kalici=False)
        assert opcua_ayar.oku()["otomatik"] is True  # kapanis ayari bozmaz
        api("POST", "/api/opcua/durdur", {})
        assert opcua_ayar.oku()["otomatik"] is False  # kullanici durdurdu
        sifir = Uygulama()
        sifir.opcua_devam()
        assert sifir._opcua_toplayici is None

    _sunucuda(dene)


def test_saklama_gunu_dogrulanir(api):
    for kotu in (-1, 4000, "30", True):
        assert api("POST", "/api/opcua/topla", {"adres": "opc.tcp://127.0.0.1:1", "kimlikler": ["a"], "saklama_gun": kotu})[0] == 400, kotu
