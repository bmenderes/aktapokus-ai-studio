import json
from pathlib import Path
import subprocess

import pytest

from aktapokus_ajan import runners
from aktapokus_ajan.runners import (
    CalistiriciHatasi,
    ClaudeCodeCalistirici,
    OpenCodeCalistirici,
    calistirici_olustur,
    opencode_olaylarini_coz,
)

# Gercek `opencode-cli run --format json` ciktisindan (v2.0.30) alinan satirlarin kisaltilmis hali
GERCEK = "\n".join(
    [
        '{"type":"step_start","timestamp":1,"sessionID":"s","part":{"type":"step-start"}}',
        '{"type":"tool_use","timestamp":2,"sessionID":"s","part":{"type":"tool","tool":"write","state":{"status":"completed"}}}',
        '{"type":"step_finish","timestamp":3,"sessionID":"s","part":{"type":"step-finish","reason":"tool-calls","cost":0,"tokens":{"input":0,"output":120,"reasoning":15,"cache":{"read":5504,"write":0}}}}',
        '{"type":"text","timestamp":4,"sessionID":"s","part":{"type":"text","text":"tamam"}}',
    ]
)


def test_opencode_olaylari_gercek_cikti():
    r = opencode_olaylarini_coz(GERCEK)
    assert r.ok and r.metin == "tamam"
    assert (r.token_girdi, r.token_cikti, r.token_onbellek) == (0, 135, 5504)  # cikti = output + reasoning
    assert r.token_yeni == 135


def test_opencode_olaylari_coklu_adim_toplanir_ve_bozuk_satir_atlanir():
    cikti = "\n".join(
        [
            "gurultu satiri",
            '{"type":"step_finish","part":{"tokens":{"input":100,"output":10,"reasoning":0,"cache":{"read":50}}}}',
            "{bozuk json",
            '{"type":"step_finish","part":{"tokens":{"input":200,"output":20,"cache":{"read":0}}}}',
            '{"type":"text","part":{"text":"bir"}}',
            '{"type":"text","part":{"text":"iki"}}',
        ]
    )
    r = opencode_olaylarini_coz(cikti)
    assert (r.token_girdi, r.token_cikti, r.token_onbellek) == (300, 30, 50)
    assert r.metin == "bir\niki"


def test_opencode_hata_olayi_ok_false():
    r = opencode_olaylarini_coz('{"type":"error","error":{"message":"limit"}}')
    assert not r.ok and "limit" in r.hata


def test_opencode_bos_cikti_ok_ama_metin_bos():
    r = opencode_olaylarini_coz("")
    assert r.ok and r.metin == "" and r.token_yeni == 0


def test_opencode_komut_kabuksuz_ve_dogru_bayraklar():
    c = OpenCodeCalistirici(cli_yolu="oc")
    assert c.komut("selam", "opencode/x", "build", True) == [
        "oc", "run", "--standalone", "--format", "json", "--auto", "--model", "opencode/x", "--agent", "build", "selam",
    ]
    assert c.komut("selam", None, None, False) == ["oc", "run", "--standalone", "--format", "json", "selam"]


@pytest.mark.parametrize("istem", ["", "   ", "-x gizli secenek", "a" * (runners.AZAMI_ISTEM_UZUNLUGU + 1)])
def test_gecersiz_istemler_reddedilir(istem):
    with pytest.raises(CalistiriciHatasi):
        OpenCodeCalistirici(cli_yolu="oc").komut(istem, None, None, True)


@pytest.mark.parametrize("tur", ["bos", "bosluk", "cok-uzun"])
def test_claude_bos_ve_asiri_buyuk_istem_reddedilir(tur, tmp_path):
    istem = {"bos": "", "bosluk": "   ", "cok-uzun": "a" * 1_000_001}[tur]
    with pytest.raises(CalistiriciHatasi):
        ClaudeCodeCalistirici(cli_yolu="cl").calistir(istem, tmp_path)


def test_istem_ozel_karakterleri_tek_arguman_kalir():
    istem = 'tirnak " ve & | ; $(x) %PATH% satir\nsonu'
    assert OpenCodeCalistirici(cli_yolu="oc").komut(istem, None, None, True)[-1] == istem


