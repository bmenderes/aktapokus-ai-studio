"""GitHub entegrasyonu: bilgisayardaki `gh` (GitHub CLI) oturumunu ve `git`i kullanir. Token'a DOKUNMAZ, saklamaz, gormez.

Kapsam: depo listele/klonla, projede commit/dal/push, pull request ac + durumu, issue listele/oku/yorumla.

Guvenlik:
- Yazan her islem (klonla, commit, push, PR, issue yorumu) YALNIZ yerel, belirtecli arayuzde kullanicinin tikladigi dugmeden gelir (Telegram'dan degil);
  arayuz neyin yapilacagini onay penceresinde gosterir. Burada hicbir sey kendiliginden yapilmaz.
- Komutlar dizi olarak calistirilir (kabuk yok); kullanici/issue metinleri bayrak degeri olarak gecer. Klonlama yalniz `sahip/depo` biciminde
  (rastgele URL, `ext::`/`file:` kullanilmaz). Zorla push (`--force`) YOKTUR.
- Commit'e gizli gorunen dosyalar (.env*, *.pem, id_rsa, .npmrc...) ve Aktapokus'un kendi izlenmeyen dosyalari (.aktapokus/, .opencode/) GIRMEZ;
  hazirlanmis (staged) gizli dosya varsa commit reddedilir. Kimlik/token benzeri dizgeler ciktilardan ayiklanir.
- Etkilesim yok: GIT_TERMINAL_PROMPT=0, GH_PROMPT_DISABLED=1 (kimlik sorusunda donup kalmaz, hata verir)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

GH_ORTAMI = "AKTAPOKUS_GH"
DEPO_DESENI = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}$")
DAL_DESENI = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,99}$")
AD_DESENI = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
GIZLI_UZANTILAR = (".pem", ".key", ".pfx", ".p12", ".keystore", ".jks", ".token", ".secret")
GIZLI_ADLAR = ("id_rsa", "id_ed25519", "id_ecdsa", "id_dsa", ".npmrc", ".pypirc", "credentials", ".netrc", ".env", "secrets.", "secret.")
KENDI_DIZINLERI = (".aktapokus/", ".opencode/")
TOKEN_DESENI = re.compile(r"(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|x-access-token:[^@\s]+)")
AZAMI_MESAJ = 5000
AZAMI_DOSYA = 5000


class GithubHatasi(Exception):
    pass


def gh_bul() -> str | None:
    ortam = os.environ.get(GH_ORTAMI)
    if ortam:
        return ortam if Path(ortam).is_file() else None
    yol = shutil.which("gh")
    if yol:
        return yol
    for aday in (r"C:\Program Files\GitHub CLI\gh.exe", r"C:\Program Files (x86)\GitHub CLI\gh.exe"):
        if Path(aday).is_file():
            return aday
    return None


def _temizle(metin: str) -> str:
    return TOKEN_DESENI.sub("***", metin or "")


def _calistir(argv: list[str], klasor: Path | None = None, zaman_asimi: int = 60, girdi: str | None = None) -> tuple[int, str, str]:
    ortam = os.environ.copy()
    ortam.update({"GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never", "GH_PROMPT_DISABLED": "1", "GH_NO_UPDATE_NOTIFIER": "1", "NO_COLOR": "1", "GH_SPINNER_DISABLED": "1"})
    bayrak = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        s = subprocess.run(
            argv, cwd=str(klasor) if klasor else None, capture_output=True, text=True, encoding="utf-8", errors="replace", env=ortam,
            input=girdi, stdin=None if girdi is not None else subprocess.DEVNULL, timeout=zaman_asimi, creationflags=bayrak,
        )
    except FileNotFoundError:
        raise GithubHatasi(f"Program bulunamadi: {argv[0]}") from None
    except subprocess.TimeoutExpired:
        raise GithubHatasi(f"Zaman asimi ({zaman_asimi} sn): {Path(argv[0]).stem} {argv[1] if len(argv) > 1 else ''}") from None
    return s.returncode, _temizle(s.stdout), _temizle(s.stderr)


def _git(klasor: Path, *args: str, zaman_asimi: int = 60, girdi: str | None = None, kontrol: bool = True) -> str:
    kod, cikti, hata = _calistir(["git", "-C", str(klasor), "-c", "core.quotepath=off", *args], None, zaman_asimi, girdi)
    if kontrol and kod != 0:
        raise GithubHatasi((hata.strip() or cikti.strip() or f"git {args[0]} basarisiz")[:600])
    return cikti


def _gh_calistir(args: tuple[str, ...], klasor: Path | None, zaman_asimi: int) -> tuple[int, str, str]:
    gh = gh_bul()
    if not gh:
        raise GithubHatasi("GitHub CLI (gh) bulunamadi. https://cli.github.com adresinden kurup `gh auth login` calistirin.")
    onek = [sys.executable, gh] if gh.lower().endswith(".py") else [gh]  # AKTAPOKUS_GH bir .py betigini (deneme) de gosterebilir
    return _calistir([*onek, *args], klasor, zaman_asimi)


def _gh(*args: str, klasor: Path | None = None, zaman_asimi: int = 60, kontrol: bool = True) -> str:
    kod, cikti, hata = _gh_calistir(args, klasor, zaman_asimi)
    if kontrol and kod != 0:
        mesaj = (hata.strip() or cikti.strip() or f"gh {args[0]} basarisiz")
        if "auth login" in mesaj or "not logged" in mesaj.lower() or "authentication" in mesaj.lower():
            mesaj = "GitHub'a giris yapilmamis. Bir terminalde `gh auth login` calistirin."
        raise GithubHatasi(mesaj[:600])
    return cikti


def _json(metin: str):
    try:
        return json.loads(metin)
    except json.JSONDecodeError:
        raise GithubHatasi("GitHub yaniti okunamadi") from None


# ---- hesap / depolar --------------------------------------------------------------------------------------------------
def durum() -> dict:
    """{kurulu, giris, hesap, hata}: etkin gh hesabi (arayuz hangi hesapla islem yapildigini hep gostersin)."""
    if not gh_bul():
        return {"kurulu": False, "giris": False, "hesap": None, "hata": "GitHub CLI (gh) kurulu degil"}
    try:
        k = _json(_gh("api", "user"))
    except GithubHatasi as hata:
        return {"kurulu": True, "giris": False, "hesap": None, "hata": str(hata)}
    return {"kurulu": True, "giris": True, "hesap": k.get("login"), "ad": k.get("name"), "hata": None}


def depolar(adet: int = 50) -> list[dict]:
    adet = max(1, min(int(adet), 100))
    v = _json(_gh("repo", "list", "--limit", str(adet), "--json", "nameWithOwner,description,isPrivate,updatedAt,url", zaman_asimi=90))
    return [{"depo": d.get("nameWithOwner"), "aciklama": d.get("description") or "", "ozel": bool(d.get("isPrivate")), "guncelleme": d.get("updatedAt"), "url": d.get("url")} for d in v if isinstance(d, dict)]


def klonla(depo: object, ust_klasor: object, ad: object = None) -> Path:
    if not isinstance(depo, str) or not DEPO_DESENI.match(depo):
        raise GithubHatasi("Depo 'sahip/ad' biciminde olmali (ornek: bmenderes/aktapokus-ajan)")
    ust = Path(str(ust_klasor)).expanduser()
    if not ust.is_absolute() or not ust.is_dir():
        raise GithubHatasi("Klonlanacak ust klasor TAM yol olmali ve var olmali")
    ad = ad if ad not in (None, "") else depo.split("/", 1)[1]
    if not isinstance(ad, str) or not AD_DESENI.match(ad):
        raise GithubHatasi("Klasor adi harf/rakam/./-/_ icermeli (yol isareti ve bosluk yok)")
    hedef = ust / ad
    if hedef.exists():
        raise GithubHatasi(f"Bu klasor zaten var: {hedef}")
    _gh("repo", "clone", depo, str(hedef), zaman_asimi=900)
    if not hedef.is_dir():
        raise GithubHatasi("Klonlama tamamlandi gorunuyor ama klasor olusmadi")
    return hedef


# ---- proje (klasor) islemleri -----------------------------------------------------------------------------------------
def gizli_yol_mu(yol: str) -> bool:
    for p in yol.replace("\\", "/").split("/"):
        k = p.lower()
        if k.endswith(GIZLI_UZANTILAR) or any(k.startswith(a) for a in GIZLI_ADLAR):
            return True
    return False


def _kendi_dosyasi_mi(yol: str) -> bool:
    y = yol.replace("\\", "/") + ("/" if not yol.endswith("/") else "")
    return any(y.startswith(d) for d in KENDI_DIZINLERI)


def _durum_listesi(klasor: Path) -> list[tuple[str, str]]:
    """[(XY, yol)] -- git status --porcelain=v1 -z (yeniden adlandirmada yeni yol)."""
    ham = _git(klasor, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    parcalar = ham.split("\0")
    sonuc: list[tuple[str, str]] = []
    i = 0
    while i < len(parcalar) and len(sonuc) < AZAMI_DOSYA:
        p = parcalar[i]
        i += 1
        if len(p) < 4:
            continue
        xy, yol = p[:2], p[3:]
        if "R" in xy or "C" in xy:
            i += 1  # bir sonraki parca eski yol
        sonuc.append((xy, yol))
    return sonuc


def _uzak_bilgi(klasor: Path) -> dict:
    url = _git(klasor, "remote", "get-url", "origin", kontrol=False).strip()
    m = re.search(r"github\.com[:/]+([^/\s]+)/([^/\s]+?)(?:\.git)?/?$", url) if url else None
    return {"url": re.sub(r"//[^/@]+@", "//", url), "sahip": m.group(1) if m else None, "depo": f"{m.group(1)}/{m.group(2)}" if m else None}


def proje_durumu(klasor: Path) -> dict:
    if _git(klasor, "rev-parse", "--is-inside-work-tree", kontrol=False).strip() != "true":
        raise GithubHatasi("Bu klasor bir git deposu degil")
    dal = _git(klasor, "branch", "--show-current", kontrol=False).strip()
    uzak = _uzak_bilgi(klasor)
    onde = geride = None
    if dal:
        kod, cikti, _ = _calistir(["git", "-C", str(klasor), "rev-list", "--left-right", "--count", "@{upstream}...HEAD"])
        if kod == 0 and cikti.split():
            geride, onde = (int(x) for x in cikti.split()[:2])
    degisen = []
    for xy, yol in _durum_listesi(klasor):
        if xy == "??" and _kendi_dosyasi_mi(yol):
            continue  # Aktapokus'un kendi izlenmeyen dosyalari (ayar/kayit/koruyucu) listede ve commit'te yok
        degisen.append({"durum": xy.strip() or "?", "yol": yol, "gizli": gizli_yol_mu(yol)})
    return {
        "dal": dal or None, "uzak": uzak, "onde": onde, "geride": geride, "upstream": onde is not None,
        "degisen": degisen[:200], "degisen_sayisi": len(degisen), "gizli_sayisi": sum(1 for d in degisen if d["gizli"]),
        "kimlik": {"ad": _git(klasor, "config", "user.name", kontrol=False).strip() or None, "eposta": _git(klasor, "config", "user.email", kontrol=False).strip() or None},
    }


def commit(klasor: Path, mesaj: object) -> dict:
    if not isinstance(mesaj, str) or not mesaj.strip() or len(mesaj) > AZAMI_MESAJ or "\x00" in mesaj:
        raise GithubHatasi(f"Commit mesaji bos olmayan metin olmali (en cok {AZAMI_MESAJ} karakter)")
    if not _git(klasor, "config", "user.email", kontrol=False).strip() or not _git(klasor, "config", "user.name", kontrol=False).strip():
        raise GithubHatasi("git kimligi tanimli degil. Bir terminalde: git config --global user.name \"Adiniz\" ve git config --global user.email \"eposta\"")
    secilen, atlanan = [], []
    for xy, yol in _durum_listesi(klasor):
        if xy == "??" and _kendi_dosyasi_mi(yol):
            continue
        (atlanan if gizli_yol_mu(yol) else secilen).append(yol)
    hazir = [y for y in _git(klasor, "diff", "--cached", "--name-only", "-z").split("\0") if y]
    hazir_gizli = [y for y in hazir if gizli_yol_mu(y)]
    if hazir_gizli:
        raise GithubHatasi(f"Hazirlanmis (staged) gizli gorunen dosya var, commit yapilmadi: {', '.join(hazir_gizli[:3])}. Once `git reset -- <dosya>` ile cikarin.")
    if not secilen and not hazir:
        raise GithubHatasi("Commit edilecek degisiklik yok" + (f" (gizli gorunen {len(atlanan)} dosya atlandi)" if atlanan else ""))
    if secilen:
        _git(klasor, "add", "--pathspec-from-file=-", "--pathspec-file-nul", girdi="\0".join(secilen) + "\0")
    _git(klasor, "commit", "-m", mesaj.strip(), zaman_asimi=120)
    sha = _git(klasor, "rev-parse", "--short", "HEAD").strip()
    return {"commit": sha, "dosya_sayisi": len(secilen) or len(hazir), "atlanan_gizli": atlanan[:20]}


def dal_olustur(klasor: Path, ad: object) -> dict:
    if not isinstance(ad, str) or not DAL_DESENI.match(ad) or ".." in ad or ad.endswith(("/", ".lock", ".")):
        raise GithubHatasi("Dal adi harf/rakam/./_/-// icermeli, '-' ile baslamamali (ornek: ozellik/giris)")
    kod, _, _ = _calistir(["git", "check-ref-format", "--branch", ad])
    if kod != 0:
        raise GithubHatasi("Gecersiz dal adi")
    _git(klasor, "switch", "-c", ad)
    return {"dal": ad}


def push(klasor: Path) -> dict:
    """Etkin dali origin'e gonderir (yoksa upstream kurar). ZORLA push yok."""
    dal = _git(klasor, "branch", "--show-current", kontrol=False).strip()
    if not dal:
        raise GithubHatasi("Bir dalda degilsiniz (detached HEAD); once dal olusturun")
    if not _uzak_bilgi(klasor)["url"]:
        raise GithubHatasi("'origin' uzak deposu tanimli degil")
    kod, _, _ = _calistir(["git", "-C", str(klasor), "rev-parse", "--abbrev-ref", "@{upstream}"])
    args = ["push"] if kod == 0 else ["push", "-u", "origin", "HEAD"]
    cikti = _git(klasor, *args, zaman_asimi=300)
    return {"dal": dal, "yeni_upstream": kod != 0, "cikti": cikti.strip()[-400:]}


