"""Gemini CLI ve Mistral Vibe calistiricilari (sahte CLI'larla; Gemini belgeye gore yazildi, Vibe akis bicimi gercek 3.0.3 ciktisindan alindi)."""

import json
import sys
import threading
import time
from pathlib import Path

import pytest

from aktapokus_ai_studio import clitanim, hesaplar, motorlar, runners
from aktapokus_ai_studio.config import BILINEN_CALISTIRICILAR
from aktapokus_ai_studio.runners import AntigravityCalistirici, CalistiriciHatasi, DshCalistirici, GeminiCalistirici, VibeCalistirici, agy_ciktisini_coz, calistirici_olustur, dsh_ciktisini_coz, gemini_ciktisini_coz

SAHTE_GEMINI = str(Path(__file__).with_name("sahte_gemini.py"))
SAHTE_VIBE = str(Path(__file__).with_name("sahte_vibe.py"))
SAHTE_DSH = str(Path(__file__).with_name("sahte_dsh.py"))
SAHTE_AGY = str(Path(__file__).with_name("sahte_agy.py"))


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


def dsh():
    return DshCalistirici([sys.executable, SAHTE_DSH])


def agy():
    return AntigravityCalistirici([sys.executable, SAHTE_AGY])


# ---------- kayit ----------
def test_yerlesik_listede_ve_calistirici_olusur():
    assert "gemini" in BILINEN_CALISTIRICILAR and "mistral" in BILINEN_CALISTIRICILAR and "deepseek" in BILINEN_CALISTIRICILAR and "antigravity" in BILINEN_CALISTIRICILAR
    assert {"gemini", "mistral", "deepseek", "antigravity"} <= set(clitanim.YERLESIK)
    assert calistirici_olustur("gemini").ad == "gemini" and calistirici_olustur("mistral").ad == "mistral" and calistirici_olustur("deepseek").ad == "deepseek" and calistirici_olustur("antigravity").ad == "antigravity"
    liste = {c["ad"]: c for c in clitanim.listele()}
    assert liste["gemini"]["yerlesik"] and "Koruyucusuz" in liste["gemini"]["aciklama"] and "Koruyucusuz" in liste["mistral"]["aciklama"] and "Koruyucusuz" in liste["deepseek"]["aciklama"] and "Koruyucusuz" in liste["antigravity"]["aciklama"]
    assert {m["ad"] for m in motorlar.MOTORLAR} >= {"gemini", "mistral", "deepseek", "antigravity"}
    with pytest.raises(clitanim.TanimHatasi):
        clitanim.tanim_coz({"ad": "gemini", "komut": [sys.executable]})  # ayrilmis ad
    with pytest.raises(clitanim.TanimHatasi):
        clitanim.tanim_coz({"ad": "deepseek", "komut": [sys.executable]})  # ayrilmis ad
    with pytest.raises(clitanim.TanimHatasi):
        clitanim.tanim_coz({"ad": "antigravity", "komut": [sys.executable]})  # ayrilmis ad


