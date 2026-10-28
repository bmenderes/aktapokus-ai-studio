"""Yayinla: bir projedeki klasoru baska bir GitHub deposuna tasir (kopya + gonderme kontrolu + commit + push). Ajan GitHub'a erismez; yayin Aktapokus'un isidir."""

import os
import subprocess
from pathlib import Path

import pytest

from aktapokus_ai_studio import yayin
from conftest import SahteCalistirici, sonuc
from test_github_api import git, kur_sunucu, ortam  # noqa: F401  (pytest fixture'lari)

TOKEN = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"


# ---------- saf yol/kopya kurallari ----------
def test_hedef_yol_dogrulama():
    assert yayin.hedef_yol_dogrula(" haberler/ ") == "haberler" and yayin.hedef_yol_dogrula("/haberler/") == "haberler" and yayin.hedef_yol_dogrula("a/b.c/d_e") == "a/b.c/d_e" and yayin.hedef_yol_dogrula("a\\b") == "a/b"
    for kotu in (None, "", "..", "../x", "a/../b", "C:/x", "C:" + chr(92) + "x", ".git", "x/.git", ".github/workflows", "a b", "a//b", ".gizli", "x" * 70, "a/b/c/d/e/f"):
        with pytest.raises(yayin.YayinHatasi):
            yayin.hedef_yol_dogrula(kotu)


def test_kaynak_proje_icinde_klasor_olmali(tmp_path):
    (tmp_path / "site" / "alt").mkdir(parents=True)
    (tmp_path / "dosya.txt").write_text("x")
    (tmp_path / ".gizli").mkdir()
    assert yayin.kaynak_coz(tmp_path, "site/alt") == (tmp_path / "site" / "alt").resolve()
    assert yayin.kaynak_coz(tmp_path, "site\\alt/") == (tmp_path / "site" / "alt").resolve()
    for kotu in (None, "", "   ", "..", "../disari", "site/../../x", "/mutlak", "C:/Windows", ".gizli", "site/.git", "yok", "dosya.txt", "a\x00b"):
        with pytest.raises(yayin.YayinHatasi):
            yayin.kaynak_coz(tmp_path, kotu)


def test_aynala_gizli_dosya_noktali_buyuk_ve_sembolik_atlanir_hedef_degistirilir(tmp_path):
    kaynak, depo = tmp_path / "kaynak", tmp_path / "depo"
    (kaynak / "alt").mkdir(parents=True)
    (kaynak / "index.html").write_text("<h1>x</h1>")
    (kaynak / "alt" / "a.css").write_text("a{}")
    (kaynak / ".env").write_text("SIR=1")
    (kaynak / ".nojekyll").write_text("")
    (kaynak / "anahtar.pem").write_text("x")
    (kaynak / ".gizli-klasor").mkdir()
    (kaynak / ".gizli-klasor" / "x.txt").write_text("x")
    (kaynak / "node_modules").mkdir()
    (kaynak / "node_modules" / "m.js").write_text("x")
    (depo / "haberler" / "eski").mkdir(parents=True)
    (depo / "haberler" / "eski" / "silinecek.txt").write_text("eski")
    (depo / "baska.txt").write_text("dokunulmaz")
    s = yayin.aynala(kaynak, depo, "haberler")
    assert s["kopyalanan"] == 3 and s["silinen"] == 1 and set(s["atlanan"]) == {".env", "anahtar.pem"}
    assert sorted(p.relative_to(depo).as_posix() for p in depo.rglob("*") if p.is_file()) == ["baska.txt", "haberler/.nojekyll", "haberler/alt/a.css", "haberler/index.html"]
    assert not (depo / "haberler" / "eski").exists()  # kaynakta olmayan dosya hedefte de silinir (site kaynakla ayni kalir)


