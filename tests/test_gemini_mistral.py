"""Gemini CLI ve Mistral Vibe calistiricilari (sahte CLI'larla; gercek CLI'lar bu makinede kurulu degil, belgeye gore yazildi)."""

import json
import sys
from pathlib import Path

import pytest

from aktapokus_ai_studio import clitanim, hesaplar, motorlar, runners
from aktapokus_ai_studio.config import BILINEN_CALISTIRICILAR
from aktapokus_ai_studio.runners import CalistiriciHatasi, GeminiCalistirici, VibeCalistirici, calistirici_olustur, gemini_ciktisini_coz

SAHTE_GEMINI = str(Path(__file__).with_name("sahte_gemini.py"))
SAHTE_VIBE = str(Path(__file__).with_name("sahte_vibe.py"))


@pytest.fixture
def log(tmp_path, monkeypatch):
    yol = tmp_path / "cli.log"
    monkeypatch.setenv("SAHTE_CLI_LOG", str(yol))
    return yol


def satirlar(yol):
    return [json.loads(s) for s in yol.read_text(encoding="utf-8").splitlines()]


def gemini():
    return GeminiCalistirici([sys.executable, SAHTE_GEMINI])


def vibe():
    return VibeCalistirici([sys.executable, SAHTE_VIBE])


# ---------- kayit ----------
def test_yerlesik_listede_ve_calistirici_olusur():
    assert "gemini" in BILINEN_CALISTIRICILAR and "mistral" in BILINEN_CALISTIRICILAR
    assert {"gemini", "mistral"} <= set(clitanim.YERLESIK)
    assert calistirici_olustur("gemini").ad == "gemini" and calistirici_olustur("mistral").ad == "mistral"
    liste = {c["ad"]: c for c in clitanim.listele()}
    assert liste["gemini"]["yerlesik"] and "Koruyucusuz" in liste["gemini"]["aciklama"] and "Koruyucusuz" in liste["mistral"]["aciklama"]
    assert {m["ad"] for m in motorlar.MOTORLAR} >= {"gemini", "mistral"}
    with pytest.raises(clitanim.TanimHatasi):
        clitanim.tanim_coz({"ad": "gemini", "komut": [sys.executable]})  # ayrilmis ad


def test_bulucular_ortam_degiskeniyle(tmp_path, monkeypatch):
    exe = tmp_path / "vibe.exe"
    exe.write_text("x")
    monkeypatch.setenv("AKTAPOKUS_VIBE", str(exe))
    assert runners.vibe_bul() == str(exe) and motorlar.kurulu_mu("mistral")
    js = tmp_path / "gemini.js"
    js.write_text("x")
    monkeypatch.setenv("AKTAPOKUS_GEMINI", str(js))
    assert runners.gemini_bul()[1] == str(js) and motorlar.kurulu_mu("gemini")
    monkeypatch.setenv("AKTAPOKUS_GEMINI", str(tmp_path / "yok.js"))
    monkeypatch.setenv("PATH", "")
    monkeypatch.setenv("APPDATA", str(tmp_path / "bos"))
    assert runners.gemini_bul() is None


# ---------- Gemini ----------
def test_gemini_komut_onayli_ve_salt_okunur_bayraklari():
    g = gemini()
    k = g.komut(None, True)
    assert k[2:] == ["-p", GeminiCalistirici.YONERGE, "--output-format", "json", "--approval-mode", "yolo"]
    assert g.komut("pro", False)[-4:] == ["--approval-mode", "plan", "-m", "pro"]
    with pytest.raises(CalistiriciHatasi):
        g.komut("--yolo", True)


def test_gemini_istem_stdinden_aynen_gider_ve_json_cozulur(tmp_path, log):
    istem = "Satir1\nSatir2 \"tirnak\" 'tek' $HOME & | > ğüşiöç"
    s = gemini().calistir(istem, tmp_path, onayli=True)
    assert s.ok and s.metin.startswith("Tamam: Satir1") and s.token_girdi == 800 and s.token_cikti == 50 and s.token_onbellek == 200  # onbellek girdiden dusulur
    kayit = satirlar(log)[0]
    assert kayit["stdin"] == istem and istem not in " ".join(kayit["argv"]) and Path(kayit["cwd"]).resolve() == tmp_path.resolve()


