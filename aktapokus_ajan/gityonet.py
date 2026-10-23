"""Git istemcisi (GitHub Desktop benzeri): gecmis, fark, dosya dosya hazirlama (stage), degisikligi atma, dal gecisi/silme/birlestirme,
cekme (fetch/pull) ve stash. YALNIZ yerel `git` kullanir (gh gerekmez); butonlu arayuz icindir, serbest komut satiri YOKTUR.

Guvenlik / guvenli varsayilanlar:
- Komutlar dizi olarak, kabuksuz; yollar `--literal-pathspecs` ve NUL ayracli dosyadan verilir; dal/commit adlari dogrulanir.
- Yikici islemler korunur: dal silme yalniz `-d` (birlestirilmemisse reddedilir, `-D` YOK); `reset --hard`/zorla push YOK; pull yalniz `--ff-only`;
  birlestirme (merge) temiz calisma agacinda yapilir, cakisirsa OTOMATIK geri alinir (yarim kalmis cakisma birakilmaz);
  degisikligi atma yalniz acikca verilen dosyalara uygulanir, gizli gorunen dosyalara dokunmaz (arayuz atmadan once anlik goruntu alir).
- Gizli gorunen dosyalar (.env*, anahtarlar...) hazirlanamaz ve farki gosterilmez."""

from __future__ import annotations

import os
import re
from pathlib import Path

from .github import GithubHatasi, _calistir, _durum_listesi, _git, gizli_yol_mu

SHA_DESENI = re.compile(r"^[0-9a-f]{7,40}$")
AZAMI_YOL = 500
AZAMI_FARK = 60_000
AZAMI_DOSYA_OKUMA = 200_000
DAL_ADI_DESENI = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,99}$")


def _basinda_commit_var(klasor: Path) -> bool:
    kod, _, _ = _calistir(["git", "-C", str(klasor), "rev-parse", "--verify", "-q", "HEAD"])
    return kod == 0


def _yol_dogrula(yol: object) -> str:
    if not isinstance(yol, str) or not yol or len(yol) > 400 or "\x00" in yol or "\n" in yol:
        raise GithubHatasi("Gecersiz dosya yolu")
    y = yol.replace("\\", "/")
    if y.startswith("/") or re.match(r"^[A-Za-z]:", y) or any(p in ("..", ".git") for p in y.split("/")):
        raise GithubHatasi("Dosya yolu proje icinde ve goreli olmali")
    return y


def _yollar(yollar: object) -> list[str]:
    if not isinstance(yollar, list) or not yollar or len(yollar) > AZAMI_YOL:
        raise GithubHatasi(f"Dosya listesi bos olmayan ve en cok {AZAMI_YOL} ogeli bir liste olmali")
    return [_yol_dogrula(y) for y in yollar]


def _sha(sha: object) -> str:
    if not isinstance(sha, str) or not SHA_DESENI.match(sha):
        raise GithubHatasi("Gecersiz commit adi")
    return sha


def _nul(yollar: list[str]) -> str:
    return "\0".join(yollar) + "\0"


# ---- commit mesaji onerisi ----------------------------------------------------------------------------------------------
def _gorev_ozeti(metin: object, azami: int = 72) -> str:
    ilk = next((s.strip() for s in str(metin or "").splitlines() if s.strip()), "")
    ilk = re.sub(r"\s+", " ", ilk)
    return ilk if len(ilk) <= azami else ilk[: azami - 1].rstrip() + "…"


