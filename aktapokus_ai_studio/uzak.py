"""Uzak erisim (telefondan/baska bilgisayardan): Tailscale ozel agi uzerinden, ACIK-KAPALI bir secenek olarak. Varsayilan KAPALI.

Guvenlik modeli:
- Uzak istekler AYRI bir dinleyiciye gelir; bu dinleyici yalniz Tailscale adresine (100.64.0.0/10) -test icin loopback- baglanir, ASLA 0.0.0.0'a.
  Sade LAN adresleri reddedilir (HTTP, sifresiz: belirtec ag dinleyicisine gorunurdu). Tailscale trafigi zaten WireGuard ile sifrelidir.
- Host/Origin yalniz bu dinleyicinin adreslerinden (Tailscale IP'si ve MagicDNS adi) kabul edilir (DNS-rebinding korumasi).
- Kimlik: CIHAZ BASINA ayri anahtar (ad, olusturma, son kullanim zamani/IP, son kullanma tarihi; varsayilan 90 gun) ya da yerel belirtec.
  Diskte yalniz anahtarin SHA-256 ozeti (DPAPI ile) saklanir; anahtar yalniz eklendiginde, YEREL arayuzde BIR KEZ gosterilir.
  Iptal edilen/suresi dolan anahtar aninda (acik akislar dahil) reddedilir; reddedilmeler uzak-erisim.log dosyasina yazilir (anahtarin kendisi asla).
- YETKI DARALTMA: uzak istemci gorev verebilir/onaylayabilir, dosya/fark/Git gorebilir; ama varsayilan olarak su islemler UZAKTAN YAPILAMAZ: terminal,
  CLI/MCP/saglayici/Telegram/beceri TANIMLAMA (bilgisayarda program calistirmak demektir), kayitsiz klasor acma, klasor gezme, depo klonlama.
  `terminal` ve `yonetim` anahtarlari bilerek ve ayri ayri acilir; uzak erisim ayarlarinin KENDISI hicbir kosulda uzaktan degistirilemez."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

AYAR_ORTAMI = "AKTAPOKUS_UZAK"
TAILSCALE_ORTAMI = "AKTAPOKUS_TAILSCALE"
VARSAYILAN_PORT = 47650
TAILSCALE_AGI = ipaddress.ip_network("100.64.0.0/10")
VARSAYILAN_GUN = 90  # yeni cihaz anahtarinin varsayilan omru
AZAMI_CIHAZ = 20
ESKI_CIHAZ_ADI = "eski cihaz"  # tek anahtarli surumden tasinan anahtar
from . import gizli

_KILIT = threading.RLock()  # ayar dosyasini oku-degistir-yaz islemleri (arayuz + uzak istek iplikleri) birbirini ezmesin


class UzakHatasi(Exception):
    pass


@dataclass
class Ayar:
    acik: bool = False
    port: int = VARSAYILAN_PORT
    terminal: bool = False  # uzaktan terminal (TAM komut calistirma): ayri ve bilincli acilir
    yonetim: bool = False  # uzaktan CLI/MCP/saglayici/Telegram/beceri tanimlama, klasor gezme, klonlama
    uyanik: bool = False  # uzak erisim ACIKKEN bilgisayar uyumasin (uyanik.py; Windows). Varsayilan kapali
    https: bool = False  # Tailscale `serve` ile https://<ad>.ts.net (ana ekrana uygulama olarak eklemek icin); dinleyici yine yalniz Tailscale adresinde
    kok: str = ""  # uzaktan secilebilen/gezilebilen klasor kokunun en ustu; bos: acik projenin ust klasoru (proje yoksa ev)
    cihazlar: list = field(default_factory=list)  # list[Cihaz]; bossa hicbir uzak anahtar gecmez

    def sozluk(self) -> dict:
        """API/arayuz icin: anahtar ozetleri DAHIL DEGIL."""
        d = {k: getattr(self, k) for k in ("acik", "port", "terminal", "yonetim", "uyanik", "https", "kok")}
        d["cihazlar"] = [c.disari() for c in self.cihazlar]
        return d


@dataclass
class Cihaz:
    kimlik: str  # 8 onaltilik karakter; gizli degil (iptal icin)
    ad: str
    ozet: str  # anahtarin SHA-256 ozeti (onaltilik); anahtarin kendisi saklanmaz
    olusturma: float
    bitis: float | None = None  # None: suresiz
    son_zaman: float | None = None
    son_ip: str | None = None

    def suresi_doldu(self, simdi: float | None = None) -> bool:
        return self.bitis is not None and (time.time() if simdi is None else simdi) >= self.bitis

    def disari(self) -> dict:
        return {"kimlik": self.kimlik, "ad": self.ad, "olusturma": self.olusturma, "bitis": self.bitis, "son_zaman": self.son_zaman,
                "son_ip": self.son_ip, "suresi_doldu": self.suresi_doldu()}

    def disk(self) -> dict:
        return {"kimlik": self.kimlik, "ad": self.ad, "ozet": gizli.koru(self.ozet), "olusturma": self.olusturma, "bitis": self.bitis,
                "son_zaman": self.son_zaman, "son_ip": self.son_ip}


def ozet(anahtar: str | bytes) -> str:
    """Anahtarlar 256 bit rastgeledir: tuzsuz SHA-256 yeterli (kaba kuvvetle tersine cevrilemez)."""
    return hashlib.sha256(anahtar.encode("utf-8") if isinstance(anahtar, str) else anahtar).hexdigest()


def _sayi(v: object) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0 else None


def _cihaz_oku(h: object) -> Cihaz | None:
    if not isinstance(h, dict):
        return None
    oz = gizli.ac(h.get("ozet"))
    kimlik, ad = h.get("kimlik"), h.get("ad")
    if not (isinstance(oz, str) and re.fullmatch(r"[0-9a-f]{64}", oz) and isinstance(kimlik, str) and re.fullmatch(r"[0-9a-f]{8}", kimlik)
            and isinstance(ad, str) and ad.strip() and _sayi(h.get("olusturma")) is not None):
        return None  # acilamayan (baska kullanici/makine) ya da bozuk kayit: bu cihaz gecmez
    ip = h.get("son_ip")
    return Cihaz(kimlik=kimlik, ad=ad[:40], ozet=oz, olusturma=_sayi(h["olusturma"]), bitis=_sayi(h.get("bitis")), son_zaman=_sayi(h.get("son_zaman")),
                 son_ip=ip if isinstance(ip, str) and len(ip) <= 64 else None)


def dosya_yolu() -> Path:
    ortam = os.environ.get(AYAR_ORTAMI)
    return Path(ortam) if ortam else Path.home() / ".aktapokus" / "uzak-erisim.json"


def port_gecerli(port: object) -> bool:
    return isinstance(port, int) and not isinstance(port, bool) and 1024 <= port <= 65535


def oku() -> Ayar:
    """Ayar dosyasi yoksa/bozuksa KAPALI varsayilan (cihazsiz: hicbir uzak anahtar gecmez) doner.
    GECIS: tek anahtarli eski dosyadaki `anahtar`, ozeti alinarak 'eski cihaz' olarak listeye tasinir ve dosyadan silinir (bagli telefon kopmaz;
    diger cihazlar gibi 90 gun sonra suresi dolar)."""
    with _KILIT:
        try:
            h = json.loads(dosya_yolu().read_text(encoding="utf-8"))
            if not isinstance(h, dict):
                raise ValueError
            ham = h.get("cihazlar")
            cihazlar = [c for c in (_cihaz_oku(x) for x in ham) if c] if isinstance(ham, list) else []
            ayar = Ayar(
                acik=h.get("acik") is True, port=h["port"] if port_gecerli(h.get("port")) else VARSAYILAN_PORT,
                terminal=h.get("terminal") is True, yonetim=h.get("yonetim") is True, https=h.get("https") is True, uyanik=h.get("uyanik") is True,
                kok=h["kok"] if isinstance(h.get("kok"), str) else "", cihazlar=cihazlar[:AZAMI_CIHAZ],
            )
        except (OSError, ValueError, json.JSONDecodeError):
            return Ayar()
        yeniden_yaz = False
        if "anahtar" in h:  # eski tek anahtar (DPAPI ile korunur; eski duz metin de okunur)
            eski = gizli.ac(h.get("anahtar"))
            if isinstance(eski, str) and len(eski) >= 32 and not any(hmac.compare_digest(c.ozet, ozet(eski)) for c in ayar.cihazlar):
                simdi = time.time()
                ayar.cihazlar.insert(0, Cihaz(kimlik=_yeni_kimlik(ayar), ad=ESKI_CIHAZ_ADI, ozet=ozet(eski), olusturma=simdi, bitis=simdi + VARSAYILAN_GUN * 86400))
            yeniden_yaz = True
        if isinstance(ham, list) and any(isinstance(x, dict) and not gizli.korumali_mi(x.get("ozet")) for x in ham) and gizli.koru("0") != "0":
            yeniden_yaz = True  # duz metin ozet: korumali bicime gecir
        if yeniden_yaz:
            try:
                yaz(ayar)
            except OSError:
                pass
        return ayar


def _yeni_kimlik(ayar: Ayar) -> str:
    while True:
        k = secrets.token_hex(4)
        if all(c.kimlik != k for c in ayar.cihazlar):
            return k


def yaz(ayar: Ayar) -> None:
    with _KILIT:
        yol = dosya_yolu()
        yol.parent.mkdir(parents=True, exist_ok=True)
        gecici = yol.with_suffix(".tmp")
        veri = {k: v for k, v in asdict(ayar).items() if k != "cihazlar"}
        veri["cihazlar"] = [c.disk() for c in ayar.cihazlar]
        gecici.write_text(json.dumps(veri, indent=2), encoding="utf-8")
        os.replace(gecici, yol)
        try:
            os.chmod(yol, 0o600)  # anahtar ozetleri iceriyor
        except OSError:
            pass


def guncelle(degisiklik: dict) -> Ayar:
    """Yerel arayuzden gelen degisiklik. Yalniz bilinen alanlar, tipleri dogrulanir."""
    with _KILIT:
        return _guncelle(degisiklik)


def _guncelle(degisiklik: dict) -> Ayar:
    ayar = oku()
    for alan in ("acik", "terminal", "yonetim", "https", "uyanik"):
        if alan in degisiklik:
            if not isinstance(degisiklik[alan], bool):
                raise UzakHatasi(f"'{alan}' true/false olmali")
            setattr(ayar, alan, degisiklik[alan])
    if "port" in degisiklik:
        if not port_gecerli(degisiklik["port"]):
            raise UzakHatasi("'port' 1024-65535 arasinda bir sayi olmali")
        ayar.port = degisiklik["port"]
    if "kok" in degisiklik:
        kok = degisiklik["kok"]
        if not isinstance(kok, str) or (kok.strip() and not Path(kok).expanduser().is_dir()):
            raise UzakHatasi("'kok' var olan bir klasor yolu (ya da bos) olmali")
        ayar.kok = str(Path(kok).expanduser().resolve()) if kok.strip() else ""
    yaz(ayar)
    return ayar


def kok_klasoru(ayar: Ayar, acik_proje: Path | None) -> Path | None:
    """Uzaktan gezilebilir klasorlerin en ustu: ayardaki `kok`, yoksa YALNIZ acik projenin kendisi, o da yoksa None (hicbir klasor gezilmez).
    2026-11-23: eskiden acik projenin UST klasoru, proje yoksa EV dizininin tamami gezilebiliyordu (yan klasorlerdeki projeler/dosyalar acikti).
    Kayitli projeler bundan bagimsiz olarak uzaktan acilabilir; yeni klasor icin kullanici kok'u bilerek secer."""
    if ayar.kok.strip():
        return Path(ayar.kok).expanduser().resolve()
    return acik_proje.resolve() if acik_proje else None


