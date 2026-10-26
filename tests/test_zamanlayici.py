"""Otomasyon Asama B: zamanlama dogrulamasi, planli an hesabi, zamanlayici kurallari (kacirilan geriye donuk calismaz, birikmez, tavan, atlama),
gercek uygulamada plan uretimi (onaysiz CALISMAZ)."""

import threading
import time
from datetime import datetime, timedelta

import pytest

from aktapokus_ai_studio import otomasyon as oto
from aktapokus_ai_studio import projeler
from aktapokus_ai_studio.arayuz import ArayuzSunucusu, Uygulama
from aktapokus_ai_studio.zamanlayici import Zamanlayici
from conftest import SahteCalistirici
from test_arayuz import _ikinci_proje
from test_otomasyon import P1, sablon

D = datetime
Z_ARALIK = {"tur": "aralik", "dakika": 60}
Z_GUNLUK = {"tur": "gunluk", "saat": "09:30"}
Z_HAFTALIK = {"tur": "haftalik", "saat": "09:30", "gunler": [0, 4]}  # pazartesi + cuma


def zamanli(zamanlama=Z_ARALIK, **ek):
    return sablon(ad=ek.pop("ad", "zamanli-is"), tur="zamanli", zamanlama=zamanlama, **ek)


# ---------- dogrulama ----------
@pytest.mark.parametrize("kotu", [
    None, "her gun", [], {}, {"tur": "ayda"},
    {"tur": "aralik"}, {"tur": "aralik", "dakika": 4}, {"tur": "aralik", "dakika": 0}, {"tur": "aralik", "dakika": -5},
    {"tur": "aralik", "dakika": oto.AZAMI_ARALIK_DK + 1}, {"tur": "aralik", "dakika": "60"}, {"tur": "aralik", "dakika": 60.5}, {"tur": "aralik", "dakika": True},
    {"tur": "gunluk"}, {"tur": "gunluk", "saat": "24:00"}, {"tur": "gunluk", "saat": "9:30"}, {"tur": "gunluk", "saat": "09:60"}, {"tur": "gunluk", "saat": "09:30\n"}, {"tur": "gunluk", "saat": 930},
    {"tur": "haftalik", "saat": "09:30"}, {"tur": "haftalik", "saat": "09:30", "gunler": []}, {"tur": "haftalik", "saat": "09:30", "gunler": [7]},
    {"tur": "haftalik", "saat": "09:30", "gunler": [-1]}, {"tur": "haftalik", "saat": "09:30", "gunler": ["0"]}, {"tur": "haftalik", "saat": "09:30", "gunler": [True]},
    {"tur": "haftalik", "saat": "09:30", "gunler": 3},
], ids=lambda z: str(z)[:40])
def test_gecersiz_zamanlama_reddedilir(kotu):
    with pytest.raises(oto.OtomasyonHatasi):
        oto.kaydet(zamanli(kotu))
    assert oto.yukle() == {}


def test_zamanlama_yalniz_zamanli_turde_ve_zamanli_tur_zamanlamasiz_olmaz():
    with pytest.raises(oto.OtomasyonHatasi):
        oto.kaydet(sablon(zamanlama=Z_ARALIK))
    with pytest.raises(oto.OtomasyonHatasi):
        oto.kaydet(sablon(tur="zamanli"))
    assert oto.kaydet(sablon(zamanlama=None)).zamanlama is None


def test_gecerli_zamanlama_normallesir_ve_fazladan_alan_saklanmaz():
    o = oto.kaydet(zamanli({"tur": "haftalik", "saat": "07:05", "gunler": [4, 0, 4], "x": "gizli"}))
    assert o.zamanlama == {"tur": "haftalik", "saat": "07:05", "gunler": [0, 4]}
    assert oto.kaydet(zamanli({"tur": "aralik", "dakika": 5, "saat": "99"}, ad="b")).zamanlama == {"tur": "aralik", "dakika": 5}
    assert oto.yukle()["zamanli-is"].zamanlama == o.zamanlama and oto.yukle()["zamanli-is"].tur == "zamanli"  # diskten de ayni


