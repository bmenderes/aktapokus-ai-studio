"""MCP sunuculari: bir kez tanimla, projede ac, OpenCode / Claude Code / Codex'e kendiliginden aktar ("ortak MCP").

Tanimlar kullanici duzeyinde saklanir (`~/.aktapokus/mcp.json`, AKTAPOKUS_MCP ile degistirilir). Her tanim hangi PROJELERDE etkin oldugunu
da tasir; varsayilan KAPALI (bir MCP sunucusu bilgisayarda keyfi program calistirir ve proje klasor korumasinin disindadir).

Guvenlik:
- Tanim yalniz yerel, belirtecli arayuzden yazilir (Telegram'dan degil).
- Komut bir DIZIDIR, kabuk kullanilmaz. Program mutlak yol ya da PATH'te bulunan bir ad olmali; .ps1/.vbs reddedilir.
- Ortam degiskeni ve baslik DEGERLERI (anahtar/belirtec icerebilir) arayuze geri VERILMEZ; yalniz adlari gorunur. Guncellemede maske ('••••')
  gelen deger eskisini korur. Degerler gunluge/olaylara yazilmaz.
- CLI'lara dosya yazmadan aktarilir: OpenCode API'si (calisma anina ozel), Claude `--mcp-config` gecici dosyasi, Codex `-c` gecersiz kilmalari.
  Kullanicinin kendi CLI yapilandirmasina DOKUNULMAZ."""

from __future__ import annotations

import json
import os
import re
import shutil
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path

KAYIT_ORTAMI = "AKTAPOKUS_MCP"
AD_DESENI = re.compile(r"^[a-z0-9][a-z0-9_-]{0,30}$")
ORTAM_DESENI = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
BASLIK_DESENI = re.compile(r"^[A-Za-z0-9!#$%&'*+.^_`|~-]{1,64}$")
YASAK_UZANTILAR = {".ps1", ".vbs", ".js"}
MASKE = "••••"
AZAMI_ARGUMAN = 50
AZAMI_UZUNLUK = 4000
AZAMI_SUNUCU = 40
TURLER = ("local", "remote")


class McpHatasi(Exception):
    pass


@dataclass(frozen=True)
class McpTanim:
    ad: str
    tur: str  # "local" (stdio) | "remote" (Streamable HTTP)
    komut: tuple[str, ...] = ()  # local: [program, argumanlar...]
    url: str = ""  # remote
    ortam: dict = field(default_factory=dict)  # local: ortam degiskenleri (DEGERLER gizli)
    basliklar: dict = field(default_factory=dict)  # remote: HTTP basliklari (DEGERLER gizli)
    projeler: tuple[str, ...] = ()  # etkin oldugu proje kimlikleri
    aciklama: str = ""

    def sozluk(self, maskeli: bool = True) -> dict:
        d = {
            "ad": self.ad, "tur": self.tur, "komut": list(self.komut), "url": self.url,
            "ortam": {k: (MASKE if maskeli else v) for k, v in self.ortam.items()},
            "basliklar": {k: (MASKE if maskeli else v) for k, v in self.basliklar.items()},
            "projeler": list(self.projeler), "aciklama": self.aciklama,
        }
        return d


def _metin_sozlugu(veri: object, ad: str, desen: re.Pattern) -> dict:
    if veri is None or veri == {}:
        return {}
    if not isinstance(veri, dict) or len(veri) > 60:
        raise McpHatasi(f"'{ad}' en cok 60 girdili bir nesne olmali")
    sonuc = {}
    for k, v in veri.items():
        if not isinstance(k, str) or not desen.match(k):
            raise McpHatasi(f"'{ad}' icinde gecersiz ad: {str(k)[:40]!r}")
        if not isinstance(v, str) or len(v) > AZAMI_UZUNLUK or "\x00" in v or "\n" in v or "\r" in v:
            raise McpHatasi(f"'{ad}.{k}' degeri tek satirlik metin olmali (en cok {AZAMI_UZUNLUK} karakter)")
        sonuc[k] = v
    return sonuc


def _program_dogrula(program: str) -> None:
    if not program or "\x00" in program or len(program) > 500:
        raise McpHatasi("Program adi bos ya da gecersiz")
    yol = Path(program)
    bulunan = str(yol) if yol.is_absolute() and yol.is_file() else shutil.which(program)
    if not bulunan:
        raise McpHatasi(f"Program bulunamadi (mutlak yol verin ya da PATH'te olsun): {program}")
    if Path(bulunan).suffix.lower() in YASAK_UZANTILAR:
        raise McpHatasi(f"{Path(bulunan).suffix} dosyalari desteklenmez; gercek programi verin (ornek: node, python, npx)")


