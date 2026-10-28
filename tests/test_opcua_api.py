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
