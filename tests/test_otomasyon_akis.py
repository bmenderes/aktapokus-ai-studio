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


def _bitir(app, istek, kosu):
    """Plani onaylar ve gorev bitene kadar bekler (sahte calistirici dosya degistirmez: 'degisiklik_yok')."""
    assert istek("POST", f"/api/gorev/{kosu}/onayla", {})[0] == 200
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and app.oturumlar[app.secili_kimlik].kosu.durum != "bitti":
        time.sleep(0.05)
    assert app.oturumlar[app.secili_kimlik].kosu.durum == "bitti"
    time.sleep(0.2)


def test_bildirim_gorev_bitince_gider_plan_asamasinda_gitmez_onay_yine_bekler(api):
    app, sv, istek, proje, ikinci, sayac = api
    bot = SahteBot()
    app.telegram = SahteYonetici(bot)
    assert istek("POST", "/api/otomasyonlar", tanim(proje=projeler.proje_kimligi(proje)))[0] == 200
    st, r = istek("POST", "/api/otomasyon-calistir", {"ad": "akisli"})
    assert st == 200 and r["plan"]["tur"] == "plan"
    time.sleep(0.5)
    assert bot.giden == [] and sayac == [] and app.oturumlar[app.secili_kimlik].kosu.durum == "plan"  # onaysiz ne calisti ne mesaj gitti
    _bitir(app, istek, r["plan"]["kosu"])
    assert bot.giden == [f"{proje.name} icin plan hazir"]  # dugum metni, degiskenler dolu


def test_bildirimde_durum_ve_yanit_degiskenleri_dolar(api):
    app, sv, istek, proje, ikinci, sayac = api
    bot = SahteBot()
    app.telegram = SahteYonetici(bot)
    a = akis()
    a["dugumler"][2]["ayar"]["metin"] = "{proje}: {durum} / {yanit}"
    istek("POST", "/api/otomasyonlar", tanim(proje=projeler.proje_kimligi(proje), akis=a))
    r = istek("POST", "/api/otomasyon-calistir", {"ad": "akisli"})[1]
    _bitir(app, istek, r["plan"]["kosu"])
    assert bot.giden == [f"{proje.name}: degisiklik_yok / x"]  # sahte kodcu yaniti 'x'


def test_bildirim_hatasi_gorevi_bozmaz_bot_kapaliysa_gecmise_yazilir(api):
    app, sv, istek, proje, ikinci, sayac = api

    class Patlayan(SahteBot):
        def _herkese(self, metin, klavye=None):
            raise RuntimeError("ag yok")

    app.telegram = SahteYonetici(Patlayan())
    istek("POST", "/api/otomasyonlar", tanim(proje=projeler.proje_kimligi(proje)))
    r = istek("POST", "/api/otomasyon-calistir", {"ad": "akisli"})[1]
    _bitir(app, istek, r["plan"]["kosu"])
    assert any(g["sonuc"] == "hata" and "bildirim" in g["neden"] for g in oto.gecmis_oku(10))
    app.telegram = None  # bot hic kurulmamis
    r = istek("POST", "/api/otomasyon-calistir", {"ad": "akisli"})[1]
    _bitir(app, istek, r["plan"]["kosu"])
    assert any(g["sonuc"] == "atlandi" and "Telegram botu calismiyor" in g["neden"] for g in oto.gecmis_oku(10))


def test_elle_gorev_otomasyon_bildirimi_tetiklemez(api):
    app, sv, istek, proje, ikinci, sayac = api
    bot = SahteBot()
    app.telegram = SahteYonetici(bot)
    istek("POST", "/api/otomasyonlar", tanim(proje=projeler.proje_kimligi(proje)))
    plan = istek("POST", "/api/gorev", {"gorev": "elle verilen gorev"})[1]
    _bitir(app, istek, plan["kosu"])
    assert bot.giden == []  # yalniz otomasyonun urettigi gorev bildirim yollar


def test_akis_uzak_politika_ayni_uc_uzerinden_yonetim_ister():
    # akis kaydi /api/otomasyonlar ucundan gecer: uzaktan tanimlama yonetim aciksa mumkun, kapaliyken yasak
    assert uzak.politika("POST", "/api/otomasyonlar", uzak.Ayar())
    assert uzak.politika("POST", "/api/otomasyonlar", uzak.Ayar(yonetim=True)) is None


def test_akis_dugum_turlerinde_onay_alani_yok():
    assert "otomatik_onay" not in Path(akis_mod.__file__).read_text(encoding="utf-8")
    assert set(akis_mod.TURLER) == {"elle", "zamanlayici", "gorev", "bildirim"}


def test_otomasyon_sayfasi_sade_ad_bos_birakilirsa_gorevden_uretilir():
    html = (Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "web" / "index.html").read_text(encoding="utf-8")
    assert "oto-bilgi" not in html and "Şablon değişkenleri:" not in html  # uzun aciklama kutusu yok (sade arayuz)
    assert "function otoAdUret(" in html and "if(!ad.value.trim()&&!duzenle)ad.value=otoAdUret(" in html
    assert 'title:"Bildirim ekle (Telegram)"' in html and 'text:"+"' in html  # renkli emoji yerine duz artı


def test_gorev_dugumunun_cikis_portu_artı_bildirim_ekler_surukleyince_baglar():
    html = (Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "web" / "index.html").read_text(encoding="utf-8")
    assert "const bildirimEkle=()=>{" in html and "onclick:bildirimEkle" in html  # arac cubugundaki + ve port ayni islev
    assert 'class:"oto-port c"+(n.tur==="gorev"?" art":"")' in html and "Bildirim ekle (tıkla) ya da bağla (sürükle)" in html
    assert 'n.tur==="gorev"&&Math.hypot(m.clientX-x0,m.clientY-y0)<5' in html  # hareketsiz tiklama = ekle; surukleme = bagla
    assert ".oto-port.c.art{width:20px" in html
