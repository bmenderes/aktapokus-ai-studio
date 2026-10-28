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


def pencere_yolu() -> Path:
    return ayar_dizini() / "uygulama.pencere"


def pencere_isaretle(durum: str | None) -> None:
    """Calisan kopyanin pencere durumu: 'aciliyor' | 'bagli' | 'kopuk' (pencere kapandi, kapanma toleransi sayiliyor). None: dosyayi siler."""
    yol = pencere_yolu()
    try:
        if durum is None:
            yol.unlink(missing_ok=True)
        else:
            yol.parent.mkdir(parents=True, exist_ok=True)
            yol.write_text(durum, encoding="utf-8")
    except OSError:
        pass


def devral_yolu() -> Path:
    return ayar_dizini() / "uygulama.devral"


def devral_iste() -> None:
    """Yeni acma istegi: pencere zaten kopuksa eski kopya kopma toleransini (20 sn) beklemeden hemen kapanir."""
    try:
        devral_yolu().parent.mkdir(parents=True, exist_ok=True)
        devral_yolu().write_text("1", encoding="utf-8")
    except OSError:
        pass


def devral_var_mi() -> bool:
    return devral_yolu().exists()


def devral_temizle() -> None:
    try:
        devral_yolu().unlink(missing_ok=True)
    except OSError:
        pass


def pencere_durumu() -> str | None:
    try:
        return pencere_yolu().read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def kapaniyor_mu() -> bool:
    return pencere_durumu() == "kopuk"


