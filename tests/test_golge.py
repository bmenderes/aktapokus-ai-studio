"""Gölge depo: git deposu OLMAYAN klasorlerde de geri alma calisir; klasore .git eklenmez, kullanicidan git istenmez."""

import subprocess
from pathlib import Path

import pytest

from aktapokus_ajan import snapshot
from aktapokus_ajan.proje import hazirla
from test_arayuz import kur, tam_kosu  # noqa: F401  (kur: pytest fixture'i)


def gitsiz(tmp_path, ad="gitsiz"):
    k = tmp_path / ad
    k.mkdir()
    (k / "a.txt").write_text("bir\n", encoding="utf-8")
    (k / "b.txt").write_text("iki\n", encoding="utf-8")
    return k


def golge_git(klasor, *a):
    return subprocess.run(["git", "--git-dir", str(snapshot.golge_dizini(klasor)), *a], capture_output=True, text=True, encoding="utf-8").stdout


def test_hazirla_gitsiz_klasorde_golge_kurar_klasore_git_eklemez(tmp_path):
    k = gitsiz(tmp_path)
    s = hazirla(k)
    assert s["git"] == "golge" and not (k / ".git").exists()
    assert snapshot.golge_mi(k) and snapshot.hazir_mi(k) and snapshot.golge_dizini(k).is_dir()
    assert snapshot.golge_dizini(k).parent == snapshot.golge_koku()  # klasorun DISINDA
    assert hazirla(k)["git"] == "golge"  # tekrar: ayni golge, hata yok
    assert "aktapokus" in (snapshot.golge_dizini(k) / "info" / "exclude").read_text(encoding="utf-8")


def test_git_baslat_istenirse_gercek_depo_kurulur_golge_degil(tmp_path):
    k = gitsiz(tmp_path)
    assert hazirla(k, git_baslat=True)["git"] == "baslatildi" and (k / ".git").is_dir() and not snapshot.golge_mi(k)


def test_golge_ile_anlik_goruntu_fark_ve_geri_yukleme(tmp_path):
    k = gitsiz(tmp_path)
    hazirla(k)
    once = snapshot.anlik_goruntu(k, "once")
    (k / "a.txt").write_text("degisti\n", encoding="utf-8")  # M
    (k / "b.txt").unlink()  # D
    (k / "yeni dosya ç.txt").write_text("yeni", encoding="utf-8")  # A
    (k / "alt").mkdir()
    (k / "alt" / "c.txt").write_text("c", encoding="utf-8")
    sonra = snapshot.anlik_goruntu(k, "sonra")
    assert snapshot.degisenler(k, once, sonra) == {"a.txt": "M", "b.txt": "D", "yeni dosya ç.txt": "A", "alt/c.txt": "A"}
    assert "degisti" in snapshot.fark_yamasi(k, once, sonra, "a.txt")
    snapshot.geri_yukle(k, once, sonra)
    assert (k / "a.txt").read_text(encoding="utf-8") == "bir\n" and (k / "b.txt").read_text(encoding="utf-8") == "iki\n"
    assert not (k / "yeni dosya ç.txt").exists() and not (k / "alt" / "c.txt").exists()
    assert not (k / ".git").exists()
    assert len(golge_git(k, "for-each-ref", "refs/aktapokus").strip().splitlines()) == 2  # anlik goruntuler golgede


def test_golge_gitignore_dosyasini_gozetir(tmp_path):
    k = gitsiz(tmp_path)
    (k / ".gitignore").write_text("gizli-cikti.log\nnode_modules/\n", encoding="utf-8")
    (k / "gizli-cikti.log").write_text("v1")
    (k / "node_modules").mkdir()
    (k / "node_modules" / "x.js").write_text("x")
    hazirla(k)
    once = snapshot.anlik_goruntu(k, "once")
    (k / "gizli-cikti.log").write_text("v2")
    (k / "node_modules" / "x.js").write_text("y")
    (k / "a.txt").write_text("degisti")
    sonra = snapshot.anlik_goruntu(k, "sonra")
    assert snapshot.degisenler(k, once, sonra) == {"a.txt": "M"}
    snapshot.geri_yukle(k, once, sonra)
    assert (k / "gizli-cikti.log").read_text() == "v2"  # yoksayilan dosyaya dokunulmaz


def test_golge_aktapokus_klasorunu_goruntuye_almaz(tmp_path):
    k = gitsiz(tmp_path)
    hazirla(k)
    once = snapshot.anlik_goruntu(k, "once")
    (k / ".aktapokus" / "kayitlar").mkdir(parents=True, exist_ok=True)
    (k / ".aktapokus" / "kayitlar" / "x.json").write_text("{}")
    assert snapshot.degisenler(k, once, snapshot.anlik_goruntu(k, "sonra")) == {}


