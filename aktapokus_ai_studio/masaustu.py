"""Masaustu kontrolu: pencereleri ve ekrani gorme, program acma, tiklama, yazma. Yalniz standart kutuphane + Windows API (ek kurulum yok).

Varsayilan KAPALI: proje bazinda kullanici acar (Ayarlar > Masaustu). Ajana MCP araci olarak verilir (masaustu_mcp.py); proje klasor korumasinin DISINDADIR.
Engeller (bir guvenlik siniri degil, kaza onleyici): engelli programlara girdi gitmez ve baslatilmaz (varsayilan: PLC programlama, kabuk, parola yoneticisi),
Aktapokus'un kendi penceresine girdi gitmez (ajan kendi planini onaylayamaz). Fare sol ust koseye goturulurse islemler durur. Yazilan metin kayda yazilmaz.
"""

from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
import sys
import time
import zlib
from pathlib import Path

AZAMI_GENISLIK = 1280
ENGELLI_PROGRAMLAR = ("logicbuilder", "machineexpert", "somachine", "codesys", "pd-netmanage", "netmanage", "tiaportal", "portal", "studio5000", "rslogix", "twincat", "xaeshell", "gxworks", "cxprogrammer",
                      "cmd", "powershell", "pwsh", "windowsterminal", "wt", "conhost", "regedit", "mmc", "keepass", "1password", "bitwarden", "lastpass")
