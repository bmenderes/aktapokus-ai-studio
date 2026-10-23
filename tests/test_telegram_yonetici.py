import json
import threading
import time

import pytest

from aktapokus_ajan import telegram_yonetici as ty
from aktapokus_ajan.arayuz import ArayuzSunucusu, Uygulama
from aktapokus_ajan.telegram_yonetici import TelegramYoneticisi, YoneticiHatasi
from conftest import SahteCalistirici
from sahte_telegram import TOKEN, SahteTelegram
from test_arayuz import BASARILI, Istemci, yaz

UID = 42


def bekle(kosul, sn=10):
    son = time.monotonic() + sn
    while time.monotonic() < son:
        if kosul():
            return True
        time.sleep(0.05)
    return False


@pytest.fixture
def kur(tmp_path):
    acik = []

    def f(token=TOKEN, izinli=(), kokler=()):
        fake = SahteTelegram()
        app = Uygulama(calistirici_uret=lambda ad: SahteCalistirici({"kodcu": yaz, "test": BASARILI}))
        ayar = tmp_path / "telegram.json"
        if izinli or kokler:
            ayar.write_text(json.dumps({"izinli": list(izinli), "icerik_gonder": False, "kokler": [str(k) for k in kokler]}), encoding="utf-8")
        y = TelegramYoneticisi(app, taban=fake.taban, ayar_yolu=ayar, token_fn=lambda: token, yoklama_sn=1)
        app.telegram = y
        acik.append((y, fake))
        return y, fake, app, ayar

    yield f
    for y, fake in acik:
        y.durdur()
        if y._is:
            y._is.join(8)
        fake.kapat()


def test_token_yoksa_anlasilir_hata_ve_token_yazma_yonergesi(kur):
    y, fake, app, _ = kur(token=None)
    d = y.durum()
    assert d["token_var"] is False and not d["calisiyor"]
    with pytest.raises(YoneticiHatasi, match="telegram.token"):
        y.baslat()


def test_baslat_durdur_gercek_yoklama_ve_token_sizmaz(kur):
    y, fake, app, _ = kur()
    d = y.baslat()
    assert d["calisiyor"] and d["bot"] and d["token_var"]
    assert any(m == "getMe" for m, _ in fake.cagrilar)
    assert bekle(lambda: any(m == "getUpdates" and v.get("offset", 0) != -1 for m, v in fake.cagrilar))  # bot gercekten yokluyor
    with pytest.raises(YoneticiHatasi, match="zaten"):
        y.baslat()
    assert TOKEN not in json.dumps(y.durum()) and all(TOKEN not in satir for satir in y.log_tamponu)
    y.durdur()
    assert y.durum()["durduruluyor"] or not y.durum()["calisiyor"]
    assert bekle(lambda: not y._canli(), sn=15)  # is parcacigi sonunda biter
    assert y.durum()["calisiyor"] is False


def test_durdurulurken_yeniden_baslatma_reddedilir(kur):
    y, fake, app, _ = kur()
    y.baslat()
    y.durdur()
    if y._canli():  # uzun yoklama bitene kadar: ikinci bir yoklayici (Telegram 409) baslatilmamali
        with pytest.raises(YoneticiHatasi, match="durduruluyor"):
            y.baslat()


def test_gecersiz_token_baslatmayi_reddeder_ve_hata_gosterir(kur):
    y, fake, app, _ = kur()
    fake.token = "baska-token"  # sahte sunucu bu token'i artik gecerli saymaz
    with pytest.raises(YoneticiHatasi, match="doğrulanamadı"):
        y.baslat()
    d = y.durum()
    assert d["hata"] and "doğrulanamadı" in d["hata"] and not d["calisiyor"]
    assert TOKEN not in d["hata"] and TOKEN not in json.dumps(d)


def test_eslesmis_kullanici_yoksa_eslestirme_kodu_gelir_varsa_gelmez_zorla_yeni_kod(kur):
    y, fake, app, _ = kur()
    d = y.baslat()
    e = d["eslestirme"]
    assert e and e["komut"] == f"/eslestir {e['kod']}" and e["kalan_sn"] > 0
    y2, fake2, app2, _ = kur(izinli=(UID,))
    assert y2.baslat()["eslestirme"] is None  # eslesmis: kod yok
    assert y2.yeni_eslestirme()["eslestirme"]["kod"]  # ama bilgisayardan ikinci cihaz icin yeni kod uretilebilir