def test_aynala_sinirlar_ve_bos_kaynak(tmp_path):
    kaynak, depo = tmp_path / "k", tmp_path / "d"
    kaynak.mkdir()
    depo.mkdir()
    with pytest.raises(yayin.YayinHatasi, match="yayinlanacak dosya yok"):
        yayin.aynala(kaynak, depo, "x")
    (kaynak / "buyuk.bin").write_bytes(b"0" * (yayin.AZAMI_TEK_DOSYA + 1))
    with pytest.raises(yayin.YayinHatasi, match="cok buyuk"):
        yayin.aynala(kaynak, depo, "x")
    (kaynak / "buyuk.bin").unlink()
    for i in range(yayin.AZAMI_DOSYA + 1):
        (kaynak / f"f{i}.txt").write_text("x")
    with pytest.raises(yayin.YayinHatasi, match="cok buyuk"):
        yayin.aynala(kaynak, depo, "x")
    assert not (depo / "x").exists()  # hata olunca hedefe hicbir sey yazilmadi
    with pytest.raises(yayin.YayinHatasi):
        yayin.aynala(kaynak, depo, "../disari")


def test_yayin_adresi():
    assert yayin.yayin_adresi("aktapokus/aktapokus.github.io", "haberler") == "https://aktapokus.github.io/haberler/"
    assert yayin.yayin_adresi("aktapokus/kesif", "ders/1") == "https://aktapokus.github.io/kesif/ders/1/"


# ---------- uctan uca: kopya -> commit (yapay zeka mesaji) -> kontrol -> push ----------
def hedef_kur(ortam):
    """Hedef depo: origin adresi github.com gibi gorunur (depo eslesmesi icin), push yerel bare'e gider."""
    proje, uzak = ortam
    git(proje, "remote", "set-url", "origin", "https://github.com/sahte/hedef.git")
    git(proje, "config", "remote.origin.pushurl", str(uzak))
    git(proje, "add", "-A")
    git(proje, "commit", "-qm", "ilk icerik")  # klonlanmis depo gibi temiz baslar (yayin commit edilmemis degisiklik varken durur)
    return proje, uzak


def ai_senaryo(istemler):
    def f(k, istem, n):
        istemler.append(istem)
        return sonuc('{"sorunlar":[],"commit_mesaji":"Haberler sayfasini ekle"}')

    return f


def yayin_ortami(tmp_path, ortam, islev=None, istemler=None):
    hedef, uzak = hedef_kur(ortam)
    istemler = [] if istemler is None else istemler
    sahte = SahteCalistirici({"gizlilik denetcisi": islev or ai_senaryo(istemler), "kodcu": lambda k, i, n: sonuc("x"), "test": lambda k, i, n: sonuc("SONUC: BASARILI")})
    app, sv, istek = kur_sunucu(uret=lambda ad: sahte)
    kaynak = tmp_path / "haberler-projesi"
    (kaynak / "site").mkdir(parents=True)
    (kaynak / "site" / "index.html").write_text("<h1>Haberler</h1>", encoding="utf-8")
    (kaynak / "site" / ".env").write_text("SIR=1", encoding="utf-8")
    app.klasor_sec(str(kaynak))
    app.proje_ac(str(hedef), sec=False)  # hedef depo daha once acilmis bir proje (yoksa Aktapokus kendisi klonlar: ayri test)
    return app, sv, istek, kaynak, hedef, uzak, istemler


