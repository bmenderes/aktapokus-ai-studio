"""MCP sunuculari + beceriler: HTTP uclari, guvenlik, CLI'lara aktarim (sahte OpenCode istemcisiyle) ve Uygulama baglantisi."""

import http.client
import json
import sys
import threading
from pathlib import Path

import pytest

from aktapokus_ajan import beceriler, mcptanim, projeler
from aktapokus_ajan.arayuz import ArayuzSunucusu, Uygulama
from aktapokus_ajan.runners import ClaudeCodeCalistirici, CodexCalistirici
from aktapokus_ajan.sunucu import SunucuCalistirici, SunucuHatasi
from test_arayuz import Istemci

GIZLI = "super-gizli-anahtar-9876"
SAHTE = {"ad": "sahte", "tur": "local", "komut": [sys.executable, "sahte_mcp.py"], "ortam": {"ANAHTAR": GIZLI}}


class SahteOpenCode:
    """OpenCode istemcisinin MCP/beceri bolumunu taklit eder; konum (klasor) basina ayri MCP tablosu tutar."""

    def __init__(self):
        self.mcp: dict[str, dict[str, dict]] = {}
        self.cagrilar: list[tuple] = []
        self.ekle_hatasi: str | None = None
        self.durum_sonrasi = {"status": "connected"}
        self.beceri_listesi: list[dict] = []

    def mcp_liste(self, klasor):
        return {ad: {"status": "connected"} if ad not in self.mcp.get(str(klasor), {}) or "durum" not in self.mcp[str(klasor)][ad] else self.mcp[str(klasor)][ad]["durum"] for ad in self.mcp.get(str(klasor), {})}

    def mcp_ekle(self, klasor, ad, config):
        self.cagrilar.append(("ekle", str(klasor), ad))
        if self.ekle_hatasi:
            raise SunucuHatasi(self.ekle_hatasi)
        self.mcp.setdefault(str(klasor), {})[ad] = {"config": config, "durum": self.durum_sonrasi}

    def mcp_sil(self, klasor, ad):
        self.cagrilar.append(("sil", str(klasor), ad))
        self.mcp.get(str(klasor), {}).pop(ad, None)

    def beceriler(self, klasor, bekle_sn=8.0):
        return self.beceri_listesi


@pytest.fixture
def api(proje):
    oc = SahteOpenCode()
    app = Uygulama(saglayici_istemci_uret=lambda: oc)
    sv = ArayuzSunucusu(app)
    sv.baslat()
    app.klasor_sec(str(proje))
    yield app, sv, Istemci(sv), oc, proje
    sv.kapat()


def pid(proje):
    return projeler.proje_kimligi(proje)


# ---------- guvenlik ----------
UCLAR = [("GET", "/api/mcp-sunuculari"), ("POST", "/api/mcp-sunuculari"), ("POST", "/api/mcp-sunuculari/sil"), ("POST", "/api/mcp-sunuculari/proje"),
         ("POST", "/api/mcp-sunuculari/dene"), ("GET", "/api/beceriler"), ("GET", "/api/beceriler/x"), ("POST", "/api/beceriler"), ("POST", "/api/beceriler/sil")]


def test_tum_uclar_belirtec_ister(api):
    _, _, istek, _, _ = api
    for yontem, yol in UCLAR:
        assert istek(yontem, yol, {} if yontem == "POST" else None, token=None)[0] == 401, yol
        assert istek(yontem, yol, {} if yontem == "POST" else None, token="yanlis")[0] == 401, yol


def test_yabanci_origin_reddedilir(api):
    _, sv, _, _, _ = api
    for yol in ("/api/mcp-sunuculari", "/api/beceriler", "/api/mcp-sunuculari/sil", "/api/beceriler/sil"):
        c = http.client.HTTPConnection("127.0.0.1", sv.port, timeout=10)
        c.request("POST", yol, body=json.dumps(SAHTE), headers={"X-Aktapokus-Token": sv.app.token, "Origin": "http://evil.example", "Content-Type": "application/json"})
        r = c.getresponse()
        r.read()
        c.close()
        assert r.status == 403, yol


