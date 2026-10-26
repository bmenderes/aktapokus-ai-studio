"""Codex ve OpenCode konusmalari + Aktapokus haberi (OpenCode talimat dosyasi, Codex/Claude kancasi kurulumu)."""

import json
import sqlite3
import time
from pathlib import Path

import pytest

from aktapokus_ai_studio import arac_oturumlari as ao, canli, haber
from test_konusma import api  # noqa: F401  (pytest fixture)
from test_uzak import ac, sunucu as uzak_sunucu, uzak_istek, ortam  # noqa: F401

CODEX_ID = "01a1690a-c7ae-7682-9f97-0484eda4db80"
OC_ID = "ses_e868e4a3affeL4lMFQ6yw4E09f"


def _codex_yaz(klasor, kimlik=CODEX_ID, satirlar=None):
    d = ao.codex_kok() / "2026" / "10" / "26"
    d.mkdir(parents=True, exist_ok=True)
    meta = {"type": "session_meta", "payload": {"id": kimlik, "cwd": str(klasor), "base_instructions": {"text": "x" * 20000}}, "timestamp": "t0"}
    varsayilan = [
        {"type": "event_msg", "payload": {"type": "item_completed", "item": {"type": "UserMessage", "content": [{"type": "text", "text": "Testleri calistir"}]}}, "timestamp": "t1"},
        {"type": "response_item", "payload": {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": "gizli sistem"}]}, "timestamp": "t1"},
        {"type": "response_item", "payload": {"type": "custom_tool_call", "name": "exec", "input": "ls"}, "timestamp": "t2"},
        {"type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Calistirdim, hepsi gecti"}]}, "timestamp": "t3"},
    ]
    yol = d / f"rollout-2026-10-26T10-00-00-{kimlik}.jsonl"
    yol.write_text("\n".join(json.dumps(o) for o in [meta, *(satirlar or varsayilan)]), encoding="utf-8")
    return yol


def _oc_db_yaz(klasor, sid=OC_ID, guncel=None):
    db = sqlite3.connect(ao.opencode_db())
    db.execute("create table session_v2 (id text primary key, parent_id text, title text, directory text, time_updated integer, time_archived integer)")
    db.execute("create table session_message (id text primary key, session_id text, type text, seq integer, time_created integer, data text)")
    db.execute("create table account (id text, access_token text)")
    db.execute("insert into account values ('a','GIZLI-TOKEN')")
    db.execute("insert into session_v2 values (?,?,?,?,?,?)", (sid, None, "baslik", str(klasor).replace("\\", "/"), int((guncel or time.time()) * 1000), None))
    mesajlar = [
        ("user", 1, {"text": "\"Dosyalari listele\""}),
        ("assistant", 2, {"content": [{"type": "reasoning", "text": "dusunce"}, {"type": "tool", "name": "shell", "state": {"input": {"command": "dir"}}}, {"type": "text", "text": "Iste liste"}]}),
        ("idle", 3, {"outcome": "succeeded"}),
    ]
    for i, (t, seq, d) in enumerate(mesajlar):
        db.execute("insert into session_message values (?,?,?,?,?,?)", (f"m{i}", sid, t, seq, 1, json.dumps(d)))
    db.commit()
    db.close()


def test_codex_listele_ve_oku(tmp_path):
    proje = tmp_path / "proje"
    proje.mkdir()
    _codex_yaz(proje)
    _codex_yaz(tmp_path / "baska", "01a1690a-0000-7682-9f97-0484eda4db80")  # baska klasorun konusmasi gorunmez
    liste = ao.listele("codex", proje)
    assert [x["kimlik"] for x in liste] == [CODEX_ID] and liste[0]["baslik"] == "Testleri calistir" and "hepsi gecti" in liste[0]["son"] and liste[0]["canli"]
    k = ao.konusma("codex", proje, CODEX_ID)
    assert [o["tur"] for o in k["olaylar"]] == ["oturum-kullanici", "oturum-arac", "oturum-yanit"]  # developer/sistem mesaji sizmaz
    assert not any("gizli sistem" in json.dumps(o) for o in k["olaylar"])
    with pytest.raises(FileNotFoundError):
        ao.konusma("codex", tmp_path / "baska-klasor", CODEX_ID)
    with pytest.raises(ValueError):
        ao.konusma("codex", proje, "../x")


def test_opencode_listele_ve_oku_kimlik_tablosuna_dokunmaz(tmp_path):
    proje = tmp_path / "proje"
    proje.mkdir()
    _oc_db_yaz(proje)
    liste = ao.listele("opencode", proje)
    assert [x["kimlik"] for x in liste] == [OC_ID] and liste[0]["baslik"] == "Dosyalari listele" and liste[0]["son"] == "Iste liste" and liste[0]["canli"]
    k = ao.konusma("opencode", proje, OC_ID)
    assert [o["tur"] for o in k["olaylar"]] == ["oturum-kullanici", "oturum-arac", "oturum-yanit"]
    assert "GIZLI-TOKEN" not in json.dumps(k) and "dusunce" not in json.dumps(k)  # dusunce adimlari ve hesap tablosu okunmaz
    assert ao.listele("opencode", tmp_path / "baska") == []
    with pytest.raises(FileNotFoundError):
        ao.konusma("opencode", tmp_path / "baska", OC_ID)
    # salt okunur: yazma denemesi mumkun degil
    db = ao._db()
    with pytest.raises(sqlite3.OperationalError):
        db.execute("insert into account values ('x','y')")
    db.close()


