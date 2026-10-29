"""Claude Code calistiricisi: canli akis (stream-json), proje basina tek konusma, durdur, zaman asimi. Gercek Claude ile elle de dogrulandi
(canli olaylar, ayni konusmaya devam, durdur)."""

import json
import threading
import time

import pytest

from aktapokus_ai_studio import runners
from aktapokus_ai_studio.runners import ClaudeCodeCalistirici
from sahte_popen import claude_taklit, sonuc_olayi

ID1 = "11111111-1111-1111-1111-111111111111"
ID2 = "22222222-2222-2222-2222-222222222222"


def yeni(kip="yeni", olaylar=None):
    c = ClaudeCodeCalistirici(cli_yolu="cl")
    c.oturum_kipi = kip
    c.ilerleme = olaylar.append if olaylar is not None else None
    return c


def asistan(*icerik):
    return {"type": "assistant", "message": {"content": list(icerik)}}


# ---------- canli akis ----------
def test_canli_olaylar_metin_arac_ve_arac_sonucu_olarak_iletilir_girdi_ozetlenir(monkeypatch, tmp_path):
    buyuk = "A" * 5000
    claude_taklit(monkeypatch, runners, olaylar=[
        {"type": "system", "subtype": "init"},
        asistan({"type": "thinking", "thinking": "gizli dusunce"}),
        asistan({"type": "tool_use", "name": "Read", "input": {"file_path": "a.txt", "ic": {"gizli": "dict"}, "buyuk": buyuk}}),
        {"type": "user", "message": {"content": [{"type": "tool_result", "content": "ICERIK", "is_error": False}]}},
        asistan({"type": "text", "text": "Dosya bos."}),
        sonuc_olayi("Dosya bos."),
    ])
    alinan: list = []
    r = yeni(olaylar=alinan).calistir("istem", tmp_path)
    assert r.ok and r.metin == "Dosya bos."
    assert [o["tur"] for o in alinan] == ["arac", "arac-sonuc", "metin"]  # dusunce/system gizli kalir
    arac = alinan[0]
    assert arac["ad"] == "Read" and arac["girdi"]["file_path"] == "a.txt" and "ic" not in arac["girdi"] and len(arac["girdi"]["buyuk"]) == 200
    assert alinan[1]["hata"] is False and alinan[2]["parca"].startswith("Dosya bos.")
    assert "ICERIK" not in json.dumps(alinan)  # arac sonucunun icerigi akisa tasinmaz


def test_geri_cagri_hata_verse_calistirma_bozulmaz(monkeypatch, tmp_path):
    claude_taklit(monkeypatch, runners, olaylar=[asistan({"type": "text", "text": "x"}), sonuc_olayi("bitti")])
    c = yeni()
    c.ilerleme = lambda e: (_ for _ in ()).throw(RuntimeError("arayuz coktu"))
    assert c.calistir("istem", tmp_path).ok


def test_sonuc_satiri_yoksa_anlasilir_hata_ve_cikis_kodu(monkeypatch, tmp_path):
    claude_taklit(monkeypatch, runners, olaylar=[asistan({"type": "text", "text": "yarim"})], hata=b"Boom hata", kod=1)
    r = yeni().calistir("istem", tmp_path)
    assert not r.ok and "sonuc dondurmedi" in r.hata and "Boom hata" in r.hata
    claude_taklit(monkeypatch, runners, olaylar=[sonuc_olayi("ok")], kod=3, hata=b"cikis hatasi")
    r = yeni().calistir("istem", tmp_path)
    assert not r.ok and "cikis kodu 3" in r.hata


def test_bozuk_satirlar_atlanir(monkeypatch, tmp_path):
    kayit, sen = claude_taklit(monkeypatch, runners, olaylar=[sonuc_olayi("ok")])
    sen["olaylar"] = [sonuc_olayi("ok")]
    r = yeni().calistir("istem", tmp_path)
    assert r.ok and r.token_girdi == 15 and r.token_cikti == 3 and r.token_onbellek == 2


