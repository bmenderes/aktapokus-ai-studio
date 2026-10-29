import socket
import time

import pytest

from aktapokus_ai_studio import ag_araci, bootp


def test_ag_coz_sinirlar():
    assert ag_araci.ag_coz("192.168.1.0/24").num_addresses == 256
    for kotu in ("abc", "8.8.8.0/24", "10.0.0.0/16", ""):
        with pytest.raises(ag_araci.AgHatasi):
            ag_araci.ag_coz(kotu)


def test_tara_sahte_islevlerle():
    canli = {"192.168.1.10", "192.168.1.20"}
    sonuc = ag_araci.tara(
        "192.168.1.0/24",
        ping=lambda ip: ip in canli,
        portlar=lambda ip: [44818] if ip == "192.168.1.10" else [],
        arp=lambda: {"192.168.1.10": "00:1D:9C:12:34:56", "192.168.1.30": "00:0E:8C:00:00:01", "192.168.2.5": "AA:AA:AA:AA:AA:AA"},
    )
    assert [c["ip"] for c in sonuc] == ["192.168.1.10", "192.168.1.20", "192.168.1.30"]  # .30 yalniz ARP'ta (ping'e yanit vermiyor)
    assert sonuc[0]["uretici"] == "Rockwell" and sonuc[0]["portlar"] == [{"no": 44818, "ad": "EtherNet/IP"}]
    assert sonuc[1]["mac"] is None and sonuc[2]["uretici"] == "Siemens"


def test_adaptor_ip_dogrulama_netsh_calismaz(monkeypatch):
    cagrilar = []
    monkeypatch.setattr(ag_araci, "_netsh", lambda a: cagrilar.append(a))
    monkeypatch.setattr(ag_araci, "adaptorler", lambda: [{"ad": "Ethernet", "ip": "10.0.0.2", "onek": 24, "maske": "255.255.255.0", "dhcp": False}])
    for ad, ip, maske in (("Yok", "10.0.0.5", "255.255.255.0"), ("Ethernet", "999.1.1.1", "255.255.255.0"), ("Ethernet", "10.0.0.5", "255.0.255.0"), ("Ethernet; calc", "1.1.1.1", "255.0.0.0")):
        with pytest.raises(ag_araci.AgHatasi):
            ag_araci.adaptor_ip_ata(ad, ip, maske)
    assert cagrilar == []
    ag_araci.adaptor_ip_ata("Ethernet", "192.168.1.5", "255.255.255.0", "192.168.1.1")
    assert cagrilar == [["interface", "ipv4", "set", "address", "name=Ethernet", "static", "192.168.1.5", "255.255.255.0", "192.168.1.1"]]
    ag_araci.adaptor_dhcp_yap("Ethernet")
    assert cagrilar[-1][-1] == "source=dhcp"


def _istek(mac="00:1D:9C:12:34:56", dhcp_tur=None, xid=b"\x01\x02\x03\x04"):
    p = bytearray(300)
    p[0:4] = bytes([1, 1, 6, 0])
    p[4:8] = xid
    p[28:34] = bytes(int(x, 16) for x in mac.split(":"))
    if dhcp_tur is not None:
        p[236:240] = bootp.MAGIC
        p[240:243] = bytes([53, 1, dhcp_tur])
        p[243] = 255
    return bytes(p)


def test_bootp_paket_cozme_ve_uretme():
    i = bootp.istek_coz(_istek())
    assert i["mac"] == "00:1D:9C:12:34:56" and i["dhcp_tur"] is None
    y = bootp.yanit_uret(i, "192.168.1.50", "255.255.255.0", "192.168.1.1", "192.168.1.2")
    assert y[0] == 2 and y[4:8] == b"\x01\x02\x03\x04" and socket.inet_ntoa(y[16:20]) == "192.168.1.50" and y[236:240] == bootp.MAGIC
    d = bootp.istek_coz(_istek(dhcp_tur=bootp.DHCP_DISCOVER))
    assert bootp.yanit_uret(d, "192.168.1.50", "255.255.255.0", None, "192.168.1.2")[240:243] == bytes([53, 1, bootp.DHCP_OFFER])
    assert bootp.yanit_uret(bootp.istek_coz(_istek(dhcp_tur=7)), "1.1.1.1", "255.0.0.0", None, "1.1.1.2") is None
    assert bootp.istek_coz(b"kisa") is None and bootp.istek_coz(bytes([2]) + bytes(299)) is None


def test_bootp_mac_ve_atama_dogrulama():
    assert bootp.mac_coz("00-1d-9c-12-34-56") == "00:1D:9C:12:34:56" and bootp.mac_coz("001D9C123456") == "00:1D:9C:12:34:56"
    s = bootp.Sunucu()
    for kotu in ("xx", "00:1D:9C"):
        with pytest.raises(bootp.BootpHatasi):
            s.ata(kotu, "10.0.0.5")
    with pytest.raises(bootp.BootpHatasi):
        s.ata("00:1D:9C:12:34:56", "10.0.0.999")


def test_bootp_yalniz_atanan_mac_yanit_alir():
    s = bootp.Sunucu(port=0, yanit_hedef=None)
    s.baslat()
    try:
        s.ata("00:1D:9C:12:34:56", "192.168.1.50", "255.255.255.0")
        port = s.gercek_port
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as c:
            c.settimeout(3)
            c.sendto(_istek("00:1D:9C:12:34:56"), ("127.0.0.1", port))
            yanit, _ = c.recvfrom(1500)
            assert socket.inet_ntoa(yanit[16:20]) == "192.168.1.50"
            c.sendto(_istek("AA:BB:CC:00:00:01"), ("127.0.0.1", port))  # atanmamis MAC: yanit yok
            c.settimeout(1)
            with pytest.raises(socket.timeout):
                c.recvfrom(1500)
        durum = s.durum()
        assert {i["mac"] for i in durum["istekler"]} == {"00:1D:9C:12:34:56", "AA:BB:CC:00:00:01"}
        assert next(i for i in durum["istekler"] if i["mac"].startswith("00:1D"))["yanit"] == 1
    finally:
        s.durdur()
    assert not s.calisiyor


def test_bootp_port_kullanimda_anlasilir_hata():
    a = bootp.Sunucu(port=0)
    a.baslat()
    try:
        b = bootp.Sunucu(port=a.gercek_port)
        # Windows'ta SO_REUSEADDR olmadan ayni port acilamaz
        with pytest.raises(bootp.BootpHatasi):
            b.baslat()
    finally:
        a.durdur()
