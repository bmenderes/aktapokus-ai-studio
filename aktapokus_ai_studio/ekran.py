"""Onizleme ekran goruntusu: Chromium tabanli tarayiciyi basiz (headless) calistirip yerel bir adresin PNG'sini alir.

Edge/Chrome baslaticisi hemen doner, dosya ~1 sn sonra belirir; bu yuzden dosya aranir ve boyutu sabitlenene kadar beklenir.
Yalniz yerel (127.0.0.1/localhost) adresler alinir; gecici profil klasoru her seferinde silinir."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

YEREL_ADRES = re.compile(r"https?://(127\.0\.0\.1|localhost)(:\d{1,5})?(/[^\s]*)?")
AZAMI_BOYUT = 12000
PNG_IMZA = b"\x89PNG\r\n\x1a\n"


class EkranHatasi(Exception):
    pass


def yerel_mi(url: object) -> bool:
    return isinstance(url, str) and len(url) <= 2000 and YEREL_ADRES.fullmatch(url) is not None


def goruntu_al(url: str, genislik: int, yukseklik: int, tarayici: str | None, zaman_asimi_sn: float = 25.0) -> bytes:
    if not yerel_mi(url):
        raise EkranHatasi("Yalnizca yerel (127.0.0.1 / localhost) adreslerin ekran goruntusu alinir")
    if not tarayici:
        raise EkranHatasi("Chromium tabanli tarayici (Edge/Chrome) bulunamadi")
    genislik, yukseklik = max(200, min(int(genislik), AZAMI_BOYUT)), max(200, min(int(yukseklik), AZAMI_BOYUT))
    gecici = Path(tempfile.mkdtemp(prefix="aktp_ekran_"))
    png = gecici / "ekran.png"
    surec = None
    try:
        surec = subprocess.Popen(
            [tarayici, "--headless=new", "--disable-gpu", "--no-first-run", "--hide-scrollbars", "--default-background-color=ffffffff",
             "--virtual-time-budget=3000", f"--user-data-dir={gecici / 'profil'}", f"--window-size={genislik},{yukseklik}", f"--screenshot={png}", url],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        bitis, son_boyut, kararli = time.monotonic() + zaman_asimi_sn, -1, 0
        while time.monotonic() < bitis:
            time.sleep(0.25)
            boyut = png.stat().st_size if png.exists() else 0
            kararli = kararli + 1 if boyut and boyut == son_boyut else 0
            son_boyut = boyut
            if kararli >= 2:
                veri = png.read_bytes()
                if veri.startswith(PNG_IMZA):
                    return veri
        raise EkranHatasi("Ekran goruntusu zamaninda alinamadi")
    finally:
        if surec is not None and surec.poll() is None:
            try:
                surec.kill()
            except OSError:
                pass
        shutil.rmtree(gecici, ignore_errors=True)