# ---------- konusma kipleri ----------
def test_tek_konusma_ilk_cagri_yeni_sonraki_ayni_konusmaya_devam_eder(monkeypatch, tmp_path):
    kayit, _ = claude_taklit(monkeypatch, runners, sirali=[[sonuc_olayi("bir", oturum=ID1)], [sonuc_olayi("iki", oturum=ID1)]])
    yeni("tek").calistir("birinci", tmp_path)
    yeni("tek").calistir("ikinci", tmp_path)  # yeni ornek: kalicilik diskten
    ilk, ikinci = kayit["cagrilar"]
    assert "--resume" not in ilk and "--no-session-persistence" not in ilk
    assert ikinci[ikinci.index("--resume") + 1] == ID1
    kayitli = json.loads((tmp_path / ".aktapokus" / "claude-oturum.json").read_text(encoding="utf-8"))
    assert kayitli["oturum"] == ID1


def test_yeni_kipi_her_seferinde_yeni_konusma_ve_hic_kaydetmez(monkeypatch, tmp_path):
    kayit, _ = claude_taklit(monkeypatch, runners, sirali=[[sonuc_olayi(oturum=ID1)], [sonuc_olayi(oturum=ID2)]])
    yeni("yeni").calistir("a", tmp_path)
    yeni("yeni").calistir("b", tmp_path)
    assert all("--resume" not in c for c in kayit["cagrilar"]) and not (tmp_path / ".aktapokus" / "claude-oturum.json").exists()


def test_hic_kipi_konusmayi_kaydetmez(monkeypatch, tmp_path):
    kayit, _ = claude_taklit(monkeypatch, runners)
    yeni("hic").calistir("a", tmp_path)
    assert "--no-session-persistence" in kayit["komut"] and "--resume" not in kayit["komut"]
    assert not (tmp_path / ".aktapokus" / "claude-oturum.json").exists()


def test_eski_ya_da_bozuk_konusma_kaydi_kullanilmaz_komuta_girmez(monkeypatch, tmp_path):
    (tmp_path / ".aktapokus").mkdir()
    yol = tmp_path / ".aktapokus" / "claude-oturum.json"
    for icerik in (
        {"oturum": ID1, "zaman": time.time() - 15 * 24 * 3600},  # 14 gunden eski
        {"oturum": "--dangerously-skip-permissions", "zaman": time.time()},  # proje klasorundeki dosya guvenilmez
        {"oturum": "../../x", "zaman": time.time()},
        {"oturum": ID1},
        "bozuk",
    ):
        yol.write_text(json.dumps(icerik), encoding="utf-8")
        kayit, _ = claude_taklit(monkeypatch, runners)
        yeni("tek").calistir("a", tmp_path)
        assert "--resume" not in kayit["komut"], icerik
    yol.write_text("{bozuk", encoding="utf-8")
    kayit, _ = claude_taklit(monkeypatch, runners)
    assert yeni("tek").calistir("a", tmp_path).ok


def test_kaybolan_konusma_yeniden_yeni_baslatilir(monkeypatch, tmp_path):
    (tmp_path / ".aktapokus").mkdir()
    (tmp_path / ".aktapokus" / "claude-oturum.json").write_text(json.dumps({"oturum": ID1, "zaman": time.time()}), encoding="utf-8")
    kayit, sen = claude_taklit(monkeypatch, runners, sirali=[[], [sonuc_olayi("tamam", oturum=ID2)]])
    sen["hata_sirasi"] = [b"No conversation found with session ID: " + ID1.encode(), b""]
    sen["kod_sirasi"] = [1, 0]
    r = yeni("tek").calistir("a", tmp_path)
    assert r.ok and r.metin == "tamam" and len(kayit["cagrilar"]) == 2
    assert "--resume" in kayit["cagrilar"][0] and "--resume" not in kayit["cagrilar"][1]
    assert json.loads((tmp_path / ".aktapokus" / "claude-oturum.json").read_text(encoding="utf-8"))["oturum"] == ID2


