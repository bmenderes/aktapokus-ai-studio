"""Gonderme kontrolu: GitHub'a giden icerik kisisel veri ve sir bakimindan denetlenir; commit ve push ASLA kontrolsuz yapilmaz.

Iki katman:
1. KURAL TABANLI tarama (anahtar/belirtec kaliplari, parola atamalari, kart/IBAN/T.C. kimlik no (algoritma dogrulamali), e-posta, telefon, kullanici klasoru yolu,
   ozel ag adlari, gizli dosya adlari). Yalniz EKLENEN satirlara bakilir; bulgu ornekleri MASKELIDIR (sir arayuze/gunluge tam yazilmaz).
2. YAPAY ZEKA incelemesi: kural tabaninin yakalayamayacagi seyler (ad-soyad, adres, ozel kurum bilgisi...). Modele giden metinde bulunan sirlar ONCEDEN
   `[GIZLI:tur]` ile degistirilir (sir bulutta bir modele gitmez). Model dosyalari degistirmemeli: calismadan once/sonra calisma agaci parmak izi karsilastirilir.
   Ayni cagri commit mesajini da onerir.

Commit mesajinda ve yapay zekanin ciktisinda da sir/kisisel veri taranir. Yuksek siddetli bulgu, kullanici AYRI AYRI kabul etmedikce gonderimi engeller."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import github

SIDDETLER = ("yuksek", "orta", "dusuk")
BOS_AGAC = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
AZAMI_BAYT = 8_000_000  # git ciktisi (kesilirse belirtilir)
AZAMI_SATIR_DOSYA = 5000
AZAMI_BULGU = 300
AI_METIN_AZAMI = 60_000
YER_TUTUCU = re.compile(r"(?i)(x{4,}|\*{3,}|example|ornek|orne[gğ]in|your[_-]|<[^>]+>|\{[^}]*\}|\$\{|changeme|dummy|placeholder|sample|test|demo|\.\.\.|olmali|buraya|degisken|env\.|process\.env|getenv)")


@dataclass(frozen=True)
class Kural:
    ad: str
    siddet: str
    desen: re.Pattern
    dogrula: Callable[[str], bool] | None = None
    grup: int = 0


def _luhn(s: str) -> bool:
    d = [int(c) for c in s if c.isdigit()]
    if not 13 <= len(d) <= 19 or len(set(d)) == 1:
        return False
    t = 0
    for i, x in enumerate(reversed(d)):
        if i % 2:
            x *= 2
            x -= 9 if x > 9 else 0
        t += x
    return t % 10 == 0


def _tc_kimlik(s: str) -> bool:
    if not re.fullmatch(r"[1-9]\d{10}", s):
        return False
    d = [int(c) for c in s]
    return ((sum(d[0:9:2]) * 7) - sum(d[1:8:2])) % 10 == d[9] and sum(d[:10]) % 10 == d[10]


def _genel_ip(s: str) -> bool:
    try:
        ip = ipaddress.ip_address(s)
    except ValueError:
        return False
    return ip.is_global and not ip.is_multicast and not s.startswith(("0.", "255."))


def _eposta_gercek(s: str) -> bool:
    k = s.lower()
    return not (k.endswith(("@example.com", "@example.org", "@users.noreply.github.com", "@noreply.github.com")) or k.startswith(("noreply@", "no-reply@", "user@", "test@", "ornek@", "adiniz@")))


def _deger_gercek(s: str) -> bool:
    return not YER_TUTUCU.search(s)


def _yol_gercek(s: str) -> bool:
    return not re.search(r"(?i)\\(adiniz|kullanici|user|username|public|default|all users)\\|/(user|username|you|adiniz)/", s)


KURALLAR: tuple[Kural, ...] = (
    Kural("ozel anahtar", "yuksek", re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----")),
    Kural("AWS anahtari", "yuksek", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    Kural("GitHub belirteci", "yuksek", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,})\b")),
    Kural("Slack belirteci", "yuksek", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    Kural("Google API anahtari", "yuksek", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    Kural("API anahtari (sk-)", "yuksek", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}")),
    Kural("Telegram bot belirteci", "yuksek", re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b")),
    Kural("Tailscale anahtari", "yuksek", re.compile(r"\btskey-[A-Za-z0-9-]{10,}")),
    Kural("JWT belirteci", "yuksek", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    Kural("adres icinde parola", "yuksek", re.compile(r"\b[a-z][a-z0-9+.-]*://[^/\s:@'\"]+:([^/\s:@'\"]{3,})@"), _deger_gercek, 1),
    Kural("banka karti numarasi", "yuksek", re.compile(r"(?<![\d.])(?:\d[ -]?){13,19}(?![\d])"), _luhn),
    Kural("IBAN", "yuksek", re.compile(r"\bTR\d{2}(?:\s?\d{4}){5}\s?\d{2}\b")),
    Kural("T.C. kimlik numarasi", "yuksek", re.compile(r"(?<![\d.])[1-9]\d{10}(?![\d])"), _tc_kimlik),
    Kural("parola/anahtar atamasi", "orta", re.compile(r"(?i)\b(?:api[_-]?key|secret|token|passwd|password|parola|sifre|access[_-]?key)\b[\"']?\s*[:=]\s*[\"']([^\"'\s]{8,})[\"']"), _deger_gercek, 1),
    Kural("kullanici klasoru yolu", "orta", re.compile(r"(?i)(?:\b[A-Z]:\\+Users\\+[A-Za-z0-9._-]{2,}\\|/(?:Users|home)/[A-Za-z0-9._-]{2,}/)"), _yol_gercek),
    Kural("e-posta adresi", "orta", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b"), _eposta_gercek),
    Kural("telefon numarasi", "orta", re.compile(r"(?<![\d.])(?:\+90|0090|0)\s?\(?5\d{2}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}(?![\d])")),
    Kural("ozel ag adi (Tailscale)", "orta", re.compile(r"\b[a-z0-9-]+\.tail[0-9a-f]+\.ts\.net\b")),
    Kural("genel IP adresi", "dusuk", re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])"), _genel_ip),
)


@dataclass(frozen=True)
class Bulgu:
    id: str
    tur: str
    siddet: str
    dosya: str
    satir: int
    ornek: str  # MASKELI

    def sozluk(self) -> dict:
        return {"id": self.id, "tur": self.tur, "siddet": self.siddet, "dosya": self.dosya, "satir": self.satir, "ornek": self.ornek, "kaynak": "kural"}


def maskele(deger: str) -> str:
    d = deger.strip()
    return "***" if len(d) <= 6 else f"{d[:3]}…({len(d)} kar.)"


def _id(tur: str, dosya: str, deger: str) -> str:
    return hashlib.sha256(f"{tur}|{dosya}|{deger}".encode("utf-8", "replace")).hexdigest()[:12]


def _eslesmeler(satir: str):
    """(kural, baslangic, bitis, deger) -- grup varsa yalniz grup (sir kismi) esler; dogrulayici reddederse atlanir."""
    for k in KURALLAR:
        for m in k.desen.finditer(satir):
            deger = m.group(k.grup) if k.grup else m.group(0)
            if k.dogrula and not k.dogrula(deger):
                continue
            yield k, m.start(k.grup), m.end(k.grup), deger


def satir_tara(satir: str, dosya: str, no: int) -> list[Bulgu]:
    bulunan, gorulen = [], set()
    for k, b, s, deger in _eslesmeler(satir[:2000]):
        if any(b < ys and s > yb for _, yb, ys in gorulen):  # ayni yeri birden cok kural yakalamasin (kart numarasi / telefon gibi)
            continue
        gorulen.add((k.ad, b, s))
        bulunan.append(Bulgu(_id(k.ad, dosya, deger), k.ad, k.siddet, dosya, no, maskele(deger)))
    return bulunan


def redakte(metin: str) -> str:
    """Modele gidecek metindeki sirlari/kisisel verileri `[GIZLI:tur]` ile degistirir (en sondan basa; ust uste binenler tek sayilir)."""
    sonuc = []
    for satir in metin.split("\n"):
        aralik = []
        for k, b, s, _ in _eslesmeler(satir[:2000]):
            if all(s <= yb or b >= ys for yb, ys, _t in aralik):
                aralik.append((b, s, k.ad))
        for b, s, ad in sorted(aralik, reverse=True):
            satir = satir[:b] + f"[GIZLI:{ad}]" + satir[s:]
        sonuc.append(satir)
    return "\n".join(sonuc)


def dosya_adi_bulgusu(yol: str) -> Bulgu | None:
    if github.gizli_yol_mu(yol):
        return Bulgu(_id("gizli dosya adi", yol, yol), "gizli gorunen dosya", "yuksek", yol, 0, Path(yol).name)
    return None


# ---- diff / icerik toplama ------------------------------------------------------------------------------------------------------------
def eklenenler(diff: str) -> list[tuple[str, int, str]]:
    """`git diff -U0` / `git log -p -U0` ciktisindan EKLENEN satirlar: [(dosya, satir_no, metin)]."""
    sonuc: list[tuple[str, int, str]] = []
    dosya, no, say = "", 0, {}
    for s in diff.split("\n"):
        if s.startswith("+++ "):
            dosya = s[4:].strip()
            dosya = dosya[2:] if dosya.startswith("b/") else dosya
            if dosya == "/dev/null":
                dosya = ""
        elif s.startswith("@@"):
            m = re.search(r"\+(\d+)", s)
            no = int(m.group(1)) if m else 0
        elif s.startswith("+") and not s.startswith("+++") and dosya:
            say[dosya] = say.get(dosya, 0) + 1
            if say[dosya] <= AZAMI_SATIR_DOSYA:
                sonuc.append((dosya, no, s[1:]))
            no += 1
    return sonuc


def _git_cikti(klasor: Path, *args: str) -> tuple[str, bool]:
    """HAM git ciktisi: github._git ciktidaki belirtec desenlerini '***' yapar (gunluk korumasi); tarayici ise sirri GORMELIDIR. Cikti hicbir yere yazilmaz."""
    try:
        s = subprocess.run(["git", "-C", str(klasor), "-c", "core.quotepath=off", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", env=github._ortam(),
                           stdin=subprocess.DEVNULL, timeout=120, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as hata:
        raise github.GithubHatasi(f"git calistirilamadi: {type(hata).__name__}") from None
    if s.returncode != 0:
        raise github.GithubHatasi((github._temizle(s.stderr).strip() or f"git {args[0]} basarisiz")[:300])
    return (s.stdout[:AZAMI_BAYT], len(s.stdout) > AZAMI_BAYT)


def toplam_gonderilecek(klasor: Path) -> dict:
    """Push ile makineden CIKACAK icerik: upstream varsa ondan sonraki commit'lerin eklenen satirlari (commit gecmisi dahil), yoksa tum gecmis."""
    kod, upstream, _ = github._calistir(["git", "-C", str(klasor), "rev-parse", "@{upstream}"])
    upstream = upstream.strip() if kod == 0 else ""
    head = github._git(klasor, "rev-parse", "HEAD", kontrol=False).strip()
    if not head:
        raise github.GithubHatasi("Gonderilecek commit yok (henuz hic commit yapilmamis)")
    aralik = f"{upstream}..HEAD" if upstream else "HEAD"
    sayi = github._git(klasor, "rev-list", "--count", aralik, kontrol=False).strip() or "0"
    diff, kesildi = _git_cikti(klasor, "log", "-p", "-U0", "--no-color", "--no-ext-diff", "--format=@@@commit %h", "-n", "400", aralik)
    return {"eklenen": eklenenler(diff), "commit_sayisi": int(sayi) if sayi.isdigit() else 0, "ilk_gonderim": not upstream, "kesildi": kesildi, "head": head, "upstream": upstream,
            "dosyalar": sorted({d for d, _n, _s in eklenenler(diff)})}


