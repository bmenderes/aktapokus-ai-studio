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
    uyanik: bool = False  # uzak erisim ACIKKEN bilgisayar uyumasin (uyanik.py; Windows). Varsayilan kapali
    https: bool = False  # Tailscale `serve` ile https://<ad>.ts.net (ana ekrana uygulama olarak eklemek icin); dinleyici yine yalniz Tailscale adresinde
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
            terminal=h.get("terminal") is True, yonetim=h.get("yonetim") is True, https=h.get("https") is True, uyanik=h.get("uyanik") is True,
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
    for alan in ("acik", "terminal", "yonetim", "https", "uyanik"):
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
    "/api/ag/kablo-adaptorler", "/api/ag/kablo-dinle",  # politika her zaman reddeder
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
    "/api/klasor", "/api/klasor-ac", "/api/klasorler", "/api/konusma-ozeti", "/api/kuyruk/sil", "/api/mcp-sunuculari", "/api/mcp-sunuculari/dene",
    "/api/mcp-sunuculari/proje", "/api/mcp-sunuculari/sil", "/api/modeller", "/api/motorlar", "/api/motorlar/rolleri-gecir", "/api/olaylar",
    "/api/oneriler", "/api/onizleme", "/api/onizleme-ac", "/api/onizleme-ekran", "/api/opcua", "/api/opcua/abone", "/api/opcua/agac",
    "/api/opcua/degerler", "/api/opcua/durdur", "/api/opcua/goz", "/api/opcua/oku", "/api/opcua/ozellik", "/api/opcua/topla", "/api/opcua/toplama",
    "/api/opcua/veri", "/api/otomasyon-calistir", "/api/otomasyonlar", "/api/otomasyonlar/izin", "/api/otomasyonlar/sil", "/api/otomatik-baslat",
    "/api/oturumlar", "/api/proje-gruplari", "/api/projeler", "/api/projeler/unut", "/api/saglayicilar", "/api/saglayicilar/baglan",
    "/api/saglayicilar/kaldir", "/api/sohbet-ad", "/api/sohbet-kararlar", "/api/sohbet-ozeti", "/api/sohbet-sec", "/api/telegram", "/api/terminal",
    "/api/terminal/ac", "/api/uzak", "/api/uzak/anahtar-yenile", "/api/yarim", "/api/yeni-konusma", "/api/yeni-sohbet",
})


def politika(yontem: str, yol: str, ayar: Ayar) -> str | None:
    """Uzak istek icin ret sebebi (Turkce) ya da izinliyse None. Cagri oncesi /api/p/<id>/ oneki ve sorgu ayiklanmis olmali."""
    if yol == "/api/uzak" or yol.startswith("/api/uzak/"):
        return "Uzak erisim ayarlari yalnizca bu bilgisayardan degistirilebilir"
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
    if yol not in UZAK_BILINEN_UCLAR:
        return "Bu islem uzaktan tanimli degil"
    if not ayar.yonetim:
        for yontemler, onek in YONETIM_KAPALIYKEN_YASAK:
            if yontem in yontemler and (yol == onek or yol.startswith(onek + "/")):
                return "Bu islem uzaktan kapali (GitHub'a gonderme, yikici Git islemleri, CLI/MCP/saglayici/Telegram/beceri tanimlama, klasor gezme ve depo klonlama icin Ayarlar > Uzak erisim'de yonetim izni gerekir)"
    return None