# ---------- planli an ----------
def test_sonraki_aralik_gunluk_haftalik_sinirlari():
    assert oto.sonraki(Z_ARALIK, D(2026, 10, 26, 10, 0)) == D(2026, 10, 26, 11, 0)
    assert oto.sonraki(Z_GUNLUK, D(2026, 10, 26, 9, 29, 59)) == D(2026, 10, 26, 9, 30)
    assert oto.sonraki(Z_GUNLUK, D(2026, 10, 26, 9, 30)) == D(2026, 10, 27, 9, 30)  # tam o an: SONRAKI (ayni an iki kez tetiklenmez)
    assert oto.sonraki(Z_GUNLUK, D(2026, 12, 31, 23, 0)) == D(2027, 1, 1, 9, 30)  # yil donumu
    assert oto.sonraki(Z_HAFTALIK, D(2026, 10, 26, 10, 0)) == D(2026, 10, 30, 9, 30)  # pzt 10:00 -> cuma
    assert oto.sonraki(Z_HAFTALIK, D(2026, 10, 30, 10, 0)) == D(2026, 11, 2, 9, 30)  # cuma gecti -> sonraki pazartesi (ay donumu)
    assert oto.sonraki(Z_HAFTALIK, D(2026, 10, 26, 8, 0)) == D(2026, 10, 26, 9, 30)  # ayni gun, saat gelmedi
    assert oto.sonraki({"tur": "haftalik", "saat": "09:30", "gunler": [2]}, D(2026, 10, 28, 9, 30)) == D(2026, 11, 4, 9, 30)  # tek gun: bir hafta sonra


# ---------- zamanlayici ----------
class Saat:
    def __init__(self, an):
        self.an = an

    def __call__(self):
        return self.an

    def ilerle(self, **kw):
        self.an += timedelta(**kw)


@pytest.fixture
def kur(monkeypatch):
    cagrilar = []
    saat = Saat(D(2026, 10, 26, 8, 0, 0))

    class SahteDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return saat.an

    monkeypatch.setattr(oto, "datetime", SahteDT)  # kaydet() 'simdi'yi sahte saatten alir

    def calistir(ad):
        cagrilar.append(ad)
        oto.gecmis_ekle(ad, "plan-olustu", tetikleyen="zamanlayici", zaman=saat().strftime(oto.ZAMAN_BICIMI))  # gercek otomasyon_calistir gibi

    def uret(**kw):
        return Zamanlayici(calistir, saat=saat, **kw)

    return uret, saat, cagrilar


def kaydet_simdi(saat, **ek):
    """Kayit, durum 'gercek simdi' ile baslar; testte sahte saate esitle."""
    o = oto.kaydet(zamanli(**ek))
    oto.durum_yaz(o.ad, saat())
    return o


def test_zamani_gelmeyen_calismaz_gelen_bir_kez_calisir_ve_tekrarlanmaz(kur):
    uret, saat, cagrilar = kur
    z = uret()
    kaydet_simdi(saat)
    saat.ilerle(minutes=59)
    assert z.tikla() == [] and cagrilar == []
    saat.ilerle(minutes=1)
    assert z.tikla() == [("zamanli-is", "plan-olustu")] and cagrilar == ["zamanli-is"]
    assert z.tikla() == [] and cagrilar == ["zamanli-is"]  # ayni an tekrar calismaz
    saat.ilerle(minutes=60)
    z.tikla()
    assert cagrilar == ["zamanli-is", "zamanli-is"]  # bir sonraki aralik simdiden sayilir


def test_kapaliyken_kacan_zamanlar_geriye_donuk_calismaz_tek_kacirildi_kaydi_yazar(kur):
    uret, saat, cagrilar = kur
    z = uret()
    kaydet_simdi(saat)
    saat.ilerle(hours=5)  # uygulama kapaliydi: 5 aralik gecti
    assert z.tikla() == [("zamanli-is", "kacirildi")] and cagrilar == []
    g = oto.gecmis_oku(10)
    assert len(g) == 1 and g[0]["sonuc"] == "kacirildi" and g[0]["tetikleyen"] == "zamanlayici" and g[0]["proje"] == P1
    assert z.tikla() == [] and len(oto.gecmis_oku(10)) == 1  # birikmedi, tekrar yazmadi
    saat.ilerle(minutes=60)
    assert z.tikla() == [("zamanli-is", "plan-olustu")]  # sonraki planli an normal calisir


def test_tolerans_icindeki_gecikme_calisir_disindaki_kacirilir(kur):
    uret, saat, cagrilar = kur
    z = uret(tolerans_dk=10)
    kaydet_simdi(saat, zamanlama=Z_GUNLUK)
    saat.an = D(2026, 10, 26, 9, 39, 59)  # 09:30 + 9:59
    assert z.tikla() == [("zamanli-is", "plan-olustu")]
    kaydet_simdi(saat, zamanlama={"tur": "gunluk", "saat": "09:00"}, ad="ikinci")
    saat.an = D(2026, 10, 27, 9, 10, 1)  # 09:00 + 10:01
    cagrilar.clear()
    sonuc = dict(z.tikla())
    assert sonuc["ikinci"] == "kacirildi" and "ikinci" not in cagrilar


