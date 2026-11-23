"""Kurulu olmayan CLI'ya bagli rol: gorev plan ONAYINDAN ONCE durur ve kurulum yolu soylenir."""

from types import SimpleNamespace

import pytest

from aktapokus_ai_studio import arayuz, clitanim

pytestmark = pytest.mark.kurulum_denetimi  # conftest denetimi varsayilan olarak atlar; burada denetimin kendisi sinanir


def _ayar(*roller):
    return SimpleNamespace(rol_sirasi=lambda: [SimpleNamespace(ad=a, calistirici=c, dogrulama=d) for a, c, d in roller])


@pytest.fixture
def listede(monkeypatch):
    monkeypatch.setattr(clitanim, "listele", lambda: [
        {"ad": "claude", "gorunen_ad": "Claude Code", "kurulu": True, "kurulum": clitanim.KURULUM["claude"]},
        {"ad": "antigravity", "gorunen_ad": "Antigravity CLI", "kurulu": False, "kurulum": clitanim.KURULUM["antigravity"]},
    ])


def test_kurulu_degilse_kurulum_yolu_ile_durur(listede):
    with pytest.raises(arayuz.UygulamaHatasi) as h:
        arayuz.Uygulama._kurulu_degilse_durdur(_ayar(("kodcu", "antigravity", False), ("test", "claude", True)), False)
    assert "Antigravity CLI kurulu degil" in str(h.value) and "install.ps1" in str(h.value) and "kodcu" in str(h.value)


def test_testsiz_kosuda_dogrulama_rolu_denetlenmez(listede):
    arayuz.Uygulama._kurulu_degilse_durdur(_ayar(("kodcu", "claude", False), ("test", "antigravity", True)), True)


def test_hepsi_kuruluysa_gecer(listede):
    arayuz.Uygulama._kurulu_degilse_durdur(_ayar(("kodcu", "claude", False)), False)


def test_her_yerlesik_cli_icin_kurulum_yolu_var():
    assert {c["ad"] for c in clitanim.listele() if c["yerlesik"]} <= set(clitanim.KURULUM)


def test_deepseek_masaustu_paketi_bulunur_ve_node_kipinde_calisir(tmp_path, monkeypatch):
    from aktapokus_ai_studio import runners
    kok = tmp_path / "Programs" / "DeepSeek Harness"
    (kok / "resources").mkdir(parents=True)
    (kok / "DeepSeek Harness.exe").write_bytes(b"MZ")
    (kok / "resources" / "app.asar").write_bytes(b"x")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("AKTAPOKUS_DSH", raising=False)
    monkeypatch.setattr(runners.shutil, "which", lambda ad: None)  # npm/dsh yok: yalniz masaustu paketi
    onek = runners.dsh_bul()
    assert onek and onek[0].endswith("DeepSeek Harness.exe") and onek[1] == "--expose-internals" and onek[2].endswith("cli.js")
    c = runners.DshCalistirici()
    assert c.komut()[:3] == onek and c.ek_ortam == {"ELECTRON_RUN_AS_NODE": "1"}  # cmd.exe sarmalayicisi kullanilmaz


def test_deepseek_masaustu_yoksa_none(tmp_path, monkeypatch):
    from aktapokus_ai_studio import runners
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert runners.dsh_masaustu() is None


def test_antigravity_kuruluysa_google_modelleri_opencode_listesinde_yok(monkeypatch):
    sahte = [{"providerID": "google", "modelID": "gemini-4-argon"}, {"providerID": "opencode", "modelID": "deepseek-v4.1-flash-free"}]
    app = arayuz.Uygulama()
    monkeypatch.setattr(app, "_saglayici_istemcisi", lambda: SimpleNamespace(modeller=lambda: sahte))
    monkeypatch.setattr(clitanim, "listele", lambda: [{"ad": "antigravity", "kurulu": True}])
    assert [m["id"] for m in app.modeller()] == ["opencode/deepseek-v4.1-flash-free"]
    monkeypatch.setattr(clitanim, "listele", lambda: [{"ad": "antigravity", "kurulu": False}])
    assert {m["id"] for m in app.modeller()} == {"google/gemini-4-argon", "opencode/deepseek-v4.1-flash-free"}


def test_google_kota_hatasi_opencode_kotasi_diye_yazilmaz():
    from aktapokus_ai_studio import sunucu
    h = sunucu.hata_acikla({"outcome": "failed", "error": "You exceeded your current quota ... https://aistudio.google.com/docs/rate-limits ... generativelanguage.googleapis.com"}, [])
    assert h.startswith("Google API anahtari (GEMINI_API_KEY) kotasi doldu") and "OpenCode" not in h


def test_agy_model_listesi_cozulur_ve_guvenli():
    from aktapokus_ai_studio import runners
    cikti = "Fetching available models...\ngemini-4-neon-high\tGemini 4 Neon (High)\nclaude-opus-5-5-low\tClaude Opus 5.5 (Low)\n--kotu\tX\nbozuk satir\ngemini-4-neon-high\tTekrar\n"
    assert runners.agy_modelleri_coz(cikti) == ["gemini-4-neon-high", "claude-opus-5-5-low"]


def test_agy_model_listesi_arayuzu_bekletmez(monkeypatch):
    from aktapokus_ai_studio import runners
    import threading
    bekle = threading.Event()
    monkeypatch.setattr(runners, "agy_bul", lambda: "agy.exe")
    monkeypatch.setattr(runners, "_agy_model_onbellek", {"zaman": 0.0, "liste": [], "calisiyor": False})
    monkeypatch.setattr(runners, "_agy_modelleri_getir", lambda: bekle.wait(5))
    assert runners.agy_modelleri() == []  # ag cagrisi arka planda; liste hemen doner
    bekle.set()