def test_cli_yoksa_anlamli_hata(monkeypatch):
    monkeypatch.setattr(runners, "opencode_bul", lambda: None)
    with pytest.raises(CalistiriciHatasi, match="OpenCode CLI bulunamadi"):
        OpenCodeCalistirici().komut("x", None, None, True)
    monkeypatch.setattr(runners.shutil, "which", lambda _a: None)
    monkeypatch.delenv("AKTAPOKUS_CLAUDE", raising=False)
    monkeypatch.setattr(runners, "claude_bul", lambda: None)
    with pytest.raises(CalistiriciHatasi, match="Claude Code CLI bulunamadi"):
        ClaudeCodeCalistirici().komut("ayar.json", None, True)


class SahteIslem:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout, self.stderr, self.returncode = stdout, stderr, returncode


def test_calistir_basarili_ve_arguman_gecisi(monkeypatch, tmp_path):
    gorulen = {}

    def sahte_run(komut, **kw):
        gorulen["komut"], gorulen["kw"] = komut, kw
        return SahteIslem(stdout=GERCEK)

    monkeypatch.setattr(runners.subprocess, "run", sahte_run)
    r = OpenCodeCalistirici(cli_yolu="oc").calistir("selam", tmp_path, model="m")
    assert r.ok and r.metin == "tamam" and r.sure_sn >= 0
    assert gorulen["kw"]["cwd"] == str(tmp_path)
    assert gorulen["kw"]["stdin"] == subprocess.DEVNULL
    assert gorulen["kw"]["env"]["PWD"] == str(tmp_path)  # gercek hata: PWD eski kalinca ajan yanlis klasore yazdi
    assert "OLDPWD" not in gorulen["kw"]["env"]
    assert "shell" not in gorulen["kw"] or gorulen["kw"]["shell"] is False


def test_pwd_eski_kabuk_klasorunu_tasisa_bile_hedefe_ayarlanir(monkeypatch, tmp_path):
    monkeypatch.setenv("PWD", "/baska/klasor")
    monkeypatch.setenv("OLDPWD", "/eski")
    gorulen = []
    monkeypatch.setattr(runners.subprocess, "run", lambda komut, **kw: (gorulen.append(kw["env"]), SahteIslem(stdout=json.dumps({"result": "x"})))[1])
    ClaudeCodeCalistirici(cli_yolu="cl").calistir("selam", tmp_path)
    OpenCodeCalistirici(cli_yolu="oc").calistir("selam", tmp_path)
    assert [e["PWD"] for e in gorulen] == [str(tmp_path), str(tmp_path)]
    assert all("OLDPWD" not in e for e in gorulen)


def test_calistir_zaman_asimi_ve_cikis_kodu(monkeypatch, tmp_path):
    def zaman_asimi(komut, **kw):
        raise subprocess.TimeoutExpired(komut, kw["timeout"])

    monkeypatch.setattr(runners.subprocess, "run", zaman_asimi)
    r = OpenCodeCalistirici(cli_yolu="oc").calistir("selam", tmp_path, zaman_asimi_sn=12)
    assert not r.ok and "Zaman asimi (12 sn)" in r.hata

    monkeypatch.setattr(runners.subprocess, "run", lambda *a, **k: SahteIslem(stdout="", stderr="patladi", returncode=3))
    r = OpenCodeCalistirici(cli_yolu="oc").calistir("selam", tmp_path)
    assert not r.ok and "cikis kodu 3" in r.hata and "patladi" in r.hata


def test_claude_komut_ve_cikti_cozumu():
    c = ClaudeCodeCalistirici(cli_yolu="cl")
    assert c.komut("a.json", "opus", True) == [
        "cl", "-p", "--output-format", "json", "--settings", "a.json", "--model", "opus", "--permission-mode", "acceptEdits",
    ]
    assert c.komut("a.json", None, False) == ["cl", "-p", "--output-format", "json", "--settings", "a.json"]
    ok = ClaudeCodeCalistirici.cikti_coz(
        json.dumps({"result": "bitti", "is_error": False, "usage": {
            "input_tokens": 7, "cache_creation_input_tokens": 100, "output_tokens": 3, "cache_read_input_tokens": 99}})
    )
    assert ok.ok and ok.metin == "bitti" and (ok.token_girdi, ok.token_cikti, ok.token_onbellek) == (107, 3, 99)
    hata = ClaudeCodeCalistirici.cikti_coz(json.dumps({"result": "limit doldu", "is_error": True}))
    assert not hata.ok and "limit doldu" in hata.hata
    assert not ClaudeCodeCalistirici.cikti_coz("json degil").ok


