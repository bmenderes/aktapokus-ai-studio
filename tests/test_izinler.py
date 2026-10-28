"""Genel izinler (Ayarlar > Izinler): tum projelerde 'Keep/Undo' sorulmasin. Varsayilan kapali, yalniz yerel arayuz, projeden okunmaz."""

from pathlib import Path

import pytest

from aktapokus_ai_studio import izinler, uzak
from test_arayuz import bekle, klasor_sec, kur  # noqa: F401  (pytest fixture'lari)

HTML = (Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "web" / "index.html").read_text(encoding="utf-8")


def test_varsayilan_kapali_yazilir_ve_gecersiz_degerler_reddedilir():
    assert izinler.oku() == {"degisiklikleri_koru": False} and izinler.koru() is False
    assert izinler.yaz({"degisiklikleri_koru": True}) == {"degisiklikleri_koru": True} and izinler.koru() is True
    for kotu in ({}, None, [], {"degisiklikleri_koru": "evet"}, {"degisiklikleri_koru": 1}, {"baska": True}, {"degisiklikleri_koru": True, "baska": True}):
        with pytest.raises(izinler.IzinHatasi):
            izinler.yaz(kotu)
    assert izinler.koru() is True  # reddedilenler bir sey degistirmedi
    izinler.dosya_yolu().write_text("{bozuk", encoding="utf-8")
    assert izinler.koru() is False  # bozuk dosya: guvenli yon (kapali)


def test_uzaktan_degistirilemez():
    for yontem in ("GET", "POST", "PUT"):
        assert uzak.politika(yontem, "/api/izinler", uzak.Ayar(yonetim=True)), yontem


def test_api_ve_gorev_bitince_keep_sorulmaz(kur):
    app, sv, api, _ = kur()
    klasor_sec(api, kur.proje)
    assert api("GET", "/api/izinler", None, token=None)[0] == 401
    assert api("GET", "/api/izinler")[1] == {"degisiklikleri_koru": False}
    assert api("POST", "/api/izinler", {"degisiklikleri_koru": "evet"})[0] == 400
    assert api("POST", "/api/izinler", {"degisiklikleri_koru": True})[1] == {"degisiklikleri_koru": True}
    plan = api("POST", "/api/gorev", {"gorev": "b.txt ekle"})[1]
    api("POST", f"/api/gorev/{plan['kosu']}/onayla", {})
    assert bekle(lambda: any(o["tur"] == "bitti" for o in app.bus.gecmis))  # durum 'bitti' olay yayinlanmadan hemen once atanir
    bitti = [o for o in app.bus.gecmis if o["tur"] == "bitti"][-1]
    assert bitti["durum"] == "onaylandi" and bitti["korundu"] is True and (kur.proje / "b.txt").exists()
    assert "karar-bekleniyor" not in [o["tur"] for o in app.bus.gecmis]


def test_arayuz_izinler_sekmesinde_genel_koru_anahtari_var():
    assert '"/api/izinler"' in HTML and "Değişiklikleri her zaman koru" in HTML and 'confirm("Değişiklikler her projede sorulmadan korunacak' in HTML