def oneri_mesaji(gorevler: list[str], degisen: list[dict]) -> dict:
    """Commit mesaji onerisi: son commit'ten beri Aktapokus gorevleri varsa ONLARDAN (kullanici ne yazacagini dusunmesin), yoksa degisen
    dosyalardan. Gizli gorunen dosya adlari mesaja yazilmaz. Kullanici mesaji elbette duzenleyebilir."""
    dosyalar = [d for d in degisen if not d.get("gizli")]
    adlar = [d["yol"] for d in dosyalar]
    ozetler = [o for o in (_gorev_ozeti(g) for g in gorevler) if o]
    if ozetler:
        konu = ozetler[0] + (f" (+{len(ozetler) - 1} gorev daha)" if len(ozetler) > 1 else "")
        kaynak = "gorev"
    else:
        durumlar = {d["durum"][:1] for d in dosyalar}
        fiil = "Guncelle" if not durumlar else "Ekle" if durumlar <= {"A", "?"} else "Sil" if durumlar == {"D"} else "Guncelle"
        goster = ", ".join(Path(a).name for a in adlar[:3]) or "degisiklikler"
        konu = f"{fiil}: {goster}" + (f" (+{len(adlar) - 3} dosya)" if len(adlar) > 3 else "")
        kaynak = "degisiklik"
    govde = []
    if len(ozetler) > 1 or (ozetler and len(adlar) > 0):
        if len(ozetler) > 1:
            govde.append("Gorevler:\n" + "\n".join(f"- {_gorev_ozeti(g, 100)}" for g in gorevler[:8] if _gorev_ozeti(g)))
        if adlar:
            govde.append(f"Degisen dosyalar ({len(adlar)}): " + ", ".join(adlar[:10]) + (f" ... (+{len(adlar) - 10})" if len(adlar) > 10 else ""))
    mesaj = konu[:200] + ("\n\n" + "\n\n".join(govde) if govde else "")
    return {"mesaj": mesaj[:2000], "kaynak": kaynak, "gorev_sayisi": len(ozetler)}


def son_commit_zamani(klasor: Path) -> float:
    """Son commit'in epoch zamani (hic commit yoksa 0)."""
    if not _basinda_commit_var(klasor):
        return 0.0
    try:
        return float(_git(klasor, "log", "-1", "--format=%ct").strip())
    except ValueError:
        return 0.0


# ---- gecmis / fark ----------------------------------------------------------------------------------------------------
def gecmis(klasor: Path, adet: int = 50) -> list[dict]:
    if not _basinda_commit_var(klasor):
        return []
    adet = max(1, min(int(adet), 300))
    ham = _git(klasor, "log", f"--max-count={adet}", "-z", "--format=%H%x1f%h%x1f%an%x1f%aI%x1f%s")
    gonderilmedi: set[str] = set()
    kod, cikti, _ = _calistir(["git", "-C", str(klasor), "rev-list", "@{upstream}..HEAD"])
    if kod == 0:
        gonderilmedi = set(cikti.split())
    sonuc = []
    for kayit in ham.split("\0"):
        p = kayit.strip("\n").split("\x1f")
        if len(p) == 5:
            sonuc.append({"sha": p[0], "kisa": p[1], "yazar": p[2], "tarih": p[3], "konu": p[4], "gonderilmedi": p[0] in gonderilmedi})
    return sonuc


def commit_ayrinti(klasor: Path, sha: object) -> dict:
    sha = _sha(sha)
    ust = _git(klasor, "show", "-s", "--format=%H%x1f%an%x1f%aI%x1f%B", sha).split("\x1f", 3)
    if len(ust) != 4:
        raise GithubHatasi("Commit okunamadi")
    parcalar = [p for p in _git(klasor, "show", "--name-status", "--format=", "--no-renames", "-z", sha).split("\0") if p]
    dosyalar = [{"durum": parcalar[i][:1], "yol": parcalar[i + 1]} for i in range(0, len(parcalar) - 1, 2)]
    return {"sha": ust[0], "yazar": ust[1], "tarih": ust[2], "mesaj": ust[3].strip(), "dosyalar": dosyalar[:500], "dosya_sayisi": len(dosyalar)}


