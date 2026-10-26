"""Hesaplar: bu bilgisayarda hangi hizmette KIMIN adina giris yapildigi. Yalniz OKUR: sifre/token/anahtar ASLA okunmaz ya da gosterilmez.

Aktapokus'un kendi kullanici hesabi yoktur (yerel calisir, giris gerekmez); asil kimlikler CLI'larin kendi oturumlaridir (GitHub/gh, Claude Code,
Codex). Burasi bunlari tek yerde gosterir ki 'misafir miyim, kim olarak giris yaptim' sorusu belirsiz kalmasin."""

from __future__ import annotations

import getpass
import json
import platform
import subprocess
from concurrent.futures import ThreadPoolExecutor

from . import runners


def yerel() -> dict:
    try:
        kullanici = getpass.getuser()
    except Exception:
        kullanici = ""
    return {"kullanici": kullanici, "bilgisayar": platform.node(), "giris": False}  # Aktapokus'un kendi hesabi yok


def _calistir(argv: list[str], zaman_asimi: int = 25) -> tuple[int, str]:
    try:
        s = subprocess.run(argv, capture_output=True, stdin=subprocess.DEVNULL, timeout=zaman_asimi)
    except (OSError, subprocess.TimeoutExpired):
        return -1, ""
    return s.returncode, (s.stdout + b"\n" + s.stderr).decode("utf-8", errors="replace")


def claude() -> dict:
    """`claude auth status`: yalniz oturum durumu, e-posta ve abonelik tipi (orgId/token gibi alanlar alinmaz)."""
    cli = runners.claude_bul()
    if not cli:
        return {"kurulu": False, "giris": False}
    kod, metin = _calistir([cli, "auth", "status"])
    i, j = metin.find("{"), metin.rfind("}")
    try:
        d = json.loads(metin[i:j + 1]) if i >= 0 and j > i else {}
    except ValueError:
        d = {}
    if not isinstance(d, dict) or "loggedIn" not in d:
        return {"kurulu": True, "giris": False, "hata": "Oturum durumu okunamadi"}
    return {
        "kurulu": True, "giris": bool(d.get("loggedIn")), "yontem": d.get("authMethod") if isinstance(d.get("authMethod"), str) else None,
        "eposta": d.get("email") if isinstance(d.get("email"), str) else None, "abonelik": d.get("subscriptionType") if isinstance(d.get("subscriptionType"), str) else None,
    }


def codex() -> dict:
    """`codex login status`: 'Logged in using ChatGPT' gibi tek satir."""
    onek = runners.codex_bul()
    if not onek:
        return {"kurulu": False, "giris": False}
    kod, metin = _calistir([*onek, "login", "status"])
    satirlar = [s.strip() for s in metin.splitlines() if s.strip()]
    ilk = satirlar[0][:120] if satirlar else ""
    giris = kod == 0 and "logged in" in ilk.lower() and "not logged in" not in ilk.lower()
    return {"kurulu": True, "giris": giris, "detay": ilk or None}


def hepsi(github_durum, telegram_durum, uzak_acik: bool) -> dict:
    """Yavas olan (alt surec calistiran) sorgular paralel yurur."""
    with ThreadPoolExecutor(max_workers=3) as havuz:
        c, x, g = havuz.submit(claude), havuz.submit(codex), havuz.submit(github_durum)
        sonuc = {"yerel": yerel(), "claude": c.result(), "codex": x.result(), "github": g.result()}
    try:
        t = telegram_durum() or {}
        sonuc["telegram"] = {"calisiyor": bool(t.get("calisiyor")), "bot": t.get("bot"), "eslesmis": int(t.get("eslesmis") or 0)}
    except Exception:
        sonuc["telegram"] = {"calisiyor": False, "bot": None, "eslesmis": 0}
    sonuc["uzak"] = {"acik": bool(uzak_acik)}
    return sonuc