def test_yayinla_kopyalar_ai_mesaji_yazar_kontrol_eder_ve_gonderir(tmp_path, ortam):
    app, sv, istek, kaynak, hedef, uzak, istemler = yayin_ortami(tmp_path, ortam)
    try:
        st, h = istek("POST", "/api/github/yayin-hazirla", {"kaynak": "site", "depo": "sahte/hedef", "hedef_yol": "haberler"})
        assert st == 200 and h["kopyalanan"] == 1 and h["atlanan"] == [".env"] and h["silinen"] == 0 and h["adres"] == "https://sahte.github.io/hedef/haberler/"
        assert Path(h["klasor"]).resolve() == hedef.resolve() and (hedef / "haberler" / "index.html").read_text(encoding="utf-8") == "<h1>Haberler</h1>"
        assert not (hedef / "haberler" / ".env").exists()  # gizli dosya kopyalanmadi
        assert (kaynak / "site" / "index.html").exists()  # kaynak bozulmadi
        on = "/api/p/" + h["proje"]
        st, o = istek("GET", on + "/git/commit-oneri?yz=1")
        assert st == 200 and o["mesaj"] == "Haberler sayfasini ekle" and o["kaynak"] == "yapay zeka"
        st, kk = istek("POST", on + "/github/commit-kontrol", {"yalniz_hazir": False})
        assert st == 200 and kk["bulgular"] == []
        st, c = istek("POST", on + "/github/commit", {"mesaj": o["mesaj"]})
        assert st == 200 and c["dosya_sayisi"] == 1 and git(hedef, "log", "-1", "--format=%s").strip() == "Haberler sayfasini ekle"
        assert istek("POST", on + "/github/push", {})[0] == 409  # kontrolsuz push yok
        st, k = istek("POST", on + "/github/gonderme-kontrol", {})
        assert st == 200 and k["ai"]["durum"] == "tamam" and k["bulgular"] == [] and k["ilk_gonderim"] is True and k["dosya_sayisi"] >= 1  # ilk gonderim tum gecmisi tarar
        assert any("Haberler" in i for i in istemler)
        st, p = istek("POST", on + "/github/push", {"kontrol": k["kontrol"]})
        dosyalar = git(uzak, "ls-tree", "-r", "--name-only", p["dal"]).split()
        assert st == 200 and "haberler/index.html" in dosyalar and not any(d.endswith(".env") for d in dosyalar)  # gizli dosya uzaga GITMEDI
    finally:
        sv.kapat()


def test_hedef_depo_kayitli_degilse_klonlanir_ve_proje_olarak_acilir(tmp_path, ortam, monkeypatch):
    from aktapokus_ai_studio import github, projeler

    hedef0, uzak = hedef_kur(ortam)
    app, sv, istek = kur_sunucu(uret=lambda ad: SahteCalistirici({}))
    kaynak = tmp_path / "kaynak-proje"
    (kaynak / "site").mkdir(parents=True)
    (kaynak / "site" / "index.html").write_text("<h1>x</h1>", encoding="utf-8")
    app.klasor_sec(str(kaynak))
    cagrilar = []

    def sahte_klonla(depo, ust, ad=None):
        cagrilar.append((depo, Path(ust), ad))
        hedef = Path(ust) / ad
        subprocess.run(["git", "clone", "-q", str(uzak), str(hedef)], check=True)
        git(hedef, "config", "user.name", "T")
        git(hedef, "config", "user.email", "t@t.com")
        git(hedef, "remote", "set-url", "origin", "https://github.com/sahte/yeni-hedef.git")
        return hedef

    monkeypatch.setattr(github, "klonla", sahte_klonla)
    try:
        st, h = istek("POST", "/api/github/yayin-hazirla", {"kaynak": "site", "depo": "sahte/yeni-hedef", "hedef_yol": "s"})
        assert st == 200 and cagrilar == [("sahte/yeni-hedef", yayin.yayin_klasoru(), "sahte__yeni-hedef")]  # klon, uygulama klasorune (gercek ~/.aktapokus degil)
        assert (Path(h["klasor"]) / "s" / "index.html").exists() and h["proje"] in {p["id"] for p in projeler.listele()}  # proje olarak acildi
        st, h2 = istek("POST", "/api/github/yayin-hazirla", {"kaynak": "site", "depo": "sahte/yeni-hedef", "hedef_yol": "s"})
        assert st == 400 and "commit edilmemis" in h2["hata"] and len(cagrilar) == 1  # ikinci kez klonlanmaz; commit edilmemis kopya varken durur
    finally:
        sv.kapat()