def fark(klasor: Path, yol: object, sha: object = None, hazir: bool = False) -> dict:
    y = _yol_dogrula(yol)
    if gizli_yol_mu(y):
        raise GithubHatasi("Gizli gorunen dosyanin icerigi gosterilmez")
    if sha:
        yama = _git(klasor, "--literal-pathspecs", "show", "--no-color", "--format=", _sha(sha), "--", y)
    elif hazir:
        yama = _git(klasor, "--literal-pathspecs", "diff", "--cached", "--no-color", "--", y)
    else:
        yama = _git(klasor, "--literal-pathspecs", "diff", "--no-color", "--", y)
        if not yama:
            kod, _, _ = _calistir(["git", "-C", str(klasor), "--literal-pathspecs", "ls-files", "--error-unmatch", "--", y])
            dosya = (klasor / y)
            if kod != 0 and dosya.is_file() and klasor.resolve() in dosya.resolve().parents:  # izlenmeyen yeni dosya: tamami 'eklendi'
                ham = dosya.read_bytes()[:AZAMI_DOSYA_OKUMA]
                if b"\0" in ham[:8192]:
                    yama = f"(ikili dosya: {y})"
                else:
                    satirlar = ham.decode("utf-8", "replace").splitlines()
                    yama = f"diff --git a/{y} b/{y}\nnew file\n@@ -0,0 +1,{len(satirlar)} @@\n" + "\n".join("+" + s for s in satirlar)
    kesildi = len(yama) > AZAMI_FARK
    return {"yama": yama[:AZAMI_FARK] + ("\n... [kisaltildi]" if kesildi else ""), "kesildi": kesildi}


# ---- hazirlama (stage) / atma ------------------------------------------------------------------------------------------
def hazirla(klasor: Path, yollar: object) -> dict:
    y = _yollar(yollar)
    gizli = [x for x in y if gizli_yol_mu(x)]
    if gizli:
        raise GithubHatasi(f"Gizli gorunen dosya hazirlanamaz: {', '.join(gizli[:3])}")
    _git(klasor, "--literal-pathspecs", "add", "--pathspec-from-file=-", "--pathspec-file-nul", girdi=_nul(y))
    return {"dosya_sayisi": len(y)}


def hazirdan_cikar(klasor: Path, yollar: object) -> dict:
    y = _yollar(yollar)
    if _basinda_commit_var(klasor):
        _git(klasor, "--literal-pathspecs", "restore", "--staged", "--pathspec-from-file=-", "--pathspec-file-nul", girdi=_nul(y))
    else:  # ilk commit'ten once HEAD yok: restore --staged calismaz
        _git(klasor, "--literal-pathspecs", "rm", "--cached", "-q", "-r", "--ignore-unmatch", "--pathspec-from-file=-", "--pathspec-file-nul", girdi=_nul(y))
    return {"dosya_sayisi": len(y)}


def degisikligi_at(klasor: Path, yollar: object) -> dict:
    """Verilen dosyalardaki degisikligi KALICI olarak atar: izlenen dosya HEAD haline doner, izlenmeyen yeni dosya silinir.
    Gizli dosyalara dokunmaz. (Arayuz bundan once anlik goruntu alir.)"""
    y = _yollar(yollar)
    gizli = [x for x in y if gizli_yol_mu(x)]
    if gizli:
        raise GithubHatasi(f"Gizli gorunen dosyaya dokunulmaz: {', '.join(gizli[:3])}")
    durumlar = {yol: xy for xy, yol in _durum_listesi(klasor)}
    bilinmeyen = [x for x in y if x not in durumlar]
    if bilinmeyen:
        raise GithubHatasi(f"Bu dosyada degisiklik yok: {', '.join(bilinmeyen[:3])}")
    head = _basinda_commit_var(klasor)
    izlenen = [x for x in y if durumlar[x] != "??" and head]
    izlenmeyen = [x for x in y if durumlar[x] == "??" or not head]
    if izlenen:
        _git(klasor, "--literal-pathspecs", "restore", "--source=HEAD", "--staged", "--worktree", "--pathspec-from-file=-", "--pathspec-file-nul", girdi=_nul(izlenen))
    silinen = 0
    kok = klasor.resolve()
    if izlenmeyen and not head:
        _git(klasor, "--literal-pathspecs", "rm", "--cached", "-q", "-r", "--ignore-unmatch", "--pathspec-from-file=-", "--pathspec-file-nul", girdi=_nul(izlenmeyen))
    for x in izlenmeyen:
        hedef = (klasor / x)
        if hedef.is_file() and not hedef.is_symlink() and kok in hedef.resolve().parents:
            hedef.unlink()
            silinen += 1
    return {"geri_alinan": len(izlenen), "silinen": silinen}


