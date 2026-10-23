"""gityonet.py: gercek git ile (yerel bare origin dahil) gecmis, fark, stage, atma, dal, merge, pull, stash ve commit mesaji onerisi."""

import subprocess
from pathlib import Path

import pytest

from aktapokus_ajan import github as g
from aktapokus_ajan import gityonet as y


def git(k, *a, kontrol=True):
    return subprocess.run(["git", "-C", str(k), "-c", "core.quotepath=off", *a], capture_output=True, text=True, encoding="utf-8", check=kontrol).stdout


@pytest.fixture
def depo(tmp_path):
    uzak = tmp_path / "uzak.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(uzak)], check=True)
    k = tmp_path / "proje"
    k.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(k)], check=True)
    git(k, "config", "user.name", "Test Kisi")
    git(k, "config", "user.email", "t@example.com")
    (k / "a.txt").write_text("bir\n", encoding="utf-8")
    (k / "b.txt").write_text("iki\n", encoding="utf-8")
    git(k, "add", "-A")
    git(k, "commit", "-qm", "ilk commit")
    git(k, "remote", "add", "origin", str(uzak))
    git(k, "push", "-q", "-u", "origin", "main")
    return k


def yaz(k, ad, icerik="x\n"):
    (k / ad).write_text(icerik, encoding="utf-8")


# ---------- gecmis / commit ayrintisi / fark ----------
def test_gecmis_siralama_alanlar_ve_gonderilmedi_isareti(depo):
    yaz(depo, "c.txt")
    git(depo, "add", "-A")
    git(depo, "commit", "-qm", "ikinci commit")
    h = y.gecmis(depo)
    assert [c["konu"] for c in h] == ["ikinci commit", "ilk commit"]
    assert h[0]["gonderilmedi"] is True and h[1]["gonderilmedi"] is False  # ilk commit push edildi, ikincisi edilmedi
    assert h[0]["yazar"] == "Test Kisi" and len(h[0]["sha"]) == 40 and len(h[0]["kisa"]) < 40 and h[0]["tarih"][:2] == "20"
    assert len(y.gecmis(depo, 1)) == 1


def test_gecmis_commit_yoksa_bos(tmp_path):
    k = tmp_path / "bos"
    k.mkdir()
    subprocess.run(["git", "init", "-q", str(k)], check=True)
    assert y.gecmis(k) == []


def test_commit_ayrintisi_dosyalar_ve_mesaj(depo):
    yaz(depo, "yeni ç.txt")
    (depo / "b.txt").unlink()
    yaz(depo, "a.txt", "degisti\n")
    git(depo, "add", "-A")
    git(depo, "commit", "-qm", "Baslik\n\nUzun aciklama satiri")
    a = y.commit_ayrinti(depo, git(depo, "rev-parse", "HEAD").strip())
    assert a["mesaj"] == "Baslik\n\nUzun aciklama satiri" and a["yazar"] == "Test Kisi"
    assert {(d["durum"], d["yol"]) for d in a["dosyalar"]} == {("A", "yeni ç.txt"), ("D", "b.txt"), ("M", "a.txt")}
    assert y.commit_ayrinti(depo, git(depo, "rev-parse", "--short", "HEAD").strip())["dosya_sayisi"] == 3  # kisa ad de kabul


@pytest.mark.parametrize("kotu", ["", "xyz", "HEAD", "--all", "abc;rm", "a" * 41, None, 5, "ABCDEF1"])
def test_gecersiz_commit_adi_reddedilir(depo, kotu):
    with pytest.raises(g.GithubHatasi):
        y.commit_ayrinti(depo, kotu)
    with pytest.raises(g.GithubHatasi):
        y.fark(depo, "a.txt", sha=kotu) if kotu not in ("", None) else (_ for _ in ()).throw(g.GithubHatasi("x"))


def test_fark_calisma_agaci_hazir_ve_commit(depo):
    yaz(depo, "a.txt", "bir\nyeni satir\n")
    assert "+yeni satir" in y.fark(depo, "a.txt")["yama"]
    assert y.fark(depo, "a.txt", hazir=True)["yama"] == ""
    git(depo, "add", "a.txt")
    assert "+yeni satir" in y.fark(depo, "a.txt", hazir=True)["yama"] and y.fark(depo, "a.txt")["yama"] == ""
    git(depo, "commit", "-qm", "satir ekle")
    assert "+yeni satir" in y.fark(depo, "a.txt", sha=git(depo, "rev-parse", "HEAD").strip())["yama"]