def test_telegram_mcp_ve_becerilere_dokunmaz():
    kaynak = (Path(__file__).resolve().parent.parent / "aktapokus_ajan" / "telegram.py").read_text(encoding="utf-8")
    assert "mcp_kaydet" not in kaynak and "mcp_sil" not in kaynak and "beceri_kaydet" not in kaynak and "beceri_sil" not in kaynak and "mcptanim" not in kaynak


# ---------- MCP uclari ----------
def test_mcp_kaydet_listele_degerler_asla_geri_donmez(api):
    _, _, istek, _, _ = api
    st, d = istek("POST", "/api/mcp-sunuculari", SAHTE)
    assert st == 200 and d["ortam"] == {"ANAHTAR": mcptanim.MASKE}
    st, liste = istek("GET", "/api/mcp-sunuculari")
    assert GIZLI not in json.dumps([d, liste]) and liste["sunucular"][0]["ad"] == "sahte"
    assert mcptanim.yukle()["sahte"].ortam["ANAHTAR"] == GIZLI  # diskte tam deger


def test_mcp_gecersiz_tanim_400_ve_hata_degeri_sizdirmaz(api):
    _, _, istek, _, _ = api
    st, d = istek("POST", "/api/mcp-sunuculari", {**SAHTE, "komut": ["olmayan-program-xyz"], "ortam": {"A": GIZLI}})
    assert st == 400 and GIZLI not in json.dumps(d) and mcptanim.yukle() == {}


def test_mcp_proje_ac_kapat_ve_bilinmeyen_proje(api):
    _, _, istek, _, proje = api
    istek("POST", "/api/mcp-sunuculari", SAHTE)
    st, d = istek("POST", "/api/mcp-sunuculari/proje", {"ad": "sahte", "proje": pid(proje), "acik": True})
    assert st == 200 and d["projeler"] == [pid(proje)]
    assert [t.ad for t in mcptanim.proje_icin(pid(proje))] == ["sahte"]
    assert istek("POST", "/api/mcp-sunuculari/proje", {"ad": "sahte", "proje": "0123456789", "acik": True})[0] == 404  # kayitli olmayan proje
    assert istek("POST", "/api/mcp-sunuculari/proje", {"ad": "yok", "proje": pid(proje), "acik": True})[0] == 404
    st, d = istek("POST", "/api/mcp-sunuculari/proje", {"ad": "sahte", "proje": pid(proje), "acik": False})
    assert st == 200 and d["projeler"] == []


def test_mcp_sil(api):
    _, _, istek, _, _ = api
    istek("POST", "/api/mcp-sunuculari", SAHTE)
    assert istek("POST", "/api/mcp-sunuculari/sil", {"ad": "sahte"})[0] == 200
    assert istek("POST", "/api/mcp-sunuculari/sil", {"ad": "sahte"})[0] == 404
    assert istek("POST", "/api/mcp-sunuculari/sil", {})[0] == 404


def test_mcp_dene_durumu_verir_ve_gecici_sunucuyu_kaldirir(api):
    _, _, istek, oc, proje = api
    istek("POST", "/api/mcp-sunuculari", SAHTE)
    st, d = istek("POST", "/api/mcp-sunuculari/dene", {"ad": "sahte"})
    assert st == 200 and d["durum"] == "connected"
    assert oc.cagrilar == [("ekle", str(proje.resolve()) if str(proje.resolve()) in oc.mcp or False else oc.cagrilar[0][1], "dene-sahte"), ("sil", oc.cagrilar[0][1], "dene-sahte")]
    assert oc.mcp[oc.cagrilar[0][1]] == {}  # gecici kayit temizlendi
    oc.durum_sonrasi = {"status": "failed", "error": "baglanilamadi: sebep"}
    st, d = istek("POST", "/api/mcp-sunuculari/dene", {"ad": "sahte"})
    assert d["durum"] == "failed" and "sebep" in d["hata"]
    assert istek("POST", "/api/mcp-sunuculari/dene", {"ad": "yok"})[0] == 404