def test_yeni_eslestirme_bot_calismiyorsa_reddedilir(kur):
    y, fake, app, _ = kur()
    with pytest.raises(YoneticiHatasi, match="başlatın"):
        y.yeni_eslestirme()


def test_otomatik_ayar_kalici_ve_diger_anahtarlari_korur(kur, tmp_path):
    y, fake, app, _ = kur()
    ty.arayuz_ayar_yaz(baska="deger")
    assert y.otomatik_ayarla(True)["otomatik"] is True
    assert ty.arayuz_ayar_oku() == {"baska": "deger", "telegram_otomatik": True}  # birlestirir, ezmez
    assert y.otomatik_ayarla(False)["otomatik"] is False


def test_otomatik_baslat_yalniz_ayar_acik_ve_token_varsa(kur):
    y, fake, app, _ = kur()
    y.otomatik_baslat()
    time.sleep(0.3)
    assert not y._canli()  # ayar kapali: baslamaz
    y.otomatik_ayarla(True)
    y.otomatik_baslat()
    assert bekle(y._canli, sn=8) and y.durum()["calisiyor"]
    y2, fake2, app2, _ = kur(token=None)
    y2.otomatik_ayarla(True)
    y2.otomatik_baslat()  # token yok: hata gunluge yazilir, istisna firlatmaz
    assert bekle(lambda: any("Otomatik başlatma başarısız" in s for s in y2.log_tamponu), sn=5)


def test_kok_ekle_sil_calisan_bota_yansir_ve_guvensiz_klasor_reddedilir(kur, tmp_path):
    y, fake, app, ayar = kur()
    kok = tmp_path / "projeler"
    kok.mkdir()
    d = y.kok_ekle(str(kok))
    assert str(kok.resolve()).lower() in [k.lower() for k in d["kokler"]]
    y.baslat()
    assert y._bot.ayar["kokler"] and y.kok_sil(str(kok.resolve()))["kokler"] == []
    assert y._bot.ayar["kokler"] == []  # calisan bot yeni durumu hemen gorur
    with pytest.raises(YoneticiHatasi, match="yok"):
        y.kok_sil("C:/olmayan")
    with pytest.raises(YoneticiHatasi):
        y.kok_ekle("goreli/yol")  # tam yol olmayan/guvensiz klasor reddedilir


def test_http_uclari_belirtec_ister_ve_yanit_token_icermez(tmp_path):
    fake = SahteTelegram()
    app = Uygulama()
    app.telegram = TelegramYoneticisi(app, taban=fake.taban, ayar_yolu=tmp_path / "t.json", token_fn=lambda: TOKEN, yoklama_sn=1)
    sv = ArayuzSunucusu(app)
    sv.baslat()
    try:
        api = Istemci(sv)
        st, d = api("GET", "/api/telegram")
        assert st == 200 and d["token_var"] and not d["calisiyor"]
        st, d = api("POST", "/api/telegram/baslat", {})
        assert st == 200 and d["calisiyor"] and TOKEN not in json.dumps(d)
        assert api("POST", "/api/telegram/baslat", {})[0] == 400  # zaten calisiyor
        assert api("POST", "/api/telegram/otomatik", {"acik": True})[1]["otomatik"] is True
        assert api("POST", "/api/telegram/yok", {})[0] == 404
        assert Istemci(sv, token="yanlis")("POST", "/api/telegram/baslat", {})[0] == 401
        assert api("POST", "/api/telegram/durdur", {})[0] == 200
    finally:
        app.telegram.durdur()
        if app.telegram._is:
            app.telegram._is.join(8)
        sv.kapat()
        fake.kapat()


def test_gunluk_token_icerse_bile_maskeler(kur):
    """Bot/api katmani token'i zaten temizler; bu son savunma hatti: gunluge yazilan HERHANGI bir metindeki token maskelenir."""
    y, fake, app, _ = kur()
    y._log(f"beklenmedik hata: https://api.telegram.org/bot{TOKEN}/getUpdates")
    satir = y.log_tamponu[-1]
    assert TOKEN not in satir and "[TOKEN]" in satir
    assert TOKEN not in json.dumps(y.durum())
