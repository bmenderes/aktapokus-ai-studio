"""Otomasyonda model secimi: gorev dugumunde istege bagli {calistirici, model}; yalniz o gorev icin rolleri degistirir, proje ayarina YAZILMAZ."""

import json
import time
from pathlib import Path

import pytest

from aktapokus_ai_studio import config, otomasyon as oto, otomasyon_akis as akis_mod, projeler
from aktapokus_ai_studio.config import ayar_yukle
from test_otomasyon import api, P1  # noqa: F401  (api: pytest fixture'i)


def akis(model=None):
    g = {"gorev": "ollama ile gorev"}
    if model is not None:
        g["model"] = model
    return {
        "dugumler": [
            {"id": "t1", "tur": "elle", "x": 0, "y": 0, "ayar": {}},
            {"id": "g1", "tur": "gorev", "x": 200, "y": 0, "ayar": g},
        ],
        "oklar": [{"kaynak": "t1", "hedef": "g1"}],
    }


def test_motor_listeleri_esit():
    assert tuple(akis_mod.MOTORLAR) == tuple(config.OTOMASYON_MOTORLARI)
    assert set(config.OTOMASYON_MOTORLARI) <= set(config.BILINEN_CALISTIRICILAR)


@pytest.mark.parametrize("kotu", [
    "ollama/qwen3", {"calistirici": "rm", "model": "x"}, {"calistirici": "claude", "model": ""}, {"calistirici": "claude", "model": 5},
    {"calistirici": "claude", "model": "a" * 121}, {"calistirici": "claude", "model": "a\nb"}, {"model": "x"}, {"calistirici": "opencode", "model": "x"},
])
def test_gecersiz_model_secimi_reddedilir(kotu):
    with pytest.raises(oto.OtomasyonHatasi):
        oto.kaydet({"ad": "m1", "proje": P1, "akis": akis(kotu)})
    assert oto.yukle() == {}


def test_model_secimi_kaydedilir_secilmezse_alan_yoktur():
    o = oto.kaydet({"ad": "m1", "proje": P1, "akis": akis({"calistirici": "opencode-sunucu", "model": "ollama/qwen3:8b", "x": "yok sayilir"})})
    assert akis_mod.gorev_modeli(o.akis) == ("opencode-sunucu", "ollama/qwen3:8b")
    assert [d for d in o.akis["dugumler"] if d["tur"] == "gorev"][0]["ayar"]["model"] == {"calistirici": "opencode-sunucu", "model": "ollama/qwen3:8b"}
    o2 = oto.kaydet({"ad": "m2", "proje": P1, "akis": akis()})
    assert akis_mod.gorev_modeli(o2.akis) is None and "model" not in [d for d in o2.akis["dugumler"] if d["tur"] == "gorev"][0]["ayar"]
    assert akis_mod.gorev_modeli(None) is None
    o3 = oto.kaydet({"ad": "m3", "proje": P1, "akis": akis({"calistirici": "mistral", "model": None})})
    assert akis_mod.gorev_modeli(o3.akis) is None or akis_mod.gorev_modeli(o3.akis) == ("mistral", None)


def test_ayar_model_gecersiz_roller_degisir_gizli_dosya_onayi_genisletilmez(tmp_path):
    (tmp_path / ".aktapokus").mkdir()
    ayar = config.ayar_coz(json.loads(json.dumps(config.VARSAYILAN_AYAR)))
    yeni = config.ayar_model_gecersiz(ayar, "claude", "haiku")
    assert {r.calistirici for r in yeni.roller.values()} == {"claude"} and {r.model for r in yeni.roller.values()} == {"haiku"}
    assert yeni.roller["test"].dogrulama is True and yeni.roller["test"].talimat == ayar.roller["test"].talimat  # rol islevi korunur
    assert all(r.okuma_riski_kabul is False for r in yeni.roller.values())  # gizli dosya onayi acilmadi
    assert ayar.roller["kodcu"].calistirici == "opencode-sunucu"  # orijinal degismedi
    assert config.ayar_model_gecersiz(ayar, "mistral", None).roller["kodcu"].model is None
    with pytest.raises(config.AyarHatasi):
        config.ayar_model_gecersiz(ayar, "bilinmeyen", "x")
    with pytest.raises(config.AyarHatasi):
        config.ayar_model_gecersiz(ayar, "claude", "a\x00b")


def test_otomasyon_secilen_modelle_calisir_proje_ayari_degismez(api):
    app, sv, istek, proje, ikinci, sayac = api
    pid = projeler.proje_kimligi(proje)
    onceki = (proje / ".aktapokus" / "roller.json").read_text(encoding="utf-8")
    assert istek("POST", "/api/otomasyonlar", {"ad": "yerelle", "proje": pid, "akis": akis({"calistirici": "claude", "model": "haiku"})})[0] == 200
    st, r = istek("POST", "/api/otomasyon-calistir", {"ad": "yerelle"})
    assert st == 200
    assert {a["calistirici"] for a in r["plan"]["adimlar"]} == {"claude"} and {a["model"] for a in r["plan"]["adimlar"]} == {"haiku"}  # plan secilen modeli gosterir
    assert (proje / ".aktapokus" / "roller.json").read_text(encoding="utf-8") == onceki  # proje ayari DEGISMEDI
    assert ayar_yukle(proje).roller["kodcu"].calistirici != "claude"
    kosu = app.oturumlar[app.secili_kimlik].kosu
    assert kosu.model_gecersiz == ("claude", "haiku") and kosu.durum == "plan"  # onaysiz calismadi
    gorulen = []
    app.calistirici_uret = lambda ad: gorulen.append(ad) or __import__("conftest").SahteCalistirici({"kodcu": lambda k, i, n: __import__("conftest").sonuc("x"), "test": lambda k, i, n: __import__("conftest").sonuc("SONUC: BASARILI")})
    assert istek("POST", f"/api/gorev/{r['plan']['kosu']}/onayla", {})[0] == 200
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and kosu.durum != "bitti":
        time.sleep(0.05)
    assert kosu.durum == "bitti" and set(gorulen) == {"claude"}  # calistirici secilen motordan uretildi
    # model secilmeyen otomasyon projenin ayariyla calisir; elle gorev etkilenmez
    assert istek("POST", "/api/otomasyonlar", {"ad": "varsayilan", "proje": pid, "akis": akis()})[0] == 200
    r2 = istek("POST", "/api/otomasyon-calistir", {"ad": "varsayilan"})[1]
    assert {a["calistirici"] for a in r2["plan"]["adimlar"]} == {"opencode-sunucu"}


def test_arayuz_model_secici_proje_ayarina_yazmaz():
    html = (Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "web" / "index.html").read_text(encoding="utf-8")
    assert "async function otoModelSecenekleri()" in html and 'e("option",{value:"",text:"Projenin rol ayarı"})' in html
    assert "otoModelSecenekleri().then(s=>{modelSecenekleri=s;panelCiz()})" in html and "n.ayar.model=JSON.parse(ms.value)" in html
    assert '["claude","codex","gemini","mistral"].includes(c.ad)' in html and 'c:"opencode-sunucu",m:m.id' in html
