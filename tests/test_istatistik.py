import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from aktapokus_ajan import istatistik
from aktapokus_ajan.arayuz import ArayuzSunucusu, Uygulama
from test_arayuz import Istemci, klasor_sec

SIMDI = datetime(2026, 10, 22, 15, 0, 0)


def adim(rol="kodcu", c="opencode-sunucu", model="opencode/m1", g=100, o=20, onb=500, ok=True, hata=None, sure=2.0):
    return {"rol": rol, "calistirici": c, "model": model, "ok": ok, "token_girdi": g, "token_cikti": o, "token_onbellek": onb, "sure_sn": sure, "hata": hata}


def kayit(zaman, adimlar, durum="onaylandi", proje="p1"):
    return {"id": zaman, "zaman": zaman.strftime("%Y-%m-%d %H:%M:%S"), "durum": durum, "adimlar": adimlar, "_proje": proje}


@pytest.mark.parametrize(
    "metin, sinif",
    [
        ("Claude AI usage limit reached|1761", "limit"),
        ("HTTP 429 Too Many Requests", "limit"),
        ("You exceeded your current quota", "limit"),
        ("rate_limit_error: slow down", "limit"),
        ("RESOURCE_EXHAUSTED", "limit"),
        ("API Error: 401 Unauthorized", "kimlik"),
        ("Invalid API key", "kimlik"),
        ("Not logged in", "kimlik"),
        ("Zaman asimi (900 sn)", "zaman_asimi"),
        ("request timed out", "zaman_asimi"),
        ("garip bir hata", "diger"),
        (None, None),
        ("", None),
    ],
)
def test_hata_siniflandirma(metin, sinif):
    assert istatistik.hata_sinifi(metin) == sinif


def test_toplamlar_gun_siniri_ve_onbellek_ayri():
    kayitlar = [
        kayit(SIMDI - timedelta(hours=1), [adim(g=100, o=20), adim("test", g=50, o=10)]),  # bugun
        kayit(SIMDI - timedelta(days=3), [adim(g=1000, o=200)]),  # hafta icinde
        kayit(SIMDI - timedelta(days=10), [adim(g=5000, o=500)]),  # hafta disinda
    ]
    o = istatistik.ozet(kayitlar, SIMDI)
    assert o["bugun"]["yeni"] == 180 and o["bugun"]["adim"] == 2
    assert o["hafta"]["yeni"] == 180 + 1200
    assert o["toplam"]["yeni"] == 180 + 1200 + 5500 and o["toplam"]["onbellek"] == 4 * 500  # onbellek 'yeni'ye katilmaz
    assert o["gorev_sayisi"] == 3
    assert len(o["gunluk"]) == 14 and o["gunluk"][-1] == {"gun": "2026-10-22", "yeni": 180}
    assert {g["gun"]: g["yeni"] for g in o["gunluk"]}["2026-10-19"] == 1200
    assert {g["gun"]: g["yeni"] for g in o["gunluk"]}["2026-10-12"] == 5500  # 10 gun once: hafta disinda ama 14 gunluk grafikte


def test_hafta_siniri_tam_yedi_gun():
    """Bugun dahil 7 gun: 6 gun onceki gun icinde, 7 gun onceki disinda."""
    alti = datetime(2026, 10, 16, 0, 0, 0)  # bugunun 6 gun oncesi, gun basi
    yedi = datetime(2026, 10, 15, 23, 59, 59)
    o = istatistik.ozet([kayit(alti, [adim(g=10, o=0)]), kayit(yedi, [adim(g=7, o=0)])], SIMDI)
    assert o["hafta"]["yeni"] == 10 and o["toplam"]["yeni"] == 17


def test_gece_yarisi_siniri():
    gece = datetime(2026, 10, 22, 0, 0, 0)
    dun = datetime(2026, 10, 21, 23, 59, 59)
    o = istatistik.ozet([kayit(gece, [adim(g=10, o=0)]), kayit(dun, [adim(g=7, o=0)])], SIMDI)
    assert o["bugun"]["yeni"] == 10 and o["hafta"]["yeni"] == 17


