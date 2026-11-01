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

import contextlib
import contextvars
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

GH_ORTAMI = "AKTAPOKUS_GH"
GH_DIZIN_ORTAMI = "AKTAPOKUS_GH_DIZIN"  # uygulamaya ozel gh oturum klasoru (varsayilan ~/.aktapokus/gh)
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


def gh_dizini() -> Path:
    ortam = os.environ.get(GH_DIZIN_ORTAMI)
    return Path(ortam) if ortam else Path.home() / ".aktapokus" / "gh"


# ---- birden cok hesap: ek hesaplar `<gh klasoru>-hesaplar/<kullanici>` altinda kendi oturumlariyla durur; depo sahibi ek hesapla eslesirse o hesap kullanilir ----
_HESAP: contextvars.ContextVar[str | None] = contextvars.ContextVar("aktapokus_gh_hesap", default=None)  # None: depo sahibine gore otomatik, "": varsayilan hesap, ad: o ek hesap
YENI_HESAP = "_yeni"
_sahip_onbellek: dict[str, tuple[float, str | None]] = {}


def hesaplar_dizini() -> Path:
    d = gh_dizini()
    return d.with_name(d.name + "-hesaplar")


def ek_hesaplar() -> list[str]:
    """Aktapokus'a giris yapilmis ek hesaplarin (kucuk harfli) kullanici adlari."""
    try:
        return sorted(d.name for d in hesaplar_dizini().iterdir() if d.is_dir() and d.name != YENI_HESAP and (d / "hosts.yml").is_file())
    except OSError:
        return []


@contextlib.contextmanager
def hesapla(ad: str | None):
    """Blok icindeki gh/git cagrilarini `ad` ek hesabiyla ('' = varsayilan hesap) yapar."""
    j = _HESAP.set(ad)
    try:
        yield
    finally:
        _HESAP.reset(j)


def _sahibin_hesabi(depo_ya_da_sahip: str) -> str | None:
    sahip = depo_ya_da_sahip.split("/", 1)[0].lower()
    return sahip if sahip in ek_hesaplar() else None


