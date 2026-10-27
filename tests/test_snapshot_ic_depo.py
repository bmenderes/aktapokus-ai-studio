"""Gercek hata: birden cok projeyi iceren ust klasorde commit'i olmayan bir ic git deposu `git add -A`'yi 'adding files failed' ile dusuruyordu."""

import subprocess

import pytest

from aktapokus_ai_studio import snapshot


def _git(klasor, *a):
    subprocess.run(["git", "-C", str(klasor), "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True, capture_output=True)


def _dosyalar(klasor, commit):
    return snapshot._git(klasor, "ls-tree", "-r", "--name-only", commit).split()  # golge depoda GIT_DIR'i dogru kurar


def _kur(ust, golge):
    ust.mkdir()
    if not golge:
        _git(ust, "init", "-q")
    (ust / "ana.txt").write_text("ana", encoding="utf-8")
    bos = ust / "commitsiz-depo"  # commit'i olmayan ic depo (hatanin kaynagi)
    bos.mkdir()
    _git(bos, "init", "-q")
    (bos / "x.txt").write_text("x", encoding="utf-8")
    dolu = ust / "commitli depo"  # bosluklu ad + commit'i olan ic depo
    dolu.mkdir()
    _git(dolu, "init", "-q")
    (dolu / "y.txt").write_text("y", encoding="utf-8")
    _git(dolu, "add", "-A")
    _git(dolu, "commit", "-qm", "ilk")
    if golge:
        snapshot.golge_baslat(ust)


@pytest.mark.parametrize("golge", [False, True], ids=["gercek-depo", "golge-depo"])
def test_ic_depolar_anlik_goruntuyu_bozmaz_ve_goruntuye_girmez(tmp_path, golge):
    ust = tmp_path / "calisma-alani"
    _kur(ust, golge)
    once = snapshot.anlik_goruntu(ust, "once")  # eskiden: fatal: adding files failed
    assert _dosyalar(ust, once) == ["ana.txt"]
    (ust / "yeni.txt").write_text("yeni", encoding="utf-8")
    (ust / "commitsiz-depo" / "x.txt").write_text("degisti", encoding="utf-8")  # ic deponun icindeki degisiklik izlenmez
    sonra = snapshot.anlik_goruntu(ust, "sonra")
    assert snapshot.degisenler(ust, once, sonra) == {"yeni.txt": "A"}
    assert (ust / "commitsiz-depo" / "x.txt").read_text(encoding="utf-8") == "degisti"  # geri alma ic depoya dokunmaz
    snapshot.geri_yukle(ust, once, sonra)
    assert not (ust / "yeni.txt").exists() and (ust / "commitsiz-depo" / "x.txt").read_text(encoding="utf-8") == "degisti"


def test_ic_depo_yokken_davranis_ayni(tmp_path):
    d = tmp_path / "duz"
    d.mkdir()
    _git(d, "init", "-q")
    (d / "a.txt").write_text("1", encoding="utf-8")
    assert _dosyalar(d, snapshot.anlik_goruntu(d, "x")) == ["a.txt"]
