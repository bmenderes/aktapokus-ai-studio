import subprocess
from pathlib import Path

import pytest

from aktapokus_ai_studio import guard, snapshot
from aktapokus_ai_studio.runners import Calistirici, CalistirmaSonucu


@pytest.fixture
def proje(tmp_path):
    """Gecici, git deposu olan bir proje klasoru (guvenli_klasor gecer: tmp_path ev dizininin altinda degil)."""
    klasor = tmp_path / "proje"
    klasor.mkdir()
    subprocess.run(["git", "-C", str(klasor), "init", "-q"], check=True)
    (klasor / "a.txt").write_text("bir\n", encoding="utf-8")
    (klasor / "b.txt").write_text("iki\n", encoding="utf-8")
    guard.kur(klasor)  # OpenCode rolleri icin koruyucu zorunlu
    return klasor


class SahteKayit:
    """otomatik_baslat.Kayit yerine bellekte tek deger (testler gercek HKCU\\...\\Run anahtarina dokunmaz)."""

    def __init__(self):
        self.deger = None

    def oku(self):
        return self.deger

    def yaz(self, komut):
        self.deger = komut

    def sil(self):
        self.deger = None


class SahteCalistirici(Calistirici):
    """Senaryo: rol adi -> islev(klasor, istem, cagri_no) -> CalistirmaSonucu. Rol, istemdeki 'ROLUN: <ad>.' satirindan okunur."""

    ad = "sahte"

    def __init__(self, senaryo):
        self.senaryo = senaryo
        self.cagrilar = []

    def calistir(self, istem, klasor, model=None, agent=None, zaman_asimi_sn=900, onayli=True):
        rol = istem.split("ROLUN: ", 1)[1].split(".", 1)[0]
        self.cagrilar.append((rol, model, istem))
        return self.senaryo[rol](Path(klasor), istem, len([c for c in self.cagrilar if c[0] == rol]))


def sonuc(metin="tamam", girdi=10, cikti=5, ok=True, hata=None):
    return CalistirmaSonucu(ok=ok, metin=metin, token_girdi=girdi, token_cikti=cikti, hata=hata)


@pytest.fixture(autouse=True)
def tarayici_acilmaz(monkeypatch):
    """HICBIR test gercek tarayici acmamali. (Gercek hata: segno kurulunca telegram_calistir testleri her kosuda kullanicinin
    tarayicisinda eslestirme/QR sayfasi acti.) Cagrilar listeye yazilir; testler isterse dogrulayabilir."""
    import webbrowser

    acilan = []
    monkeypatch.setattr(webbrowser, "open", lambda url, *a, **k: acilan.append(url) or False)
    monkeypatch.setattr(webbrowser, "open_new", lambda url: acilan.append(url) or False)
    monkeypatch.setattr(webbrowser, "open_new_tab", lambda url: acilan.append(url) or False)
    return acilan


@pytest.fixture(autouse=True)
def cli_kayit_yalitimi(tmp_path_factory, monkeypatch):
    """Hicbir test kullanicinin gercek ~/.aktapokus/clilar.json dosyasini okumasin ya da yazmasin."""
    monkeypatch.setenv("AKTAPOKUS_CLILAR", str(tmp_path_factory.mktemp("clilar") / "clilar.json"))


@pytest.fixture(autouse=True)
def proje_kayit_yalitimi(tmp_path_factory, monkeypatch):
    """Hicbir test kullanicinin gercek ~/.aktapokus/projeler.json dosyasini okumasin ya da yazmasin."""
    monkeypatch.setenv("AKTAPOKUS_PROJELER", str(tmp_path_factory.mktemp("projeler") / "projeler.json"))


@pytest.fixture(autouse=True)
def telegram_yonetici_yalitimi(tmp_path_factory, monkeypatch):
    """Arayuz ayari gecici; yoneticinin varsayilan token'i YOK: hicbir test gercek token'la gercek Telegram'a baglanmaz."""
    from aktapokus_ai_studio import telegram_yonetici

    monkeypatch.setenv("AKTAPOKUS_ARAYUZ_AYAR", str(tmp_path_factory.mktemp("arayuzayar") / "arayuz-ayar.json"))
    monkeypatch.setattr(telegram_yonetici, "_varsayilan_token", lambda: None)


