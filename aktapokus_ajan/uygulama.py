"""Masaustu uygulamasi modu (`ui --uygulama`): arayuz sunucusunu SESSIZCE baslatir, Edge/Chrome'un adres cubugu olmayan "uygulama" penceresinde acar,
pencere KAPANINCA sunucuyu (ve altindaki OpenCode surecini) kapatir.

Pencere kapanisi tarayici SURECINDEN degil, sayfanin sunucuyla olan canli baglantisindan (olay akisi) anlasilir: Edge ayni profille calisan bir surece
devredip hemen cikabilir (gercek hata: sunucu 1 sn sonra kapandi, pencere "baglanilamadi" gosterdi). Uygulamaya OZEL ayri bir tarayici profili
(`--user-data-dir`) kullanicinin normal tarayicisina/sekmelerine dokunmaz. Konsol penceresi olmayan `pythonw` ile calisirken alt surecler
(OpenCode, git, codex...) kendi siyah pencerelerini acmasin diye bu modda Popen'a CREATE_NO_WINDOW eklenir. Hatalar `~/.aktapokus/uygulama.log` dosyasina yazilir."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

AYAR_KLASORU = Path.home() / ".aktapokus"
CREATE_NO_WINDOW = 0x08000000


def ayar_dizini() -> Path:
    return Path(os.environ.get("AKTAPOKUS_UYGULAMA_DIZINI") or AYAR_KLASORU)


def log_yolu() -> Path:
    return ayar_dizini() / "uygulama.log"


def log_yaz(mesaj: str) -> None:
    try:
        d = ayar_dizini()
        d.mkdir(parents=True, exist_ok=True)
        with open(log_yolu(), "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + mesaj + "\n")
    except OSError:
        pass


def tarayici_bul() -> str | None:
    """Uygulama modunu destekleyen Chromium tabanli tarayici: AKTAPOKUS_TARAYICI, sonra Edge, sonra Chrome."""
    ortam = os.environ.get("AKTAPOKUS_TARAYICI")
    if ortam and Path(ortam).is_file():
        return ortam
    kokler = [os.environ.get(a) for a in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA")]
    adaylar = []
    for kok in filter(None, kokler):
        adaylar.append(Path(kok) / "Microsoft" / "Edge" / "Application" / "msedge.exe")
    for kok in filter(None, kokler):
        adaylar.append(Path(kok) / "Google" / "Chrome" / "Application" / "chrome.exe")
    for a in adaylar:
        if a.is_file():
            return str(a)
    for ad in ("msedge", "chrome", "google-chrome", "chromium"):
        yol = shutil.which(ad)
        if yol:
            return yol
    return None


def pencere_komutu(tarayici: str, url: str, profil: Path) -> list[str]:
    return [
        tarayici, f"--app={url}", f"--user-data-dir={profil}", "--no-first-run", "--no-default-browser-check",
        # GERCEK HATA: yeni profilde Edge, uygulama penceresinin yaninda ikinci bir pencere aciyordu (edge://sync-confirmation-dialog:
        # "We are now syncing your browsing data..."); --disable-sync bunu kaldirir (gercek Edge'de olculdu: 2 pencere -> 1).
        "--disable-sync", "--disable-features=Translate,TranslateUI,msImplicitSignin", "--window-size=1320,880",
    ]


def sessiz_alt_surecler() -> None:
    """Windows'ta bu surecin actigi tum alt surecler konsol penceresi acmasin (pythonw altinda her konsol programi siyah pencere acardi)."""
    if sys.platform != "win32":
        return
    asil = subprocess.Popen.__init__

    def _init(self, *a, **k):
        k["creationflags"] = k.get("creationflags", 0) | CREATE_NO_WINDOW
        asil(self, *a, **k)

    subprocess.Popen.__init__ = _init  # type: ignore[method-assign]


def _son_klasor_yolu() -> Path:
    return ayar_dizini() / "uygulama.json"


def son_klasoru_oku() -> str | None:
    try:
        k = json.loads(_son_klasor_yolu().read_text(encoding="utf-8")).get("son_klasor")
        return str(k) if k and Path(k).is_dir() else None
    except (OSError, ValueError, AttributeError):
        return None


def son_klasoru_yaz(klasor: str | None) -> None:
    if not klasor:
        return
    try:
        ayar_dizini().mkdir(parents=True, exist_ok=True)
        _son_klasor_yolu().write_text(json.dumps({"son_klasor": str(klasor)}), encoding="utf-8")
    except OSError:
        pass


def _kutu(mesaj: str, ikon: int) -> None:
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, mesaj, "Aktapokus", ikon)
        except Exception:
            pass


def hata_goster(mesaj: str) -> None:
    """pythonw'de konsol yok: hatayi log'a yaz, Windows'ta ayrica kutuyla goster."""
    log_yaz("HATA: " + mesaj)
    _kutu(mesaj + f"\n\nAyrintilar: {log_yolu()}", 0x10)


def bilgi_goster(mesaj: str) -> None:
    log_yaz(mesaj)
    _kutu(mesaj, 0x40)


