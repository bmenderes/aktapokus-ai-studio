import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from aktapokus_ai_studio import uygulama, cli


@pytest.fixture(autouse=True)
def yalitim(tmp_path, monkeypatch):
    """Gercek ~/.aktapokus dosyalarina ve gercek tarayiciya dokunma."""
    monkeypatch.setenv("AKTAPOKUS_UYGULAMA_DIZINI", str(tmp_path / "ayar"))
    monkeypatch.delenv("AKTAPOKUS_TARAYICI", raising=False)
    monkeypatch.setattr(uygulama, "_kutu", lambda mesaj, ikon: None)  # test hicbir zaman gercek mesaj kutusu acmasin


def test_tarayici_ortam_degiskeni_oncelikli(tmp_path, monkeypatch):
    sahte = tmp_path / "tarayici.exe"
    sahte.write_text("")
    monkeypatch.setenv("AKTAPOKUS_TARAYICI", str(sahte))
    assert uygulama.tarayici_bul() == str(sahte)
    monkeypatch.setenv("AKTAPOKUS_TARAYICI", str(tmp_path / "yok.exe"))
    assert uygulama.tarayici_bul() != str(tmp_path / "yok.exe")  # olmayan yol yok sayilir


def test_tarayici_edge_chrome_den_once_aranir(tmp_path, monkeypatch):
    for ad in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        monkeypatch.setenv(ad, str(tmp_path / ad))
    edge = tmp_path / "PROGRAMFILES" / "Microsoft" / "Edge" / "Application" / "msedge.exe"
    chrome = tmp_path / "LOCALAPPDATA" / "Google" / "Chrome" / "Application" / "chrome.exe"
    for d in (edge, chrome):
        d.parent.mkdir(parents=True)
        d.write_text("")
    assert uygulama.tarayici_bul() == str(edge)
    edge.unlink()
    assert uygulama.tarayici_bul() == str(chrome)
    chrome.unlink()
    monkeypatch.setattr(uygulama.shutil, "which", lambda ad: None)
    assert uygulama.tarayici_bul() is None


def test_pencere_komutu_kabuksuz_ve_ayri_profil(tmp_path):
    k = uygulama.pencere_komutu("C:/t/msedge.exe", "http://127.0.0.1:5000/#t=abc", tmp_path / "profil")
    assert k[0] == "C:/t/msedge.exe" and "--app=http://127.0.0.1:5000/#t=abc" in k
    assert f"--user-data-dir={tmp_path / 'profil'}" in k  # kullanicinin normal tarayici profilinden ayri
    assert "--disable-sync" in k  # yoksa Edge uygulama penceresinin yaninda ikinci bir "sync-confirmation" penceresi acar
    assert any(x.startswith("--disable-features=") and "Translate" in x for x in k)
    assert "--no-proxy-server" in k  # yoksa Edge proxy otomatik algilamasinda 24-27 sn takilir (olculdu); pencere yalniz 127.0.0.1'e baglanir


def test_pencere_komutu_proxy_ortami_ile_sistem_proxysine_donulebilir(tmp_path, monkeypatch):
    monkeypatch.setenv("AKTAPOKUS_PROXY", "1")
    assert "--no-proxy-server" not in uygulama.pencere_komutu("C:/t/msedge.exe", "http://127.0.0.1:5000/", tmp_path / "profil")
    monkeypatch.setenv("AKTAPOKUS_PROXY", "0")
    assert "--no-proxy-server" in uygulama.pencere_komutu("C:/t/msedge.exe", "http://127.0.0.1:5000/", tmp_path / "profil")


def test_son_klasor_hatirlanir_ve_silinmisse_yok_sayilir(tmp_path):
    assert uygulama.son_klasoru_oku() is None
    proje = tmp_path / "proje"
    proje.mkdir()
    uygulama.son_klasoru_yaz(str(proje))
    assert uygulama.son_klasoru_oku() == str(proje)
    proje.rmdir()
    assert uygulama.son_klasoru_oku() is None
    uygulama.son_klasoru_yaz(None)  # bos deger dosyayi bozmaz
    (uygulama.ayar_dizini() / "uygulama.json").write_text("{bozuk", encoding="utf-8")
    assert uygulama.son_klasoru_oku() is None


