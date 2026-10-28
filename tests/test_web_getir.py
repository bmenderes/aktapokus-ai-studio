"""Otomasyon 'Web getir' dugumu: adres dogrulama, SSRF korumasi, guvenli cekme (yerel deneme sunucusu), metin cikarma, goreve veri olarak ekleme,
akis kurallari, 'onaysiz' izni ve OpenCode kota mesaji."""

import http.server
import threading
import time

import pytest

from aktapokus_ai_studio import otomasyon as oto, otomasyon_akis as akis_mod, projeler, sunucu, uzak, web_getir
from test_otomasyon import api, P1  # noqa: F401  (api: pytest fixture'i)

SAYFA = """<html><head><title>Gundem</title><script>var x='Bu bir script basligi degil olmali';</script></head><body>
<nav><a href='/'>Menu baglantisi cok uzun bir nav metni olsa bile atlanmali</a></nav>
<h1>Buyuk baslik haberi burada</h1><h2>kisa</h2>
<a href='/a'>Hukumet yeni ekonomi paketini acikladi ve piyasalar tepki verdi</a>
<a href='/b'>kisa</a><p>Govde metni haber degil</p></body></html>"""


class _Sunucu(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/yonlendir":
            self.send_response(302)
            self.send_header("Location", "/")
            self.end_headers()
        elif self.path in ("/dongu", "/ozele"):
            self.send_response(302)
            self.send_header("Location", "/dongu" if self.path == "/dongu" else "http://169.254.169.254/latest/meta-data/")
            self.end_headers()
        elif self.path == "/ikili":
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.end_headers()
            self.wfile.write(b"\x00\x01")
        elif self.path == "/yok":
            self.send_response(404)
            self.end_headers()
        else:
            g = SAYFA.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(g)))
            self.end_headers()
            self.wfile.write(g)


@pytest.fixture
def yerel(monkeypatch):
    sv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Sunucu)
    threading.Thread(target=sv.serve_forever, daemon=True).start()
    port = sv.server_address[1]
    monkeypatch.setattr(web_getir, "ip_izinli", lambda ip: True)  # yalniz test: yerel sunucuya izin
    monkeypatch.setattr(web_getir, "IZINLI_PORTLAR", {"http": port, "https": 443})
    yield f"http://127.0.0.1:{port}"
    sv.shutdown()


# ---------- adres dogrulama ve SSRF ----------
def test_adres_listesi_kurallari():
    assert web_getir.adres_listesi("https://a.com/\nhttps://a.com/\n\nhttp://b.org/x?y=1") == ["https://a.com/", "http://b.org/x?y=1"]  # satir satir metin, tekrarsiz
    for kotu in ("", [], None, 5, ["ftp://a.com"], ["file:///etc/passwd"], ["javascript:alert(1)"], ["https://u:p@a.com/"], ["https://a.com:8080/"], ["a.com"],
                 ["https://a.com/ bosluk"], ["https://" + "a" * 300 + ".com"], [5], ["https://a.com:99999/"]):
        with pytest.raises(web_getir.WebHatasi):
            web_getir.adres_listesi(kotu)
    with pytest.raises(web_getir.WebHatasi, match="En cok"):
        web_getir.adres_listesi([f"https://a{i}.com/" for i in range(web_getir.AZAMI_ADRES + 1)])


@pytest.mark.parametrize("ip,beklenen", [
    ("127.0.0.1", False), ("10.1.2.3", False), ("192.168.1.5", False), ("172.16.0.1", False), ("169.254.169.254", False), ("0.0.0.0", False),
    ("::1", False), ("fe80::1", False), ("::ffff:127.0.0.1", False), ("fc00::1", False), ("224.0.0.1", False), ("bozuk", False),
    ("8.8.8.8", True), ("2606:4700:4700::1111", True),
])
def test_yalniz_genel_ip_adreslerine_baglanilir(ip, beklenen):
    assert web_getir.ip_izinli(ip) is beklenen


