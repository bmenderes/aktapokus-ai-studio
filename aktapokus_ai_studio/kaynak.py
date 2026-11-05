"""Bilgisayarin TOPLAM islemci (CPU) ve ekran karti (GPU) kullanimi: hangi Windows kullanicisinin yukledigi fark etmez, durum cubugunda gosterilir.
Boylece ayni bilgisayari paylasan baska biri agir is calistiriyorsa (SolidWorks, yerel model...) kullanici bunu gorur.

Gizlilik: yalniz iki yuzde (ve GPU bellek orani) okunur; surec adi, kullanici adi, icerik toplanmaz/gosterilmez. Ek paket yok: CPU icin kernel32.GetSystemTimes,
GPU icin nvidia-smi (varsa), yoksa Windows sayaci (typeperf). Olcum yalnizca biri istedikten sonra ~30 sn boyunca arka planda surer."""

from __future__ import annotations

import csv
import io
import os
import shutil
import subprocess
import threading
import time

ARALIK_SN = 2.0
AKTIF_SN = 30.0  # son istekten bu yana bu kadar sure olcum surer; sonra durur (bosuna islemci yemez)
_GIZLE = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def cpu_yuzde(onceki: tuple[int, int] | None, simdi: tuple[int, int]) -> float | None:
    """(bosta, toplam) sayac cifti -> iki olcum arasindaki CPU yuzdesi."""
    if onceki is None:
        return None
    bosta = simdi[0] - onceki[0]
    toplam = simdi[1] - onceki[1]
    if toplam <= 0:
        return None
    return round(max(0.0, min(100.0, 100.0 * (1.0 - bosta / toplam))), 1)


def _sistem_zamanlari() -> tuple[int, int] | None:
    """Windows: (bosta, toplam) 100 ns sayaclari. Kernel zamani bosta suresini de icerir."""
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes

    bosta, cekirdek, kullanici = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
    if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(bosta), ctypes.byref(cekirdek), ctypes.byref(kullanici)):
        return None

    def sayi(f) -> int:
        return (f.dwHighDateTime << 32) | f.dwLowDateTime

    return sayi(bosta), sayi(cekirdek) + sayi(kullanici)


def nvidia_ayristir(cikti: str) -> tuple[float, float | None] | None:
    """`nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits` -> (en yuksek GPU %, toplam bellek %)."""
    kullanim, kullanilan, toplam = [], 0.0, 0.0
    for satir in cikti.splitlines():
        parca = [p.strip() for p in satir.split(",")]
        if len(parca) < 3:
            continue
        try:
            kullanim.append(float(parca[0]))
            kullanilan += float(parca[1])
            toplam += float(parca[2])
        except ValueError:
            continue
    if not kullanim:
        return None
    return round(max(kullanim), 1), (round(100.0 * kullanilan / toplam, 1) if toplam > 0 else None)


def typeperf_ayristir(cikti: str) -> float | None:
    """`typeperf "\\GPU Engine(*)\\Utilization Percentage" -sc 1` CSV'si -> GPU %. Motor turu (3D, Compute, Copy...) basina toplanir, en yuksek tur alinir (Gorev Yoneticisi gibi)."""
    satirlar = [s for s in csv.reader(io.StringIO(cikti)) if len(s) > 2]
    if len(satirlar) < 2:
        return None
    baslik, degerler = satirlar[0], satirlar[1]
    tur_toplam: dict[str, float] = {}
    for ad, deger in zip(baslik[1:], degerler[1:]):
        govde = ad.lower()
        if "engtype_" not in govde:
            continue
        tur = govde.split("engtype_", 1)[1].split(")", 1)[0].split("\\", 1)[0]
        try:
            tur_toplam[tur] = tur_toplam.get(tur, 0.0) + float(deger)
        except ValueError:
            continue
    return round(min(100.0, max(tur_toplam.values())), 1) if tur_toplam else None


def _calistir(argv: list[str]) -> str | None:
    try:
        c = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL, timeout=6, creationflags=_GIZLE)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return c.stdout if c.returncode == 0 else None


def gpu_oku() -> tuple[float | None, float | None]:
    """(GPU %, GPU bellek %). Okunamazsa (None, None)."""
    if shutil.which("nvidia-smi"):
        cikti = _calistir(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total", "--format=csv,noheader,nounits"])
        sonuc = nvidia_ayristir(cikti) if cikti else None
        if sonuc:
            return sonuc
    if os.name == "nt" and shutil.which("typeperf"):
        cikti = _calistir(["typeperf", r"\GPU Engine(*)\Utilization Percentage", "-sc", "1"])
        yuzde = typeperf_ayristir(cikti) if cikti else None
        if yuzde is not None:
            return yuzde, None
    return None, None


class Izleyici:
    def __init__(self):
        self._kilit = threading.Lock()
        self._veri: dict = {"cpu": None, "gpu": None, "gpu_bellek": None, "zaman": None}
        self._son_istek = 0.0
        self._is_parcacigi: threading.Thread | None = None

    def oku(self) -> dict:
        """Son olcum (anlik; olcumu arka plan parcacigi yapar)."""
        with self._kilit:
            self._son_istek = time.time()
            if self._is_parcacigi is None or not self._is_parcacigi.is_alive():
                self._is_parcacigi = threading.Thread(target=self._dongu, daemon=True)
                self._is_parcacigi.start()
            return dict(self._veri)

    def _dongu(self) -> None:
        onceki = _sistem_zamanlari()
        while True:
            time.sleep(ARALIK_SN)
            with self._kilit:
                if time.time() - self._son_istek > AKTIF_SN:
                    self._is_parcacigi = None
                    return
            simdi = _sistem_zamanlari()
            cpu = cpu_yuzde(onceki, simdi) if simdi else None
            onceki = simdi or onceki
            gpu, bellek = gpu_oku()
            with self._kilit:
                self._veri = {"cpu": cpu, "gpu": gpu, "gpu_bellek": bellek, "zaman": time.time()}
