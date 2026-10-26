"""Otomasyon (Asama A: sablonlar + 'Simdi calistir' + Telegram /sablon): dogrulama, kayit, degisken doldurma, gecmis, plan uretimi (onaysiz CALISMAZ),
proje izolasyonu, uzak politika, Telegram yetki siniri."""

import http.client
import json
import re
import time
from pathlib import Path

import pytest

from aktapokus_ai_studio import otomasyon as oto
from aktapokus_ai_studio import projeler, uzak
from aktapokus_ai_studio.arayuz import ArayuzSunucusu, Uygulama
from conftest import SahteCalistirici
from test_arayuz import Istemci, _ikinci_proje, bekle
from test_telegram import UID, kur as telegram_kur, son_klavye  # noqa: F401  (telegram_kur: pytest fixture'i)

P1 = "a" * 10


def sablon(**ek):
    v = {"ad": "haftalik-rapor", "proje": P1, "gorev": "Testleri calistir ({tarih})", "aciklama": "rapor"}
    v.update(ek)
    return v


# ---------- dogrulama / kayit ----------
@pytest.mark.parametrize("kotu", [
    {"ad": "Buyuk"}, {"ad": "../x"}, {"ad": ""}, {"ad": "a" * 40}, {"ad": None}, {"ad": "bosluk var"}, {"ad": "ğüş"}, {"ad": "satir\n"},
    {"proje": "xyz"}, {"proje": "../etc"}, {"proje": "A" * 10}, {"proje": None}, {"proje": "a" * 11},
    {"gorev": ""}, {"gorev": "   "}, {"gorev": None}, {"gorev": 5}, {"gorev": "x" * (oto.AZAMI_GOREV + 1)}, {"gorev": "a\x00b"},
    {"acik": "evet"}, {"acik": 1}, {"tur": "zamanli"}, {"tur": "baska"}, {"aciklama": "iki\nsatir"}, {"aciklama": "x" * 301}, {"aciklama": 5},
], ids=lambda d: next(iter(d)) + "=" + str(list(d.values())[0])[:12].replace("\x00", "NUL").replace("\n", "NL"))
def test_gecersiz_tanimlar_reddedilir(kotu):
    with pytest.raises(oto.OtomasyonHatasi):
        oto.kaydet(sablon(**kotu))
    assert oto.yukle() == {}


def test_kaydet_yukle_duzenle_sil_ve_olusturma_zamani_korunur():
    o = oto.kaydet(sablon())
    assert oto.bul("haftalik-rapor").gorev == "Testleri calistir ({tarih})" and o.acik is True and o.tur == "sablon"
    ilk = oto.bul("haftalik-rapor").olusturma
    time.sleep(1.1)
    oto.kaydet(sablon(gorev="degisti", acik=False))
    d = oto.bul("haftalik-rapor")
    assert d.gorev == "degisti" and d.acik is False and d.olusturma == ilk  # duzenleme olusturma zamanini degistirmez
    assert oto.sil("haftalik-rapor") is True and oto.sil("haftalik-rapor") is False and oto.bul("haftalik-rapor") is None and oto.bul(5) is None


def test_sinir_bozuk_dosya_ve_gecersiz_girdiler_atlanir(monkeypatch):
    for i in range(oto.AZAMI_OTOMASYON):
        oto.kaydet(sablon(ad=f"o{i}"))
    with pytest.raises(oto.OtomasyonHatasi, match="En cok"):
        oto.kaydet(sablon(ad="fazla"))
    oto.kaydet(sablon(ad="o0", gorev="duzenleme sinira takilmaz"))
    oto.dosya_yolu().write_text("{bozuk", encoding="utf-8")
    assert oto.yukle() == {}
    oto.dosya_yolu().write_text(json.dumps({"otomasyonlar": [{"ad": "KOTU"}, sablon(ad="iyi")]}), encoding="utf-8")
    assert list(oto.yukle()) == ["iyi"]


# ---------- degiskenler ----------
def test_degiskenler_bilinenler_dolar_bilinmeyenler_ve_format_enjeksiyonu_dokunulmaz():
    b = {"tarih": "2026-10-26", "saat": "09:30", "proje": "benim-proje", "dal": "main"}
    assert oto.degiskenleri_doldur("{tarih} {saat} {proje} {dal}", b) == "2026-10-26 09:30 benim-proje main"
    assert oto.degiskenleri_doldur("{bilinmeyen} {0} {tarih.__class__} {__import__} {}", b) == "{bilinmeyen} {0} {tarih.__class__} {__import__} {}"
    assert oto.degiskenleri_doldur("{dal}", {"tarih": "x"}) == "{dal}"  # baglamda yoksa oldugu gibi kalir
    assert oto.degiskenleri_doldur("{tarih}{tarih}", b) == "2026-10-262026-10-26"
    assert oto.degiskenleri_doldur("deger icinde {proje}", {"proje": "{tarih}", "tarih": "T"}) == "deger icinde {tarih}"  # doldurulan deger yeniden yorumlanmaz