def kokun_icinde(yol: str | Path, kok: Path | None) -> bool:
    if kok is None:
        return False
    try:
        y, k = os.path.normcase(str(Path(yol).expanduser().resolve())), os.path.normcase(str(kok.resolve()))
        return os.path.commonpath([y, k]) == k
    except (OSError, ValueError):
        return False


AZAMI_KAYIT = 1_000_000  # uzak-erisim.log bu boyutu asinca .log.1'e devredilir (reddedilen istek seli diski doldurmasin)


def kayit_yaz(olay: str) -> None:
    """Uzaktan yapilan klasor secimlerini ve reddedilen anahtarlari ~/.aktapokus/uzak-erisim.log dosyasina ekler (kayit basarisizsa sessiz).
    Cagiranlar ANAHTARI asla yazmaz; denetim karakterleri temizlenir (sahte kayit satiri eklenemesin)."""
    try:
        yol = dosya_yolu().with_suffix(".log")
        yol.parent.mkdir(parents=True, exist_ok=True)
        try:
            if yol.stat().st_size > AZAMI_KAYIT:
                os.replace(yol, yol.with_suffix(".log.1"))
        except FileNotFoundError:
            pass
        temiz = "".join(c if c.isprintable() else "?" for c in olay)[:500]
        with yol.open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {temiz}\n")
    except OSError:
        pass