def test_fark_izlenmeyen_yeni_dosyayi_tamami_eklendi_gosterir_ikiliyi_gostermez(depo):
    yaz(depo, "yeni.txt", "ilk\nikinci\n")
    yama = y.fark(depo, "yeni.txt")["yama"]
    assert "new file" in yama and "+ilk" in yama and "+ikinci" in yama and "@@ -0,0 +1,2 @@" in yama
    (depo / "ikili.bin").write_bytes(b"\x00\x01\x02" * 100)
    assert "ikili dosya" in y.fark(depo, "ikili.bin")["yama"]


def test_fark_uzun_ciktiyi_kisaltir(depo):
    yaz(depo, "buyuk.txt", "satir\n" * 40000)
    git(depo, "add", "buyuk.txt")
    r = y.fark(depo, "buyuk.txt", hazir=True)
    assert r["kesildi"] is True and len(r["yama"]) < y.AZAMI_FARK + 50


@pytest.mark.parametrize("yol", [".env", "a/.env.local", "anahtar.pem", "id_rsa"])
def test_gizli_dosyanin_farki_gosterilmez(depo, yol):
    (depo / Path(yol).parent).mkdir(exist_ok=True)
    yaz(depo, yol, "SIR=1\n")
    with pytest.raises(g.GithubHatasi, match="Gizli"):
        y.fark(depo, yol)


@pytest.mark.parametrize("yol", ["", "../x", "..\\x", "/etc/passwd", "C:\\x", "a/../../x", ".git/config", None, 5, "a\x00b"])
def test_fark_gecersiz_yol_reddedilir(depo, yol):
    with pytest.raises(g.GithubHatasi):
        y.fark(depo, yol)


# ---------- hazirlama / cikarma / atma ----------
def test_hazirla_ve_hazirdan_cikar_dosya_dosya(depo):
    yaz(depo, "a.txt", "degisti\n")
    yaz(depo, "yeni.txt")
    yaz(depo, "ucuncu ç.txt")
    y.hazirla(depo, ["a.txt", "ucuncu ç.txt"])
    d = {x["yol"]: x for x in g.proje_durumu(depo)["degisen"]}
    assert d["a.txt"]["hazir"] and d["ucuncu ç.txt"]["hazir"] and not d["yeni.txt"]["hazir"] and g.proje_durumu(depo)["hazir_sayisi"] == 2
    y.hazirdan_cikar(depo, ["a.txt"])
    d = {x["yol"]: x for x in g.proje_durumu(depo)["degisen"]}
    assert not d["a.txt"]["hazir"] and d["a.txt"]["calisma"] and d["ucuncu ç.txt"]["hazir"]
    assert (depo / "a.txt").read_text(encoding="utf-8") == "degisti\n"  # dosya icerigi korundu


def test_hazirla_silinen_dosyayi_da_hazirlar(depo):
    (depo / "b.txt").unlink()
    y.hazirla(depo, ["b.txt"])
    assert [x for x in g.proje_durumu(depo)["degisen"] if x["yol"] == "b.txt"][0]["durum"] == "D" and g.proje_durumu(depo)["hazir_sayisi"] == 1


def test_hazirla_gizli_dosyayi_reddeder_ve_hicbir_seyi_hazirlamaz(depo):
    yaz(depo, ".env", "S=1")
    yaz(depo, "iyi.txt")
    with pytest.raises(g.GithubHatasi, match="Gizli"):
        y.hazirla(depo, ["iyi.txt", ".env"])
    assert g.proje_durumu(depo)["hazir_sayisi"] == 0


def test_hazirdan_cikar_ilk_commit_oncesi_depoda_da_calisir(tmp_path):
    k = tmp_path / "yeni"
    k.mkdir()
    subprocess.run(["git", "init", "-q", str(k)], check=True)
    yaz(k, "a.txt")
    y.hazirla(k, ["a.txt"])
    assert g.proje_durumu(k)["hazir_sayisi"] == 1
    y.hazirdan_cikar(k, ["a.txt"])
    assert g.proje_durumu(k)["hazir_sayisi"] == 0 and (k / "a.txt").exists()