# ---- tek kopya: ikinci tiklama ayni tarayici profiline baglanip aninda kapanir ve ikinci sunucuyu da oldururdu ----
def kilit_yolu() -> Path:
    return ayar_dizini() / "uygulama.kilit"


def surec_canli_mi(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes

        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        kod = ctypes.c_ulong()
        tamam = k.GetExitCodeProcess(h, ctypes.byref(kod))
        k.CloseHandle(h)
        return bool(tamam) and kod.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def kilit_al() -> bool:
    """Baska bir Aktapokus penceresi canliysa False. Olu sureclerden kalan kilit yok sayilir."""
    yol = kilit_yolu()
    try:
        onceki = int(yol.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        onceki = None
    if onceki and onceki != os.getpid() and surec_canli_mi(onceki):
        return False
    try:
        yol.parent.mkdir(parents=True, exist_ok=True)
        yol.write_text(str(os.getpid()), encoding="utf-8")
    except OSError:
        pass
    return True


def kilit_birak() -> None:
    yol = kilit_yolu()
    try:
        if yol.read_text(encoding="utf-8").strip() == str(os.getpid()):
            yol.unlink()
    except OSError:
        pass


ACILIS_SURESI_SN = 90.0  # pencere bu surede sunucuya hic baglanmazsa vazgecilir
KOPMA_TOLERANSI_SN = 20.0  # baglanti bu kadar suredir yoksa pencere kapanmis sayilir (yenileme/kisa kopmalar tolere edilir)


def pencere_bekle(baglanti_say: Callable[[], int], bekle_sn: float, acilis_sn: float, kopma_sn: float, saat: Callable[[], float] = time.monotonic) -> str:
    """'kapandi' (en az bir kez baglandi, sonra kopma_sn boyunca baglanti yok) ya da 'baglanmadi' (acilis_sn icinde hic baglanmadi)."""
    baslangic = son = saat()
    gorulen = False
    while True:
        simdi = saat()
        if baglanti_say() > 0:
            gorulen, son = True, simdi
        elif gorulen and simdi - son > kopma_sn:
            return "kapandi"
        elif not gorulen and simdi - baslangic > acilis_sn:
            return "baglanmadi"
        time.sleep(bekle_sn)


def uygulama_calistir(
    klasor: str | None = None,
    port: int = 0,
    pencere_ac: Callable[[list[str]], "subprocess.Popen"] | None = None,
    bekle_sn: float = 0.5,
    baglanti_say: Callable[[], int] | None = None,
    acilis_sn: float = ACILIS_SURESI_SN,
    kopma_sn: float = KOPMA_TOLERANSI_SN,
) -> int:
    tarayici = tarayici_bul()
    if not tarayici:
        hata_goster("Edge ya da Chrome bulunamadi. Uygulama penceresi icin biri gerekir (AKTAPOKUS_TARAYICI ile yol verilebilir).")
        return 1
    if not kilit_al():
        bilgi_goster(f"Aktapokus zaten acik (gorev cubugunda). Pencere yoksa {kilit_yolu()} dosyasini silin.")
        return 0
    try:
        return _calistir(klasor, port, pencere_ac, bekle_sn, tarayici, baglanti_say, acilis_sn, kopma_sn)
    finally:
        kilit_birak()


def _calistir(klasor, port, pencere_ac, bekle_sn, tarayici, baglanti_say, acilis_sn, kopma_sn) -> int:
    from .arayuz import ArayuzSunucusu, Uygulama, UygulamaHatasi
    from .runners import hepsini_kapat

    sessiz_alt_surecler()
    app = Uygulama()
    sunucu = ArayuzSunucusu(app, port)
    try:
        sunucu.baslat()
    except OSError as hata:
        hata_goster(f"Arayuz sunucusu baslatilamadi: {hata}")
        return 1
    secilecek = klasor or son_klasoru_oku()
    if secilecek:
        try:
            app.klasor_sec(secilecek, git_baslat=False)
        except UygulamaHatasi as hata:
            log_yaz(f"Klasor secilemedi ({hata}); arayuzden secilebilir.")
    profil = ayar_dizini() / "uygulama-profil"
    profil.mkdir(parents=True, exist_ok=True)
    komut = pencere_komutu(tarayici, sunucu.url(), profil)
    log_yaz("baslatildi: " + komut[0])
    def sayac() -> int:
        with app.bus.kilit:
            return len(app.bus.aboneler)

    try:
        (pencere_ac or (lambda k: subprocess.Popen(k)))(komut)  # surec ID'sine/ömrüne güvenilmez (devir olabilir)
        sonuc = pencere_bekle(baglanti_say or sayac, bekle_sn, acilis_sn, kopma_sn)
        if sonuc == "baglanmadi":
            hata_goster(f"Pencere {acilis_sn:.0f} sn icinde arayuze baglanamadi. Tarayici penceresi acildiysa kapatip kisayola yeniden tiklayin.")
            return 1
        log_yaz("pencere kapandi (sayfa baglantisi koptu)")
    except KeyboardInterrupt:
        pass
    except OSError as hata:
        hata_goster(f"Pencere acilamadi: {hata}")
        return 1
    finally:
        son_klasoru_yaz(str(app.klasor) if app.klasor else None)
        sunucu.kapat()
        hepsini_kapat()
    return 0