def test_model_rol_proje_dokumu_ve_hatalar():
    kayitlar = [
        kayit(SIMDI - timedelta(hours=2), [adim(model="m1", g=100), adim("test", c="claude", model="haiku", g=40, o=0, ok=False, hata="Claude AI usage limit reached")], proje="a"),
        kayit(SIMDI - timedelta(hours=1), [adim(model="m1", g=300)], durum="butce_asildi", proje="b"),
    ]
    o = istatistik.ozet(kayitlar, SIMDI)
    assert [m["model"] for m in o["modeller"]] == ["m1", "haiku"]  # cok harcayan once
    m1 = o["modeller"][0]
    assert m1["adim"] == 2 and m1["yeni"] == 100 + 20 + 300 + 20 and m1["hata"] == 0
    assert o["modeller"][1]["hata"] == 1
    assert {r["rol"] for r in o["roller"]} == {"kodcu", "test"} and {p["proje"] for p in o["projeler"]} == {"a", "b"}
    assert o["hatalar"] == {"limit/kota": 1, "bütçe": 1}
    assert o["son_hatalar"][0]["sinif"] == "limit" and o["durumlar"] == {"onaylandi": 1, "butce_asildi": 1}


def test_bozuk_alanlar_ozeti_dusurmez():
    garip = {"zaman": "dun", "durum": None, "adimlar": ["metin", {"token_girdi": "x", "sure_sn": "uzun"}, {"calistirici": "c", "token_girdi": None, "token_cikti": -5}]}
    o = istatistik.ozet([garip, {"adimlar": None}, {}], SIMDI)
    assert o["gorev_sayisi"] == 3 and o["toplam"]["yeni"] == 0


def test_kayitlari_oku_ve_bozuk_dosyayi_atla(tmp_path):
    k = tmp_path / "proje" / ".aktapokus" / "kayit"
    k.mkdir(parents=True)
    (k / "1.json").write_text(json.dumps({"zaman": "2026-10-22 10:00:00", "adimlar": []}), encoding="utf-8")
    (k / "2.json").write_text("{bozuk", encoding="utf-8")
    (k / "3.json").write_text("[1,2]", encoding="utf-8")
    r = istatistik.kayitlari_oku([tmp_path / "proje", tmp_path / "yok"])
    assert len(r) == 1 and r[0]["_proje"] == "proje"


def test_bilinen_klasorler_kok_alt_klasorleri_gizli_ve_noktali_haric(tmp_path, monkeypatch):
    kok = tmp_path / "kok"
    for ad in ("a", "b", "gizliproje", ".nokta", "kayitsiz"):
        (kok / ad).mkdir(parents=True)
    for ad in ("a", "b", "gizliproje", ".nokta"):
        (kok / ad / ".aktapokus" / "kayit").mkdir(parents=True)
    acik = tmp_path / "baska"
    (acik / ".aktapokus" / "kayit").mkdir(parents=True)
    ayar = tmp_path / "telegram.json"
    ayar.write_text(json.dumps({"kokler": [str(kok), str(tmp_path / "olmayan")], "gizli": ["GizliProje"]}), encoding="utf-8")
    monkeypatch.setenv("AKTAPOKUS_TELEGRAM_AYAR", str(ayar))
    adlar = [p.name for p in istatistik.bilinen_klasorler(acik)]
    assert adlar == ["baska", "a", "b"]  # acik proje basta; gizli, noktali ve kayitsiz klasorler yok; tekrar yok
    assert [p.name for p in istatistik.bilinen_klasorler(kok / "a")] == ["a", "b"]  # ayni klasor iki kez sayilmaz
    ayar.write_text("{bozuk", encoding="utf-8")
    assert [p.name for p in istatistik.bilinen_klasorler(acik)] == ["baska"]


ADAYLAR = [
    {"calistirici": "opencode-sunucu", "model": "opencode/deepseek-v4.1-flash-free", "ucretsiz": True},
    {"calistirici": "claude", "model": "haiku", "ucretsiz": False},
    {"calistirici": "claude", "model": "sonnet", "ucretsiz": False},
    {"calistirici": "codex", "model": None, "ucretsiz": False},
]
ROLLER = {"kodcu": {"calistirici": "claude", "model": "sonnet"}, "test": {"calistirici": "opencode-sunucu", "model": "opencode/deepseek-v4.1-flash-free"}}


def limitli():
    return istatistik.ozet([kayit(SIMDI - timedelta(hours=3), [adim("kodcu", c="claude", model="sonnet", ok=False, hata="Claude AI usage limit reached")])], SIMDI)


def test_limit_onerisi_ucretsiz_once_ve_yalniz_etkilenen_rol():
    oneriler = istatistik.oneriler(limitli(), ROLLER, ADAYLAR)
    assert oneriler and all(o["tur"] == "limit" and o["uygula"]["rol"] == "kodcu" for o in oneriler)  # 'test' rolu claude kullanmiyor
    assert oneriler[0]["uygula"] == {"rol": "kodcu", "calistirici": "opencode-sunucu", "model": "opencode/deepseek-v4.1-flash-free"}
    assert "ücretsiz" in oneriler[0]["etiket"]
    assert not any(o["uygula"] == {"rol": "kodcu", "calistirici": "claude", "model": "sonnet"} for o in oneriler)  # sorunlu modelin kendisi onerilmez
    assert len(oneriler) == 2  # rol basina en cok iki secenek


