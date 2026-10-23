"""github.py: gercek git (yerel bare 'origin' ile push dahil) + sahte gh. Ag/hesap gerekmez."""

import json
import subprocess
from pathlib import Path

import pytest

from aktapokus_ajan import github as g

SAHTE_GH = str(Path(__file__).with_name("sahte_gh.py"))


def git(klasor, *a, kontrol=True):
    return subprocess.run(["git", "-C", str(klasor), "-c", "core.quotepath=off", *a], capture_output=True, text=True, encoding="utf-8", check=kontrol).stdout


@pytest.fixture
def gh(monkeypatch, tmp_path):
    log = tmp_path / "gh.log"
    monkeypatch.setenv("AKTAPOKUS_GH", SAHTE_GH)
    monkeypatch.setenv("SAHTE_GH_LOG", str(log))

    class Gh:
        def cagrilar(self):
            return [json.loads(s)["argv"] for s in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []

    return Gh()


@pytest.fixture
def depo(tmp_path):
    """Kendi kimligi tanimli, bir commit'li depo + yerel bare 'origin'."""
    uzak = tmp_path / "uzak.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(uzak)], check=True)
    k = tmp_path / "proje"
    k.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(k)], check=True)
    git(k, "config", "user.name", "Test Kisi")
    git(k, "config", "user.email", "test@example.com")
    (k / "a.txt").write_text("bir\n", encoding="utf-8")
    git(k, "add", "-A")
    git(k, "commit", "-qm", "ilk")
    git(k, "remote", "add", "origin", str(uzak))
    return k


# ---------- gh / hesap ----------
def test_durum_giris_yapilmis(gh):
    assert g.durum() == {"kurulu": True, "giris": True, "hesap": "sahte-kullanici", "ad": "Sahte Kisi", "hata": None}


def test_durum_giris_yok_anlasilir_mesaj(gh, monkeypatch):
    monkeypatch.setenv("SAHTE_GH_GIRIS", "0")
    d = g.durum()
    assert d["kurulu"] and not d["giris"] and "gh auth login" in d["hata"]


def test_durum_gh_kurulu_degil(monkeypatch, tmp_path):
    monkeypatch.setenv("AKTAPOKUS_GH", str(tmp_path / "yok.exe"))
    d = g.durum()
    assert d == {"kurulu": False, "giris": False, "hesap": None, "hata": "GitHub CLI (gh) kurulu degil"}


def test_depolar_listelenir(gh):
    d = g.depolar()
    assert [x["depo"] for x in d] == ["sahte-kullanici/proje-bir", "sahte-kullanici/proje-iki"] and d[0]["ozel"] is True and d[1]["aciklama"] == ""
    assert gh.cagrilar()[-1][:3] == ["repo", "list", "--limit"]


def test_gh_hatasindaki_token_benzeri_dizgeler_ayiklanir(gh, monkeypatch):
    monkeypatch.setenv("SAHTE_GH_HATA", "1")
    with pytest.raises(g.GithubHatasi) as h:
        g.depolar()
    assert "ghp_" not in str(h.value) and "***" in str(h.value)


# ---------- klonla ----------
@pytest.mark.parametrize("kotu", ["a/b/c", "https://github.com/a/b", "ext::sh -c calc", "-x/y", "a/..", "../x", "a b/c", "", "a", None, 5, "a/b;c", "a/b c"])
def test_klonla_gecersiz_depo_reddedilir_ve_gh_calistirilmaz(gh, tmp_path, kotu):
    with pytest.raises(g.GithubHatasi):
        g.klonla(kotu, tmp_path)
    assert gh.cagrilar() == []


def test_klonla_hedef_kosullari(gh, tmp_path):
    with pytest.raises(g.GithubHatasi, match="TAM yol"):
        g.klonla("a/b", "goreli/klasor")
    with pytest.raises(g.GithubHatasi, match="TAM yol"):
        g.klonla("a/b", tmp_path / "yok")
    (tmp_path / "b").mkdir()
    with pytest.raises(g.GithubHatasi, match="zaten var"):
        g.klonla("a/b", tmp_path)
    for kotu_ad in ("../kacis", "a/b", "a b", ".git", "-x", "x" * 101):
        with pytest.raises(g.GithubHatasi, match="Klasor adi"):
            g.klonla("a/c", tmp_path, kotu_ad)
    assert gh.cagrilar() == []


def test_klonla_basarili_ve_ad_degistirilebilir(gh, tmp_path):
    hedef = g.klonla("sahte-kullanici/proje-bir", tmp_path)
    assert hedef == tmp_path / "proje-bir" and (hedef / "README.md").is_file()
    assert gh.cagrilar()[-1] == ["repo", "clone", "sahte-kullanici/proje-bir", str(hedef)]
    assert g.klonla("sahte-kullanici/proje-bir", tmp_path, "baska-ad") == tmp_path / "baska-ad"
    assert g._uzak_bilgi(hedef)["depo"] == "sahte-kullanici/proje-bir"


