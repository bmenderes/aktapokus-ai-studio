"""Git ile anlik goruntu, fark ve geri yukleme.

Kullanicinin dallarina, indeksine veya gecmisine DOKUNMAZ: gecici bir indeks dosyasiyla calisma
alanindan bir agac (tree) yazar, onu refs/aktapokus/* altinda tutulan bir commit'e baglar.
.gitignore'daki dosyalar anlik goruntuye girmez (ve geri yuklenmez). .aktapokus/ dahil edilmez.

GOLGE DEPO: klasor bir git deposu degilse kullanicidan git ISTENMEZ. Anlik goruntuler klasorun DISINDA, `~/.aktapokus/golge/<kimlik>.git`
altindaki ozel bir depoda tutulur (GIT_DIR + GIT_WORK_TREE); klasore `.git` eklenmez. Klasor sonradan gercek bir git deposu olursa
(`.git` belirirse) gercek depo kullanilir. Cok buyuk klasorler (dosya sayisi/boyut siniri) golge depoya alinmaz."""

from __future__ import annotations

import os
import subprocess
import tempfile
import uuid
from pathlib import Path

from .config import SNAPSHOT_DISI

_GIT_ORTAMI = {
    "GIT_AUTHOR_NAME": "Aktapokus",
    "GIT_AUTHOR_EMAIL": "aktapokus@localhost",
    "GIT_COMMITTER_NAME": "Aktapokus",
    "GIT_COMMITTER_EMAIL": "aktapokus@localhost",
    "GIT_OPTIONAL_LOCKS": "0",
    "GIT_LITERAL_PATHSPECS": "1",
}


GOLGE_ORTAMI = "AKTAPOKUS_GOLGE"
AZAMI_GOLGE_DOSYA = 20_000
AZAMI_GOLGE_BAYT = 1 << 30  # 1 GiB


class GitHatasi(Exception):
    pass


def golge_koku() -> Path:
    ortam = os.environ.get(GOLGE_ORTAMI)
    return Path(ortam) if ortam else Path.home() / ".aktapokus" / "golge"


def golge_dizini(klasor: str | Path) -> Path:
    from . import projeler  # tembel: dairesel ice aktarma yok ama modul yuklemesini hafif tut

    return golge_koku() / f"{projeler.proje_kimligi(klasor)}.git"


def golge_mi(klasor: str | Path) -> bool:
    """Bu klasor icin golge depo kullaniliyor mu? (golge var VE klasorde gercek `.git` yok)"""
    return golge_dizini(klasor).is_dir() and not (Path(klasor) / ".git").exists()


def git_dizini(klasor: str | Path) -> Path:
    """Gercek git dizini ya da (golge kullaniliyorsa) golge deponun dizini: info/exclude buraya yazilir."""
    return golge_dizini(klasor) if golge_mi(klasor) else Path(klasor) / ".git"


def _golge_ortami(klasor: Path) -> dict:
    return {"GIT_DIR": str(golge_dizini(klasor)), "GIT_WORK_TREE": str(Path(klasor).resolve())} if golge_mi(klasor) else {}


def golge_baslat(klasor: str | Path) -> bool:
    """Golge depoyu kurar (yoksa). Yeni kurulduysa True. Klasore dokunmaz."""
    klasor = Path(klasor)
    dizin = golge_dizini(klasor)
    if dizin.is_dir():
        return False
    dizin.parent.mkdir(parents=True, exist_ok=True)
    ortam = os.environ.copy()
    ortam.update(_GIT_ORTAMI)
    ortam.pop("GIT_DIR", None)
    ortam.pop("GIT_WORK_TREE", None)
    try:
        s = subprocess.run(["git", "init", "-q", "--bare", str(dizin)], capture_output=True, text=True, encoding="utf-8", errors="replace", env=ortam, stdin=subprocess.DEVNULL, timeout=120)
    except FileNotFoundError as hata:
        raise GitHatasi("git bulunamadi; git kurulu ve PATH'te olmali") from hata
    if s.returncode != 0:
        raise GitHatasi(f"Golge depo kurulamadi: {s.stderr.strip()}")
    # golge bir 'bare olmayan' depo gibi kullanilir ama calisma alani GIT_WORK_TREE ile verilir: yanlislikla kendi icinde calismasin
    _git(klasor, "config", "core.bare", "false", env={"GIT_DIR": str(dizin)})
    _git(klasor, "config", "core.worktree", str(klasor.resolve()), env={"GIT_DIR": str(dizin)})
    return True