@pytest.mark.parametrize("yollar", [[], None, "a.txt", [5], ["a"] * 501, [".git/x"]])
def test_hazirlama_gecersiz_liste(depo, yollar):
    with pytest.raises(g.GithubHatasi):
        y.hazirla(depo, yollar)


def test_degisikligi_at_izlenen_geri_gelir_izlenmeyen_silinir(depo):
    yaz(depo, "a.txt", "bozuk\n")
    yaz(depo, "yeni.txt", "gecici\n")
    y.hazirla(depo, ["a.txt"])
    r = y.degisikligi_at(depo, ["a.txt", "yeni.txt"])
    assert r == {"geri_alinan": 1, "silinen": 1}
    assert (depo / "a.txt").read_text(encoding="utf-8") == "bir\n" and not (depo / "yeni.txt").exists()
    assert g.proje_durumu(depo)["degisen_sayisi"] == 0


def test_degisikligi_at_yalniz_istenen_dosyalara_dokunur(depo):
    yaz(depo, "a.txt", "a-degisti\n")
    yaz(depo, "b.txt", "b-degisti\n")
    y.degisikligi_at(depo, ["a.txt"])
    assert (depo / "a.txt").read_text(encoding="utf-8") == "bir\n" and (depo / "b.txt").read_text(encoding="utf-8") == "b-degisti\n"


def test_degisikligi_at_gizli_ve_degisikligi_olmayan_dosyayi_reddeder(depo):
    yaz(depo, ".env", "SIR")
    with pytest.raises(g.GithubHatasi, match="Gizli"):
        y.degisikligi_at(depo, [".env"])
    assert (depo / ".env").exists()  # gizli dosya SILINMEDI
    with pytest.raises(g.GithubHatasi, match="degisiklik yok"):
        y.degisikligi_at(depo, ["a.txt"])


def test_degisikligi_at_klasoru_ya_da_proje_disini_silmez(depo, tmp_path):
    (depo / "alt").mkdir()
    yaz(depo / "alt", "x.txt")
    disarida = tmp_path / "disarida.txt"
    disarida.write_text("dokunma")
    with pytest.raises(g.GithubHatasi):
        y.degisikligi_at(depo, ["../disarida.txt"])
    assert disarida.exists()


def test_degisikligi_at_silinen_dosyayi_geri_getirir(depo):
    (depo / "b.txt").unlink()
    y.degisikligi_at(depo, ["b.txt"])
    assert (depo / "b.txt").read_text(encoding="utf-8") == "iki\n"


# ---------- dallar ----------
def test_dallar_listesi_aktif_upstream_ve_uzakta_olanlar(depo, tmp_path):
    git(depo, "branch", "yerel-dal")
    git(depo, "push", "-q", "origin", "main:uzak-dal")
    git(depo, "fetch", "-q")
    d = y.dallar(depo)
    adlar = {x["ad"]: x for x in d["yerel"]}
    assert set(adlar) == {"main", "yerel-dal"} and adlar["main"]["aktif"] and not adlar["yerel-dal"]["aktif"] and adlar["main"]["upstream"] == "origin/main"
    assert d["uzak_yalniz"] == ["uzak-dal"]


def test_dal_gec_yerel_ve_uzaktaki_dala(depo):
    git(depo, "branch", "yerel-dal")
    git(depo, "push", "-q", "origin", "main:uzak-dal")
    git(depo, "fetch", "-q")
    assert y.dal_gec(depo, "yerel-dal") == {"dal": "yerel-dal"} and git(depo, "branch", "--show-current").strip() == "yerel-dal"
    y.dal_gec(depo, "uzak-dal")
    assert git(depo, "branch", "--show-current").strip() == "uzak-dal"
    assert "uzak-dal" in [x["ad"] for x in y.dallar(depo)["yerel"]]  # yerel takip dali kuruldu


def test_dal_gec_degisiklik_cakisiyorsa_git_reddeder_dosya_korunur(depo):
    git(depo, "switch", "-q", "-c", "diger")
    yaz(depo, "a.txt", "diger dalda\n")
    git(depo, "commit", "-qam", "diger")
    git(depo, "switch", "-q", "main")
    yaz(depo, "a.txt", "main'de yerel degisiklik\n")
    with pytest.raises(g.GithubHatasi):
        y.dal_gec(depo, "diger")
    assert (depo / "a.txt").read_text(encoding="utf-8") == "main'de yerel degisiklik\n" and git(depo, "branch", "--show-current").strip() == "main"