def pr_ac(klasor: Path, baslik: object, govde: object, taslak: object = False) -> dict:
    if not isinstance(baslik, str) or not baslik.strip() or len(baslik) > 256 or "\n" in baslik or "\x00" in baslik:
        raise GithubHatasi("PR basligi tek satirlik, bos olmayan metin olmali (en cok 256 karakter)")
    govde = govde if isinstance(govde, str) else ""
    if len(govde) > 20000 or "\x00" in govde:
        raise GithubHatasi("PR aciklamasi cok uzun (en cok 20000 karakter)")
    args = ["pr", "create", "--title", baslik.strip(), "--body", govde]
    if taslak:
        args.append("--draft")
    cikti = _gh(*args, klasor=klasor, zaman_asimi=120)
    m = re.findall(r"https://github\.com/\S+/pull/\d+", cikti)
    if not m:
        raise GithubHatasi("PR olusturuldu mu belirsiz: " + cikti.strip()[-200:])
    return {"url": m[-1]}


def pr_durumu(klasor: Path) -> dict | None:
    """Etkin dalin PR'i (yoksa None): durum, taslak mi, CI ozeti."""
    kod, cikti, hata = _gh_calistir(("pr", "view", "--json", "number,title,state,url,isDraft,reviewDecision,statusCheckRollup"), klasor, 60)
    if kod != 0:
        if "no pull requests found" in (hata + cikti).lower():
            return None
        raise GithubHatasi((hata.strip() or cikti.strip())[:300])
    v = _json(cikti)
    kontroller = v.get("statusCheckRollup") or []
    ozet = {"basarili": 0, "basarisiz": 0, "bekleyen": 0}
    for k in kontroller:
        sonuc = str(k.get("conclusion") or k.get("state") or "").upper()
        durum = str(k.get("status") or "").upper()
        if sonuc in ("SUCCESS", "NEUTRAL", "SKIPPED"):
            ozet["basarili"] += 1
        elif sonuc in ("FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED"):
            ozet["basarisiz"] += 1
        elif sonuc in ("PENDING", "") or durum in ("IN_PROGRESS", "QUEUED", "PENDING"):
            ozet["bekleyen"] += 1
    return {"no": v.get("number"), "baslik": v.get("title"), "durum": v.get("state"), "url": v.get("url"), "taslak": bool(v.get("isDraft")), "inceleme": v.get("reviewDecision"), "kontroller": ozet}