def test_mcp_dene_hata_mesajindaki_gizli_degerler_maskelenir(api):
    _, _, istek, oc, _ = api
    istek("POST", "/api/mcp-sunuculari", SAHTE)
    oc.ekle_hatasi = f"HTTP 400: gecersiz ortam ANAHTAR={GIZLI}"
    st, d = istek("POST", "/api/mcp-sunuculari/dene", {"ad": "sahte"})
    assert d["durum"] == "failed" and GIZLI not in json.dumps(d) and "***" in d["hata"]


# ---------- Beceri uclari ----------
BECERI = {"kimlik": "sunum-hazirla", "ad": "Sunum Hazirla", "aciklama": "Kisa sunum cikarir", "govde": "# Adimlar\n1. Sor", "otomatik": True}


def test_beceri_olustur_oku_listele_sil(api):
    _, _, istek, oc, _ = api
    assert istek("POST", "/api/beceriler", BECERI)[0] == 200
    assert (beceriler.kok() / "sunum-hazirla" / "SKILL.md").is_file()
    st, d = istek("GET", "/api/beceriler/sunum-hazirla")
    assert st == 200 and d["govde"].startswith("# Adimlar") and d["ad"] == "Sunum Hazirla"
    st, liste = istek("GET", "/api/beceriler")  # OpenCode henuz gormuyor: yine de listelenir
    yerel = [b for b in liste["beceriler"] if b["kimlik"] == "sunum-hazirla"]
    assert st == 200 and yerel and yerel[0]["duzenlenebilir"] is True and yerel[0]["kaynak"] == "Aktapokus"
    assert istek("POST", "/api/beceriler/sil", {"kimlik": "sunum-hazirla"})[0] == 200
    assert istek("GET", "/api/beceriler/sunum-hazirla")[0] == 404
    assert istek("POST", "/api/beceriler/sil", {"kimlik": "sunum-hazirla"})[0] == 404


def test_beceri_listesi_kaynak_etiketleri_ve_duzenlenebilirlik(api, tmp_path):
    _, _, istek, oc, proje = api
    istek("POST", "/api/beceriler", BECERI)
    ev = Path.home()
    oc.beceri_listesi = [
        {"kimlik": "opencode", "ad": "OpenCode", "aciklama": "d", "yol": "/builtin/opencode.md", "otomatik": True},
        {"kimlik": "graphify", "ad": "g", "aciklama": "", "yol": str(ev / ".claude" / "skills" / "graphify" / "SKILL.md"), "otomatik": True},
        {"kimlik": "sunum-hazirla", "ad": "Sunum Hazirla", "aciklama": "", "yol": str(beceriler.kok() / "sunum-hazirla" / "SKILL.md"), "otomatik": True},
        {"kimlik": "projeye-ozel", "ad": "p", "aciklama": "", "yol": str(proje / ".opencode" / "skills" / "projeye-ozel" / "SKILL.md"), "otomatik": True},
    ]
    st, liste = istek("GET", "/api/beceriler")
    k = {b["kimlik"]: b for b in liste["beceriler"]}
    assert k["opencode"]["kaynak"] == "OpenCode (yerlesik)" and not k["opencode"]["duzenlenebilir"]
    assert k["graphify"]["kaynak"].startswith("Claude") and not k["graphify"]["duzenlenebilir"]  # ~/.claude/skills DEGISTIRILMEZ
    assert k["sunum-hazirla"]["kaynak"] == "Aktapokus" and k["sunum-hazirla"]["duzenlenebilir"]
    assert k["projeye-ozel"]["duzenlenebilir"] is False
    assert len(liste["beceriler"]) == 4  # yerel olan iki kez sayilmaz