ENGELLI_BASLIK_TAM = ("aktapokus",)  # kendi arayuzumuz
KILIT_PROGRAMLARI = ("lockapp.exe", "logonui.exe", "consent.exe", "credentialuibroker.exe")  # kilit ekrani ve parola/izin sorulari: listeden kaldirilamaz
ENGELLI_BASLIK_ICERIR = ("node-red",)  # akislari PLC'ye yazabilir
YASAK_TUSLAR = {"win"}  # Win+R gibi kisayollar program engelini atlatir
TUSLAR = {"ctrl": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B, "enter": 0x0D, "tab": 0x09, "esc": 0x1B, "backspace": 0x08, "delete": 0x2E, "space": 0x20, "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
          "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22, **{f"f{i}": 0x6F + i for i in range(1, 13)}}
_son_goruntu = {"x": 0, "y": 0, "olcek": 1.0}


class MasaustuHatasi(Exception):
    pass


# --- ayar ve kayit -----------------------------------------------------------------------------------------------------
def _klasor() -> Path:
    return Path(os.environ.get("AKTAPOKUS_MASAUSTU") or Path.home() / ".aktapokus" / "masaustu")


def ayar_oku() -> dict:
    try:
        v = json.loads((_klasor() / "ayar.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        v = {}
    programlar = v.get("programlar") if isinstance(v, dict) else None
    return {"durduruldu": bool(v.get("durduruldu")) if isinstance(v, dict) else False,
            "programlar": [str(p).strip().lower() for p in programlar if str(p).strip()] if isinstance(programlar, list) else list(ENGELLI_PROGRAMLAR)}


def ayar_yaz(durduruldu: object = None, programlar: object = None) -> dict:
    a = ayar_oku()
    if durduruldu is not None:
        a["durduruldu"] = bool(durduruldu)
    if programlar is not None:
        if not isinstance(programlar, list) or len(programlar) > 200 or not all(isinstance(p, str) and len(p) < 100 for p in programlar):
            raise MasaustuHatasi("Program listesi gecersiz")
        a["programlar"] = [p.strip().lower() for p in programlar if p.strip()]
    _klasor().mkdir(parents=True, exist_ok=True)
    (_klasor() / "ayar.json").write_text(json.dumps(a, ensure_ascii=False, indent=1), encoding="utf-8")
    return a


def kaydet(arac: str, ozet: object, sonuc: str = "tamam") -> None:
    try:
        _klasor().mkdir(parents=True, exist_ok=True)
        yol = _klasor() / "kayit.jsonl"
        if yol.is_file() and yol.stat().st_size > 1_000_000:
            os.replace(yol, yol.with_suffix(".eski"))
        with open(yol, "a", encoding="utf-8") as f:
            f.write(json.dumps({"zaman": time.strftime("%Y-%m-%d %H:%M:%S"), "arac": arac, "ozet": str(ozet)[:200], "sonuc": sonuc[:200]}, ensure_ascii=False) + "\n")
    except OSError:
        pass


def kayit_oku(adet: int = 20) -> list[dict]:
    try:
        satirlar = (_klasor() / "kayit.jsonl").read_text(encoding="utf-8", errors="replace").splitlines()[-adet:]
    except OSError:
        return []
    sonuc = []
    for s in reversed(satirlar):
        try:
            sonuc.append(json.loads(s))
        except ValueError:
            continue
    return sonuc


# --- engel kurallari ---------------------------------------------------------------------------------------------------
def program_engelli(ad: str, liste: list[str] | None = None) -> bool:
    k = Path(ad).stem.lower().replace(" ", "") if ad else ""
    return any(e.replace(" ", "") in k for e in (liste if liste is not None else ayar_oku()["programlar"]) if e) if k else False


def baslik_engelli(baslik: str) -> bool:
    b = (baslik or "").strip().lower()
    return b in ENGELLI_BASLIK_TAM or any(p in b for p in ENGELLI_BASLIK_ICERIR)


def _izin_ver(hwnd: int) -> dict:
    """Girdi gidecek pencereyi denetler; engelliyse hata verir (engellenen pencerenin icerigi kayda yazilmaz)."""
    if not hwnd:
        raise MasaustuHatasi("Etkin pencere yok (oturum kilitli ya da uzak masaustu simge durumunda olabilir)")
    b = pencere_bilgi(hwnd)
    if b["program"].lower() in KILIT_PROGRAMLARI or "lock screen" in b["baslik"].lower():
        raise MasaustuHatasi("Oturum kilitli ya da parola/izin soruluyor: girdi gonderilmez")
    if program_engelli(b["program"]) or baslik_engelli(b["baslik"]):
        raise MasaustuHatasi(f"Bu pencereye girdi gonderilemez: {b['program']} (Ayarlar > Masaustu'nden degistirilebilir)")
    return b


def _hazirlik() -> None:
    if sys.platform != "win32":
        raise MasaustuHatasi("Masaustu kontrolu yalniz Windows'ta calisir")
    if ayar_oku()["durduruldu"]:
        raise MasaustuHatasi("Masaustu kontrolu kullanici tarafindan durduruldu")
    x, y = _fare_konumu()
    ox, oy, _, _ = _sanal_ekran()
    if abs(x - ox) <= 2 and abs(y - oy) <= 2:
        raise MasaustuHatasi("Acil durdurma: fare ekranin sol ust kosesinde")


def tus_coz(metin: object) -> list[int]:
    """'ctrl+s' > sanal tus kodlari. Yalniz bilinen tuslar ve tek harf/rakam."""
    if not isinstance(metin, str) or not metin.strip():
        raise MasaustuHatasi("Tus gecersiz")
    kodlar = []
    for p in metin.lower().replace(" ", "").split("+"):
        if p in YASAK_TUSLAR:
            raise MasaustuHatasi(f"'{p}' tusu kullanilamaz")
        if p in TUSLAR:
            kodlar.append(TUSLAR[p])
        elif len(p) == 1 and p.isascii() and p.isalnum():
            kodlar.append(ord(p.upper()))
        else:
            raise MasaustuHatasi(f"Bilinmeyen tus: {p}")
    return kodlar


def koordinat_coz(x: object, y: object, kaynak: object = "goruntu", son: dict | None = None) -> tuple[int, int]:
    """Goruntu koordinati son ekran goruntusune gore ekrana cevrilir; 'ekran' oldugu gibi kalir (ogeler aracinin kutulari)."""
    try:
        x, y = float(x), float(y)
    except (TypeError, ValueError):
        raise MasaustuHatasi("Koordinat sayi olmali") from None
    if kaynak == "ekran":
        return int(x), int(y)
    s = son or _son_goruntu
    return int(s["x"] + x / s["olcek"]), int(s["y"] + y / s["olcek"])


# --- PNG ---------------------------------------------------------------------------------------------------------------
def png_kodla(bgra: bytes, g: int, y: int) -> bytes:
    satirlar = bytearray()
    for j in range(y):
        s = bgra[j * g * 4:(j + 1) * g * 4]
        r = bytearray(g * 3)
        r[0::3], r[1::3], r[2::3] = s[2::4], s[1::4], s[0::4]
        satirlar.append(0)
        satirlar += r

    def blok(t: bytes, v: bytes) -> bytes:
        return struct.pack(">I", len(v)) + t + v + struct.pack(">I", zlib.crc32(t + v))
    return b"\x89PNG\r\n\x1a\n" + blok(b"IHDR", struct.pack(">IIBBBBB", g, y, 8, 2, 0, 0, 0)) + blok(b"IDAT", zlib.compress(bytes(satirlar), 6)) + blok(b"IEND", b"")


# --- Windows API (testler bu katmani gercek masaustune dokunmadan degistirir) ---------------------------------------------
_w = None


def _api():
    global _w
    if _w is not None:
        return _w
    import ctypes
    from ctypes import wintypes as t

    if sys.platform != "win32":
        raise MasaustuHatasi("Masaustu kontrolu yalniz Windows'ta calisir")
    u, g, k = ctypes.WinDLL("user32", use_last_error=True), ctypes.WinDLL("gdi32"), ctypes.WinDLL("kernel32", use_last_error=True)
    try:
        u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # koordinatlar gercek piksel olsun
    except (OSError, AttributeError):
        pass
    H = ctypes.c_void_p
    for ad, ret, arg in (
        ("GetForegroundWindow", H, []), ("SetForegroundWindow", t.BOOL, [H]), ("GetWindowTextW", ctypes.c_int, [H, t.LPWSTR, ctypes.c_int]), ("GetWindowRect", t.BOOL, [H, ctypes.POINTER(t.RECT)]),
        ("IsWindowVisible", t.BOOL, [H]), ("IsWindow", t.BOOL, [H]), ("IsIconic", t.BOOL, [H]), ("ShowWindow", t.BOOL, [H, ctypes.c_int]), ("GetWindowThreadProcessId", t.DWORD, [H, ctypes.POINTER(t.DWORD)]),
        ("WindowFromPoint", H, [t.POINT]), ("GetAncestor", H, [H, t.UINT]), ("GetSystemMetrics", ctypes.c_int, [ctypes.c_int]), ("SetCursorPos", t.BOOL, [ctypes.c_int, ctypes.c_int]), ("GetCursorPos", t.BOOL, [ctypes.POINTER(t.POINT)]),
        ("GetDC", H, [H]), ("ReleaseDC", ctypes.c_int, [H, H]),
    ):
        f = getattr(u, ad)
        f.restype, f.argtypes = ret, arg
    for ad, ret, arg in (
        ("CreateCompatibleDC", H, [H]), ("CreateCompatibleBitmap", H, [H, ctypes.c_int, ctypes.c_int]), ("SelectObject", H, [H, H]), ("SetStretchBltMode", ctypes.c_int, [H, ctypes.c_int]),
        ("StretchBlt", t.BOOL, [H, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, H, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, t.DWORD]),
        ("GetDIBits", ctypes.c_int, [H, H, t.UINT, t.UINT, H, H, t.UINT]), ("DeleteObject", t.BOOL, [H]), ("DeleteDC", t.BOOL, [H]),
    ):
        f = getattr(g, ad)
        f.restype, f.argtypes = ret, arg
    k.OpenProcess.restype, k.OpenProcess.argtypes = H, [t.DWORD, t.BOOL, t.DWORD]
    k.CloseHandle.argtypes = [H]
    k.QueryFullProcessImageNameW.restype, k.QueryFullProcessImageNameW.argtypes = t.BOOL, [H, t.DWORD, t.LPWSTR, ctypes.POINTER(t.DWORD)]

    class MI(ctypes.Structure):
        _fields_ = [("dx", t.LONG), ("dy", t.LONG), ("veri", t.DWORD), ("bayrak", t.DWORD), ("zaman", t.DWORD), ("ek", ctypes.c_size_t)]

    class KI(ctypes.Structure):
        _fields_ = [("vk", t.WORD), ("tarama", t.WORD), ("bayrak", t.DWORD), ("zaman", t.DWORD), ("ek", ctypes.c_size_t)]

    class HI(ctypes.Structure):
        _fields_ = [("a", t.DWORD), ("b", t.WORD), ("c", t.WORD)]

    class BIRLIK(ctypes.Union):
        _fields_ = [("m", MI), ("k", KI), ("h", HI)]

    class GIRDI(ctypes.Structure):
        _fields_ = [("tur", t.DWORD), ("b", BIRLIK)]

    u.SendInput.restype, u.SendInput.argtypes = t.UINT, [t.UINT, ctypes.POINTER(GIRDI), ctypes.c_int]
    _w = type("W", (), {"u": u, "g": g, "k": k, "c": ctypes, "t": t, "MI": MI, "KI": KI, "GIRDI": GIRDI})
    return _w


def _fare_konumu() -> tuple[int, int]:
    w = _api()
    p = w.t.POINT()
    w.u.GetCursorPos(w.c.byref(p))
    return p.x, p.y


def _sanal_ekran() -> tuple[int, int, int, int]:
    m = _api().u.GetSystemMetrics
    return m(76), m(77), m(78), m(79)


def _on_pencere() -> int:
    return _api().u.GetForegroundWindow() or 0


def _nokta_penceresi(x: int, y: int) -> int:
    w = _api()
    h = w.u.WindowFromPoint(w.t.POINT(x, y))
    return (w.u.GetAncestor(h, 2) or 0) if h else 0


def pencere_bilgi(hwnd: int) -> dict:
    w = _api()
    tampon = w.c.create_unicode_buffer(512)
    w.u.GetWindowTextW(hwnd, tampon, 512)
    r = w.t.RECT()
    w.u.GetWindowRect(hwnd, w.c.byref(r))
    pid = w.t.DWORD()
    w.u.GetWindowThreadProcessId(hwnd, w.c.byref(pid))
    program = ""
    h = w.k.OpenProcess(0x1000, False, pid.value)
    if h:
        ad = w.c.create_unicode_buffer(1024)
        n = w.t.DWORD(1024)
        if w.k.QueryFullProcessImageNameW(h, 0, ad, w.c.byref(n)):
            program = Path(ad.value).name
        w.k.CloseHandle(h)
    return {"pencere": int(hwnd), "baslik": tampon.value, "program": program, "x": r.left, "y": r.top, "genislik": r.right - r.left, "yukseklik": r.bottom - r.top, "kucuk": bool(w.u.IsIconic(hwnd))}


def _girdi(ogeler: list[tuple]) -> None:
    """('k', vk, tarama, bayrak) ya da ('m', veri, bayrak) listesini tek seferde gonderir."""
    w = _api()
    dizi = (w.GIRDI * len(ogeler))()
    for i, o in enumerate(ogeler):
        if o[0] == "k":
            dizi[i].tur = 1
            dizi[i].b.k = w.KI(o[1], o[2], o[3], 0, 0)
        else:
            dizi[i].tur = 0
            dizi[i].b.m = w.MI(0, 0, o[1] & 0xFFFFFFFF, o[2], 0, 0)
    if w.u.SendInput(len(ogeler), dizi, w.c.sizeof(w.GIRDI)) != len(ogeler):
        raise MasaustuHatasi("Girdi gonderilemedi (hedef pencere yonetici olarak calisiyor olabilir)")


# --- araclar -----------------------------------------------------------------------------------------------------------
def pencereler() -> list[dict]:
    if sys.platform != "win32":
        raise MasaustuHatasi("Masaustu kontrolu yalniz Windows'ta calisir")
    w = _api()
    bulunan: list[int] = []
    GERI = w.c.WINFUNCTYPE(w.t.BOOL, w.c.c_void_p, w.c.c_void_p)

    def bak(h, _):
        if w.u.IsWindowVisible(h) and w.u.GetWindowTextW(h, w.c.create_unicode_buffer(2), 2):
            bulunan.append(h or 0)
        return True
    w.u.EnumWindows.argtypes = [GERI, w.c.c_void_p]
    w.u.EnumWindows(GERI(bak), None)
    on = _on_pencere()
    sonuc = []
    dwm = w.c.WinDLL("dwmapi")
    for h in bulunan:
        gizli = w.t.DWORD()
        dwm.DwmGetWindowAttribute(w.c.c_void_p(h), 14, w.c.byref(gizli), 4)  # sanal masaustu/UWP hayaletleri
        b = pencere_bilgi(h)
        if gizli.value or b["genislik"] <= 0:
            continue
        b["etkin"] = h == on
        sonuc.append(b)
    return sonuc


def odakla(hwnd: object) -> dict:
    _hazirlik()
    w = _api()
    try:
        h = int(hwnd)
    except (TypeError, ValueError):
        raise MasaustuHatasi("Pencere numarasi gecersiz") from None
    if not w.u.IsWindow(h):
        raise MasaustuHatasi("Boyle bir pencere yok")
    b = _izin_ver(h)
    if w.u.IsIconic(h):
        w.u.ShowWindow(h, 9)
    _girdi([("k", 0x12, 0, 0), ("k", 0x12, 0, 2)])  # Windows odak kilidi: son girdi bizden olmali
    w.u.SetForegroundWindow(h)
    son = time.monotonic() + 1.5
    while _on_pencere() != h and time.monotonic() < son:
        time.sleep(0.05)
    if _on_pencere() != h:
        raise MasaustuHatasi("Pencere one getirilemedi")
    kaydet("odakla", b["baslik"])
    return pencere_bilgi(h)


def ekran_goruntusu(hwnd: object = None) -> tuple[bytes, dict]:
    """(PNG, bilgi). Pencere verilirse once one alinir ve yalniz o alan cekilir; tiklama koordinatlari bu goruntuye gore cevrilir."""
    _hazirlik()
    w = _api()
    if hwnd:
        b = odakla(hwnd)
        x, y, gen, yuk = b["x"], b["y"], b["genislik"], b["yukseklik"]
        time.sleep(0.2)
    else:
        x, y, gen, yuk = _sanal_ekran()
    if gen <= 0 or yuk <= 0:
        raise MasaustuHatasi("Goruntu alani bos")
    olcek = min(1.0, AZAMI_GENISLIK / gen)
    tg, ty = max(1, int(gen * olcek)), max(1, int(yuk * olcek))
    kaynak = w.u.GetDC(None)
    hedef = w.g.CreateCompatibleDC(kaynak)
    bmp = w.g.CreateCompatibleBitmap(kaynak, tg, ty)
    try:
        w.g.SelectObject(hedef, bmp)
        w.g.SetStretchBltMode(hedef, 4)
        if not w.g.StretchBlt(hedef, 0, 0, tg, ty, kaynak, x, y, gen, yuk, 0x00CC0020):
            raise MasaustuHatasi("Ekran okunamadi (oturum kilitli olabilir)")
        bas = struct.pack("<IiiHHIIiiII", 40, tg, -ty, 1, 32, 0, 0, 0, 0, 0, 0)
        bi = w.c.create_string_buffer(bas, 44)
        tampon = w.c.create_string_buffer(tg * ty * 4)
        if w.g.GetDIBits(hedef, bmp, 0, ty, tampon, bi, 0) != ty:
            raise MasaustuHatasi("Ekran okunamadi")
    finally:
        w.g.DeleteObject(bmp)
        w.g.DeleteDC(hedef)
        w.u.ReleaseDC(None, kaynak)
    _son_goruntu.update(x=x, y=y, olcek=olcek)
    kaydet("ekran_goruntusu", f"{gen}x{yuk}")
    return png_kodla(tampon.raw, tg, ty), {"genislik": tg, "yukseklik": ty, "olcek": round(olcek, 4)}


def tikla(x: object, y: object, dugme: object = "sol", cift: object = False, kaynak: object = "goruntu") -> dict:
    _hazirlik()
    ex, ey = koordinat_coz(x, y, kaynak)
    b = _izin_ver(_nokta_penceresi(ex, ey))
    if dugme not in ("sol", "sag"):
        raise MasaustuHatasi("Dugme 'sol' ya da 'sag' olmali")
    _api().u.SetCursorPos(ex, ey)
    time.sleep(0.03)
    a, k = (2, 4) if dugme == "sol" else (8, 0x10)
    _girdi([("m", 0, a), ("m", 0, k)] * (2 if cift else 1))
    kaydet("tikla", f"{ex},{ey} {dugme} {b['program']}")
    return {"x": ex, "y": ey, "pencere": b["baslik"]}


def yaz(metin: object) -> dict:
    _hazirlik()
    if not isinstance(metin, str) or not metin or len(metin) > 20000:
        raise MasaustuHatasi("Metin bos ya da cok uzun")
    b = _izin_ver(_on_pencere())
    ogeler: list[tuple] = []
    for ch in metin.replace("\r\n", "\n"):
        if ch in "\n\t":
            vk = 0x0D if ch == "\n" else 0x09
            ogeler += [("k", vk, 0, 0), ("k", vk, 0, 2)]
            continue
        v = ch.encode("utf-16-le")
        for i in range(0, len(v), 2):
            b16 = int.from_bytes(v[i:i + 2], "little")
            ogeler += [("k", 0, b16, 4), ("k", 0, b16, 6)]
    for i in range(0, len(ogeler), 200):
        _hazirlik()  # uzun metinde acil durdurma ve odak degisimi denetlensin
        if _on_pencere() != b["pencere"]:
            raise MasaustuHatasi("Yazarken etkin pencere degisti; durduruldu")
        _girdi(ogeler[i:i + 200])
        time.sleep(0.02)
    kaydet("yaz", f"{len(metin)} karakter > {b['program']}")
    return {"pencere": b["baslik"], "karakter": len(metin)}


def tus(tuslar: object) -> dict:
    _hazirlik()
    kodlar = tus_coz(tuslar)
    b = _izin_ver(_on_pencere())
    _girdi([("k", k, 0, 0) for k in kodlar] + [("k", k, 0, 2) for k in reversed(kodlar)])
    kaydet("tus", f"{tuslar} > {b['program']}")
    return {"pencere": b["baslik"], "tus": tuslar}


def kaydir(x: object, y: object, miktar: object, kaynak: object = "goruntu") -> dict:
    _hazirlik()
    ex, ey = koordinat_coz(x, y, kaynak)
    b = _izin_ver(_nokta_penceresi(ex, ey))
    try:
        adet = max(-50, min(50, int(miktar)))
    except (TypeError, ValueError):
        raise MasaustuHatasi("Miktar sayi olmali") from None
    _api().u.SetCursorPos(ex, ey)
    _girdi([("m", adet * 120, 0x800)])
    kaydet("kaydir", f"{ex},{ey} {adet} {b['program']}")
    return {"x": ex, "y": ey, "miktar": adet}


def _baslatma_menusu() -> list[Path]:
    yerler = [Path(os.environ.get("ProgramData", r"C:\ProgramData")), Path(os.environ.get("APPDATA", ""))]
    sonuc: list[Path] = []
    for y in yerler:
        sonuc += list((y / "Microsoft" / "Windows" / "Start Menu" / "Programs").rglob("*.lnk"))
    return sonuc


def _lnk_hedefi(lnk: Path) -> str:
    betik = "$OutputEncoding=[Console]::OutputEncoding=[Text.UTF8Encoding]::new();(New-Object -ComObject WScript.Shell).CreateShortcut($args[0]).TargetPath"
    try:
        return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", betik, str(lnk)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,
                              stdin=subprocess.DEVNULL, creationflags=0x08000000).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def program_coz(ad: object, menu=None, hedef=None) -> tuple[str, Path | None]:
    """(calistirilacak exe, kisayol). Mutlak .exe, PATH'teki ad ya da Baslat menusundeki kisayol adi. Engelli olan ve .exe olmayan reddedilir."""
    if not isinstance(ad, str) or not ad.strip() or len(ad) > 400 or "\0" in ad:
        raise MasaustuHatasi("Program adi gecersiz")
    ad = ad.strip()
    if program_engelli(ad):
        raise MasaustuHatasi(f"Bu program baslatilamaz: {ad}")
    exe = ad if Path(ad).is_absolute() and Path(ad).is_file() else shutil.which(ad)
    lnk = None
    if not exe:
        adaylar = [p for p in (menu if menu is not None else _baslatma_menusu()) if ad.lower() in p.stem.lower()]
        tam = [p for p in adaylar if p.stem.lower() == ad.lower()]
        adaylar = tam or adaylar
        if not adaylar:
            raise MasaustuHatasi(f"Program bulunamadi: {ad}")
        if len(adaylar) > 1:
            raise MasaustuHatasi("Birden cok eslesme: " + ", ".join(sorted(p.stem for p in adaylar)[:10]))
        lnk = adaylar[0]
        exe = (hedef or _lnk_hedefi)(lnk)
    if lnk is not None and not exe:
        return "", lnk  # kurulum kisayolu: hedefi okunamiyor, Windows acar
    if Path(exe).suffix.lower() != ".exe":
        raise MasaustuHatasi(f"Yalniz .exe programlar baslatilir: {Path(exe).name}")
    if program_engelli(Path(exe).name):
        raise MasaustuHatasi(f"Bu program baslatilamaz: {Path(exe).name}")
    return exe, lnk


def program_baslat(ad: object, argumanlar: object = None) -> dict:
    _hazirlik()
    args = argumanlar or []
    if not isinstance(args, list) or len(args) > 30 or not all(isinstance(a, str) and len(a) < 2000 for a in args):
        raise MasaustuHatasi("Argumanlar metin listesi olmali")
    exe, lnk = program_coz(ad)
    if not exe:
        if args:
            raise MasaustuHatasi("Bu kisayola arguman verilemez")
        os.startfile(str(lnk))  # type: ignore[attr-defined]
        kaydet("program_baslat", lnk.stem)
        return {"program": lnk.stem}
    from .runners import _alt_surec_ortami

    p = subprocess.Popen([exe, *args], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=_alt_surec_ortami(Path(exe).parent), cwd=str(Path(exe).parent), creationflags=0x00000008)
    kaydet("program_baslat", f"{Path(exe).name} {len(args)} arguman")
    return {"program": Path(exe).name, "pid": p.pid}


def ogeler(hwnd: object) -> list[dict]:
    """Penceredeki dugme, kutu ve menuler (UI Automation): gorsel gormeyen modeller de kullanabilsin. Kutular ekran koordinatidir."""
    _hazirlik()
    try:
        h = int(hwnd)
    except (TypeError, ValueError):
        raise MasaustuHatasi("Pencere numarasi gecersiz") from None
    _izin_ver(h)
    betik = (
        "$OutputEncoding=[Console]::OutputEncoding=[Text.UTF8Encoding]::new();Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes;"
        "$c=[Windows.Automation.TreeWalker]::ControlViewWalker;$s=New-Object Collections.ArrayList;"
        "function g($e,$d){if($s.Count -ge 300 -or $d -gt 7){return};$k=$c.GetFirstChild($e);while($k -ne $null -and $s.Count -lt 300){$i=$k.Current;$r=$i.BoundingRectangle;"
        "if(-not $r.IsEmpty -and ($i.Name -or $i.AutomationId)){[void]$s.Add(@{ad=$i.Name;tur=$i.ControlType.ProgrammaticName -replace 'ControlType.','';x=[int]$r.X;y=[int]$r.Y;genislik=[int]$r.Width;yukseklik=[int]$r.Height;etkin=$i.IsEnabled})};"
        "g $k ($d+1);$k=$c.GetNextSibling($k)}};"
        f"g ([Windows.Automation.AutomationElement]::FromHandle([IntPtr]{h})) 0;ConvertTo-Json -Compress -InputObject @($s)")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", betik], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, stdin=subprocess.DEVNULL, creationflags=0x08000000)
        v = json.loads(r.stdout) if r.stdout.strip() else []
    except (OSError, subprocess.SubprocessError, ValueError) as hata:
        raise MasaustuHatasi(f"Ogeler okunamadi: {hata}") from None
    kaydet("ogeler", len(v))
    return v if isinstance(v, list) else [v]