def test_kapali_ve_sablon_turu_otomasyonlar_calismaz_yeniden_acilinca_gecmise_donuk_kacirildi_uretmez(kur):
    uret, saat, cagrilar = kur
    z = uret()
    kaydet_simdi(saat, acik=False)
    oto.kaydet(sablon(ad="duz"))
    saat.ilerle(hours=3)
    assert z.tikla() == [] and cagrilar == [] and oto.gecmis_oku(5) == []
    oto.kaydet(zamanli(acik=True))  # yeniden acildi: zaman simdiden sayilir
    assert z.tikla() == [] and cagrilar == []


def test_zamanlama_degisince_bekleyen_eski_an_sayilmaz(kur):
    uret, saat, cagrilar = kur
    z = uret()
    kaydet_simdi(saat)
    saat.ilerle(hours=2)
    oto.kaydet(zamanli({"tur": "aralik", "dakika": 90}))  # duzenleme: durum gercek 'simdi'ye sifirlanir (sahte saat 2 saat ileride)
    sonuc = z.tikla()
    assert ("zamanli-is", "plan-olustu") not in sonuc and cagrilar == []


def test_gunluk_tavan_asilinca_atlanir(kur):
    uret, saat, cagrilar = kur
    z = uret(gunluk_tavan=2)
    for ad in ("a", "b", "c"):
        kaydet_simdi(saat, ad=ad)
    saat.ilerle(hours=1)
    sonuc = dict(z.tikla())
    assert sorted(sonuc.values()) == ["atlandi", "plan-olustu", "plan-olustu"] and len(cagrilar) == 2


def test_tavan_gecmisten_sayilir_ve_gun_degisince_sifirlanir(kur):
    uret, saat, cagrilar = kur
    z = uret(gunluk_tavan=2)
    kaydet_simdi(saat, ad="a")
    bugun = saat().strftime("%Y-%m-%d")
    for i in range(2):
        oto.gecmis_ekle("baska", "plan-olustu", tetikleyen="zamanlayici", zaman=f"{bugun} 07:0{i}:00")
    oto.gecmis_ekle("baska", "plan-olustu", tetikleyen="elle", zaman=f"{bugun} 07:30:00")  # elle yapilan sayilmaz
    saat.ilerle(hours=1)
    assert z.tikla() == [("a", "atlandi")] and cagrilar == []
    assert "tavan" in oto.gecmis_oku(1)[0]["neden"]
    saat.ilerle(days=1)  # ertesi gun tavan sifir
    assert z.tikla() == [("a", "kacirildi")]  # gun degisti: tavan sifir ama 1 gunluk bosluk geriye donuk calismaz
    saat.ilerle(minutes=60)
    assert z.tikla() == [("a", "plan-olustu")] and cagrilar == ["a"]


def test_durum_calistirmadan_once_yazilir_calistirma_cokse_bile_tekrar_denenmez(kur):
    uret, saat, cagrilar = kur

    def patlayan(ad):
        cagrilar.append(ad)
        raise RuntimeError("bozuk")

    z = Zamanlayici(patlayan, saat=saat)
    kaydet_simdi(saat)
    saat.ilerle(hours=1)
    assert z.tikla() == [("zamanli-is", "atlandi/hata")]
    assert z.tikla() == [] and cagrilar == ["zamanli-is"]
    g = oto.gecmis_oku(5)
    assert g[0]["sonuc"] == "hata" and "RuntimeError" in g[0]["neden"] and g[0]["tetikleyen"] == "zamanlayici"


def test_uygulama_hatasi_ikinci_kez_kayda_yazilmaz(kur):
    from aktapokus_ai_studio.arayuz import UygulamaHatasi
    uret, saat, _ = kur

    def atlayan(ad):
        oto.gecmis_ekle(ad, "atlandi", "projede gorev var", "zamanlayici")
        raise UygulamaHatasi("Atlandi", 409)

    z = Zamanlayici(atlayan, saat=saat)
    kaydet_simdi(saat)
    saat.ilerle(hours=1)
    z.tikla()
    assert [k["sonuc"] for k in oto.gecmis_oku(5)] == ["atlandi"]


def test_bozuk_durum_dosyasi_ve_bozuk_olusturma_zamani_zamanlayiciyi_dusurmez(kur):
    uret, saat, cagrilar = kur
    z = uret()
    kaydet_simdi(saat)
    oto.durum_yolu().write_text("{bozuk", encoding="utf-8")
    saat.ilerle(hours=1)
    z.tikla()  # durum yok -> olusturma zamanindan (gercek saat, 'gelecek') hesaplanir; hata atmaz
    oto.durum_yolu().write_text('{"zamanli-is": "dun degil"}', encoding="utf-8")
    z.tikla()


def test_silinen_otomasyonun_durumu_temizlenir(kur):
    uret, saat, _ = kur
    kaydet_simdi(saat)
    assert oto.durum_oku("zamanli-is") is not None
    oto.sil("zamanli-is")
    assert oto.durum_oku("zamanli-is") is None