def test_bulucular_ortam_degiskeniyle(tmp_path, monkeypatch):
    exe = tmp_path / "vibe.exe"
    exe.write_text("x")
    monkeypatch.setenv("AKTAPOKUS_VIBE", str(exe))
    assert runners.vibe_bul() == str(exe) and motorlar.kurulu_mu("mistral")
    agy_exe = tmp_path / "agy.exe"
    agy_exe.write_text("x")
    monkeypatch.setenv("AKTAPOKUS_AGY", str(agy_exe))
    assert runners.agy_bul() == str(agy_exe) and motorlar.kurulu_mu("antigravity")
    agy_cmd = tmp_path / "agy.cmd"
    agy_cmd.write_text("@echo off")
    monkeypatch.setenv("AKTAPOKUS_AGY", str(agy_cmd))  # .cmd sarmalayicisi reddedilir
    monkeypatch.setattr(runners.shutil, "which", lambda a: None)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "bos"))
    monkeypatch.setattr(runners.Path, "home", staticmethod(lambda: tmp_path))
    assert runners.agy_bul() is None
    js = tmp_path / "gemini.js"
    js.write_text("x")
    monkeypatch.setenv("AKTAPOKUS_GEMINI", str(js))
    assert runners.gemini_bul()[1] == str(js) and motorlar.kurulu_mu("gemini")
    dsh_js = tmp_path / "bin.js"
    dsh_js.write_text("x")
    monkeypatch.setenv("AKTAPOKUS_DSH", str(dsh_js))
    assert runners.dsh_bul()[1] == str(dsh_js) and motorlar.kurulu_mu("deepseek")
    monkeypatch.setenv("AKTAPOKUS_GEMINI", str(tmp_path / "yok.js"))
    monkeypatch.setenv("AKTAPOKUS_DSH", str(tmp_path / "yok-dsh.js"))
    monkeypatch.setenv("PATH", "")
    monkeypatch.setenv("APPDATA", str(tmp_path / "bos"))
    assert runners.gemini_bul() is None and runners.dsh_bul() is None and runners.agy_bul() is None


# ---------- Gemini ----------
def test_gemini_komut_onayli_ve_salt_okunur_bayraklari():
    g = gemini()
    k = g.komut(None, True)
    assert k[2:] == ["-p", GeminiCalistirici.YONERGE, "--output-format", "stream-json", "--approval-mode", "yolo", "--skip-trust"]
    assert g.komut("pro", False)[-5:] == ["--approval-mode", "plan", "--skip-trust", "-m", "pro"]
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


def test_gemini_canli_olaylar_arayuz_bicimiyle_gelir_ve_durdurulur(tmp_path, monkeypatch):
    monkeypatch.setenv("SAHTE_GEMINI_MOD", "stream_canli")
    g, gelen = gemini(), []
    g.ilerleme = gelen.append
    s = g.calistir("gorev-testi", tmp_path)
    assert s.ok and s.metin == "Merhaba gorev-test"
    assert s.token_girdi == 800 and s.token_cikti == 50 and s.token_onbellek == 200
    assert {"tur": "durum", "durum": "bekliyor"} in gelen
    assert {"tur": "dusunce", "parca": "planliyorum\n"} in gelen
    assert {"tur": "arac", "ad": "run_shell_command", "girdi": {"command": "pytest -q"}} in gelen
    assert {"tur": "kabuk", "satir": "pytest -q", "sure_sn": 0} in gelen
    assert {"tur": "arac-sonuc", "hata": False} in gelen
    assert {"tur": "arac", "ad": "read_file", "girdi": {"path": "x.py"}} in gelen
    assert {"tur": "arac-sonuc", "hata": True} in gelen
    assert {"tur": "metin", "parca": "Merhaba "} in gelen and {"tur": "metin", "parca": "gorev-test"} in gelen

    monkeypatch.setenv("SAHTE_GEMINI_MOD", "takili")
    g2, sonuc = gemini(), {}
    t = threading.Thread(target=lambda: sonuc.update(s=g2.calistir("x", tmp_path)))
    t.start()
    son = time.monotonic() + 20
    while g2._islem is None and time.monotonic() < son:
        time.sleep(0.05)
    assert g2.durdur()
    t.join(30)
    assert sonuc["s"].hata == "Durduruldu"


# ---------- Mistral Vibe ----------
def test_vibe_komut_ajan_ve_model_kurali():
    v = vibe()
    k = v.komut("istem.txt", "cikti", None, True)
    assert k[2:] == ["--prompt-file", "istem.txt", "--output", "streaming", "--agent", "accept-edits", "--output-dir", "cikti"]
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
    assert not s.ok and "cikis kodu 3" in s.hata and "tur siniri" in s.hata


