"""Gorev akisi secenekleri: planin otomatik onaylanmasi (otomasyon/issue ASLA), testin (dogrulama) atlanmasi ve calisirken iptali."""

import threading
import time

import pytest

from aktapokus_ai_studio import config, pipeline, projeler
from aktapokus_ai_studio import otomasyon as oto
from aktapokus_ai_studio.arayuz import ArayuzSunucusu, Uygulama
from aktapokus_ai_studio.config import AyarHatasi, VARSAYILAN_AYAR, ayar_coz
from conftest import SahteCalistirici, sonuc
from test_arayuz import Istemci, bekle
from test_uzak import ac, sunucu as uzak_sunucu, uzak_istek, ortam  # noqa: F401  (pytest fixture'lari)


BAYRAK = {"engelle": False}


class BloklananTest(SahteCalistirici):
    """'test' rolu durdur() cagrilana kadar bekler (calisan CLI sureci gibi)."""

    def __init__(self, senaryo, bloke):
        super().__init__(senaryo)
        self.bloke = bloke

    def durdur(self):
        self.bloke.set()
        return True


@pytest.fixture
def api(proje):
    ornekler = []
    bloke = threading.Event()

    def senaryo_test(k, i, n):
        if BAYRAK["engelle"]:
            bloke.wait(10)
            return sonuc("", ok=False, hata="durduruldu")
        return sonuc("SONUC: BASARILI")

    BAYRAK["engelle"] = False

    def uret(ad):
        c = BloklananTest({"kodcu": lambda k, i, n: sonuc("x"), "test": senaryo_test}, bloke)
        ornekler.append(c)
        return c

    app = Uygulama(calistirici_uret=uret)
    sv = ArayuzSunucusu(app)
    sv.baslat()
    app.klasor_sec(str(proje))
    yield app, Istemci(sv), ornekler
    bloke.set()
    sv.kapat()


def roller(ornekler):
    return [c[0] for o in ornekler for c in o.cagrilar]


def ayarla(app, **alanlar):
    ayar = app.ayar_oku()
    ayar.update(alanlar)
    app.ayar_yaz(ayar)


def bitti(app):
    return bekle(lambda: app.kosu and app.kosu.durum == "bitti")


# ---------- ayar ----------
def test_ayar_alanlari_varsayilan_kapali_ve_dogrulanir():
    a = ayar_coz(VARSAYILAN_AYAR)
    assert a.otomatik_onay is False and a.testi_atla is False
    for alan in ("otomatik_onay", "testi_atla"):
        for kotu in ("evet", 1, None, []):
            v = dict(VARSAYILAN_AYAR, **{alan: kotu})
            with pytest.raises(AyarHatasi, match=alan):
                ayar_coz(v)


# ---------- otomatik onay ----------
def test_varsayilan_onay_ister_otomatik_onay_acikken_onay_beklemeden_baslar(api):
    app, istek, ornekler = api
    st, plan = istek("POST", "/api/gorev", {"gorev": "bir sey yap"})
    assert st == 200 and plan["otomatik"] is False
    time.sleep(1.0)
    assert app.kosu.durum == "plan" and roller(ornekler) == []  # onay yok -> hicbir sey calismaz
    istek("POST", f"/api/gorev/{plan['kosu']}/reddet", {})
    ayarla(app, otomatik_onay=True)
    st, plan = istek("POST", "/api/gorev", {"gorev": "bir sey yap"})
    assert plan["otomatik"] is True
    assert bitti(app) and roller(ornekler) == ["kodcu", "test"]


def test_otomasyon_gorevi_otomatik_onay_acikken_de_onay_bekler(api, proje):
    app, istek, ornekler = api
    ayarla(app, otomatik_onay=True)
    oto.kaydet({"ad": "gunluk", "proje": projeler.proje_kimligi(proje), "gorev": "rapor"})
    r = app.otomasyon_calistir("gunluk")
    assert r["plan"]["otomatik"] is False
    time.sleep(1.0)
    assert app.kosu.durum == "plan" and roller(ornekler) == []


def test_disaridan_gelen_metin_gorevi_otomatik_onaya_tabi_degil(api):
    app, istek, ornekler = api
    ayarla(app, otomatik_onay=True)
    plan = app.gorev_olustur("issue metni", otomatik_onay_izni=False)
    assert plan["otomatik"] is False
    time.sleep(0.8)
    assert app.kosu.durum == "plan" and roller(ornekler) == []


def test_uzaktan_otomatik_onay_degistirilemez(uzak_sunucu):
    app, sv, yerel, proje = uzak_sunucu
    port, _ = ac(yerel)
    ayar = uzak_istek(port, "GET", "/api/ayar")[1]
    ayar["otomatik_onay"] = True
    st, d = uzak_istek(port, "PUT", "/api/ayar", ayar)
    assert st == 403 and "otomatik_onay" in d["hata"] and not app.ayar_oku().get("otomatik_onay")
    assert yerel("PUT", "/api/ayar", ayar)[0] == 200  # yerelde serbest
    ayar["otomatik_onay"] = False
    assert uzak_istek(port, "PUT", "/api/ayar", ayar)[0] == 403  # kapatmak da uzaktan degisiklik sayilir (tutarli)


# ---------- test atlama ----------
def test_testsiz_gorev_test_adimini_calistirmaz(api):
    app, istek, ornekler = api
    st, plan = istek("POST", "/api/gorev", {"gorev": "x", "testsiz": True})
    assert plan["testsiz"] is True
    istek("POST", f"/api/gorev/{plan['kosu']}/onayla", {})
    assert bitti(app) and roller(ornekler) == ["kodcu"]