class SahtePencere:
    """Tarayici penceresi: kapat() cagrilana kadar sunucuya 'bagli' sayilir (olay akisi baglantisi)."""

    def __init__(self):
        self.acik = False
        self.komut = None

    def baglanti(self):
        return 1 if self.acik else 0

    def kapat(self):
        self.acik = False


def _calistir(tmp_path, monkeypatch, klasor=None, pencere=None, sure=2.5):
    sahte = tmp_path / "tarayici.exe"
    sahte.write_text("")
    monkeypatch.setenv("AKTAPOKUS_TARAYICI", str(sahte))
    monkeypatch.setattr(uygulama, "sessiz_alt_surecler", lambda: None)  # testte Popen'i kalici degistirme
    pencere = pencere or SahtePencere()
    gorulen = {}

    def ac(komut):
        pencere.komut = komut
        gorulen["komut"] = komut
        pencere.acik = True
        threading.Timer(sure, pencere.kapat).start()
        return None

    kod = {}
    t = threading.Thread(
        target=lambda: kod.setdefault("v", uygulama.uygulama_calistir(klasor, 0, ac, bekle_sn=0.05, baglanti_say=pencere.baglanti, acilis_sn=10, kopma_sn=0.3))
    )
    baslangic = time.monotonic()
    t.start()
    t.join(30)
    assert not t.is_alive(), "pencere kapaninca uygulama sonlanmali"
    assert time.monotonic() - baslangic >= sure * 0.9, "pencere ACIKKEN uygulama calismaya devam etmeli (erken kapanmamali)"
    return kod["v"], gorulen


def test_pencere_kapaninca_uygulama_sonlanir_ve_son_klasor_yazilir(proje, tmp_path, monkeypatch):
    kod, g = _calistir(tmp_path, monkeypatch, klasor=str(proje))
    assert kod == 0
    url = next(a for a in g["komut"] if a.startswith("--app=")).removeprefix("--app=")
    assert url.startswith("http://127.0.0.1:") and "#t=" in url
    assert uygulama.son_klasoru_oku() == str(proje)
    log = (uygulama.ayar_dizini() / "uygulama.log").read_text(encoding="utf-8")
    assert "pencere kapandi" in log
    import urllib.error, urllib.request

    with pytest.raises((urllib.error.URLError, OSError)):  # sunucu gercekten kapandi
        urllib.request.urlopen(url.split("#")[0], timeout=2)


def test_klasor_verilmezse_son_klasor_acilir(proje, tmp_path, monkeypatch):
    uygulama.son_klasoru_yaz(str(proje))
    kod, g = _calistir(tmp_path, monkeypatch, klasor=None)
    assert kod == 0 and uygulama.son_klasoru_oku() == str(proje)


def test_tarayici_yoksa_hata_kutusu_ve_log(tmp_path, monkeypatch):
    monkeypatch.setattr(uygulama, "tarayici_bul", lambda: None)
    kutular = []
    monkeypatch.setattr(uygulama, "hata_goster", lambda m: kutular.append(m) or uygulama.log_yaz("HATA: " + m))
    assert uygulama.uygulama_calistir(None, 0) == 1
    assert kutular and "Edge ya da Chrome" in kutular[0]
    assert "HATA" in (uygulama.ayar_dizini() / "uygulama.log").read_text(encoding="utf-8")


def test_pencere_acilamazsa_sunucu_yine_kapanir(proje, tmp_path, monkeypatch):
    sahte = tmp_path / "t.exe"
    sahte.write_text("")
    monkeypatch.setenv("AKTAPOKUS_TARAYICI", str(sahte))
    monkeypatch.setattr(uygulama, "sessiz_alt_surecler", lambda: None)
    monkeypatch.setattr(uygulama, "hata_goster", lambda m: uygulama.log_yaz("HATA: " + m))
    kapatilan = []
    from aktapokus_ai_studio import arayuz

    asil = arayuz.ArayuzSunucusu.kapat
    monkeypatch.setattr(arayuz.ArayuzSunucusu, "kapat", lambda self: (kapatilan.append(1), asil(self))[1])

    def ac(komut):
        raise OSError("acilamadi")

    assert uygulama.uygulama_calistir(str(proje), 0, ac) == 1
    assert kapatilan == [1]


