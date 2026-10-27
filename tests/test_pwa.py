"""PWA (ana ekrana uygulama olarak ekleme) + Tailscale `serve` ile HTTPS + sade yan cubuk. Sahte `tailscale` CLI'i kullanilir."""

import http.client
import json
from pathlib import Path

import pytest

from aktapokus_ai_studio import uzak
from test_uzak import DNS, ac, ortam, sunucu, uzak_istek  # noqa: F401  (pytest fixture'lari)

WEB = Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "web"


@pytest.fixture
def serve(ortam, tmp_path):
    yol = tmp_path / "serve.json"
    ortam.setenv("SAHTE_TS_SERVE", str(yol))
    return yol


def _cfg(yol):
    try:
        return json.loads(yol.read_text(encoding="utf-8"))
    except OSError:
        return {"Web": {}}


def _ham_get(port, yol, host, adres="127.0.0.2"):
    c = http.client.HTTPConnection(adres, port, timeout=10)
    c.request("GET", yol, headers={"Host": host})  # belirtec YOK
    r = c.getresponse()
    govde = r.read()
    c.close()
    return r.status, r.getheader("Content-Type"), govde


# ---------- statik PWA dosyalari ----------
def test_manifest_ve_simgeler_dosyada_ve_tutarli():
    m = json.loads((WEB / "manifest.webmanifest").read_text(encoding="utf-8"))
    assert m["display"] == "standalone" and m["start_url"] == "/" and m["short_name"]
    boyutlar = {i["sizes"] for i in m["icons"]}
    assert {"192x192", "512x512"} <= boyutlar
    for i in m["icons"]:
        assert (WEB / i["src"].lstrip("/")).is_file()
    assert "caches" not in (WEB / "sw.js").read_text(encoding="utf-8")  # onbellek YOK: belirtec/ozel veri saklanmaz


def test_pwa_dosyalari_belirtecsiz_yerelde_ve_uzakta_servis_edilir(sunucu):
    app, sv, yerel, proje = sunucu
    port, _ = ac(yerel)
    for yol, tur in (("/manifest.webmanifest", "application/manifest+json"), ("/sw.js", "text/javascript"), ("/simge-192.png", "image/png"), ("/simge-512.png", "image/png")):
        st, ct, govde = _ham_get(port, yol, f"127.0.0.2:{port}")
        assert st == 200 and ct.startswith(tur) and govde, yol
        st, ct, govde = _ham_get(sv.port, yol, f"127.0.0.1:{sv.port}", "127.0.0.1")
        assert st == 200 and ct.startswith(tur), yol
    assert _ham_get(port, "/simge-999.png", f"127.0.0.2:{port}")[0] == 404
    assert _ham_get(port, "/manifest.webmanifest", "kotu.example:80")[0] == 403  # Host denetimi PWA dosyalarinda da gecerli


def test_arayuz_pwa_ve_sade_yan_cubuk_baglidir():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    for parca in ('rel="manifest"', 'name="theme-color"', '"/sw.js"', "akisiYenidenKur", "visibilitychange", "HTTPS ile aç"):
        assert parca in html, parca
    assert "https://" not in html  # disa acik adres yok
    # sade yan cubuk: 'Yeni' (uzun etiket yok), hesap kutusunda aciklama satiri yok, terminal/ayar yuvarlak simge dugmeleri, dugmeler ekranla buyumez
    assert "+ Yeni</button>" in html and "+ Yeni görev</button>" not in html
    assert 'id="terminalDugme" class="yuvarlak simge"' in html and 'id="ayarDugme" class="yuvarlak simge"' in html
    assert "#girdi>.row{flex-wrap:nowrap!important" in html and "#girdiBilgi{display:none!important}" in html and "test-nokta" in html  # yazma kutusu alti her zaman tek satir
    assert ".arac-komut{background:var(--errbg)" not in html and "gercekHata" in html and "bitis-sade" in html  # kirmizi yalniz gercek hata
    assert 'id="onayBar"' in html and "onayBar(w)" in html and "karar-satir" in html  # onay/yetki istegi yazma kutusunun ustunde, akista degil
    assert "field-sizing:content" in html and "#gorev{border:0!important" in html  # yazma alani cercevesiz, kendiliginden buyur
    assert ".fark-satir{display:flex" in html and "overflow-wrap:anywhere" in html  # uzun yol satiri sarilir, yatay kaydirma yok
    assert '"Hep onayla"' in html and "otomatik_onay:true" in html  # onay satirinda tek tikla 'bir daha sorma'
    assert "plan-ayrinti" in html and 'k.style.display="none"' in html  # plan karti sade: ayrintilar kapali, otomatik onayda kart yok
    assert ".hesap-chip .hc{display:none}" in html and "function bas_harfler" in html  # hesap kutusu: yalniz yuvarlak bas harfler (BM)
    assert 'id="terminalDugme" style="width:100%"' not in html and 'id="ayarDugme" style="width:100%"' not in html