def test_vibe_canli_olaylar_arayuz_bicimiyle_gelir(tmp_path):
    v, gelen = vibe(), []
    v.ilerleme = gelen.append
    s = v.calistir("gorev", tmp_path)
    assert s.ok and s.metin == "Bitti: gorev"  # kullanicinin istemi yanit sayilmaz
    assert {"tur": "dusunce", "parca": "dusunuyorum\n"} in gelen
    assert {"tur": "arac", "ad": "bash", "girdi": {"command": "echo merhaba"}} in gelen
    assert {"tur": "arac-sonuc", "hata": True} in gelen and {"tur": "arac-sonuc", "hata": False} in gelen
    assert {"tur": "metin", "parca": "Bitti: gorev\n"} in gelen


def test_vibe_hareket_surdukce_zaman_asimi_olmaz_durursa_kesilir(tmp_path, monkeypatch):
    monkeypatch.setenv("SAHTE_VIBE_MOD", "yavas")
    assert vibe().calistir("x", tmp_path, zaman_asimi_sn=1).ok  # toplam ~2.5 sn ama her kayit sureyi yeniler
    monkeypatch.setenv("SAHTE_VIBE_MOD", "takili")
    s = vibe().calistir("x", tmp_path, zaman_asimi_sn=1)
    assert not s.ok and s.hata == "Zaman asimi (1 sn)" and s.sure_sn < 30


def test_vibe_durdurulur(tmp_path, monkeypatch):
    monkeypatch.setenv("SAHTE_VIBE_MOD", "takili")
    v, sonuc = vibe(), {}
    t = threading.Thread(target=lambda: sonuc.update(s=v.calistir("x", tmp_path)))
    t.start()
    son = time.monotonic() + 20
    while v._islem is None and time.monotonic() < son:
        time.sleep(0.05)
    assert v.durdur()
    t.join(30)
    assert sonuc["s"].hata == "Durduruldu"


# ---------- hesap/giris durumu ----------
def test_hesap_durumu_dosya_varligina_bakar_icerik_okumaz(tmp_path, monkeypatch):
    monkeypatch.setattr(runners, "gemini_bul", lambda: ["g"])
    monkeypatch.setattr(runners, "vibe_bul", lambda: "v")
    monkeypatch.setattr(runners, "dsh_bul", lambda: ["d"])
    monkeypatch.setattr(runners, "agy_bul", lambda: "a")
    monkeypatch.setattr(hesaplar.Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(hesaplar, "_windows_kimlik_var", lambda hedef: False)  # bu bilgisayarin gercek anahtar deposundan bagimsiz
    for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "MISTRAL_API_KEY", "VIBE_HOME", "DEEPSEEK_API_KEY", "DSH_HOME", "AGY_ADC_AUTH"):
        monkeypatch.delenv(k, raising=False)
    assert hesaplar.gemini()["giris"] is False and hesaplar.mistral()["giris"] is False and hesaplar.deepseek()["giris"] is False and hesaplar.antigravity()["giris"] is False
    (tmp_path / ".gemini").mkdir()
    (tmp_path / ".gemini" / "oauth_creds.json").write_text("{}")
    (tmp_path / ".gemini" / "antigravity-cli").mkdir()
    (tmp_path / ".gemini" / "antigravity-cli" / "settings.json").write_text("{}")
    (tmp_path / ".vibe").mkdir()
    (tmp_path / ".vibe" / ".env").write_text("MISTRAL_API_KEY=gizli-deger")
    (tmp_path / ".dsh").mkdir()
    (tmp_path / ".dsh" / ".env").write_text("DEEPSEEK_API_KEY=gizli-dsh")
    g, m, d, a = hesaplar.gemini(), hesaplar.mistral(), hesaplar.deepseek(), hesaplar.antigravity()
    assert g["giris"] and g["yontem"] == "Google hesabı" and m["giris"] and d["giris"] and d["yontem"] == "DeepSeek Harness (~/.dsh/.env)"
    assert a["giris"] and a["yontem"] == "Antigravity (Google hesabı)"
    assert "gizli-deger" not in json.dumps(m) and "gizli-deger" not in json.dumps(g) and "gizli-dsh" not in json.dumps(d)
    monkeypatch.setenv("AGY_ADC_AUTH", "true")
    assert hesaplar.antigravity() == {"kurulu": True, "giris": True, "yontem": "Google Cloud ADC"}
    monkeypatch.delenv("AGY_ADC_AUTH")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env")
    assert hesaplar.deepseek() == {"kurulu": True, "giris": True, "yontem": "API anahtarı (ortam değişkeni)"}
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    (tmp_path / ".dsh" / ".env").unlink()
    (tmp_path / ".dsh" / "settings.yaml").write_text("model: deepseek-chat\n")
    assert hesaplar.deepseek() == {"kurulu": True, "giris": True, "yontem": "DeepSeek Harness (~/.dsh/settings.yaml)"}
    monkeypatch.setattr(runners, "gemini_bul", lambda: None)
    monkeypatch.setattr(runners, "dsh_bul", lambda: None)
    monkeypatch.setattr(runners, "agy_bul", lambda: None)
    assert hesaplar.gemini() == {"kurulu": False, "giris": False} and hesaplar.deepseek() == {"kurulu": False, "giris": False} and hesaplar.antigravity() == {"kurulu": False, "giris": False}