@pytest.mark.skipif(sys.platform != "win32", reason="CREATE_NO_WINDOW yalniz Windows'ta")
def test_sessiz_alt_surecler_popen_e_pencere_yok_bayragi_ekler():
    orijinal = subprocess.Popen.__init__
    gorulen = {}

    def kayit(self, *a, **k):
        gorulen.clear()
        gorulen.update(k)
        raise RuntimeError("durdur")

    subprocess.Popen.__init__ = kayit  # yama bunu saracak
    try:
        uygulama.sessiz_alt_surecler()
        with pytest.raises(RuntimeError):
            subprocess.Popen(["x"])
        assert gorulen["creationflags"] == uygulama.CREATE_NO_WINDOW
        with pytest.raises(RuntimeError):
            subprocess.Popen(["x"], creationflags=0x200)
        assert gorulen["creationflags"] == 0x200 | uygulama.CREATE_NO_WINDOW  # var olan bayraklar korunur
    finally:
        subprocess.Popen.__init__ = orijinal


def test_cli_uygulama_secenegi_dogru_islevi_cagirir(monkeypatch):
    cagrilar = []
    monkeypatch.setattr(uygulama, "uygulama_calistir", lambda klasor, port: cagrilar.append((klasor, port)) or 0)
    assert cli.main(["ui", "--uygulama", "--klasor", "X", "--port", "7"]) == 0
    assert cagrilar == [("X", 7)]


# ---- tek kopya kilidi ----
@pytest.fixture
def baska_canli_surec():
    """Gercek, calisan baska bir surec (testin kendisi degil)."""
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    yield p
    p.kill()
    p.wait()


def test_kilit_baska_canli_kopya_varsa_alinmaz_olu_kopya_yok_sayilir(baska_canli_surec, tmp_path):
    uygulama.ayar_dizini().mkdir(parents=True, exist_ok=True)
    uygulama.kilit_yolu().write_text(str(baska_canli_surec.pid), encoding="utf-8")
    assert uygulama.kilit_al() is False
    baska_canli_surec.kill()
    baska_canli_surec.wait()
    assert uygulama.kilit_al() is True  # olu surecin kilidi bayat: alinir
    assert uygulama.kilit_yolu().read_text(encoding="utf-8") == str(__import__("os").getpid())
    uygulama.kilit_birak()
    assert not uygulama.kilit_yolu().exists()


def _kilitle(baska_canli_surec, durum=None):
    uygulama.ayar_dizini().mkdir(parents=True, exist_ok=True)
    uygulama.kilit_yolu().write_text(str(baska_canli_surec.pid), encoding="utf-8")
    if durum:
        uygulama.pencere_isaretle(durum)


def test_kapanmakta_olan_kopya_varsa_yeniden_acma_bekler_ve_acilir(baska_canli_surec, monkeypatch):
    """Gercek hata: pencereyi kapatip hemen yeniden acinca 'zaten acik' denip acilmiyordu."""
    monkeypatch.setattr(uygulama, "mevcut_pencereyi_one_getir", lambda: False)  # pencere yok (kapandi)
    _kilitle(baska_canli_surec, "kopuk")
    threading.Timer(0.8, baska_canli_surec.kill).start()
    baslangic = time.monotonic()
    assert uygulama.ikinci_kopya_bekle(azami_sn=10) == "al"
    assert 0.5 < time.monotonic() - baslangic < 6
    uygulama.kilit_birak()


def test_gercek_pencere_varsa_hemen_one_getirilir_beklenmez(baska_canli_surec, monkeypatch):
    monkeypatch.setattr(uygulama, "mevcut_pencereyi_one_getir", lambda: True)
    _kilitle(baska_canli_surec, "bagli")
    baslangic = time.monotonic()
    assert uygulama.ikinci_kopya_bekle(azami_sn=10) == "one"
    assert time.monotonic() - baslangic < 1.0