# ---------- gecmis ----------
def test_gecmis_yeniden_eskiye_sinirli_ve_bozuk_satir_atlanir(monkeypatch):
    monkeypatch.setattr(oto, "AZAMI_GECMIS", 5)
    for i in range(8):
        oto.gecmis_ekle("a", "plan-olustu", neden="n" * 400 if i == 7 else "", tetikleyen=f"t{i}")
    g = oto.gecmis_oku(30)
    assert [k["tetikleyen"] for k in g] == ["t7", "t6", "t5", "t4", "t3"] and len(g[0]["neden"]) == 300
    with open(oto.gecmis_yolu(), "a", encoding="utf-8") as f:
        f.write("{bozuk\n")
    assert len(oto.gecmis_oku(30)) == 5
    assert oto.gecmis_oku(2)[0]["tetikleyen"] == "t7" and len(oto.gecmis_oku(2)) == 2


def test_otomasyon_tanimlari_proje_klasorunden_okunmaz(proje):
    (proje / ".aktapokus").mkdir(exist_ok=True)
    (proje / ".aktapokus" / "otomasyonlar.json").write_text(json.dumps({"otomasyonlar": [sablon(ad="zehirli", gorev="rm -rf")]}), encoding="utf-8")
    assert oto.yukle() == {}
    kaynak = (Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "otomasyon.py").read_text(encoding="utf-8")
    assert "klasor" not in kaynak.split('"""', 2)[2].replace("kullanici klasorunde", "")  # modul hicbir proje klasorune bakmaz


# ---------- Uygulama / HTTP ----------
class SayanCalistirici(SahteCalistirici):
    pass


@pytest.fixture
def api(proje, tmp_path):
    sayac = []

    def uret(ad):
        sayac.append(ad)
        return SahteCalistirici({"kodcu": lambda k, i, n: __import__("conftest").sonuc("x"), "test": lambda k, i, n: __import__("conftest").sonuc("SONUC: BASARILI")})

    app = Uygulama(calistirici_uret=uret)
    sv = ArayuzSunucusu(app)
    sv.baslat()
    app.klasor_sec(str(proje))
    ikinci = _ikinci_proje(tmp_path)
    app.proje_ac(str(ikinci), sec=False)  # kayitli ama SECILI DEGIL
    yield app, sv, Istemci(sv), proje, ikinci, sayac
    sv.kapat()


def test_uclar_belirtec_ister_ve_yabanci_origin_reddedilir(api):
    app, sv, istek, proje, ikinci, sayac = api
    for yontem, yol in (("GET", "/api/otomasyonlar"), ("POST", "/api/otomasyonlar"), ("POST", "/api/otomasyonlar/sil"), ("POST", "/api/otomasyon-calistir")):
        assert istek(yontem, yol, {} if yontem == "POST" else None, token=None)[0] == 401, yol
        if yontem == "POST":
            c = http.client.HTTPConnection("127.0.0.1", sv.port, timeout=10)
            c.request("POST", yol, body="{}", headers={"X-Aktapokus-Token": app.token, "Origin": "http://evil.example", "Content-Type": "application/json"})
            r = c.getresponse()
            r.read()
            c.close()
            assert r.status == 403, yol


def test_kaydet_listele_sil_http_ve_kayitsiz_proje_reddi(api):
    app, sv, istek, proje, ikinci, sayac = api
    pid = projeler.proje_kimligi(proje)
    assert istek("POST", "/api/otomasyonlar", sablon(proje=P1))[0] == 404  # kayitli olmayan proje
    st, d = istek("POST", "/api/otomasyonlar", sablon(proje=pid))
    assert st == 200 and d["ad"] == "haftalik-rapor"
    st, liste = istek("GET", "/api/otomasyonlar")
    o = liste["otomasyonlar"][0]
    assert st == 200 and o["proje_ad"] == proje.name and o["proje_var"] is True and {p["id"] for p in liste["projeler"]} >= {pid, projeler.proje_kimligi(ikinci)}
    assert istek("POST", "/api/otomasyonlar", sablon(proje=pid, ad="BUYUK"))[0] == 400
    assert istek("POST", "/api/otomasyonlar/sil", {"ad": "haftalik-rapor"})[0] == 200
    assert istek("POST", "/api/otomasyonlar/sil", {"ad": "haftalik-rapor"})[0] == 404 and istek("POST", "/api/otomasyonlar/sil", {})[0] == 404