def toplam_commit(klasor: Path, yalniz_hazir: bool) -> dict:
    """Commit'e girecek icerik: hazirlanmis (staged) degisiklikler; yalniz_hazir=False ise commit'in kendiliginden hazirlayacagi (gizli olmayan) tum degisiklikler."""
    eklenen: list[tuple[str, int, str]] = []
    dosyalar: set[str] = set()
    if yalniz_hazir:
        diff, kesildi = _git_cikti(klasor, "diff", "--cached", "-U0", "--no-color", "--no-ext-diff")
        eklenen = eklenenler(diff)
        dosyalar = {y for y in github._git(klasor, "diff", "--cached", "--name-only", "-z").split("\0") if y}
    else:
        kesildi = False
        izlenen, _ = _git_cikti(klasor, "diff", "HEAD", "-U0", "--no-color", "--no-ext-diff") if github._git(klasor, "rev-parse", "--verify", "HEAD", kontrol=False).strip() else _git_cikti(klasor, "diff", "--cached", "-U0", "--no-color", "--no-ext-diff")
        eklenen = eklenenler(izlenen)
        for xy, yol in github._durum_listesi(klasor):
            if github.gizli_yol_mu(yol) or (xy == "??" and github._kendi_dosyasi_mi(yol)):
                continue  # commit bunlari kendisi atlar
            dosyalar.add(yol)
            if xy == "??" and not github._kendi_dosyasi_mi(yol) and not github.gizli_yol_mu(yol):
                p = Path(klasor) / yol
                try:
                    if p.is_file() and p.stat().st_size <= 2_000_000:
                        for i, s in enumerate(p.read_text(encoding="utf-8", errors="strict").split("\n")[:AZAMI_SATIR_DOSYA], 1):
                            eklenen.append((yol, i, s))
                except (OSError, UnicodeDecodeError):
                    continue  # ikili/okunamayan dosya
    return {"eklenen": eklenen, "kesildi": kesildi, "dosyalar": sorted(dosyalar)}