def test_durum_bagli_gorunse_de_pencere_yoksa_beklenir_gercek_hata(baska_canli_surec, monkeypatch):
    """Gercek Edge: pencere kapandi ama baglanti birkac sn daha 'bagli' gorundu; ikinci istek pes edip kutu gosteriyordu."""
    monkeypatch.setattr(uygulama, "mevcut_pencereyi_one_getir", lambda: False)
    _kilitle(baska_canli_surec, "bagli")
    threading.Timer(1.2, baska_canli_surec.kill).start()  # eski kopya birazdan kapanir
    assert uygulama.ikinci_kopya_bekle(azami_sn=10) == "al"
    uygulama.kilit_birak()


def test_pencere_henuz_aciliyorsa_belirene_kadar_beklenir_ve_one_getirilir(baska_canli_surec, monkeypatch):
    sayac = {"n": 0}

    def pencere():
        sayac["n"] += 1
        return sayac["n"] >= 4  # ilk yoklamalarda pencere yok, sonra belirir

    monkeypatch.setattr(uygulama, "mevcut_pencereyi_one_getir", pencere)
    _kilitle(baska_canli_surec, "aciliyor")
    assert uygulama.ikinci_kopya_bekle(azami_sn=10) == "one"


def test_pencere_hic_yoksa_ve_surec_kapanmiyorsa_azami_sureden_sonra_mesaj(baska_canli_surec, monkeypatch):
    monkeypatch.setattr(uygulama, "mevcut_pencereyi_one_getir", lambda: False)
    _kilitle(baska_canli_surec, "bagli")
    baslangic = time.monotonic()
    assert uygulama.ikinci_kopya_bekle(azami_sn=1.2) == "mesaj"
    assert 1.0 < time.monotonic() - baslangic < 4
    assert not uygulama.devral_var_mi()  # istek temizlenir
    assert not uygulama.pencere_iste_yolu().exists()


def test_telefon_bagliyken_pencere_yoksa_eski_kopyadan_pencere_istenir_gercek_hata(baska_canli_surec, monkeypatch):
    """Gercek hata: pencere kapali, telefondaki tarayici bagli; eski kopya kapanmiyor, kisayol 30 sn sonra 'zaten acik' kutusu gosteriyordu."""
    istek = []

    def pencere():  # eski kopya istegi gorup pencere acana kadar pencere yok
        istek.append(uygulama.pencere_iste_yolu().exists())
        return len(istek) >= 3 and any(istek)

    monkeypatch.setattr(uygulama, "mevcut_pencereyi_one_getir", pencere)
    _kilitle(baska_canli_surec, "bagli")
    assert uygulama.ikinci_kopya_bekle(azami_sn=10) == "one"
    assert any(istek) and not uygulama.pencere_iste_yolu().exists()


def test_acik_kopya_pencere_istegi_gelince_yeni_pencere_acar_ve_kapanmaz(proje, tmp_path, monkeypatch):
    sahte = tmp_path / "t.exe"
    sahte.write_text("")
    monkeypatch.setenv("AKTAPOKUS_TARAYICI", str(sahte))
    monkeypatch.setattr(uygulama, "sessiz_alt_surecler", lambda: None)
    monkeypatch.setattr(uygulama, "mevcut_pencereyi_one_getir", lambda: False)
    pencere, acilan = SahtePencere(), []

    def ac(komut):
        acilan.append(komut)
        pencere.acik = True

    threading.Timer(0.5, uygulama._isaret, [uygulama.pencere_iste_yolu()]).start()
    threading.Timer(1.5, pencere.kapat).start()
    kod = uygulama.uygulama_calistir(str(proje), 0, ac, bekle_sn=0.05, baglanti_say=pencere.baglanti, acilis_sn=10, kopma_sn=0.3)
    assert kod == 0 and len(acilan) == 2 and acilan[0] == acilan[1]  # ayni sunucuya ikinci pencere; istek tuketildi
    assert not uygulama.pencere_iste_yolu().exists()


