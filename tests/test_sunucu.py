import copy
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from aktapokus_ai_studio import guard
from aktapokus_ai_studio.config import BILINEN_CALISTIRICILAR, VARSAYILAN_AYAR, ayar_coz
from aktapokus_ai_studio.pipeline import calistir_hat
from aktapokus_ai_studio.runners import calistirici_olustur, hepsini_kapat
from aktapokus_ai_studio.sunucu import Istemci, Sunucu, SunucuCalistirici, SunucuHatasi, mesajlardan_metin, model_coz
from aktapokus_ai_studio import sunucu as sunucu_modulu
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
        "from aktapokus_ai_studio.sunucu import Sunucu\n"
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
    from aktapokus_ai_studio import sunucu

    monkeypatch.setattr(sunucu, "opencode_bul", lambda: None)
    with pytest.raises(SunucuHatasi, match="bulunamadi"):
        Sunucu()


def test_fabrika_kalici_ornek_ve_hepsini_kapat(monkeypatch):
    assert "opencode-sunucu" in BILINEN_CALISTIRICILAR
    a = calistirici_olustur("opencode-sunucu")
    b = calistirici_olustur("opencode-sunucu")
    assert a is not b and a._sunucu is b._sunucu  # calistirici cagri basina ayri; sunucu sureci ortak
    kapandi = []
    monkeypatch.setattr(a._sunucu, "kapat", lambda: kapandi.append(1))
    a.kapat()  # paylasilan sunucuyu kapatmaz
    assert kapandi == []
    hepsini_kapat()
    assert kapandi == [1]
    assert calistirici_olustur("opencode-sunucu")._sunucu is not a._sunucu  # kapatildiktan sonra yeni sunucu


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
    from aktapokus_ai_studio.pipeline import HatHatasi

    with pytest.raises(HatHatasi, match="Koruyucu"):  # sunucu modunda koruyucusuz klasor disi yazma SORUSUZ olur (gercek denemede goruldu)
        calistir_hat(k, "g", ayar_coz(veri), lambda ad: None, lambda q: True)


def test_iki_calistirici_ayni_sunucuda_birbirinin_oturumunu_durdurmaz(tmp_path):
    """P2: iki proje ayni OpenCode sunucusunu paylasir; bir calistiricinin durdur()'u YALNIZ kendi oturumunu durdurur ve
    canli ilerleme olaylari yalniz kendi geri cagrisina gider."""
    s = SahteSunucu(davranis="takili")
    try:
        a_ol, b_ol = [], []
        a, b = calistirici(s, ilerleme=a_ol.append), calistirici(s, ilerleme=b_ol.append)
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        sonuclar = {}
        ta = threading.Thread(target=lambda: sonuclar.__setitem__("a", a.calistir("a", tmp_path / "a", zaman_asimi_sn=20)), daemon=True)
        tb = threading.Thread(target=lambda: sonuclar.__setitem__("b", b.calistir("b", tmp_path / "b", zaman_asimi_sn=20)), daemon=True)
        ta.start()
        tb.start()
        for _ in range(100):
            if a._aktif_sid and b._aktif_sid and all(s.durum.oturumlar[x._aktif_sid]["aktif"] for x in (a, b)):
                break
            time.sleep(0.05)
        assert a._aktif_sid and b._aktif_sid and a._aktif_sid != b._aktif_sid
        sid_a = a._aktif_sid
        assert a.durdur() is True
        ta.join(10)
        assert not ta.is_alive() and tb.is_alive()  # B hala kosuyor
        kesilenler = [c[1] for c in s.durum.cagrilar if c[0] == "INTERRUPT"]
        assert kesilenler == [sid_a]  # yalniz A'nin oturumu kesildi
        assert b.durdur() is True
        tb.join(10)
        assert not tb.is_alive()
        assert not sonuclar["a"].ok and not sonuclar["b"].ok
    finally:
        s.kapat()