def tara(toplanan: dict) -> list[dict]:
    """Eklenen satirlari ve dosya adlarini tarar; bulgular siddete gore sirali, ayni (tur,dosya,deger) tekrar edilmez."""
    gorulen: dict[str, Bulgu] = {}
    for yol in toplanan.get("dosyalar", []):
        b = dosya_adi_bulgusu(yol)
        if b:
            gorulen.setdefault(b.id, b)
    for dosya, no, satir in toplanan.get("eklenen", []):
        if github.gizli_yol_mu(dosya) and not dosya_adi_bulgusu(dosya):
            continue
        for b in satir_tara(satir, dosya, no):
            gorulen.setdefault(b.id, b)
        if len(gorulen) >= AZAMI_BULGU:
            break
    sira = {s: i for i, s in enumerate(SIDDETLER)}
    return [b.sozluk() for b in sorted(gorulen.values(), key=lambda b: (sira[b.siddet], b.dosya, b.satir))]


# ---- yapay zeka -----------------------------------------------------------------------------------------------------------------------
def ai_metni(toplanan: dict, azami: int = AI_METIN_AZAMI) -> tuple[str, bool]:
    """Modele gidecek, SIRLARI MASKELENMIS ozet: dosya basliklari + eklenen satirlar. (metin, kesildi)"""
    parcalar, uzunluk, dosya, kesildi = [], 0, None, False
    for d, no, s in toplanan.get("eklenen", []):
        satir = f"{no}: {redakte(s)[:400]}"
        if d != dosya:
            parcalar.append(f"### {d}")
            dosya = d
        if uzunluk + len(satir) > azami:
            kesildi = True
            break
        parcalar.append(satir)
        uzunluk += len(satir) + 1
    return "\n".join(parcalar), kesildi