def test_pencere_bekle_yeni_acma_istegi_gelince_kopma_toleransini_beklemeden_kapanir():
    sira = {"n": 0}

    def sayac():
        sira["n"] += 1
        return 1 if sira["n"] <= 3 else 0  # 3 yoklama bagli, sonra kopuk

    saat = SahteSaat()

    def erken():
        return sira["n"] >= 6  # kopmadan 3 yoklama sonra yeni acma istegi

    assert uygulama.pencere_bekle(sayac, 0, 90, 1000, saat, erken_cik=erken) == "kapandi"
    assert sira["n"] <= 8, "yeni acma istegi geldi ama 1000 sn'lik toleransi bekledi"


def test_pencere_bekle_erken_cikis_yalniz_pencere_gorulmus_ve_kopuksa_isler():
    saat = SahteSaat()
    sira = {"n": 0}

    def hic_baglanmadi():
        sira["n"] += 1
        return 0

    assert uygulama.pencere_bekle(hic_baglanmadi, 0, 5, 5, saat, erken_cik=lambda: True) == "baglanmadi"  # hic gorulmediyse erken cikis yok


def test_kopuk_kopyaya_devral_istegi_yazilir_ve_sonunda_temizlenir(baska_canli_surec, monkeypatch):
    monkeypatch.setattr(uygulama, "mevcut_pencereyi_one_getir", lambda: False)
    _kilitle(baska_canli_surec, "kopuk")
    yazilan = []
    asil = uygulama.devral_iste
    monkeypatch.setattr(uygulama, "devral_iste", lambda: (yazilan.append(1), asil())[1])
    assert uygulama.ikinci_kopya_bekle(azami_sn=1.2) == "mesaj"  # surec kapanmiyor: sure doldu
    assert yazilan and not uygulama.devral_var_mi()


def test_acik_pencere_varsa_mesaj_kutusu_yerine_pencere_one_getirilir(baska_canli_surec, tmp_path, monkeypatch):
    sahte = tmp_path / "t.exe"
    sahte.write_text("")
    monkeypatch.setenv("AKTAPOKUS_TARAYICI", str(sahte))
    _kilitle(baska_canli_surec, "bagli")
    kutular, one = [], []
    monkeypatch.setattr(uygulama, "bilgi_goster", lambda m: kutular.append(m))
    monkeypatch.setattr(uygulama, "mevcut_pencereyi_one_getir", lambda: one.append(1) or True)
    assert uygulama.uygulama_calistir(None, 0, lambda k: (_ for _ in ()).throw(AssertionError("pencere acilmamali"))) == 0
    assert one and kutular == []  # pencere one getirildi, kutu YOK
    one.clear()
    monkeypatch.setattr(uygulama, "KAPANMA_BEKLEME_SN", 0.6)
    monkeypatch.setattr(uygulama, "mevcut_pencereyi_one_getir", lambda: one.append(1) or False)  # pencere bulunamazsa eski mesaj
    assert uygulama.uygulama_calistir(None, 0, lambda k: None) == 0 and kutular and "zaten acik" in kutular[0]


def test_kilit_bozuk_dosya_ve_baskasinin_kilidini_silmez(baska_canli_surec):
    uygulama.ayar_dizini().mkdir(parents=True, exist_ok=True)
    uygulama.kilit_yolu().write_text("sayi degil", encoding="utf-8")
    assert uygulama.kilit_al() is True
    uygulama.kilit_yolu().write_text(str(baska_canli_surec.pid), encoding="utf-8")
    uygulama.kilit_birak()  # baskasinin kilidi: dokunulmaz
    assert uygulama.kilit_yolu().read_text(encoding="utf-8") == str(baska_canli_surec.pid)