# ---- issue'lar --------------------------------------------------------------------------------------------------------
def _no(no: object) -> str:
    if isinstance(no, bool) or not isinstance(no, (int, str)) or not re.fullmatch(r"[0-9]{1,7}", str(no)):
        raise GithubHatasi("Issue numarasi sayi olmali")
    return str(int(no))


def issueler(klasor: Path, adet: int = 30) -> list[dict]:
    v = _json(_gh("issue", "list", "--limit", str(max(1, min(int(adet), 100))), "--json", "number,title,state,labels,url,updatedAt", klasor=klasor, zaman_asimi=90))
    return [{"no": i.get("number"), "baslik": i.get("title"), "durum": i.get("state"), "etiketler": [l.get("name") for l in i.get("labels") or []], "url": i.get("url"), "guncelleme": i.get("updatedAt")} for i in v if isinstance(i, dict)]


def issue_oku(klasor: Path, no: object, azami_govde: int = 6000) -> dict:
    i = _json(_gh("issue", "view", _no(no), "--json", "number,title,body,url,state", klasor=klasor))
    govde = i.get("body") or ""
    return {"no": i.get("number"), "baslik": i.get("title"), "govde": govde[:azami_govde], "kesildi": len(govde) > azami_govde, "url": i.get("url"), "durum": i.get("state")}


def issue_yorum(klasor: Path, no: object, metin: object) -> dict:
    if not isinstance(metin, str) or not metin.strip() or len(metin) > 4000 or "\x00" in metin:
        raise GithubHatasi("Yorum bos olmayan metin olmali (en cok 4000 karakter)")
    cikti = _gh("issue", "comment", _no(no), "--body", metin.strip(), klasor=klasor, zaman_asimi=90)
    m = re.findall(r"https://github\.com/\S+", cikti)
    return {"url": m[-1] if m else None}
