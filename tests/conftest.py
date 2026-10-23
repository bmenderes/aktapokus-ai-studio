import subprocess
from pathlib import Path

import pytest

from aktapokus_ajan import guard, snapshot
from aktapokus_ajan.runners import Calistirici, CalistirmaSonucu


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
    from aktapokus_ajan import telegram_yonetici

    monkeypatch.setenv("AKTAPOKUS_ARAYUZ_AYAR", str(tmp_path_factory.mktemp("arayuzayar") / "arayuz-ayar.json"))
    monkeypatch.setattr(telegram_yonetici, "_varsayilan_token", lambda: None)


@pytest.fixture(autouse=True)
def mcp_ve_beceri_yalitimi(tmp_path_factory, monkeypatch):
    """Hicbir test kullanicinin gercek ~/.aktapokus/mcp.json ya da ~/.agents/skills klasorunu okumasin/yazmasin."""
    monkeypatch.setenv("AKTAPOKUS_MCP", str(tmp_path_factory.mktemp("mcp") / "mcp.json"))
    monkeypatch.setenv("AKTAPOKUS_BECERILER", str(tmp_path_factory.mktemp("beceriler") / "skills"))
    monkeypatch.setenv("AKTAPOKUS_GOLGE", str(tmp_path_factory.mktemp("golge")))  # golge (git'siz) yedek depolari gercek ~/.aktapokus altina yazilmasin
