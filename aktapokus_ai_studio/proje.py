"""Proje hazirligi: git deposu, yerel exclude, koruyucu (izin ayari) ve rol ayari. CLI ve arayuz ortak kullanir."""

from __future__ import annotations

import json
from pathlib import Path

from . import baglam, guard, motorlar, snapshot
from .config import AYAR_KLASORU, VARSAYILAN_AYAR, ayar_yolu
from .klasor import guvenli_klasor


class GitGerekli(Exception):
    """ESKI: klasor git deposu degilse artik GOLGE DEPO kullanilir (snapshot.golge_*); hazirla() bunu firlatmaz. Uyumluluk icin durur."""


def hazirla(klasor: str | Path, git_baslat: bool = False) -> dict:
    """Idempotent. {'klasor': Path, 'git': 'mevcut'|'baslatildi', 'koruyucu': ..., 'ayar': 'olusturuldu'|'mevcut'}.
    Hatalar: KlasorHatasi, GitGerekli, snapshot.GitHatasi, guard.KoruyucuHatasi."""
    klasor = guvenli_klasor(klasor)
    git = "mevcut"
    if not snapshot.hazir_mi(klasor):
        if git_baslat:  # kullanici AYRICA gercek bir git deposu istedi
            snapshot.repo_baslat(klasor)
            git = "baslatildi"
        else:  # git ISTENMEZ: geri alma klasorun disindaki golge depoda tutulur
            yeni = snapshot.golge_baslat(klasor)
            try:
                snapshot.golge_boyut_denetle(klasor)
            except snapshot.GitHatasi:
                if yeni:
                    snapshot.golge_sil(klasor)
                raise
            git = "golge"
    elif snapshot.golge_mi(klasor):
        snapshot.golge_boyut_denetle(klasor)
        git = "golge"
    hariclik = snapshot.git_dizini(klasor) / "info" / "exclude"
    hariclik.parent.mkdir(parents=True, exist_ok=True)
    mevcut = hariclik.read_text(encoding="utf-8") if hariclik.exists() else ""
    eklenecek = [s for s in (f"{AYAR_KLASORU}/", ".opencode/opencode.json") if s not in mevcut.splitlines()]
    if eklenecek:
        hariclik.write_text(mevcut + ("" if mevcut.endswith("\n") or not mevcut else "\n") + "\n".join(eklenecek) + "\n", encoding="utf-8")
    koruyucu = guard.kur(klasor)
    baglam_kaynak = baglam.kaynak_olustur(klasor)
    yol = ayar_yolu(klasor)
    ayar = "mevcut"
    if not yol.exists():
        yol.parent.mkdir(parents=True, exist_ok=True)
        # Yeni projenin varsayilan rolleri KURULU motora gore (OpenCode yoksa ama Claude Code/Codex varsa onlarla); mevcut ayar asla ezilmez
        yol.write_text(json.dumps(motorlar.ayar_uret(motorlar.tercih()), ensure_ascii=False, indent=2), encoding="utf-8")
        ayar = "olusturuldu"
    return {"klasor": klasor, "git": git, "koruyucu": koruyucu, "ayar": ayar, "baglam": baglam_kaynak}