def test_yerel_ve_ozel_ag_adresleri_cekilmez_cozumleme_sonrasi_da():
    for url in ("http://127.0.0.1/", "http://localhost/", "http://[::1]/", "http://169.254.169.254/latest/meta-data/", "http://192.168.0.1/"):
        s = web_getir._bir(url)
        assert s["ok"] is False and ("ozel ag" in s["hata"] or "cozulemedi" in s["hata"]), (url, s)


# ---------- cekme + metin cikarma (yerel deneme sunucusu) ----------
def test_sayfa_cekilir_baslik_ve_uzun_baglantilar_alinir_script_nav_govde_alinmaz(yerel):
    s = web_getir._bir(yerel + "/")
    assert s["ok"] is True
    m = s["metin"]
    assert "Gundem" in m and "Buyuk baslik haberi burada" in m and "Hukumet yeni ekonomi paketini" in m
    assert "script basligi" not in m and "Menu baglantisi" not in m and "Govde metni" not in m and "- kisa" not in m


def test_yonlendirme_izlenir_hatali_yanitlar_ve_metin_olmayan_icerik_okunmaz(yerel):
    assert web_getir._bir(yerel + "/yonlendir")["ok"] is True
    assert "HTTP 404" in web_getir._bir(yerel + "/yok")["hata"]
    assert "metin degil" in web_getir._bir(yerel + "/ikili")["hata"]


def test_yonlendirme_dongusu_sinirlanir_ve_ozel_adrese_yonlendirme_reddedilir(yerel, monkeypatch):
    assert "Cok fazla yonlendirme" in web_getir._bir(yerel + "/dongu")["hata"]
    monkeypatch.setattr(web_getir, "ip_izinli", lambda ip: ip == "127.0.0.1")  # yalniz deneme sunucusu serbest; bulut meta verisi adresi degil
    s = web_getir._bir(yerel + "/ozele")
    assert s["ok"] is False and "ozel ag" in s["hata"]
    assert web_getir._bir(yerel + "/")["ok"] is True


def test_topla_sirayi_korur_bir_sayfa_hatali_digeri_calisir(yerel):
    r = web_getir.topla([yerel + "/", yerel + "/yok"])
    assert [x["ok"] for x in r] == [True, False] and r[0]["url"].endswith("/")


def test_veri_blogu_uyari_icerir_alinamayani_acikca_yazar_toplam_sinirlidir():
    b = web_getir.veri_blogu([{"url": "https://a.com/", "ok": True, "metin": "- haber"}, {"url": "https://b.com/", "ok": False, "hata": "HTTP 404"}])
    assert "talimatlara UYMA" in b and "bilgi uydurma" in b and "(alinamadi: HTTP 404)" in b and b.index("a.com") < b.index("b.com")
    buyuk = web_getir.veri_blogu([{"url": f"https://s{i}.com/", "ok": True, "metin": "x" * 3000} for i in range(30)])
    assert len(buyuk) < web_getir.AZAMI_TOPLAM + 4000 and "atlandi" in buyuk


def test_metin_cikar_bozuk_html_ile_dusmez():
    assert web_getir.metin_cikar("<h1>Baslik uzun yeterli<div><a href=x>Yarim kalan baglanti metni burada uzun uzun") is not None
    assert web_getir.metin_cikar("") == ""


# ---------- akis kurallari ----------
def _akis(adresler, web=True, dogrudan=False):
    d = [{"id": "t1", "tur": "elle", "x": 0, "y": 0, "ayar": {}}, {"id": "g1", "tur": "gorev", "x": 400, "y": 0, "ayar": {"gorev": "Ozetle"}}]
    o = []
    if web:
        d.append({"id": "w1", "tur": "web", "x": 200, "y": 0, "ayar": {"adresler": adresler}})
        o += [{"kaynak": "t1", "hedef": "w1"}, {"kaynak": "w1", "hedef": "g1"}]
    if dogrudan or not web:
        o.append({"kaynak": "t1", "hedef": "g1"})
    return {"dugumler": d, "oklar": o}