# ---- cihaz anahtarlari ---------------------------------------------------------------------------------------------------
def ad_dogrula(ad: object) -> str:
    if not isinstance(ad, str) or not ad.strip():
        raise UzakHatasi("Cihaz adi gerekli")
    ad = ad.strip()
    if len(ad) > 40 or any(not c.isprintable() for c in ad):
        raise UzakHatasi("Cihaz adi en fazla 40 yazdirilabilir karakter olmali")
    return ad


def cihaz_ekle(ad: object, gun: object = VARSAYILAN_GUN) -> tuple[Ayar, Cihaz, str]:
    """Yeni cihaz anahtari uretir. Anahtar YALNIZ bu donuste vardir (diskte ozeti kalir). gun: 1-3650 ya da 0 (suresiz)."""
    ad = ad_dogrula(ad)
    if not isinstance(gun, int) or isinstance(gun, bool) or not 0 <= gun <= 3650:
        raise UzakHatasi("'gun' 0 (suresiz) ile 3650 arasinda bir sayi olmali")
    with _KILIT:
        ayar = oku()
        if len(ayar.cihazlar) >= AZAMI_CIHAZ:
            raise UzakHatasi(f"En fazla {AZAMI_CIHAZ} cihaz eklenebilir; kullanmadiklarinizi iptal edin")
        if any(c.ad.casefold() == ad.casefold() for c in ayar.cihazlar):
            raise UzakHatasi("Bu adla bir cihaz zaten var")
        anahtar = secrets.token_urlsafe(32)
        simdi = time.time()
        c = Cihaz(kimlik=_yeni_kimlik(ayar), ad=ad, ozet=ozet(anahtar), olusturma=simdi, bitis=simdi + gun * 86400 if gun else None)
        ayar.cihazlar.append(c)
        yaz(ayar)
        return ayar, c, anahtar