def test_calistir_baska_projede_plan_uretir_secili_projeyi_degistirmez_ve_onaysiz_calismaz(api):
    app, sv, istek, proje, ikinci, sayac = api
    b = projeler.proje_kimligi(ikinci)
    a_id = app.secili_kimlik
    istek("POST", "/api/otomasyonlar", sablon(proje=b, gorev="{proje} icin rapor ({tarih} {saat}) {bilinmeyen}"))
    st, r = istek("POST", "/api/otomasyon-calistir", {"ad": "haftalik-rapor"})
    assert st == 200 and r["proje"] == b and r["proje_ad"] == ikinci.name and r["plan"]["tur"] == "plan"
    assert re.fullmatch(rf"{re.escape(ikinci.name)} icin rapor \(\d{{4}}-\d{{2}}-\d{{2}} \d{{2}}:\d{{2}}\) \{{bilinmeyen\}}", r["plan"]["gorev"]), r["plan"]["gorev"]
    assert app.secili_kimlik == a_id  # arayuzde secili proje DEGISMEDI
    assert app.oturumlar[b].kosu.durum == "plan" and app.oturumlar[a_id].kosu is None
    time.sleep(1.5)
    assert sayac == [] and app.oturumlar[b].kosu.durum == "plan"  # onay verilmeden hicbir calistirici baslatilmadi
    _, olaylar = app.bus.abone_ol(0)
    assert [o for o in olaylar if o.get("tur") == "plan" and o.get("proje") == b]  # plan olayi o projenin etiketiyle yayinlandi
    g = istek("GET", "/api/otomasyonlar")[1]["gecmis"][0]
    assert g["sonuc"] == "plan-olustu" and g["otomasyon"] == "haftalik-rapor" and g["tetikleyen"] == "elle" and g["gorev"] == r["plan"]["kosu"]


def test_projede_gorev_varsa_atlanir_birikmez_ve_gecmise_yazilir(api):
    app, sv, istek, proje, ikinci, sayac = api
    pid = projeler.proje_kimligi(proje)
    istek("POST", "/api/otomasyonlar", sablon(proje=pid))
    assert istek("POST", "/api/otomasyon-calistir", {"ad": "haftalik-rapor"})[0] == 200
    st, d = istek("POST", "/api/otomasyon-calistir", {"ad": "haftalik-rapor"})
    assert st == 409 and "Atlandi" in d["hata"]
    planlar = [o for o in app.bus.abone_ol(0)[1] if o.get("tur") == "plan"]
    assert len(planlar) == 1  # ikinci plan olusmadi (birikme yok)
    assert [g["sonuc"] for g in istek("GET", "/api/otomasyonlar")[1]["gecmis"]] == ["atlandi", "plan-olustu"]


def test_kapali_otomasyon_yalniz_elle_calisir_telegram_yolu_reddeder(api):
    app, sv, istek, proje, ikinci, sayac = api
    istek("POST", "/api/otomasyonlar", sablon(proje=projeler.proje_kimligi(proje), acik=False))
    with pytest.raises(Exception, match="kapali"):
        app.otomasyon_calistir("haftalik-rapor", "telegram", yalniz_acik=True)
    assert istek("POST", "/api/otomasyon-calistir", {"ad": "haftalik-rapor"})[0] == 200  # arayuzden elle her zaman


def test_calistir_bilinmeyen_ad_ve_kayitten_dusen_proje(api):
    app, sv, istek, proje, ikinci, sayac = api
    assert istek("POST", "/api/otomasyon-calistir", {"ad": "yok"})[0] == 404 and istek("POST", "/api/otomasyon-calistir", {})[0] == 404
    b = projeler.proje_kimligi(ikinci)
    istek("POST", "/api/otomasyonlar", sablon(proje=b))
    assert istek("POST", "/api/projeler/unut", {"id": b})[0] == 200
    st, d = istek("POST", "/api/otomasyon-calistir", {"ad": "haftalik-rapor"})
    assert st == 404 and "kayitli degil" in d["hata"] and istek("GET", "/api/otomasyonlar")[1]["gecmis"][0]["sonuc"] == "hata"
    assert istek("GET", "/api/otomasyonlar")[1]["otomasyonlar"][0]["proje_ad"] is None  # liste yine acilir, proje 'yok' gorunur


# ---------- uzak politika ----------
def test_uzak_politika_tanimlama_yonetim_ister_calistirma_ve_okuma_serbest():
    a = uzak.Ayar()
    assert uzak.politika("POST", "/api/otomasyonlar", a) and uzak.politika("POST", "/api/otomasyonlar/sil", a)
    assert uzak.politika("POST", "/api/otomasyon-calistir", a) is None and uzak.politika("GET", "/api/otomasyonlar", a) is None  # plan uretir, onay ister
    assert uzak.politika("POST", "/api/otomasyonlar", uzak.Ayar(yonetim=True)) is None


