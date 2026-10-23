"""Terminal HTTP ucu: belirtec/Origin/sinir denetimleri (ConPTY gerektirmeden) ve gercek ConPTY ile SSE akisi."""

import base64
import http.client
import json
import time

import pytest

from aktapokus_ajan import terminal
from aktapokus_ajan.arayuz import ArayuzSunucusu, Uygulama
from test_arayuz import Istemci, bekle

CONPTY = terminal.kontrol()
gerek = pytest.mark.skipif(not CONPTY, reason="ConPTY bu ortamda calismiyor")


@pytest.fixture
def api(proje):
    app = Uygulama()
    sv = ArayuzSunucusu(app)
    sv.baslat()
    app.klasor = proje
    yield app, sv, Istemci(sv)
    sv.kapat()


def b64(metin: bytes) -> str:
    return base64.b64encode(metin).decode()


def akis_oku(sv, kimlik, ifade: bytes, sn=15, son=0):
    c = http.client.HTTPConnection("127.0.0.1", sv.port, timeout=sn)
    c.request("GET", f"/api/terminal/{kimlik}/akis?son={son}", headers={"X-Aktapokus-Token": sv.app.token})
    r = c.getresponse()
    assert r.status == 200 and r.getheader("Content-Type").startswith("text/event-stream")
    cikti, bitis = b"", time.monotonic() + sn
    while time.monotonic() < bitis and ifade not in cikti:
        satir = r.readline()
        if not satir:
            break
        if satir.startswith(b"data: "):
            d = json.loads(satir[6:])
            if d.get("bitti"):
                break
            cikti += base64.b64decode(d["b"])
    c.close()
    return cikti


# ---------- guvenlik (ConPTY'siz) ----------
def test_terminal_uclari_belirtec_ister(api):
    _, _, istek = api
    assert istek("GET", "/api/terminal", token=None)[0] == 401
    assert istek("POST", "/api/terminal/ac", {}, token=None)[0] == 401
    assert istek("POST", "/api/terminal/abcd1234/girdi", {"b": "eA=="}, token="yanlis")[0] == 401


def test_yabanci_origin_durum_degistiren_istekleri_reddeder(api):
    _, sv, _ = api
    for origin in ("http://evil.example", "null", f"http://127.0.0.1:{sv.port + 1}"):
        c = http.client.HTTPConnection("127.0.0.1", sv.port, timeout=10)
        c.request("POST", "/api/terminal/ac", body="{}", headers={"X-Aktapokus-Token": sv.app.token, "Origin": origin, "Content-Type": "application/json"})
        r = c.getresponse()
        r.read()
        c.close()
        assert r.status == 403, origin


def test_kendi_origin_kabul_edilir(api, monkeypatch):
    _, sv, _ = api
    monkeypatch.setattr(terminal, "destekleniyor", lambda: False)
    c = http.client.HTTPConnection("127.0.0.1", sv.port, timeout=10)
    c.request("POST", "/api/terminal/ac", body="{}", headers={"X-Aktapokus-Token": sv.app.token, "Origin": f"http://127.0.0.1:{sv.port}", "Content-Type": "application/json"})
    r = c.getresponse()
    r.read()
    c.close()
    assert r.status == 501  # Origin gecti; terminal desteklenmedigi icin anlasilir hata


def test_olmayan_terminal_404(api):
    _, _, istek = api
    assert istek("POST", "/api/terminal/abcd1234/girdi", {"b": "eA=="})[0] == 404
    assert istek("POST", "/api/terminal/abcd1234/boyut", {"satir": 20, "sutun": 80})[0] == 404
    assert istek("POST", "/api/terminal/abcd1234/kapat", {})[0] == 404
    assert istek("GET", "/api/terminal/abcd1234/akis")[0] == 404


def test_vendor_yalniz_izin_listesindeki_dosyalar(api):
    _, sv, _ = api
    for ad, tur in (("xterm.js", "javascript"), ("xterm.css", "css"), ("addon-fit.js", "javascript")):
        c = http.client.HTTPConnection("127.0.0.1", sv.port, timeout=10)
        c.request("GET", f"/vendor/{ad}")
        r = c.getresponse()
        govde = r.read()
        c.close()
        assert r.status == 200 and tur in r.getheader("Content-Type") and len(govde) > 1000, ad
    for kotu in ("../index.html", "LICENSE-xterm.txt", "..%2Findex.html", "SURUMLER.txt"):
        c = http.client.HTTPConnection("127.0.0.1", sv.port, timeout=10)
        c.request("GET", f"/vendor/{kotu}")
        r = c.getresponse()
        r.read()
        c.close()
        assert r.status == 404, kotu


def test_vendor_yabanci_host_ile_reddedilir(api):
    _, sv, _ = api
    c = http.client.HTTPConnection("127.0.0.1", sv.port, timeout=10)
    c.request("GET", "/vendor/xterm.js", headers={"Host": "evil.example"})
    r = c.getresponse()
    r.read()
    c.close()
    assert r.status in (400, 403)  # DNS-rebinding korumasi statik dosyalarda da gecerli


