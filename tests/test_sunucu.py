import copy
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from aktapokus_ajan import guard
from aktapokus_ajan.config import BILINEN_CALISTIRICILAR, VARSAYILAN_AYAR, ayar_coz
from aktapokus_ajan.pipeline import calistir_hat
from aktapokus_ajan.runners import calistirici_olustur, hepsini_kapat
from aktapokus_ajan.sunucu import Istemci, Sunucu, SunucuCalistirici, SunucuHatasi, mesajlardan_metin, model_coz
from aktapokus_ajan import sunucu as sunucu_modulu
from sahte_sunucu import SahteSunucu

SAHTE = str(Path(__file__).with_name("sahte_sunucu.py"))


@pytest.fixture
def sahte():
    s = SahteSunucu()
    yield s
    s.kapat()


def istemci_of(s, parola="p"):
    return Istemci(s.taban, parola, zaman_asimi=5)


def test_model_coz():
    assert model_coz(None) is None and model_coz("") is None
    assert model_coz("opencode/deepseek-v4.1-flash-free") == {"providerID": "opencode", "id": "deepseek-v4.1-flash-free"}
    assert model_coz("openrouter/anthropic/claude-x#hizli") == {"providerID": "openrouter", "id": "anthropic/claude-x", "variant": "hizli"}
    for kotu in ("duz-ad", "/model", "saglayici/"):
        with pytest.raises(SunucuHatasi):
            model_coz(kotu)


def test_istemci_kimlik_bilgi_oturum(sahte):
    assert istemci_of(sahte).bilgi()["version"].startswith("2.0.30")
    with pytest.raises(SunucuHatasi, match="401"):
        istemci_of(sahte, parola="yanlis").bilgi()
    i = istemci_of(sahte)
    sid = i.oturum_olustur("/proje", model="opencode/m1", agent="build", baslik="t")
    o = sahte.durum.oturumlar[sid]
    assert o["dir"] == "/proje" and o["model"] == {"providerID": "opencode", "id": "m1"} and o["agent"] == "build" and o["title"] == "t"
    sid2 = i.oturum_olustur("/proje")
    assert sahte.durum.oturumlar[sid2]["model"] is None  # verilmeyen alan gonderilmez


def test_istemci_hatalari_anlamli(sahte):
    i = istemci_of(sahte)
    with pytest.raises(SunucuHatasi, match="InvalidRequestError.*bilinmeyen saglayici"):
        i.oturum_olustur("/p", model="yok/x")
    with pytest.raises(SunucuHatasi, match="SessionNotFoundError"):
        i.oturum_al("ses_999")
    sahte.kapat()
    with pytest.raises(SunucuHatasi, match="ulasilamadi"):
        i.bilgi()
    with pytest.raises(SunucuHatasi):
        Istemci("http://127.0.0.1:1", "p", zaman_asimi=1).bilgi()


def test_izin_karari_dogrulanir(sahte):
    with pytest.raises(SunucuHatasi, match="Gecersiz izin"):
        istemci_of(sahte).izin_yanitla("s", "r", "belki")


def test_mesajlardan_metin_siralama_ve_filtre():
    m = [
        {"type": "idle"},
        {"type": "assistant", "time": {"created": 2}, "content": [{"type": "reasoning", "text": "gizli dusunce"}, {"type": "text", "text": "ikinci"}]},
        {"type": "assistant", "time": {"created": 1}, "content": [{"type": "tool", "name": "x"}, {"type": "text", "text": "  birinci "}, {"type": "text", "text": "   "}]},
        {"type": "user", "text": "istem"},
    ]
    assert mesajlardan_metin(m) == "birinci\nikinci"
    assert mesajlardan_metin([]) == ""


def calistirici(sahte, **kw):
    return SunucuCalistirici(istemci=istemci_of(sahte), yoklama_sn=0.05, **kw)


def test_calistir_basarili(sahte, tmp_path):
    r = calistirici(sahte).calistir("gorev metni", tmp_path, model="opencode/m1", agent="build")
    assert r.ok and r.metin == "Dosyayi olusturuyorum.\nBitti.\nSONUC: BASARILI"  # reasoning haric, zaman sirali
    assert (r.token_girdi, r.token_cikti, r.token_onbellek) == (100, 25, 50)  # cikti = output + reasoning
    o = next(iter(sahte.durum.oturumlar.values()))
    assert o["dir"] == str(tmp_path) and o["istemler"] == ["gorev metni"] and o["model"]["id"] == "m1"


