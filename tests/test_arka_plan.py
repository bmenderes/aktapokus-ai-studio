"""Penceresiz arka plan modu (`ui --arka-plan`): sunucu pencere olmadan calisir, masaustu kisayolu pencereyi arka plandaki kopyadan ister (belirtec diske yazilmaz),
pencere kapaninca sunucu KAPANMAZ, `--durdur` nazikce kapatir. Testler gercek ~/.aktapokus klasorune ve gercek pencerelere dokunmaz (conftest)."""

import os
import threading
import time

import pytest

from aktapokus_ai_studio import cli, uygulama


def bekle(kosul, sn=15):
    son = time.monotonic() + sn
    while time.monotonic() < son:
        if kosul():
            return True
        time.sleep(0.05)
    return False


@pytest.fixture
def arka_plan(monkeypatch, tmp_path):
    """Arka plan kopyasini bir iplikte calistirir; fixture sonunda durdurur. acilan: arka planin actigi pencere komutlari."""
    acilan = []
    monkeypatch.setattr(uygulama, "tarayici_bul", lambda: "sahte-tarayici.exe")
    monkeypatch.setattr(uygulama, "_kutu", lambda mesaj, ikon: None)
    sonuc = {}
    ip = threading.Thread(target=lambda: sonuc.setdefault("kod", uygulama.arka_plan_calistir(pencere_ac=lambda k: acilan.append(k), bekle_sn=0.05)), daemon=True)
    ip.start()
    assert bekle(lambda: uygulama.arka_plan_pid() == os.getpid()), "arka plan baslamadi"
    yield acilan, sonuc, ip
    uygulama._isaret(uygulama.dur_yolu())
    ip.join(20)
    assert not ip.is_alive()


def test_arka_plan_penceresiz_baslar_ikinci_kopya_baslatilmaz_durdurulunca_temizlenir(arka_plan):
    acilan, sonuc, ip = arka_plan
    assert acilan == []  # pencere ACILMADI
    assert uygulama.kilit_yolu().read_text(encoding="utf-8").strip() == str(os.getpid())  # tek kopya kilidi alindi
    assert uygulama.arka_plan_calistir() == 0 and ip.is_alive()  # ikinci arka plan kopyasi: sessizce 0, ilkine dokunmaz
    assert uygulama.durdur(bekle_sn=15) is True
    ip.join(15)
    assert not ip.is_alive() and sonuc["kod"] == 0
    assert not uygulama.arkaplan_yolu().exists() and not uygulama.kilit_yolu().exists() and not uygulama.dur_yolu().exists()  # isaretler temizlendi
    assert uygulama.arka_plan_pid() is None and uygulama.durdur() is False  # calisan kopya yok


def test_masaustu_kisayolu_arka_plandan_pencere_ister_ikinci_sunucu_baslatmaz(arka_plan):
    acilan, sonuc, ip = arka_plan
    assert uygulama.uygulama_calistir() == 0  # kisayola tiklandi: pencereyi arka plandaki kopya acar
    assert len(acilan) == 1 and acilan[0][0] == "sahte-tarayici.exe" and acilan[0][1].startswith("--app=http://127.0.0.1:")  # arka planin kendi sunucusuna baglanan pencere
    assert not uygulama.pencere_iste_yolu().exists()  # istek tuketildi
    assert "#t=" in acilan[0][1]  # belirtec yalniz pencere komutunda; hicbir dosyaya yazilmadi
    for dosya in uygulama.ayar_dizini().iterdir():
        if dosya.is_file():
            assert "#t=" not in dosya.read_text(encoding="utf-8", errors="ignore"), dosya.name
    assert ip.is_alive()  # sunucu hala calisiyor
    assert uygulama.uygulama_calistir() == 0 and len(acilan) == 2  # pencere kapatilip yeniden tiklanirsa yenisi acilir


def test_pencere_kapaninca_sunucu_kapanmaz_pencere_acikken_yeni_pencere_acilmaz(arka_plan, monkeypatch):
    acilan, sonuc, ip = arka_plan
    uygulama.uygulama_calistir()
    assert len(acilan) == 1
    monkeypatch.setattr(uygulama, "mevcut_pencereyi_one_getir", lambda: True)  # pencere zaten acik: one getirilir, ikincisi acilmaz
    assert uygulama.uygulama_calistir() == 0 and len(acilan) == 1
    time.sleep(0.5)
    assert ip.is_alive() and uygulama.arka_plan_pid() == os.getpid()  # pencere kapansa da (burada: hic baglanti yok) sunucu ayakta


def test_olu_surecten_kalan_arka_plan_dosyasi_yok_sayilir(monkeypatch):
    uygulama._isaret(uygulama.arkaplan_yolu(), "99999999")
    monkeypatch.setattr(uygulama, "surec_canli_mi", lambda pid: False)
    assert uygulama.arka_plan_pid() is None and uygulama.durdur() is False
    uygulama._isaret(uygulama.arkaplan_yolu(), "bozuk")
    assert uygulama.arka_plan_pid() is None


def test_pencere_kopyasi_aciksa_arka_plan_baslamaz(monkeypatch):
    uygulama.kilit_yolu().write_text("424242", encoding="utf-8")
    monkeypatch.setattr(uygulama, "surec_canli_mi", lambda pid: pid == 424242)
    assert uygulama.arka_plan_calistir() == 0 and uygulama.arka_plan_pid() is None  # pencere kopyasinin sunucusuna dokunmadi, ikinci sunucu kurulmadi


def test_cli_bayraklari_ve_otomatik_baslat_arka_plana_gider(monkeypatch):
    cagrilar = []
    monkeypatch.setattr(uygulama, "arka_plan_calistir", lambda klasor=None, port=0, **k: cagrilar.append(("arka", klasor, port)) or 0)
    monkeypatch.setattr(uygulama, "durdur", lambda **k: cagrilar.append("durdur") or True)
    assert cli.main(["ui", "--arka-plan", "--port", "5"]) == 0 and cagrilar == [("arka", None, 5)]
    assert cli.main(["ui", "--durdur"]) == 0 and cagrilar[-1] == "durdur"
    monkeypatch.setattr(uygulama, "durdur", lambda **k: False)
    assert cli.main(["ui", "--durdur"]) == 1  # calisan kopya yoktu
    from aktapokus_ai_studio import otomatik_baslat

    assert "'ui','--arka-plan'" in otomatik_baslat.komut_uret(python="x.exe", kok=uygulama.ayar_dizini())  # acilista baslatma penceresiz modu kullanir
