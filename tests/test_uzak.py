"""Uzak erisim: ayar, Tailscale algilama, yalniz Tailscale/loopback'e baglanma, Host/Origin/anahtar, yetki daraltma, kapatinca akislarin kesilmesi.
Gercek soketler kullanilir: Tailscale yerine sahte CLI 127.0.0.2 (loopback) adresini bildirir."""

import http.client
import json
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


def ac(yerel, **ek):
    port = bos_port()
    st, d = yerel("POST", "/api/uzak", {"acik": True, "port": port, **ek})
    assert st == 200, d
    return port, d


def uzak_istek(port, yontem, yol, veri=None, token="__anahtar__", host="__dogru__", origin=None, adres="127.0.0.2"):
    anahtar = uzak.oku().anahtar
    c = http.client.HTTPConnection(adres, port, timeout=10)
    b = {"Content-Type": "application/json", "Host": f"{DNS if host == '__dogru__' else host}:{port}" if host in ("__dogru__",) else host}
    if host == "__dogru__":
        b["Host"] = f"{adres}:{port}"
    t = anahtar if token == "__anahtar__" else token
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
    assert (a.acik, a.terminal, a.yonetim, a.port) == (False, False, False, uzak.VARSAYILAN_PORT) and len(a.anahtar) >= 32
    assert "anahtar" not in a.sozluk() and uzak.guncelle({"acik": True, "terminal": True}).terminal is True
    for kotu in ({"acik": "evet"}, {"terminal": 1}, {"yonetim": None}, {"port": 80}, {"port": 70000}, {"port": "47650"}, {"port": True}, {"port": 1023}):
        with pytest.raises(uzak.UzakHatasi):
            uzak.guncelle(kotu)
    assert uzak.oku().terminal is True  # reddedilen degisiklik dosyaya yazilmadi


def test_anahtar_kalici_ve_yenilenebilir(ortam):
    uzak.guncelle({"acik": True})
    a1 = uzak.oku().anahtar
    assert uzak.oku().anahtar == a1
    assert uzak.anahtari_yenile().anahtar != a1 and uzak.oku().anahtar != a1


def test_bozuk_ya_da_eksik_dosya_kapali_varsayilan(ortam):
    uzak.dosya_yolu().write_text("{bozuk", encoding="utf-8")
    assert uzak.oku().acik is False
    uzak.dosya_yolu().write_text(json.dumps({"acik": "true", "port": 5, "terminal": "evet", "anahtar": "kisa"}), encoding="utf-8")
    a = uzak.oku()
    assert (a.acik, a.terminal, a.port) == (False, False, uzak.VARSAYILAN_PORT) and len(a.anahtar) >= 32  # gecersiz degerler guvenli varsayilana


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
    ("GET", "/api/uzak"), ("POST", "/api/uzak"), ("POST", "/api/uzak/anahtar-yenile"),
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
    for yontem, yol in (("GET", "/api/uzak"), ("POST", "/api/uzak"), ("POST", "/api/uzak/anahtar-yenile")):
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
    baglantilar = d["dinleyici"]["baglantilar"]
    assert baglantilar[0].startswith(f"http://{DNS}:{port}/#t=") and baglantilar[1].startswith(f"http://127.0.0.2:{port}/#t=")
    assert baglantilar[0].split("#t=")[1] == uzak.oku().anahtar


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
    assert yerel("GET", "/api/durum", token=uzak.oku().anahtar)[0] == 401  # uzak anahtar YEREL dinleyicide gecmez


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
    for yontem, yol in (("GET", "/api/uzak"), ("POST", "/api/uzak"), ("POST", "/api/uzak/anahtar-yenile")):
        assert uzak_istek(port, yontem, yol, {"acik": False} if yontem == "POST" else None)[0] == 403, yol  # her sey acikken bile
    assert yerel("GET", "/api/uzak")[1]["dinleyici"]["calisiyor"] is True