def test_beceri_opencode_ulasilamazsa_uyari_ve_yerel_liste():
    class Bozuk:
        def beceriler(self, klasor, bekle_sn=8.0):
            raise SunucuHatasi("ulasilamadi")

    app = Uygulama(saglayici_istemci_uret=lambda: Bozuk())
    beceriler.olustur("yerel-beceri", "Yerel", "aciklama", "govde")
    d = app.beceri_listele()
    assert d["uyari"] and [b["kimlik"] for b in d["beceriler"]] == ["yerel-beceri"]


def test_beceri_gecersiz_kimlik_ve_yol_gezintisi(api, tmp_path):
    _, _, istek, _, _ = api
    assert istek("POST", "/api/beceriler", {**BECERI, "kimlik": "../kacis"})[0] == 400
    assert istek("POST", "/api/beceriler", {**BECERI, "kimlik": "A-Buyuk"})[0] == 400
    assert istek("POST", "/api/beceriler", {**BECERI, "aciklama": "iki\nsatir"})[0] == 400
    assert istek("POST", "/api/beceriler/sil", {"kimlik": "../../x"})[0] == 400
    for kotu in ("/api/beceriler/..%2f..%2fx", "/api/beceriler/a%5cb", "/api/beceriler/a.b"):
        assert istek("GET", kotu)[0] in (400, 404), kotu
    assert not (beceriler.kok().parent / "kacis").exists() and list(beceriler.kok().glob("*")) == []


def test_beceri_silme_klasorde_baska_dosya_varsa_409(api):
    _, _, istek, _, _ = api
    istek("POST", "/api/beceriler", BECERI)
    (beceriler.kok() / "sunum-hazirla" / "notlar.txt").write_text("onemli")
    st, d = istek("POST", "/api/beceriler/sil", {"kimlik": "sunum-hazirla"})
    assert st == 409 and "notlar.txt" in d["hata"] and (beceriler.kok() / "sunum-hazirla" / "notlar.txt").is_file()


# ---------- CLI'lara aktarim ----------
def _t(ad="sahte", **kw):
    return mcptanim.tanim_coz({**SAHTE, "ad": ad, **kw}, program_denetle=False)


def test_claude_komutu_yalniz_mcp_varsa_bayrak_ekler_ve_yalniz_o_sunuculari_izinli_yapar():
    c = ClaudeCodeCalistirici(cli_yolu="claude")
    temel = c.komut("ayar.json", None, True)
    assert "--mcp-config" not in temel and "--allowedTools" not in temel
    k = c.komut("ayar.json", None, True, "mcp.json", ("sahte", "diger"))
    i = k.index("--mcp-config")
    assert k[i + 1] == "mcp.json" and k[k.index("--allowedTools"):][1:] == ["mcp__sahte", "mcp__diger"]


def test_claude_calistir_gecici_mcp_dosyasi_yazar_ve_kullanici_ayarina_dokunmaz(monkeypatch, tmp_path):
    from aktapokus_ajan import runners

    yakalanan = {}

    def sahte_calistir(komut, istem, klasor, zaman_asimi):
        i = komut.index("--mcp-config")
        yakalanan["icerik"] = json.loads(Path(komut[i + 1]).read_text(encoding="utf-8"))
        yakalanan["dosya"] = komut[i + 1]
        return type("R", (), {"stdout": json.dumps({"result": "ok", "usage": {}}), "stderr": "", "returncode": 0})()

    monkeypatch.setattr(runners, "_stdinli_calistir", sahte_calistir)
    c = ClaudeCodeCalistirici(cli_yolu="claude")
    c.mcp = (_t(),)
    c.calistir("istem", tmp_path)
    assert yakalanan["icerik"]["mcpServers"]["sahte"]["env"] == {"ANAHTAR": GIZLI}
    assert not Path(yakalanan["dosya"]).exists()  # gecici dosya (anahtar iceriyor) calisma bitince silindi