# ---------- Tailscale serve ile HTTPS ----------
def test_https_acilinca_serve_vekili_kurulur_baglanti_https_olur(sunucu, serve):
    app, sv, yerel, proje = sunucu
    port, d = ac(yerel, https=True)
    h = d["dinleyici"]["https"]
    assert h["calisiyor"] and h["url"] == f"https://{DNS}" and not h["hata"]
    assert d["dinleyici"]["baglantilar"][0].startswith(f"https://{DNS}/#t=")
    vekil = _cfg(serve)["Web"][f"{DNS}:443"]["Handlers"]["/"]["Proxy"]
    assert vekil == f"http://127.0.0.2:{port}"  # yalniz Tailscale (burada loopback) dinleyicisine; funnel/0.0.0.0 yok
    assert uzak.serve_acik_mi("127.0.0.2", port)


def test_https_uzerinden_gelen_host_ve_origin_kabul_edilir_baskalari_edilmez(sunucu, serve):
    app, sv, yerel, proje = sunucu
    port, _ = ac(yerel, https=True)
    # serve vekili Host'u portsuz ad olarak iletir; Origin https://<ad>
    st, d = uzak_istek(port, "GET", "/api/durum", host=DNS)
    assert st == 200 and d["baglanti"]["uzak"]
    st, d = uzak_istek(port, "POST", "/api/uzak", {"acik": False}, host=DNS, origin=f"https://{DNS}")
    assert st == 403 and "yalnizca bu bilgisayardan" in d["hata"]  # origin kabul; ama uzak ayari yine uzaktan degistirilemez (politika)
    assert uzak_istek(port, "POST", "/api/gorev-sil", {}, host=DNS, origin="https://kotu.example")[0] == 403  # yabanci Origin
    assert uzak_istek(port, "GET", "/api/durum", host="kotu.example")[0] == 403


def test_https_kapaliyken_portsuz_host_kabul_edilmez(sunucu, serve):
    app, sv, yerel, proje = sunucu
    port, _ = ac(yerel)
    assert uzak_istek(port, "GET", "/api/durum", host=DNS)[0] == 403


def test_https_kapatilinca_ve_uzak_erisim_kapaninca_yalniz_kendi_vekilimiz_kalkar(sunucu, serve):
    app, sv, yerel, proje = sunucu
    # kullanicinin baska bir serve ayari var: dokunulmamali
    serve.write_text(json.dumps({"Web": {"baska.ts.net:8443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:3000"}}}}}), encoding="utf-8")
    port, _ = ac(yerel, https=True)
    assert f"{DNS}:443" in _cfg(serve)["Web"]
    st, d = yerel("POST", "/api/uzak", {"https": False})
    assert st == 200 and not d["dinleyici"]["https"]["calisiyor"] and f"{DNS}:443" not in _cfg(serve)["Web"] and "baska.ts.net:8443" in _cfg(serve)["Web"]
    yerel("POST", "/api/uzak", {"https": True})
    assert f"{DNS}:443" in _cfg(serve)["Web"]
    yerel("POST", "/api/uzak", {"acik": False})
    assert f"{DNS}:443" not in _cfg(serve)["Web"] and "baska.ts.net:8443" in _cfg(serve)["Web"]


def test_https_tailscale_tarafinda_kapaliysa_anlasilir_hata_dinleyici_calismaya_devam_eder(sunucu, serve, ortam):
    app, sv, yerel, proje = sunucu
    ortam.setenv("SAHTE_TS_MOD", "serve-kapali")
    port, d = ac(yerel, https=True)
    h = d["dinleyici"]["https"]
    assert not h["calisiyor"] and "HTTPS Certificates" in h["hata"]
    assert d["dinleyici"]["calisiyor"] and not d["dinleyici"]["baglantilar"][0].startswith("https://")  # http baglantisi calismaya devam
    assert uzak_istek(port, "GET", "/api/durum")[0] == 200


def test_https_ayari_gecersiz_tip_reddedilir(sunucu):
    app, sv, yerel, proje = sunucu
    assert yerel("POST", "/api/uzak", {"https": "evet"})[0] == 400