def test_ikinci_kopya_sunucu_baslatmadan_cikar(baska_canli_surec, tmp_path, monkeypatch):
    sahte = tmp_path / "t.exe"
    sahte.write_text("")
    monkeypatch.setenv("AKTAPOKUS_TARAYICI", str(sahte))
    uygulama.ayar_dizini().mkdir(parents=True, exist_ok=True)
    uygulama.kilit_yolu().write_text(str(baska_canli_surec.pid), encoding="utf-8")
    kutular = []
    monkeypatch.setattr(uygulama, "bilgi_goster", lambda m: kutular.append(m))
    from aktapokus_ai_studio import arayuz

    monkeypatch.setattr(uygulama, "mevcut_pencereyi_one_getir", lambda: False)
    monkeypatch.setattr(uygulama, "KAPANMA_BEKLEME_SN", 0.6)
    baslayan = []
    def baslat(self):  # kilit denetimi atlanirsa burasi cagrilir: hemen OSError (sunucu hic baslamadigi icin kapat() beklemez)
        baslayan.append(1)
        raise OSError("test")

    monkeypatch.setattr(arayuz.ArayuzSunucusu, "baslat", baslat)
    assert uygulama.uygulama_calistir(None, 0, lambda k: (_ for _ in ()).throw(AssertionError("pencere acilmamali"))) == 0
    assert baslayan == [] and kutular and "zaten acik" in kutular[0]
    assert uygulama.kilit_yolu().read_text(encoding="utf-8") == str(baska_canli_surec.pid)  # kilide dokunulmadi


def test_normal_calismada_kilit_alinir_ve_cikista_birakilir(proje, tmp_path, monkeypatch):
    gorulen = []
    asil = uygulama.kilit_al
    monkeypatch.setattr(uygulama, "kilit_al", lambda: (gorulen.append("al"), asil())[1])
    kod, g = _calistir(tmp_path, monkeypatch, klasor=str(proje), sure=0.4)
    assert kod == 0 and gorulen == ["al"]
    assert not uygulama.kilit_yolu().exists()  # pencere kapaninca kilit birakildi


# ---- kapanis algisi: sayfa baglantisina dayanir (tarayici sureci devredip cikabilir) ----
class SahteSaat:
    def __init__(self, adim=1.0):
        self.t, self.adim = 0.0, adim

    def __call__(self):
        self.t += self.adim
        return self.t


def _bekle(dizi, acilis=90, kopma=20, adim=1.0):
    """dizi: her yoklamada donecek baglanti sayilari; bitince 0 doner."""
    kalan = list(dizi)
    return uygulama.pencere_bekle(lambda: kalan.pop(0) if kalan else 0, 0, acilis, kopma, SahteSaat(adim))


def test_pencere_bekle_baglandiktan_sonra_kopma_suresi_dolunca_kapandi():
    assert _bekle([0, 0, 1, 1, 1], kopma=5) == "kapandi"


def test_pencere_bekle_kisa_kopmalari_tolere_eder():
    # 3 yoklamalik kopma, tolerans 5: pencere yenilendi sayilir; ancak SONDAKI uzun kopmada kapanir
    assert _bekle([1, 1, 0, 0, 0, 1, 1], kopma=5) == "kapandi"
    kalan = [1, 0, 0, 0, 1, 1, 1, 1, 1, 1]
    gorulen_sonuc = {}
    uyg_sayac = lambda: kalan.pop(0) if kalan else 0  # noqa: E731
    gorulen_sonuc["v"] = uygulama.pencere_bekle(uyg_sayac, 0, 90, 5, SahteSaat())
    assert gorulen_sonuc["v"] == "kapandi" and kalan == []  # 10 yoklamanin HEPSI tuketildi: arada erken kapanmadi


def test_pencere_bekle_hic_baglanmazsa_baglanmadi_ve_baglantidan_once_kapandi_denmez():
    assert _bekle([], acilis=10) == "baglanmadi"
    # tolerans acilis suresinden KISA olsa bile hic baglanmamis pencere 'kapandi' sayilmaz
    assert _bekle([], acilis=10, kopma=2) == "baglanmadi"


def test_tarayici_sureci_hemen_cikarsa_bile_sunucu_baglanti_suresince_acik_kalir(proje, tmp_path, monkeypatch):
    """GERCEK HATA: Edge ayni profille calisan bir surece devredip aninda cikti; uygulama bunu 'pencere kapandi' sanip sunucuyu kapatti."""
    sahte = tmp_path / "t.exe"
    sahte.write_text("")
    monkeypatch.setenv("AKTAPOKUS_TARAYICI", str(sahte))
    monkeypatch.setattr(uygulama, "sessiz_alt_surecler", lambda: None)
    pencere = SahtePencere()

    def devir(komut):
        pencere.acik = True
        threading.Timer(2.0, pencere.kapat).start()
        return SimpleNamespace(poll=lambda: 0, returncode=0)  # surec ANINDA bitti (devir)

    baslangic = time.monotonic()
    kod = uygulama.uygulama_calistir(str(proje), 0, devir, bekle_sn=0.05, baglanti_say=pencere.baglanti, acilis_sn=10, kopma_sn=0.3)
    assert kod == 0 and time.monotonic() - baslangic >= 1.9