def _klasor_sahibi(klasor: str) -> str | None:
    """Klasorun origin adresindeki sahip adi (hesap yonlendirmesi icin; ham git, gh oturumu gerekmez)."""
    simdi = time.monotonic()
    eski = _sahip_onbellek.get(klasor)
    if eski and simdi - eski[0] < 10:
        return eski[1]
    sahip = None
    try:
        s = subprocess.run(["git", "-C", klasor, "remote", "get-url", "origin"], capture_output=True, text=True, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL, timeout=10,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        m = re.search(r"github\.com[:/]+([^/\s]+)/", s.stdout.strip()) if s.returncode == 0 else None
        sahip = m.group(1) if m else None
    except (OSError, subprocess.TimeoutExpired):
        pass
    _sahip_onbellek[klasor] = (simdi, sahip)
    return sahip


def _dizin_sec(argv: list[str], klasor: Path | None) -> Path:
    """Bu cagrinin gh oturum klasoru: acik secim > klasorun origin sahibi (ek hesapla eslesirse) > varsayilan."""
    secim = _HESAP.get()
    if secim is None:
        ek = ek_hesaplar()
        yol = str(klasor) if klasor else (argv[argv.index("-C") + 1] if "-C" in argv[:-1] else None)
        sahip = _klasor_sahibi(yol) if ek and yol else None
        secim = sahip.lower() if sahip and sahip.lower() in ek else ""
    return hesaplar_dizini() / secim if secim else gh_dizini()


def _ortam(dizin: Path | None = None) -> dict:
    """gh/git ortami: Aktapokus'un KENDI GitHub oturumu (gh_dizini); sistemdeki gh hesabi ve GH_TOKEN/GITHUB_TOKEN kullanilmaz.
    git'in github.com kimlik yardimcisi bu oturuma bagli gh olur (push/klon ayni hesapla)."""
    ortam = os.environ.copy()
    for k in ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN"):
        ortam.pop(k, None)
    ortam.update({"GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never", "GH_PROMPT_DISABLED": "1", "GH_NO_UPDATE_NOTIFIER": "1", "NO_COLOR": "1", "GH_SPINNER_DISABLED": "1",
                  "GH_CONFIG_DIR": str(dizin or gh_dizini())})
    gh = gh_bul()
    if gh and not gh.lower().endswith(".py"):
        ortam.update({"GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "credential.https://github.com.helper", "GIT_CONFIG_VALUE_0": "",
                      "GIT_CONFIG_KEY_1": "credential.https://github.com.helper", "GIT_CONFIG_VALUE_1": '!"' + gh.replace("\\", "/") + '" auth git-credential'})
    return ortam


def _calistir(argv: list[str], klasor: Path | None = None, zaman_asimi: int = 60, girdi: str | None = None) -> tuple[int, str, str]:
    ortam = _ortam(_dizin_sec(argv, klasor))
    if argv[:1] == ["git"] and "core.fsmonitor=false" not in argv:  # depo yapilandirmasi guvenilmez: .git/config'teki core.fsmonitor=<komut> her git status'ta calisirdi
        argv = [argv[0], "-c", "core.fsmonitor=false", *argv[1:]]
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
    kod, cikti, hata = _calistir(["git", "-C", str(klasor), "-c", "core.quotepath=off", "-c", "core.fsmonitor=false", *args], None, zaman_asimi, girdi)
    if kontrol and kod != 0:
        raise GithubHatasi((hata.strip() or cikti.strip() or f"git {args[0]} basarisiz")[:600])
    return cikti


def _gh_calistir(args: tuple[str, ...], klasor: Path | None, zaman_asimi: int) -> tuple[int, str, str]:
    gh = gh_bul()
    if not gh:
        raise GithubHatasi("GitHub CLI (gh) bulunamadi. https://cli.github.com adresinden kurun.")
    onek = [sys.executable, gh] if gh.lower().endswith(".py") else [gh]  # AKTAPOKUS_GH bir .py betigini (deneme) de gosterebilir
    return _calistir([*onek, *args], klasor, zaman_asimi)


def _gh(*args: str, klasor: Path | None = None, zaman_asimi: int = 60, kontrol: bool = True) -> str:
    kod, cikti, hata = _gh_calistir(args, klasor, zaman_asimi)
    if kontrol and kod != 0:
        mesaj = (hata.strip() or cikti.strip() or f"gh {args[0]} basarisiz")
        if "auth login" in mesaj or "not logged" in mesaj.lower() or "authentication" in mesaj.lower():
            mesaj = "GitHub'a giris yapilmamis. Ayarlar > Hesaplar > GitHub'dan giris yapin."
        raise GithubHatasi(mesaj[:600])
    return cikti


def _json(metin: str):
    try:
        return json.loads(metin)
    except json.JSONDecodeError:
        raise GithubHatasi("GitHub yaniti okunamadi") from None


# ---- uygulamaya ozel giris (cihaz kodu): `gh auth login --web`, belirtec Aktapokus'un kendi gh klasorunde (gh_dizini) kalir ----
KOD_DESENI = re.compile(r"\b([A-Z0-9]{4}-[A-Z0-9]{4})\b")
GIRIS_ADRESI = "https://github.com/login/device"
GIRIS_AZAMI_SN = 15 * 60
_giris_kilit = threading.Lock()
_giris: dict = {}


def _giris_oku(surec: subprocess.Popen, g: dict) -> None:
    try:
        for satir in surec.stdout:  # type: ignore[union-attr]
            if g.get("surec") is not surec:  # yeni giris baslatildi: eski surecin ciktisi yeni durumu bozmasin
                return
            m = KOD_DESENI.search(satir)
            if m and not g.get("kod") and ("code" in satir.lower() or "kod" in satir.lower()):
                g["kod"] = m.group(1)
            g["cikti"] = (g.get("cikti", "") + _temizle(satir))[-600:]
    except (OSError, ValueError):
        pass


def giris_baslat(ek: bool = False) -> dict:
    """Cihaz kodu akisini baslatir: {kod, adres}. Kullanici adresi acip kodu girer; sonucu giris_durumu() verir.
    ek=True: varsayilan hesaba DOKUNMADAN ikinci bir hesap eklenir (giris bitince kullanici adiyla ek hesaplar arasina alinir)."""
    gh = gh_bul()
    if not gh:
        raise GithubHatasi("GitHub CLI (gh) bulunamadi. https://cli.github.com adresinden kurun.")
    giris_iptal()
    dizin = hesaplar_dizini() / YENI_HESAP if ek else gh_dizini()
    if ek:
        shutil.rmtree(dizin, ignore_errors=True)  # yarim kalmis onceki ek giris denemesi
    dizin.mkdir(parents=True, exist_ok=True)
    onek = [sys.executable, gh] if gh.lower().endswith(".py") else [gh]
    surec = subprocess.Popen([*onek, "auth", "login", "--hostname", "github.com", "--git-protocol", "https", "--web", "--skip-ssh-key"], stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", env=_ortam(dizin), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    with _giris_kilit:
        _giris.clear()
        _giris.update({"surec": surec, "kod": None, "cikti": "", "baslangic": time.time(), "iptal": False, "ek": ek})
    g = _giris  # okuyucu iplik ve durum sorgusu AYNI sozlugu kullanir
    threading.Thread(target=_giris_oku, args=(surec, g), daemon=True).start()
    bitis = time.time() + 20
    while time.time() < bitis and not g["kod"] and surec.poll() is None:
        time.sleep(0.1)
    if not g["kod"]:
        giris_iptal()
        raise GithubHatasi("GitHub giris kodu alinamadi: " + (g["cikti"].strip()[:300] or "gh yanit vermedi"))
    return {"kod": g["kod"], "adres": GIRIS_ADRESI}


def giris_durumu() -> dict:
    """{durum: yok|bekliyor|tamam|hata|iptal, kod, adres, hesap}"""
    with _giris_kilit:
        g = dict(_giris)
    if not g:
        return {"durum": "yok"}
    surec = g["surec"]
    kod = surec.poll()
    if kod is None:
        if time.time() - g["baslangic"] > GIRIS_AZAMI_SN:
            giris_iptal()
            return {"durum": "hata", "hata": "Giris suresi doldu; yeniden baslatin."}
        return {"durum": "bekliyor", "kod": g["kod"], "adres": GIRIS_ADRESI}
    if g.get("iptal"):
        return {"durum": "iptal"}
    if kod == 0:
        if g.get("ek"):
            return _ek_tamamla()
        return {"durum": "tamam", **{k: v for k, v in durum().items() if k in ("giris", "hesap", "ad")}}
    return {"durum": "hata", "hata": (g.get("cikti", "").strip() or "Giris basarisiz")[:300]}


def giris_iptal() -> dict:
    with _giris_kilit:
        g = _giris.get("surec")
        if _giris:
            _giris["iptal"] = True
    if g is not None and g.poll() is None:
        try:
            g.kill()
        except OSError:
            pass
    return {"tamam": True}


def _ek_tamamla() -> dict:
    """Ek hesap girisi bitti: kullanici adini oku, `_yeni` klasorunu o ada tasi. Varsayilanla ayni hesapsa eklenmez."""
    yeni = hesaplar_dizini() / YENI_HESAP
    try:
        with hesapla(YENI_HESAP):
            login = _json(_gh("api", "user")).get("login")
        if not isinstance(login, str) or not SAHIP_DESENI.fullmatch(login):
            raise GithubHatasi("Hesap adi okunamadi")
        with hesapla(""):
            varsayilan = durum().get("hesap")
        if varsayilan and varsayilan.lower() == login.lower():
            raise GithubHatasi(f"@{login} zaten varsayilan hesap olarak bagli")
        hedef = hesaplar_dizini() / login.lower()
        shutil.rmtree(hedef, ignore_errors=True)
        yeni.rename(hedef)
    except GithubHatasi as h:
        shutil.rmtree(yeni, ignore_errors=True)
        return {"durum": "hata", "hata": str(h)[:300]}
    return {"durum": "tamam", "giris": True, "hesap": login, "ek": True}


def cikis(hesap: object = None) -> dict:
    """Aktapokus'un GitHub oturumunu kapatir (yalniz kendi gh klasoru; sistemdeki gh hesabina dokunmaz). hesap verilirse yalniz o ek hesap kapatilir."""
    giris_iptal()
    if hesap not in (None, ""):
        if not isinstance(hesap, str) or hesap.lower() not in ek_hesaplar():
            raise GithubHatasi("Bu ek hesap bulunamadi")
        with hesapla(hesap.lower()):
            if gh_bul():
                _gh_calistir(("auth", "logout", "--hostname", "github.com"), None, 30)
        shutil.rmtree(hesaplar_dizini() / hesap.lower(), ignore_errors=True)
        return {"tamam": True}
    with hesapla(""):
        if gh_bul():
            _gh_calistir(("auth", "logout", "--hostname", "github.com"), None, 30)
    hosts = gh_dizini() / "hosts.yml"
    try:
        hosts.unlink()
    except OSError:
        pass
    return {"tamam": True}


# ---- hesap / depolar --------------------------------------------------------------------------------------------------
def durum() -> dict:
    """{kurulu, giris, hesap, hata}: etkin gh hesabi (arayuz hangi hesapla islem yapildigini hep gostersin)."""
    if not gh_bul():
        return {"kurulu": False, "giris": False, "hesap": None, "hata": "GitHub CLI (gh) kurulu degil"}
    try:
        k = _json(_gh("api", "user"))
    except GithubHatasi as hata:
        return {"kurulu": True, "giris": False, "hesap": None, "hata": str(hata)}
    return {"kurulu": True, "giris": True, "hesap": k.get("login"), "ad": k.get("name"), "hata": None, "ekler": ek_hesaplar()}


SAHIP_DESENI = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
AZAMI_SAHIP = 20


def depolar(adet: int = 100) -> list[dict]:
    """Varsayilan VE ek hesaplarin depolari (bir hesap hata verirse kalanlar gosterilir; hepsi hata verirse ilk hata iletilir)."""
    sonuc: dict[str, dict] = {}
    ilk_hata: GithubHatasi | None = None
    for ad in ("", *ek_hesaplar()):
        try:
            with hesapla(ad):
                for d in _hesap_depolari(adet):
                    sonuc.setdefault(d["depo"], d)
        except GithubHatasi as h:
            ilk_hata = ilk_hata or h
    if not sonuc and ilk_hata:
        raise ilk_hata
    return sorted(sonuc.values(), key=lambda x: x.get("guncelleme") or "", reverse=True)


def _hesap_depolari(adet: int = 100) -> list[dict]:
    """Kendi hesabinin VE uye oldugu organizasyonlarin depolari (GERCEK EKSIK: yalniz kendi hesabi listeleniyordu; asil depolar organizasyondaydi).
    Organizasyon listesi okunamazsa ya da bir organizasyon hata verirse kalanlar yine gosterilir; kendi hesabinin hatasi iletilir."""
    adet = max(1, min(int(adet), 100))
    sahipler: list[str | None] = [None]
    try:
        for o in _json(_gh("api", "user/orgs?per_page=100", zaman_asimi=60)):
            giris = o.get("login") if isinstance(o, dict) else None
            if isinstance(giris, str) and SAHIP_DESENI.fullmatch(giris):
                sahipler.append(giris)
    except GithubHatasi:
        pass
    sonuc: dict[str, dict] = {}
    for sahip in sahipler[:AZAMI_SAHIP]:
        args = ("repo", "list", *((sahip,) if sahip else ()), "--limit", str(adet), "--json", "nameWithOwner,description,isPrivate,updatedAt,url")
        try:
            v = _json(_gh(*args, zaman_asimi=90))
        except GithubHatasi:
            if sahip is None:
                raise
            continue
        for d in v:
            if isinstance(d, dict) and isinstance(d.get("nameWithOwner"), str):
                sonuc.setdefault(d["nameWithOwner"], {"depo": d["nameWithOwner"], "aciklama": d.get("description") or "", "ozel": bool(d.get("isPrivate")), "guncelleme": d.get("updatedAt"), "url": d.get("url")})
    return sorted(sonuc.values(), key=lambda x: x.get("guncelleme") or "", reverse=True)


def klonla(depo: object, ust_klasor: object, ad: object = None) -> Path:
    if not isinstance(depo, str) or not DEPO_DESENI.fullmatch(depo):
        raise GithubHatasi("Depo 'sahip/ad' biciminde olmali (ornek: bmenderes/aktapokus-ai-studio)")
    ust = Path(str(ust_klasor)).expanduser()
    if not ust.is_absolute() or not ust.is_dir():
        raise GithubHatasi("Klonlanacak ust klasor TAM yol olmali ve var olmali")
    ad = ad if ad not in (None, "") else depo.split("/", 1)[1]
    if not isinstance(ad, str) or not AD_DESENI.fullmatch(ad):
        raise GithubHatasi("Klasor adi harf/rakam/./-/_ icermeli (yol isareti ve bosluk yok)")
    hedef = ust / ad
    if hedef.exists():
        raise GithubHatasi(f"Bu klasor zaten var: {hedef}")
    with hesapla(_sahibin_hesabi(depo) or ""):
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
        degisen.append({"durum": xy.strip() or "?", "yol": yol, "gizli": gizli_yol_mu(yol), "hazir": xy[:1] not in (" ", "?"), "calisma": xy[1:2] != " "})
    return {
        "dal": dal or None, "uzak": uzak, "onde": onde, "geride": geride, "upstream": onde is not None,
        "degisen": degisen[:200], "degisen_sayisi": len(degisen), "gizli_sayisi": sum(1 for d in degisen if d["gizli"]), "hazir_sayisi": sum(1 for d in degisen if d["hazir"]),
        "kimlik": {"ad": _git(klasor, "config", "user.name", kontrol=False).strip() or None, "eposta": _git(klasor, "config", "user.email", kontrol=False).strip() or None},
    }


def commit(klasor: Path, mesaj: object, yalniz_hazir: bool = False) -> dict:
    """yalniz_hazir=False: degisen (gizli olmayan) tum dosyalari hazirlayip commit eder. True: yalniz ZATEN hazirlanmis (staged) dosyalari commit eder."""
    if not isinstance(mesaj, str) or not mesaj.strip() or len(mesaj) > AZAMI_MESAJ or "\x00" in mesaj:
        raise GithubHatasi(f"Commit mesaji bos olmayan metin olmali (en cok {AZAMI_MESAJ} karakter)")
    if not _git(klasor, "config", "user.email", kontrol=False).strip() or not _git(klasor, "config", "user.name", kontrol=False).strip():
        raise GithubHatasi("git kimligi tanimli degil. Bir terminalde: git config --global user.name \"Adiniz\" ve git config --global user.email \"eposta\"")
    secilen, atlanan = [], []
    for xy, yol in ([] if yalniz_hazir else _durum_listesi(klasor)):
        if xy == "??" and _kendi_dosyasi_mi(yol):
            continue
        (atlanan if gizli_yol_mu(yol) else secilen).append(yol)
    hazir = [y for y in _git(klasor, "diff", "--cached", "--name-only", "-z").split("\0") if y]
    hazir_gizli = [y for y in hazir if gizli_yol_mu(y)]
    if hazir_gizli:
        raise GithubHatasi(f"Hazirlanmis (staged) gizli gorunen dosya var, commit yapilmadi: {', '.join(hazir_gizli[:3])}. Once `git reset -- <dosya>` ile cikarin.")
    if yalniz_hazir and not hazir:
        raise GithubHatasi("Commit icin once dosyalari secin (hazirlayin); hazirlanmis dosya yok")
    if not secilen and not hazir:
        raise GithubHatasi("Commit edilecek degisiklik yok" + (f" (gizli gorunen {len(atlanan)} dosya atlandi)" if atlanan else ""))
    if secilen:
        _git(klasor, "add", "--pathspec-from-file=-", "--pathspec-file-nul", girdi="\0".join(secilen) + "\0")
    _git(klasor, "commit", "-m", mesaj.strip(), zaman_asimi=120)
    sha = _git(klasor, "rev-parse", "--short", "HEAD").strip()
    return {"commit": sha, "dosya_sayisi": len(secilen) or len(hazir), "atlanan_gizli": atlanan[:20]}


def dal_olustur(klasor: Path, ad: object) -> dict:
    if not isinstance(ad, str) or not DAL_DESENI.fullmatch(ad) or ".." in ad or ad.endswith(("/", ".lock", ".")):
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