def test_arayuz_gemini_mistral_baglidir():
    html = (Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "web" / "index.html").read_text(encoding="utf-8")
    for parca in ('c.ad==="gemini"||c.ad==="mistral"', "Gemini CLI", "Mistral Vibe", "DeepSeek Harness", 'c.ad==="deepseek"', "Antigravity CLI", 'c.ad==="antigravity"', "OpenCode · ", 'c==="antigravity"?["low","medium","high"]'):
        assert parca in html, parca


# ---------- DeepSeek Harness (dsh) ----------
def test_dsh_komut_ve_model_guvenligi():
    c = dsh()
    assert c.komut(None, True)[2:] == ["--profile", "headless"]
    assert c.komut("deepseek-chat", False)[2:] == ["--profile", "headless", "--model", "deepseek-chat"]
    with pytest.raises(CalistiriciHatasi):
        c.komut("--patch", True)


def test_dsh_istem_stdinden_aynen_gider_duz_metin_ve_json_cozulur(tmp_path, log, monkeypatch):
    istem = "Satir1\nSatir2 \"tirnak\" 'tek' $HOME & | > ğüşiöç"
    s = dsh().calistir(istem, tmp_path)
    assert s.ok and s.metin.startswith("Tamam: Satir1") and s.token_girdi == 0 and s.token_cikti == 0
    kayit = satirlar(log)[0]
    assert kayit["stdin"] == istem and istem not in " ".join(kayit["argv"]) and Path(kayit["cwd"]).resolve() == tmp_path.resolve()

    monkeypatch.setenv("SAHTE_DSH_MOD", "json")
    s_json = dsh().calistir(istem, tmp_path)
    assert s_json.ok and s_json.metin.startswith("Tamam: Satir1")
    assert s_json.token_girdi == 900 and s_json.token_cikti == 50 and s_json.token_onbellek == 200

    monkeypatch.setenv("SAHTE_DSH_MOD", "jsonl")
    s_jsonl = dsh().calistir(istem, tmp_path)
    assert s_jsonl.ok and s_jsonl.metin == "SatirA\nSatirB"
    assert s_jsonl.token_girdi == 400 and s_jsonl.token_cikti == 40 and s_jsonl.token_onbellek == 100


def test_dsh_hatalar_ve_bulunamama(tmp_path, monkeypatch):
    for mod, parca in (("hata", "bakiye yetersiz"), ("cikis1", "cikis kodu 1")):
        monkeypatch.setenv("SAHTE_DSH_MOD", mod)
        s = dsh().calistir("x", tmp_path)
        assert not s.ok and parca in s.hata, mod
    with pytest.raises(CalistiriciHatasi):
        dsh().calistir("   ", tmp_path)
    monkeypatch.setattr(runners, "dsh_bul", lambda: None)
    with pytest.raises(CalistiriciHatasi, match="bulunamadi"):
        DshCalistirici().komut()