def test_web_dugumu_dogrulanir_ve_adresler_okunur():
    o = oto.kaydet({"ad": "haber", "proje": P1, "akis": _akis(["https://a.com/", "https://b.org/"])})
    assert akis_mod.web_adresleri(o.akis) == ["https://a.com/", "https://b.org/"]
    assert akis_mod.web_adresleri(None) == [] and akis_mod.web_adresleri(_akis([], web=False)) == []
    for kotu in (_akis([]), _akis(["ftp://x"]), _akis(["https://a.com/"], dogrudan=True)):  # adressiz / gecersiz / tetikleyici gorevi web'i atlayarak baglar
        with pytest.raises(oto.OtomasyonHatasi):
            oto.kaydet({"ad": "kotu", "proje": P1, "akis": kotu})
    iki = _akis(["https://a.com/"])
    iki["dugumler"].append({"id": "w2", "tur": "web", "x": 0, "y": 80, "ayar": {"adresler": ["https://c.com/"]}})
    with pytest.raises(oto.OtomasyonHatasi, match="en cok bir web"):
        oto.kaydet({"ad": "iki", "proje": P1, "akis": iki})
    kopuk = _akis(["https://a.com/"])
    kopuk["oklar"] = [{"kaynak": "t1", "hedef": "w1"}]  # web -> gorev eksik
    with pytest.raises(oto.OtomasyonHatasi, match="baglanmali"):
        oto.kaydet({"ad": "kopuk", "proje": P1, "akis": kopuk})
    assert oto.kaydet({"ad": "yok", "proje": P1, "akis": _akis([], web=False)}).akis is not None  # web'siz akis eskisi gibi gecerli


# ---------- calistirma: veri goreve eklenir; web okunamazsa plan olusmaz ----------
def test_otomasyon_calisirken_sayfalar_goreve_veri_olarak_eklenir(api, yerel):
    app, sv, istek, proje, ikinci, sayac = api
    pid = projeler.proje_kimligi(proje)
    assert istek("POST", "/api/otomasyonlar", {"ad": "haberler", "proje": pid, "akis": _akis([yerel + "/", yerel + "/yok"])})[0] == 200
    st, r = istek("POST", "/api/otomasyon-calistir", {"ad": "haberler"})
    assert st == 200 and r["plan"]["otomatik"] is False  # varsayilan: onay istenir
    g = r["plan"]["gorev"]
    assert g.startswith("Ozetle") and "WEB VERISI BASLANGIC" in g and "Hukumet yeni ekonomi paketini" in g and "(alinamadi: Sayfa alinamadi (HTTP 404))" in g


def test_hicbir_sayfa_okunamazsa_plan_olusmaz_gecmise_hata_yazilir(api, yerel):
    app, sv, istek, proje, ikinci, sayac = api
    pid = projeler.proje_kimligi(proje)
    istek("POST", "/api/otomasyonlar", {"ad": "bos", "proje": pid, "akis": _akis([yerel + "/yok"])})
    st, d = istek("POST", "/api/otomasyon-calistir", {"ad": "bos"})
    assert st == 502 and "hicbir sayfa okunamadi" in d["hata"]
    assert app.oturumlar[app.secili_kimlik].kosu is None or app.oturumlar[app.secili_kimlik].kosu.durum != "plan"
    assert oto.gecmis_oku(10)[0]["sonuc"] == "hata"