def tanim_coz(veri: object, eski: McpTanim | None = None, program_denetle: bool = True) -> McpTanim:
    """Arayuzden gelen tanimi dogrular. `eski` verilirse maske ('••••') gelen ortam/baslik degerleri eskisinden korunur."""
    if not isinstance(veri, dict):
        raise McpHatasi("Tanim bir nesne olmali")
    ad = veri.get("ad")
    if not isinstance(ad, str) or not AD_DESENI.match(ad):
        raise McpHatasi("'ad' kucuk harf/rakam/-/_ icermeli ve 31 karakteri gecmemeli (ornek: dosya-arama)")
    tur = veri.get("tur", "local")
    if tur not in TURLER:
        raise McpHatasi("'tur' 'local' ya da 'remote' olmali")
    komut: tuple[str, ...] = ()
    url = ""
    if tur == "local":
        ham = veri.get("komut")
        if not isinstance(ham, list) or not ham or not all(isinstance(x, str) for x in ham):
            raise McpHatasi("'komut' en az programi iceren metin listesi olmali (ornek: [\"npx\", \"-y\", \"paket\"])")
        if len(ham) > AZAMI_ARGUMAN or any(len(x) > AZAMI_UZUNLUK or "\x00" in x for x in ham):
            raise McpHatasi(f"'komut' en cok {AZAMI_ARGUMAN} oge icerebilir ve ogeler cok uzun olamaz")
        if program_denetle:
            _program_dogrula(ham[0])
        komut = tuple(ham)
    else:
        url = veri.get("url")
        if not isinstance(url, str):
            raise McpHatasi("'url' gerekli")
        u = urllib.parse.urlsplit(url.strip())
        if u.scheme not in ("http", "https") or not u.hostname or u.username or u.password:
            raise McpHatasi("'url' http:// ya da https:// ile baslayan, kullanici/parola icermeyen tam adres olmali")
        url = url.strip()
    ortam = _metin_sozlugu(veri.get("ortam"), "ortam", ORTAM_DESENI) if tur == "local" else {}
    basliklar = _metin_sozlugu(veri.get("basliklar"), "basliklar", BASLIK_DESENI) if tur == "remote" else {}
    for sozluk, onceki in ((ortam, eski.ortam if eski else {}), (basliklar, eski.basliklar if eski else {})):
        for k, v in list(sozluk.items()):
            if v == MASKE:
                if k not in onceki:
                    raise McpHatasi(f"'{k}' icin yeni deger girin (kayitli deger yok)")
                sozluk[k] = onceki[k]
    projeler = veri.get("projeler", list(eski.projeler) if eski else [])
    if not isinstance(projeler, list) or not all(isinstance(x, str) and re.fullmatch(r"[0-9a-f]{10}", x) for x in projeler):
        raise McpHatasi("'projeler' proje kimliklerinin listesi olmali")
    aciklama = veri.get("aciklama") or ""
    if not isinstance(aciklama, str) or len(aciklama) > 300:
        raise McpHatasi("'aciklama' en cok 300 karakterlik metin olmali")
    return McpTanim(ad=ad, tur=tur, komut=komut, url=url, ortam=ortam, basliklar=basliklar, projeler=tuple(dict.fromkeys(projeler)), aciklama=aciklama.strip())


# ---- kayit defteri ----------------------------------------------------------------------------------------------------
def kayit_yolu() -> Path:
    ortam = os.environ.get(KAYIT_ORTAMI)
    return Path(ortam) if ortam else Path.home() / ".aktapokus" / "mcp.json"