# ---- dallar -----------------------------------------------------------------------------------------------------------
def dallar(klasor: Path) -> dict:
    ham = _git(klasor, "for-each-ref", "--format=%(HEAD)%1f%(refname:short)%1f%(upstream:short)%1f%(upstream:track)%1f%(committerdate:iso8601-strict)%1f%(subject)", "refs/heads")
    yerel = []
    for satir in ham.splitlines():
        p = satir.split("\x1f")
        if len(p) == 6:
            yerel.append({"ad": p[1], "aktif": p[0] == "*", "upstream": p[2] or None, "takip": p[3].strip("[]") or None, "tarih": p[4], "konu": p[5]})
    uzak_ham = _git(klasor, "for-each-ref", "--format=%(refname:short)", "refs/remotes", kontrol=False)
    uzak = [u for u in uzak_ham.split() if not u.endswith("/HEAD")]
    yerel_adlar = {d["ad"] for d in yerel}
    uzak_yalniz = [u.split("/", 1)[1] for u in uzak if "/" in u and u.split("/", 1)[1] not in yerel_adlar]
    return {"yerel": yerel, "uzak_yalniz": uzak_yalniz[:100]}


def _dal_adi(ad: object) -> str:
    if not isinstance(ad, str) or not DAL_ADI_DESENI.match(ad) or ".." in ad:
        raise GithubHatasi("Gecersiz dal adi")
    return ad


def _temiz_mi(klasor: Path) -> bool:
    return not _git(klasor, "status", "--porcelain", "--untracked-files=no").strip()


def dal_gec(klasor: Path, ad: object) -> dict:
    ad = _dal_adi(ad)
    d = dallar(klasor)
    if ad not in {x["ad"] for x in d["yerel"]} and ad not in d["uzak_yalniz"]:
        raise GithubHatasi("Boyle bir dal yok")
    _git(klasor, "switch", ad)  # uzakta olan dal icin git yerel takip dali kurar; calisma agaci cakisirsa git reddeder
    return {"dal": ad}


def dal_sil(klasor: Path, ad: object) -> dict:
    ad = _dal_adi(ad)
    d = dallar(klasor)
    secili = next((x for x in d["yerel"] if x["ad"] == ad), None)
    if secili is None:
        raise GithubHatasi("Boyle bir yerel dal yok")
    if secili["aktif"]:
        raise GithubHatasi("Uzerinde bulundugunuz dal silinemez; once baska bir dala gecin")
    _git(klasor, "branch", "-d", ad)  # -d: birlestirilmemis commit varsa git reddeder (veri kaybi olmaz)
    return {"silinen": ad}


def birlestir(klasor: Path, ad: object) -> dict:
    ad = _dal_adi(ad)
    d = dallar(klasor)
    aktif = next((x["ad"] for x in d["yerel"] if x["aktif"]), None)
    if aktif is None:
        raise GithubHatasi("Bir dalda degilsiniz (detached HEAD)")
    if ad == aktif or ad not in {x["ad"] for x in d["yerel"]}:
        raise GithubHatasi("Birlestirilecek dal gecersiz (kendisi ya da yok)")
    if not _temiz_mi(klasor):
        raise GithubHatasi("Birlestirmeden once calisma agacindaki degisiklikleri commit edin ya da rafa kaldirin")
    kod, cikti, hata = _calistir(["git", "-C", str(klasor), "merge", "--no-edit", ad], None, 120)
    if kod != 0:
        if (_git(klasor, "rev-parse", "--git-dir").strip()):
            gitdir = Path(_git(klasor, "rev-parse", "--absolute-git-dir").strip())
            if (gitdir / "MERGE_HEAD").exists():
                _calistir(["git", "-C", str(klasor), "merge", "--abort"])
                raise GithubHatasi(f"'{ad}' dalini '{aktif}' icine birlestirirken CAKISMA cikti; birlestirme geri alindi (dosyalariniza dokunulmadi). Cakismalari Terminal'de cozun.")
        raise GithubHatasi((hata.strip() or cikti.strip() or "Birlestirme basarisiz")[:400])
    return {"birlesen": ad, "icine": aktif, "cikti": cikti.strip()[-300:]}


