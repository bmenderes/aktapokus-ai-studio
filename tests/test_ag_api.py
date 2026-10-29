"""Ag araci HTTP uclari ve ayri /ag sayfasi. Gercek ag/adaptor ASLA degistirilmez: netsh ve tarama sahtelenir, BOOTP bos porta baglanir."""

import http.client

import pytest

from aktapokus_ai_studio import ag_araci, bootp, uzak
from aktapokus_ai_studio.arayuz import ArayuzSunucusu, Uygulama
from test_arayuz import Istemci

UCLAR = [("GET", "/api/ag/profiller"), ("POST", "/api/ag/profil"), ("POST", "/api/ag/profil-sil"), ("POST", "/api/ag/profil-uygula"), ("GET", "/api/ag/adaptorler"), ("GET", "/api/ag/bootp"), ("POST", "/api/ag/tara"), ("POST", "/api/ag/adaptor-ip"), ("POST", "/api/ag/adaptor-dhcp"),
         ("POST", "/api/ag/bootp/baslat"), ("POST", "/api/ag/bootp/durdur"), ("POST", "/api/ag/bootp/ata"), ("POST", "/api/ag/bootp/kaldir")]


@pytest.fixture
def api(proje, monkeypatch):
    netsh = []
    monkeypatch.setattr(ag_araci, "_netsh", lambda a: netsh.append(a))
    monkeypatch.setattr(ag_araci, "adaptorler", lambda: [{"ad": "Ethernet", "ip": "10.0.0.2", "onek": 24, "maske": "255.255.255.0", "dhcp": False}])
    monkeypatch.setattr(ag_araci, "_ping", lambda ip: ip == "10.0.0.7")
    monkeypatch.setattr(ag_araci, "_acik_portlar", lambda ip: [502])
    monkeypatch.setattr(ag_araci, "_arp", lambda: {"10.0.0.7": "00:80:F4:00:00:01"})
    app = Uygulama()
    app._bootp = bootp.Sunucu(port=0, yanit_hedef=None)  # gercek 67. porta baglanma
    sv = ArayuzSunucusu(app)
    sv.baslat()
    app.klasor_sec(str(proje))
    yield Istemci(sv), netsh, sv
    sv.kapat()


def test_belirec_ister(api):
    istek, _, _ = api
    for yontem, yol in UCLAR:
        assert istek(yontem, yol, {} if yontem == "POST" else None, token=None)[0] == 401, yol


def test_ag_sayfasi_ayri_ve_belirtecsiz_statik(api):
    _, _, sv = api
    c = http.client.HTTPConnection("127.0.0.1", sv.port, timeout=10)
    c.request("GET", "/ag")
    r = c.getresponse()
    govde = r.read().decode("utf-8")
    assert r.status == 200 and "Aktapokus Ağ" in govde and "frame-ancestors 'none'" in r.getheader("Content-Security-Policy")
    assert "/api/ag/tara" in govde and sv.app.token not in govde  # belirtec sayfaya gomulu degil


def test_tara_ve_hatalar(api):
    istek, _, _ = api
    st, d = istek("POST", "/api/ag/tara", {"ag": "10.0.0.0/24"})
    assert st == 200 and d["cihazlar"] == [{"ip": "10.0.0.7", "mac": "00:80:F4:00:00:01", "uretici": "Schneider", "portlar": [{"no": 502, "ad": "Modbus"}]}]
    assert istek("POST", "/api/ag/tara", {"ag": "8.8.8.0/24"})[0] == 400
    assert istek("POST", "/api/ag/tara", {})[0] == 400


def test_adaptor_ip_dogrulanir_ve_netsh_sahte(api):
    istek, netsh, _ = api
    assert istek("POST", "/api/ag/adaptor-ip", {"ad": "Yok", "ip": "10.0.0.5", "maske": "255.255.255.0"})[0] == 400
    assert istek("POST", "/api/ag/adaptor-ip", {"ad": "Ethernet", "ip": "10.0.0.256", "maske": "255.255.255.0"})[0] == 400
    assert netsh == []
    st, d = istek("POST", "/api/ag/adaptor-ip", {"ad": "Ethernet", "ip": "192.168.1.5", "maske": "255.255.255.0"})
    assert st == 200 and d["adaptorler"][0]["ad"] == "Ethernet" and len(netsh) == 1
    assert istek("POST", "/api/ag/adaptor-dhcp", {"ad": "Ethernet"})[0] == 200 and netsh[-1][-1] == "source=dhcp"


def test_bootp_baslat_ata_durdur(api):
    istek, _, _ = api
    assert istek("GET", "/api/ag/bootp")[1]["calisiyor"] is False
    assert istek("POST", "/api/ag/bootp/baslat", {})[1]["calisiyor"] is True
    st, d = istek("POST", "/api/ag/bootp/ata", {"mac": "00-1d-9c-12-34-56", "ip": "192.168.1.50"})
    assert st == 200 and d["atamalar"] == [{"mac": "00:1D:9C:12:34:56", "ip": "192.168.1.50", "maske": "255.255.255.0", "gecit": None}]
    assert istek("POST", "/api/ag/bootp/ata", {"mac": "xx", "ip": "192.168.1.50"})[0] == 400
    assert istek("POST", "/api/ag/bootp/kaldir", {"mac": "00:1D:9C:12:34:56"})[1]["atamalar"] == []
    assert istek("POST", "/api/ag/bootp/durdur", {})[1]["calisiyor"] is False


def test_uzak_yonetim_kapaliyken_yazan_uclar_yasak():
    a = uzak.Ayar()
    for yontem, yol in UCLAR:
        if yontem == "POST":
            assert uzak.politika("POST", yol, a), yol


def test_profil_kaydet_uygula_sil(api):
    istek, netsh, _ = api
    assert istek("GET", "/api/ag/profiller")[1] == {"profiller": []}
    assert istek("POST", "/api/ag/profil", {"ad": "PLC", "adaptor": "Ethernet", "ip": "192.168.0.10", "maske": "255.255.255.0"})[0] == 200
    assert istek("POST", "/api/ag/profil", {"ad": "Ofis", "adaptor": "Ethernet", "dhcp": True})[0] == 200
    assert istek("POST", "/api/ag/profil", {"ad": "Kotu", "adaptor": "Ethernet", "ip": "1.2.3", "maske": "255.255.255.0"})[0] == 400
    assert [p["ad"] for p in istek("GET", "/api/ag/profiller")[1]["profiller"]] == ["PLC", "Ofis"]
    assert istek("POST", "/api/ag/profil-uygula", {"ad": "PLC"})[0] == 200 and netsh[-1][-2:] == ["192.168.0.10", "255.255.255.0"]
    assert istek("POST", "/api/ag/profil-uygula", {"ad": "Ofis"})[0] == 200 and netsh[-1][-1] == "source=dhcp"
    assert istek("POST", "/api/ag/profil-uygula", {"ad": "Yok"})[0] == 400
    assert [p["ad"] for p in istek("POST", "/api/ag/profil-sil", {"ad": "PLC"})[1]["profiller"]] == ["Ofis"]