def golge_sil(klasor: str | Path) -> None:
    import shutil

    dizin = golge_dizini(klasor)
    if dizin.is_dir() and dizin.parent == golge_koku():
        shutil.rmtree(dizin, ignore_errors=True)


def golge_boyut_denetle(klasor: str | Path) -> None:
    """Golge depoya alinacak dosyalarin sayisi/boyutu sinirlari asarsa GitHatasi (ornegin Masaustu ya da sanal ortam dolu klasor)."""
    klasor = Path(klasor)
    cikti = _git(klasor, "ls-files", "-o", "--exclude-standard", "-z")
    dosyalar = [d for d in cikti.split("\0") if d]
    if len(dosyalar) > AZAMI_GOLGE_DOSYA:
        raise GitHatasi(
            f"Bu klasor cok buyuk ({len(dosyalar)} dosya; sinir {AZAMI_GOLGE_DOSYA}). Geri alma icin anlik goruntu alinamaz. "
            "Daha kucuk bir proje klasoru secin ya da buyuk klasorleri (node_modules, .venv...) .gitignore ile disarida birakin."
        )
    toplam = 0
    for d in dosyalar:
        try:
            toplam += (klasor / d).stat().st_size
        except OSError:
            continue
        if toplam > AZAMI_GOLGE_BAYT:
            raise GitHatasi("Bu klasor cok buyuk (1 GB'i asiyor). Geri alma icin anlik goruntu alinamaz; daha kucuk bir proje klasoru secin ya da buyuk dosyalari .gitignore ile disarida birakin.")