def test_zaman_asimi_hareketsizlik_sayilir_ilerleyen_gorev_oldurulmez(tmp_path):
    """Gercek hata: 79 arac cagrisi yapan, derleyen, ekran goruntusu ureten canli bir gorev 900 sn dolunca 'basarisiz' sayilip oldurulmustu."""
    s = SahteSunucu(davranis="ilerliyor")
    try:
        r = calistirici(s).calistir("g", tmp_path, zaman_asimi_sn=1)  # toplam ~2.4 sn > 1 sn, ama token sayaci surekli artiyor
        assert r.ok, r.hata
    finally:
        s.kapat()


def test_yerel_model_icin_once_model_listesi_istenir_opencode_modelinde_istenmez_sunucu_basina_bir_kez(sahte, tmp_path):
    cagrilar = []

    class Izleyen(Istemci):
        def modeller(self):
            cagrilar.append(self.oturumlar_say())
            return []  # basarili liste: sunucu basina bir kez istenir (hata verirse sonraki gorevde yeniden denenir)

        def oturumlar_say(self):
            return len(sahte.durum.oturumlar)  # liste istendiginde kac oturum acilmisti

    i = Izleyen(sahte.taban, "p", zaman_asimi=5)
    c = SunucuCalistirici(istemci=i, yoklama_sn=0.05)
    c.calistir("g", tmp_path, model="opencode/m1")
    assert cagrilar == []  # OpenCode'un kendi modeli: kesif gerekmez
    r = c.calistir("g", tmp_path, model="ollama/qwen3:8b")  # fake sunucu bu saglayiciyi bilmeyebilir: sonuc onemli degil
    assert cagrilar == [1]  # liste, YENI oturum acilmadan ONCE istendi (onceki opencode oturumu 1 tane)
    c.calistir("g", tmp_path, model="ollama/qwen3:8b")
    assert cagrilar == [1]  # ayni sunucuda ikinci kez istenmez
    assert r is not None


def test_model_kesfi_hata_verirse_gorev_yine_denenir(sahte, tmp_path):
    class Bozuk(Istemci):
        def modeller(self):
            raise SunucuHatasi("liste yok")

    c = SunucuCalistirici(istemci=Bozuk(sahte.taban, "p", zaman_asimi=5), yoklama_sn=0.05)
    r = c.calistir("g", tmp_path, model="opencode/m1") if False else c.calistir("g", tmp_path, model="ollama/x")
    assert r is not None and "liste yok" not in str(r.hata or "")  # kesif hatasi gorev sonucuna yansimaz


def test_mesajlardan_beceriler_cagrilan_becerileri_sirayla_ve_tekrarsiz_verir():
    mesajlar = [
        {"type": "user", "content": []},
        {"type": "assistant", "time": {"created": 2}, "content": [{"type": "tool", "name": "skill", "state": {"input": {"id": "ikinci"}}}, {"type": "tool", "name": "read", "state": {"input": {"path": "x"}}}]},
        {"type": "assistant", "time": {"created": 1}, "content": [{"type": "tool", "name": "skill", "state": {"input": {"id": "birinci"}}}, {"type": "tool", "name": "skill", "state": {"input": {"id": "ikinci"}}}, {"type": "tool", "name": "skill", "state": {}}]},
    ]
    assert sunucu_modulu.mesajlardan_beceriler(mesajlar) == ["birinci", "ikinci"]
    assert sunucu_modulu.mesajlardan_beceriler([]) == []


def test_sunucu_istemi_komut_satiri_sinirina_takilmaz_ama_ust_siniri_vardir():
    from aktapokus_ai_studio import runners
    uzun = "a" * 38_336
    with pytest.raises(runners.CalistiriciHatasi):
        runners._istemi_denetle(uzun)  # CLI: komut satiri siniri
    runners._istemi_denetle(uzun, sunucu_modulu.AZAMI_SUNUCU_ISTEMI)  # sunucu: HTTP govdesi
    with pytest.raises(runners.CalistiriciHatasi):
        runners._istemi_denetle("a" * (sunucu_modulu.AZAMI_SUNUCU_ISTEMI + 1), sunucu_modulu.AZAMI_SUNUCU_ISTEMI)