def test_hic_baglanmayan_pencere_hata_verir_ve_sunucu_kapanir(proje, tmp_path, monkeypatch):
    sahte = tmp_path / "t.exe"
    sahte.write_text("")
    monkeypatch.setenv("AKTAPOKUS_TARAYICI", str(sahte))
    monkeypatch.setattr(uygulama, "sessiz_alt_surecler", lambda: None)
    hatalar = []
    monkeypatch.setattr(uygulama, "hata_goster", lambda m: hatalar.append(m) or uygulama.log_yaz("HATA: " + m))
    assert uygulama.uygulama_calistir(str(proje), 0, lambda k: None, bekle_sn=0.05, baglanti_say=lambda: 0, acilis_sn=0.6, kopma_sn=0.3) == 1
    assert hatalar and "baglanamadi" in hatalar[0]
    assert not uygulama.kilit_yolu().exists()


def test_gercek_olay_akisi_baglantisi_sayilir_ve_kopunca_uygulama_kapanir(proje, tmp_path, monkeypatch):
    """Tarayici yerine gercek bir HTTP istemcisi /api/olaylar'a baglanir: sayac gercek `app.bus.aboneler` ile calisir."""
    import http.client
    import re

    sahte = tmp_path / "t.exe"
    sahte.write_text("")
    monkeypatch.setenv("AKTAPOKUS_TARAYICI", str(sahte))
    monkeypatch.setattr(uygulama, "sessiz_alt_surecler", lambda: None)
    bitir = threading.Event()
    baglandi = threading.Event()

    def sayfa(komut):
        url = next(a for a in komut if a.startswith("--app=")).removeprefix("--app=")
        port = int(re.search(r":(\d+)/", url).group(1))
        token = url.split("#t=")[1]

        def oku():
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            c.request("GET", "/api/olaylar?son=0", headers={"X-Aktapokus-Token": token})
            r = c.getresponse()
            assert r.status == 200
            baglandi.set()
            bitir.wait(10)
            c.close()  # pencere kapandi: baglanti kopar

        threading.Thread(target=oku, daemon=True).start()
        threading.Timer(2.0, bitir.set).start()

    baslangic = time.monotonic()
    kod = uygulama.uygulama_calistir(str(proje), 0, sayfa, bekle_sn=0.05, acilis_sn=15, kopma_sn=0.5)
    assert baglandi.is_set() and kod == 0
    assert not uygulama.pencere_yolu().exists()  # cikista pencere isareti silinir
    assert time.monotonic() - baslangic >= 1.9  # baglanti suresince acik kaldi, kopunca kapandi


def test_olay_akisi_dahili_aboneler_tarayici_sayisina_girmez():
    from aktapokus_ai_studio.arayuz import OlayAkisi

    bus = OlayAkisi()
    assert bus.tarayici_sayisi() == 0
    dahili, _ = bus.abone_ol(0, dahili=True)
    assert bus.tarayici_sayisi() == 0 and len(bus.aboneler) == 1
    sayfa, _ = bus.abone_ol(0)
    assert bus.tarayici_sayisi() == 1
    bus.ayril(sayfa)
    assert bus.tarayici_sayisi() == 0
    bus.ayril(dahili)
    assert bus.aboneler == [] and bus.dahili == set()