def _git(klasor: Path, *args: str, env: dict | None = None, kontrol: bool = True) -> str:
    ortam = os.environ.copy()
    ortam.update(_GIT_ORTAMI)
    ortam.update(_golge_ortami(klasor))
    if env:
        ortam.update(env)
    try:
        sonuc = subprocess.run(
            ["git", "-C", str(klasor), "-c", "core.quotepath=off", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=ortam,
            stdin=subprocess.DEVNULL,
            timeout=300,
        )
    except FileNotFoundError as hata:
        raise GitHatasi("git bulunamadi; git kurulu ve PATH'te olmali") from hata
    except subprocess.TimeoutExpired as hata:
        raise GitHatasi(f"git zaman asimina ugradi: git {' '.join(args)}") from hata
    if kontrol and sonuc.returncode != 0:
        raise GitHatasi(f"git {' '.join(args)}: {sonuc.stderr.strip() or sonuc.stdout.strip()}")
    return sonuc.stdout


def repo_koku(klasor: str | Path) -> Path | None:
    klasor = Path(klasor)
    cikti = _git(klasor, "rev-parse", "--show-toplevel", kontrol=False).strip()
    return Path(cikti).resolve() if cikti else None


def hazir_mi(klasor: str | Path) -> bool:
    """Klasor, kendisi kok olan bir git deposu mu?"""
    koku = repo_koku(klasor)
    return koku is not None and koku == Path(klasor).resolve()


def repo_baslat(klasor: str | Path) -> None:
    _git(Path(klasor), "init", "-q")


def anlik_goruntu(klasor: str | Path, etiket: str) -> str:
    """Calisma alaninin o anki halini bir commit olarak saklar ve commit adini dondurur."""
    klasor = Path(klasor)
    if golge_mi(klasor):
        golge_boyut_denetle(klasor)  # klasor sonradan sisebilir (sanal ortam, indirilen buyuk dosyalar)
    with tempfile.TemporaryDirectory() as gecici:
        ortam = {"GIT_INDEX_FILE": str(Path(gecici) / "indeks")}
        _git(klasor, "add", "-A", "--", ".", env=ortam)
        # .aktapokus/ (ayar ve kayitlar) anlik goruntuye girmez; zaten .git/info/exclude'daysa 'add' onu hic eklemez
        _git(klasor, "rm", "-r", "--cached", "-q", "--ignore-unmatch", "--", *SNAPSHOT_DISI, env=ortam)
        agac = _git(klasor, "write-tree", env=ortam).strip()
        ust = _git(klasor, "rev-parse", "-q", "--verify", "HEAD", kontrol=False).strip()
        komut = ["commit-tree", agac, "-m", etiket]
        if ust:
            komut[2:2] = ["-p", ust]
        commit = _git(klasor, *komut, env=ortam).strip()
    _git(klasor, "update-ref", f"refs/aktapokus/{uuid.uuid4().hex[:12]}", commit)
    return commit


def degisenler(klasor: str | Path, once: str, sonra: str) -> dict[str, str]:
    """{yol: 'A'|'M'|'D'} -- iki anlik goruntu arasindaki farklar."""
    cikti = _git(Path(klasor), "diff", "--name-status", "-z", "--no-renames", once, sonra)
    parcalar = [p for p in cikti.split("\0") if p]
    sonuc: dict[str, str] = {}
    for i in range(0, len(parcalar) - 1, 2):
        sonuc[parcalar[i + 1]] = parcalar[i][0]
    return sonuc


def fark_ozeti(klasor: str | Path, once: str, sonra: str, azami_satir: int = 40) -> str:
    cikti = _git(Path(klasor), "diff", "--stat", "--no-renames", once, sonra).rstrip()
    satirlar = cikti.splitlines()
    if len(satirlar) > azami_satir:
        satirlar = satirlar[: azami_satir - 1] + [f"... {len(satirlar) - azami_satir + 1} satir daha"]
    return "\n".join(satirlar)


def commit_var_mi(klasor: str | Path, commit: str) -> bool:
    import re

    if not re.fullmatch(r"[0-9a-f]{40}", commit or ""):
        return False
    ortam = os.environ.copy()
    ortam.update(_golge_ortami(Path(klasor)))
    return subprocess.run(["git", "-C", str(klasor), "cat-file", "-e", f"{commit}^{{commit}}"], capture_output=True, stdin=subprocess.DEVNULL, env=ortam).returncode == 0


def fark_yamasi(klasor: str | Path, once: str, sonra: str, dosya: str | None = None, azami: int = 60_000) -> str:
    """Iki anlik goruntu arasindaki birlesik (unified) fark. Commit adlari dogrulanir; 'dosya' literal yol olarak verilir."""
    for c in (once, sonra):
        if not commit_var_mi(klasor, c):
            raise GitHatasi(f"Gecersiz anlik goruntu: {c!r}")
    komut = ["diff", "--no-renames", "--no-color", once, sonra]
    if dosya:
        komut += ["--", dosya]
    cikti = _git(Path(klasor), *komut)
    return cikti if len(cikti) <= azami else cikti[:azami] + "\n... [kisaltildi]"


def geri_yukle(klasor: str | Path, once: str, sonra: str) -> int:
    """'sonra' goruntusunde 'once'ye gore degisen dosyalari 'once' haline dondurur. Dondurulen dosya sayisini verir."""
    klasor = Path(klasor).resolve()
    farklar = degisenler(klasor, once, sonra)
    for yol, durum in farklar.items():
        if durum == "A":
            hedef = (klasor / yol).resolve()
            if klasor not in hedef.parents:
                raise GitHatasi(f"Klasor disina cikan yol reddedildi: {yol}")
            if hedef.is_file() or hedef.is_symlink():
                hedef.unlink()
            ust = hedef.parent
            while ust != klasor and ust.is_dir() and not any(ust.iterdir()):
                ust.rmdir()
                ust = ust.parent
    geri_donecek = [y for y, d in farklar.items() if d in ("M", "D")]
    for i in range(0, len(geri_donecek), 50):
        parca = geri_donecek[i : i + 50]
        _git(klasor, "restore", f"--source={once}", "--worktree", "--", *parca)
    return len(farklar)