def test_klasorde_gercek_git_belirirse_gercek_depo_kullanilir(tmp_path):
    k = gitsiz(tmp_path)
    hazirla(k)
    assert snapshot.golge_mi(k)
    subprocess.run(["git", "init", "-q", str(k)], check=True)  # kullanici sonradan git init yapti
    assert not snapshot.golge_mi(k) and snapshot.hazir_mi(k)
    snapshot.anlik_goruntu(k, "x")
    assert subprocess.run(["git", "-C", str(k), "for-each-ref", "refs/aktapokus"], capture_output=True, text=True).stdout.strip()  # gercek depoda


def test_ust_klasorde_git_deposu_olsa_da_alt_klasor_golge_kullanir_ve_ust_depoya_dokunmaz(tmp_path):
    ust = tmp_path / "ust"
    ust.mkdir()
    subprocess.run(["git", "init", "-q", str(ust)], check=True)
    alt = ust / "alt"
    alt.mkdir()
    (alt / "a.txt").write_text("a")
    assert not snapshot.hazir_mi(alt)
    assert hazirla(alt)["git"] == "golge"
    snapshot.anlik_goruntu(alt, "x")
    assert subprocess.run(["git", "-C", str(ust), "for-each-ref", "refs/aktapokus"], capture_output=True, text=True).stdout.strip() == ""


def test_ayni_adli_iki_klasorun_golgeleri_ayridir(tmp_path):
    a, b = gitsiz(tmp_path / "x" if (tmp_path / "x").mkdir() is None else tmp_path, "proje"), None
    (tmp_path / "y").mkdir()
    b = gitsiz(tmp_path / "y", "proje")
    hazirla(a)
    hazirla(b)
    assert snapshot.golge_dizini(a) != snapshot.golge_dizini(b) and snapshot.golge_dizini(a).is_dir() and snapshot.golge_dizini(b).is_dir()


def test_cok_buyuk_klasor_reddedilir_ve_golge_birakilmaz(tmp_path, monkeypatch):
    k = gitsiz(tmp_path)
    for i in range(6):
        (k / f"d{i}.txt").write_text("x")
    monkeypatch.setattr(snapshot, "AZAMI_GOLGE_DOSYA", 5)
    with pytest.raises(snapshot.GitHatasi, match="cok buyuk"):
        hazirla(k)
    assert not snapshot.golge_dizini(k).exists() and not (k / ".git").exists()
    monkeypatch.setattr(snapshot, "AZAMI_GOLGE_DOSYA", 50)
    assert hazirla(k)["git"] == "golge"


def test_buyuk_dosya_boyut_siniri(tmp_path, monkeypatch):
    k = gitsiz(tmp_path)
    (k / "buyuk.bin").write_bytes(b"x" * 5000)
    monkeypatch.setattr(snapshot, "AZAMI_GOLGE_BAYT", 1000)
    with pytest.raises(snapshot.GitHatasi, match="1 GB"):
        hazirla(k)
    assert not snapshot.golge_dizini(k).exists()


def test_klasor_sonradan_sisince_anlik_goruntu_reddedilir(tmp_path, monkeypatch):
    k = gitsiz(tmp_path)
    hazirla(k)
    monkeypatch.setattr(snapshot, "AZAMI_GOLGE_DOSYA", 2)
    (k / "c.txt").write_text("c")
    with pytest.raises(snapshot.GitHatasi, match="cok buyuk"):
        snapshot.anlik_goruntu(k, "x")
    assert golge_git(k, "for-each-ref", "refs/aktapokus").strip() == ""  # yarim goruntu birakilmadi


def test_golge_sil_yalniz_golge_kokunun_altini_siler(tmp_path):
    k = gitsiz(tmp_path)
    hazirla(k)
    snapshot.golge_sil(k)
    assert not snapshot.golge_dizini(k).exists() and k.is_dir() and (k / "a.txt").is_file()  # kullanicinin klasorune dokunulmadi


# ---------- arayuz: gitsiz klasorde tam gorev + geri al ----------
def test_arayuzde_gitsiz_klasorde_gorev_calisir_geri_al_dosyayi_siler(kur, tmp_path):
    app, sv, api, _ = kur()
    k = gitsiz(tmp_path)
    st, d = api("POST", "/api/klasor", {"yol": str(k)})
    assert st == 200 and d["git"] is True and d["golge"] is True
    tam_kosu(app, api, k, karar=False)
    assert not (k / "yeni.txt").exists() and not (k / ".git").exists()  # geri alindi (golge yedekten)


def test_arayuzde_gitsiz_klasorde_korunsun_dosyayi_birakir(kur, tmp_path):
    app, sv, api, _ = kur()
    k = gitsiz(tmp_path)
    tam_kosu(app, api, k, karar=True)
    assert (k / "yeni.txt").read_text(encoding="utf-8") == "yeni\n" and not (k / ".git").exists()


def test_arayuz_buyuk_gitsiz_klasoru_anlasilir_hatayla_reddeder(kur, tmp_path, monkeypatch):
    app, sv, api, _ = kur()
    k = gitsiz(tmp_path)
    monkeypatch.setattr(snapshot, "AZAMI_GOLGE_DOSYA", 1)
    st, d = api("POST", "/api/klasor", {"yol": str(k)})
    assert st == 400 and "cok buyuk" in d["hata"] and app.klasor is None