def test_codex_komutu_mcp_gecersiz_kilmalari_yalniz_mcp_varsa():
    c = CodexCalistirici(komut_oneki=["codex"])
    assert not any("mcp_servers" in a for a in c.komut(Path("."), None, True, "son.txt"))
    c.mcp = (_t(),)
    komut = c.komut(Path("."), None, True, "son.txt")
    assert any(a.startswith("mcp_servers.sahte.command=") for a in komut) and any("default_tools_approval_mode" in a for a in komut)
    assert komut[-1] == "-"


def calistirici(oc, *tanimlar):
    c = SunucuCalistirici(istemci=oc)
    c.mcp = tuple(tanimlar)
    return c


def test_opencode_etkin_sunucu_eklenir_etkin_olmayan_kayitli_kaldirilir_kullanicinin_kendisi_korunur(tmp_path):
    oc = SahteOpenCode()
    mcptanim.kaydet(SAHTE)
    mcptanim.kaydet({**SAHTE, "ad": "kapali"})
    k = str(tmp_path)
    oc.mcp[k] = {"kapali": {"config": {}}, "kullanicinin-kendi": {"config": {}}}  # biri bizim kayitli (etkin degil), biri kullanicinin kendi opencode.json'u
    sorun = calistirici(oc, _t())._mcp_uygula(oc, tmp_path)
    assert sorun == []
    assert set(oc.mcp[k]) == {"sahte", "kullanicinin-kendi"}  # 'kapali' kaldirildi, kullanicinin kendisine dokunulmadi
    assert oc.mcp[k]["sahte"]["config"]["environment"] == {"ANAHTAR": GIZLI}


def test_opencode_ayni_yapilandirma_yeniden_eklenmez_degisen_yeniden_eklenir(tmp_path):
    SunucuCalistirici._mcp_uygulanan.clear()
    oc = SahteOpenCode()
    mcptanim.kaydet(SAHTE)
    c = calistirici(oc, _t())
    c._mcp_uygula(oc, tmp_path)
    c._mcp_uygula(oc, tmp_path)
    assert [x[0] for x in oc.cagrilar] == ["ekle"]  # ikinci calismada baglanti korunur (yeniden baslatma maliyeti yok)
    calistirici(oc, _t(ortam={"ANAHTAR": "yeni"}))._mcp_uygula(oc, tmp_path)
    assert [x[0] for x in oc.cagrilar] == ["ekle", "sil", "ekle"] and oc.mcp[str(tmp_path)]["sahte"]["config"]["environment"] == {"ANAHTAR": "yeni"}


def test_opencode_baglanti_hatasi_sorun_olarak_doner_ve_deger_sizdirmaz(tmp_path):
    SunucuCalistirici._mcp_uygulanan.clear()
    oc = SahteOpenCode()
    mcptanim.kaydet(SAHTE)
    oc.ekle_hatasi = f"HTTP 400 PUT: ortam {GIZLI} gecersiz"
    sorun = calistirici(oc, _t())._mcp_uygula(oc, tmp_path)
    assert len(sorun) == 1 and sorun[0]["ad"] == "sahte" and GIZLI not in json.dumps(sorun) and "***" in sorun[0]["hata"]


def test_opencode_failed_durumu_sorun_olarak_bildirilir(tmp_path):
    SunucuCalistirici._mcp_uygulanan.clear()
    oc = SahteOpenCode()
    oc.durum_sonrasi = {"status": "failed", "error": "baslamadi"}
    mcptanim.kaydet(SAHTE)
    sorun = calistirici(oc, _t())._mcp_uygula(oc, tmp_path)
    assert sorun == [{"ad": "sahte", "hata": "baslamadi"}]


def test_opencode_mcp_yoksa_ve_kayit_bossa_sunucuya_hic_istek_atilmaz(tmp_path):
    class Yasak(SahteOpenCode):
        def mcp_liste(self, klasor):
            raise AssertionError("MCP yokken OpenCode'a MCP istegi atilmamali")

    assert calistirici(Yasak())._mcp_uygula(Yasak(), tmp_path) == []


