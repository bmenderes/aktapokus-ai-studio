"""Codex ve OpenCode konusmalari (yalniz OKUR): bir projenin klasorunde yurutulen konusmalari listeler, canli olani isaretler ve Aktapokus akisinda
gosterilecek olaylara (`oturum-kullanici` / `oturum-yanit` / `oturum-arac`) cevirir. Claude Code icin `claude_oturumlari.py`.

- Codex: `~/.codex/sessions/YYYY/AA/GG/rollout-*.jsonl` (ilk satir `session_meta` + cwd). Dosyalar buyuk olabilir: basindan/sonundan sinirli parca okunur.
- OpenCode: `~/.local/share/opencode/opencode.db` (SQLite) SALT OKUNUR acilir; YALNIZ session_v2 ve session_message tablolarinin gerekli sutunlari okunur.
  Hesap/kimlik bilgisi tablolarina (account, credential, ...) HIC dokunulmaz.
Hicbir sey yazilmaz. Biçim bu araçların sürümüne göre değişebilir: okunamayan kayıt atlanır, hata uygulamayı etkilemez."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from pathlib import Path

CODEX_ORTAMI = "AKTAPOKUS_CODEX_OTURUMLARI"
OPENCODE_ORTAMI = "AKTAPOKUS_OPENCODE_DB"
KAYNAKLAR = ("claude", "codex", "opencode")
CODEX_KIMLIK = re.compile(r"[0-9a-fA-F-]{36}")
OPENCODE_KIMLIK = re.compile(r"ses_[A-Za-z0-9]{10,40}")
CANLI_SN = 25
BAS_BAYT = 512 * 1024
SON_BAYT = 3 * 1024 * 1024
AZAMI_OLAY = 400
AZAMI_METIN = 6000
AZAMI_TARAMA = 400  # Codex: en yeni bu kadar dosyaya bakilir
_codex_onbellek: dict[tuple[str, float, int], dict] = {}


def _kisa(m: object, n: int) -> str:
    return " ".join(str(m or "").split())[:n]


def _ayni_klasor(a: object, b: object) -> bool:
    def norm(x: object) -> str:
        try:
            return os.path.normcase(os.path.realpath(str(x)))
        except (OSError, ValueError):
            return str(x).lower()

    return bool(a) and bool(b) and norm(a) == norm(b)


def _girdi_ozeti(girdi: object) -> dict:
    if isinstance(girdi, str):
        try:
            girdi = json.loads(girdi)
        except ValueError:
            return {"komut": girdi[:200]}
    if not isinstance(girdi, dict):
        return {}
    return {str(k): (v[:200] if isinstance(v, str) else v) for k, v in list(girdi.items())[:8] if isinstance(v, (str, int, float, bool))}


# ---------------- Codex ----------------
def codex_kok() -> Path:
    ortam = os.environ.get(CODEX_ORTAMI)
    return Path(ortam) if ortam else Path.home() / ".codex" / "sessions"


def _jsonl(yol: Path, bas: bool, bayt: int) -> tuple[list[dict], bool]:
    try:
        boyut = yol.stat().st_size
        with open(yol, "rb") as f:
            if not bas and boyut > bayt:
                f.seek(boyut - bayt)
            ham = f.read(bayt)
    except OSError:
        return [], False
    parcalar = ham.decode("utf-8", errors="ignore").split("\n")
    kesik = boyut > bayt
    if kesik:
        parcalar = parcalar[:-1] if bas else parcalar[1:]
    sonuc = []
    for s in parcalar:
        s = s.strip()
        if s.startswith("{"):
            try:
                o = json.loads(s)
            except ValueError:
                continue
            if isinstance(o, dict):
                sonuc.append(o)
    return sonuc, kesik


def _codex_metin(icerik: object, tipler: tuple[str, ...]) -> str:
    if isinstance(icerik, str):
        return icerik
    return "\n".join(p["text"] for p in icerik if isinstance(p, dict) and p.get("type") in tipler and isinstance(p.get("text"), str)) if isinstance(icerik, list) else ""


def _codex_kullanici(o: dict) -> str | None:
    p = o.get("payload") if isinstance(o.get("payload"), dict) else {}
    if o.get("type") == "event_msg" and p.get("type") == "item_completed":
        it = p.get("item") if isinstance(p.get("item"), dict) else {}
        if it.get("type") == "UserMessage":
            return _codex_metin(it.get("content"), ("text", "input_text")).strip() or None
    return None


def _codex_yanit(o: dict) -> str | None:
    p = o.get("payload") if isinstance(o.get("payload"), dict) else {}
    if o.get("type") == "response_item" and p.get("type") == "message" and p.get("role") == "assistant":
        return _codex_metin(p.get("content"), ("output_text", "text")).strip() or None
    return None


def _codex_dosyalari() -> list[tuple[float, int, Path]]:
    kok = codex_kok()
    sonuc = []
    try:
        for yol in kok.glob("*/*/*/rollout-*.jsonl"):
            try:
                st = yol.stat()
            except OSError:
                continue
            sonuc.append((st.st_mtime, st.st_size, yol))
    except OSError:
        return []
    sonuc.sort(reverse=True)
    return sonuc[:AZAMI_TARAMA]


def _codex_ozet(yol: Path) -> dict:
    bas, _ = _jsonl(yol, True, BAS_BAYT)
    meta = next((o.get("payload") for o in bas if o.get("type") == "session_meta" and isinstance(o.get("payload"), dict)), {})
    ilk = next((m for m in (_codex_kullanici(o) for o in bas) if m and not m.lstrip().startswith("<")), "")
    sonlar, _ = _jsonl(yol, False, 256 * 1024)
    son = next((m for m in (_codex_yanit(o) for o in reversed(sonlar)) if m), "")
    return {"kimlik": str(meta.get("id") or ""), "cwd": str(meta.get("cwd") or ""), "baslik": _kisa(ilk, 140), "son": _kisa(son, 200)}


def _codex_bul(klasor: str | Path, kimlik: str | None = None):
    """[(mtime, boyut, yol, ozet)] bu klasore ait konusmalar (en yeni once); kimlik verilirse yalniz o."""
    sonuc = []
    for mtime, boyut, yol in _codex_dosyalari():
        if kimlik and kimlik not in yol.name:
            continue
        anahtar = (str(yol), mtime, boyut)
        if anahtar not in _codex_onbellek:
            if len(_codex_onbellek) > 500:
                _codex_onbellek.clear()
            _codex_onbellek[anahtar] = _codex_ozet(yol)
        o = _codex_onbellek[anahtar]
        if o["kimlik"] and _ayni_klasor(o["cwd"], klasor):
            sonuc.append((mtime, boyut, yol, o))
    return sonuc


def codex_listele(klasor: str | Path, adet: int = 5) -> list[dict]:
    simdi = time.time()
    return [{"kimlik": o["kimlik"], "zaman": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(m)), "boyut": b, "canli": simdi - m < CANLI_SN, "baslik": o["baslik"], "son": o["son"]}
            for m, b, _, o in _codex_bul(klasor)[: max(1, min(int(adet), 30))]]


def codex_konusma(klasor: str | Path, kimlik: object) -> dict:
    if not isinstance(kimlik, str) or not CODEX_KIMLIK.fullmatch(kimlik):
        raise ValueError("Gecersiz konusma kimligi")
    bulunan = _codex_bul(klasor, kimlik)
    if not bulunan:
        raise FileNotFoundError("Konusma bulunamadi")
    mtime, _, yol, ozet = bulunan[0]
    satirlar, kesik = _jsonl(yol, False, SON_BAYT)
    olaylar: list[dict] = []
    for o in satirlar:
        zaman = o.get("timestamp")
        k = _codex_kullanici(o)
        if k and not k.lstrip().startswith("<"):
            olaylar.append({"tur": "oturum-kullanici", "metin": k[:AZAMI_METIN], "zaman": zaman})
            continue
        y = _codex_yanit(o)
        if y:
            olaylar.append({"tur": "oturum-yanit", "metin": y[:AZAMI_METIN], "zaman": zaman})
            continue
        p = o.get("payload") if isinstance(o.get("payload"), dict) else {}
        if o.get("type") == "response_item" and p.get("type") in ("custom_tool_call", "function_call", "local_shell_call"):
            olaylar.append({"tur": "oturum-arac", "ad": str(p.get("name") or p.get("type")), "girdi": _girdi_ozeti(p.get("input") if "input" in p else p.get("arguments")), "zaman": zaman})
    return {"kimlik": kimlik, "olaylar": olaylar[-AZAMI_OLAY:], "kesildi": kesik or len(olaylar) > AZAMI_OLAY, "canli": time.time() - mtime < CANLI_SN, "baslik": ozet["baslik"], "son": ozet["son"]}


# ---------------- OpenCode ----------------
def opencode_db() -> Path:
    ortam = os.environ.get(OPENCODE_ORTAMI)
    return Path(ortam) if ortam else Path.home() / ".local" / "share" / "opencode" / "opencode.db"


def _db() -> sqlite3.Connection | None:
    yol = opencode_db()
    if not yol.is_file():
        return None
    try:
        return sqlite3.connect("file:" + yol.as_posix() + "?mode=ro", uri=True, timeout=2)
    except sqlite3.Error:
        return None


def _json(s: object) -> dict:
    try:
        v = json.loads(s) if isinstance(s, str) else {}
    except ValueError:
        return {}
    return v if isinstance(v, dict) else {}


def _oc_metin(d: dict) -> str:
    t = d.get("text")
    if isinstance(t, str) and len(t) >= 2 and t[0] == '"' and t[-1] == '"':  # CLI mesaji tirnakli yazabilir
        try:
            t = json.loads(t)
        except ValueError:
            pass
    return t.strip() if isinstance(t, str) else ""


def _oc_son_yanit(db: sqlite3.Connection, sid: str) -> str:
    for (veri,) in db.execute("select data from session_message where session_id=? and type='assistant' order by seq desc limit 6", (sid,)):
        for p in reversed(_json(veri).get("content") or []):
            if isinstance(p, dict) and p.get("type") == "text" and isinstance(p.get("text"), str) and p["text"].strip():
                return p["text"].strip()
    return ""


def opencode_listele(klasor: str | Path, adet: int = 5) -> list[dict]:
    db = _db()
    if db is None:
        return []
    try:
        simdi = time.time()
        sonuc = []
        for sid, baslik, dizin, guncel in db.execute("select id, title, directory, time_updated from session_v2 where parent_id is null and time_archived is null order by time_updated desc limit 400"):
            if not _ayni_klasor(dizin, klasor) or not isinstance(sid, str) or not OPENCODE_KIMLIK.fullmatch(sid):
                continue
            ilk = db.execute("select data from session_message where session_id=? and type='user' order by seq limit 1", (sid,)).fetchone()
            sonuc.append({"kimlik": sid, "zaman": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime((guncel or 0) / 1000)), "boyut": 0, "canli": simdi - (guncel or 0) / 1000 < CANLI_SN,
                          "baslik": _kisa(_oc_metin(_json(ilk[0])) if ilk else baslik, 140) or _kisa(baslik, 140), "son": _kisa(_oc_son_yanit(db, sid), 200)})
            if len(sonuc) >= max(1, min(int(adet), 30)):
                break
        return sonuc
    except sqlite3.Error:
        return []
    finally:
        db.close()


def opencode_konusma(klasor: str | Path, kimlik: object) -> dict:
    if not isinstance(kimlik, str) or not OPENCODE_KIMLIK.fullmatch(kimlik):
        raise ValueError("Gecersiz konusma kimligi")
    db = _db()
    if db is None:
        raise FileNotFoundError("Konusma bulunamadi")
    try:
        s = db.execute("select directory, title, time_updated from session_v2 where id=?", (kimlik,)).fetchone()
        if not s or not _ayni_klasor(s[0], klasor):
            raise FileNotFoundError("Konusma bulunamadi")
        satirlar = list(reversed(db.execute("select type, data, time_created from session_message where session_id=? and type in ('user','assistant') order by seq desc limit 800", (kimlik,)).fetchall()))
        olaylar: list[dict] = []
        for tur, veri, zaman in satirlar:
            d = _json(veri)
            if tur == "user":
                m = _oc_metin(d)
                if m:
                    olaylar.append({"tur": "oturum-kullanici", "metin": m[:AZAMI_METIN], "zaman": zaman})
                continue
            for p in d.get("content") or []:
                if not isinstance(p, dict):
                    continue
                if p.get("type") == "text" and isinstance(p.get("text"), str) and p["text"].strip():
                    olaylar.append({"tur": "oturum-yanit", "metin": p["text"].strip()[:AZAMI_METIN], "zaman": zaman})
                elif p.get("type") == "tool":
                    st = p.get("state") if isinstance(p.get("state"), dict) else {}
                    olaylar.append({"tur": "oturum-arac", "ad": str(p.get("name") or ""), "girdi": _girdi_ozeti(st.get("input")), "zaman": zaman})
        ilk = next((o["metin"] for o in olaylar if o["tur"] == "oturum-kullanici"), s[1] or "")
        son = next((o["metin"] for o in reversed(olaylar) if o["tur"] == "oturum-yanit"), "")
        return {"kimlik": kimlik, "olaylar": olaylar[-AZAMI_OLAY:], "kesildi": len(olaylar) > AZAMI_OLAY or len(satirlar) >= 800, "canli": time.time() - (s[2] or 0) / 1000 < CANLI_SN,
                "baslik": _kisa(ilk, 140), "son": _kisa(son, 200)}
    except sqlite3.Error:
        raise FileNotFoundError("Konusma okunamadi") from None
    finally:
        db.close()


# ---------------- ortak ----------------
def listele(kaynak: str, klasor: str | Path, adet: int = 5) -> list[dict]:
    if kaynak == "codex":
        return codex_listele(klasor, adet)
    if kaynak == "opencode":
        return opencode_listele(klasor, adet)
    raise ValueError("Bilinmeyen kaynak")


def konusma(kaynak: str, klasor: str | Path, kimlik: object) -> dict:
    if kaynak == "codex":
        return codex_konusma(klasor, kimlik)
    if kaynak == "opencode":
        return opencode_konusma(klasor, kimlik)
    raise ValueError("Bilinmeyen kaynak")


def var_mi(kaynak: str, klasor: str | Path, kimlik: object) -> bool:
    try:
        konusma(kaynak, klasor, kimlik)
        return True
    except (ValueError, FileNotFoundError):
        return False