def test_calisan_arac_hareketsizlik_sayilmaz():
    arac = lambda durum: [{"type": "assistant", "content": [{"type": "tool", "name": "shell", "state": {"status": durum}}]}]
    assert sunucu_modulu.arac_calisiyor(arac("running")) and sunucu_modulu.arac_calisiyor(arac("pending"))
    assert not sunucu_modulu.arac_calisiyor(arac("completed")) and not sunucu_modulu.arac_calisiyor([])


@pytest.mark.parametrize("davranis", ["dusunuyor", "komut"])
def test_token_oynamasa_da_olay_ya_da_komut_ciktisi_gelen_gorev_zaman_asimina_dusmez(tmp_path, monkeypatch, davranis):
    monkeypatch.setattr(sunucu_modulu, "arac_calisiyor", lambda m: False)  # yalniz canli sinyal denensin
    s = SahteSunucu(davranis=davranis, gecikme=0)
    try:
        r = calistirici(s).calistir("g", tmp_path, zaman_asimi_sn=1)  # gorev ~2.4 sn, aralarda 0.2 sn sinyal
        assert r.ok, r.hata
    finally:
        s.kapat()


def test_ciktisiz_komut_arac_durumu_olmadan_zaman_asimina_duser_token_sifir_kalmaz(tmp_path, monkeypatch):
    monkeypatch.setattr(sunucu_modulu, "arac_calisiyor", lambda m: False)
    s = SahteSunucu(davranis="sessiz-komut", gecikme=0)
    try:
        r = calistirici(s).calistir("g", tmp_path, zaman_asimi_sn=1)
        assert not r.ok and "Zaman asimi (1 sn)" in r.hata
        assert r.token_girdi == 100 and r.token_cikti == 25  # kesilen gorevin harcamasi kaybolmaz
    finally:
        s.kapat()


def test_model_soru_sorarsa_gorev_beklemez_yaziyla_sormasi_istenir(tmp_path):
    s = SahteSunucu(davranis="soru", gecikme=0)
    try:
        olaylar = []
        c = SunucuCalistirici(istemci=Istemci(s.taban, "p", zaman_asimi=5), yoklama_sn=0.05, ilerleme=olaylar.append)
        r = c.calistir("g", tmp_path, zaman_asimi_sn=5)
        assert r.ok and r.sure_sn < 4
        (tur, govde), = s.durum.form_yanitlari
        assert tur == "yanit" and govde["answer"]["q0"] == sunucu_modulu.SORU_NOTU and govde["answer"]["q1"] == []  # coklu secim metin kabul etmez
        assert {"tur": "durum", "durum": "soru"} in olaylar
    finally:
        s.kapat()


def test_soru_olmayan_form_iptal_edilir(tmp_path):
    s = SahteSunucu(davranis="form", gecikme=0)
    try:
        assert calistirici(s).calistir("g", tmp_path, zaman_asimi_sn=5).ok
        (tur, sorgu), = s.durum.form_yanitlari
        assert tur == "iptal" and sorgu["message"] == [sunucu_modulu.SORU_NOTU]
    finally:
        s.kapat()


def test_ekrana_dusunce_ve_komutun_son_satiri_gider(tmp_path):
    for davranis, beklenen in (("dusunuyor", "dusunce"), ("komut", "kabuk")):
        s = SahteSunucu(davranis=davranis, gecikme=0)
        try:
            olaylar = []
            c = SunucuCalistirici(istemci=Istemci(s.taban, "p", zaman_asimi=5), yoklama_sn=0.05, ilerleme=olaylar.append)
            assert c.calistir("g", tmp_path, zaman_asimi_sn=2).ok
            gelen = [o for o in olaylar if o["tur"] == beklenen]
            assert gelen, olaylar
            if beklenen == "kabuk":
                assert any(o["satir"].startswith("satir ") for o in gelen) and "sh_1" not in str(gelen)
            else:
                assert gelen[0]["parca"] == "adim 0\n"
        finally:
            s.kapat()