def test_gemini_hatalar(tmp_path, monkeypatch):
    for mod, parca in (("hata", "kota doldu"), ("bozuk", "JSON degil"), ("cikis1", "cikis kodu 1")):
        monkeypatch.setenv("SAHTE_GEMINI_MOD", mod)
        s = gemini().calistir("x", tmp_path)
        assert not s.ok and parca in s.hata, mod
    with pytest.raises(CalistiriciHatasi):
        gemini().calistir("   ", tmp_path)


def test_gemini_ciktisi_log_satirlariyla_karisik_olsa_da_cozulur():
    s = gemini_ciktisini_coz('Loaded cached credentials.\n{"response":"merhaba","stats":{}}\n')
    assert s.ok and s.metin == "merhaba" and s.token_girdi == 0


# ---------- Mistral Vibe ----------
def test_vibe_komut_ajan_ve_model_kurali():
    v = vibe()
    k = v.komut("istem.txt", "cikti", None, True)
    assert k[2:] == ["--prompt-file", "istem.txt", "--output", "text", "--agent", "accept-edits", "--output-dir", "cikti"]
    assert v.komut("istem.txt", "cikti", None, False)[k.index("--agent")] == "--agent" and "plan" in v.komut("istem.txt", "cikti", None, False)
    with pytest.raises(CalistiriciHatasi, match="model"):
        v.komut("istem.txt", "cikti", "mistral-large", True)


def test_vibe_istem_dosyadan_gider_token_exporttan_okunur(tmp_path, log):
    istem = "Satir1\nSatir2 \"tirnak\" ğüşiöç"
    s = vibe().calistir(istem, tmp_path)
    assert s.ok and s.metin.startswith("Bitti: Satir1") and s.token_girdi == 700 and s.token_cikti == 30
    kayit = satirlar(log)[0]
    assert kayit["istem"] == istem and istem not in " ".join(kayit["argv"])


def test_vibe_sinir_cikis_kodu_hata_sayilir(tmp_path, monkeypatch):
    monkeypatch.setenv("SAHTE_VIBE_MOD", "sinir")
    s = vibe().calistir("x", tmp_path)
    assert not s.ok and "cikis kodu 3" in s.hata


# ---------- hesap/giris durumu ----------
def test_hesap_durumu_dosya_varligina_bakar_icerik_okumaz(tmp_path, monkeypatch):
    monkeypatch.setattr(runners, "gemini_bul", lambda: ["g"])
    monkeypatch.setattr(runners, "vibe_bul", lambda: "v")
    monkeypatch.setattr(hesaplar.Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(hesaplar, "_windows_kimlik_var", lambda hedef: False)  # bu bilgisayarin gercek anahtar deposundan bagimsiz
    for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "MISTRAL_API_KEY", "VIBE_HOME"):
        monkeypatch.delenv(k, raising=False)
    assert hesaplar.gemini()["giris"] is False and hesaplar.mistral()["giris"] is False
    (tmp_path / ".gemini").mkdir()
    (tmp_path / ".gemini" / "oauth_creds.json").write_text("{}")
    (tmp_path / ".vibe").mkdir()
    (tmp_path / ".vibe" / ".env").write_text("MISTRAL_API_KEY=gizli-deger")
    g, m = hesaplar.gemini(), hesaplar.mistral()
    assert g["giris"] and g["yontem"] == "Google hesabı" and m["giris"]
    assert "gizli-deger" not in json.dumps(m) and "gizli-deger" not in json.dumps(g)
    monkeypatch.setattr(runners, "gemini_bul", lambda: None)
    assert hesaplar.gemini() == {"kurulu": False, "giris": False}