# ---------- gercek ConPTY ----------
@gerek
def test_ac_girdi_akis_boyut_kapat_tam_dongu(api):
    app, sv, istek = api
    st, d = istek("POST", "/api/terminal/ac", {"satir": 24, "sutun": 80})
    assert st == 200, d
    kimlik = d["id"]
    assert istek("GET", "/api/terminal")[1]["acik"][0]["id"] == kimlik
    assert istek("POST", f"/api/terminal/{kimlik}/girdi", {"b": b64(b"echo HTTP_TERMINAL_DENEME\r\n")})[0] == 200
    assert b"HTTP_TERMINAL_DENEME" in akis_oku(sv, kimlik, b"HTTP_TERMINAL_DENEME")
    st, d2 = istek("POST", f"/api/terminal/{kimlik}/boyut", {"satir": 30, "sutun": 120})
    assert st == 200 and (d2["satir"], d2["sutun"]) == (30, 120)
    # yeniden baglanan tarayici ekrani bastan alir
    assert b"HTTP_TERMINAL_DENEME" in akis_oku(sv, kimlik, b"HTTP_TERMINAL_DENEME", son=0)
    assert istek("POST", f"/api/terminal/{kimlik}/kapat", {})[0] == 200
    assert istek("GET", "/api/terminal")[1]["acik"] == []


@gerek
def test_en_cok_uc_terminal_ve_gecersiz_girdiler(api):
    app, sv, istek = api
    kimlikler = [istek("POST", "/api/terminal/ac", {})[1]["id"] for _ in range(3)]
    st, d = istek("POST", "/api/terminal/ac", {})
    assert st == 409 and "3" in d["hata"]
    k = kimlikler[0]
    assert istek("POST", f"/api/terminal/{k}/girdi", {"b": "bu base64 degil!!"})[0] == 400
    assert istek("POST", f"/api/terminal/{k}/girdi", {"b": b64(b"x" * 70000)})[0] == 413
    assert istek("POST", f"/api/terminal/{k}/girdi", {})[0] == 413
    assert istek("POST", f"/api/terminal/{k}/boyut", {"satir": "abc", "sutun": 80})[0] == 400
    assert istek("POST", "/api/terminal/ac", {"satir": "x"})[0] in (400, 409)


@gerek
def test_sunucu_kapanirken_terminaller_de_kapanir(proje):
    app = Uygulama()
    sv = ArayuzSunucusu(app)
    sv.baslat()
    app.klasor = proje
    istek = Istemci(sv)
    kimlik = istek("POST", "/api/terminal/ac", {})[1]["id"]
    t = app.terminal_al(kimlik)
    pid = t.pid
    sv.kapat()
    assert bekle(lambda: not t.canli, 10)
    from aktapokus_ajan import uygulama

    assert bekle(lambda: not uygulama.surec_canli_mi(pid), 10)
    assert app.terminaller == {}


@gerek
def test_bitmis_terminal_yeni_acilista_temizlenir(api):
    app, sv, istek = api
    ids = [istek("POST", "/api/terminal/ac", {})[1]["id"] for _ in range(3)]
    istek("POST", f"/api/terminal/{ids[0]}/girdi", {"b": b64(b"exit\r\n")})
    assert bekle(lambda: not app.terminal_al(ids[0]).canli, 12)
    st, _ = istek("POST", "/api/terminal/ac", {})  # sinir dolu ama biri bitti -> temizlenir, acilir
    assert st == 200
    assert istek("POST", f"/api/terminal/{ids[0]}/girdi", {"b": b64(b"x")})[0] == 404


def test_arayuz_sayfasi_terminal_dugmesini_ve_vendor_yollarini_icerir():
    from aktapokus_ajan.arayuz import WEB

    html = (WEB / "index.html").read_text(encoding="utf-8")
    for parca in ('id="terminalDugme"', 'id="terminalSayfa"', "/vendor/xterm.js", "/vendor/addon-fit.js", "/api/terminal/ac"):
        assert parca in html, parca


def test_inter_yazi_tipi_sunulur_ve_arayuzde_tanimlidir(api):
    from aktapokus_ajan.arayuz import WEB

    _, sv, _ = api
    for ad in ("inter-latin-wght-normal.woff2", "inter-latin-ext-wght-normal.woff2"):
        c = http.client.HTTPConnection("127.0.0.1", sv.port, timeout=10)
        c.request("GET", f"/vendor/{ad}")
        r = c.getresponse()
        govde = r.read()
        c.close()
        assert r.status == 200 and r.getheader("Content-Type") == "font/woff2" and govde[:4] == b"wOF2", ad
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert '"Inter"' in html and "inter-latin-ext-wght-normal.woff2" in html  # Turkce karakterler (ğşıİ) latin-ext dosyasinda
    assert "system-ui,-apple-system" not in html  # eski varsayilan yazi tipi bir daha kullanilmaz