# ---------- proje durumu ----------
def test_proje_durumu_temiz_ve_degisikliklerle(depo):
    d = g.proje_durumu(depo)
    assert d["dal"] == "main" and d["degisen_sayisi"] == 0 and d["kimlik"] == {"ad": "Test Kisi", "eposta": "test@example.com"} and d["upstream"] is False
    (depo / "a.txt").write_text("iki\n", encoding="utf-8")
    (depo / "yeni dosya ç.txt").write_text("x", encoding="utf-8")
    (depo / ".env").write_text("SIR=1", encoding="utf-8")
    d = g.proje_durumu(depo)
    yollar = {x["yol"]: x for x in d["degisen"]}
    assert set(yollar) == {"a.txt", "yeni dosya ç.txt", ".env"} and yollar[".env"]["gizli"] is True and yollar["a.txt"]["durum"] == "M" and d["gizli_sayisi"] == 1


def test_proje_durumu_kendi_izlenmeyen_dosyalarini_gizler(depo):
    (depo / ".aktapokus").mkdir()
    (depo / ".aktapokus" / "ayar.json").write_text("{}")
    (depo / ".opencode").mkdir()
    (depo / ".opencode" / "opencode.json").write_text("{}")
    assert g.proje_durumu(depo)["degisen_sayisi"] == 0


def test_proje_durumu_git_deposu_degilse_anlasilir_hata(tmp_path):
    with pytest.raises(g.GithubHatasi, match="git deposu degil"):
        g.proje_durumu(tmp_path)


def test_proje_durumu_yeniden_adlandirma_ve_upstream(depo):
    git(depo, "mv", "a.txt", "b.txt")
    assert [x["yol"] for x in g.proje_durumu(depo)["degisen"]] == ["b.txt"]
    git(depo, "commit", "-qm", "ad degisti")
    git(depo, "push", "-q", "-u", "origin", "main")
    (depo / "c.txt").write_text("c")
    git(depo, "add", "-A")
    git(depo, "commit", "-qm", "yerel")
    d = g.proje_durumu(depo)
    assert d["upstream"] is True and (d["onde"], d["geride"]) == (1, 0)


# ---------- commit ----------
def test_commit_degisiklikleri_kullanici_kimligiyle_yazar(depo):
    (depo / "a.txt").write_text("iki\n", encoding="utf-8")
    (depo / "yeni dosya ç.txt").write_text("x", encoding="utf-8")
    r = g.commit(depo, "  Basliklari guncelle  ")
    assert r["dosya_sayisi"] == 2 and r["atlanan_gizli"] == []
    assert git(depo, "log", "-1", "--format=%an <%ae>|%s").strip() == "Test Kisi <test@example.com>|Basliklari guncelle"
    assert set(git(depo, "show", "--name-only", "--format=", "HEAD").split("\n")) - {""} == {"a.txt", "yeni dosya ç.txt"}
    assert git(depo, "status", "--porcelain") == ""


def test_commit_gizli_dosyalari_ve_kendi_dosyalarini_dahil_etmez(depo):
    for ad in (".env", ".env.local", "anahtar.pem", "id_rsa", ".npmrc"):
        (depo / ad).write_text("sir")
    (depo / ".aktapokus").mkdir()
    (depo / ".aktapokus" / "ayar.json").write_text("{}")
    (depo / ".opencode").mkdir()
    (depo / ".opencode" / "opencode.json").write_text("{}")
    (depo / "kod.py").write_text("print(1)")
    r = g.commit(depo, "kod ekle")
    assert git(depo, "show", "--name-only", "--format=", "HEAD").split() == ["kod.py"]
    assert sorted(r["atlanan_gizli"]) == [".env", ".env.local", ".npmrc", "anahtar.pem", "id_rsa"]
    assert (depo / ".env").exists()  # atlanan dosyalar SILINMEZ
    assert ".aktapokus/ayar.json" in git(depo, "status", "--porcelain", "-uall") or ".aktapokus/" in git(depo, "status", "--porcelain")  # hala izlenmiyor


def test_commit_izlenen_opencode_dosyasindaki_degisiklik_dahil_edilir(depo):
    (depo / ".opencode").mkdir()
    (depo / ".opencode" / "kural.md").write_text("bir")
    git(depo, "add", "-f", ".opencode/kural.md")
    git(depo, "commit", "-qm", "kural")
    (depo / ".opencode" / "kural.md").write_text("iki")  # kullanici bunu izliyor: degisiklik commit'e girmeli
    g.commit(depo, "kural guncelle")
    assert ".opencode/kural.md" in git(depo, "show", "--name-only", "--format=", "HEAD")