def json_cikar(metin: str) -> dict | None:
    """Model ciktisindaki SON uygun JSON nesnesi ('sorunlar' ya da 'commit_mesaji' anahtarli)."""
    dec = json.JSONDecoder()
    for m in reversed(list(re.finditer(r"\{", metin or ""))):
        try:
            o, _ = dec.raw_decode(metin[m.start():])
        except ValueError:
            continue
        if isinstance(o, dict) and ("sorunlar" in o or "commit_mesaji" in o):
            return o
    return None


def ai_istemi(metin: str, bulgular: list[dict], kesildi: bool, commit_mesaji_iste: bool = True) -> str:
    kural_ozeti = "\n".join(f"- {b['dosya']}:{b['satir']} {b['tur']} ({b['siddet']})" for b in bulgular[:30]) or "(yok)"
    return (
        "ROLUN: gizlilik denetcisi. DOSYALARI DEGISTIRME, arac/komut KULLANMA, dosya OKUMA; yalniz asagidaki metni incele.\n"
        "Asagidaki satirlar GitHub'a gonderilecek. Icinde kisisel veri (ad-soyad, adres, telefon, e-posta, kimlik/hesap numarasi, ozel yol, "
        "ozel kurum/musteri bilgisi, ozel ag adresi) ya da gizli bilgi (anahtar, parola, belirtec) var mi? Zaten maskelenmis [GIZLI:...] yerlerine bakma.\n"
        f"Kural tabanli tarama bunlari buldu:\n{kural_ozeti}\n\n"
        f"GONDERILECEK SATIRLAR{' (uzun oldugu icin kesildi)' if kesildi else ''}:\n{metin}\n\n"
        "Yanitinin SON satiri tek satirlik bir JSON nesnesi olsun, baska hicbir sey yazma:\n"
        '{"sorunlar":[{"dosya":"yol","aciklama":"kisa aciklama","siddet":"yuksek|orta|dusuk"}]'
        + (',"commit_mesaji":"Turkce, ilk satir en cok 72 karakter, yapilan isi anlatan commit mesaji"}' if commit_mesaji_iste else "}")
    )