@pytest.mark.parametrize("kotu", ["", "-x", "yok-dal", "a..b", "a b", None, "--detach", "x" * 101])
def test_dal_gec_gecersiz(depo, kotu):
    with pytest.raises(g.GithubHatasi):
        y.dal_gec(depo, kotu)


def test_dal_sil_yalniz_birlestirilmis_ve_aktif_olmayan(depo):
    git(depo, "branch", "birlesik")
    git(depo, "switch", "-q", "-c", "birlesmemis")
    yaz(depo, "k.txt")
    git(depo, "add", "-A")
    git(depo, "commit", "-qm", "ozel is")
    git(depo, "switch", "-q", "main")
    assert y.dal_sil(depo, "birlesik") == {"silinen": "birlesik"}
    with pytest.raises(g.GithubHatasi):
        y.dal_sil(depo, "birlesmemis")  # -d: veri kaybi olmaz
    assert "birlesmemis" in git(depo, "branch", "--format=%(refname:short)")
    with pytest.raises(g.GithubHatasi, match="Uzerinde bulundugunuz"):
        y.dal_sil(depo, "main")
    with pytest.raises(g.GithubHatasi, match="yok"):
        y.dal_sil(depo, "olmayan")


def test_birlestir_basarili(depo):
    git(depo, "switch", "-q", "-c", "ozellik")
    yaz(depo, "ozellik.txt")
    git(depo, "add", "-A")
    git(depo, "commit", "-qm", "ozellik ekle")
    git(depo, "switch", "-q", "main")
    r = y.birlestir(depo, "ozellik")
    assert r["birlesen"] == "ozellik" and r["icine"] == "main" and (depo / "ozellik.txt").exists()


def test_birlestir_cakisirsa_otomatik_geri_alinir(depo):
    git(depo, "switch", "-q", "-c", "diger")
    yaz(depo, "a.txt", "diger\n")
    git(depo, "commit", "-qam", "diger degisti")
    git(depo, "switch", "-q", "main")
    yaz(depo, "a.txt", "main\n")
    git(depo, "commit", "-qam", "main degisti")
    onceki = git(depo, "rev-parse", "HEAD")
    with pytest.raises(g.GithubHatasi, match="CAKISMA"):
        y.birlestir(depo, "diger")
    gitdir = Path(git(depo, "rev-parse", "--absolute-git-dir").strip())
    assert not (gitdir / "MERGE_HEAD").exists() and git(depo, "rev-parse", "HEAD") == onceki  # yarim kalmis birlestirme yok
    assert (depo / "a.txt").read_text(encoding="utf-8") == "main\n" and git(depo, "status", "--porcelain") == ""


def test_birlestir_kirli_agacta_ve_gecersiz_dalda_reddedilir(depo):
    git(depo, "branch", "baska")
    yaz(depo, "a.txt", "kirli\n")
    with pytest.raises(g.GithubHatasi, match="commit edin"):
        y.birlestir(depo, "baska")
    git(depo, "checkout", "-q", "--", "a.txt")
    with pytest.raises(g.GithubHatasi):
        y.birlestir(depo, "main")  # kendisi
    with pytest.raises(g.GithubHatasi):
        y.birlestir(depo, "yok")


# ---------- cek / pull ----------
def _uzakta_commit(tmp_path, mesaj="uzakta degisiklik"):
    diger = tmp_path / "diger"
    if not diger.exists():
        subprocess.run(["git", "clone", "-q", str(tmp_path / "uzak.git"), str(diger)], check=True)
        git(diger, "config", "user.name", "D")
        git(diger, "config", "user.email", "d@d")
    yaz(diger, "uzak.txt", mesaj + "\n")
    git(diger, "add", "-A")
    git(diger, "commit", "-qm", mesaj)
    git(diger, "push", "-q", "origin", "main")


def test_cek_calisma_agacina_dokunmaz_pull_ileri_sarar(depo, tmp_path):
    _uzakta_commit(tmp_path)
    yaz(depo, "a.txt", "yerel degisiklik\n")
    y.cek(depo)
    assert "uzakta degisiklik" in git(depo, "log", "--format=%s", "origin/main") and not (depo / "uzak.txt").exists()
    assert (depo / "a.txt").read_text(encoding="utf-8") == "yerel degisiklik\n"
    r = y.pull(depo)  # a.txt ile cakismayan yerel degisiklik varken ff pull calisir
    assert (depo / "uzak.txt").exists() and (depo / "a.txt").read_text(encoding="utf-8") == "yerel degisiklik\n" and "cikti" in r