def test_kaynak_yoksa_bos_doner(tmp_path):
    assert ao.listele("codex", tmp_path) == [] and ao.listele("opencode", tmp_path) == []


def test_uc_noktalar_kaynakla(api, monkeypatch):
    app, istek, proje = api
    _codex_yaz(proje.resolve())
    _oc_db_yaz(proje.resolve())
    for kaynak, kimlik in (("codex", CODEX_ID), ("opencode", OC_ID)):
        st, d = istek("GET", f"/api/claude-oturumlari?kaynak={kaynak}")
        assert st == 200 and d["kaynak"] == kaynak and d["oturumlar"][0]["kimlik"] == kimlik
        st, d = istek("GET", f"/api/claude-konusma?kaynak={kaynak}&id={kimlik}")
        assert st == 200 and d["olaylar"][0]["tur"] == "oturum-kullanici"
    assert istek("GET", "/api/claude-oturumlari?kaynak=zehir")[0] == 400
    girdiler = []
    monkeypatch.setattr(app, "terminal_ac", lambda *a, **k: {"id": "t7"})
    import base64
    monkeypatch.setattr(app, "terminal_girdi", lambda tid, b64: girdiler.append(base64.b64decode(b64).decode()) or {"tamam": True})
    monkeypatch.setattr("aktapokus_ai_studio.arayuz.codex_bul", lambda: [r"C:\c\codex.exe"])
    monkeypatch.setattr("aktapokus_ai_studio.arayuz.opencode_bul", lambda: r"C:\c\opencode.exe")
    assert istek("POST", "/api/claude-surdur", {"id": CODEX_ID, "kaynak": "codex"})[1] == {"terminal": "t7"}
    assert istek("POST", "/api/claude-surdur", {"id": OC_ID, "kaynak": "opencode"})[0] == 200
    assert girdiler == [f"& 'C:\\c\\codex.exe' 'resume' '{CODEX_ID}'\r", f"& 'C:\\c\\opencode.exe' --session {OC_ID}\r"]
    assert istek("POST", "/api/claude-surdur", {"id": "x'; calc; '", "kaynak": "codex"})[0] == 404 and len(girdiler) == 2


def test_uzaktan_kaynakli_uclar_kapali(uzak_sunucu):
    app, sv, yerel, proje = uzak_sunucu
    port, _ = ac(yerel)
    st, d = uzak_istek(port, "GET", "/api/claude-oturumlari?kaynak=codex", None)
    assert st == 403 and "uzaktan kapali" in d["hata"]


# ---------------- OpenCode talimat dosyasi ve kurulum ----------------
def test_opencode_haber_dosyasi_gorev_durumunu_yazar():
    haber.opencode_yaz()
    assert "yeni biten gorev yok" in haber.opencode_haber_yolu().read_text(encoding="utf-8")
    canli.olay("p1", "demo", "C:/demo", {"tur": "plan", "gorev": "Sayfa ekle"})
    canli.olay("p1", "demo", "C:/demo", {"tur": "basladi"})
    haber.opencode_yaz()
    t = haber.opencode_haber_yolu().read_text(encoding="utf-8")
    assert "CALISIYOR" in t and "Sayfa ekle" in t and "yalnizca bilgi" in t


def test_kur_claude_codex_opencode_mevcut_ayarlari_korur(tmp_path, monkeypatch):
    claude, codex, oc = tmp_path / "claude.json", tmp_path / "hooks.json", tmp_path / "opencode.json"
    claude.write_text(json.dumps({"permissions": {"allow": ["x"]}, "hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": "baska"}]}]}}), encoding="utf-8")
    oc.write_text(json.dumps({"model": "m", "instructions": ["AGENTS.md"]}), encoding="utf-8")
    monkeypatch.setenv(haber.CLAUDE_AYAR_ORTAMI, str(claude))
    monkeypatch.setenv(haber.CODEX_KANCA_ORTAMI, str(codex))
    monkeypatch.setenv(haber.OPENCODE_AYAR_ORTAMI, str(oc))
    ilk = haber.kur("hepsi")
    assert len(ilk) == 3 and "eklendi" in ilk[0] and "eklendi" in ilk[1] and "/hooks" in ilk[1] and "eklendi" in ilk[2]
    c = json.loads(claude.read_text(encoding="utf-8"))
    assert c["permissions"] == {"allow": ["x"]} and len(c["hooks"]["UserPromptSubmit"]) == 2 and "haber_kancasi.py" in c["hooks"]["UserPromptSubmit"][1]["hooks"][0]["command"]
    assert (tmp_path / "claude.json.aktapokus-yedek").is_file()
    o = json.loads(oc.read_text(encoding="utf-8"))
    assert o["model"] == "m" and o["instructions"][0] == "AGENTS.md" and o["instructions"][1].endswith("haber.md")
    assert "haber_kancasi.py" in json.loads(codex.read_text(encoding="utf-8"))["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
    ikinci = haber.kur("hepsi")  # tekrar: cogaltmaz
    assert all("zaten" in s for s in ikinci)
    assert len(json.loads(claude.read_text(encoding="utf-8"))["hooks"]["UserPromptSubmit"]) == 2


def test_arayuz_cok_aracli_bolumler_baglidir():
    html = (Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "web" / "index.html").read_text(encoding="utf-8")
    for parca in ("ARAC_KAYNAKLARI", "aracBolumu", "oturum-kullanici", "oturum-yanit", "oturum-arac", "&kaynak="):
        assert parca in html, parca