def test_telegram_botu_acikken_de_pencere_kapaninca_uygulama_kapanir(proje, tmp_path, monkeypatch):
    """Gerçek hata: içteki Telegram botu olay akisine abone oldugu icin pencere kapansa da uygulama hic sonlanmiyordu."""
    import http.client
    import re

    from aktapokus_ai_studio import arayuz

    sahte = tmp_path / "t.exe"
    sahte.write_text("")
    monkeypatch.setenv("AKTAPOKUS_TARAYICI", str(sahte))
    monkeypatch.setattr(uygulama, "sessiz_alt_surecler", lambda: None)
    asil = arayuz.OlayAkisi.__init__

    def bot_gibi(self, *a, **k):
        asil(self, *a, **k)
        self.abone_ol(0, dahili=True)  # Telegram botunun aboneligi

    monkeypatch.setattr(arayuz.OlayAkisi, "__init__", bot_gibi)
    bitir = threading.Event()

    def sayfa(komut):
        url = next(a for a in komut if a.startswith("--app=")).removeprefix("--app=")
        port = int(re.search(r":(\d+)/", url).group(1))
        token = url.split("#t=")[1]

        def oku():
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            c.request("GET", "/api/olaylar?son=0", headers={"X-Aktapokus-Token": token})
            assert c.getresponse().status == 200
            bitir.wait(10)
            c.close()

        threading.Thread(target=oku, daemon=True).start()
        threading.Timer(1.0, bitir.set).start()

    sonuc: dict = {}
    t = threading.Thread(target=lambda: sonuc.setdefault("kod", uygulama.uygulama_calistir(str(proje), 0, sayfa, bekle_sn=0.05, acilis_sn=15, kopma_sn=0.5)), daemon=True)
    t.start()
    t.join(20)
    assert not t.is_alive(), "pencere kapandi ama uygulama sonlanmadi (dahili abone pencere sayacini kirletiyor)"
    assert sonuc["kod"] == 0


def test_tolerans_SON_baglantidan_itibaren_sayilir_ilk_baglantidan_degil():
    """Uzun suredir bagli bir pencere kapaninca HEMEN kapandi denmemeli; kopma_sn kadar beklenmeli."""
    cagri = {"n": 0}
    dizi = [1] * 10  # 10 yoklama boyunca bagli, sonra 0

    def sayac():
        cagri["n"] += 1
        return dizi.pop(0) if dizi else 0

    sonuc = uygulama.pencere_bekle(sayac, 0, 90, 5, SahteSaat())
    assert sonuc == "kapandi"
    assert cagri["n"] >= 10 + 5, f"baglanti koptuktan sonra toleransi beklemeden kapandi ({cagri['n']} yoklama)"


def test_sayfa_cevirme_ve_simge_isaretlerini_icerir():
    html = (Path(__file__).parent.parent / "aktapokus_ai_studio" / "web" / "index.html").read_text(encoding="utf-8")
    assert '<html lang="tr" translate="no">' in html and '<meta name="google" content="notranslate">' in html


def test_uzak_erisim_kurulumu_yavas_olsa_da_pencere_hemen_acilir(proje, tmp_path, monkeypatch):
    """GERCEK HATA: uzak erisim + https aciksa `tailscale serve` 15 sn'ye kadar bekliyor ve pencere o kadar gec aciliyordu (kullanici kisayola iki kez tikliyordu)."""
    from aktapokus_ai_studio import arayuz

    cagrildi = threading.Event()

    def yavas(self):
        cagrildi.set()
        time.sleep(3)
        return {}

    monkeypatch.setattr(arayuz.ArayuzSunucusu, "uzak_uygula", yavas)
    t0 = time.monotonic()
    acilis = {}
    sahte = tmp_path / "tarayici.exe"
    sahte.write_text("")
    monkeypatch.setenv("AKTAPOKUS_TARAYICI", str(sahte))
    monkeypatch.setattr(uygulama, "sessiz_alt_surecler", lambda: None)

    def ac(komut):
        acilis["sn"] = time.monotonic() - t0

    kod = uygulama.uygulama_calistir(str(proje), 0, ac, bekle_sn=0.05, baglanti_say=lambda: 0, acilis_sn=0.3, kopma_sn=0.2)
    assert kod == 1  # hic baglanti olmadi: acilis zaman asimi (bu testin konusu degil)
    assert cagrildi.wait(5), "uzak kurulum yine de calistirilmali"
    assert acilis["sn"] < 2.0, f"pencere uzak kurulumu beklememeli ({acilis['sn']:.1f} sn)"