def cek(klasor: Path) -> dict:
    """fetch: uzak degisiklikleri indirir, calisma agacina DOKUNMAZ."""
    if not _git(klasor, "remote", "get-url", "origin", kontrol=False).strip():
        raise GithubHatasi("'origin' uzak deposu tanimli degil")
    _git(klasor, "fetch", "--prune", "origin", zaman_asimi=180)
    return {"tamam": True}


def pull(klasor: Path) -> dict:
    """Yalniz hizli ileri sarma (--ff-only): birlestirme commit'i ya da rebase OLUSTURMAZ; yapamazsa reddeder."""
    kod, _, _ = _calistir(["git", "-C", str(klasor), "rev-parse", "--abbrev-ref", "@{upstream}"])
    if kod != 0:
        raise GithubHatasi("Bu dal icin upstream (uzak dal) tanimli degil; once push edin")
    cikti = _git(klasor, "pull", "--ff-only", zaman_asimi=180)
    return {"cikti": cikti.strip()[-300:]}


# ---- stash ------------------------------------------------------------------------------------------------------------
def stashler(klasor: Path) -> list[dict]:
    ham = _git(klasor, "stash", "list", "--format=%gd%x1f%gs%x1f%cI", kontrol=False)
    sonuc = []
    for satir in ham.splitlines():
        p = satir.split("\x1f")
        m = re.match(r"^stash@\{(\d+)\}$", p[0]) if len(p) == 3 else None
        if m:
            sonuc.append({"indeks": int(m.group(1)), "mesaj": p[1], "tarih": p[2]})
    return sonuc


def stash_kaydet(klasor: Path, mesaj: object = "") -> dict:
    if mesaj is None:
        mesaj = ""
    if not isinstance(mesaj, str) or len(mesaj) > 200 or "\n" in mesaj or "\x00" in mesaj:
        raise GithubHatasi("Stash mesaji tek satirlik, en cok 200 karakter olmali")
    if _temiz_mi(klasor):
        raise GithubHatasi("Rafa kaldirilacak izlenen dosya degisikligi yok (izlenmeyen yeni dosyalar rafa alinmaz)")
    _git(klasor, "stash", "push", "-m", mesaj.strip() or "Aktapokus")
    return {"tamam": True}


def _stash_indeksi(klasor: Path, indeks: object) -> int:
    if isinstance(indeks, bool) or not isinstance(indeks, int) or indeks < 0:
        raise GithubHatasi("Gecersiz stash numarasi")
    if indeks not in {s["indeks"] for s in stashler(klasor)}:
        raise GithubHatasi("Boyle bir stash yok")
    return indeks


def stash_uygula(klasor: Path, indeks: object, sil: bool = False) -> dict:
    i = _stash_indeksi(klasor, indeks)
    kod, cikti, hata = _calistir(["git", "-C", str(klasor), "stash", "pop" if sil else "apply", f"stash@{{{i}}}"], None, 120)
    if kod != 0:
        raise GithubHatasi(("Stash uygulanamadi (cakisma ya da yerel degisiklik olabilir; stash silinmedi): " + (hata.strip() or cikti.strip()))[:500])
    return {"uygulanan": i, "silindi": bool(sil)}


def stash_sil(klasor: Path, indeks: object) -> dict:
    i = _stash_indeksi(klasor, indeks)
    _git(klasor, "stash", "drop", f"stash@{{{i}}}")
    return {"silinen": i}