def mevcut_pencereyi_one_getir() -> bool:
    """Acik Aktapokus uygulama penceresini (Edge/Chrome 'Aktapokus' basligi) one getirir; bulunursa True. Yalniz Windows."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        u = ctypes.windll.user32
        bulunan: list[int] = []
        islev_tipi = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def bak(hwnd, _):
            if u.IsWindowVisible(hwnd):
                uzunluk = u.GetWindowTextLengthW(hwnd)
                if uzunluk:
                    baslik = ctypes.create_unicode_buffer(uzunluk + 1)
                    u.GetWindowTextW(hwnd, baslik, uzunluk + 1)
                    sinif = ctypes.create_unicode_buffer(64)
                    u.GetClassNameW(hwnd, sinif, 64)
                    if sinif.value.startswith("Chrome_WidgetWin") and baslik.value.startswith("Aktapokus"):
                        bulunan.append(hwnd)
            return True

        u.EnumWindows(islev_tipi(bak), 0)
        if not bulunan:
            return False
        u.ShowWindow(bulunan[0], 9)  # SW_RESTORE (simge durumundaysa)
        u.SetForegroundWindow(bulunan[0])
        return True
    except Exception:
        return False


KAPANMA_BEKLEME_SN = 30.0  # pencere kapaninca uygulama kopma toleransi (20 sn) kadar daha acik kalir; hemen yeniden acma bunu bekler


def ikinci_kopya_bekle(azami_sn: float | None = None, saat: Callable[[], float] = time.monotonic, uyku: Callable[[float], None] = time.sleep) -> str:
    """Kilit baska bir kopyadaysa: 'al' (kilit alindi, devam), 'one' (acik pencere one getirildi) ya da 'mesaj' (azami sure doldu).

    GERCEK HATA (gercek Edge ile yeniden uretildi): pencere kapaninca Edge baglantiyi birkac sn sonra birakir; o aralikta eski kopya
    'pencere acik' sanir ve hemen yeniden acma 'zaten acik' kutusunda takiliyordu. Durum dosyasina GUVENILMEZ: asil olcut GERCEK pencere.
    Pencere varsa one getirilir; yoksa (kapaniyor ya da henuz aciliyor) kilit alinana ya da pencere belirene kadar beklenir."""
    if kilit_al():
        return "al"
    bitis = saat() + (KAPANMA_BEKLEME_SN if azami_sn is None else azami_sn)
    while saat() < bitis:
        if mevcut_pencereyi_one_getir():
            devral_temizle()
            return "one"
        if pencere_durumu() == "kopuk":
            devral_iste()  # eski kopya pencere kopukken kopma toleransini beklemeden kapanir
        uyku(0.5)
        if kilit_al():
            devral_temizle()
            return "al"
    devral_temizle()
    return "mesaj"


def kilit_birak() -> None:
    yol = kilit_yolu()
    try:
        if yol.read_text(encoding="utf-8").strip() == str(os.getpid()):
            yol.unlink()
    except OSError:
        pass


ACILIS_SURESI_SN = 90.0  # pencere bu surede sunucuya hic baglanmazsa vazgecilir
KOPMA_TOLERANSI_SN = 20.0  # baglanti bu kadar suredir yoksa pencere kapanmis sayilir (yenileme/kisa kopmalar tolere edilir)


def pencere_bekle(baglanti_say: Callable[[], int], bekle_sn: float, acilis_sn: float, kopma_sn: float, saat: Callable[[], float] = time.monotonic, erken_cik: Callable[[], bool] | None = None) -> str:
    """'kapandi' (en az bir kez baglandi, sonra kopma_sn boyunca baglanti yok) ya da 'baglanmadi' (acilis_sn icinde hic baglanmadi)."""
    baslangic = son = saat()
    gorulen = False
    while True:
        simdi = saat()
        if baglanti_say() > 0:
            gorulen, son = True, simdi
        elif gorulen and (simdi - son > kopma_sn or (erken_cik is not None and erken_cik())):  # erken_cik: yeni acma istegi geldi, pencere zaten kopuk
            return "kapandi"
        elif not gorulen and simdi - baslangic > acilis_sn:
            return "baglanmadi"
        time.sleep(bekle_sn)


# ---- Penceresiz ARKA PLAN modu (`ui --arka-plan`): sunucu pencere olmadan calisir (telefon/Telegram/zamanlayici icin); pencere kapaninca KAPANMAZ ----
def arkaplan_yolu() -> Path:
    return ayar_dizini() / "uygulama.arkaplan"


def pencere_iste_yolu() -> Path:
    return ayar_dizini() / "uygulama.pencere-iste"


def dur_yolu() -> Path:
    return ayar_dizini() / "uygulama.dur"


def _isaret(yol: Path, icerik: str = "1") -> None:
    try:
        yol.parent.mkdir(parents=True, exist_ok=True)
        yol.write_text(icerik, encoding="utf-8")
    except OSError:
        pass


def arka_plan_pid() -> int | None:
    """Penceresiz arka plan kopyasi calisiyorsa surec kimligi (olu surecten kalan dosya yok sayilir)."""
    try:
        pid = int(arkaplan_yolu().read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    return pid if pid > 0 and surec_canli_mi(pid) else None


def arka_plan_pencere_iste(bekle_sn: float = 15.0, saat: Callable[[], float] = time.monotonic, uyku: Callable[[float], None] = time.sleep) -> bool:
    """Arka plandaki kopyadan bir pencere acmasini ister. Baglanti anahtari diske YAZILMAZ: pencereyi sunucuyu calistiran surec acar. Istek tuketilince True."""
    _isaret(pencere_iste_yolu())
    bitis = saat() + bekle_sn
    while saat() < bitis:
        if not pencere_iste_yolu().exists():
            return True
        uyku(0.3)
    return False


def durdur(bekle_sn: float = 20.0, saat: Callable[[], float] = time.monotonic, uyku: Callable[[float], None] = time.sleep) -> bool:
    """Arka plandaki kopyayi nazikce kapatir (dur isareti). Calisan kopya yoksa False; kapandiysa True."""
    pid = arka_plan_pid()
    if pid is None:
        return False
    _isaret(dur_yolu())
    bitis = saat() + bekle_sn
    while saat() < bitis:
        if arka_plan_pid() is None:
            return True
        uyku(0.3)
    return False


def arka_plan_calistir(klasor: str | None = None, port: int = 0, pencere_ac: Callable[[list[str]], "subprocess.Popen"] | None = None, bekle_sn: float = 1.0) -> int:
    if arka_plan_pid() is not None:
        return 0  # zaten arka planda calisiyor: ikinci kopya baslatilmaz
    if not kilit_al():
        log_yaz("arka plan baslatilmadi: pencere kopyasi acik")
        return 0
    try:
        return _arka_plan(klasor, port, pencere_ac, bekle_sn)
    finally:
        kilit_birak()


def _arka_plan(klasor, port, pencere_ac, bekle_sn) -> int:
    from .arayuz import ArayuzSunucusu, Uygulama, UygulamaHatasi
    from .runners import hepsini_kapat

    sessiz_alt_surecler()
    app = Uygulama()
    app._telegram().otomatik_baslat()
    sunucu = ArayuzSunucusu(app, port)
    try:
        sunucu.baslat()
        sunucu.zamanlayici_baslat()
        try:
            sunucu.uzak_uygula()
        except Exception:
            pass
    except OSError as hata:
        hata_goster(f"Arayuz sunucusu baslatilamadi: {hata}")
        return 1
    secilecek = klasor or son_klasoru_oku()
    if secilecek:
        try:
            app.klasor_sec(secilecek, git_baslat=False)
        except UygulamaHatasi as hata:
            log_yaz(f"Klasor secilemedi ({hata}); arayuzden secilebilir.")
    for eski in (dur_yolu(), pencere_iste_yolu()):
        try:
            eski.unlink(missing_ok=True)
        except OSError:
            pass
    _isaret(arkaplan_yolu(), str(os.getpid()))
    log_yaz("arka plan: baslatildi (pencere yok)")
    profil = ayar_dizini() / "uygulama-profil"

    def pencere_ac_simdi() -> None:
        if mevcut_pencereyi_one_getir():
            return
        tarayici = tarayici_bul()
        if not tarayici:
            log_yaz("arka plan: Edge/Chrome bulunamadi, pencere acilamadi")
            return
        profil.mkdir(parents=True, exist_ok=True)
        (pencere_ac or (lambda k: subprocess.Popen(k)))(pencere_komutu(tarayici, sunucu.url(), profil))
        log_yaz("arka plan: pencere acildi (istek uzerine)")

    try:
        while not dur_yolu().exists():
            if pencere_iste_yolu().exists():
                try:
                    pencere_iste_yolu().unlink(missing_ok=True)  # once tuket: ayni istek tekrar islenmesin
                except OSError:
                    pass
                try:
                    pencere_ac_simdi()
                except OSError as hata:
                    log_yaz(f"arka plan: pencere acilamadi: {hata}")
            time.sleep(bekle_sn)
        log_yaz("arka plan: durduruldu")
    except KeyboardInterrupt:
        pass
    finally:
        try:
            if arkaplan_yolu().read_text(encoding="utf-8").strip() == str(os.getpid()):
                arkaplan_yolu().unlink()
            dur_yolu().unlink(missing_ok=True)
        except OSError:
            pass
        son_klasoru_yaz(str(app.klasor) if app.klasor else None)
        sunucu.kapat()
        hepsini_kapat()
    return 0


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
    if arka_plan_pid() is not None:  # penceresiz arka plan kopyasi calisiyor (acilista baslatildi): pencereyi o acar/one getirir; ikinci sunucu baslatilmaz
        if not mevcut_pencereyi_one_getir() and not arka_plan_pencere_iste():
            bilgi_goster("Aktapokus arka planda calisiyor ama pencere acilamadi. Biraz sonra yeniden deneyin.")
        return 0
    ikinci = ikinci_kopya_bekle()
    if ikinci == "one":
        return 0  # acik pencere one getirildi (kutu gosterilmez)
    if ikinci == "mesaj":
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
    app._telegram().otomatik_baslat()  # Ayarlar > Telegram'da 'otomatik baslat' aciksa ve token varsa bot arka planda baslar
    sunucu = ArayuzSunucusu(app, port)
    try:
        sunucu.baslat()
        sunucu.zamanlayici_baslat()
        try:
            sunucu.uzak_uygula()  # Ayarlar > Uzak erisim aciksa Tailscale dinleyicisi (varsayilan kapali); hata pencere acilisini engellemez
        except Exception:
            pass
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
        return app.bus.tarayici_sayisi()  # Telegram botu gibi dahili aboneler sayilmaz: yoksa pencere kapansa da uygulama kapanmaz

    gorulen = {"pencere": False, "durum": None}

    def izle() -> int:
        n = (baglanti_say or sayac)()
        gorulen["pencere"] = gorulen["pencere"] or n > 0
        if n > 0:
            devral_temizle()  # pencere geri geldi (yenileme): eski devral istegi gecersiz
        durum = "bagli" if n > 0 else ("kopuk" if gorulen["pencere"] else "aciliyor")
        if durum != gorulen["durum"]:
            gorulen["durum"] = durum
            pencere_isaretle(durum)
        return n

    try:
        (pencere_ac or (lambda k: subprocess.Popen(k)))(komut)  # surec ID'sine/ömrüne güvenilmez (devir olabilir)
        sonuc = pencere_bekle(izle, bekle_sn, acilis_sn, kopma_sn, erken_cik=devral_var_mi)
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
        pencere_isaretle(None)
        devral_temizle()
        son_klasoru_yaz(str(app.klasor) if app.klasor else None)
        sunucu.kapat()
        hepsini_kapat()
    return 0