def test_eski_limit_hatasi_oneri_uretmez_ama_sayilir():
    eski = istatistik.ozet([kayit(SIMDI - timedelta(hours=istatistik.LIMIT_PENCERESI_SA + 1), [adim(c="claude", model="sonnet", ok=False, hata="usage limit reached")])], SIMDI)
    assert eski["hatalar"] == {"limit/kota": 1}
    assert istatistik.oneriler(eski, ROLLER, ADAYLAR) == []


def test_aday_yoksa_aciklayici_oneri_ve_projesiz_oneri():
    assert "başka bir model yok" in istatistik.oneriler(limitli(), ROLLER, [])[0]["aciklama"]
    projesiz = istatistik.oneriler(limitli(), None, ADAYLAR)
    assert projesiz and all("uygula" not in o for o in projesiz)  # rol bilinmiyorsa tek tikla uygulama yok


def test_butce_ve_kimlik_onerileri():
    o = istatistik.ozet([kayit(SIMDI, [adim(ok=False, hata="401 Unauthorized")], durum="butce_asildi")], SIMDI)
    turler = {x["tur"] for x in istatistik.oneriler(o, ROLLER, ADAYLAR)}
    assert turler == {"butce", "kimlik"}


def test_http_ucu_proje_ve_tum_kapsam(proje, tmp_path, monkeypatch):
    k = proje / ".aktapokus" / "kayit"
    k.mkdir(parents=True, exist_ok=True)
    simdi = datetime.now()
    (k / "x.json").write_text(json.dumps({"id": "x", "zaman": simdi.strftime("%Y-%m-%d %H:%M:%S"), "gorev": "g", "token_toplam": 100, "durum": "onaylandi", "adimlar": [adim(g=70, o=30)]}), encoding="utf-8")
    ayar = tmp_path / "telegram.json"
    ayar.write_text(json.dumps({"kokler": [str(proje.parent)], "gizli": []}), encoding="utf-8")
    monkeypatch.setenv("AKTAPOKUS_TELEGRAM_AYAR", str(ayar))
    sv = ArayuzSunucusu(Uygulama())
    sv.baslat()
    try:
        api = Istemci(sv)
        assert api("GET", "/api/istatistik")[0] >= 400  # klasor secilmeden
        klasor_sec(api, proje)
        st, d = api("GET", "/api/istatistik")
        assert st == 200 and d["kapsam"] == "proje" and d["bugun"]["yeni"] == 100 and d["proje_sayisi"] == 1
        assert not any(a.startswith("_") for a in d)  # ic alanlar disari cikmaz
        st, d = api("GET", "/api/istatistik?kapsam=tum")
        assert st == 200 and d["kapsam"] == "tum" and d["toplam"]["yeni"] == 100
        assert api("GET", "/api/istatistik?kapsam=baska")[0] == 400
        assert Istemci(sv, token="yanlis")("GET", "/api/istatistik")[0] == 401
    finally:
        sv.kapat()


def test_sorunlu_model_kendisi_onerilmez_ve_siralama_ADAY_SIRASINDAN_bagimsiz():
    """Sorunlu model en iyi adayken (ucretsiz) bile onerilmemeli; adaylar ters sirada verilse de ucretsizler once gelmeli."""
    roller = {"kodcu": {"calistirici": "opencode-sunucu", "model": "opencode/deepseek-v4.1-flash-free"}}
    sorun = istatistik.ozet([kayit(SIMDI - timedelta(hours=1), [adim("kodcu", c="opencode-sunucu", model="opencode/deepseek-v4.1-flash-free", ok=False, hata="429 Too Many Requests")])], SIMDI)
    ters = list(reversed(ADAYLAR)) + [{"calistirici": "opencode-sunucu", "model": "opencode/baska-free", "ucretsiz": True}]
    hedefler = [o["uygula"] for o in istatistik.oneriler(sorun, roller, ters)]
    assert {"rol": "kodcu", "calistirici": "opencode-sunucu", "model": "opencode/deepseek-v4.1-flash-free"} not in hedefler
    assert hedefler[0]["model"] == "opencode/baska-free"  # ucretsiz, ters sirada olmasina ragmen basta
    assert len(hedefler) == 2 and hedefler[1]["model"] != "opencode/baska-free"
