"""Degisiklikleri otomatik koru (secmeli), GitHub isareti, kenar cubugu sadelesmesi, Enter ile gonderme ve sesli yazma baglantilari."""

from pathlib import Path

import pytest

from aktapokus_ai_studio.arayuz import github_deposu_mu
from aktapokus_ai_studio.config import AyarHatasi, ayar_coz
from test_arayuz import bekle, klasor_sec, kur  # noqa: F401  (pytest fixture'lari)

HTML = (Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "web" / "index.html").read_text(encoding="utf-8")


def test_otomatik_koru_karar_sormadan_korur(kur):
    app, sv, api, _ = kur()
    klasor_sec(api, kur.proje)
    ayar = api("GET", "/api/ayar")[1]
    assert ayar.get("otomatik_koru", False) is False  # varsayilan kapali: karar sorulur
    ayar["otomatik_koru"] = True
    assert api("PUT", "/api/ayar", ayar)[0] == 200
    assert api("GET", "/api/durum")[1]["ayar"]["otomatik_koru"] is True
    plan = api("POST", "/api/gorev", {"gorev": "yeni.txt ekle"})[1]
    api("POST", f"/api/gorev/{plan['kosu']}/onayla", {})
    assert bekle(lambda: any(o["tur"] == "bitti" for o in app.bus.gecmis))  # durum 'bitti' olay yayinlanmadan hemen once atanir: olayi bekle
    bitti = [o for o in app.bus.gecmis if o["tur"] == "bitti"][-1]
    assert bitti["durum"] == "onaylandi" and bitti["korundu"] is True
    assert "karar-bekleniyor" not in [o["tur"] for o in app.bus.gecmis]
    assert (kur.proje / "yeni.txt").exists()


def test_otomatik_koru_gecersiz_deger_reddedilir(kur):
    app, sv, api, _ = kur()
    klasor_sec(api, kur.proje)
    ayar = api("GET", "/api/ayar")[1]
    ayar["otomatik_koru"] = "evet"
    assert api("PUT", "/api/ayar", ayar)[0] == 400
    with pytest.raises(AyarHatasi):
        ayar_coz(ayar)


def test_github_isareti_yalniz_github_origin_icin(tmp_path):
    assert github_deposu_mu(tmp_path) is False  # git deposu yok
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text('[remote "origin"]\n\turl = https://example.com/x/y.git\n', encoding="utf-8")
    assert github_deposu_mu(tmp_path) is False
    (tmp_path / ".git" / "config").write_text('[remote "origin"]\n\turl = git@github.com:bmenderes/x.git\n', encoding="utf-8")
    assert github_deposu_mu(tmp_path) is True


def test_proje_gruplari_github_alani(kur):
    app, sv, api, _ = kur()
    klasor_sec(api, kur.proje)
    gruplar = api("GET", "/api/proje-gruplari")[1]["projeler"]
    assert all(isinstance(g["github"], bool) for g in gruplar)


def test_arayuz_enter_gonderir_sesli_yazma_ve_sade_kenar():
    assert 'id="gonder" style="display:none"' in HTML  # gorunur Gonder dugmesi yok
    assert "ev.key===\"Enter\"&&!ev.shiftKey&&!ev.isComposing" in HTML
    assert 'id="mikDugme"' in HTML and "webkitSpeechRecognition" in HTML and "isSecureContext" in HTML and "r.lang=DIL.yerel" in HTML
    assert "Son görevler" not in HTML  # kenar cubugunda ayri liste yok
    assert "@keyframes don" in HTML and "grup-gh" in HTML
    assert "Hep koru" in HTML and "otomatik_koru" in HTML


def test_yeni_konusma_siniri_listede_birikir(kur):
    app, sv, api, _ = kur()
    klasor_sec(api, kur.proje)
    z = api("POST", "/api/yeni-konusma", {})[1]["zaman"]
    g = [x for x in api("GET", "/api/proje-gruplari")[1]["projeler"] if x["secili"]][0]
    assert g["konusma_basi"] == z and g["konusma_sinirlar"][-1] == z
    assert "konusmaGruplari" in HTML and "konusmaOzeti" in HTML  # kenar cubugu konusma basina tek satir


def test_ciktilar_alt_cerceve_listeyi_kapatmaz():
    assert 'id="ciktiIzle"' in HTML and "async function ciktiAc" in HTML and "function ciktiSekmedeAc" in HTML
    assert 'const p=$("#ciktiListe")' in HTML  # liste kendi kabinde yenilenir, alt cerceve korunur
