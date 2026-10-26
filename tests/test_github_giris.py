"""GitHub'a uygulamaya ozel giris (cihaz kodu): kod alma, bekleme, onay, iptal, cikis, ortam yalitimi, uzak politika."""

import sys
import time
from pathlib import Path

import pytest

from aktapokus_ai_studio import github
from test_konusma import api  # noqa: F401  (pytest fixture)
from test_uzak import ac, sunucu as uzak_sunucu, uzak_istek, ortam  # noqa: F401

SAHTE = str(Path(__file__).resolve().parent / "sahte_gh.py")


@pytest.fixture(autouse=True)
def gh_ortami(tmp_path, monkeypatch):
    monkeypatch.setenv("AKTAPOKUS_GH", SAHTE)
    monkeypatch.setenv("AKTAPOKUS_GH_DIZIN", str(tmp_path / "gh"))
    monkeypatch.setenv("SAHTE_GH_ONAY", str(tmp_path / "onay"))
    yield
    github.giris_iptal()
    github._giris.clear()


def bekle(kosul, sn=10):
    bitis = time.time() + sn
    while time.time() < bitis:
        v = kosul()
        if v:
            return v
        time.sleep(0.1)
    return kosul()


def test_giris_kod_verir_onaydan_sonra_tamamlanir(tmp_path):
    assert github.giris_durumu() == {"durum": "yok"}
    r = github.giris_baslat()
    assert r == {"kod": "ABCD-1234", "adres": "https://github.com/login/device"}
    d = github.giris_durumu()
    assert d["durum"] == "bekliyor" and d["kod"] == "ABCD-1234"
    (tmp_path / "onay").write_text("1")  # kullanici tarayicida onayladi
    d = bekle(lambda: github.giris_durumu() if github.giris_durumu()["durum"] != "bekliyor" else None)
    assert d["durum"] == "tamam" and d["hesap"] == "sahte-kullanici"


def test_giris_iptal_ve_yeniden_baslatma(tmp_path):
    github.giris_baslat()
    assert github.giris_iptal() == {"tamam": True}
    assert bekle(lambda: github.giris_durumu()["durum"] == "iptal")
    assert github.giris_baslat()["kod"] == "ABCD-1234"  # onceki surec oldurulup yenisi baslar
    assert github.giris_durumu()["durum"] == "bekliyor"


def test_giris_basarisizsa_hata_durumu(monkeypatch):
    monkeypatch.setenv("SAHTE_GH_ONAY", "")  # onay hic gelmez: sahte gh ~10 sn sonra hata ile cikar
    github.giris_baslat()
    d = bekle(lambda: github.giris_durumu() if github.giris_durumu()["durum"] != "bekliyor" else None, sn=20)
    assert d["durum"] == "hata" and "zaman asimi" in d["hata"]


def test_ortam_uygulamaya_ozel_oturum_kullanir_belirtecleri_atar(tmp_path, monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "ghp_" + "x" * 36)
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_" + "y" * 36)
    o = github._ortam()
    assert o["GH_CONFIG_DIR"] == str(tmp_path / "gh") and "GH_TOKEN" not in o and "GITHUB_TOKEN" not in o and o["GH_PROMPT_DISABLED"] == "1"
    assert "GIT_CONFIG_COUNT" not in o  # .py (deneme) gh icin git yardimcisi eklenmez
    gercek = tmp_path / "gh.exe"
    gercek.write_text("x")
    monkeypatch.setenv("AKTAPOKUS_GH", str(gercek))
    o = github._ortam()
    assert o["GIT_CONFIG_COUNT"] == "2" and o["GIT_CONFIG_VALUE_0"] == "" and o["GIT_CONFIG_VALUE_1"].endswith('auth git-credential') and "gh.exe" in o["GIT_CONFIG_VALUE_1"]


def test_cikis_hosts_dosyasini_siler(tmp_path):
    d = tmp_path / "gh"
    d.mkdir()
    (d / "hosts.yml").write_text("github.com:\n  user: x\n")
    assert github.cikis() == {"tamam": True} and not (d / "hosts.yml").exists()


def test_uc_noktalar(api, tmp_path):
    app, istek, proje = api
    st, d = istek("GET", "/api/github/giris/durum")
    assert st == 200 and d == {"durum": "yok"}
    st, d = istek("POST", "/api/github/giris/baslat", {})
    assert st == 200 and d["kod"] == "ABCD-1234"
    assert istek("GET", "/api/github/giris/durum")[1]["durum"] == "bekliyor"
    assert istek("POST", "/api/github/giris/iptal", {})[0] == 200
    assert istek("POST", "/api/github/cikis", {})[0] == 200


def test_uzaktan_github_giris_kapali(uzak_sunucu):
    app, sv, yerel, proje = uzak_sunucu
    port, _ = ac(yerel)
    for yontem, yol in (("POST", "/api/github/giris/baslat"), ("POST", "/api/github/giris/iptal"), ("POST", "/api/github/cikis"), ("GET", "/api/github/giris/durum")):
        st, d = uzak_istek(port, yontem, yol, {} if yontem == "POST" else None)
        assert st == 403 and "uzaktan kapali" in d["hata"], yol


def test_arayuz_github_giris_karti_baglidir():
    html = (Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "web" / "index.html").read_text(encoding="utf-8")
    for parca in ("githubKarti", "/api/github/giris/baslat", "/api/github/giris/durum", "/api/github/giris/iptal", "/api/github/cikis", "Kodu kopyala", "Adresi aç"):
        assert parca in html, parca
    assert "gh auth login" not in html
