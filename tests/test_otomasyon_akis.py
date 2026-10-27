"""Otomasyon is akisi (tuval, ilk dilim): dogrulama, eski sablonlarla geriye uyum, turetilmis alanlar, bildirim, onay siniri, uzak politika."""

import time
from pathlib import Path

import pytest

from aktapokus_ai_studio import otomasyon as oto
from aktapokus_ai_studio import otomasyon_akis as akis_mod
from aktapokus_ai_studio import projeler, uzak
from test_otomasyon import api, P1  # noqa: F401  (api: pytest fixture'i)


def akis(**ek):
    v = {
        "dugumler": [
            {"id": "t1", "tur": "zamanlayici", "x": 10, "y": 20, "ayar": {"zamanlama": {"tur": "aralik", "dakika": 30}}},
            {"id": "g1", "tur": "gorev", "x": 300, "y": 20, "ayar": {"gorev": "Testleri calistir ({tarih})"}},
            {"id": "b1", "tur": "bildirim", "x": 600, "y": 20, "ayar": {"metin": "{proje} icin plan hazir"}},
        ],
        "oklar": [{"kaynak": "t1", "hedef": "g1"}, {"kaynak": "g1", "hedef": "b1"}],
    }
    v.update(ek)
    return v


def tanim(**ek):
    v = {"ad": "akisli", "proje": P1, "akis": akis()}
    v.update(ek)
    return v


def _degistir(yol, deger):
    a = akis()
    d = a["dugumler"]
    if yol == "tetik-yok":
        d.pop(0)
        a["oklar"] = a["oklar"][1:]
    elif yol == "iki-gorev":
        d.append({"id": "g2", "tur": "gorev", "ayar": {"gorev": "x"}})
    elif yol == "ok-ters":
        a["oklar"][1] = {"kaynak": "b1", "hedef": "g1"}
    elif yol == "ok-yok":
        a["oklar"] = []
    elif yol == "bilinmeyen-tur":
        d.append({"id": "k1", "tur": "kabuk", "ayar": {}})
    elif yol == "tekrar-id":
        d.append({"id": "t1", "tur": "bildirim", "ayar": {"metin": "x"}})
    elif yol == "kotu-id":
        d[1]["id"] = "../x"
    elif yol == "bos-gorev":
        d[1]["ayar"]["gorev"] = "  "
    elif yol == "uzun-bildirim":
        d[2]["ayar"]["metin"] = "x" * (akis_mod.AZAMI_BILDIRIM + 1)
    elif yol == "kotu-konum":
        d[0]["x"] = "sol"
    elif yol == "uzak-konum":
        d[0]["y"] = 10 ** 9
    elif yol == "cok-dugum":
        d.extend({"id": f"b{i}", "tur": "bildirim", "ayar": {"metin": "x"}} for i in range(2, 14))
    elif yol == "kotu-zamanlama":
        d[0]["ayar"]["zamanlama"] = {"tur": "aralik", "dakika": 1}
    elif yol == "ayni-ok":
        a["oklar"].append(dict(a["oklar"][0]))
    elif yol == "dugum-degil":
        d.append("x")
    elif yol == "bilinmeyen-ok":
        a["oklar"].append({"kaynak": "t1", "hedef": "yok"})
    return a


@pytest.mark.parametrize("yol", ["tetik-yok", "iki-gorev", "ok-ters", "ok-yok", "bilinmeyen-tur", "tekrar-id", "kotu-id", "bos-gorev", "uzun-bildirim", "kotu-konum", "uzak-konum", "cok-dugum", "kotu-zamanlama", "ayni-ok", "dugum-degil", "bilinmeyen-ok"])
def test_gecersiz_akislar_reddedilir(yol):
    with pytest.raises(oto.OtomasyonHatasi):
        oto.kaydet(tanim(akis=_degistir(yol, None)))
    assert oto.yukle() == {}


def test_akis_alanlari_turetilir_istemcinin_gorev_ve_turu_yok_sayilir():
    o = oto.kaydet(tanim(gorev="ISTEMCI METNI", tur="sablon", zamanlama=None))
    assert o.tur == "zamanli" and o.zamanlama == {"tur": "aralik", "dakika": 30} and o.gorev == "Testleri calistir ({tarih})"
    yuklu = oto.bul("akisli")
    assert yuklu.akis["oklar"] == akis()["oklar"] and [d["id"] for d in yuklu.akis["dugumler"]] == ["t1", "g1", "b1"]
    elle = akis()
    elle["dugumler"][0] = {"id": "t1", "tur": "elle", "x": 0, "y": 0, "ayar": {}}
    o = oto.kaydet(tanim(akis=elle))
    assert o.tur == "sablon" and o.zamanlama is None


