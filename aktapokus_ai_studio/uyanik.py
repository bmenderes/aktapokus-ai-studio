"""Uyku engeli: uzak erisim (Tailscale) acikken bilgisayar uyumasin; telefondan baglanirken Windows uykuya gecip baglantiyi koparmasin.

Windows `SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)`: sistemin UYUMASINI ister (ekran kapanabilir; ES_DISPLAY_REQUIRED kullanilmaz). Durum
cagiran IPLIGE baglidir: bu yuzden ayri bir arka plan ipligi bunu ayarlar, `kapat()` gelene kadar bekler ve sonra eski haline dondurur (surec kapanirsa
isletim sistemi de kendiliginden birakir). Windows disinda yapacak bir sey yoktur (`desteklenir` False). Ek kurulum gerekmez (yalniz standart kutuphane ctypes)."""

from __future__ import annotations

import sys
import threading
from typing import Callable

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def _windows_durum_ayarla(bayrak: int) -> int:
    import ctypes

    return int(ctypes.windll.kernel32.SetThreadExecutionState(ctypes.c_uint(bayrak)))


class UykuEngeli:
    def __init__(self, ayarla: Callable[[int], int] | None = None, windows: bool | None = None):
        self._ayarla = ayarla or _windows_durum_ayarla
        self.desteklenir = (sys.platform == "win32") if windows is None else windows
        self._kilit = threading.Lock()
        self._durdur: threading.Event | None = None
        self._ip: threading.Thread | None = None
        self.hata: str | None = None

    @property
    def aktif(self) -> bool:
        return self._ip is not None and self._ip.is_alive()

    def ac(self) -> bool:
        """Uyku engelini baslatir (zaten aciksa bir sey yapmaz). Basarili/aktif ise True."""
        if not self.desteklenir:
            return False
        with self._kilit:
            if self.aktif:
                return True
            hazir, durdur = threading.Event(), threading.Event()
            self.hata = None

            def calis() -> None:
                try:
                    if not self._ayarla(ES_CONTINUOUS | ES_SYSTEM_REQUIRED):
                        self.hata = "Windows uyku engelini kabul etmedi"
                        return
                except Exception as hata:  # ctypes/Windows hatasi uygulamayi dusurmesin
                    self.hata = f"{type(hata).__name__}: {hata}"
                    return
                finally:
                    hazir.set()
                durdur.wait()
                try:
                    self._ayarla(ES_CONTINUOUS)  # eski haline don
                except Exception:
                    pass

            self._durdur = durdur
            self._ip = threading.Thread(target=calis, daemon=True, name="uyku-engeli")
            self._ip.start()
            hazir.wait(timeout=5)
            if self.hata:  # ayar reddedildi/patladi: is parcacigi cikmak uzere; 'aktif' degeri kosul yarisina girmesin
                self._ip.join(timeout=2)
            return self.aktif

    def kapat(self) -> None:
        with self._kilit:
            if self._durdur is not None:
                self._durdur.set()
            ip, self._ip, self._durdur = self._ip, None, None
        if ip is not None:
            ip.join(timeout=5)
