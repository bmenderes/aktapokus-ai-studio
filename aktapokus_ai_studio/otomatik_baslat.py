"""Bilgisayar acilinca (Windows'ta oturum acilinca) Aktapokus kendiliginden baslasin.

Kayit: `HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run` altinda `Aktapokus` degeri (yonetici izni gerekmez, yalniz bu kullanici).
Komut masaustu kisayoluyla ayni modu acar (`ui --uygulama`: konsolsuz pythonw, kendi penceresi); paket kurulu olmadigi icin yol komutun icine gomulur
(Run anahtari calisma klasorunu ayarlamaz). Ayar ayri bir dosyada TUTULMAZ: kaynak dogruluk kayit defteridir, anahtari kullanici ya da Windows silerse
ayar da kendiliginden kapali gorunur. Yalniz yerel arayuzden yonetilir (`uzak.politika`). Windows disinda `desteklenir` False.

Testler gercek kayit defterine ASLA dokunmaz: `Kayit` arayuzu sahteyle degistirilir (conftest)."""

from __future__ import annotations

import sys
from pathlib import Path

ANAHTAR_YOLU = r"Software\Microsoft\Windows\CurrentVersion\Run"
DEGER_ADI = "Aktapokus"
PROJE_KOKU = Path(__file__).resolve().parent.parent


class Kayit:
    """Run anahtarindaki tek degerin okunmasi/yazilmasi/silinmesi (winreg uzerinden; testlerde sahtesi kullanilir)."""

    def oku(self) -> str | None:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, ANAHTAR_YOLU, 0, winreg.KEY_READ) as k:
                deger, tur = winreg.QueryValueEx(k, DEGER_ADI)
        except FileNotFoundError:
            return None
        return deger if isinstance(deger, str) else None

    def yaz(self, komut: str) -> None:
        import winreg

        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, ANAHTAR_YOLU, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, DEGER_ADI, 0, winreg.REG_SZ, komut)

    def sil(self) -> None:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, ANAHTAR_YOLU, 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, DEGER_ADI)
        except FileNotFoundError:
            pass


class OtomatikBaslatHatasi(Exception):
    pass


def _gercek() -> Kayit:
    return Kayit()


def desteklenir() -> bool:
    return sys.platform == "win32"


def komut_uret(python: str | None = None, kok: Path | None = None) -> str:
    """Kayda yazilacak komut: konsolsuz pythonw, proje klasoru yola eklenip oraya gecilir, sonra masaustu uygulamasi modu."""
    py = Path(python or sys.executable)
    if py.name.lower() == "python.exe" and (py.parent / "pythonw.exe").is_file():
        py = py.parent / "pythonw.exe"
    kok = Path(kok or PROJE_KOKU)
    if "'" in str(kok) or '"' in str(kok):
        raise OtomatikBaslatHatasi("Proje klasoru yolunda tirnak isareti var; otomatik baslatma kurulamaz")
    kod = f"import os,sys;os.chdir(r'{kok}');sys.path.insert(0,r'{kok}');sys.argv=['aktapokus','ui','--uygulama'];from aktapokus_ai_studio.cli import main_giris;main_giris()"
    return f'"{py}" -c "{kod}"'


def durum(kayit: Kayit | None = None) -> dict:
    """{desteklenir, acik}: acik = Run anahtarinda Aktapokus'a ait bir deger var."""
    if not desteklenir() and kayit is None:
        return {"desteklenir": False, "acik": False}
    try:
        deger = (kayit or _gercek()).oku()
    except OSError:
        deger = None
    return {"desteklenir": True, "acik": bool(deger and "aktapokus_ai_studio" in deger)}


def ayarla(acik: object, kayit: Kayit | None = None, komut: str | None = None) -> dict:
    if not isinstance(acik, bool):
        raise OtomatikBaslatHatasi("'acik' true/false olmali")
    if not desteklenir() and kayit is None:
        raise OtomatikBaslatHatasi("Otomatik baslatma yalniz Windows'ta desteklenir")
    k = kayit or _gercek()
    try:
        if acik:
            k.yaz(komut or komut_uret())
        else:
            k.sil()
    except OSError as hata:
        raise OtomatikBaslatHatasi(f"Kayit defterine yazilamadi: {hata.strerror or type(hata).__name__}") from None
    return durum(k)