def test_yayinlanan_icerikte_sir_varsa_commit_ve_push_engellenir(tmp_path, ortam):
    app, sv, istek, kaynak, hedef, uzak, istemler = yayin_ortami(tmp_path, ortam)
    try:
        (kaynak / "site" / "ayar.js").write_text(f'const t = "{TOKEN}";\n', encoding="utf-8")
        h = istek("POST", "/api/github/yayin-hazirla", {"kaynak": "site", "depo": "sahte/hedef", "hedef_yol": "haberler"})[1]
        on = "/api/p/" + h["proje"]
        st, kk = istek("POST", on + "/github/commit-kontrol", {"yalniz_hazir": False})
        assert st == 200 and [b["tur"] for b in kk["bulgular"]] == ["GitHub belirteci"] and TOKEN not in str(kk)
        st, d = istek("POST", on + "/github/commit", {"mesaj": "Ekle"})
        assert st == 409 and "yuksek riskli bulgu" in d["hata"]
        assert git(uzak, "branch", "--list").strip() == ""  # hicbir sey uzaga gitmedi
    finally:
        sv.kapat()


def test_hedefte_kaydedilmemis_degisiklik_varsa_ve_ayni_proje_ise_durur_gecersiz_girdiler_400(tmp_path, ortam):
    app, sv, istek, kaynak, hedef, uzak, istemler = yayin_ortami(tmp_path, ortam)
    try:
        (hedef / "yarim.txt").write_text("yarim kalmis is", encoding="utf-8")
        st, d = istek("POST", "/api/github/yayin-hazirla", {"kaynak": "site", "depo": "sahte/hedef", "hedef_yol": "haberler"})
        assert st == 400 and "commit edilmemis" in d["hata"] and not (hedef / "haberler").exists()
        for govde in ({"kaynak": "site", "depo": "kotu depo", "hedef_yol": "x"}, {"kaynak": "site", "depo": "a/b", "hedef_yol": "../x"}, {"kaynak": "../disari", "depo": "a/b", "hedef_yol": "x"},
                      {"kaynak": "", "depo": "a/b", "hedef_yol": "x"}, {"kaynak": "yok-klasor", "depo": "sahte/hedef", "hedef_yol": "x"}, {}):
            assert istek("POST", "/api/github/yayin-hazirla", govde)[0] == 400, govde
        app.klasor_sec(str(hedef))  # kaynak = hedef ayni proje
        (hedef / "yarim.txt").unlink()
        (hedef / "s").mkdir()
        (hedef / "s" / "i.txt").write_text("x")
        st, d = istek("POST", "/api/github/yayin-hazirla", {"kaynak": "s", "depo": "sahte/hedef", "hedef_yol": "x"})
        assert st == 400 and "ayni proje" in d["hata"]
    finally:
        sv.kapat()


def test_yayin_ucu_belirtec_ister_ve_uzaktan_yonetim_izni_olmadan_reddedilir(tmp_path, ortam):
    from aktapokus_ai_studio import uzak

    app, sv, istek, *_ = yayin_ortami(tmp_path, ortam)
    try:
        assert istek("POST", "/api/github/yayin-hazirla", {}, token=None)[0] == 401
        assert uzak.politika("POST", "/api/github/yayin-hazirla", uzak.Ayar())
        assert uzak.politika("POST", "/api/github/yayin-hazirla", uzak.Ayar(yonetim=True)) is None
    finally:
        sv.kapat()


def test_arayuz_yayinla_penceresi_baglidir():
    html = (Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "web" / "index.html").read_text(encoding="utf-8")
    for parca in ("/api/github/yayin-hazirla", "function yayinPenceresi", "yayinAkisi", '"/github/gonderme-kontrol"', '"/git/commit-oneri?yz=1"'):
        assert parca in html, parca


# ---------- kok modu: deponun kokune EKLE (silme yok, ayni adli dosyalar degisir; yalniz acik istekle) ----------
def test_kok_hedefi_yalniz_acik_izinle_gecerlidir():
    assert yayin.hedef_yol_dogrula("", True) == "" and yayin.hedef_yol_dogrula(" / ", True) == "" and yayin.hedef_yol_dogrula("haberler", True) == "haberler"
    for kotu in ("", " ", "/"):
        with pytest.raises(yayin.YayinHatasi):
            yayin.hedef_yol_dogrula(kotu)
    assert yayin.yayin_adresi("bmenderes/bmenderes.github.io", "") == "https://bmenderes.github.io/"


