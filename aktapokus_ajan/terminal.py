"""Arayuz terminali: Windows ConPTY uzerinde gercek bir PowerShell (ek paket YOK, yalniz ctypes).

Tam erisimli bir terminaldir (VS Code'daki gibi): komut yazilir, paket kurulur, etkilesimli programlar calisir. Bu yuzden GUVENLIK onemlidir ve burada degil,
cagiran katmanda (arayuz.py) saglanir: yalniz yerel (127.0.0.1) sunucu, belirtec (X-Aktapokus-Token), Host ve Origin denetimi, en cok 3 eszamanli terminal.
Telegram bu modulu KULLANMAZ; telefondan terminale erisilemez.

Surec yasam dongusu: terminal sureci bir Windows 'job' nesnesine baglanir (uygulama olunce, hatta zorla kapatilsa bile OS tum alt surecleri oldurur).
Cikti bellekte sinirli bir tamponda (en son ~1 MB) tutulur: tarayici yeniden baglanirsa son ekrani yeniden alir."""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from pathlib import Path

from . import winjob

AZAMI_TAMPON = 1_000_000  # bayt
CREATE_UNICODE_ENVIRONMENT = 0x400
EXTENDED_STARTUPINFO_PRESENT = 0x00080000
PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE = 0x00020016
INFINITE = 0xFFFFFFFF


class TerminalHatasi(Exception):
    pass


def varsayilan_kabuk() -> list[str]:
    kok = os.environ.get("SystemRoot", r"C:\Windows")
    ps = Path(kok) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    return [str(ps) if ps.is_file() else "powershell.exe", "-NoLogo"]


def destekleniyor() -> bool:
    if os.name != "nt":
        return False
    try:
        import ctypes

        return hasattr(ctypes.WinDLL("kernel32"), "CreatePseudoConsole")  # Windows 10 1809+
    except Exception:
        return False


_KONTROL: dict = {}


def kontrol(yeniden: bool = False) -> bool:
    """ConPTY BU ORTAMDA gercekten calisiyor mu? Kucuk bir kabuk acip isaretli bir cikti bekler (sonuc onbellekte).
    GERCEK DURUM: bazi kisitli ortamlarda (ornegin araclarin kum havuzu) sahte konsol ozniteligi yok sayilir; kabuk gercek konsola yazar ve terminal
    sessiz kalir. Bu durum sessiz bir bos ekran yerine acik bir hata olarak gosterilsin diye arayuz bunu sorar."""
    if "sonuc" in _KONTROL and not yeniden:
        return _KONTROL["sonuc"]
    sonuc = False
    if destekleniyor():
        t = None
        try:
            t = Terminal(["cmd.exe", "/c", "echo AKTAPOKUS_PTY_TAMAM"], None, 24, 80)
            son, cikti = 0, b""
            bitis = time.monotonic() + 8
            while time.monotonic() < bitis and b"AKTAPOKUS_PTY_TAMAM" not in cikti:
                parcalar, bitti = t.bekle(son, 1.0)
                for sira, veri in parcalar:
                    son, cikti = sira, cikti + veri
                if bitti:
                    break
            sonuc = b"AKTAPOKUS_PTY_TAMAM" in cikti
        except Exception:
            sonuc = False
        finally:
            if t:
                t.kapat()
    _KONTROL["sonuc"] = sonuc
    return sonuc