def test_baska_oturumun_komutu_izlenmez_gecersiz_kimlik_url_ye_girmez():
    etkinlik = {"zaman": 0, "kabuklar": {}}
    Olay = sunucu_modulu.Olay
    sunucu_modulu._kabuk_olayi(Olay("shell.created", {"info": {"id": "sh_b", "metadata": {"sessionID": "baska"}}}, {}), "ben", etkinlik)
    sunucu_modulu._kabuk_olayi(Olay("session.tool.progress", {"sessionID": "ben", "metadata": {"shellID": "../../gizli"}}, {}), "ben", etkinlik)
    assert etkinlik["kabuklar"] == {}
    sunucu_modulu._kabuk_olayi(Olay("session.tool.progress", {"sessionID": "ben", "metadata": {"shellID": "sh_1"}}, {}), "ben", etkinlik)
    assert list(etkinlik["kabuklar"]) == ["sh_1"]
    sunucu_modulu._kabuk_olayi(Olay("shell.exited", {"id": "sh_1"}, {}), "ben", etkinlik)
    assert etkinlik["kabuklar"] == {}


def test_satir_sonu_vermeyen_cikti_birikir_tamamlanan_satir_kalir():
    gelen = iter(["..", "..\nbitti\r\n", "ya"])
    imlec = iter([2, 11, 13])

    class Kabuk:
        def kabuk_cikti(self, kabuk, klasor, i):
            return {"output": next(gelen), "cursor": next(imlec)}

    etkinlik = {"zaman": 0, "kabuklar": {}}
    sunucu_modulu._kabuk_olayi(sunucu_modulu.Olay("session.tool.progress", {"sessionID": "ben", "metadata": {"shellID": "sh_1"}}, {}), "ben", etkinlik)
    olaylar = []
    c = SunucuCalistirici(istemci=object(), ilerleme=olaylar.append)
    for _ in range(3):
        c._kabuklari_izle(Kabuk(), "k", etkinlik)
    assert [o["satir"] for o in olaylar] == ["..", "bitti", "ya"]
    assert etkinlik["zaman"] > 0


def test_arac_adi_hazirlanirken_gelen_olaydan_alinir():
    Olay = sunucu_modulu.Olay
    d = {"sessionID": "ben", "id": "call_1"}

    class Akis:
        def olaylar(self):
            yield Olay("session.tool.input.started", {**d, "name": "shell"}, {})
            yield Olay("session.tool.called", {**d, "input": {"command": "x"}}, {})

    olaylar = []
    durdur, bitti = threading.Event(), threading.Event()
    SunucuCalistirici(istemci=object(), ilerleme=olaylar.append)._dinleyici(Akis(), "ben", durdur, bitti, {"zaman": 0, "kabuklar": {}}).join(5)
    assert olaylar[-1] == {"tur": "arac", "ad": "shell", "girdi": {"command": "x"}}


def test_yeniden_deneme_ve_ozetleme_ekrana_yansir():
    Olay = sunucu_modulu.Olay
    o = sunucu_modulu.olay_ilerlemesi(Olay("session.retry.scheduled", {"attempt": 2, "error": {"message": "rate  limit"}}, {}))
    assert o == {"tur": "durum", "durum": "yeniden", "deneme": 2, "hata": "rate limit"}
    assert sunucu_modulu.olay_ilerlemesi(Olay("session.compaction.started", {}, {}))["durum"] == "ozetleniyor"
    assert sunucu_modulu.olay_ilerlemesi(Olay("session.step.streamed", {}, {})) is None