def test_uzaktan_klasor_acma_yalniz_kayitli_projeler(sunucu, tmp_path):
    app, sv, yerel, proje = sunucu
    port, _ = ac(yerel)
    yabanci = tmp_path / "yabanci"
    yabanci.mkdir()
    st, d = uzak_istek(port, "POST", "/api/klasor", {"yol": str(yabanci)})
    assert st == 403 and "kayitli" in d["hata"] and app.klasor == proje.resolve()
    assert uzak_istek(port, "POST", "/api/klasor", {"yol": str(proje), "git_baslat": True})[0] == 403
    assert uzak_istek(port, "POST", "/api/klasor", {"yol": ""})[0] == 403 and uzak_istek(port, "POST", "/api/klasor", {})[0] == 403
    assert uzak_istek(port, "POST", "/api/klasor", {"yol": str(proje)})[0] == 200


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
    c.request("GET", "/api/olaylar", headers={"Host": f"127.0.0.2:{port}", "X-Aktapokus-Token": uzak.oku().anahtar})
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


def test_anahtar_yenilenince_eski_anahtar_ve_acik_akislar_gecersiz(sunucu):
    app, sv, yerel, proje = sunucu
    port, _ = ac(yerel)
    eski = uzak.oku().anahtar
    c = http.client.HTTPConnection("127.0.0.2", port, timeout=10)
    c.request("GET", "/api/olaylar", headers={"Host": f"127.0.0.2:{port}", "X-Aktapokus-Token": eski})
    r = c.getresponse()
    bitti = threading.Event()
    threading.Thread(target=lambda: (r.read(), bitti.set()), daemon=True).start()
    st, d = yerel("POST", "/api/uzak/anahtar-yenile", {})
    assert st == 200 and d["dinleyici"]["calisiyor"] is True
    yeni = uzak.oku().anahtar
    assert yeni != eski and bitti.wait(6)
    assert uzak_istek(port, "GET", "/api/durum", token=eski)[0] == 401 and uzak_istek(port, "GET", "/api/durum", token=yeni)[0] == 200
    c.close()


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
    anahtar = uzak.oku().anahtar
    govde = json.dumps({"x": "y" * 500})
    ornekler = [
        ("127.0.0.2", port, f"127.0.0.2:{port}", anahtar, "/api/clilar"),      # uzak: politika 403
        ("127.0.0.2", port, f"127.0.0.2:{port}", None, "/api/gorev"),          # uzak: belirtec yok 401
        ("127.0.0.2", port, f"evil.example:{port}", anahtar, "/api/gorev"),    # uzak: Host 403
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
            geri = {"Host": f"127.0.0.2:{p}" if p == port else f"127.0.0.1:{p}", "X-Aktapokus-Token": anahtar if p == port else app.token}
            c.request("GET", "/api/durum", headers=geri)  # AYNI baglanti
            r2 = c.getresponse()
            r2.read()
            assert r2.status == 200, (yol, "sonraki istek bozuldu", r2.status)
        finally:
            c.close()


def test_arayuz_uzak_erisim_bolumu_ve_telefon_duzeni():
    html = (Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "web" / "index.html").read_text(encoding="utf-8")
    for parca in ('["uzak","Uzak erişim"]', "function uzakBolumu", "function uzakDuzen", "/api/uzak/anahtar-yenile", 'id="mobilGezinme"', "function mobilGoster", "@media (max-width:900px)",
                  'data-m="sol"', 'data-m="orta"', 'data-m="sag"', 'id="motorUyari"'):
        assert parca in html, parca
    govde = html.split("function uzakBolumu")[1].split("/* ---- Telefon / dar ekran")[0]  # yalniz uzakBolumu govdesi (sonraki bolumlerdeki sabit simge tablosu innerHTML kullanir)
    # terminal ve yonetim anahtarlari acilirken ortak degistir(govde, onay) onay penceresi gosterir; anahtar yenileme ayrica onaylidir
    assert "confirm(onay)" in govde and govde.count("Yine de açılsın mı?") == 2 and "Uzak anahtar yenilensin mi?" in govde and "innerHTML" not in govde
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