def test_dsh_ciktisi_duz_metin_json_ve_karisik_log_cozulur():
    assert dsh_ciktisini_coz("merhaba dunya\n").metin == "merhaba dunya"
    assert dsh_ciktisini_coz('{"other":"json"}\n').metin == '{"other":"json"}'
    s = dsh_ciktisini_coz('dsh: starting\n{"event":"response","data":{"text":"hazir","usage":{"prompt_tokens":300,"completion_tokens":20,"cache_read_tokens":50}}}\n')
    assert s.ok and s.metin == "hazir" and s.token_girdi == 250 and s.token_cikti == 20 and s.token_onbellek == 50


def test_dsh_canli_olaylar_arayuz_bicimiyle_gelir_ve_durdurulur(tmp_path, monkeypatch):
    monkeypatch.setenv("SAHTE_DSH_MOD", "jsonl")
    d, gelen = dsh(), []
    d.ilerleme = gelen.append
    s = d.calistir("gorev", tmp_path)
    assert s.ok and s.metin == "SatirA\nSatirB"
    assert {"tur": "dusunce", "parca": "analiz ediyorum\n"} in gelen
    assert {"tur": "dusunce", "parca": "derin dusunce\n"} in gelen
    assert {"tur": "arac", "ad": "bash", "girdi": {"command": "pytest"}} in gelen
    assert {"tur": "kabuk", "satir": "pytest", "sure_sn": 0} in gelen
    assert {"tur": "arac-sonuc", "hata": False} in gelen
    assert {"tur": "metin", "parca": "SatirA\n"} in gelen and {"tur": "metin", "parca": "SatirB\n"} in gelen

    monkeypatch.setenv("SAHTE_DSH_MOD", "takili")
    d2, sonuc = dsh(), {}
    t = threading.Thread(target=lambda: sonuc.update(s=d2.calistir("x", tmp_path)))
    t.start()
    son = time.monotonic() + 20
    while d2._islem is None and time.monotonic() < son:
        time.sleep(0.05)
    assert d2.durdur()
    t.join(30)
    assert sonuc["s"].hata == "Durduruldu"


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


# ---------- Antigravity CLI (agy) ----------
def test_agy_komut_izin_model_ve_effort_bayraklari():
    c = agy()
    assert c.komut(None, True)[2:] == ["-p", AntigravityCalistirici.YONERGE, "--output-format", "stream-json", "--dangerously-skip-permissions"]
    assert c.komut(None, False)[2:] == ["-p", AntigravityCalistirici.YONERGE, "--output-format", "stream-json", "--mode=plan"]
    c.dusunme = "high"
    assert c.komut("gemini-pro", True)[-4:] == ["--effort", "high", "--model", "gemini-pro"]
    c.dusunme = "max"  # desteklenmeyen seviye yok sayilir
    assert "--effort" not in c.komut(None, True)
    with pytest.raises(CalistiriciHatasi):
        c.komut("--model", True)