def cihaz_iptal(kimlik: object) -> Ayar:
    with _KILIT:
        ayar = oku()
        kalan = [c for c in ayar.cihazlar if c.kimlik != kimlik]
        if len(kalan) == len(ayar.cihazlar):
            raise UzakHatasi("Cihaz bulunamadi")
        ayar.cihazlar = kalan
        yaz(ayar)
        return ayar


def cihaz_bul(ayar: Ayar, jeton: str | bytes) -> tuple[Cihaz | None, str]:
    """Jetonun cihazi ve (reddedilirse) Turkce sebep. Ozetler hmac.compare_digest ile, ERKEN CIKMADAN hepsiyle karsilastirilir."""
    if not jeton:
        return None, "anahtar yok"
    oz = ozet(jeton)
    bulunan = None
    for c in ayar.cihazlar:
        if hmac.compare_digest(c.ozet, oz):
            bulunan = c
    if bulunan is None:
        return None, "gecersiz ya da iptal edilmis anahtar"
    if bulunan.suresi_doldu():
        return None, f"suresi dolmus anahtar (cihaz: {bulunan.ad})"
    return bulunan, ""


def cihaz_kullanildi(kimlik: str, ip: str, zaman: float) -> None:
    """Son kullanim zamani/IP'yi diske yazar (iptal edilmis cihazi geri getirmez)."""
    with _KILIT:
        ayar = oku()
        for c in ayar.cihazlar:
            if c.kimlik == kimlik:
                c.son_zaman, c.son_ip = zaman, ip
                try:
                    yaz(ayar)
                except OSError:
                    pass
                return


def qr_veri_adresi(metin: str) -> str | None:
    """Baglantinin QR kodu (data:image/svg+xml). Istege bagli 'segno' paketi yoksa None (baglanti yine gosterilir)."""
    try:
        import segno
    except ImportError:
        return None
    try:
        return segno.make(metin, error="m").svg_data_uri(scale=5, border=2)
    except Exception:
        return None


