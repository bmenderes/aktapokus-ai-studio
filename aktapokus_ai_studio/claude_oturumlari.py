"""Claude Code konusmalari (yalniz OKUR): bir projenin klasorunde yurutulen Claude Code konusmalarini (Aktapokus gorevleri VE kullanicinin
kendi etkilesimli konusmalari) listeler, canli olani isaretler, icerigini Aktapokus akisinda gosterilecek olaylara cevirir.

Claude Code konusmalari `~/.claude/projects/<klasor-kodu>/<kimlik>.jsonl` dosyalarindadir (klasor-kodu: yolun harf/rakam disindaki her karakteri '-').
Dosyalar COK buyuk olabilir (yuzlerce MB): yalniz basindan (baslik) ve sonundan (son yanit, icerik) sinirli parca okunur; hicbir sey yazilmaz."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

KOK_ORTAMI = "AKTAPOKUS_CLAUDE_PROJELER"
KIMLIK_DESENI = re.compile(r"[0-9a-fA-F-]{36}")
CANLI_SN = 25  # dosya son 25 sn icinde yazildiysa konusma canlidir
BAS_BAYT = 256 * 1024
SON_BAYT = 3 * 1024 * 1024
AZAMI_OLAY = 400
AZAMI_METIN = 6000
_onbellek: dict[tuple[str, float, int], dict] = {}


def kok() -> Path:
    ortam = os.environ.get(KOK_ORTAMI)
    return Path(ortam) if ortam else Path.home() / ".claude" / "projects"


def klasor_kodu(klasor: str | Path) -> str:
    """Claude Code'un proje klasoru adi: yolun harf/rakam disindaki her karakteri '-' olur (C:\\a\\b -> C--a-b)."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(klasor))


def _proje_klasoru(klasor: str | Path) -> Path | None:
    kod = klasor_kodu(klasor).lower()
    try:
        for d in kok().iterdir():  # buyuk/kucuk harf ve 8.3 farklarina dayanikli eslesme
            if d.is_dir() and d.name.lower() == kod:
                return d
    except OSError:
        return None
    return None


def _metin(mesaj: object) -> str:
    """Kullanici/asistan mesajinin duz metni (arac sonuclari ve dusunceler dahil degil)."""
    icerik = mesaj.get("content") if isinstance(mesaj, dict) else None
    if isinstance(icerik, str):
        return icerik
    parcalar = []
    for p in icerik if isinstance(icerik, list) else []:
        if isinstance(p, dict) and p.get("type") == "text" and isinstance(p.get("text"), str):
            parcalar.append(p["text"])
    return "\n".join(parcalar)


def _gercek_kullanici_metni(metin: str) -> bool:
    t = metin.lstrip()
    return bool(t) and not t.startswith("<") and not t.startswith("Caveat:")  # sistem hatirlaticilari/komut etiketleri kullanici mesaji degildir


def _satirlar(yol: Path, bas: bool, bayt: int) -> tuple[list[dict], bool]:
    """Dosyanin basindan ya da sonundan en cok `bayt` kadarini JSON satirlari olarak okur. (satirlar, dosya_daha_buyuk_mu)"""
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
        parcalar = parcalar[:-1] if bas else parcalar[1:]  # kesilen yarim satir atilir
    sonuc = []
    for s in parcalar:
        s = s.strip()
        if not s.startswith("{"):
            continue
        try:
            o = json.loads(s)
        except ValueError:
            continue
        if isinstance(o, dict):
            sonuc.append(o)
    return sonuc, kesik


def _ozet(yol: Path) -> dict:
    ilk = ""
    bas, _ = _satirlar(yol, True, BAS_BAYT)
    for o in bas:
        if o.get("type") == "user" and not o.get("isMeta"):
            m = _metin(o.get("message"))
            if _gercek_kullanici_metni(m):
                ilk = m.strip()
                break
    son = ""
    sonlar, _ = _satirlar(yol, False, 256 * 1024)
    for o in reversed(sonlar):
        if o.get("type") == "assistant":
            m = _metin(o.get("message")).strip()
            if m:
                son = m
                break
    return {"baslik": " ".join(ilk.split())[:140], "son": " ".join(son.split())[:200]}


