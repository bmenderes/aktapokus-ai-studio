"""Calisma klasoru guvenligi: gelistirme yalnizca bilincli secilmis bir proje klasorunde yapilir."""

from __future__ import annotations

import os
from pathlib import Path


class KlasorHatasi(Exception):
    pass


def _sistem_klasorleri() -> list[Path]:
    adaylar = []
    for ad in ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramData"):
        deger = os.environ.get(ad)
        if deger:
            adaylar.append(Path(deger).resolve())
    for sabit in ("/etc", "/usr", "/bin", "/sbin", "/var", "/boot", "/System"):
        adaylar.append(Path(sabit))
    return adaylar


def guvenli_klasor(klasor: str | Path) -> Path:
    """Klasoru cozer ve ana dizin, surucu koku, sistem klasoru gibi yerleri reddeder."""
    yol = Path(klasor).expanduser().resolve()
    if not yol.is_dir():
        raise KlasorHatasi(f"Klasor bulunamadi: {yol}")
    ev = Path.home().resolve()
    if yol == ev or yol in ev.parents:
        raise KlasorHatasi(f"Ana dizin veya ustu proje klasoru olamaz: {yol}. Bir proje klasoru secin.")
    if yol == Path(yol.anchor):
        raise KlasorHatasi(f"Surucu koku proje klasoru olamaz: {yol}")
    for sistem in _sistem_klasorleri():
        if yol == sistem or sistem in yol.parents:
            raise KlasorHatasi(f"Sistem klasoru proje klasoru olamaz: {yol}")
    return yol