def test_commit_hazirlanmis_gizli_dosya_varsa_reddeder_ve_dokunmaz(depo):
    (depo / ".env").write_text("sir")
    git(depo, "add", "-f", ".env")
    (depo / "kod.py").write_text("x")
    onceki = git(depo, "rev-parse", "HEAD")
    with pytest.raises(g.GithubHatasi, match="staged"):
        g.commit(depo, "m")
    assert git(depo, "rev-parse", "HEAD") == onceki and ".env" in git(depo, "diff", "--cached", "--name-only")  # indekse dokunulmadi


@pytest.mark.parametrize("mesaj", ["", "   ", None, 5, "x" * (g.AZAMI_MESAJ + 1), "a\x00b"])
def test_commit_gecersiz_mesaj(depo, mesaj):
    (depo / "kod.py").write_text("x")
    with pytest.raises(g.GithubHatasi):
        g.commit(depo, mesaj)
    assert "kod.py" in git(depo, "status", "--porcelain")


def test_commit_degisiklik_yoksa_ve_yalniz_gizli_varsa(depo):
    with pytest.raises(g.GithubHatasi, match="degisiklik yok"):
        g.commit(depo, "m")
    (depo / ".env").write_text("sir")
    with pytest.raises(g.GithubHatasi, match="1 dosya atlandi"):
        g.commit(depo, "m")


def test_commit_git_kimligi_yoksa_anlasilir_hata(depo, monkeypatch, tmp_path):
    git(depo, "config", "--unset", "user.name")
    git(depo, "config", "--unset", "user.email")
    bos = tmp_path / "bosgitconfig"
    bos.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(bos))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    (depo / "kod.py").write_text("x")
    with pytest.raises(g.GithubHatasi, match="git kimligi"):
        g.commit(depo, "m")


# ---------- dal / push ----------
def test_dal_olustur(depo):
    assert g.dal_olustur(depo, "ozellik/giris") == {"dal": "ozellik/giris"}
    assert git(depo, "branch", "--show-current").strip() == "ozellik/giris"
    with pytest.raises(g.GithubHatasi):
        g.dal_olustur(depo, "ozellik/giris")  # zaten var


@pytest.mark.parametrize("kotu", ["", "-x", "a..b", "a b", "x.lock", "a/", "@{x}", "a~1", "a^", "a:b", "a\\b", "x" * 101, None, "--delete"])
def test_dal_gecersiz_adlar_reddedilir(depo, kotu):
    with pytest.raises(g.GithubHatasi):
        g.dal_olustur(depo, kotu)
    assert git(depo, "branch", "--show-current").strip() == "main"


def test_push_ilk_seferde_upstream_kurar_sonra_duz_push(depo, tmp_path):
    (depo / "b.txt").write_text("b")
    g.commit(depo, "b ekle")
    r = g.push(depo)
    assert r["dal"] == "main" and r["yeni_upstream"] is True
    assert "b ekle" in git(tmp_path / "uzak.git", "log", "--format=%s", "main")
    (depo / "c.txt").write_text("c")
    g.commit(depo, "c ekle")
    assert g.push(depo)["yeni_upstream"] is False
    assert git(tmp_path / "uzak.git", "log", "-1", "--format=%s", "main").strip() == "c ekle"


def test_push_zorla_degil_uzak_ilerideyse_reddedilir_ve_uzak_bozulmaz(depo, tmp_path):
    g.push(depo)
    diger = tmp_path / "diger"
    subprocess.run(["git", "clone", "-q", str(tmp_path / "uzak.git"), str(diger)], check=True)
    git(diger, "config", "user.name", "D")
    git(diger, "config", "user.email", "d@d")
    (diger / "x.txt").write_text("x")
    git(diger, "add", "-A")
    git(diger, "commit", "-qm", "uzakta degisiklik")
    git(diger, "push", "-q", "origin", "main")
    (depo / "y.txt").write_text("y")
    g.commit(depo, "yerel degisiklik")
    with pytest.raises(g.GithubHatasi):
        g.push(depo)
    assert git(tmp_path / "uzak.git", "log", "-1", "--format=%s", "main").strip() == "uzakta degisiklik"  # ezilmedi


def test_push_detached_head_ve_origin_yoksa(depo):
    git(depo, "remote", "remove", "origin")
    with pytest.raises(g.GithubHatasi, match="origin"):
        g.push(depo)
    git(depo, "checkout", "-q", "--detach")
    with pytest.raises(g.GithubHatasi, match="detached"):
        g.push(depo)


