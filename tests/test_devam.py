"""Kapanista gorev kurtarma (devam.py): kayit yazma/silme, dogrulama, 'yarim kaldi' sorusu; devam = yeni PLAN (onay yine sart), geri al, yok say."""

import json
import threading

import pytest

from aktapokus_ai_studio import devam
from aktapokus_ai_studio.config import ayar_yolu
from aktapokus_ai_studio.arayuz import Uygulama, UygulamaHatasi
from conftest import SahteCalistirici, sonuc
from test_arayuz import BASARILI, bekle, klasor_sec, kur  # noqa: F401  (kur: pytest fixture'i)

SHA = "a" * 40


# ---------- devam.py ----------
def test_yaz_oku_sil_ve_bos_kayit_dosyayi_siler(tmp_path):
    devam.yaz(tmp_path, {"kimlik": "ab12", "gorev": "x ekle", "durum": "calisiyor", "testsiz": False, "once": SHA}, [{"gorev": "sonra", "testsiz": None}])
    d = devam.oku(tmp_path)
    assert d["kosu"] == {"kimlik": "ab12", "gorev": "x ekle", "durum": "calisiyor", "testsiz": False, "once": SHA} and d["kuyruk"] == [{"gorev": "sonra", "testsiz": None}]
    assert devam.yol(tmp_path).parent.name == ".aktapokus"
    devam.yaz(tmp_path, None, [])
    assert not devam.yol(tmp_path).exists() and devam.oku(tmp_path) is None
    devam.sil(tmp_path)  # olmayan dosya hata vermez


@pytest.mark.parametrize("kotu", [
    "{bozuk", "[]", "5", json.dumps({"kosu": {"durum": "bitti", "gorev": "x"}}), json.dumps({"kosu": {"durum": "calisiyor", "gorev": "  "}}),
    json.dumps({"kosu": {"durum": "calisiyor", "gorev": "x" * (devam.AZAMI_GOREV + 1)}}), json.dumps({"kosu": {"durum": "calisiyor", "gorev": "a\x00b"}}),
    json.dumps({"kosu": "x"}), json.dumps({"kuyruk": [{"gorev": 5}, "x", {}]}), json.dumps({"kuyruk": "x"}), json.dumps({}),
])
def test_bozuk_ya_da_yabanci_kayit_yok_sayilir(tmp_path, kotu):
    devam.yol(tmp_path).parent.mkdir()
    devam.yol(tmp_path).write_text(kotu, encoding="utf-8")
    assert devam.oku(tmp_path) is None


def test_gecersiz_commit_adi_dusurulur_ve_kuyruk_sinirlanir(tmp_path):
    devam.yaz(tmp_path, {"kimlik": "k", "gorev": "x", "durum": "karar-bekliyor", "testsiz": True, "once": "--upload-pack=calistir"}, [{"gorev": f"g{i}"} for i in range(30)])
    d = devam.oku(tmp_path)
    assert d["kosu"]["once"] is None and len(d["kuyruk"]) == devam.AZAMI_KUYRUK and d["kosu"]["testsiz"] is True


# ---------- uygulama akisi ----------
class Engelleyici:
    """kodcu rolu: dosya yazar, sonra serbest birakilana kadar bekler (uygulamanin 'cokmesi' simule edilir)."""

    def __init__(self):
        self.serbest = threading.Event()
        self.basladi = threading.Event()

    def kodcu(self, k, i, n):
        (k / "yeni.txt").write_text("yarim\n", encoding="utf-8")
        self.basladi.set()
        self.serbest.wait(15)
        return sonuc("yazildi")


def _yeni_uygulama(proje, senaryo=None):
    sahte = SahteCalistirici(senaryo or {"kodcu": lambda k, i, n: sonuc("x"), "test": BASARILI})
    app = Uygulama(calistirici_uret=lambda ad: sahte)
    app.klasor_sec(str(proje))
    return app


def test_plan_bekleyen_gorev_ve_kuyruk_diske_yazilir_ve_bitince_silinir(kur):
    eng = Engelleyici()
    app, sv, api, _ = kur({"kodcu": eng.kodcu, "test": BASARILI})
    klasor_sec(api, kur.proje)
    plan = api("POST", "/api/gorev", {"gorev": "ilk gorev"})[1]
    assert devam.oku(kur.proje)["kosu"]["durum"] == "plan"
    api("POST", f"/api/gorev/{plan['kosu']}/onayla", {})
    assert eng.basladi.wait(10) and bekle(lambda: devam.oku(kur.proje) and devam.oku(kur.proje)["kosu"]["once"])
    assert api("POST", "/api/gorev", {"gorev": "ikinci", "kuyruga": True})[0] == 200
    d = devam.oku(kur.proje)
    assert d["kosu"]["durum"] == "calisiyor" and d["kosu"]["gorev"] == "ilk gorev" and [k["gorev"] for k in d["kuyruk"]] == ["ikinci"]
    assert api("POST", "/api/kuyruk/sil", {"sira": 0})[0] == 200 and devam.oku(kur.proje)["kuyruk"] == []
    eng.serbest.set()
    assert bekle(lambda: app.kosu.durum == "karar-bekliyor") and devam.oku(kur.proje)["kosu"]["durum"] == "karar-bekliyor"
    api("POST", f"/api/gorev/{plan['kosu']}/karar", {"korunsun": True})
    assert bekle(lambda: app.kosu.durum == "bitti" and not devam.yol(kur.proje).exists())


