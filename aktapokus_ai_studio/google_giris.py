"""Google hesabi baglantisi: OAuth 2.0 masaustu akisi (PKCE + 127.0.0.1 geri donusu). Yalniz standart kutuphane; ek kurulum yok.

Guvenlik tasarimi (coklu kullanici icin):
- Her kullanici KENDI Windows hesabinda, kendi Google hesabiyla girer; anahtarlar o kullanicinin profilinde (~/.aktapokus/google-token.json) durur.
- Yenileme anahtari (refresh token) ve istemci sirri Windows DPAPI ile sifrelenir (yalniz ayni Windows kullanicisi acabilir). Windows disinda anahtar SAKLANMAZ
  (giris yapilamaz; acik metin dosya yazilmaz).
- Anahtarlar arayuze/API yanitina/gunluge ASLA verilmez: durum yalniz {bagli, eposta, baglayicilar}.
- PKCE (S256) + rastgele `state` (sabit sureli karsilastirma) + tek kullanimlik, 5 dk omurlu, yalniz 127.0.0.1 uzerinde dinleyen gecici sunucu.
- Izinler en az ayricalikla ve baglayici basina ayri istenir (yalniz OKUMA: gmail.readonly, calendar.readonly, drive.readonly). Yazma/silme izni istenmez.
- Cikista Google'a iptal istegi gonderilir ve yerel kayit silinir.
- Bu modul uzak (Tailscale) isteklerle yonetilmez (uzak.py/arayuz.py reddeder)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import http.server
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

YETKI_ADRESI = "https://accounts.google.com/o/oauth2/v2/auth"
BELIRTEC_ADRESI = "https://oauth2.googleapis.com/token"
IPTAL_ADRESI = "https://oauth2.googleapis.com/revoke"
TEMEL_IZINLER = ("openid", "email")
BAGLAYICILAR = {  # baglayici -> yalniz OKUMA izni
    "gmail": "https://www.googleapis.com/auth/gmail.readonly",
    "takvim": "https://www.googleapis.com/auth/calendar.readonly",
    "drive": "https://www.googleapis.com/auth/drive.readonly",
}
AKIS_OMRU_SN = 300
GERI_YOLU = "/oauth2callback"
ISTEMCI_DESENI_SON_EK = ".apps.googleusercontent.com"


class GoogleHatasi(Exception):
    pass


def ayar_yolu() -> Path:
    ortam = os.environ.get("AKTAPOKUS_GOOGLE_AYAR")
    return Path(ortam) if ortam else Path.home() / ".aktapokus" / "google-token.json"


def istemci_dosya_yolu() -> Path:
    ortam = os.environ.get("AKTAPOKUS_GOOGLE_ISTEMCI_DOSYASI")
    return Path(ortam) if ortam else Path.home() / ".aktapokus" / "google-istemci.json"


def istemci_dosyasi_oku() -> tuple[str, str | None] | None:
    """Google Cloud'dan indirilen client JSON ({"installed"|"web": {client_id, client_secret}}) ya da duz {client_id, client_secret}. Yoksa/bozuksa None."""
    try:
        veri = json.loads(istemci_dosya_yolu().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if isinstance(veri, dict):
        veri = veri.get("installed") or veri.get("web") or veri
    if not isinstance(veri, dict):
        return None
    kimlik, sir = veri.get("client_id"), veri.get("client_secret")
    if not isinstance(kimlik, str) or not kimlik.strip().endswith(ISTEMCI_DESENI_SON_EK) or not 20 <= len(kimlik.strip()) <= 200:
        return None
    return kimlik.strip(), (sir if isinstance(sir, str) and 0 < len(sir) <= 200 else None)


# ---- anahtar koruma (Windows DPAPI) -----------------------------------------------------------------------------------------
_ENTROPI = b"aktapokus-ai-studio/google/v1"


def _dpapi(veri: bytes, koru: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def blob(b: bytes) -> Blob:
        tampon = ctypes.create_string_buffer(b, len(b))
        return Blob(len(b), ctypes.cast(tampon, ctypes.POINTER(ctypes.c_char))), tampon

    girdi, t1 = blob(veri)
    entropi, t2 = blob(_ENTROPI)
    cikti = Blob()
    crypt32 = ctypes.windll.crypt32
    f = crypt32.CryptProtectData if koru else crypt32.CryptUnprotectData
    if not f(ctypes.byref(girdi), None, ctypes.byref(entropi), None, None, 0x1, ctypes.byref(cikti)):  # 0x1: arayuz gosterme
        raise GoogleHatasi("Anahtar korunamadi/acilamadi (Windows DPAPI)")
    try:
        return ctypes.string_at(cikti.pbData, cikti.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(cikti.pbData)


def _koru(veri: bytes) -> str:
    if os.name != "nt":
        raise GoogleHatasi("Google anahtarlari yalniz Windows'ta (DPAPI ile sifrelenerek) saklanir; bu sistemde giris desteklenmiyor")
    return base64.b64encode(_dpapi(veri, True)).decode("ascii")


def _ac(metin: str) -> bytes:
    if os.name != "nt":
        raise GoogleHatasi("Google anahtarlari yalniz Windows'ta saklanir")
    return _dpapi(base64.b64decode(metin.encode("ascii")), False)


# ---- yardimcilar -------------------------------------------------------------------------------------------------------------
def pkce_olustur() -> tuple[str, str]:
    """(dogrulayici, S256 sinama). RFC 7636: challenge = BASE64URL(SHA256(verifier)), dolgusuz."""
    dogrulayici = secrets.token_urlsafe(64)
    return dogrulayici, sinama_hesapla(dogrulayici)


def sinama_hesapla(dogrulayici: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(dogrulayici.encode("ascii")).digest()).rstrip(b"=").decode("ascii")


def _form_gonder(adres: str, alanlar: dict) -> dict:
    istek = urllib.request.Request(adres, data=urllib.parse.urlencode(alanlar).encode("utf-8"), method="POST",
                                   headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(istek, timeout=15) as y:  # varsayilan baglam: TLS sertifikasi dogrulanir
            govde = y.read(200_000)
    except urllib.error.HTTPError as h:
        try:
            veri = json.loads(h.read(20_000).decode("utf-8", "replace"))
            neden = str(veri.get("error_description") or veri.get("error") or h.code)[:150]
        except (ValueError, OSError):
            neden = str(h.code)
        raise GoogleHatasi(f"Google istegi reddetti: {neden}") from None
    except (urllib.error.URLError, OSError, TimeoutError) as h:
        raise GoogleHatasi(f"Google'a ulasilamadi: {getattr(h, 'reason', h)}"[:200]) from None
    try:
        veri = json.loads(govde.decode("utf-8")) if govde else {}
    except ValueError:
        raise GoogleHatasi("Google yaniti anlasilamadi") from None
    return veri if isinstance(veri, dict) else {}


def _kimlik_eposta(kimlik_belirteci: object) -> str | None:
    """id_token dogrudan Google'dan TLS ile alinir (belirtec ucundan); yuku okunur, e-posta bicimi dogrulanir."""
    if not isinstance(kimlik_belirteci, str) or kimlik_belirteci.count(".") != 2:
        return None
    try:
        yuk = kimlik_belirteci.split(".")[1]
        veri = json.loads(base64.urlsafe_b64decode(yuk + "=" * (-len(yuk) % 4)).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    eposta = veri.get("email") if isinstance(veri, dict) else None
    return eposta if isinstance(eposta, str) and "@" in eposta and len(eposta) <= 200 else None


def _izin_adlari(kapsam: str) -> list[str]:
    """Google'in verdigi kapsam metninden baglayici adlari."""
    verilen = set(kapsam.split())
    return sorted(ad for ad, izin in BAGLAYICILAR.items() if izin in verilen)


class _Akis:
    def __init__(self, dogrulayici: str, state: str, geri_adresi: str, sunucu, bitis: float):
        self.dogrulayici, self.state, self.geri_adresi, self.sunucu, self.bitis = dogrulayici, state, geri_adresi, sunucu, bitis


class Yonetici:
    def __init__(self):
        self._kilit = threading.RLock()
        self._akis: _Akis | None = None
        self._hata: str | None = None
        self._erisim: tuple[str, float] | None = None  # (belirtec, bitis) yalniz bellekte

    # -- kayit dosyasi ------------------------------------------------------------------------------------------------------
    def _oku(self) -> dict:
        try:
            veri = json.loads(ayar_yolu().read_text(encoding="utf-8"))
            return veri if isinstance(veri, dict) else {}
        except (OSError, ValueError):
            return {}

    def _yaz(self, veri: dict) -> None:
        yol = ayar_yolu()
        yol.parent.mkdir(parents=True, exist_ok=True)
        gecici = yol.with_suffix(".tmp")
        gecici.write_text(json.dumps(veri), encoding="utf-8")
        try:
            os.chmod(gecici, 0o600)  # en iyi caba (Windows'ta kisitli; asil koruma DPAPI)
        except OSError:
            pass
        os.replace(gecici, yol)

    # -- istemci kimligi ----------------------------------------------------------------------------------------------------
    def istemci_kaydet(self, istemci_id: object, sir: object) -> None:
        if not isinstance(istemci_id, str) or not istemci_id.strip().endswith(ISTEMCI_DESENI_SON_EK) or not 20 <= len(istemci_id.strip()) <= 200:
            raise GoogleHatasi("Istemci kimligi '...apps.googleusercontent.com' ile bitmeli (Google Cloud > Credentials > Desktop app)")
        if sir is not None and (not isinstance(sir, str) or len(sir) > 200):
            raise GoogleHatasi("Istemci sirri gecersiz")
        veri = self._oku()
        veri["istemci"] = {"id": istemci_id.strip(), "sir": _koru(sir.encode("utf-8")) if sir else None}
        self._yaz(veri)

    def _istemci(self) -> tuple[str, str | None]:
        dosya = istemci_dosyasi_oku()
        if dosya:  # kullanicinin kendi koydugu client JSON her seyden once gelir
            return dosya
        ist = self._oku().get("istemci") or {}
        kimlik = os.environ.get("AKTAPOKUS_GOOGLE_ISTEMCI_ID") or ist.get("id")
        if not isinstance(kimlik, str) or not kimlik:
            raise GoogleHatasi("Once Google istemci kimligini girin")
        sir = ist.get("sir")
        return kimlik, (_ac(sir).decode("utf-8") if isinstance(sir, str) and sir else None)

    # -- durum --------------------------------------------------------------------------------------------------------------
    def durum(self) -> dict:
        """Yalniz gosterilebilir bilgi: anahtar/sir ASLA dondurulmez."""
        veri = self._oku()
        hesap = veri.get("hesap") or {}
        with self._kilit:
            bekliyor = self._akis is not None and time.time() < self._akis.bitis
            hata = self._hata
        return {"istemci_var": bool(istemci_dosyasi_oku() or os.environ.get("AKTAPOKUS_GOOGLE_ISTEMCI_ID") or (veri.get("istemci") or {}).get("id")),
                "bagli": bool(hesap.get("yenileme")), "eposta": hesap.get("eposta"), "baglayicilar": list(hesap.get("baglayicilar") or []),
                "bekliyor": bekliyor, "hata": hata}

    # -- giris akisi --------------------------------------------------------------------------------------------------------
    def baglan(self, baglayici: object) -> str:
        """Tarayicida acilacak Google adresini dondurur; geri donusu 127.0.0.1'deki gecici sunucu karsilar."""
        if baglayici not in ("hesap", "hepsi") and baglayici not in BAGLAYICILAR:
            raise GoogleHatasi("Bilinmeyen baglayici")
        kimlik, _sir = self._istemci()
        with self._kilit:
            self._akisi_kapat()
            self._hata = None
            sunucu = http.server.HTTPServer(("127.0.0.1", 0), _geri_isleyici_sinifi(self))
            sunucu.timeout = 1
            geri_adresi = f"http://127.0.0.1:{sunucu.server_port}{GERI_YOLU}"
            dogrulayici, sinama = pkce_olustur()
            state = secrets.token_urlsafe(32)
            self._akis = _Akis(dogrulayici, state, geri_adresi, sunucu, time.time() + AKIS_OMRU_SN)
            threading.Thread(target=self._sun, args=(sunucu, self._akis), daemon=True).start()
            izinler = list(TEMEL_IZINLER) + [BAGLAYICILAR[b] for b in (self._oku().get("hesap") or {}).get("baglayicilar", []) if b in BAGLAYICILAR]
            if baglayici == "hepsi":  # tek giriste uc servis: yalniz OKUMA izinleri
                izinler += [i for i in BAGLAYICILAR.values() if i not in izinler]
            elif baglayici in BAGLAYICILAR and BAGLAYICILAR[baglayici] not in izinler:
                izinler.append(BAGLAYICILAR[baglayici])
            sorgu = urllib.parse.urlencode({"client_id": kimlik, "redirect_uri": geri_adresi, "response_type": "code", "scope": " ".join(izinler),
                                            "code_challenge": sinama, "code_challenge_method": "S256", "state": state,
                                            "access_type": "offline", "prompt": "consent"})
            return f"{YETKI_ADRESI}?{sorgu}"

    def _sun(self, sunucu, akis: _Akis) -> None:
        try:
            while time.time() < akis.bitis:
                with self._kilit:
                    if self._akis is not akis:
                        break
                sunucu.handle_request()
        finally:
            sunucu.server_close()
            with self._kilit:
                if self._akis is akis:
                    self._akis = None

    def _akisi_kapat(self) -> None:
        with self._kilit:
            self._akis = None  # sunucu dongusu bunu gorup kapanir

    def geri_donus(self, host: str, yol_sorgu: str, port: int) -> tuple[int, str]:
        """Gecici sunucunun tek GET isleyicisi: (HTTP kodu, HTML)."""
        if host != f"127.0.0.1:{port}":
            return 400, _sayfa("Gecersiz istek")
        u = urllib.parse.urlsplit(yol_sorgu)
        if u.path != GERI_YOLU:
            return 404, _sayfa("Bulunamadi")
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        with self._kilit:
            akis = self._akis
            if akis is None or time.time() >= akis.bitis:
                return 410, _sayfa("Bu giris istegi suresi doldu; uygulamadan yeniden baslatin")
            if not hmac.compare_digest(q.get("state", ""), akis.state):
                return 400, _sayfa("Gecersiz dogrulama kodu")  # akisi TUKETMEZ: sahte istek gercek girisi bozamaz
            self._akis = None  # tek kullanimlik
        if q.get("error"):
            self._hata = "Google girisi reddedildi ya da iptal edildi"
            return 400, _sayfa("Giris tamamlanmadi. Bu pencereyi kapatabilirsiniz.")
        kod = q.get("code")
        if not kod:
            self._hata = "Google'dan kod gelmedi"
            return 400, _sayfa("Giris tamamlanmadi")
        try:
            self._kodu_degistir(kod, akis)
        except GoogleHatasi as h:
            self._hata = str(h)
            return 400, _sayfa("Giris tamamlanamadi. Uygulamaya donup hata mesajina bakin.")
        return 200, _sayfa("Google hesabi baglandi. Bu pencereyi kapatip uygulamaya donebilirsiniz.")

    def _kodu_degistir(self, kod: str, akis: _Akis) -> None:
        kimlik, sir = self._istemci()
        alanlar = {"code": kod, "client_id": kimlik, "code_verifier": akis.dogrulayici, "redirect_uri": akis.geri_adresi, "grant_type": "authorization_code"}
        if sir:
            alanlar["client_secret"] = sir
        yanit = _form_gonder(BELIRTEC_ADRESI, alanlar)
        yenileme = yanit.get("refresh_token")
        if not isinstance(yenileme, str) or not yenileme:
            raise GoogleHatasi("Google yenileme anahtari vermedi; baglantiyi yeniden kurun")
        veri = self._oku()
        eski = veri.get("hesap") or {}
        eposta = _kimlik_eposta(yanit.get("id_token")) or eski.get("eposta")
        veri["hesap"] = {"eposta": eposta, "baglayicilar": _izin_adlari(str(yanit.get("scope") or "")), "yenileme": _koru(yenileme.encode("utf-8"))}
        self._yaz(veri)
        with self._kilit:
            self._erisim = None
            self._hata = None

    # -- kullanim (dahili; API'den DISARI verilmez) ---------------------------------------------------------------------------
    def erisim_belirteci(self) -> str:
        """Kisa omurlu erisim belirteci (bellekte). Yalniz sunucu tarafi baglayicilar kullanir; HTTP yanitina konmaz."""
        with self._kilit:
            if self._erisim and time.time() < self._erisim[1] - 60:
                return self._erisim[0]
        hesap = self._oku().get("hesap") or {}
        if not hesap.get("yenileme"):
            raise GoogleHatasi("Google hesabi bagli degil")
        kimlik, sir = self._istemci()
        alanlar = {"client_id": kimlik, "refresh_token": _ac(hesap["yenileme"]).decode("utf-8"), "grant_type": "refresh_token"}
        if sir:
            alanlar["client_secret"] = sir
        yanit = _form_gonder(BELIRTEC_ADRESI, alanlar)
        belirtec = yanit.get("access_token")
        if not isinstance(belirtec, str) or not belirtec:
            raise GoogleHatasi("Erisim belirteci alinamadi; baglantiyi yeniden kurun")
        sure = yanit.get("expires_in")
        with self._kilit:
            self._erisim = (belirtec, time.time() + (sure if isinstance(sure, (int, float)) and sure > 0 else 300))
        return belirtec

    def cikis(self) -> None:
        """Google'a iptal istegi (en iyi caba) + yerel kaydi sil."""
        self._akisi_kapat()
        veri = self._oku()
        hesap = veri.pop("hesap", None) or {}
        self._yaz(veri)
        with self._kilit:
            self._erisim = None
            self._hata = None
        if hesap.get("yenileme"):
            try:
                _form_gonder(IPTAL_ADRESI, {"token": _ac(hesap["yenileme"]).decode("utf-8")})
            except GoogleHatasi:
                pass  # yerel kayit zaten silindi; Google tarafinda hesap ayarlarindan da kaldirilabilir


def _sayfa(mesaj: str) -> str:
    return ("<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Aktapokus</title>"
            f"<body style='font:16px system-ui;max-width:480px;margin:15vh auto;padding:0 16px'><p>{html.escape(mesaj)}</p></body>")


def _geri_isleyici_sinifi(yonetici: Yonetici):
    class Isleyici(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):  # kod/state gunluge dusmesin
            pass

        def do_GET(self):
            kod, sayfa = yonetici.geri_donus(self.headers.get("Host", ""), self.path, self.server.server_port)
            govde = sayfa.encode("utf-8")
            self.send_response(kod)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(govde)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(govde)

    return Isleyici
