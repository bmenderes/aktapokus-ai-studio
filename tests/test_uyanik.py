"""Uyku engeli: uzak erisim acikken bilgisayar uyumasin (Windows SetThreadExecutionState; testlerde sahte)."""

import threading
import time
from pathlib import Path

import pytest

from aktapokus_ai_studio import uyanik, uzak

HTML = (Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "web" / "index.html").read_text(encoding="utf-8")


class SahteWindows:
    def __init__(self, sonuc=1):
        self.cagrilar = []
        self.ipler = []
        self.sonuc = sonuc

    def __call__(self, bayrak):
        self.cagrilar.append(bayrak)
        self.ipler.append(threading.current_thread().name)
        return self.sonuc


def test_ac_kapat_dogru_bayraklarla_ayni_iplikten_ayarlar_ve_eski_haline_doner():
    w = SahteWindows()
    e = uyanik.UykuEngeli(ayarla=w, windows=True)
    assert e.aktif is False and e.ac() is True and e.aktif is True
    assert w.cagrilar == [uyanik.ES_CONTINUOUS | uyanik.ES_SYSTEM_REQUIRED]  # ekran acik kalmasi (ES_DISPLAY_REQUIRED) istenmez
    assert e.ac() is True and len(w.cagrilar) == 1  # tekrar acmak yeni is yapmaz
    e.kapat()
    assert e.aktif is False and w.cagrilar[-1] == uyanik.ES_CONTINUOUS  # bayraklar temizlendi
    assert set(w.ipler) == {"uyku-engeli"}  # durum cagiran ipliğe baglidir: ayarlayan ve birakan ayni arka plan ipligi
    e.kapat()  # ikinci kapatma zararsiz
    assert e.ac() is True and e.aktif is True
    e.kapat()


def test_windows_disinda_ve_hata_durumunda_guvenli():
    w = SahteWindows()
    e = uyanik.UykuEngeli(ayarla=w, windows=False)
    assert e.desteklenir is False and e.ac() is False and e.aktif is False and w.cagrilar == []
    reddeden = uyanik.UykuEngeli(ayarla=SahteWindows(sonuc=0), windows=True)
    assert reddeden.ac() is False and reddeden.aktif is False and "kabul etmedi" in reddeden.hata

    def patlar(_b):
        raise OSError("windll yok")

    k = uyanik.UykuEngeli(ayarla=patlar, windows=True)
    assert k.ac() is False and "OSError" in k.hata
    k.kapat()


def test_uzak_ayarinda_uyanik_varsayilan_kapali_dogrulanir_ve_kalicidir():
    assert uzak.oku().uyanik is False
    assert uzak.guncelle({"uyanik": True}).uyanik is True and uzak.oku().uyanik is True
    with pytest.raises(uzak.UzakHatasi):
        uzak.guncelle({"uyanik": "evet"})
    assert uzak.oku().uyanik is True
    assert "uyanik" in uzak.oku().sozluk()


def test_sunucu_yalniz_dinleyici_calisirken_ve_ayar_istiyorsa_uyku_engeli_acar():
    from aktapokus_ai_studio.arayuz import ArayuzSunucusu, Dinleyici, Uygulama

    w = SahteWindows()
    sv = ArayuzSunucusu(Uygulama())  # baslat() CAGRILMAZ: kapat() bu yuzden cagrilmaz (serve_forever calismayan sunucuda shutdown() sonsuza kadar bekler)
    sv.uyku_engeli = uyanik.UykuEngeli(ayarla=w, windows=True)
    try:
        uzak.guncelle({"uyanik": True})  # testlerde ayar dosyasi gecici (conftest: AKTAPOKUS_UZAK)
        sv.uzak_uygula()  # uzak erisim kapali: dinleyici yok
        assert sv.uyku_engeli.aktif is False
        sv.uzak_ayar = uzak.oku()
        sv.uzak_dinleyici = Dinleyici("100.64.0.1", 47650, frozenset({"100.64.0.1"}))  # dinleyici calisiyor gibi
        sv._uyku_guncelle()
        assert sv.uyku_engeli.aktif is True and sv.uzak_bilgi()["uyanik"]["aktif"] is True
        uzak.guncelle({"uyanik": False})
        sv.uzak_ayar = uzak.oku()
        sv._uyku_guncelle()
        assert sv.uyku_engeli.aktif is False
        sv.uzak_ayar.uyanik = True
        sv._uyku_guncelle()
        assert sv.uyku_engeli.aktif is True
        sv.kapaniyor.set()  # sunucu kapanirken engel birakilir
        sv._uyku_guncelle()
        assert sv.uyku_engeli.aktif is False
    finally:
        sv.uzak_dinleyici = None
        sv.uyku_engeli.kapat()


def test_testler_gercek_uzak_ayar_dosyasina_dokunmaz():
    import os

    assert os.environ.get("AKTAPOKUS_UZAK") and str(uzak.dosya_yolu()) == os.environ["AKTAPOKUS_UZAK"]
    assert ".aktapokus" not in Path(os.environ["AKTAPOKUS_UZAK"]).parts


def test_arayuz_bilgisayar_uyumasin_anahtari_var():
    assert 'kutu("Bilgisayar uyumasın",ay.uyanik,"uyanik"' in HTML and "d.dinleyici.uyanik.desteklenir" in HTML
