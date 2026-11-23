"""Uzak erisim: ayar, Tailscale algilama, yalniz Tailscale/loopback'e baglanma, Host/Origin/anahtar, yetki daraltma, kapatinca akislarin kesilmesi.
Gercek soketler kullanilir: Tailscale yerine sahte CLI 127.0.0.2 (loopback) adresini bildirir."""

import http.client
import json
import re
import socket
import threading
import time
from pathlib import Path

import pytest

from aktapokus_ai_studio import uzak
from aktapokus_ai_studio.arayuz import ArayuzSunucusu, Uygulama
from test_arayuz import Istemci

SAHTE_TS = str(Path(__file__).with_name("sahte_tailscale.py"))
DNS = "bilgisayarim.tailabc12.ts.net"


def bos_port():
    s = socket.socket()
    s.bind(("127.0.0.2", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.fixture
def ortam(monkeypatch, tmp_path):
    monkeypatch.setenv(uzak.AYAR_ORTAMI, str(tmp_path / "uzak-erisim.json"))
    monkeypatch.setenv(uzak.TAILSCALE_ORTAMI, SAHTE_TS)
    for k in ("SAHTE_TS_MOD", "SAHTE_TS_IP"):
        monkeypatch.delenv(k, raising=False)
    return monkeypatch


@pytest.fixture
def sunucu(ortam, proje):
    app = Uygulama()
    sv = ArayuzSunucusu(app)
    sv.baslat()
    app.klasor_sec(str(proje))
    yerel = Istemci(sv)
    yield app, sv, yerel, proje
    sv.kapat()


_ANAHTAR = {"v": None}  # son ac() cagrisinda eklenen "telefon" cihazinin anahtari (yalniz ekleme yanitinda bir kez doner)


def anahtar():
    return _ANAHTAR["v"]


def cihaz_ekle(yerel, ad="telefon", gun=90):
    st, d = yerel("POST", "/api/uzak/cihaz-ekle", {"ad": ad, "gun": gun})
    assert st == 200, d
    return d["yeni"]["baglantilar"][0].split("#t=")[1], d


def ac(yerel, **ek):
    port = bos_port()
    st, d = yerel("POST", "/api/uzak", {"acik": True, "port": port, **ek})
    assert st == 200, d
    _ANAHTAR["v"], _ = cihaz_ekle(yerel)
    return port, d


def uzak_istek(port, yontem, yol, veri=None, token="__anahtar__", host="__dogru__", origin=None, adres="127.0.0.2"):
    c = http.client.HTTPConnection(adres, port, timeout=10)
    b = {"Content-Type": "application/json", "Host": f"{DNS if host == '__dogru__' else host}:{port}" if host in ("__dogru__",) else host}
    if host == "__dogru__":
        b["Host"] = f"{adres}:{port}"
    t = anahtar() if token == "__anahtar__" else token
    if t is not None:
        b["X-Aktapokus-Token"] = t
    if origin:
        b["Origin"] = origin
    c.request(yontem, yol, body=json.dumps(veri) if veri is not None else None, headers=b)
    r = c.getresponse()
    ham = r.read()
    c.close()
    try:
        return r.status, json.loads(ham)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return r.status, ham


# ---------- adres / ayar ----------
@pytest.mark.parametrize("adres,beklenen", [
    ("100.64.0.1", True), ("100.101.102.103", True), ("100.127.255.254", True), ("127.0.0.2", True), ("127.0.0.1", True),
    ("0.0.0.0", False), ("192.168.1.5", False), ("10.0.0.5", False), ("172.16.0.1", False), ("8.8.8.8", False), ("100.128.0.1", False), ("100.63.255.255", False),
    ("::1", False), ("fd7a:115c:a1e0::1", False), ("", False), ("localhost", False), (None, False), ("100.64.0.1/10", False),
])
def test_adres_gecerli(adres, beklenen):
    assert uzak.adres_gecerli(adres) is beklenen


def test_ayar_varsayilan_kapali_ve_dogrulanir(ortam):
    a = uzak.oku()
    assert (a.acik, a.terminal, a.yonetim, a.port, a.cihazlar) == (False, False, False, uzak.VARSAYILAN_PORT, [])  # cihazsiz: hicbir uzak anahtar gecmez
    assert "anahtar" not in a.sozluk() and uzak.guncelle({"acik": True, "terminal": True}).terminal is True
    for kotu in ({"acik": "evet"}, {"terminal": 1}, {"yonetim": None}, {"port": 80}, {"port": 70000}, {"port": "47650"}, {"port": True}, {"port": 1023}):
        with pytest.raises(uzak.UzakHatasi):
            uzak.guncelle(kotu)
    assert uzak.oku().terminal is True  # reddedilen degisiklik dosyaya yazilmadi


def test_cihaz_anahtari_kalici_yalniz_ozeti_saklanir(ortam):
    uzak.guncelle({"acik": True})
    _, c, k = uzak.cihaz_ekle("telefon")
    assert len(k) >= 32 and c.ozet == uzak.ozet(k) and uzak.oku().cihazlar[0].ozet == c.ozet
    ham = uzak.dosya_yolu().read_text(encoding="utf-8")
    assert k not in ham and '"anahtar"' not in ham  # diskte anahtar YOK; yalniz (korumali) ozet
    if uzak.gizli.koru("x") != "x":
        assert c.ozet not in ham  # Windows: ozet de DPAPI ile korunur
    assert uzak.cihaz_bul(uzak.oku(), k)[0].kimlik == c.kimlik
    guncel = uzak.guncelle({"terminal": True})  # ayar degisikligi cihazlari silmez
    assert [x.kimlik for x in guncel.cihazlar] == [c.kimlik]


def test_bozuk_ya_da_eksik_dosya_kapali_varsayilan(ortam):
    uzak.dosya_yolu().write_text("{bozuk", encoding="utf-8")
    assert uzak.oku().acik is False
    uzak.dosya_yolu().write_text(json.dumps({"acik": "true", "port": 5, "terminal": "evet", "anahtar": "kisa"}), encoding="utf-8")
    a = uzak.oku()
    assert (a.acik, a.terminal, a.port, a.cihazlar) == (False, False, uzak.VARSAYILAN_PORT, [])  # gecersiz degerler guvenli varsayilana; kisa anahtar tasinmaz
    uzak.dosya_yolu().write_text(json.dumps({"cihazlar": [{"kimlik": "zz", "ad": "x", "ozet": "a" * 64, "olusturma": 1}, {"kimlik": "0123abcd", "ad": "", "ozet": "a" * 64, "olusturma": 1},
                                                          {"kimlik": "0123abcd", "ad": "x", "ozet": "kisa", "olusturma": 1}, 5, None]}), encoding="utf-8")
    assert uzak.oku().cihazlar == []  # bozuk cihaz kayitlari gecmez


# ---------- tailscale algilama ----------
def test_tailscale_calisiyor(ortam):
    d = uzak.tailscale_durum()
    assert d == {"kurulu": True, "calisiyor": True, "adres": "127.0.0.2", "dns": DNS, "hata": None}


@pytest.mark.parametrize("mod,parca", [("durdu", "kapali"), ("oturumsuz", "kapali"), ("bozuk", "okunamadi"), ("ip-yok", "adresi okunamadi"), ("hata", "kapali")])
def test_tailscale_sorunlu_durumlar_anlasilir_hata(ortam, mod, parca):
    ortam.setenv("SAHTE_TS_MOD", mod)
    d = uzak.tailscale_durum()
    assert d["kurulu"] is True and d["adres"] is None and parca in d["hata"]


@pytest.mark.parametrize("ip", ["192.168.1.5", "0.0.0.0", "10.1.2.3", "8.8.8.8"])
def test_tailscale_tailscale_agi_disindaki_adresi_reddeder(ortam, ip):
    ortam.setenv("SAHTE_TS_IP", ip)
    d = uzak.tailscale_durum()
    assert d["adres"] is None and d["hata"]


def test_tailscale_kurulu_degil(ortam, tmp_path):
    ortam.setenv(uzak.TAILSCALE_ORTAMI, str(tmp_path / "yok.exe"))
    d = uzak.tailscale_durum()
    assert d["kurulu"] is False and d["adres"] is None and "kurulu degil" in d["hata"]


# ---------- politika tablosu ----------
YASAK_VARSAYILAN = [
    ("GET", "/api/terminal"), ("POST", "/api/terminal/ac"), ("POST", "/api/terminal/abcd/girdi"), ("GET", "/api/terminal/abcd/akis"),
    ("POST", "/api/clilar"), ("POST", "/api/clilar/sil"), ("POST", "/api/clilar/dene"),
    ("POST", "/api/mcp-sunuculari"), ("POST", "/api/mcp-sunuculari/sil"), ("POST", "/api/mcp-sunuculari/dene"), ("POST", "/api/mcp-sunuculari/proje"),
    ("POST", "/api/ag/tara"), ("POST", "/api/ag/profil-uygula"), ("POST", "/api/ag/adaptor-ip"), ("POST", "/api/ag/bootp/baslat"),
    ("POST", "/api/opcua/agac"), ("POST", "/api/opcua/oku"), ("POST", "/api/opcua/abone"), ("POST", "/api/opcua/topla"), ("POST", "/api/opcua/durdur"),
    ("POST", "/api/saglayicilar/baglan"), ("POST", "/api/saglayicilar/kaldir"),
    ("POST", "/api/telegram/baslat"), ("POST", "/api/telegram/kok"), ("POST", "/api/telegram/eslestir"),
    ("POST", "/api/beceriler"), ("POST", "/api/beceriler/sil"),
    ("POST", "/api/github/klonla"), ("POST", "/api/github/yayin-hazirla"), ("GET", "/api/klasorler"),
    ("GET", "/api/uzak"), ("POST", "/api/uzak"), ("POST", "/api/uzak/cihaz-ekle"), ("POST", "/api/uzak/cihaz-iptal"),
]
IZINLI = [("GET", "/api/durum"), ("GET", "/api/ayar"), ("GET", "/api/proje-gruplari"), ("GET", "/api/oturumlar"), ("GET", "/api/dosyalar"), ("GET", "/api/ciktilar"),
          ("GET", "/api/github/proje"), ("GET", "/api/git/gecmis"), ("POST", "/api/gorev"), ("GET", "/api/mcp-sunuculari"), ("GET", "/api/beceriler"), ("GET", "/api/clilar"),
          ("GET", "/api/telegram"), ("GET", "/api/modeller"), ("GET", "/api/saglayicilar"), ("POST", "/api/git/hazirla"), ("POST", "/api/github/commit")]


def test_politika_varsayilan_kapali_yasaklar_ve_izinliler(ortam):
    a = uzak.Ayar()
    for yontem, yol in YASAK_VARSAYILAN:
        assert uzak.politika(yontem, yol, a), (yontem, yol)
    for yontem, yol in IZINLI:
        assert uzak.politika(yontem, yol, a) is None, (yontem, yol)


def test_politika_terminal_ve_yonetim_anahtarlari_ayri_calisir_uzak_ayari_hic_acilmaz():
    a = uzak.Ayar(terminal=True)
    assert uzak.politika("POST", "/api/terminal/ac", a) is None and uzak.politika("POST", "/api/mcp-sunuculari", a)  # terminal acik, yonetim hala kapali
    a = uzak.Ayar(yonetim=True)
    assert uzak.politika("POST", "/api/terminal/ac", a) and uzak.politika("POST", "/api/mcp-sunuculari", a) is None and uzak.politika("GET", "/api/klasorler", a) is None
    a = uzak.Ayar(terminal=True, yonetim=True)
    for yontem, yol in (("GET", "/api/uzak"), ("POST", "/api/uzak"), ("POST", "/api/uzak/cihaz-ekle"), ("POST", "/api/uzak/cihaz-iptal")):
        assert uzak.politika(yontem, yol, a), (yontem, yol)  # ikisi de acik olsa bile uzak ayari uzaktan degistirilemez


# ---------- gercek dinleyici ----------
def test_varsayilan_kapali_dinleyici_yok(sunucu):
    app, sv, yerel, proje = sunucu
    st, d = yerel("GET", "/api/uzak")
    assert st == 200 and d["ayar"]["acik"] is False and d["dinleyici"]["calisiyor"] is False and "anahtar" not in d["ayar"] and d["tailscale"]["adres"] == "127.0.0.2"


def test_acinca_yalniz_tailscale_adresine_baglanir_0000a_degil(sunucu):
    app, sv, yerel, proje = sunucu
    port, d = ac(yerel)
    assert d["dinleyici"]["calisiyor"] and d["dinleyici"]["adres"] == "127.0.0.2" and d["dinleyici"]["port"] == port
    assert sv.uzak_http.server_address == ("127.0.0.2", port)  # 0.0.0.0 DEGIL
    assert d["dinleyici"]["adresler"] == [f"http://{DNS}:{port}/", f"http://127.0.0.2:{port}/"]  # anahtarsiz
    k, e = cihaz_ekle(yerel, "tablet")
    assert e["yeni"]["baglantilar"] == [f"http://{DNS}:{port}/#t={k}", f"http://127.0.0.2:{port}/#t={k}"]


@pytest.mark.parametrize("ip", ["192.168.1.5", "0.0.0.0"])
def test_tailscale_agi_disinda_adresle_dinleyici_kurulmaz(sunucu, ip):
    app, sv, yerel, proje = sunucu
    sunucu_ortam = pytest.MonkeyPatch()
    try:
        sunucu_ortam.setenv("SAHTE_TS_IP", ip)
        st, d = yerel("POST", "/api/uzak", {"acik": True, "port": bos_port()})
    finally:
        sunucu_ortam.undo()
    assert st == 200 and d["dinleyici"]["calisiyor"] is False and d["dinleyici"]["hata"] and sv.uzak_http is None


def test_tailscale_kapaliyken_acilamaz_hata_gosterilir(sunucu):
    app, sv, yerel, proje = sunucu
    sunucu_ortam = pytest.MonkeyPatch()
    try:
        sunucu_ortam.setenv("SAHTE_TS_MOD", "durdu")
        st, d = yerel("POST", "/api/uzak", {"acik": True, "port": bos_port()})
    finally:
        sunucu_ortam.undo()
    assert d["dinleyici"]["calisiyor"] is False and "kapali" in d["dinleyici"]["hata"] and d["ayar"]["acik"] is True


def test_port_doluysa_anlasilir_hata(sunucu):
    app, sv, yerel, proje = sunucu
    port = bos_port()
    tutan = socket.socket()
    tutan.bind(("127.0.0.2", port))
    tutan.listen(1)
    try:
        st, d = yerel("POST", "/api/uzak", {"acik": True, "port": port})
        assert d["dinleyici"]["calisiyor"] is False and "baglanilamadi" in d["dinleyici"]["hata"]
    finally:
        tutan.close()


def test_kimlik_yerel_belirtec_ve_uzak_anahtar(sunucu):
    app, sv, yerel, proje = sunucu
    port, _ = ac(yerel)
    assert uzak_istek(port, "GET", "/api/durum", token=None)[0] == 401
    assert uzak_istek(port, "GET", "/api/durum", token="yanlis")[0] == 401
    assert uzak_istek(port, "GET", "/api/durum", token="")[0] == 401
    st, d = uzak_istek(port, "GET", "/api/durum")
    assert st == 200 and d["baglanti"] == {"uzak": True, "terminal": False, "yonetim": False}
    assert uzak_istek(port, "GET", "/api/durum", token=app.token)[0] == 200  # yerel belirtec de gecerli
    assert yerel("GET", "/api/durum")[1]["baglanti"] == {"uzak": False, "terminal": True, "yonetim": True}
    assert yerel("GET", "/api/durum", token=anahtar())[0] == 401  # cihaz anahtari YEREL dinleyicide gecmez


def test_host_ve_origin_denetimi(sunucu):
    app, sv, yerel, proje = sunucu
    port, _ = ac(yerel)
    assert uzak_istek(port, "GET", "/api/durum", host=f"{DNS}:{port}")[0] == 200  # MagicDNS adi
    assert uzak_istek(port, "GET", "/api/durum", host=f"127.0.0.2:{port}")[0] == 200
    for kotu in (f"127.0.0.1:{port}", f"evil.example:{port}", f"127.0.0.2:{port + 1}", "127.0.0.2", "", f"localhost:{port}"):
        assert uzak_istek(port, "GET", "/api/durum", host=kotu)[0] == 403, kotu
    for origin in ("http://evil.example", "null", f"http://evil.example:{port}", f"http://127.0.0.1:{port}", f"https://127.0.0.2:{port}"):
        assert uzak_istek(port, "POST", "/api/gorev", {"gorev": "x"}, host=f"127.0.0.2:{port}", origin=origin)[0] == 403, origin
    assert uzak_istek(port, "POST", "/api/gorev", {"gorev": "x"}, host=f"127.0.0.2:{port}", origin=f"http://{DNS}:{port}")[0] == 200


def test_uzak_istemci_gorev_verebilir_ve_proje_islerini_gorur(sunucu):
    app, sv, yerel, proje = sunucu
    port, _ = ac(yerel)
    st, plan = uzak_istek(port, "POST", "/api/gorev", {"gorev": "uzaktan gorev"})
    assert st == 200 and plan["tur"] == "plan" and plan["gorev"] == "uzaktan gorev"
    for yontem, yol in (("GET", "/api/dosyalar"), ("GET", "/api/github/proje"), ("GET", "/api/git/gecmis"), ("GET", "/api/ciktilar"), ("GET", "/api/proje-gruplari"), ("GET", "/api/modeller")):
        assert uzak_istek(port, yontem, yol)[0] != 403, yol


def test_yasaklar_http_uzerinden_de_gecerli_ve_hata_mesaji_aciklayici(sunucu):
    app, sv, yerel, proje = sunucu
    port, _ = ac(yerel)
    for yontem, yol in YASAK_VARSAYILAN:
        st, d = uzak_istek(port, yontem, yol, {} if yontem == "POST" else None)
        assert st == 403 and "hata" in d, (yontem, yol, st)
    assert "Terminal uzaktan kapali" in uzak_istek(port, "GET", "/api/terminal")[1]["hata"]
    assert yerel("GET", "/api/terminal")[0] == 200  # yerelde etkilenmez


def test_terminal_ve_yonetim_anahtarlari_http_ile_acilir(sunucu):
    app, sv, yerel, proje = sunucu
    port, _ = ac(yerel, terminal=True)
    assert uzak_istek(port, "GET", "/api/terminal")[0] == 200 and uzak_istek(port, "POST", "/api/mcp-sunuculari", {})[0] == 403
    yerel("POST", "/api/uzak", {"yonetim": True})
    assert uzak_istek(port, "POST", "/api/mcp-sunuculari", {})[0] == 400  # politikadan gecti, govde gecersiz
    assert uzak_istek(port, "GET", "/api/klasorler")[0] == 200
    kimlik = yerel("GET", "/api/uzak")[1]["ayar"]["cihazlar"][0]["kimlik"]
    for yontem, yol, govde in (("GET", "/api/uzak", None), ("POST", "/api/uzak", {"acik": False}), ("POST", "/api/uzak/cihaz-ekle", {"ad": "saldirgan"}),
                               ("POST", "/api/uzak/cihaz-iptal", {"kimlik": kimlik})):
        assert uzak_istek(port, yontem, yol, govde)[0] == 403, yol  # her sey acikken bile
    assert yerel("GET", "/api/uzak")[1]["dinleyici"]["calisiyor"] is True


def test_uzaktan_klasor_acma_kayitli_proje_ya_da_kok_altinda(sunucu):
    app, sv, yerel, proje = sunucu
    port, _ = ac(yerel)
    disarida = proje.resolve().parent.parent  # kok: acik projenin ust klasoru
    st, d = uzak_istek(port, "POST", "/api/klasor", {"yol": str(disarida)})
    assert st == 403 and "kayitli" in d["hata"] and app.klasor == proje.resolve()
    assert uzak_istek(port, "POST", "/api/klasor", {"yol": "goreli"})[0] == 403
    assert uzak_istek(port, "POST", "/api/klasor", {"yol": str(proje), "git_baslat": True})[0] == 403
    assert uzak_istek(port, "POST", "/api/klasor", {"yol": ""})[0] == 403 and uzak_istek(port, "POST", "/api/klasor", {})[0] == 403
    assert uzak_istek(port, "POST", "/api/klasor", {"yol": str(proje)})[0] == 200
    yan = proje.resolve().parent / "yan-klasor"
    yan.mkdir()
    assert uzak_istek(port, "POST", "/api/klasor", {"yol": str(yan)})[0] == 403  # kok secilmemisse yalniz acik proje: yan klasor ACILMAZ
    ic = proje.resolve() / "alt-klasor"
    ic.mkdir()
    assert uzak_istek(port, "POST", "/api/klasor", {"yol": str(ic)})[0] == 200  # acik projenin icindeki kayitsiz klasor acilir
    assert yerel("POST", "/api/uzak", {"acik": True, "port": port, "kok": str(proje.resolve().parent)})[0] == 200  # kullanici koku bilerek secer
    assert uzak_istek(port, "POST", "/api/klasor", {"yol": str(yan)})[0] == 200


def test_uzaktan_model_degisir_ama_gizli_dosya_korumasi_kapatilamaz(sunucu):
    app, sv, yerel, proje = sunucu
    port, _ = ac(yerel)
    ayar = uzak_istek(port, "GET", "/api/ayar")[1]
    ayar["roller"]["kodcu"]["model"] = "baska/model"
    assert uzak_istek(port, "PUT", "/api/ayar", ayar)[0] == 200 and app.ayar_oku()["roller"]["kodcu"]["model"] == "baska/model"
    ayar["roller"]["kodcu"]["okuma_riski_kabul"] = True
    st, d = uzak_istek(port, "PUT", "/api/ayar", ayar)
    assert st == 403 and "okuma_riski_kabul" in d["hata"] and not app.ayar_oku()["roller"]["kodcu"].get("okuma_riski_kabul")
    assert yerel("PUT", "/api/ayar", ayar)[0] == 200  # yerelde serbest (bilincli karar)


def test_son_uzak_erisim_kaydedilir(sunucu):
    app, sv, yerel, proje = sunucu
    port, _ = ac(yerel)
    assert yerel("GET", "/api/uzak")[1]["dinleyici"]["son_erisim"] is None
    uzak_istek(port, "GET", "/api/durum")
    son = yerel("GET", "/api/uzak")[1]["dinleyici"]["son_erisim"]
    assert son["ip"] == "127.0.0.1" and son["zaman"][:2] == "20"
    yerel("GET", "/api/durum")
    assert yerel("GET", "/api/uzak")[1]["dinleyici"]["son_erisim"] == son  # yerel istekler uzak erisim sayilmaz


def test_kapatinca_port_kapanir_ve_acik_akis_kesilir(sunucu):
    app, sv, yerel, proje = sunucu
    port, _ = ac(yerel)
    c = http.client.HTTPConnection("127.0.0.2", port, timeout=10)
    c.request("GET", "/api/olaylar", headers={"Host": f"127.0.0.2:{port}", "X-Aktapokus-Token": anahtar()})
    r = c.getresponse()
    assert r.status == 200
    bitti = threading.Event()
    threading.Thread(target=lambda: (r.read(), bitti.set()), daemon=True).start()
    time.sleep(0.5)
    assert not bitti.is_set()
    yerel("POST", "/api/uzak", {"acik": False})
    assert bitti.wait(6), "acik uzak akis kapatinca kesilmedi"
    c.close()
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.2", port), timeout=2).close()
    assert yerel("GET", "/api/uzak")[1]["dinleyici"]["calisiyor"] is False


def _akis_ac(port, jeton):
    c = http.client.HTTPConnection("127.0.0.2", port, timeout=10)
    c.request("GET", "/api/olaylar", headers={"Host": f"127.0.0.2:{port}", "X-Aktapokus-Token": jeton})
    r = c.getresponse()
    assert r.status == 200
    bitti = threading.Event()
    threading.Thread(target=lambda: (r.read(), bitti.set()), daemon=True).start()
    return c, bitti


def test_cihaz_iptal_edilince_anahtari_ve_acik_akisi_aninda_gecersiz_digerleri_etkilenmez(sunucu):
    app, sv, yerel, proje = sunucu
    port, _ = ac(yerel)
    telefon = anahtar()
    tablet, _ = cihaz_ekle(yerel, "tablet")
    c1, bitti1 = _akis_ac(port, telefon)
    c2, bitti2 = _akis_ac(port, tablet)
    time.sleep(0.3)
    kimlik = next(c["kimlik"] for c in yerel("GET", "/api/uzak")[1]["ayar"]["cihazlar"] if c["ad"] == "telefon")
    st, d = yerel("POST", "/api/uzak/cihaz-iptal", {"kimlik": kimlik})
    assert st == 200 and [c["ad"] for c in d["ayar"]["cihazlar"]] == ["tablet"] and d["dinleyici"]["calisiyor"] is True
    assert bitti1.wait(6), "iptal edilen cihazin acik akisi kesilmedi"
    assert not bitti2.is_set()  # diger cihazin oturumu surer (dinleyici yeniden kurulmadi)
    assert uzak_istek(port, "GET", "/api/durum", token=telefon)[0] == 401 and uzak_istek(port, "GET", "/api/durum", token=tablet)[0] == 200
    assert "ANAHTAR-REDDEDILDI 127.0.0.1 gecersiz ya da iptal edilmis anahtar" in uzak.dosya_yolu().with_suffix(".log").read_text(encoding="utf-8")
    assert yerel("POST", "/api/uzak/cihaz-iptal", {"kimlik": kimlik})[0] == 404
    c1.close()
    c2.close()


def test_suresi_dolan_anahtar_ve_acik_akisi_reddedilir(sunucu, monkeypatch):
    app, sv, yerel, proje = sunucu
    port, _ = ac(yerel)
    c, bitti = _akis_ac(port, anahtar())
    time.sleep(0.3)
    assert not bitti.is_set()
    gercek = time.time
    monkeypatch.setattr(uzak.time, "time", lambda: gercek() + 91 * 86400)  # 90 gun sonrasi
    assert bitti.wait(6), "suresi dolan anahtarin acik akisi kesilmedi"
    assert uzak_istek(port, "GET", "/api/durum")[0] == 401
    kayit = uzak.dosya_yolu().with_suffix(".log").read_text(encoding="utf-8")
    assert "suresi dolmus anahtar (cihaz: telefon)" in kayit and anahtar() not in kayit
    assert yerel("GET", "/api/uzak")[1]["ayar"]["cihazlar"][0]["suresi_doldu"] is True
    c.close()


def test_suresiz_cihaz_ve_ekleme_dogrulamasi(sunucu):
    app, sv, yerel, proje = sunucu
    port, _ = ac(yerel)
    k, d = cihaz_ekle(yerel, "masaustu", gun=0)
    assert d["yeni"]["cihaz"]["bitis"] is None and uzak_istek(port, "GET", "/api/durum", token=k)[0] == 200
    for kotu in ({"ad": ""}, {"ad": "  "}, {"ad": "x" * 41}, {"ad": "a\nb"}, {"ad": 5}, {"ad": "TELEFON"}, {"ad": "y", "gun": -1}, {"ad": "y", "gun": "90"},
                 {"ad": "y", "gun": True}, {"ad": "y", "gun": 4000}):
        assert yerel("POST", "/api/uzak/cihaz-ekle", kotu)[0] == 400, kotu
    assert [c["ad"] for c in yerel("GET", "/api/uzak")[1]["ayar"]["cihazlar"]] == ["telefon", "masaustu"]


def test_cihaz_son_kullanim_zamani_ve_ip_kaydedilir(sunucu):
    app, sv, yerel, proje = sunucu
    port, _ = ac(yerel)
    assert yerel("GET", "/api/uzak")[1]["ayar"]["cihazlar"][0]["son_zaman"] is None
    once = time.time()
    uzak_istek(port, "GET", "/api/durum")
    c = yerel("GET", "/api/uzak")[1]["ayar"]["cihazlar"][0]
    assert c["son_ip"] == "127.0.0.1" and c["son_zaman"] >= once - 1
    assert uzak.oku().cihazlar[0].son_ip == "127.0.0.1"  # diske de yazildi


def test_gecis_eski_tek_anahtar_eski_cihaz_olur_ve_calismaya_devam_eder(ortam, proje):
    eski = "e" * 43
    port = bos_port()
    uzak.dosya_yolu().write_text(json.dumps({"acik": True, "port": port, "terminal": False, "yonetim": False, "anahtar": uzak.gizli.koru(eski)}), encoding="utf-8")
    a = uzak.oku()
    assert [c.ad for c in a.cihazlar] == [uzak.ESKI_CIHAZ_ADI] and a.acik is True and a.port == port
    c = a.cihazlar[0]
    assert c.ozet == uzak.ozet(eski) and 89 * 86400 < c.bitis - c.olusturma <= 90 * 86400
    ham = uzak.dosya_yolu().read_text(encoding="utf-8")
    assert '"anahtar"' not in ham and eski not in ham  # eski anahtar dosyadan silindi
    assert [x.kimlik for x in uzak.oku().cihazlar] == [c.kimlik]  # ikinci okumada yeniden tasinmaz
    app = Uygulama()
    sv = ArayuzSunucusu(app)
    sv.baslat()
    try:
        assert sv.uzak_uygula()["calisiyor"] is True
        assert uzak_istek(port, "GET", "/api/durum", token=eski)[0] == 200  # bagli telefon kopmaz
    finally:
        sv.kapat()


def test_gecis_duz_metin_eski_anahtar_da_tasinir(ortam):
    eski = "d" * 43
    uzak.dosya_yolu().write_text(json.dumps({"anahtar": eski}), encoding="utf-8")
    assert uzak.cihaz_bul(uzak.oku(), eski)[0].ad == uzak.ESKI_CIHAZ_ADI
    assert eski not in uzak.dosya_yolu().read_text(encoding="utf-8")


def test_karsilastirma_sabit_zamanli_ve_erken_cikmaz(ortam, monkeypatch):
    for ad in ("a", "b", "c"):
        uzak.cihaz_ekle(ad)
    ayar = uzak.oku()
    cagrilar = []
    gercek = uzak.hmac.compare_digest
    monkeypatch.setattr(uzak.hmac, "compare_digest", lambda x, y: cagrilar.append(1) or gercek(x, y))
    eslesen = ayar.cihazlar[0]
    _, _, k = uzak.cihaz_ekle("d")
    ayar = uzak.oku()
    cagrilar.clear()
    assert uzak.cihaz_bul(ayar, k)[0].ad == "d" and len(cagrilar) == 4
    cagrilar.clear()
    assert uzak.cihaz_bul(ayar, "yanlis")[0] is None and len(cagrilar) == 4  # eslesme olsa da olmasa da hepsi karsilastirilir
    assert eslesen.ad == "a"
    assert uzak.cihaz_bul(ayar, "") == (None, "anahtar yok")
    kaynak = (Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "uzak.py").read_text(encoding="utf-8")
    govde = kaynak.split("def cihaz_bul")[1].split("\ndef ")[0]
    assert "hmac.compare_digest" in govde and "==" not in govde and "break" not in govde and "return" not in govde.split("for c in")[1].split("if bulunan is None")[0]


def test_anahtar_hicbir_api_yanitina_ve_gunluge_sizmaz(sunucu):
    app, sv, yerel, proje = sunucu
    port, _ = ac(yerel, terminal=True, yonetim=True)
    k = anahtar()
    oz = uzak.ozet(k)
    uzak_istek(port, "GET", "/api/durum")
    uzak_istek(port, "GET", "/api/durum", token=k[:-1] + ("A" if k[-1] != "A" else "B"))  # reddedilen (gunluge yazilir)
    uzak_istek(port, "POST", "/api/klasor", {"yol": str(proje.parent.parent)})  # klasor reddi de gunluge yazilir
    for yontem, yol in (("GET", "/api/uzak"), ("GET", "/api/durum"), ("GET", "/api/ayar"), ("GET", "/api/hesaplar"), ("GET", "/api/telegram")):
        metin = json.dumps(yerel(yontem, yol)[1], ensure_ascii=False)
        assert k not in metin and oz not in metin, yol
    for yontem, yol in (("GET", "/api/durum"), ("GET", "/api/ayar"), ("GET", "/api/hesaplar")):
        metin = json.dumps(uzak_istek(port, yontem, yol)[1], ensure_ascii=False)
        assert k not in metin and oz not in metin, yol
    kayit = uzak.dosya_yolu().with_suffix(".log").read_text(encoding="utf-8")
    assert "ANAHTAR-REDDEDILDI" in kayit and k not in kayit and k[:-1] not in kayit and oz not in kayit
    assert k not in uzak.dosya_yolu().read_text(encoding="utf-8")


def test_gunluk_satir_enjeksiyonu_ve_boyut_siniri(ortam, monkeypatch):
    uzak.kayit_yaz("REDDEDILDI 1.2.3.4 a\nSAHTE SATIR")
    assert uzak.dosya_yolu().with_suffix(".log").read_text(encoding="utf-8").count("\n") == 1
    monkeypatch.setattr(uzak, "AZAMI_KAYIT", 10)
    uzak.kayit_yaz("ikinci")
    assert uzak.dosya_yolu().with_suffix(".log.1").is_file() and "ikinci" in uzak.dosya_yolu().with_suffix(".log").read_text(encoding="utf-8")


def test_ayar_degisince_dinleyici_yeniden_kurulur_terminal_kapaninca_akis_kesilir(sunucu):
    app, sv, yerel, proje = sunucu
    port, _ = ac(yerel, terminal=True)
    assert uzak_istek(port, "GET", "/api/terminal")[0] == 200
    yerel("POST", "/api/uzak", {"terminal": False})
    assert uzak_istek(port, "GET", "/api/terminal")[0] == 403


def test_uzak_ayar_uclari_gecersiz_girdiler(sunucu):
    app, sv, yerel, proje = sunucu
    for kotu in ({"acik": "evet"}, {"port": 80}, {"terminal": 1}):
        assert yerel("POST", "/api/uzak", kotu)[0] == 400
    assert yerel("POST", "/api/uzak", [1, 2])[0] in (400, 500)
    assert uzak.oku().acik is False
    assert yerel("GET", "/api/uzak", token=None)[0] == 401 and yerel("POST", "/api/uzak", {}, token=None)[0] == 401


def test_kayitli_acik_ayarla_baslayinca_dinleyici_kendiliginden_kurulur(ortam, proje):
    port = bos_port()
    uzak.guncelle({"acik": True, "port": port})
    app = Uygulama()
    sv = ArayuzSunucusu(app)
    sv.baslat()
    try:
        assert sv.uzak_uygula()["calisiyor"] is True and sv.uzak_http.server_address == ("127.0.0.2", port)
    finally:
        sv.kapat()
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.2", port), timeout=2).close()


def test_sunucu_kapaninca_uzak_dinleyici_de_kapanir(ortam, proje):
    app = Uygulama()
    sv = ArayuzSunucusu(app)
    sv.baslat()
    port, _ = ac(Istemci(sv))
    assert sv.uzak_http is not None
    sv.kapat()
    assert sv.uzak_http is None
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.2", port), timeout=2).close()


def test_telegram_uzak_erisime_dokunmaz():
    kaynak = (Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "telegram.py").read_text(encoding="utf-8")
    assert "uzak_ayarla" not in kaynak and "uzak_anahtar" not in kaynak and "import uzak" not in kaynak and "from . import uzak" not in kaynak


def test_kaynakta_tum_arayuzlere_baglanma_yok():
    kaynak = (Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "arayuz.py").read_text(encoding="utf-8")
    assert '"0.0.0.0"' not in kaynak and '("", ' not in kaynak and "YEREL_ISTEMCILER" in kaynak


def test_reddedilen_istegin_govdesi_ayni_baglantidaki_sonraki_istegi_bozmaz(sunucu):
    """Gercek hata: 401/403 govde okunmadan donunce kalan byte'lar keep-alive baglantida bir sonraki istegin basi sanildi (501)."""
    app, sv, yerel, proje = sunucu
    port, _ = ac(yerel)
    jeton_u = anahtar()
    govde = json.dumps({"x": "y" * 500})
    ornekler = [
        ("127.0.0.2", port, f"127.0.0.2:{port}", jeton_u, "/api/clilar"),      # uzak: politika 403
        ("127.0.0.2", port, f"127.0.0.2:{port}", None, "/api/gorev"),          # uzak: belirtec yok 401
        ("127.0.0.2", port, f"evil.example:{port}", jeton_u, "/api/gorev"),    # uzak: Host 403
        ("127.0.0.1", sv.port, f"127.0.0.1:{sv.port}", None, "/api/gorev"),    # yerel: belirtec yok 401
        ("127.0.0.1", sv.port, f"127.0.0.1:{sv.port}", app.token, "/api/yok"), # yerel: 404
    ]
    for adres, p, host, jeton, yol in ornekler:
        c = http.client.HTTPConnection(adres, p, timeout=10)
        try:
            basliklar = {"Host": host, "Content-Type": "application/json"}
            if jeton:
                basliklar["X-Aktapokus-Token"] = jeton
            c.request("POST", yol, body=govde, headers=basliklar)
            r1 = c.getresponse()
            r1.read()
            assert r1.status in (401, 403, 404), (yol, r1.status)
            geri = {"Host": f"127.0.0.2:{p}" if p == port else f"127.0.0.1:{p}", "X-Aktapokus-Token": jeton_u if p == port else app.token}
            c.request("GET", "/api/durum", headers=geri)  # AYNI baglanti
            r2 = c.getresponse()
            r2.read()
            assert r2.status == 200, (yol, "sonraki istek bozuldu", r2.status)
        finally:
            c.close()


def test_arayuz_uzak_erisim_bolumu_ve_telefon_duzeni():
    html = (Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "web" / "index.html").read_text(encoding="utf-8")
    for parca in ('["uzak","Uzak erişim"]', "function uzakBolumu", "function uzakDuzen", "/api/uzak/cihaz-ekle", "/api/uzak/cihaz-iptal", 'id="mobilGezinme"', "function mobilGoster", "@media (max-width:900px)",
                  'data-m="sol"', 'data-m="orta"', 'data-m="sag"', 'id="motorUyari"'):
        assert parca in html, parca
    govde = html.split("function uzakBolumu")[1].split("/* ---- Telefon / dar ekran")[0]  # yalniz uzakBolumu govdesi (sonraki bolumlerdeki sabit simge tablosu innerHTML kullanir)
    # terminal ve yonetim anahtarlari acilirken ortak degistir(govde, onay) onay penceresi gosterir; cihaz iptali iki adimli dugmedir (acilir pencere yok)
    assert "confirm(onay)" in govde and govde.count("Yine de açılsın mı?") == 2 and "innerHTML" not in govde
    cihaz = govde.split("/* cihazlar")[1]
    assert 'textContent="İptal?"' in cihaz and "confirm(" not in cihaz and "alert(" not in cihaz and "prompt(" not in cihaz and "yeni=null" in cihaz
    assert "TAM komut" in govde and "KAPALI" in govde  # riskli anahtarlar acikca anlatilir
    assert 'localStorage' in html.split("const T=")[1].split("})();")[0]  # uzak (telefon) kaynakta belirtec kalici; yerelde yalniz sekme oturumu


def test_politika_tablosu_politika_uygulanmadan_once_govdeyi_tuketir():
    kaynak = (Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "arayuz.py").read_text(encoding="utf-8")
    assert "_govdeyi_bosalt" in kaynak and "def _yol_ic" in kaynak


def test_dinleyici_kurarken_ters_dns_sorgusu_yapilmaz(monkeypatch):
    """Regresyon: http.server.HTTPServer.server_bind socket.getfqdn() cagirir; Windows'ta 127.0.0.1 disi adreslerde saniyelerce surup arayuzu kilitliyordu."""
    from aktapokus_ai_studio.arayuz import UzakSunucu, YerelSunucu
    from http.server import BaseHTTPRequestHandler

    def yasak(*a, **k):
        raise AssertionError("getfqdn cagrildi")

    monkeypatch.setattr(socket, "getfqdn", yasak)
    for sinif, adres in ((UzakSunucu, "127.0.0.2"), (YerelSunucu, "127.0.0.1")):
        s = sinif((adres, 0), BaseHTTPRequestHandler)
        try:
            assert s.server_address[0] == adres and s.server_name == adres and s.server_port == s.server_address[1]
        finally:
            s.server_close()


def test_yikici_git_ve_gonderme_yonetim_izni_ister(ortam):
    kapali = uzak.Ayar(yonetim=False)
    acik = uzak.Ayar(yonetim=True)
    for yol in ("/api/github/push", "/api/github/pr", "/api/github/dal", "/api/github/issue-yorum", "/api/git/degisiklik-at", "/api/git/pull", "/api/git/cek",
                "/api/git/birlestir", "/api/git/dal-sil", "/api/git/stash-sil", "/api/projeler/unut", "/api/motorlar/rolleri-gecir"):
        assert uzak.politika("POST", yol, kapali), yol
        assert uzak.politika("POST", yol, acik) is None, yol
    assert uzak.politika("POST", "/api/github/commit", kapali) is None and uzak.politika("GET", "/api/git/gecmis", kapali) is None


def test_bilinmeyen_uc_uzaktan_reddedilir(ortam):
    for a in (uzak.Ayar(yonetim=False), uzak.Ayar(yonetim=True)):
        assert uzak.politika("POST", "/api/yeni-tehlikeli-uc", a)
        assert uzak.politika("GET", "/api/yeni-tehlikeli-uc", a)


def test_her_uc_uzak_listesinde_siniflandirilmis():
    """Yeni uc eklendiyse bu test duser: uzaktan guvenli mi karar verip uzak.UZAK_BILINEN_UCLAR'a (gerekirse YONETIM_KAPALIYKEN_YASAK'a) ekleyin."""
    kaynak = (Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "arayuz.py").read_text(encoding="utf-8")
    assert set(re.findall(r'"(/api/[a-zA-Z0-9_/-]+)"', kaynak)) <= uzak.UZAK_BILINEN_UCLAR



def test_dinamik_uclar_uzak_listesinde():
    """Yolunda kimlik tasiyan her uc (re.match deseni) uzak.UZAK_DINAMIK_UCLAR'da olmali; yoksa telefondan 'tanimli degil' doner."""
    kaynak = (Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "arayuz.py").read_text(encoding="utf-8")
    desenler = set(re.findall(r're\.match\(r"(\^/api/[^"]+)"', kaynak)) - {r"^/api/p/([0-9a-f]{10})(/.*)$"}
    assert desenler and desenler <= set(uzak.UZAK_DINAMIK_UCLAR)


def test_telefondan_plan_onayi_ve_karar_verilir():
    a = uzak.Ayar()
    for islem in ("onayla", "reddet", "karar", "durdur", "testi-atla"):
        assert uzak.politika("POST", f"/api/gorev/1a2b3c/{islem}", a) is None, islem
    assert uzak.politika("GET", "/api/beceriler/ornek-beceri", a) is None
    assert uzak.politika("POST", "/api/gorev/1a2b3c/baska", a) and uzak.politika("POST", "/api/gorev/xyz/onayla", a)
    assert uzak.politika("POST", "/api/telegram/baslat", a) and uzak.politika("POST", "/api/telegram/baslat", uzak.Ayar(yonetim=True)) is None
    assert uzak.politika("POST", "/api/terminal/abcd/girdi", a) and uzak.politika("POST", "/api/terminal/abcd/girdi", uzak.Ayar(terminal=True)) is None

def test_aktapokus_sirlari_ajan_ortamina_gecmez(monkeypatch, tmp_path):
    from aktapokus_ai_studio.runners import _alt_surec_ortami
    monkeypatch.setenv("AKTAPOKUS_TELEGRAM_TOKEN", "gizli")
    monkeypatch.setenv("AKTAPOKUS_CLAUDE", "yol")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "cli-anahtari")
    o = _alt_surec_ortami(tmp_path)
    assert "AKTAPOKUS_TELEGRAM_TOKEN" not in o and o["AKTAPOKUS_CLAUDE"] == "yol" and o["ANTHROPIC_API_KEY"] == "cli-anahtari"


def test_uzak_kok_siniri(tmp_path):
    kok = tmp_path / "kok"
    (kok / "proje").mkdir(parents=True)
    (tmp_path / "disari").mkdir()
    assert uzak.kok_klasoru(uzak.Ayar(), kok / "proje") == (kok / "proje").resolve()  # yalniz acik proje (ust klasor DEGIL)
    assert uzak.kok_klasoru(uzak.Ayar(), None) is None and not uzak.kokun_icinde(Path.home(), None)  # proje yoksa ev dizini gezilmez
    assert uzak.kokun_icinde(kok / "proje", kok) and uzak.kokun_icinde(kok, kok)
    assert not uzak.kokun_icinde(tmp_path / "disari", kok)
    assert not uzak.kokun_icinde(kok / ".." / "disari", kok)
    assert uzak.guncelle({"kok": str(kok)}).kok == str(kok.resolve())
    with pytest.raises(uzak.UzakHatasi):
        uzak.guncelle({"kok": str(tmp_path / "yok")})