def test_reddedilen_plan_kaydi_siler(kur):
    app, sv, api, _ = kur()
    klasor_sec(api, kur.proje)
    plan = api("POST", "/api/gorev", {"gorev": "x"})[1]
    assert devam.yol(kur.proje).exists()
    api("POST", f"/api/gorev/{plan['kosu']}/reddet", {})
    assert not devam.yol(kur.proje).exists()


def test_yeniden_acilista_yarim_kaldi_sorulur_yok_say_siler(kur):
    eng = Engelleyici()
    app, sv, api, _ = kur({"kodcu": eng.kodcu, "test": BASARILI})
    klasor_sec(api, kur.proje)
    plan = api("POST", "/api/gorev", {"gorev": "kesilecek gorev"})[1]
    api("POST", f"/api/gorev/{plan['kosu']}/onayla", {})
    assert eng.basladi.wait(10) and bekle(lambda: devam.oku(kur.proje)["kosu"]["once"])
    yeni = _yeni_uygulama(kur.proje)  # uygulama kapanip yeniden acildi
    y = yeni.durum()["yarim"]
    assert y["gorev"] == "kesilecek gorev" and y["durum"] == "calisiyor" and y["geri_al"] is True and yeni.durum()["kosu"] is None
    assert yeni.yarim_coz("yoksay") == {"tamam": True} and yeni.durum()["yarim"] is None and not devam.yol(kur.proje).exists()
    with pytest.raises(UygulamaHatasi):
        yeni.yarim_coz("yoksay")
    eng.serbest.set()


def test_devam_yeni_plan_uretir_otomatik_onay_acik_olsa_da_onay_ister_kuyruk_geri_gelir(kur):
    eng = Engelleyici()
    app, sv, api, _ = kur({"kodcu": eng.kodcu, "test": BASARILI})
    klasor_sec(api, kur.proje)
    plan = api("POST", "/api/gorev", {"gorev": "kesilen"})[1]
    api("POST", f"/api/gorev/{plan['kosu']}/onayla", {})
    assert eng.basladi.wait(10) and bekle(lambda: devam.oku(kur.proje)["kosu"]["once"])
    api("POST", "/api/gorev", {"gorev": "siradaki", "kuyruga": True})
    yeni = _yeni_uygulama(kur.proje)
    yol = ayar_yolu(kur.proje)
    ayar = json.loads(yol.read_text(encoding="utf-8"))
    ayar["otomatik_onay"] = True  # otomatik onay ACIK: kurtarilan gorev yine de onay istemeli
    yol.write_text(json.dumps(ayar), encoding="utf-8")
    sonuc_ = yeni.yarim_coz("devam")
    assert sonuc_["plan"]["tur"] == "plan" and sonuc_["plan"]["otomatik"] is False and sonuc_["plan"]["gorev"] == "kesilen"
    assert yeni.kosu.durum == "plan"  # onaysiz calismadi
    assert [k["gorev"] for k in yeni.secili.kuyruk] == ["siradaki"] and yeni.durum()["yarim"] is None
    assert devam.oku(kur.proje)["kosu"]["durum"] == "plan" and devam.oku(kur.proje)["kuyruk"][0]["gorev"] == "siradaki"
    eng.serbest.set()


def test_geri_al_dosyalari_gorevden_onceki_hale_dondurur(kur):
    eng = Engelleyici()
    app, sv, api, _ = kur({"kodcu": eng.kodcu, "test": BASARILI})
    klasor_sec(api, kur.proje)
    plan = api("POST", "/api/gorev", {"gorev": "yeni.txt yaz"})[1]
    api("POST", f"/api/gorev/{plan['kosu']}/onayla", {})
    assert eng.basladi.wait(10) and bekle(lambda: devam.oku(kur.proje)["kosu"]["once"])
    assert (kur.proje / "yeni.txt").read_text(encoding="utf-8") == "yarim\n"
    yeni = _yeni_uygulama(kur.proje)
    assert yeni.yarim_coz("geri-al")["geri_alinan"] >= 1
    assert not (kur.proje / "yeni.txt").exists() and yeni.durum()["yarim"] is None and not devam.yol(kur.proje).exists()
    eng.serbest.set()


def test_plan_asamasindaki_kayitta_geri_al_yok_ve_gecersiz_islem_reddedilir(kur):
    app, sv, api, _ = kur()
    klasor_sec(api, kur.proje)
    api("POST", "/api/gorev", {"gorev": "sadece plan"})
    yeni = _yeni_uygulama(kur.proje)
    assert yeni.durum()["yarim"]["geri_al"] is False
    with pytest.raises(UygulamaHatasi):
        yeni.yarim_coz("geri-al")
    with pytest.raises(UygulamaHatasi):
        yeni.yarim_coz("sil")
    assert yeni.durum()["yarim"] is not None  # hatali istek kaydi bozmaz


def test_yeni_gorev_baslayinca_eski_yarim_karari_gecersiz_olur(kur):
    app, sv, api, _ = kur()
    klasor_sec(api, kur.proje)
    api("POST", "/api/gorev", {"gorev": "eski"})
    yeni = _yeni_uygulama(kur.proje)
    assert yeni.durum()["yarim"]["gorev"] == "eski"
    yeni.gorev_olustur("tamamen yeni gorev")
    assert yeni.durum()["yarim"] is None and devam.oku(kur.proje)["kosu"]["gorev"] == "tamamen yeni gorev"