def test_calistir_basarisiz_outcome(tmp_path):
    s = SahteSunucu(davranis="basarisiz")
    try:
        r = calistirici(s).calistir("g", tmp_path)
        assert not r.ok and "outcome='failed'" in r.hata
    finally:
        s.kapat()


def test_calistir_zaman_asimi_durdurur(tmp_path):
    s = SahteSunucu(davranis="takili")
    try:
        r = calistirici(s).calistir("g", tmp_path, zaman_asimi_sn=1)
        assert not r.ok and "Zaman asimi (1 sn)" in r.hata
        assert any(c[0] == "INTERRUPT" for c in s.durum.cagrilar)  # sunucudaki is gercekten durduruldu
    finally:
        s.kapat()


def test_izin_istegi_reddedilir_ve_is_devam_eder(tmp_path):
    s = SahteSunucu(davranis="izin")
    try:
        r = calistirici(s).calistir("g", tmp_path)
        assert r.ok
        assert s.durum.yanitlar and s.durum.yanitlar[0][2]["decision"] == "reject"
        assert "otomatik" in s.durum.yanitlar[0][2]["message"]
    finally:
        s.kapat()


def test_izin_karari_ayarlanabilir(tmp_path):
    s = SahteSunucu(davranis="izin")
    try:
        calistirici(s, izin_karari="once").calistir("g", tmp_path)
        assert s.durum.yanitlar[0][2]["decision"] == "once"
    finally:
        s.kapat()


def test_gecersiz_istem_ve_model_sunucuya_gitmeden_hata(sahte, tmp_path):
    c = calistirici(sahte)
    assert not c.calistir("   ", tmp_path).ok and not sahte.durum.oturumlar
    r = c.calistir("g", tmp_path, model="yok/x")
    assert not r.ok and "bilinmeyen saglayici" in r.hata


def test_ilerleme_olaylari_iletilir(sahte, tmp_path):
    olaylar = []
    calistirici(sahte, ilerleme=olaylar.append).calistir("g", tmp_path)
    time.sleep(0.5)
    turler = [o["tur"] for o in olaylar]
    assert "metin" in turler and "bitti" in turler
    assert next(o for o in olaylar if o["tur"] == "bitti")["durum"] == "succeeded"


def test_es_zamanli_baslat_tek_surec_baslatir(tmp_path):
    """Gercek hata: arayuz iki istegi ayni anda atinca (saglayicilar + modeller) iki OpenCode sureci basladi; ilki yetim kaldi
    ve taze veri klasorunde ikisi birbirini cokertti."""
    import threading

    sv = Sunucu(komut_oneki=[sys.executable, SAHTE], baslangic_klasoru=tmp_path, hazir_zaman_asimi=30)
    baslayan = []
    asil = sunucu_modulu.subprocess.Popen

    def sayan(*a, **k):
        baslayan.append(1)
        return asil(*a, **k)

    sunucu_modulu.subprocess.Popen = sayan
    sonuclar = []
    try:
        isler = [threading.Thread(target=lambda: sonuclar.append(sv.baslat())) for _ in range(4)]
        for t in isler:
            t.start()
        for t in isler:
            t.join(40)
        assert len(baslayan) == 1 and len(sonuclar) == 4 and all(i is sonuclar[0] for i in sonuclar)
    finally:
        sunucu_modulu.subprocess.Popen = asil
        sv.kapat()


def test_sunucu_sureci_baslat_kapat(tmp_path):
    sv = Sunucu(komut_oneki=[sys.executable, SAHTE], baslangic_klasoru=tmp_path, hazir_zaman_asimi=30)
    i = sv.baslat()
    try:
        assert i.bilgi()["version"].startswith("2.0.30")
        assert sv.baslat() is i  # ikinci cagri ayni sunucuyu kullanir
        port = i.taban.rsplit(":", 1)[1]
        cmd = " ".join(sv.islem.args)
        assert "--hostname 127.0.0.1" in cmd and f"--port {port}" in cmd
        parola = i._kimlik  # parola komut satirinda gorunmemeli
        import base64

        gercek = base64.b64decode(parola.split()[1]).decode().split(":", 1)[1]
        assert gercek and gercek not in cmd
    finally:
        sv.kapat()
    assert sv.islem is None
    with pytest.raises(SunucuHatasi):
        i.bilgi()  # surec gercekten oldu