@pytest.fixture(autouse=True)
def mcp_ve_beceri_yalitimi(tmp_path_factory, monkeypatch):
    """Hicbir test kullanicinin gercek ~/.aktapokus/mcp.json ya da ~/.agents/skills klasorunu okumasin/yazmasin."""
    monkeypatch.setenv("AKTAPOKUS_OPCUA_DB", str(tmp_path_factory.mktemp("opcuadb") / "opcua.db"))  # OPC UA olcum veritabani gercek ~/.aktapokus altina yazilmasin
    monkeypatch.setenv("AKTAPOKUS_AG_PROFILLER", str(tmp_path_factory.mktemp("agprofil") / "ag-profiller.json"))  # IP profilleri gercek ~/.aktapokus altina yazilmasin
    monkeypatch.setenv("AKTAPOKUS_OPCUA_TOPLAMA", str(tmp_path_factory.mktemp("opcuatopla") / "opcua-toplama.json"))  # kayitli toplama ayari gercek ~/.aktapokus altina yazilmasin / testler gercek toplamayi surdurmesin
    monkeypatch.setenv("AKTAPOKUS_NODERED", str(tmp_path_factory.mktemp("nodered")))  # Node-RED gercek ~/.aktapokus altina kurulmasin
    monkeypatch.setenv("AKTAPOKUS_MCP", str(tmp_path_factory.mktemp("mcp") / "mcp.json"))
    monkeypatch.setenv("AKTAPOKUS_BECERILER", str(tmp_path_factory.mktemp("beceriler") / "skills"))
    monkeypatch.setenv("AKTAPOKUS_MOTOR_TERCIH", "opencode-sunucu")  # test sonuclari bu bilgisayarda hangi CLI'in kurulu oldugundan bagimsiz olsun
    monkeypatch.setenv("AKTAPOKUS_UZAK", str(tmp_path_factory.mktemp("uzak") / "uzak-erisim.json"))  # uzak erisim ayari (anahtar iceriyor) gercek ~/.aktapokus altina ASLA yazilmasin/okunmasin
    from aktapokus_ai_studio import otomatik_baslat

    monkeypatch.setattr(otomatik_baslat, "_gercek", lambda: SahteKayit())  # Windows kayit defteri (acilista baslat) gercek makineye YAZILMASIN
    monkeypatch.setenv("AKTAPOKUS_YAYIN", str(tmp_path_factory.mktemp("yayin")))  # yayin icin klonlanan hedef depolar gercek ~/.aktapokus altina yazilmasin
    monkeypatch.setenv("AKTAPOKUS_UYGULAMA_DIZINI", str(tmp_path_factory.mktemp("uygulama")))  # kilit/pencere/arka plan isaretleri gercek ~/.aktapokus altina yazilmasin
    from aktapokus_ai_studio import uygulama as _uygulama

    monkeypatch.setattr(_uygulama, "mevcut_pencereyi_one_getir", lambda: False)  # testler kullanicinin gercek Aktapokus penceresini one getirmesin
    monkeypatch.setenv("AKTAPOKUS_IZINLER", str(tmp_path_factory.mktemp("izinler") / "izinler.json"))  # genel izinler gercek ~/.aktapokus altina yazilmasin
    monkeypatch.setenv("AKTAPOKUS_OTOMASYON", str(tmp_path_factory.mktemp("otomasyon") / "otomasyonlar.json"))  # testler gercek otomasyon tanimlarina dokunmasin
    monkeypatch.setenv("AKTAPOKUS_GOREV_META", str(tmp_path_factory.mktemp("gorevmeta") / "gorev-meta.json"))  # sabitle/arsivle bilgileri gercek ~/.aktapokus altina yazilmasin
    monkeypatch.setenv("AKTAPOKUS_CANLI", str(tmp_path_factory.mktemp("canli") / "canli.json"))  # canli durum/haber dosyalari gercek ~/.aktapokus altina yazilmasin
    monkeypatch.setenv("AKTAPOKUS_HABER_DURUM", str(tmp_path_factory.mktemp("haber") / "haber-durum.json"))
    monkeypatch.setenv("AKTAPOKUS_CLAUDE_PROJELER", str(tmp_path_factory.mktemp("claudeproje")))
    monkeypatch.setenv("AKTAPOKUS_CODEX_OTURUMLARI", str(tmp_path_factory.mktemp("codexoturum")))
    monkeypatch.setenv("AKTAPOKUS_OPENCODE_DB", str(tmp_path_factory.mktemp("ocdb") / "opencode.db"))
    monkeypatch.setenv("AKTAPOKUS_OPENCODE_HABER", str(tmp_path_factory.mktemp("ochaber") / "haber.md"))
    monkeypatch.setenv("AKTAPOKUS_GOLGE", str(tmp_path_factory.mktemp("golge")))  # golge (git'siz) yedek depolari gercek ~/.aktapokus altina yazilmasin
    from aktapokus_ai_studio import baglam as _baglam
    _baglam._ACILIS.clear()  # "uygulama acilisinda bir kere oku" isaretleri testler arasinda sizmasin
    monkeypatch.setenv("AKTAPOKUS_GH_DIZIN", str(tmp_path_factory.mktemp("ghdizin") / "gh"))  # Aktapokus'un GitHub oturumlari (varsayilan + ek hesaplar) gercek ~/.aktapokus altindan okunmasin/yazilmasin
    monkeypatch.setenv("AKTAPOKUS_GOOGLE_AYAR", str(tmp_path_factory.mktemp("googleayar") / "google-token.json"))  # Google token kaydi gercek ~/.aktapokus altina yazilmasin/okunmasin
    monkeypatch.setenv("AKTAPOKUS_GOOGLE_ISTEMCI_DOSYASI", str(tmp_path_factory.mktemp("googleistemci") / "google-istemci.json"))  # gercek client JSON okunmasin
    monkeypatch.delenv("AKTAPOKUS_GOOGLE_ISTEMCI_ID", raising=False)