def test_claude_reddedilen_izinler_metinde_gorunur():
    r = ClaudeCodeCalistirici.cikti_coz(json.dumps({
        "result": "yapamadim", "is_error": False,
        "permission_denials": [{"tool_name": "Write"}, {"tool_name": "Bash"}, {"tool_name": "Write"}],
    }))
    assert r.ok and "izin reddedildi: Bash, Write" in r.metin


def test_claude_istem_stdinden_ve_yasak_kurallari_ayar_dosyasinda(monkeypatch, tmp_path):
    gorulen = {}

    def sahte_run(komut, **kw):
        gorulen["komut"], gorulen["kw"] = komut, kw
        ayar = Path(komut[komut.index("--settings") + 1])
        gorulen["ayar"] = json.loads(ayar.read_text(encoding="utf-8"))  # gecici dizin silinmeden once oku
        return SahteIslem(stdout=json.dumps({"result": "x"}))

    monkeypatch.setattr(runners.subprocess, "run", sahte_run)
    istem = "-ile baslayan \" tirnakli & istem"
    ClaudeCodeCalistirici(cli_yolu="cl").calistir(istem, tmp_path)
    assert gorulen["kw"]["input"] == istem.encode("utf-8") and istem not in gorulen["komut"]  # bayt: \n -> \r\n cevrilmez
    assert "Read(**/.env)" in gorulen["ayar"]["permissions"]["deny"] and "Edit(**/.env.*)" in gorulen["ayar"]["permissions"]["deny"]
    assert not Path(gorulen["komut"][gorulen["komut"].index("--settings") + 1]).exists()  # gecici ayar silinir


def test_claude_bul_cmd_sarmalayicisini_kullanmaz(monkeypatch, tmp_path):
    monkeypatch.delenv("AKTAPOKUS_CLAUDE", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "ap"))
    monkeypatch.setattr(runners.Path, "home", classmethod(lambda cls: tmp_path / "ev"))
    npm = tmp_path / "ap" / "npm"
    npm.mkdir(parents=True)
    (npm / "claude.cmd").write_text("@echo off")
    monkeypatch.setattr(runners.shutil, "which", lambda a: str(npm / "claude.cmd") if a == "claude" else None)
    assert runners.claude_bul() is None
    exe = npm / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("")
    assert runners.claude_bul() == str(exe)


def test_opencode_bul_ortam_ve_masaustu_paketi(monkeypatch, tmp_path):
    monkeypatch.delenv("AKTAPOKUS_OPENCODE", raising=False)
    monkeypatch.setattr(runners.shutil, "which", lambda _a: None)
    cli = tmp_path / "ai.opencode.desktop" / "cli"
    for surum in ("1.9.0-x64", "2.0.30-x64", "2.0.4-x64"):
        (cli / surum).mkdir(parents=True)
        (cli / surum / "opencode-cli.exe").write_text("x")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert runners.opencode_bul().endswith(str(cli / "2.0.30-x64" / "opencode-cli.exe"))  # sayisal siralama, 2.0.4 degil
    ozel = tmp_path / "ozel.exe"
    ozel.write_text("x")
    monkeypatch.setenv("AKTAPOKUS_OPENCODE", str(ozel))
    assert runners.opencode_bul() == str(ozel)


def test_calistirici_olustur():
    assert isinstance(calistirici_olustur("opencode"), OpenCodeCalistirici)
    assert isinstance(calistirici_olustur("claude"), ClaudeCodeCalistirici)
    with pytest.raises(CalistiriciHatasi):
        calistirici_olustur("yok")