# ---------- Uygulama baglantisi ----------
def test_kosu_adimlari_projede_etkin_mcp_sunucularini_alir(proje):
    from conftest import SahteCalistirici, sonuc
    from test_arayuz import BASARILI, bekle, yaz

    t = mcptanim.kaydet(SAHTE)
    gorulen = []

    def uret(ad):
        c = SahteCalistirici({"kodcu": yaz, "test": BASARILI})
        gorulen.append(c)
        return c

    app = Uygulama(calistirici_uret=uret)
    app.klasor_sec(str(proje))
    plan = app.gorev_olustur("g")
    app.onayla(plan["kosu"])
    assert bekle(lambda: app.kosu.durum in ("karar-bekliyor", "bitti"))
    assert gorulen and all(c.mcp == () for c in gorulen)  # varsayilan KAPALI
    if app.kosu.durum == "karar-bekliyor":
        app.karar_ver(plan["kosu"], False)
        assert bekle(lambda: app.kosu.durum == "bitti")
    mcptanim.proje_ayarla("sahte", pid(proje), True)
    gorulen.clear()
    plan = app.gorev_olustur("g2")
    app.onayla(plan["kosu"])
    assert bekle(lambda: app.kosu.durum in ("karar-bekliyor", "bitti"))
    assert gorulen and all([x.ad for x in c.mcp] == ["sahte"] for c in gorulen)
    if app.kosu.durum == "karar-bekliyor":
        app.karar_ver(plan["kosu"], False)
        assert bekle(lambda: app.kosu.durum == "bitti")


def test_baska_projede_etkin_sunucu_bu_projeye_aktarilmaz(proje, tmp_path):
    from test_arayuz import _ikinci_proje

    mcptanim.kaydet(SAHTE)
    ikinci = _ikinci_proje(tmp_path)
    mcptanim.proje_ayarla("sahte", pid(proje), True)
    assert mcptanim.proje_icin(pid(ikinci)) == [] and len(mcptanim.proje_icin(pid(proje))) == 1


def test_beceri_yolu_kisa_8_3_adla_gelse_de_duzenlenebilir_sayilir(api, monkeypatch):
    """Gercek hata: OpenCode yolu 'BARIS~1.MEN' gibi kisa adla dondurebilir; karsilastirma gercek yola cevrilerek yapilmali."""
    import ctypes

    _, _, istek, oc, _ = api
    istek("POST", "/api/beceriler", BECERI)
    gercek = beceriler.kok() / "sunum-hazirla" / "SKILL.md"
    if sys.platform == "win32":
        tampon = ctypes.create_unicode_buffer(1024)
        ctypes.windll.kernel32.GetShortPathNameW(str(gercek), tampon, 1024)
        kisa = tampon.value or str(gercek)
    else:
        kisa = str(gercek)
    oc.beceri_listesi = [{"kimlik": "sunum-hazirla", "ad": "x", "aciklama": "", "yol": kisa, "otomatik": True}]
    k = {b["kimlik"]: b for b in istek("GET", "/api/beceriler")[1]["beceriler"]}
    assert k["sunum-hazirla"]["duzenlenebilir"] is True and k["sunum-hazirla"]["kaynak"] == "Aktapokus"


def test_ayarlar_sayfasi_mcp_ve_beceri_bolumlerini_icerir():
    html = (Path(__file__).resolve().parent.parent / "aktapokus_ajan" / "web" / "index.html").read_text(encoding="utf-8")
    for parca in ('["mcp","MCP sunucuları"]', '["beceriler","Beceriler"]', "function mcpBolumu", "function mcpFormu", "function beceriBolumu", "function beceriFormu",
                  "/api/mcp-sunuculari/dene", "/api/mcp-sunuculari/proje", "/api/beceriler/sil"):
        assert parca in html, parca
    assert "textContent" in html and "innerHTML=" not in html.split("function mcpBolumu")[1].split("async function beceriBolumu")[0]  # MCP bolumu kullanici verisini innerHTML'e yazmaz