def test_kok_aynala_hicbir_seyi_silmez_ayni_adlilari_listeler(tmp_path):
    kaynak, depo = tmp_path / "k", tmp_path / "d"
    (kaynak / "alt").mkdir(parents=True)
    (kaynak / "index.html").write_text("yeni", encoding="utf-8")
    (kaynak / "alt" / "a.txt").write_text("a", encoding="utf-8")
    (kaynak / ".env").write_text("SIR=1", encoding="utf-8")
    (depo / "sorun-ne").mkdir(parents=True)
    (depo / "index.html").write_text("eski yazi", encoding="utf-8")
    (depo / "sorun-ne" / "x.html").write_text("kalmali", encoding="utf-8")
    (depo / "alt").mkdir()
    (depo / "alt" / "a.txt").write_text("a", encoding="utf-8")  # ayni icerik: ezilmis sayilmaz
    s = yayin.aynala(kaynak, depo, "", kok_izinli=True)
    assert s["silinen"] == 0 and s["kopyalanan"] == 2 and s["ezilen"] == ["index.html"] and s["ezilen_sayisi"] == 1 and s["atlanan"] == [".env"]
    assert (depo / "index.html").read_text(encoding="utf-8") == "yeni" and (depo / "sorun-ne" / "x.html").read_text(encoding="utf-8") == "kalmali"  # baska dosyalar yerinde
    assert not (depo / ".env").exists()
    with pytest.raises(yayin.YayinHatasi):
        yayin.aynala(kaynak, depo, "")  # izin yoksa bos hedef reddedilir (depo silinmesin)


def test_kok_aynala_klasor_dosya_cakismasini_reddeder(tmp_path):
    kaynak, depo = tmp_path / "k", tmp_path / "d"
    kaynak.mkdir()
    depo.mkdir()
    (kaynak / "alt").write_text("dosya", encoding="utf-8")
    (depo / "alt").mkdir()
    with pytest.raises(yayin.YayinHatasi):
        yayin.aynala(kaynak, depo, "", kok_izinli=True)


def test_kok_yayini_uc_noktada_acik_istek_ister_ve_mevcut_icerigi_korur(tmp_path, ortam):
    app, sv, istek, kaynak, hedef, uzak, istemler = yayin_ortami(tmp_path, ortam)
    try:
        onceki = sorted(p.name for p in hedef.iterdir() if p.name != ".git")
        st, h = istek("POST", "/api/github/yayin-hazirla", {"kaynak": "site", "depo": "sahte/hedef", "hedef_yol": ""})
        assert st == 400 and sorted(p.name for p in hedef.iterdir() if p.name != ".git") == onceki  # kok=true yok: hicbir sey kopyalanmadi
        st, h = istek("POST", "/api/github/yayin-hazirla", {"kaynak": "site", "depo": "sahte/hedef", "hedef_yol": "", "kok": True})
        assert st == 200 and h["hedef_yol"] == "" and h["silinen"] == 0 and h["adres"] == "https://sahte.github.io/hedef/"
        assert (hedef / "index.html").read_text(encoding="utf-8") == "<h1>Haberler</h1>" and all((hedef / n).exists() for n in onceki)  # onceki dosyalar duruyor
    finally:
        sv.kapat()


def test_kok_yayini_engellenirse_calisma_agaci_eski_haline_doner(tmp_path):
    depo = tmp_path / "d"
    depo.mkdir()
    subprocess.run(["git", "init", "-q", str(depo)], check=True)
    (depo / "index.html").write_text("eski", encoding="utf-8")
    subprocess.run(["git", "-C", str(depo), "-c", "user.name=t", "-c", "user.email=t@t", "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(depo), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "ilk"], check=True)
    kaynak = tmp_path / "k"
    kaynak.mkdir()
    (kaynak / "index.html").write_text("yeni", encoding="utf-8")
    (kaynak / "yeni.html").write_text("y", encoding="utf-8")
    yayin.aynala(kaynak, depo, "", kok_izinli=True)
    yayin.calisma_geri_al(depo, "")
    assert (depo / "index.html").read_text(encoding="utf-8") == "eski" and not (depo / "yeni.html").exists()