def test_arayuz_gemini_mistral_baglidir():
    html = (Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "web" / "index.html").read_text(encoding="utf-8")
    for parca in ('c.ad==="gemini"||c.ad==="mistral"', "Gemini CLI", "Mistral Vibe"):
        assert parca in html, parca


def test_vibe_3_salt_okunur_kipte_plan_yerine_ask_kullanilir(monkeypatch):
    """Gercek hata: Vibe 3.0.3'te 'plan' ajani yok ("Agent 'plan' not found"); yerlesik ajanlar ask/accept-edits/smart-approve/auto-approve."""
    from aktapokus_ai_studio import runners

    class Cikti:
        def __init__(self, metin):
            self.stdout = metin.encode("utf-8")

    yeni = "--agent <NAME>\n Agent to use (builtin: ask, accept-edits, smart-approve, auto-approve, or custom from ~/.vibe/agents/NAME.toml)"
    eski = "--agent <NAME>\n Agent to use (builtin: default, plan, accept-edits, auto-approve)"
    for yol, yardim, beklenen in (("C:/x/vibe3.exe", yeni, "ask"), ("C:/x/vibe2.exe", eski, "plan")):
        monkeypatch.setattr(runners.subprocess, "run", lambda *a, _y=yardim, **k: Cikti(_y))
        monkeypatch.setattr(runners, "vibe_bul", lambda y=yol: y)
        runners._VIBE_OKUNUR_AJAN.clear()
        k = runners.VibeCalistirici().komut("istem.txt", "cikti", None, False)
        assert k[k.index("--agent") + 1] == beklenen, yol
        assert runners.VibeCalistirici().komut("istem.txt", "cikti", None, True)[k.index("--agent") + 1] == "accept-edits"  # onayli kip degismez
    monkeypatch.setattr(runners.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError("yok")))
    runners._VIBE_OKUNUR_AJAN.clear()
    assert runners._vibe_okunur_ajan(["C:/x/yok.exe"]) == "plan"  # okunamazsa eski varsayilan


def test_mistral_anahtar_deposundaysa_giris_yapildi_sayilir_deger_okunmaz(tmp_path, monkeypatch):
    """Gercek durum: Vibe tarayici girisinde anahtari Windows anahtar deposuna yazar (~/.vibe/.env olusmaz); rozet 'giris yok' demesin."""
    monkeypatch.setattr(runners, "vibe_bul", lambda: "v")
    monkeypatch.setattr(hesaplar.Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.delenv("VIBE_HOME", raising=False)
    sorulan = []
    monkeypatch.setattr(hesaplar, "_windows_kimlik_var", lambda hedef: sorulan.append(hedef) or True)
    m = hesaplar.mistral()
    assert m == {"kurulu": True, "giris": True, "yontem": "Windows anahtar deposu"} and sorulan == ["MISTRAL_API_KEY@ai.mistral.vibe"]
    monkeypatch.setattr(hesaplar, "_windows_kimlik_var", lambda hedef: False)
    assert hesaplar.mistral()["giris"] is False


def test_windows_kimlik_var_yalniz_kayit_adina_bakar(monkeypatch):
    class Cikti:
        returncode = 0
        stdout = (
            "Currently stored credentials for X:\n\n"
            "    Target: MISTRAL_API_KEY@ai.mistral.vibe\n"
            "    Type: Generic\n"
            "    User: gizli-kullanici\n"
        )

    monkeypatch.setattr(hesaplar.os, "name", "nt")
    monkeypatch.setattr(hesaplar.subprocess, "run", lambda *a, **k: Cikti())
    assert hesaplar._windows_kimlik_var("MISTRAL_API_KEY@ai.mistral.vibe") is True
    assert hesaplar._windows_kimlik_var("baska@hedef") is False
    monkeypatch.setattr(hesaplar.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError("yok")))
    assert hesaplar._windows_kimlik_var("MISTRAL_API_KEY@ai.mistral.vibe") is False
    monkeypatch.setattr(hesaplar.os, "name", "posix")
    assert hesaplar._windows_kimlik_var("MISTRAL_API_KEY@ai.mistral.vibe") is False
