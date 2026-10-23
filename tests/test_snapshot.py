import subprocess
from pathlib import Path

import pytest

from aktapokus_ajan import snapshot


def oku(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_hazir_mi_ve_repo_baslat(tmp_path):
    k = tmp_path / "k"
    k.mkdir()
    assert not snapshot.hazir_mi(k)
    snapshot.repo_baslat(k)
    assert snapshot.hazir_mi(k)


def test_alt_klasor_git_koku_degil_sayilir(proje):
    alt = proje / "alt"
    alt.mkdir()
    assert not snapshot.hazir_mi(alt)


def test_degisiklik_tespiti_ve_geri_yukleme(proje):
    once = snapshot.anlik_goruntu(proje, "once")
    (proje / "a.txt").write_text("degisti\n", encoding="utf-8")  # M
    (proje / "b.txt").unlink()  # D
    (proje / "yeni").mkdir()
    (proje / "yeni" / "c.txt").write_text("yeni\n", encoding="utf-8")  # A (alt klasorlu)
    sonra = snapshot.anlik_goruntu(proje, "sonra")
    assert snapshot.degisenler(proje, once, sonra) == {"a.txt": "M", "b.txt": "D", "yeni/c.txt": "A"}
    assert "a.txt" in snapshot.fark_ozeti(proje, once, sonra)
    assert snapshot.geri_yukle(proje, once, sonra) == 3
    assert oku(proje / "a.txt") == "bir\n"
    assert oku(proje / "b.txt") == "iki\n"
    assert not (proje / "yeni").exists()  # bos kalan klasor de temizlenir


def test_degisiklik_yoksa_bos(proje):
    once = snapshot.anlik_goruntu(proje, "once")
    sonra = snapshot.anlik_goruntu(proje, "sonra")
    assert snapshot.degisenler(proje, once, sonra) == {}
    assert snapshot.fark_ozeti(proje, once, sonra) == ""


def test_aktapokus_klasoru_ve_gitignore_dahil_edilmez(proje):
    (proje / ".gitignore").write_text("gizli/\n", encoding="utf-8")
    (proje / "gizli").mkdir()
    (proje / "gizli" / "x.txt").write_text("1", encoding="utf-8")
    (proje / ".aktapokus").mkdir()
    (proje / ".aktapokus" / "roller.json").write_text("{}", encoding="utf-8")
    once = snapshot.anlik_goruntu(proje, "once")
    (proje / "gizli" / "x.txt").write_text("2", encoding="utf-8")
    (proje / ".aktapokus" / "roller.json").write_text('{"a":1}', encoding="utf-8")
    sonra = snapshot.anlik_goruntu(proje, "sonra")
    assert snapshot.degisenler(proje, once, sonra) == {}


def test_kullanici_git_gecmisine_ve_indeksine_dokunmaz(proje):
    subprocess.run(["git", "-C", str(proje), "add", "a.txt"], check=True)
    indeks_once = subprocess.run(["git", "-C", str(proje), "status", "--porcelain"], capture_output=True, text=True).stdout
    snapshot.anlik_goruntu(proje, "x")
    indeks_sonra = subprocess.run(["git", "-C", str(proje), "status", "--porcelain"], capture_output=True, text=True).stdout
    assert indeks_once == indeks_sonra
    dallar = subprocess.run(["git", "-C", str(proje), "branch", "--list"], capture_output=True, text=True).stdout
    assert dallar.strip() == ""  # dal olusmadi
    refler = subprocess.run(["git", "-C", str(proje), "for-each-ref", "refs/aktapokus"], capture_output=True, text=True).stdout
    assert "refs/aktapokus/" in refler


def test_turkce_ve_bosluklu_dosya_adlari(proje):
    once = snapshot.anlik_goruntu(proje, "once")
    (proje / "çalışma notu ğ.txt").write_text("merhaba", encoding="utf-8")
    sonra = snapshot.anlik_goruntu(proje, "sonra")
    assert snapshot.degisenler(proje, once, sonra) == {"çalışma notu ğ.txt": "A"}
    snapshot.geri_yukle(proje, once, sonra)
    assert not (proje / "çalışma notu ğ.txt").exists()


def test_glob_karakterli_dosya_adi_literal_islenir(proje):
    once = snapshot.anlik_goruntu(proje, "once")
    (proje / "a[1].txt").write_text("x", encoding="utf-8")
    (proje / "a1.txt").write_text("y", encoding="utf-8")
    (proje / "a.txt").write_text("degisti", encoding="utf-8")
    sonra = snapshot.anlik_goruntu(proje, "sonra")
    snapshot.geri_yukle(proje, once, sonra)
    assert not (proje / "a[1].txt").exists() and not (proje / "a1.txt").exists()
    assert oku(proje / "a.txt") == "bir\n"


def test_ilk_commit_olmayan_depoda_calisir(proje):
    # proje fixture'inda hic commit yok; anlik goruntu yine de alinir ve zincirlenir
    ilk = snapshot.anlik_goruntu(proje, "ilk")
    (proje / "a.txt").write_text("z", encoding="utf-8")
    ikinci = snapshot.anlik_goruntu(proje, "ikinci")
    assert ilk != ikinci
    assert snapshot.degisenler(proje, ilk, ikinci) == {"a.txt": "M"}


def test_git_hatasi_anlamli(tmp_path):
    with pytest.raises(snapshot.GitHatasi):
        snapshot.anlik_goruntu(tmp_path / "yok", "x")