def temiz_mesaj(m: object) -> str | None:
    if not isinstance(m, str):
        return None
    m = re.sub(r"^```\w*\n?|\n?```$", "", m.strip()).strip()
    if not m or "\x00" in m:
        return None
    return m[:2000]


def ai_sonucu(cikti: str, toplanan: dict, ai_mesaj_iste: bool = True) -> dict:
    """Model ciktisini dogrular: sorunlar normallestirilir; commit mesaji sir/kisisel veri icin TARANIR (bulunursa atilir)."""
    o = json_cikar(cikti)
    if o is None:
        return {"durum": "hata", "neden": "Yapay zeka yaniti okunamadi (JSON yok)", "sorunlar": [], "commit_mesaji": None}
    sorunlar = []
    for s in (o.get("sorunlar") if isinstance(o.get("sorunlar"), list) else [])[:50]:
        if not isinstance(s, dict):
            continue
        siddet = s.get("siddet") if s.get("siddet") in SIDDETLER else "orta"
        dosya, aciklama = str(s.get("dosya", ""))[:200], " ".join(str(s.get("aciklama", "")).split())[:300]
        if aciklama:
            sorunlar.append({"id": _id("yz", dosya, aciklama), "tur": "yapay zeka bulgusu", "siddet": siddet, "dosya": dosya, "satir": 0, "ornek": aciklama, "kaynak": "yapay zeka"})
    mesaj = temiz_mesaj(o.get("commit_mesaji")) if ai_mesaj_iste else None
    if mesaj and any(satir_tara(s, "commit mesaji", 0) for s in mesaj.split("\n")):
        mesaj = None  # model mesaja bir sir/kisisel veri yazmis: kullanilmaz
    return {"durum": "tamam", "neden": None, "sorunlar": sorunlar, "commit_mesaji": mesaj}


def engel_nedenleri(bulgular: list[dict], ai: dict | None = None) -> list[str]:
    """GOZETIMSIZ yayin (otomasyon) icin: kimse bulguyu kabul edemez, bu yuzden yuksek VE orta siddetli her bulgu (kural tabanli ya da yapay zeka) yayini engeller;
    yapay zeka kontrolu verilmisse yapilamamasi da engeldir. Bos liste = yayinlanabilir."""
    nedenler = [f"{b['dosya']}{':' + str(b['satir']) if b.get('satir') else ''} {b['tur']} ({b['siddet']})" for b in bulgular if b.get("siddet") in ("yuksek", "orta")]
    if ai is not None:
        if ai.get("durum") != "tamam":
            nedenler.append(f"yapay zeka kontrolu yapilamadi ({ai.get('neden') or ai.get('durum')})")
        nedenler += [f"{s['dosya']} {s['ornek'][:80]} ({s['siddet']}, yapay zeka)" for s in ai.get("sorunlar", []) if s.get("siddet") in ("yuksek", "orta")]
    return nedenler


def agac_parmak_izi(klasor: Path) -> str:
    """Calisma agacinin durum + fark ozeti: yapay zeka cagrisi dosyalari degistirdi mi anlamak icin (yalniz git, gizli dosya icerigi okunmaz)."""
    durum = github._git(klasor, "status", "--porcelain=v1", "-z", "--untracked-files=all", kontrol=False)
    fark = github._git(klasor, "diff", "HEAD", "--no-color", "--no-ext-diff", kontrol=False) if github._git(klasor, "rev-parse", "--verify", "HEAD", kontrol=False).strip() else ""
    return hashlib.sha256((durum + "\0" + fark).encode("utf-8", "replace")).hexdigest()