def test_varsayilan_testi_atla_ve_onay_aninda_gorev_basina_degistirme(api):
    app, istek, ornekler = api
    ayarla(app, testi_atla=True)
    st, plan = istek("POST", "/api/gorev", {"gorev": "x"})
    assert plan["testsiz"] is True  # proje varsayilani
    istek("POST", f"/api/gorev/{plan['kosu']}/onayla", {"testsiz": False})  # bu gorevde testi geri ac
    assert bitti(app) and roller(ornekler) == ["kodcu", "test"]
    st, plan = istek("POST", "/api/gorev", {"gorev": "y", "testsiz": False})
    assert plan["testsiz"] is False  # acik istek varsayilani ezer


def test_calisirken_test_iptal_edilir_hata_sayilmaz_akis_devam_eder(api):
    app, istek, ornekler = api
    BAYRAK["engelle"] = True
    st, plan = istek("POST", "/api/gorev", {"gorev": "x"})
    istek("POST", f"/api/gorev/{plan['kosu']}/onayla", {})
    assert bekle(lambda: "test" in roller(ornekler))  # test adimi basladi ve bekliyor
    st, d = istek("POST", f"/api/gorev/{plan['kosu']}/testi-atla", {})
    assert st == 200 and d["durduruldu"] is True
    assert bitti(app)
    s = app.kosu.sonuc
    assert s.durum == "degisiklik_yok" and s.adimlar[-1].dogrulama == "atlandi"  # basarisiz DEGIL


def test_testi_atla_calismayan_gorevde_409(api):
    app, istek, ornekler = api
    assert istek("POST", "/api/gorev/abcd1234/testi-atla", {})[0] == 404
    st, plan = istek("POST", "/api/gorev", {"gorev": "x"})
    assert istek("POST", f"/api/gorev/{plan['kosu']}/testi-atla", {})[0] == 409  # plan asamasi: calismiyor


# ---------- hat (pipeline) ----------
def test_hat_testi_atla_olayi_onceden_ayarliysa_test_rolu_hic_calismaz(proje):
    c = SahteCalistirici({"kodcu": lambda *a: sonuc("x"), "test": lambda *a: sonuc("SONUC: BASARISIZ")})
    olay = threading.Event()
    olay.set()
    s = pipeline.calistir_hat(proje, "g", ayar_coz(VARSAYILAN_AYAR), lambda ad: c, lambda q: True, testi_atla=olay)
    assert [x[0] for x in c.cagrilar] == ["kodcu"] and s.durum == "degisiklik_yok"  # BASARISIZ test calismadigi icin duzeltme turu da yok


def test_hat_testsiz_dogrulama_rollerini_eler(proje):
    c = SahteCalistirici({"kodcu": lambda *a: sonuc("x"), "test": lambda *a: sonuc("SONUC: BASARISIZ")})
    mesajlar = []
    s = pipeline.calistir_hat(proje, "g", ayar_coz(VARSAYILAN_AYAR), lambda ad: c, lambda q: True, mesajlar.append, testsiz=True)
    assert [x[0] for x in c.cagrilar] == ["kodcu"] and s.durum == "degisiklik_yok" and any("atlandi" in m for m in mesajlar)


# ---------- arayuz ----------
def test_durum_ayar_ozetinde_otomatik_onay_ve_testi_atla_gorunur(api):
    app, istek, ornekler = api
    assert istek("GET", "/api/durum")[1]["ayar"]["testi_atla"] is False
    ayarla(app, testi_atla=True, otomatik_onay=True)
    a = istek("GET", "/api/durum")[1]["ayar"]
    assert a["testi_atla"] is True and a["otomatik_onay"] is True


def test_arayuz_kodu_otomatik_onayda_durumu_ezmez_ve_test_kapsulu_tiklanir():
    from pathlib import Path

    html = (Path(__file__).parent.parent / "aktapokus_ai_studio" / "web" / "index.html").read_text(encoding="utf-8")
    # gercek hata: otomatik onayli gorev sunucu cevabindan once basladigi icin arayuz 'plan onayinizi bekliyor' yazip kaliyordu
    assert '(S.kosu&&S.kosu.kimlik===p.kosu)?S.kosu.durum:(p.otomatik?"calisiyor":"plan")' in html
    assert "async function testiAcKapat" in html and "testiAcKapat()" in html and 'ay.testi_atla=!ay.testi_atla' in html
    assert 'x.dogrulama&&S.ayar.testi_atla' in html  # pasif gorunum


def test_gecmis_gorev_ozet_karti_degil_konusma_olarak_yeniden_oynatilir():
    """Gecmis gorev canli gorevle ayni akis ekraninda ayni cizimle acilir; 'Gecmis gorev' ozet karti yok (ust uste yigilan kartlar da yok)."""
    from pathlib import Path

    html = (Path(__file__).parent.parent / "aktapokus_ai_studio" / "web" / "index.html").read_text(encoding="utf-8")
    assert 'text:"Geçmiş görev"' not in html and "gecmis-karti" not in html
    assert 'for(const o of r.olaylar||[])' in html and "olayIsle(Object.assign({},o,{proje:S.projeId}))" in html
    for ad in ("gorevMenusu", "gorevSatiri", "menuKapat", "acilisParametreleri"):
        assert f"function {ad}" in html or f"async function {ad}" in html
    for yol in ("/gorev-meta", "/gorev-sil", "/klasor-ac", "/claude-devam"):
        assert yol in html
    for etiket in ("Üste sabitle", "Okunmadı işaretle", "Yeniden adlandır", "Yeni görev olarak kopyala", "Arşive kaldır", "Sil", "Yeni pencere", "Dosya Gezgini", "VS Code", "Claude Code'da sürdür"):
        assert etiket in html