# ---------- durdur / zaman asimi ----------
def test_durdur_calisan_claude_surecini_sonlandirir_ve_durduruldu_doner(monkeypatch, tmp_path):
    claude_taklit(monkeypatch, runners, olaylar=[asistan({"type": "text", "text": "basladi"})], engelle=True)
    c = yeni()
    sonuc: dict = {}
    t = threading.Thread(target=lambda: sonuc.setdefault("r", c.calistir("uzun is", tmp_path)))
    t.start()
    for _ in range(100):
        if c._islem is not None:
            break
        time.sleep(0.02)
    assert c.durdur() is True
    t.join(10)
    assert not t.is_alive() and sonuc["r"].ok is False and sonuc["r"].hata == "Durduruldu"
    assert c.durdur() is False  # calisan yok


def test_zaman_asimi_sureci_oldurur(monkeypatch, tmp_path):
    claude_taklit(monkeypatch, runners, olaylar=[], engelle=True)
    r = yeni().calistir("istem", tmp_path, zaman_asimi_sn=0.3)
    assert not r.ok and "Zaman asimi" in r.hata


def test_baska_projedeki_calistirici_bu_calistiricinin_surecine_dokunmaz():
    c1, c2 = yeni(), yeni()
    assert c1.durdur() is False and c2.durdur() is False and c1._islem is None


# ---------- Claude konusmasinda yalniz gorev gorunur ----------
def test_istem_ayrilir_kurallar_sistem_istemine_gorev_kullanici_mesajina(monkeypatch, tmp_path):
    """Gercek durum: Claude'un konusma listesinde istek 'KURALLAR: ...' diye gorunuyordu; simdi yalniz kullanicinin istegi gorunur."""
    import copy

    from aktapokus_ai_studio.config import VARSAYILAN_AYAR, ayar_coz
    from aktapokus_ai_studio.pipeline import istem_olustur

    rol = ayar_coz(copy.deepcopy(VARSAYILAN_AYAR)).roller["kodcu"]
    istem = istem_olustur(rol, "README'ye baslik ekle\n\nGOREV: bu satir kullanicinin kendi metni", "onceki adimin ciktisi", None)
    kayit, _ = claude_taklit(monkeypatch, runners)
    yakalanan = {}
    asil = kayit  # ayar/sistem dosyalari calisma bitince silinir: Popen sahtesi komut listesini saklar, sistem dosyasini simdi okutalim
    from sahte_popen import SahtePopen

    giris = SahtePopen.__init__

    def okuyarak(self, komut, *a, **k):
        if "--append-system-prompt-file" in komut:
            from pathlib import Path

            yakalanan["sistem"] = Path(komut[komut.index("--append-system-prompt-file") + 1]).read_text(encoding="utf-8")
        return giris(self, komut, *a, **k)

    monkeypatch.setattr(SahtePopen, "__init__", okuyarak)
    yeni("yeni").calistir(istem, tmp_path)
    girdi = kayit["girdi"].decode("utf-8")
    assert girdi.startswith("README'ye baslik ekle") and "KURALLAR" not in girdi and "ROLUN" not in girdi  # kullanici mesaji = gorev (+ onceki cikti)
    assert "GOREV: bu satir kullanicinin kendi metni" in girdi and "ONCEKI ADIMIN CIKTISI" in girdi  # kullanicinin kendi 'GOREV:' metni bozulmaz
    assert yakalanan["sistem"].startswith("KURALLAR:") and "ROLUN: kodcu" in yakalanan["sistem"] and "README'ye baslik" not in yakalanan["sistem"]
    assert "--append-system-prompt-file" in kayit["komut"] and asil is kayit