def test_pull_ff_yapilamazsa_reddeder_birlestirme_commiti_olusturmaz(depo, tmp_path):
    _uzakta_commit(tmp_path)
    yaz(depo, "yerel.txt")
    git(depo, "add", "-A")
    git(depo, "commit", "-qm", "yerel commit")
    onceki = git(depo, "rev-parse", "HEAD")
    with pytest.raises(g.GithubHatasi):
        y.pull(depo)
    assert git(depo, "rev-parse", "HEAD") == onceki and git(depo, "log", "--merges", "--format=%H") == ""


def test_pull_ve_cek_upstream_origin_yoksa_anlasilir_hata(depo):
    git(depo, "switch", "-q", "-c", "upstream-yok")
    with pytest.raises(g.GithubHatasi, match="upstream"):
        y.pull(depo)
    git(depo, "remote", "remove", "origin")
    with pytest.raises(g.GithubHatasi, match="origin"):
        y.cek(depo)


# ---------- stash ----------
def test_stash_kaydet_listele_uygula_sil(depo):
    yaz(depo, "a.txt", "rafa\n")
    y.stash_kaydet(depo, "Yarim kalan is")
    assert (depo / "a.txt").read_text(encoding="utf-8") == "bir\n"  # degisiklik rafa kalkti
    s = y.stashler(depo)
    assert len(s) == 1 and s[0]["indeks"] == 0 and "Yarim kalan is" in s[0]["mesaj"] and s[0]["tarih"][:2] == "20"
    y.stash_uygula(depo, 0)
    assert (depo / "a.txt").read_text(encoding="utf-8") == "rafa\n" and len(y.stashler(depo)) == 1  # apply: raf korunur
    git(depo, "checkout", "-q", "--", "a.txt")
    y.stash_uygula(depo, 0, sil=True)  # pop
    assert y.stashler(depo) == [] and (depo / "a.txt").read_text(encoding="utf-8") == "rafa\n"


def test_stash_sil_ve_gecersiz_numara(depo):
    yaz(depo, "a.txt", "1\n")
    y.stash_kaydet(depo, "")
    assert "Aktapokus" in y.stashler(depo)[0]["mesaj"]  # bos mesajda varsayilan ad
    for kotu in (-1, 5, "0", True, None, 1.5):
        with pytest.raises(g.GithubHatasi):
            y.stash_sil(depo, kotu)
    assert y.stash_sil(depo, 0) == {"silinen": 0} and y.stashler(depo) == []


def test_stash_degisiklik_yoksa_ve_gecersiz_mesaj(depo):
    with pytest.raises(g.GithubHatasi, match="degisikligi yok"):
        y.stash_kaydet(depo, "m")
    yaz(depo, "a.txt", "x\n")
    for kotu in ("iki\nsatir", "x" * 201, 5):
        with pytest.raises(g.GithubHatasi):
            y.stash_kaydet(depo, kotu)
    assert (depo / "a.txt").read_text(encoding="utf-8") == "x\n"  # reddedilince degisiklik rafa kalkmadi


def test_stash_uygulama_cakismada_stash_silinmez(depo):
    yaz(depo, "a.txt", "rafta\n")
    y.stash_kaydet(depo, "raf")
    yaz(depo, "a.txt", "yerel baska\n")
    with pytest.raises(g.GithubHatasi, match="silinmedi"):
        y.stash_uygula(depo, 0, sil=True)
    assert len(y.stashler(depo)) == 1


def test_stash_izlenmeyen_dosyalari_rafa_almaz(depo):
    yaz(depo, "a.txt", "izlenen\n")
    yaz(depo, "yeni.txt", "izlenmeyen\n")
    yaz(depo, ".env", "SIR")
    y.stash_kaydet(depo, "m")
    assert (depo / "yeni.txt").exists() and (depo / ".env").exists()  # gizli/izlenmeyen dosyalar yerinde