# ---------- Telegram ----------
def test_telegram_sablon_listeler_ve_yalniz_acik_olanlari_gosterir(telegram_kur, tmp_path):
    bot, fake, app, _ = telegram_kur()
    app.klasor_sec(str(telegram_kur.proje))
    fake.mesaj(UID, "/sablon")
    assert bekle(lambda: any("Kayitli sablon yok" in m for m in fake.metinler()))
    pid = projeler.proje_kimligi(telegram_kur.proje)
    oto.kaydet(sablon(ad="acik-olan", proje=pid, aciklama="acik aciklama"))
    oto.kaydet(sablon(ad="kapali-olan", proje=pid, acik=False))
    fake.mesaj(UID, "/sablon")
    assert bekle(lambda: son_klavye(fake, "s:")[0] is not None)
    v, dugmeler = son_klavye(fake, "s:")
    assert set(dugmeler.values()) == {"s:acik-olan"} and "acik aciklama" in v["text"] and "kapali-olan" not in v["text"]


def test_telegram_sablon_calistirinca_plan_ve_onay_dugmeleri_gelir_aktif_proje_degismez(telegram_kur, tmp_path):
    bot, fake, app, _ = telegram_kur()
    app.klasor_sec(str(telegram_kur.proje))
    ikinci = _ikinci_proje(tmp_path)
    app.proje_ac(str(ikinci), sec=False)
    b = projeler.proje_kimligi(ikinci)
    oto.kaydet(sablon(ad="rapor", proje=b, gorev="{proje} raporu"))
    fake.mesaj(UID, "/sablon rapor")
    assert bekle(lambda: any("plan olusturuldu" in m and ikinci.name in m for m in fake.metinler()))
    assert bekle(lambda: son_klavye(fake, "o:")[0] is not None)  # plan + Onayla/Reddet (normal bildirim akisi)
    assert app.oturumlar[b].kosu.durum == "plan" and bot.aktif_proje.get(UID) is None
    kosu = son_klavye(fake, "o:")[1]["Onayla"].split(":")[1]
    assert kosu == app.oturumlar[b].kosu.kimlik
    time.sleep(1)
    assert app.oturumlar[b].kosu.durum == "plan"  # Telegram onay dugmesine basilmadikca CALISMADI


def test_telegram_dugmesiyle_sablon_calisir(telegram_kur):
    bot, fake, app, _ = telegram_kur()
    app.klasor_sec(str(telegram_kur.proje))
    oto.kaydet(sablon(ad="dugme-sablon", proje=projeler.proje_kimligi(telegram_kur.proje)))
    fake.mesaj(UID, "/sablon")
    assert bekle(lambda: son_klavye(fake, "s:")[0] is not None)
    fake.dugme(UID, son_klavye(fake, "s:")[1]["dugme-sablon"])
    assert bekle(lambda: any("plan olusturuldu" in m for m in fake.metinler()))


def test_telegram_tanimlayamaz_gecersiz_kapali_ve_bilinmeyen_adlar_reddedilir(telegram_kur):
    bot, fake, app, _ = telegram_kur()
    app.klasor_sec(str(telegram_kur.proje))
    pid = projeler.proje_kimligi(telegram_kur.proje)
    oto.kaydet(sablon(ad="kapali-olan", proje=pid, acik=False))
    for mesaj in ("/sablon yeni-ad bir gorev metni yaz", "/sablon ../x", "/sablon kapali-olan", "/sablon yok-boyle", "/sablon rm -rf"):
        fake.mesaj(UID, mesaj)
    assert bekle(lambda: sum(("calistirilamadi" in m or "Gecersiz sablon" in m) for m in fake.metinler()) >= 5)
    assert list(oto.yukle()) == ["kapali-olan"]  # telefondan hicbir sey tanimlanmadi
    assert app.oturumlar[pid].kosu is None


def test_telegram_otomasyon_tanimlama_koduna_sahip_degil():
    kaynak = (Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "telegram.py").read_text(encoding="utf-8")
    for yasak in ("otomasyon_kaydet", "otomasyon_sil", "otomasyon.kaydet", "otomasyon.sil", "otomasyon.coz"):
        assert yasak not in kaynak, yasak


# ---------- arayuz ----------
def test_arayuz_otomasyon_bolumu():
    html = (Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "web" / "index.html").read_text(encoding="utf-8")
    for parca in ('["otomasyon","Otomasyonlar"]', "function otomasyonBolumu", "function otomasyonFormu", "/api/otomasyonlar", "/api/otomasyon-calistir", "Şimdi çalıştır", "yalnızca PLAN"):
        assert parca in html, parca
    govde = html.split("async function otomasyonBolumu")[1].split("(async()=>{if(!T)")[0]
    assert "confirm(" in govde and "innerHTML" not in govde  # silme onayli; gorev metinleri textContent ile