class Terminal:
    def __init__(self, komut: list[str] | None = None, klasor: str | Path | None = None, satir: int = 24, sutun: int = 80):
        if not destekleniyor():
            raise TerminalHatasi("Terminal yalnız Windows 10 (1809+) / Windows 11'de desteklenir.")
        self.komut = komut or varsayilan_kabuk()
        self.klasor = str(klasor) if klasor else str(Path.home())
        self.satir, self.sutun = max(2, min(500, int(satir))), max(2, min(1000, int(sutun)))
        self._kilit = threading.Lock()
        self._cond = threading.Condition()
        self._parcalar: deque[tuple[int, bytes]] = deque()
        self._boyut = 0
        self._sira = 0
        self._bitti = False
        self._kapali = False
        self.pid: int | None = None
        self._h: dict = {}
        self._is_tutamaci = None
        self._baslat()

    # ---- ctypes tanimlari ----
    def _api(self):
        import ctypes
        from ctypes import wintypes

        k = ctypes.WinDLL("kernel32", use_last_error=True)
        V = ctypes.c_void_p

        class COORD(ctypes.Structure):
            _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]

        class STARTUPINFOW(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR), ("lpDesktop", wintypes.LPWSTR), ("lpTitle", wintypes.LPWSTR),
                        ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD), ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD),
                        ("dwXCountChars", wintypes.DWORD), ("dwYCountChars", wintypes.DWORD), ("dwFillAttribute", wintypes.DWORD),
                        ("dwFlags", wintypes.DWORD), ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD), ("lpReserved2", V),
                        ("hStdInput", V), ("hStdOutput", V), ("hStdError", V)]

        class STARTUPINFOEXW(ctypes.Structure):
            _fields_ = [("StartupInfo", STARTUPINFOW), ("lpAttributeList", V)]

        class PROCESS_INFORMATION(ctypes.Structure):
            _fields_ = [("hProcess", V), ("hThread", V), ("dwProcessId", wintypes.DWORD), ("dwThreadId", wintypes.DWORD)]

        k.CreatePipe.argtypes = [ctypes.POINTER(V), ctypes.POINTER(V), V, wintypes.DWORD]
        k.CreatePipe.restype = wintypes.BOOL
        k.CreatePseudoConsole.argtypes = [COORD, V, V, wintypes.DWORD, ctypes.POINTER(V)]
        k.CreatePseudoConsole.restype = ctypes.c_long  # HRESULT
        k.ResizePseudoConsole.argtypes = [V, COORD]
        k.ResizePseudoConsole.restype = ctypes.c_long
        k.ClosePseudoConsole.argtypes = [V]
        k.ClosePseudoConsole.restype = None
        k.InitializeProcThreadAttributeList.argtypes = [V, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.c_size_t)]
        k.InitializeProcThreadAttributeList.restype = wintypes.BOOL
        k.UpdateProcThreadAttribute.argtypes = [V, wintypes.DWORD, ctypes.c_size_t, V, ctypes.c_size_t, V, V]
        k.UpdateProcThreadAttribute.restype = wintypes.BOOL
        k.DeleteProcThreadAttributeList.argtypes = [V]
        k.DeleteProcThreadAttributeList.restype = None
        k.CreateProcessW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, V, V, wintypes.BOOL, wintypes.DWORD, V, wintypes.LPCWSTR, V, V]
        k.CreateProcessW.restype = wintypes.BOOL
        k.ReadFile.argtypes = [V, V, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), V]
        k.ReadFile.restype = wintypes.BOOL
        k.WriteFile.argtypes = [V, V, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), V]
        k.WriteFile.restype = wintypes.BOOL
        k.CloseHandle.argtypes = [V]
        k.CloseHandle.restype = wintypes.BOOL
        k.TerminateProcess.argtypes = [V, wintypes.UINT]
        k.TerminateProcess.restype = wintypes.BOOL
        k.WaitForSingleObject.argtypes = [V, wintypes.DWORD]
        k.WaitForSingleObject.restype = wintypes.DWORD
        return ctypes, wintypes, k, V, COORD, STARTUPINFOEXW, PROCESS_INFORMATION

    def _baslat(self) -> None:
        ctypes, wintypes, k, V, COORD, STARTUPINFOEXW, PROCESS_INFORMATION = self._api()
        self._k, self._ct, self._wt, self._COORD = k, ctypes, wintypes, COORD
        girdi_oku, girdi_yaz, cikti_oku, cikti_yaz = V(), V(), V(), V()
        if not k.CreatePipe(ctypes.byref(girdi_oku), ctypes.byref(girdi_yaz), None, 0) or not k.CreatePipe(ctypes.byref(cikti_oku), ctypes.byref(cikti_yaz), None, 0):
            raise TerminalHatasi("Boru oluşturulamadı.")
        hpc = V()
        hr = k.CreatePseudoConsole(COORD(self.sutun, self.satir), girdi_oku, cikti_yaz, 0, ctypes.byref(hpc))
        if hr != 0:
            for h in (girdi_oku, girdi_yaz, cikti_oku, cikti_yaz):
                k.CloseHandle(h)
            raise TerminalHatasi(f"Sahte konsol (ConPTY) oluşturulamadı (HRESULT {hr & 0xFFFFFFFF:#x}).")
        k.CloseHandle(girdi_oku)  # artik PTY'ye ait
        k.CloseHandle(cikti_yaz)
        boyut = ctypes.c_size_t(0)
        k.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(boyut))
        liste = ctypes.create_string_buffer(boyut.value)
        if not k.InitializeProcThreadAttributeList(liste, 1, 0, ctypes.byref(boyut)):
            raise TerminalHatasi("Öznitelik listesi oluşturulamadı.")
        if not k.UpdateProcThreadAttribute(liste, 0, PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE, hpc, ctypes.sizeof(V), None, None):
            raise TerminalHatasi("Sahte konsol sürece bağlanamadı.")
        si = STARTUPINFOEXW()
        si.StartupInfo.cb = ctypes.sizeof(STARTUPINFOEXW)
        # GERCEK HATA: bu surecin standart tutamaclari bir dosyaya/boruya yonlendirilmisse (pytest'in cikti yakalamasi, bazi arac ortamlari) kabuk sahte konsola
        # DEGIL bu yonlendirmeye yazar ve terminal sessiz kalir. STARTF_USESTDHANDLES'i BOS tutamaclarla vermek, alt surecin ebeveynin tutamaclarini
        # devralmasini engeller ve standart tutamaclarini sahte konsoldan almasini saglar.
        si.StartupInfo.dwFlags = 0x00000100  # STARTF_USESTDHANDLES (hStdInput/hStdOutput/hStdError = NULL)
        si.lpAttributeList = ctypes.cast(liste, V)
        pi = PROCESS_INFORMATION()
        ortam = os.environ.copy()
        ortam["AKTAPOKUS_TERMINAL"] = "1"
        blok = ctypes.create_unicode_buffer("".join(f"{a}={d}\0" for a, d in ortam.items()) + "\0")
        satir = ctypes.create_unicode_buffer(" ".join(f'"{a}"' if " " in a else a for a in self.komut))
        ok = k.CreateProcessW(None, satir, None, None, False, EXTENDED_STARTUPINFO_PRESENT | CREATE_UNICODE_ENVIRONMENT, ctypes.cast(blok, V), self.klasor, ctypes.byref(si), ctypes.byref(pi))
        k.DeleteProcThreadAttributeList(liste)
        if not ok:
            hata = ctypes.get_last_error()
            k.ClosePseudoConsole(hpc)
            k.CloseHandle(girdi_yaz)
            k.CloseHandle(cikti_oku)
            raise TerminalHatasi(f"Kabuk başlatılamadı (Windows hatası {hata}): {self.komut[0]}")
        k.CloseHandle(pi.hThread)
        self.pid = int(pi.dwProcessId)
        self._h = {"hpc": hpc, "girdi": girdi_yaz, "cikti": cikti_oku, "surec": pi.hProcess}
        self._is_tutamaci = winjob.bagla(int(pi.hProcess))
        threading.Thread(target=self._okuyucu, daemon=True, name=f"terminal-oku-{self.pid}").start()
        threading.Thread(target=self._gozcu, daemon=True, name=f"terminal-gozcu-{self.pid}").start()

    # ---- cikti ----
    def _ekle(self, veri: bytes) -> None:
        with self._cond:
            self._sira += 1
            self._parcalar.append((self._sira, veri))
            self._boyut += len(veri)
            while self._boyut > AZAMI_TAMPON and len(self._parcalar) > 1:
                _, eski = self._parcalar.popleft()
                self._boyut -= len(eski)
            self._cond.notify_all()

    def _okuyucu(self) -> None:
        k, ct, wt = self._k, self._ct, self._wt
        tampon = ct.create_string_buffer(8192)
        okunan = wt.DWORD(0)
        while True:
            ok = k.ReadFile(self._h["cikti"], tampon, 8192, ct.byref(okunan), None)
            if not ok or okunan.value == 0:
                break
            self._ekle(tampon.raw[: okunan.value])
        with self._cond:
            self._bitti = True
            self._cond.notify_all()

    def _gozcu(self) -> None:
        """Surec bitince ConPTY borusu kendiliginden kapanmayabilir: sahte konsolu kapatarak okuyucuyu serbest birak."""
        self._k.WaitForSingleObject(self._h["surec"], INFINITE)
        time.sleep(0.3)  # son cikti okunabilsin
        if not self._kapali:
            threading.Thread(target=self._sahte_konsolu_kapat, daemon=True).start()

    def _sahte_konsolu_kapat(self) -> None:
        h = self._h.pop("hpc", None)
        if h:
            self._k.ClosePseudoConsole(h)

    def bekle(self, son_sira: int, zaman_asimi: float = 10.0) -> tuple[list[tuple[int, bytes]], bool]:
        """`son_sira`dan sonraki parcalar (en cok zaman_asimi sn bekler) ve terminalin bitip bitmedigi. Tamponun basi atildiysa eldekiler doner."""
        son = time.monotonic() + zaman_asimi
        with self._cond:
            while True:
                yeni = [(s, v) for s, v in self._parcalar if s > son_sira]
                if yeni or self._bitti:
                    return yeni, self._bitti and not yeni
                kalan = son - time.monotonic()
                if kalan <= 0:
                    return [], False
                self._cond.wait(kalan)

    # ---- girdi / boyut ----
    @property
    def canli(self) -> bool:
        return not self._bitti and not self._kapali

    def yaz(self, veri: bytes) -> None:
        if not self.canli or not veri:
            return
        ct, wt = self._ct, self._wt
        with self._kilit:
            yazilan = wt.DWORD(0)
            tampon = ct.create_string_buffer(bytes(veri), len(veri))
            if not self._k.WriteFile(self._h["girdi"], tampon, len(veri), ct.byref(yazilan), None):
                raise TerminalHatasi("Terminale yazılamadı (kapanmış olabilir).")

    def boyutla(self, satir: int, sutun: int) -> None:
        if not self.canli or "hpc" not in self._h:
            return
        self.satir, self.sutun = max(2, min(500, int(satir))), max(2, min(1000, int(sutun)))
        self._k.ResizePseudoConsole(self._h["hpc"], self._COORD(self.sutun, self.satir))

    # ---- kapatma ----
    def kapat(self) -> None:
        if self._kapali:
            return
        self._kapali = True
        k = self._k
        try:
            k.TerminateProcess(self._h["surec"], 1)
        except Exception:
            pass
        threading.Thread(target=self._sahte_konsolu_kapat, daemon=True).start()  # ClosePseudoConsole bazen cikti bosalana dek bekler: ayri is parcacigi
        for ad in ("girdi",):
            h = self._h.pop(ad, None)
            if h:
                k.CloseHandle(h)
        # cikti tutamagi okuyucu bitince serbest kalir; surec tutamagi ve is nesnesi kapatilir (is nesnesi kapaninca kalan alt surecler de olur)
        threading.Thread(target=self._son_temizlik, daemon=True).start()

    def _son_temizlik(self) -> None:
        for _ in range(50):
            if self._bitti:
                break
            time.sleep(0.1)
        k = self._k
        for ad in ("cikti", "surec"):
            h = self._h.pop(ad, None)
            if h:
                k.CloseHandle(h)
        if self._is_tutamaci:
            k.CloseHandle(self._is_tutamaci)
            self._is_tutamaci = None