def listele(klasor: str | Path, adet: int = 5) -> list[dict]:
    """Projenin Claude Code konusmalari, en yeni once. Her biri: kimlik, baslik, son yanit ozeti, zaman, canli mi."""
    d = _proje_klasoru(klasor)
    if d is None:
        return []
    dosyalar = []
    try:
        for e in os.scandir(d):
            if e.name.endswith(".jsonl") and KIMLIK_DESENI.fullmatch(e.name[:-6]) and e.is_file():
                st = e.stat()
                dosyalar.append((st.st_mtime, st.st_size, e.path, e.name[:-6]))
    except OSError:
        return []
    dosyalar.sort(reverse=True)
    simdi = time.time()
    sonuc = []
    for mtime, boyut, yol, kimlik in dosyalar[: max(1, min(int(adet), 30))]:
        anahtar = (yol, mtime, boyut)
        if anahtar not in _onbellek:
            if len(_onbellek) > 300:
                _onbellek.clear()
            _onbellek[anahtar] = _ozet(Path(yol))
        sonuc.append({"kimlik": kimlik, "zaman": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime)), "boyut": boyut, "canli": simdi - mtime < CANLI_SN, **_onbellek[anahtar]})
    return sonuc


def _girdi_ozeti(girdi: object) -> dict:
    if not isinstance(girdi, dict):
        return {}
    return {str(k): (v[:200] if isinstance(v, str) else v) for k, v in list(girdi.items())[:8] if isinstance(v, (str, int, float, bool))}


def konusma(klasor: str | Path, kimlik: object) -> dict:
    """Konusmanin SON bolumu, Aktapokus akisinda cizilecek olaylar olarak: claude-kullanici / claude-yanit / claude-arac."""
    if not isinstance(kimlik, str) or not KIMLIK_DESENI.fullmatch(kimlik):
        raise ValueError("Gecersiz konusma kimligi")
    d = _proje_klasoru(klasor)
    yol = (d / f"{kimlik}.jsonl") if d else None
    if yol is None or not yol.is_file() or yol.parent != d:
        raise FileNotFoundError("Konusma bulunamadi")
    satirlar, kesik = _satirlar(yol, False, SON_BAYT)
    olaylar: list[dict] = []
    for o in satirlar:
        tur, zaman = o.get("type"), o.get("timestamp")
        if tur == "user" and not o.get("isMeta"):
            m = _metin(o.get("message"))
            if _gercek_kullanici_metni(m):
                olaylar.append({"tur": "claude-kullanici", "metin": m.strip()[:AZAMI_METIN], "zaman": zaman})
        elif tur == "assistant":
            icerik = (o.get("message") or {}).get("content") if isinstance(o.get("message"), dict) else None
            for p in icerik if isinstance(icerik, list) else []:
                if not isinstance(p, dict):
                    continue
                if p.get("type") == "text" and isinstance(p.get("text"), str) and p["text"].strip():
                    olaylar.append({"tur": "claude-yanit", "metin": p["text"].strip()[:AZAMI_METIN], "zaman": zaman})
                elif p.get("type") == "tool_use":
                    olaylar.append({"tur": "claude-arac", "ad": p.get("name") if isinstance(p.get("name"), str) else "", "girdi": _girdi_ozeti(p.get("input")), "zaman": zaman})
    try:
        st = yol.stat()
        canli = time.time() - st.st_mtime < CANLI_SN
    except OSError:
        canli = False
    return {"kimlik": kimlik, "olaylar": olaylar[-AZAMI_OLAY:], "kesildi": kesik or len(olaylar) > AZAMI_OLAY, "canli": canli, **_ozet(yol)}


def var_mi(klasor: str | Path, kimlik: object) -> bool:
    if not isinstance(kimlik, str) or not KIMLIK_DESENI.fullmatch(kimlik):
        return False
    d = _proje_klasoru(klasor)
    return bool(d and (d / f"{kimlik}.jsonl").is_file())