def adres_gecerli(adres: object) -> bool:
    """Uzak dinleyici yalniz Tailscale agina (100.64.0.0/10) ya da loopback'e baglanabilir. 0.0.0.0, LAN ve genel adresler reddedilir."""
    try:
        ip = ipaddress.ip_address(str(adres))
    except ValueError:
        return False
    return ip.version == 4 and (ip in TAILSCALE_AGI or ip.is_loopback)


# ---- Tailscale ----------------------------------------------------------------------------------------------------------
def tailscale_bul() -> str | None:
    ortam = os.environ.get(TAILSCALE_ORTAMI)
    if ortam:
        return ortam if Path(ortam).is_file() else None
    yol = shutil.which("tailscale")
    if yol:
        return yol
    for aday in (r"C:\Program Files\Tailscale\tailscale.exe", r"C:\Program Files (x86)\Tailscale\tailscale.exe"):
        if Path(aday).is_file():
            return aday
    return None


def _calistir(args: list[str]) -> tuple[int, str]:
    ts = tailscale_bul()
    if not ts:
        raise UzakHatasi("Tailscale kurulu degil")
    onek = [sys.executable, ts] if ts.lower().endswith(".py") else [ts]  # AKTAPOKUS_TAILSCALE bir .py betigini (deneme) de gosterebilir
    try:
        s = subprocess.run([*onek, *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10, stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as hata:
        raise UzakHatasi(f"Tailscale calistirilamadi: {type(hata).__name__}") from None
    return s.returncode, s.stdout


def tailscale_durum() -> dict:
    """{kurulu, calisiyor, adres, dns, hata}. Hicbir ayar degistirmez; yalniz okur."""
    if not tailscale_bul():
        return {"kurulu": False, "calisiyor": False, "adres": None, "dns": None, "hata": "Tailscale kurulu degil"}
    try:
        kod, cikti = _calistir(["status", "--json"])
        durum = json.loads(cikti) if kod == 0 and cikti.strip() else {}
        calisiyor = durum.get("BackendState") == "Running"
        dns = str((durum.get("Self") or {}).get("DNSName") or "").rstrip(".").lower() or None
        if dns and not re.fullmatch(r"[a-z0-9.-]{1,253}", dns):
            dns = None
        adres = None
        if calisiyor:
            kod, cikti = _calistir(["ip", "-4"])
            if kod == 0:
                adres = next((s for s in cikti.split() if adres_gecerli(s)), None)
        hata = None if calisiyor and adres else ("Tailscale kapali ya da oturum acilmamis" if not calisiyor else "Tailscale IPv4 adresi okunamadi")
        return {"kurulu": True, "calisiyor": calisiyor, "adres": adres, "dns": dns, "hata": hata}
    except (UzakHatasi, json.JSONDecodeError, AttributeError, TypeError) as hata:
        return {"kurulu": True, "calisiyor": False, "adres": None, "dns": None, "hata": f"Tailscale durumu okunamadi ({type(hata).__name__})"}


SERVE_PORTU = 443


def _serve_calistir(args: list[str]) -> tuple[int | None, str]:
    """`tailscale serve ...`: (cikis kodu, stdout+stderr). Zaman asiminda kodu None'dur (Tailscale HTTPS'i etkinlestirmeni beklerken takilabilir)."""
    ts = tailscale_bul()
    if not ts:
        raise UzakHatasi("Tailscale kurulu degil")
    onek = [sys.executable, ts] if ts.lower().endswith(".py") else [ts]
    try:
        s = subprocess.run([*onek, "serve", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15, stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired as hata:
        kismi = hata.stdout if isinstance(hata.stdout, str) else (hata.stdout or b"").decode("utf-8", "replace")
        kismi += hata.stderr if isinstance(hata.stderr, str) else (hata.stderr or b"").decode("utf-8", "replace")
        return None, kismi
    except OSError as hata:
        raise UzakHatasi(f"Tailscale calistirilamadi: {type(hata).__name__}") from None
    return s.returncode, (s.stdout or "") + (s.stderr or "")


def serve_acik_mi(adres: str, port: int) -> bool:
    """Tailscale `serve` yapilandirmasinda bu dinleyiciye giden bir https vekili var mi (baska vekillere bakmaz)."""
    try:
        kod, cikti = _serve_calistir(["status", "--json"])
        if kod != 0:
            return False
        hedef = f"http://{adres}:{port}"
        for web in (json.loads(cikti).get("Web") or {}).values():
            for h in (web.get("Handlers") or {}).values():
                if str(h.get("Proxy", "")).rstrip("/") == hedef:
                    return True
    except (UzakHatasi, json.JSONDecodeError, AttributeError, TypeError):
        pass
    return False


def _serve_hata_metni(kod: int | None, cikti: str) -> str:
    satirlar = [s.strip() for s in cikti.splitlines() if s.strip()]
    metin = " ".join(satirlar)[:400]
    if kod is None or "not enabled" in cikti.lower() or "https certificates" in cikti.lower() or "login.tailscale.com" in cikti:
        return ("Tailscale HTTPS henuz acik degil. Tailscale yonetim sayfasinda (DNS bolumu) 'HTTPS Certificates' ozelligini acin, sonra yeniden deneyin."
                + (f" Tailscale'in mesaji: {metin}" if metin else ""))
    return f"Tailscale serve basarisiz: {metin or 'bilinmeyen hata'}"


def serve_ac(adres: str, port: int) -> None:
    """https://<ad>.ts.net -> http://<tailscale ip>:<port>. Yalniz Tailscale ag icinde (funnel DEGIL: internete acilmaz)."""
    kod, cikti = _serve_calistir(["--bg", f"--https={SERVE_PORTU}", f"http://{adres}:{port}"])
    if kod != 0:
        raise UzakHatasi(_serve_hata_metni(kod, cikti))


def serve_kapat(adres: str, port: int) -> None:
    """Yalniz BU dinleyiciye giden vekil varsa kapatir; kullanicinin baska serve ayarlarina dokunmaz."""
    if serve_acik_mi(adres, port):
        _serve_calistir([f"--https={SERVE_PORTU}", "off"])


# ---- politika (uzak istekler icin) ---------------------------------------------------------------------------------------
# (yontem kumesi, yol on eki / tam yol, yalniz-yonetim-acikken-serbest mi) -- yonetim kapaliyken reddedilenler:
YONETIM_KAPALIYKEN_YASAK = (
    ({"POST", "PUT", "DELETE"}, "/api/clilar"),
    ({"POST", "PUT", "DELETE"}, "/api/mcp-sunuculari"),
    ({"POST"}, "/api/opcua"),  # istek sunucusundan ag adreslerine baglanir
    ({"POST"}, "/api/ag"),  # bilgisayarin IP'sini degistirir, agi tarar, BOOTP yanitlar
    ({"POST", "PUT", "DELETE"}, "/api/saglayicilar"),
    ({"POST", "PUT", "DELETE"}, "/api/telegram"),
    ({"POST", "PUT", "DELETE"}, "/api/beceriler"),
    ({"POST"}, "/api/gorev-sil"),  # kalici silme
    ({"POST"}, "/api/klasor-ac"),  # bilgisayarda Dosya Gezgini/VS Code acar
    ({"POST"}, "/api/claude-devam"),  # bilgisayarda terminal acar
    ({"POST"}, "/api/onizleme-ac"),  # bilgisayarda tarayici acar
    ({"POST"}, "/api/onizleme-ekran"),  # bilgisayarda tarayici calistirir
    ({"POST"}, "/api/claude-surdur"),  # bilgisayarda terminal acar
    ({"GET"}, "/api/claude-oturumlari"),  # kullanicinin Claude Code konusmalari (ozel icerik): yalniz bu bilgisayar
    ({"GET"}, "/api/claude-konusma"),
    ({"POST", "PUT", "DELETE"}, "/api/otomasyonlar"),  # zamanlanmis calistirma tanimlamak; '/api/otomasyon-calistir' (yalniz plan uretir) serbest
    ({"POST"}, "/api/github/giris/baslat"),  # GitHub hesabi baglamak
    ({"POST"}, "/api/github/giris/iptal"),
    ({"POST"}, "/api/github/cikis"),
    ({"GET"}, "/api/github/giris/durum"),
    ({"POST"}, "/api/github/klonla"),
    ({"POST"}, "/api/github/push"),  # disariya gonderir ya da geri donusu zor: uzaktan yalniz yonetim izniyle
    ({"POST"}, "/api/github/pr"),
    ({"POST"}, "/api/github/dal"),
    ({"POST"}, "/api/github/issue-yorum"),
    ({"POST"}, "/api/git/degisiklik-at"),
    ({"POST"}, "/api/git/pull"),
    ({"POST"}, "/api/git/cek"),
    ({"POST"}, "/api/git/birlestir"),
    ({"POST"}, "/api/git/dal-sil"),
    ({"POST"}, "/api/git/stash-sil"),
    ({"POST"}, "/api/projeler/unut"),
    ({"POST"}, "/api/motorlar/rolleri-gecir"),
    ({"POST"}, "/api/github/yayin-hazirla"),  # baska depoya klasor kopyalar (GitHub islemleri uzaktan yonetim izni ister)
    ({"GET"}, "/api/klasorler"),
    ({"GET"}, "/api/beceri-kaynak"),  # bilgisayardan internete cikis tetikler
)


# Uzaktan degerlendirilen uclar: listede olmayan uc uzaktan REDDEDILIR (yeni uc eklenince kendiliginden acik kalmasin).
# Yeni uc eklerken once uzaktan guvenli mi diye karar verin: tests/test_uzak.py eksik siniflandirmayi yakalar.
UZAK_BILINEN_UCLAR = frozenset({
    "/api/nodered", "/api/nodered/kur", "/api/nodered/baslat", "/api/nodered/durdur",  # politika her zaman reddeder
    "/api/ag/kablo-adaptorler", "/api/ag/kablo-dinle", "/api/masaustu",  # politika her zaman reddeder
    "/api/ag/adaptor-dhcp", "/api/ag/adaptor-ip", "/api/ag/adaptorler", "/api/ag/bootp", "/api/ag/bootp/ata", "/api/ag/bootp/baslat",
    "/api/ag/bootp/durdur", "/api/ag/bootp/kaldir", "/api/ag/profil", "/api/ag/profil-sil", "/api/ag/profil-uygula", "/api/ag/profiller",
    "/api/ag/ada-gore", "/api/ag/plc-sor", "/api/ag/tara", "/api/ayar", "/api/beceri-kaynak", "/api/beceri-kaynak/onizle", "/api/beceriler", "/api/beceriler/indir", "/api/beceriler/sil",
    "/api/ciktilar", "/api/claude-devam", "/api/claude-konusma", "/api/claude-oturumlari", "/api/claude-surdur", "/api/clilar", "/api/clilar/dene",
    "/api/clilar/sil", "/api/dosya", "/api/dosyalar", "/api/durum", "/api/ek", "/api/fark", "/api/gecmis", "/api/git/birlestir", "/api/git/cek",
    "/api/git/commit", "/api/git/commit-oneri", "/api/git/dal-gec", "/api/git/dal-sil", "/api/git/dallar", "/api/git/degisiklik-at", "/api/git/fark",
    "/api/git/gecmis", "/api/git/hazirdan-cikar", "/api/git/hazirla", "/api/git/pull", "/api/git/stash", "/api/git/stash-sil",
    "/api/git/stash-uygula", "/api/git/stashler", "/api/github/cikis", "/api/github/commit", "/api/github/commit-kontrol", "/api/github/dal",
    "/api/github/depolar", "/api/github/durum", "/api/github/giris/baslat", "/api/github/giris/durum", "/api/github/giris/iptal",
    "/api/github/gonderme-kontrol", "/api/github/issue-gorev", "/api/github/issue-yorum", "/api/github/issueler", "/api/github/klonla",
    "/api/github/pr", "/api/github/proje", "/api/github/push", "/api/github/yayin-hazirla", "/api/google", "/api/google/baglan", "/api/google/cikis",
    "/api/google/istemci", "/api/gorev", "/api/gorev-meta", "/api/gorev-sil", "/api/hesaplar", "/api/imza", "/api/istatistik", "/api/izinler",
    "/api/kaynak", "/api/klasor", "/api/klasor-ac", "/api/klasorler", "/api/konusma-ozeti", "/api/kuyruk/sil", "/api/mcp-sunuculari", "/api/mcp-sunuculari/dene",
    "/api/mcp-sunuculari/proje", "/api/mcp-sunuculari/sil", "/api/modeller", "/api/motorlar", "/api/motorlar/rolleri-gecir", "/api/olaylar",
    "/api/oneriler", "/api/onizleme", "/api/onizleme-ac", "/api/onizleme-ekran", "/api/opcua", "/api/opcua/abone", "/api/opcua/agac",
    "/api/opcua/degerler", "/api/opcua/durdur", "/api/opcua/goz", "/api/opcua/oku", "/api/opcua/ozellik", "/api/opcua/topla", "/api/opcua/toplama",
    "/api/opcua/veri", "/api/otomasyon-calistir", "/api/otomasyonlar", "/api/otomasyonlar/izin", "/api/otomasyonlar/sil", "/api/otomatik-baslat",
    "/api/oturumlar", "/api/proje-gruplari", "/api/projeler", "/api/projeler/unut", "/api/saglayicilar", "/api/saglayicilar/baglan",
    "/api/saglayicilar/kaldir", "/api/konusma-hafiza", "/api/sohbet-ad", "/api/sohbet-kararlar", "/api/sohbet-ozeti", "/api/sohbet-sec", "/api/telegram", "/api/terminal",
    "/api/terminal/ac", "/api/uzak", "/api/uzak/cihaz-ekle", "/api/uzak/cihaz-iptal", "/api/yarim", "/api/yeni-konusma", "/api/yeni-sohbet",
})


# Yolunda kimlik/ad tasiyan uclar (arayuz.py'deki re.match desenleriyle AYNI metin; tests/test_uzak.py eksigi yakalar).
# Yonetim kurallari (YONETIM_KAPALIYKEN_YASAK) bunlara da onek uzerinden uygulanir.
UZAK_DINAMIK_UCLAR = (
    r"^/api/gorev/([0-9a-f]+)/(onayla|reddet|karar|durdur|testi-atla|izin)$",  # plan onayi, koru/geri al, durdur
    r"^/api/beceriler/([A-Za-z0-9-]{1,64})$",  # beceri okuma (yazma yonetim ister)
    r"^/api/telegram/(baslat|durdur|eslestir|otomatik|ilerleme|kok|kok-sil|eslesme-kaldir)$",  # yonetim ister
    r"^/api/terminal/([0-9a-f]+)/akis$", r"^/api/terminal/([0-9a-f]+)/(girdi|boyut|kapat)$",  # terminal anahtarina bagli
)

def politika(yontem: str, yol: str, ayar: Ayar) -> str | None:
    """Uzak istek icin ret sebebi (Turkce) ya da izinliyse None. Cagri oncesi /api/p/<id>/ oneki ve sorgu ayiklanmis olmali."""
    if yol == "/api/uzak" or yol.startswith("/api/uzak/"):
        return "Uzak erisim ayarlari yalnizca bu bilgisayardan degistirilebilir"
    if yol == "/api/masaustu":
        return "Masaustu kontrolu yalnizca bu bilgisayardan acilip kapatilir"
    if yol.startswith("/api/ag/kablo-"):
        return "Kablo dinleme yalnizca bu bilgisayardan yapilir (yonetici izni ister)"
    if yol == "/api/nodered" or yol.startswith("/api/nodered/"):
        return "Node-RED yalnizca bu bilgisayardan yonetilir (duzenleyicisi kod calistirabilir)"
    if yol == "/api/otomatik-baslat":
        return "Otomatik baslatma yalnizca bu bilgisayardan degistirilebilir (Windows acilisina program ekler)"
    if yol == "/api/izinler":
        return "Genel izinler yalnizca bu bilgisayardan degistirilebilir (onay sorularini kaldirir)"
    if yol == "/api/otomasyonlar/izin":
        return "Otomasyon izinleri (onaysiz calistirma) yalnizca bu bilgisayardan degistirilebilir"
    if yol == "/api/terminal" or yol.startswith("/api/terminal/"):
        return None if ayar.terminal else "Terminal uzaktan kapali (bilgisayardan Ayarlar > Uzak erisim'den acilabilir)"
    if yol not in UZAK_BILINEN_UCLAR and not any(re.match(desen, yol) for desen in UZAK_DINAMIK_UCLAR):
        return "Bu islem uzaktan tanimli degil"
    if not ayar.yonetim:
        for yontemler, onek in YONETIM_KAPALIYKEN_YASAK:
            if yontem in yontemler and (yol == onek or yol.startswith(onek + "/")):
                return "Bu islem uzaktan kapali (GitHub'a gonderme, yikici Git islemleri, CLI/MCP/saglayici/Telegram/beceri tanimlama, klasor gezme ve depo klonlama icin Ayarlar > Uzak erisim'de yonetim izni gerekir)"
    return None