def test_agy_canli_akim_stdin_ve_durdurma(tmp_path, log, monkeypatch):
    c, gelen = agy(), []
    c.ilerleme = gelen.append
    istem = "Satir1\nSatir2 \"tirnak\" 'tek' $HOME & | > ğüşiöç"
    s = c.calistir(istem, tmp_path)
    assert s.ok and s.metin == "Merhaba Satir1\nSat"
    assert s.token_girdi == 800 and s.token_cikti == 50 and s.token_onbellek == 200
    kayit = satirlar(log)[0]
    assert kayit["istem"] == istem and kayit["stdin"] == "" and ("--print=" + istem) in kayit["argv"] and Path(kayit["cwd"]).resolve() == tmp_path.resolve()  # agy stdin okumaz: istem TEK arguman
    assert {"tur": "durum", "durum": "bekliyor"} in gelen
    assert {"tur": "dusunce", "parca": "planliyorum\n"} in gelen
    assert {"tur": "arac", "ad": "bash", "girdi": {"command": "pytest -q"}} in gelen
    assert {"tur": "kabuk", "satir": "pytest -q", "sure_sn": 0} in gelen
    assert {"tur": "arac-sonuc", "hata": False} in gelen
    assert {"tur": "arac", "ad": "read_file", "girdi": {"path": "x.py"}} in gelen
    assert {"tur": "arac-sonuc", "hata": True} in gelen
    assert {"tur": "metin", "parca": "Merhaba "} in gelen and {"tur": "metin", "parca": "Satir1\nSat"} in gelen

    monkeypatch.setenv("SAHTE_AGY_MOD", "takili")
    c2, sonuc = agy(), {}
    t = threading.Thread(target=lambda: sonuc.update(s=c2.calistir("x", tmp_path)))
    t.start()
    son = time.monotonic() + 20
    while c2._islem is None and time.monotonic() < son:
        time.sleep(0.05)
    assert c2.durdur()
    t.join(30)
    assert sonuc["s"].hata == "Durduruldu"


def test_agy_gercek_ic_ice_bicim_cozulur(tmp_path, monkeypatch):
    """agy 1.5 gercek cikti: olaylar step_update/result icinde; metin text_delta, arac tool_info.parameters (CommandLine, Path)."""
    monkeypatch.setenv("SAHTE_AGY_MOD", "gercek")
    c, gelen = agy(), []
    c.ilerleme = gelen.append
    s = c.calistir("merhaba dunya", tmp_path)
    assert s.ok and s.metin == "Tamam: merhab" and s.token_girdi == 700 and s.token_cikti == 30 and s.token_onbellek == 100
    assert {"tur": "arac", "ad": "run_command", "girdi": {"command": "dir"}} in gelen and {"tur": "kabuk", "satir": "dir", "sure_sn": 0} in gelen
    assert {"tur": "arac", "ad": "write_file", "girdi": {"path": "not.txt"}} in gelen
    assert {"tur": "arac-sonuc", "hata": False} in gelen and {"tur": "arac-sonuc", "hata": True} in gelen
    assert {"tur": "metin", "parca": "Tamam: "} in gelen


def test_agy_istem_tire_ile_baslasa_da_bayrak_sanilmaz():
    assert agy().komut(None, True, "--model x")[2] == "--print=--model x"
    with pytest.raises(CalistiriciHatasi):
        agy().calistir("x" * 30000, ".")  # Windows komut satiri siniri: istem arguman olarak gider


def test_agy_tekli_json_duz_metin_ve_hatalar(tmp_path, monkeypatch):
    monkeypatch.setenv("SAHTE_AGY_MOD", "json")
    s_json = agy().calistir("merhaba", tmp_path)
    assert s_json.ok and s_json.metin == "Tamam: merhaba" and s_json.token_girdi == 800 and s_json.token_cikti == 50 and s_json.token_onbellek == 200

    monkeypatch.setenv("SAHTE_AGY_MOD", "metin")
    s_metin = agy().calistir("merhaba", tmp_path)
    assert s_metin.ok and s_metin.metin == "Tamam: merhaba"

    for mod, parca in (("hata", "kota doldu"), ("cikis1", "cikis kodu 1")):
        monkeypatch.setenv("SAHTE_AGY_MOD", mod)
        s_hata = agy().calistir("x", tmp_path)
        assert not s_hata.ok and parca in s_hata.hata, mod

    with pytest.raises(CalistiriciHatasi):
        agy().calistir("   ", tmp_path)
    monkeypatch.setattr(runners, "agy_bul", lambda: None)
    with pytest.raises(CalistiriciHatasi, match="bulunamadi"):
        AntigravityCalistirici().komut()
    assert agy_ciktisini_coz("duz yanit\n").metin == "duz yanit"