def test_kaynakta_zorla_push_ve_kabuk_kullanimi_yok():
    kaynak = (Path(__file__).resolve().parent.parent / "aktapokus_ajan" / "github.py").read_text(encoding="utf-8")
    kod = kaynak.split('"""', 2)[2]  # modul aciklamasi hariç (orada '--force' yok demek icin gecer)
    assert "--force" not in kod and '"-f"' not in kod and "+refs" not in kod and "shell=True" not in kod


# ---------- pull request ----------
def test_pr_ac_argumanlari_ve_url(gh, depo):
    r = g.pr_ac(depo, "-baslik tire ile baslar", "Govde\nikinci satir", True)
    assert r == {"url": "https://github.com/sahte-kullanici/proje-bir/pull/12"}
    argv = gh.cagrilar()[-1]
    assert argv == ["pr", "create", "--title", "-baslik tire ile baslar", "--body", "Govde\nikinci satir", "--draft"]
    g.pr_ac(depo, "b", "")
    assert "--draft" not in gh.cagrilar()[-1]


@pytest.mark.parametrize("baslik,govde", [("", ""), ("   ", ""), ("iki\nsatir", ""), (None, ""), ("x" * 257, ""), ("a\x00b", ""), ("ok", "g" * 20001), ("ok", "a\x00b")])
def test_pr_gecersiz_girdiler(gh, depo, baslik, govde):
    with pytest.raises(g.GithubHatasi):
        g.pr_ac(depo, baslik, govde)
    assert gh.cagrilar() == []


def test_pr_durumu_ozet_ve_pr_yoksa_none(gh, depo, monkeypatch):
    d = g.pr_durumu(depo)
    assert d["no"] == 12 and d["durum"] == "OPEN" and d["kontroller"] == {"basarili": 1, "basarisiz": 1, "bekleyen": 1}
    monkeypatch.setenv("SAHTE_GH_PR_YOK", "1")
    assert g.pr_durumu(depo) is None


# ---------- issue ----------
def test_issue_listele_ve_oku_govde_kisaltilir(gh, depo):
    assert g.issueler(depo)[0] == {"no": 7, "baslik": "Giris sayfasi hatali", "durum": "OPEN", "etiketler": ["bug"], "url": "https://github.com/sahte-kullanici/proje-bir/issues/7", "guncelleme": "2026-10-02T00:00:00Z"}
    i = g.issue_oku(depo, 7)
    assert i["no"] == 7 and len(i["govde"]) == 6000 and i["kesildi"] is True and gh.cagrilar()[-1][:3] == ["issue", "view", "7"]


@pytest.mark.parametrize("kotu", ["1; calc", "../1", "-1", "", True, None, "12345678", 1.5, "1 2"])
def test_issue_numarasi_dogrulanir(gh, depo, kotu):
    with pytest.raises(g.GithubHatasi, match="sayi"):
        g.issue_oku(depo, kotu)
    with pytest.raises(g.GithubHatasi, match="sayi"):
        g.issue_yorum(depo, kotu, "m")
    assert gh.cagrilar() == []


def test_issue_yorum(gh, depo):
    assert g.issue_yorum(depo, "7", " Tamamlandi ") == {"url": "https://github.com/sahte-kullanici/proje-bir/issues/7#issuecomment-1"}
    assert gh.cagrilar()[-1] == ["issue", "comment", "7", "--body", "Tamamlandi"]
    for kotu in ("", "  ", None, "x" * 4001, "a\x00b"):
        with pytest.raises(g.GithubHatasi):
            g.issue_yorum(depo, 7, kotu)


# ---------- gizli dosya deseni ----------
@pytest.mark.parametrize("yol", [".env", ".env.local", "a/.env.production", "k.pem", "x/anahtar.KEY", "id_rsa", "id_ed25519.pub", ".npmrc", "credentials.json", "secrets.yaml", ".netrc", "a/b/api.token", "k.p12"])
def test_gizli_yol_mu_evet(yol):
    assert g.gizli_yol_mu(yol)


@pytest.mark.parametrize("yol", ["a.txt", "src/main.py", "environment.md", "README.md", "keyboard.py", "docs/secretary.md"])
def test_gizli_yol_mu_hayir(yol):
    assert not g.gizli_yol_mu(yol)


def test_gizli_desen_arayuzdekini_kapsar():
    from aktapokus_ajan import arayuz

    for uz in arayuz.GIZLI_UZANTILAR:
        assert g.gizli_yol_mu("x" + uz), uz
    for ad in arayuz.GIZLI_ADLAR:
        assert g.gizli_yol_mu(ad), ad
