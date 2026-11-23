"""Kullanici klasorunde saklanan sirlar (uzak erisim anahtari, Telegram token'i) icin Windows DPAPI korumasi.

- Windows'ta deger `dpapi:` onekiyle, YALNIZ bu Windows kullanicisinin acabilecegi bicimde saklanir (dosya kopyalansa baska kullanici/makine acamaz).
- Eski duz metin degerler okunmaya devam eder (geriye uyumlu); cagiran bir sonraki yazimda korumali bicime gecirir.
- Windows disinda deger oldugu gibi kalir (dosya izinleri 0600). Acilamayan (baska kullanici/makine) deger None doner: cagiran yenisini uretir."""

from __future__ import annotations

import base64
import os

ON_EK = "dpapi:"
_ENTROPI = b"aktapokus-gizli-v1"


def _dpapi(veri: bytes, koru: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def blob(b: bytes):
        tampon = ctypes.create_string_buffer(b, len(b))
        return Blob(len(b), ctypes.cast(tampon, ctypes.POINTER(ctypes.c_char))), tampon

    girdi, _t1 = blob(veri)
    entropi, _t2 = blob(_ENTROPI)
    cikti = Blob()
    crypt32 = ctypes.windll.crypt32
    f = crypt32.CryptProtectData if koru else crypt32.CryptUnprotectData
    if not f(ctypes.byref(girdi), None, ctypes.byref(entropi), None, None, 0x1, ctypes.byref(cikti)):  # 0x1: arayuz gosterme
        raise OSError("Windows DPAPI islemi basarisiz")
    try:
        return ctypes.string_at(cikti.pbData, cikti.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(cikti.pbData)


def korumali_mi(deger: object) -> bool:
    return isinstance(deger, str) and deger.startswith(ON_EK)


def koru(metin: str) -> str:
    """Saklanacak bicim. Windows disinda ya da DPAPI basarisizsa duz metin (eski davranis) doner."""
    if os.name != "nt":
        return metin
    try:
        return ON_EK + base64.b64encode(_dpapi(metin.encode("utf-8"), True)).decode("ascii")
    except (OSError, AttributeError, ValueError):
        return metin


def ac(deger: object) -> str | None:
    """Saklanan degeri acar: korumaliysa cozer, duz metinse aynen doner; acilamazsa None."""
    if not isinstance(deger, str):
        return None
    if not deger.startswith(ON_EK):
        return deger
    if os.name != "nt":
        return None
    try:
        return _dpapi(base64.b64decode(deger[len(ON_EK):].encode("ascii")), False).decode("utf-8")
    except (OSError, AttributeError, ValueError, UnicodeDecodeError):
        return None