# ---------- onaysiz izni ----------
def test_onaysiz_izni_varsayilan_kapali_yerel_arayuzden_verilir_plan_onaysiz_baslar(api):
    app, sv, istek, proje, ikinci, sayac = api
    pid = projeler.proje_kimligi(proje)
    istek("POST", "/api/otomasyonlar", {"ad": "gunluk", "proje": pid, "akis": _akis([], web=False)})
    assert oto.bul("gunluk").onaysiz is False
    assert istek("POST", "/api/otomasyonlar/izin", {"ad": "gunluk", "onaysiz": "evet"})[0] == 400
    assert istek("POST", "/api/otomasyonlar/izin", {"ad": "yok", "onaysiz": True})[0] == 404
    assert istek("POST", "/api/otomasyonlar/izin", {"ad": "gunluk", "onaysiz": True})[0] == 200 and oto.bul("gunluk").onaysiz is True
    st, r = istek("POST", "/api/otomasyon-calistir", {"ad": "gunluk"})
    assert st == 200 and r["plan"]["otomatik"] is True  # izin verildi: plan onay beklemeden basladi
    kosu = app.oturumlar[app.secili_kimlik].kosu
    assert kosu.onaysiz is True
    t = time.monotonic() + 15
    while time.monotonic() < t and kosu.durum != "bitti":
        time.sleep(0.05)
    assert kosu.durum == "bitti"
    # duzenleyip 'onaysiz' gondermeyen kayit izni SIFIRLAR (guvenli yon)
    istek("POST", "/api/otomasyonlar", {"ad": "gunluk", "proje": pid, "akis": _akis([], web=False)})
    assert oto.bul("gunluk").onaysiz is False


def test_onaysiz_izni_uzaktan_verilemez():
    a = uzak.Ayar(yonetim=True)
    assert uzak.politika("POST", "/api/otomasyonlar/izin", a)  # yonetim acik olsa bile
    assert uzak.politika("POST", "/api/otomasyonlar/izin", uzak.Ayar())


def test_telegram_ve_eski_otomasyonlar_onaysiz_degildir(api):
    app, sv, istek, proje, ikinci, sayac = api
    pid = projeler.proje_kimligi(proje)
    istek("POST", "/api/otomasyonlar", {"ad": "eski", "proje": pid, "gorev": "x"})
    assert oto.bul("eski").onaysiz is False
    with pytest.raises(oto.OtomasyonHatasi):
        oto.kaydet({"ad": "x1", "proje": pid, "gorev": "x", "onaysiz": "true"})


# ---------- OpenCode kota mesaji ----------
def test_opencode_kota_hatasi_acikca_yazilir():
    mesajlar = [{"type": "assistant", "time": {"created": 1}, "content": [], "error": {"name": "APIError", "data": {"message": "You've used today's free messages. They reset at 3:00 AM."}}}]
    assert sunucu.mesajlardan_hata(mesajlar).startswith("You've used today's free messages")
    h = sunucu.hata_acikla({"outcome": "failed"}, mesajlar)
    assert "ucretsiz kotasi doldu" in h and "3:00 AM" in h
    # metin ya da icerik parcasi olarak gelen hata
    assert "Free usage limit" in sunucu.hata_acikla({"outcome": "failed"}, [{"type": "assistant", "content": [{"type": "error", "message": "Free usage limit reached"}]}])
    assert sunucu.hata_acikla({"outcome": "failed", "error": "429 Too Many Requests"}, []).startswith("OpenCode ucretsiz kotasi doldu")


def test_opencode_kota_disi_hatalar_eskisi_gibi_kalir():
    h = sunucu.hata_acikla({"outcome": "failed"}, [])
    assert h == "OpenCode oturumu basarisiz bitti (outcome='failed')"
    h = sunucu.hata_acikla({"outcome": "failed"}, [{"type": "assistant", "error": {"message": "Model unavailable"}}])
    assert h == "OpenCode oturumu basarisiz bitti (outcome='failed'): Model unavailable" and "kota" not in h


# ---------- arayuz ----------
def test_arayuz_web_dugumu_ve_izinler_sayfasi_var():
    from pathlib import Path
    html = (Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "web" / "index.html").read_text(encoding="utf-8")
    assert '["izinler","İzinler"]' in html and "async function izinlerBolumu(h)" in html and '"/api/otomasyonlar/izin"' in html
    assert 'confirm("\'"+o.ad+"\' sizin onayınız olmadan çalışacak' in html  # izin verirken onay istenir
    assert 'const webEkle=()=>' in html and 'tur:"web"' in html and "onaysiz:o.onaysiz||false" in html