# ---------- commit mesaji onerisi ----------
def test_oneri_gorevlerden_uretilir():
    r = y.oneri_mesaji(["Giris sayfasina sifre unuttum baglantisi ekle\nDetay satiri"], [{"durum": "M", "yol": "login.html", "gizli": False}])
    assert r["kaynak"] == "gorev" and r["mesaj"].splitlines()[0] == "Giris sayfasina sifre unuttum baglantisi ekle" and r["gorev_sayisi"] == 1
    assert "Detay satiri" not in r["mesaj"]  # yalniz ilk satir


def test_oneri_birden_cok_gorev_govdede_listelenir_ve_kisaltilir():
    gorevler = ["Birinci is", "Ikinci is " + "x" * 200, "Ucuncu"]
    r = y.oneri_mesaji(gorevler, [{"durum": "M", "yol": f"d{i}.py", "gizli": False} for i in range(12)])
    ilk, *_ = r["mesaj"].splitlines()
    assert ilk == "Birinci is (+2 gorev daha)" and "Gorevler:\n- Birinci is\n- Ikinci is" in r["mesaj"] and "Degisen dosyalar (12): d0.py" in r["mesaj"] and "(+2)" in r["mesaj"]
    assert max(len(s) for s in r["mesaj"].splitlines()) < 300 and len(r["mesaj"]) <= 2000


def test_oneri_gorev_yoksa_degisikliklerden_ve_gizli_dosya_adini_yazmaz():
    r = y.oneri_mesaji([], [{"durum": "A", "yol": "src/yeni.py", "gizli": False}, {"durum": "?", "yol": "notlar.md", "gizli": False}, {"durum": "?", "yol": ".env", "gizli": True}])
    assert r["kaynak"] == "degisiklik" and r["mesaj"] == "Ekle: yeni.py, notlar.md" and ".env" not in r["mesaj"]
    assert y.oneri_mesaji([], [{"durum": "D", "yol": "eski.py", "gizli": False}])["mesaj"] == "Sil: eski.py"
    assert y.oneri_mesaji([], [{"durum": "M", "yol": f"f{i}.py", "gizli": False} for i in range(5)])["mesaj"] == "Guncelle: f0.py, f1.py, f2.py (+2 dosya)"
    assert y.oneri_mesaji([], [])["mesaj"] == "Guncelle: degisiklikler"


def test_oneri_bos_ve_bosluklu_gorevleri_atlar():
    assert y.oneri_mesaji(["   ", "", None], [{"durum": "M", "yol": "a.py", "gizli": False}])["kaynak"] == "degisiklik"


def test_son_commit_zamani(depo, tmp_path):
    assert y.son_commit_zamani(depo) > 1_700_000_000
    bos = tmp_path / "bos"
    bos.mkdir()
    subprocess.run(["git", "init", "-q", str(bos)], check=True)
    assert y.son_commit_zamani(bos) == 0.0


# ---------- commit: yalniz hazirlananlar ----------
def test_commit_yalniz_hazir_modu_sadece_hazirlananlari_alir(depo):
    yaz(depo, "a.txt", "degisti\n")
    yaz(depo, "yeni.txt")
    y.hazirla(depo, ["a.txt"])
    r = g.commit(depo, "Yalniz a", yalniz_hazir=True)
    assert r["dosya_sayisi"] == 1 and git(depo, "show", "--name-only", "--format=", "HEAD").split() == ["a.txt"]
    assert "yeni.txt" in git(depo, "status", "--porcelain")  # hazirlanmayan dosya commit'e girmedi


def test_commit_yalniz_hazir_hicbir_sey_hazir_degilse_reddeder(depo):
    yaz(depo, "a.txt", "degisti\n")
    with pytest.raises(g.GithubHatasi, match="once dosyalari secin"):
        g.commit(depo, "m", yalniz_hazir=True)
    assert "a.txt" in git(depo, "status", "--porcelain") and git(depo, "log", "--format=%s").count("\n") == 1


def test_kaynakta_tehlikeli_git_secenekleri_yok():
    kaynak = (Path(__file__).resolve().parent.parent / "aktapokus_ajan" / "gityonet.py").read_text(encoding="utf-8").split('"""', 2)[2]
    for yasak in ("--hard", "--force", "--force-with-lease", '"-D"', "shell=True", '"reset"', '"clean"', '"-f"', '"push", "origin"', "+refs"):
        assert yasak not in kaynak, yasak