def test_bilinmeyen_dugum_ayarlari_dusurulur_onay_alani_tasinamaz():
    a = akis()
    a["dugumler"][1]["ayar"].update({"otomatik_onay": True, "onayla": True, "komut": "rm -rf /"})
    oto.kaydet(tanim(akis=a))
    assert oto.bul("akisli").akis["dugumler"][1]["ayar"] == {"gorev": "Testleri calistir ({tarih})"}


def test_akissiz_eski_sablon_aynen_calisir_ve_tuvalde_sanal_akis_olarak_gorunur():
    o = oto.kaydet({"ad": "eski", "proje": P1, "gorev": "eski gorev"})
    assert o.akis is None and o.sozluk()["akis"] is None and o.tur == "sablon"
    sanal = akis_mod.sablondan_akis(o.gorev, None)
    assert [d["tur"] for d in sanal["dugumler"]] == ["elle", "gorev"]
    kayit = oto.kaydet({"ad": "eski", "proje": P1, "akis": sanal})  # tuvalde kaydedince akisa donusur
    assert kayit.gorev == "eski gorev" and kayit.akis is not None
    z = akis_mod.sablondan_akis("g", {"tur": "gunluk", "saat": "09:00"})
    assert oto.kaydet({"ad": "eski2", "proje": P1, "akis": z}).zamanlama == {"tur": "gunluk", "saat": "09:00"}


def test_bildirim_metinleri_yalniz_gorevden_cikanlar():
    assert akis_mod.bildirim_metinleri(None) == []
    a = akis()
    a["oklar"] = a["oklar"][:1]  # bildirim bagli degil
    assert akis_mod.bildirim_metinleri(a) == []
    assert akis_mod.bildirim_metinleri(akis()) == ["{proje} icin plan hazir"]


# ---------- calistirma ----------
class SahteBot:
    def __init__(self):
        self.giden = []

    def _herkese(self, metin, klavye=None):
        self.giden.append(metin)


class SahteYonetici:
    def __init__(self, bot):
        self._bot = bot

    def _canli(self):
        return True


def test_calistirinca_plan_olusur_bildirim_gider_onay_yine_bekler(api):
    app, sv, istek, proje, ikinci, sayac = api
    bot = SahteBot()
    app.telegram = SahteYonetici(bot)
    assert istek("POST", "/api/otomasyonlar", tanim(proje=projeler.proje_kimligi(proje)))[0] == 200
    st, r = istek("POST", "/api/otomasyon-calistir", {"ad": "akisli"})
    assert st == 200 and r["plan"]["tur"] == "plan"
    assert bot.giden == [f"{proje.name} icin plan hazir"]  # degiskenler dolu
    time.sleep(1)
    assert sayac == [] and app.oturumlar[app.secili_kimlik].kosu.durum == "plan"  # onaysiz calistirici baslamadi


def test_bildirim_hatasi_plani_bozmaz_ve_bot_kapaliysa_sessiz_atlanir(api):
    app, sv, istek, proje, ikinci, sayac = api

    class Patlayan(SahteBot):
        def _herkese(self, metin, klavye=None):
            raise RuntimeError("ag yok")

    app.telegram = SahteYonetici(Patlayan())
    istek("POST", "/api/otomasyonlar", tanim(proje=projeler.proje_kimligi(proje)))
    assert istek("POST", "/api/otomasyon-calistir", {"ad": "akisli"})[0] == 200
    assert any(g["sonuc"] == "hata" and "bildirim" in g["neden"] for g in oto.gecmis_oku(10))
    app.oturumlar[app.secili_kimlik].kosu = None
    app.telegram = None  # bot hic kurulmamis
    assert istek("POST", "/api/otomasyon-calistir", {"ad": "akisli"})[0] == 200


def test_akis_uzak_politika_ayni_uc_uzerinden_yonetim_ister():
    # akis kaydi /api/otomasyonlar ucundan gecer: uzaktan tanimlama yonetim aciksa mumkun, kapaliyken yasak
    assert uzak.politika("POST", "/api/otomasyonlar", uzak.Ayar())
    assert uzak.politika("POST", "/api/otomasyonlar", uzak.Ayar(yonetim=True)) is None


def test_akis_dugum_turlerinde_onay_alani_yok():
    assert "otomatik_onay" not in Path(akis_mod.__file__).read_text(encoding="utf-8")
    assert set(akis_mod.TURLER) == {"elle", "zamanlayici", "gorev", "bildirim"}