def yukle() -> dict[str, McpTanim]:
    """Gecerli tanimlar; bozuk olan atlanir (programi silinmis olsa bile LISTELENIR: kullanici gorup duzeltebilsin)."""
    try:
        ham = json.loads(kayit_yolu().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    sonuc: dict[str, McpTanim] = {}
    for oge in ham.get("sunucular", []) if isinstance(ham, dict) else []:
        try:
            t = tanim_coz(oge, program_denetle=False)
        except McpHatasi:
            continue
        sonuc[t.ad] = t
    return sonuc


def _yaz(tanimlar: dict[str, McpTanim]) -> None:
    yol = kayit_yolu()
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_suffix(".tmp")
    gecici.write_text(json.dumps({"surum": 1, "sunucular": [t.sozluk(maskeli=False) for t in tanimlar.values()]}, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(gecici, yol)
    try:
        os.chmod(yol, 0o600)  # anahtar iceren dosya: yalniz kullanici (Windows'ta etkisi sinirli)
    except OSError:
        pass


def kaydet(veri: object) -> McpTanim:
    tanimlar = yukle()
    ad = veri.get("ad") if isinstance(veri, dict) else None
    t = tanim_coz(veri, eski=tanimlar.get(ad) if isinstance(ad, str) else None)
    if t.ad not in tanimlar and len(tanimlar) >= AZAMI_SUNUCU:
        raise McpHatasi(f"En cok {AZAMI_SUNUCU} MCP sunucusu tanimlanabilir")
    tanimlar[t.ad] = t
    _yaz(tanimlar)
    return t


def sil(ad: str) -> bool:
    tanimlar = yukle()
    if ad not in tanimlar:
        return False
    del tanimlar[ad]
    _yaz(tanimlar)
    return True


def proje_ayarla(ad: str, proje: str, acik: bool) -> McpTanim:
    tanimlar = yukle()
    t = tanimlar.get(ad)
    if t is None:
        raise McpHatasi("Boyle bir MCP sunucusu yok")
    if not re.fullmatch(r"[0-9a-f]{10}", proje or ""):
        raise McpHatasi("Gecersiz proje kimligi")
    projeler = [p for p in t.projeler if p != proje] + ([proje] if acik else [])
    yeni = McpTanim(t.ad, t.tur, t.komut, t.url, t.ortam, t.basliklar, tuple(projeler), t.aciklama)
    tanimlar[ad] = yeni
    _yaz(tanimlar)
    return yeni


def proje_icin(proje: str | None) -> list[McpTanim]:
    """Bu projede etkin sunucular (CLI'lara aktarilacaklar)."""
    return [t for t in yukle().values() if proje and proje in t.projeler]


def listele() -> list[dict]:
    return [t.sozluk() for t in yukle().values()]


# ---- CLI bicimlerine donusum ------------------------------------------------------------------------------------------
def opencode_ayari(t: McpTanim) -> dict:
    """OpenCode `PUT /api/experimental/mcp/{ad}` govdesindeki `config`."""
    if t.tur == "local":
        c: dict = {"type": "local", "command": list(t.komut)}
        if t.ortam:
            c["environment"] = dict(t.ortam)
        return c
    c = {"type": "remote", "url": t.url}
    if t.basliklar:
        c["headers"] = dict(t.basliklar)
    return c


def claude_ayari(tanimlar: list[McpTanim]) -> dict:
    """`claude --mcp-config` dosyasinin icerigi."""
    sunucular: dict = {}
    for t in tanimlar:
        if t.tur == "local":
            s: dict = {"type": "stdio", "command": t.komut[0], "args": list(t.komut[1:])}
            if t.ortam:
                s["env"] = dict(t.ortam)
        else:
            s = {"type": "http", "url": t.url}
            if t.basliklar:
                s["headers"] = dict(t.basliklar)
        sunucular[t.ad] = s
    return {"mcpServers": sunucular}


def _toml_metin(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)  # JSON dizgesi gecerli TOML temel dizgesidir


def codex_gecersiz_kilmalari(tanimlar: list[McpTanim]) -> list[str]:
    """`codex exec -c anahtar=deger` argumanlari: kullanicinin config.toml'una dokunmadan bu calismaya ozel."""
    args: list[str] = []
    for t in tanimlar:
        on = f"mcp_servers.{t.ad}"
        # Kullanici bu sunucuyu BU projede kendisi etkinlestirdi: araclari onay sorusuz kullanilsin (yoksa approval_policy=never hepsini reddeder)
        args += ["-c", f'{on}.default_tools_approval_mode="approve"', "-c", f"{on}.startup_timeout_sec=60"]
        if t.tur == "local":
            args += ["-c", f"{on}.command={_toml_metin(t.komut[0])}"]
            if len(t.komut) > 1:
                args += ["-c", f"{on}.args=[{', '.join(_toml_metin(a) for a in t.komut[1:])}]"]
            if t.ortam:
                args += ["-c", f"{on}.env={{{', '.join(f'{k} = {_toml_metin(v)}' for k, v in t.ortam.items())}}}"]
        else:
            args += ["-c", f"{on}.url={_toml_metin(t.url)}"]
            if t.basliklar:
                args += ["-c", f"{on}.http_headers={{{', '.join(f'{_toml_metin(k)} = {_toml_metin(v)}' for k, v in t.basliklar.items())}}}"]
    return args
