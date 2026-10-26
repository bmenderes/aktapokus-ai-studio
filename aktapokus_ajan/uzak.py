"""Uzak erisim (telefondan/baska bilgisayardan): Tailscale ozel agi uzerinden, ACIK-KAPALI bir secenek olarak. Varsayilan KAPALI.

Guvenlik modeli:
- Uzak istekler AYRI bir dinleyiciye gelir; bu dinleyici yalniz Tailscale adresine (100.64.0.0/10) -test icin loopback- baglanir, ASLA 0.0.0.0'a.
  Sade LAN adresleri reddedilir (HTTP, sifresiz: belirtec ag dinleyicisine gorunurdu). Tailscale trafigi zaten WireGuard ile sifrelidir.
- Host/Origin yalniz bu dinleyicinin adreslerinden (Tailscale IP'si ve MagicDNS adi) kabul edilir (DNS-rebinding korumasi).
- Kimlik: sabit "uzak anahtar" (dosyada, yenilenebilir) ya da yerel belirtec. Anahtar yalniz YEREL arayuzde gosterilir.
- YETKI DARALTMA: uzak istemci gorev verebilir/onaylayabilir, dosya/fark/Git gorebilir; ama varsayilan olarak su islemler UZAKTAN YAPILAMAZ: terminal,
  CLI/MCP/saglayici/Telegram/beceri TANIMLAMA (bilgisayarda program calistirmak demektir), kayitsiz klasor acma, klasor gezme, depo klonlama.
  `terminal` ve `yonetim` anahtarlari bilerek ve ayri ayri acilir; uzak erisim ayarlarinin KENDISI hicbir kosulda uzaktan degistirilemez."""

from __future__ import annotations

import ipaddress
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

AYAR_ORTAMI = "AKTAPOKUS_UZAK"
TAILSCALE_ORTAMI = "AKTAPOKUS_TAILSCALE"
VARSAYILAN_PORT = 47650
TAILSCALE_AGI = ipaddress.ip_network("100.64.0.0/10")


class UzakHatasi(Exception):
    pass


@dataclass
class Ayar:
    acik: bool = False
    port: int = VARSAYILAN_PORT
    terminal: bool = False  # uzaktan terminal (TAM komut calistirma): ayri ve bilincli acilir
    yonetim: bool = False  # uzaktan CLI/MCP/saglayici/Telegram/beceri tanimlama, klasor gezme, klonlama
    anahtar: str = field(default_factory=lambda: secrets.token_urlsafe(32))

    def sozluk(self, anahtarli: bool = False) -> dict:
        d = asdict(self)
        if not anahtarli:
            d.pop("anahtar")
        return d


def dosya_yolu() -> Path:
    ortam = os.environ.get(AYAR_ORTAMI)
    return Path(ortam) if ortam else Path.home() / ".aktapokus" / "uzak-erisim.json"


def port_gecerli(port: object) -> bool:
    return isinstance(port, int) and not isinstance(port, bool) and 1024 <= port <= 65535


def oku() -> Ayar:
    """Ayar dosyasi yoksa/bozuksa KAPALI varsayilan (yeni anahtarla) doner; yalniz yazildiginda kalicilasir."""
    try:
        h = json.loads(dosya_yolu().read_text(encoding="utf-8"))
        if not isinstance(h, dict):
            raise ValueError
        anahtar = h.get("anahtar")
        return Ayar(
            acik=h.get("acik") is True, port=h["port"] if port_gecerli(h.get("port")) else VARSAYILAN_PORT,
            terminal=h.get("terminal") is True, yonetim=h.get("yonetim") is True,
            anahtar=anahtar if isinstance(anahtar, str) and len(anahtar) >= 32 else secrets.token_urlsafe(32),
        )
    except (OSError, ValueError, json.JSONDecodeError):
        return Ayar()


def yaz(ayar: Ayar) -> None:
    yol = dosya_yolu()
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_suffix(".tmp")
    gecici.write_text(json.dumps(asdict(ayar), indent=2), encoding="utf-8")
    os.replace(gecici, yol)
    try:
        os.chmod(yol, 0o600)  # anahtar iceriyor
    except OSError:
        pass


def guncelle(degisiklik: dict) -> Ayar:
    """Yerel arayuzden gelen degisiklik. Yalniz bilinen alanlar, tipleri dogrulanir."""
    ayar = oku()
    for alan in ("acik", "terminal", "yonetim"):
        if alan in degisiklik:
            if not isinstance(degisiklik[alan], bool):
                raise UzakHatasi(f"'{alan}' true/false olmali")
            setattr(ayar, alan, degisiklik[alan])
    if "port" in degisiklik:
        if not port_gecerli(degisiklik["port"]):
            raise UzakHatasi("'port' 1024-65535 arasinda bir sayi olmali")
        ayar.port = degisiklik["port"]
    yaz(ayar)
    return ayar


def anahtari_yenile() -> Ayar:
    ayar = oku()
    ayar.anahtar = secrets.token_urlsafe(32)
    yaz(ayar)
    return ayar


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


# ---- politika (uzak istekler icin) ---------------------------------------------------------------------------------------
# (yontem kumesi, yol on eki / tam yol, yalniz-yonetim-acikken-serbest mi) -- yonetim kapaliyken reddedilenler:
YONETIM_KAPALIYKEN_YASAK = (
    ({"POST", "PUT", "DELETE"}, "/api/clilar"),
    ({"POST", "PUT", "DELETE"}, "/api/mcp-sunuculari"),
    ({"POST", "PUT", "DELETE"}, "/api/saglayicilar"),
    ({"POST", "PUT", "DELETE"}, "/api/telegram"),
    ({"POST", "PUT", "DELETE"}, "/api/beceriler"),
    ({"POST", "PUT", "DELETE"}, "/api/otomasyonlar"),  # zamanlanmis calistirma tanimlamak; '/api/otomasyon-calistir' (yalniz plan uretir) serbest
    ({"POST"}, "/api/github/klonla"),
    ({"GET"}, "/api/klasorler"),
)


def politika(yontem: str, yol: str, ayar: Ayar) -> str | None:
    """Uzak istek icin ret sebebi (Turkce) ya da izinliyse None. Cagri oncesi /api/p/<id>/ oneki ve sorgu ayiklanmis olmali."""
    if yol == "/api/uzak" or yol.startswith("/api/uzak/"):
        return "Uzak erisim ayarlari yalnizca bu bilgisayardan degistirilebilir"
    if yol == "/api/terminal" or yol.startswith("/api/terminal/"):
        return None if ayar.terminal else "Terminal uzaktan kapali (bilgisayardan Ayarlar > Uzak erisim'den acilabilir)"
    if not ayar.yonetim:
        for yontemler, onek in YONETIM_KAPALIYKEN_YASAK:
            if yontem in yontemler and (yol == onek or yol.startswith(onek + "/")):
                return "Bu islem uzaktan kapali (CLI/MCP/saglayici/Telegram/beceri tanimlama, klasor gezme ve depo klonlama bilgisayardan yapilir)"
    return None