def test_tanidik_olmayan_istem_oldugu_gibi_kullanici_mesaji_olur(monkeypatch, tmp_path):
    kayit, _ = claude_taklit(monkeypatch, runners)
    yeni("yeni").calistir("sadece bir istem", tmp_path)
    assert kayit["girdi"] == b"sadece bir istem" and "--append-system-prompt-file" not in kayit["komut"]
    kayit2, _ = claude_taklit(monkeypatch, runners)
    yeni("yeni").calistir("KURALLAR: ama ayrac yok", tmp_path)
    assert kayit2["girdi"] == "KURALLAR: ama ayrac yok".encode("utf-8") and "--append-system-prompt-file" not in kayit2["komut"]
    assert runners.istemi_ayir("KURALLAR: k\n\nROLUN: r\n\nGOREV:\n") == (None, "KURALLAR: k\n\nROLUN: r\n\nGOREV:\n")  # bos gorev: ayrilmaz


def test_arayuz_akisi_kullanici_en_alttaysa_otomatik_asagi_kayar():
    """Gercek sikayet: arac karti/canli metin/karar dugmeleri eklenince akis kendiliginden alta inmiyor, elle kaydirmak gerekiyordu."""
    from pathlib import Path

    html = (Path(__file__).parent.parent / "aktapokus_ai_studio" / "web" / "index.html").read_text(encoding="utf-8")
    assert "new MutationObserver(sabitle).observe(a,{childList:true,subtree:true,characterData:true})" in html and "sabitle=()=>{if(S.altaYapisik)a.scrollTop=a.scrollHeight}" in html  # yeni icerik gelince (yalniz alta yapisiksa) iner
    assert 'case "karar-bekleniyor":{alttaGoster();' in html and 'alttaGoster();try{const p=await api("/api/gorev"' in html
    assert 'class:"fark-sade"' in html and 'sekme("p-degisiklik")' in html  # degisen dosyalar akista tek satir; liste Degisiklikler sekmesinde


def test_beklenmedik_olay_bicimleri_calistirmayi_bozmaz(monkeypatch, tmp_path):
    """Gercek hata: Claude bazi olaylarda "message"i duz metin gonderdi ('str' object has no attribute 'get') ve gorev basarisiz sayildi."""
    claude_taklit(monkeypatch, runners, olaylar=[
        {"type": "user", "message": "duz metin mesaj"},
        {"type": "assistant", "message": None},
        {"type": "assistant", "message": ["liste"]},
        {"type": "user", "message": {"content": "metin icerik"}},
        {"type": "system", "message": 5},
        asistan({"type": "text", "text": "Tamam."}),
        sonuc_olayi("Tamam."),
    ])
    alinan: list = []
    r = yeni(olaylar=alinan).calistir("istem", tmp_path)
    assert r.ok and r.metin == "Tamam." and [o["tur"] for o in alinan] == ["metin"]  # bozuk olaylar atlanir, saglam olay iletilir


def test_ilerleyen_gorev_zaman_asimiyla_oldurulmez_takili_olan_olur(monkeypatch, tmp_path):
    """Akistan her satir sureyi yeniden baslatir: toplam sure sinirdan uzun olsa da arada hareket varsa gorev oldurulmez."""
    import time as _t

    from sahte_popen import SahtePopen

    claude_taklit(monkeypatch, runners, olaylar=[asistan({"type": "text", "text": "x"})] * 5 + [sonuc_olayi("bitti")])
    orijinal = SahtePopen._satirlar

    def yavas(self, sen):
        for satir in orijinal(self, sen):
            _t.sleep(0.15)
            yield satir

    monkeypatch.setattr(SahtePopen, "_satirlar", yavas)
    r = yeni().calistir("istem", tmp_path, zaman_asimi_sn=0.4)  # toplam ~0.9 sn > 0.4 sn, aralar 0.15 sn
    assert r.ok and r.metin == "bitti"