def test_baslat_durdur_is_parcacigi_calisir_ve_kapanir(kur):
    uret, saat, cagrilar = kur
    z = uret(tik_sn=0.05)
    kaydet_simdi(saat)
    saat.ilerle(hours=1)
    z.baslat()
    z.baslat()  # ikinci cagri ikinci is parcacigi acmaz
    for _ in range(100):
        if cagrilar:
            break
        time.sleep(0.05)
    z.durdur()
    assert cagrilar == ["zamanli-is"]
    assert not [t for t in threading.enumerate() if t.name == "otomasyon-zamanlayici"]


# ---------- gercek uygulama ----------
@pytest.fixture
def api(proje, tmp_path):
    cagrilar = []

    def uret(ad):
        cagrilar.append(ad)
        return SahteCalistirici({"kodcu": lambda k, i, n: __import__("conftest").sonuc("x"), "test": lambda k, i, n: __import__("conftest").sonuc("SONUC: BASARILI")})

    app = Uygulama(calistirici_uret=uret)
    sv = ArayuzSunucusu(app)
    sv.baslat()
    app.klasor_sec(str(proje))
    ikinci = _ikinci_proje(tmp_path)
    app.proje_ac(str(ikinci), sec=False)
    yield app, sv, proje, ikinci, cagrilar
    sv.kapat()


def test_gercek_uygulamada_zamanlayici_plan_uretir_onaysiz_calistirmaz_secili_projeyi_degistirmez(api):
    app, sv, proje, ikinci, cagrilar = api
    b = projeler.proje_kimligi(ikinci)
    a_id = app.secili_kimlik
    oto.kaydet(zamanli(proje=b, gorev="{proje} zamanli ({tarih})"))
    saat = Saat(D.now())
    z = Zamanlayici(lambda ad: app.otomasyon_calistir(ad, "zamanlayici", yalniz_acik=True), saat=saat)
    saat.ilerle(hours=1)
    assert z.tikla() == [("zamanli-is", "plan-olustu")]
    g = oto.gecmis_oku(1)[0]
    assert g["sonuc"] == "plan-olustu" and g["tetikleyen"] == "zamanlayici" and g["proje"] == b
    assert app.oturumlar[b].kosu.durum == "plan" and app.secili_kimlik == a_id
    time.sleep(1.5)
    assert app.oturumlar[b].kosu.durum == "plan" and cagrilar == []  # ONAY YOK: hicbir calistirici baslamadi


def test_gercek_uygulamada_projede_gorev_varsa_zamanlayici_atlar_ve_birikmez(api):
    app, sv, proje, ikinci, cagrilar = api
    b = projeler.proje_kimligi(ikinci)
    oto.kaydet(zamanli(proje=b))
    saat = Saat(D.now())
    z = Zamanlayici(lambda ad: app.otomasyon_calistir(ad, "zamanlayici", yalniz_acik=True), saat=saat)
    saat.ilerle(hours=1)
    z.tikla()  # birinci plan olustu, onay bekliyor
    plan1 = app.oturumlar[b].kosu
    saat.ilerle(hours=1)
    assert z.tikla() == [("zamanli-is", "atlandi/hata")]
    assert app.oturumlar[b].kosu is plan1  # ikinci plan YIGILMADI
    assert [k["sonuc"] for k in oto.gecmis_oku(3)] == ["atlandi", "plan-olustu"]


def test_sunucu_zamanlayiciyi_yalniz_istenince_baslatir_ve_kapatirken_durdurur(proje):
    app = Uygulama(calistirici_uret=lambda ad: SahteCalistirici({}))
    sv = ArayuzSunucusu(app)
    sv.baslat()
    assert sv.zamanlayici is None  # testlerde/varsayilanda kendiliginden calismaz
    sv.zamanlayici_baslat()
    ilk = sv.zamanlayici
    sv.zamanlayici_baslat()
    assert sv.zamanlayici is ilk
    sv.kapat()
    assert not [t for t in threading.enumerate() if t.name == "otomasyon-zamanlayici"]


def test_elle_yapilan_planlar_zamanlayici_tavanina_sayilmaz(kur):
    uret, saat, cagrilar = kur
    z = uret(gunluk_tavan=2)
    kaydet_simdi(saat, ad="a")
    bugun = saat().strftime("%Y-%m-%d")
    oto.gecmis_ekle("baska", "plan-olustu", tetikleyen="zamanlayici", zaman=f"{bugun} 07:00:00")
    for i in range(5):
        oto.gecmis_ekle("baska", "plan-olustu", tetikleyen="elle", zaman=f"{bugun} 07:1{i}:00")
    saat.ilerle(hours=1)
    assert z.tikla() == [("a", "plan-olustu")] and cagrilar == ["a"]  # 1 zamanlayici + 5 elle: tavan (2) dolmadi
