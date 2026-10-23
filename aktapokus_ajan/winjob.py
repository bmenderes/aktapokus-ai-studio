"""Windows 'job' nesnesi: bu surec olunce (hatta zorla kapatilirsa) bagli alt surecleri OS'in kendisi oldurur.
Gercek denemede arayuz zorla kapatilinca OpenCode sunucusu yetim kalmisti; terminal surecleri icin de ayni guvence gerekir. En iyi caba: basarisizsa None."""

from __future__ import annotations

import os


def bagla(surec_tutamaci: int):
    """`surec_tutamaci`: Windows SURECI tutamaci (Popen._handle ya da CreateProcess'ten gelen hProcess). Donen is tutamaci acik kaldigi surece alt surec yasar."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class TEMEL(ctypes.Structure):
            _fields_ = [("a", ctypes.c_int64), ("b", ctypes.c_int64), ("LimitFlags", wintypes.DWORD), ("c", ctypes.c_size_t), ("d", ctypes.c_size_t),
                        ("e", wintypes.DWORD), ("f", ctypes.c_size_t), ("g", wintypes.DWORD), ("h", wintypes.DWORD)]

        class IO(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint64) for n in "abcdef"]

        class GENIS(ctypes.Structure):
            _fields_ = [("Temel", TEMEL), ("Io", IO), ("a", ctypes.c_size_t), ("b", ctypes.c_size_t), ("c", ctypes.c_size_t), ("d", ctypes.c_size_t)]

        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.CreateJobObjectW.restype = wintypes.HANDLE
        k.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        k.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        is_ = k.CreateJobObjectW(None, None)
        if not is_:
            return None
        bilgi = GENIS()
        bilgi.Temel.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not k.SetInformationJobObject(is_, 9, ctypes.byref(bilgi), ctypes.sizeof(bilgi)):
            return None
        if not k.AssignProcessToJobObject(is_, int(surec_tutamaci)):
            return None
        return is_
    except Exception:
        return None