@pytest.mark.skipif(sys.platform != "win32", reason="job nesnesi yalniz Windows'ta")
def test_ebeveyn_zorla_olunce_sunucu_yetim_kalmaz(tmp_path):
    """Gercek denemede arayuz zorla kapatilinca OpenCode sunucusu yetim kaldi; job nesnesi bunu onler."""
    kok = Path(__file__).resolve().parent.parent
    betik = (
        "import sys,time\n"
        f"sys.path.insert(0, {str(kok)!r})\n"
        "from aktapokus_ajan.sunucu import Sunucu\n"
        f"sv = Sunucu(komut_oneki=[sys.executable, {SAHTE!r}], baslangic_klasoru={str(tmp_path)!r}, hazir_zaman_asimi=30)\n"
        "sv.baslat(); print(sv.islem.pid, flush=True); time.sleep(120)\n"
    )
    ebeveyn = subprocess.Popen([sys.executable, "-c", betik], stdout=subprocess.PIPE, text=True)
    try:
        cocuk_pid = int(ebeveyn.stdout.readline())

        def canli(pid):
            return str(pid) in subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout

        assert canli(cocuk_pid)
        ebeveyn.kill()  # zorla: atexit/finally calismaz
        ebeveyn.wait(10)
        assert bekle_ol(lambda: not canli(cocuk_pid)), "alt surec yetim kaldi"
    finally:
        ebeveyn.kill()


def bekle_ol(kosul, sn=10):
    son = time.monotonic() + sn
    while time.monotonic() < son:
        if kosul():
            return True
        time.sleep(0.2)
    return False


def test_sunucu_erken_kapanirsa_hata(tmp_path):
    class Cokus(Sunucu):
        def baslat(self):
            self.komut_oneki = [sys.executable, "-c", "import sys; sys.exit(3)"]
            return super().baslat()

    with pytest.raises(SunucuHatasi, match="erken kapandi"):
        Cokus(komut_oneki=[sys.executable], baslangic_klasoru=tmp_path, hazir_zaman_asimi=20).baslat()


def test_sunucu_hazir_olmazsa_zaman_asimi_ve_temizlik(tmp_path):
    sv = Sunucu(komut_oneki=[sys.executable, "-c", "import time; time.sleep(60)", "--"], baslangic_klasoru=tmp_path, hazir_zaman_asimi=1.5)
    with pytest.raises(SunucuHatasi, match="hazir olmadi"):
        sv.baslat()
    assert sv.islem is None


def test_sunucu_cli_yoksa_anlamli_hata(monkeypatch):
    from aktapokus_ajan import sunucu

    monkeypatch.setattr(sunucu, "opencode_bul", lambda: None)
    with pytest.raises(SunucuHatasi, match="bulunamadi"):
        Sunucu()


def test_fabrika_kalici_ornek_ve_hepsini_kapat(monkeypatch):
    assert "opencode-sunucu" in BILINEN_CALISTIRICILAR
    a = calistirici_olustur("opencode-sunucu")
    assert calistirici_olustur("opencode-sunucu") is a
    kapandi = []
    monkeypatch.setattr(a, "kapat", lambda: kapandi.append(1))
    hepsini_kapat()
    assert kapandi == [1]
    assert calistirici_olustur("opencode-sunucu") is not a  # kapatildiktan sonra yeni ornek


def test_hat_sunucu_calistiricisiyla(proje):
    s = SahteSunucu(dosya=("c.txt", "yeni\n"))
    try:
        veri = copy.deepcopy(VARSAYILAN_AYAR)
        for r in veri["roller"].values():
            r["calistirici"] = "opencode-sunucu"
        c = calistirici(s)
        sonuc = calistir_hat(proje, "c.txt ekle", ayar_coz(veri), lambda ad: c, lambda q: True)
        assert sonuc.durum == "onaylandi" and sonuc.degisen == {"c.txt": "A"}
        assert [a.rol for a in sonuc.adimlar] == ["kodcu", "test"] and sonuc.adimlar[1].dogrulama == "basarili"
        assert all(o["dir"] == str(proje.resolve()) or o["dir"] == str(proje) for o in s.durum.oturumlar.values())
    finally:
        s.kapat()


def test_hat_sunucu_modunda_koruyucu_sart(tmp_path):
    k = tmp_path / "p"
    k.mkdir()
    subprocess.run(["git", "-C", str(k), "init", "-q"], check=True)
    veri = copy.deepcopy(VARSAYILAN_AYAR)
    for r in veri["roller"].values():
        r["calistirici"] = "opencode-sunucu"
    from aktapokus_ajan.pipeline import HatHatasi

    with pytest.raises(HatHatasi, match="Koruyucu"):  # sunucu modunda koruyucusuz klasor disi yazma SORUSUZ olur (gercek denemede goruldu)
        calistir_hat(k, "g", ayar_coz(veri), lambda ad: None, lambda q: True)
