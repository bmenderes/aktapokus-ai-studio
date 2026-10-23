"""GitHub HTTP uclari: belirtec/Origin, gorev surerken kisit, kilit, issue->gorev (guvenilmeyen metin), klonla->proje. Sahte gh + gercek git."""

import http.client
import json
import subprocess
from pathlib import Path

import pytest

from aktapokus_ajan import projeler
from aktapokus_ajan.arayuz import ArayuzSunucusu, Uygulama
from test_arayuz import Engelli, Istemci, bekle

SAHTE_GH = str(Path(__file__).with_name("sahte_gh.py"))

GET_UCLARI = ["/api/github/durum", "/api/github/depolar", "/api/github/proje", "/api/github/issueler"]
POST_UCLARI = ["/api/github/klonla", "/api/github/commit", "/api/github/dal", "/api/github/push", "/api/github/pr", "/api/github/issue-gorev", "/api/github/issue-yorum"]


def git(k, *a):
    return subprocess.run(["git", "-C", str(k), "-c", "core.quotepath=off", *a], capture_output=True, text=True, encoding="utf-8", check=True).stdout


@pytest.fixture
def ortam(proje, tmp_path, monkeypatch):
    monkeypatch.setenv("AKTAPOKUS_GH", SAHTE_GH)
    monkeypatch.setenv("SAHTE_GH_LOG", str(tmp_path / "gh.log"))
    uzak = tmp_path / "uzak.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(uzak)], check=True)
    git(proje, "checkout", "-q", "-B", "main")
    git(proje, "config", "user.name", "Test")
    git(proje, "config", "user.email", "t@t.com")
    git(proje, "remote", "add", "origin", str(uzak))
    return proje, uzak


def kur_sunucu(uret=None):
    app = Uygulama(**({"calistirici_uret": uret} if uret else {}))
    sv = ArayuzSunucusu(app)
    sv.baslat()
    return app, sv, Istemci(sv)


@pytest.fixture
def api(ortam):
    proje, uzak = ortam
    app, sv, istek = kur_sunucu()
    app.klasor_sec(str(proje))
    yield app, sv, istek, proje, uzak
    sv.kapat()


# ---------- guvenlik ----------
def test_tum_uclar_belirtec_ister(api):
    _, _, istek, _, _ = api
    for yol in GET_UCLARI:
        assert istek("GET", yol, token=None)[0] == 401, yol
    for yol in POST_UCLARI:
        assert istek("POST", yol, {}, token=None)[0] == 401, yol
        assert istek("POST", yol, {}, token="yanlis")[0] == 401, yol


def test_yabanci_origin_yazan_istekleri_reddeder(api):
    _, sv, _, _, _ = api
    for yol in POST_UCLARI:
        c = http.client.HTTPConnection("127.0.0.1", sv.port, timeout=10)
        c.request("POST", yol, body="{}", headers={"X-Aktapokus-Token": sv.app.token, "Origin": "http://evil.example", "Content-Type": "application/json"})
        r = c.getresponse()
        r.read()
        c.close()
        assert r.status == 403, yol


def test_telegram_githuba_dokunmaz():
    kaynak = (Path(__file__).resolve().parent.parent / "aktapokus_ajan" / "telegram.py").read_text(encoding="utf-8").lower()
    assert "github_commit" not in kaynak and "github_push" not in kaynak and "github_pr" not in kaynak and "github_klonla" not in kaynak and "import github" not in kaynak and "from . import github" not in kaynak


# ---------- okuma ----------
def test_durum_ve_depolar(api):
    _, _, istek, _, _ = api
    assert istek("GET", "/api/github/durum")[1]["hesap"] == "sahte-kullanici"
    assert [d["depo"] for d in istek("GET", "/api/github/depolar")[1]["depolar"]] == ["sahte-kullanici/proje-bir", "sahte-kullanici/proje-iki"]


def test_depolar_giris_yoksa_anlasilir_hata(api, monkeypatch):
    _, _, istek, _, _ = api
    monkeypatch.setenv("SAHTE_GH_GIRIS", "0")
    monkeypatch.setenv("SAHTE_GH_HATA", "1")
    st, d = istek("GET", "/api/github/depolar")
    assert st == 400 and "ghp_" not in json.dumps(d)


def test_proje_durumu_degisiklikler_ve_pr(api):
    _, _, istek, proje, _ = api
    (proje / "a.txt").write_text("degisti\n")
    (proje / ".env").write_text("SIR=1")
    st, d = istek("GET", "/api/github/proje")
    assert st == 200 and d["dal"] == "main" and d["gizli_sayisi"] == 1 and {x["yol"] for x in d["degisen"]} >= {"a.txt", ".env"}
    assert d["pr"] is None  # uzak 'depo' GitHub adresi degil (yerel bare): PR sorgulanmaz
    assert d["kimlik"]["eposta"] == "t@t.com"


def test_proje_durumu_github_uzakliysa_pr_gelir(api):
    _, _, istek, proje, _ = api
    git(proje, "remote", "set-url", "origin", "https://github.com/sahte-kullanici/proje-bir.git")
    st, d = istek("GET", "/api/github/proje")
    assert d["uzak"]["depo"] == "sahte-kullanici/proje-bir" and d["pr"]["no"] == 12 and d["pr"]["kontroller"]["basarisiz"] == 1


def test_git_olmayan_klasorde_anlasilir_hata(ortam, tmp_path):
    app, sv, istek = kur_sunucu()
    try:
        k = tmp_path / "gitsiz"
        k.mkdir()
        (k / "a.txt").write_text("a")
        app.klasor_sec(str(k))  # golge yedek: GitHub ozellikleri icin gercek git deposu gerekir
        st, d = istek("GET", "/api/github/proje")
        assert st == 400 and "git deposu degil" in d["hata"]
    finally:
        sv.kapat()


# ---------- yazan islemler ----------
def test_commit_dal_push_tam_dongu_yerel_origin(api):
    _, _, istek, proje, uzak = api
    (proje / "yeni.txt").write_text("yeni")
    (proje / ".env").write_text("SIR")
    assert istek("POST", "/api/github/dal", {"ad": "ozellik/giris"})[1] == {"dal": "ozellik/giris"}
    st, d = istek("POST", "/api/github/commit", {"mesaj": "Giris ekle"})
    assert st == 200 and d["atlanan_gizli"] == [".env"] and "yeni.txt" in git(proje, "show", "--name-only", "--format=", "HEAD")
    st, d = istek("POST", "/api/github/push", {})
    assert st == 200 and d["dal"] == "ozellik/giris" and d["yeni_upstream"] is True
    assert git(uzak, "log", "-1", "--format=%s", "ozellik/giris").strip() == "Giris ekle"
    assert ".env" not in git(uzak, "ls-tree", "-r", "--name-only", "ozellik/giris")  # gizli dosya uzaga GITMEDI


def test_gecersiz_girdiler_400(api):
    _, _, istek, proje, _ = api
    (proje / "x.txt").write_text("x")
    assert istek("POST", "/api/github/commit", {"mesaj": ""})[0] == 400
    assert istek("POST", "/api/github/commit", {})[0] == 400
    assert istek("POST", "/api/github/dal", {"ad": "-x"})[0] == 400
    assert istek("POST", "/api/github/pr", {"baslik": "iki\nsatir"})[0] == 400
    assert istek("POST", "/api/github/issue-yorum", {"no": "1;x", "metin": "m"})[0] == 400
    assert istek("POST", "/api/github/klonla", {"depo": "ext::sh -c calc", "klasor": str(proje.parent)})[0] == 400
    assert "x.txt" in git(proje, "status", "--porcelain")  # hicbir sey commit edilmedi


def test_gorev_surerken_commit_dal_push_reddedilir_pr_ve_issue_serbest(ortam):
    proje, uzak = ortam
    e = Engelli()
    app, sv, istek = kur_sunucu(uret=lambda ad: e)
    try:
        app.klasor_sec(str(proje))
        (proje / "k.txt").write_text("k")
        plan = app.gorev_olustur("uzun gorev")
        app.onayla(plan["kosu"])
        assert e.basladi.wait(10)
        for yol, govde in (("/api/github/commit", {"mesaj": "m"}), ("/api/github/dal", {"ad": "x"}), ("/api/github/push", {})):
            st, d = istek("POST", yol, govde)
            assert st == 409 and "Gorev surerken" in d["hata"], yol
        assert subprocess.run(["git", "-C", str(proje), "rev-parse", "--verify", "-q", "HEAD"], capture_output=True).returncode != 0  # hicbir commit olusmadi
        assert "k.txt" in git(proje, "status", "--porcelain")
        assert istek("POST", "/api/github/pr", {"baslik": "p", "govde": ""})[0] == 200  # calisma agacini degistirmeyen islemler serbest
        assert istek("GET", "/api/github/issueler")[0] == 200
        assert istek("GET", "/api/github/proje")[0] == 200
    finally:
        e.serbest.set()
        sv.kapat()


def test_ayni_projede_es_zamanli_islem_409(api):
    app, _, istek, proje, _ = api
    kilit = app._github_kilitleri.setdefault(app.secili.kimlik, __import__("threading").Lock())
    assert kilit.acquire(blocking=False)
    try:
        st, d = istek("GET", "/api/github/proje")
        assert st == 409 and "baska bir GitHub islemi" in d["hata"]
    finally:
        kilit.release()
    assert istek("GET", "/api/github/proje")[0] == 200


def test_pr_ac_ve_issue_yorumu(api):
    _, _, istek, _, _ = api
    assert istek("POST", "/api/github/pr", {"baslik": "Ozellik", "govde": "Aciklama", "taslak": True})[1] == {"url": "https://github.com/sahte-kullanici/proje-bir/pull/12"}
    assert istek("POST", "/api/github/issue-yorum", {"no": 7, "metin": "Tamamlandi"})[0] == 200
    assert istek("GET", "/api/github/issueler")[1]["issueler"][0]["no"] == 7


# ---------- issue -> gorev ----------
def test_issue_gorev_plani_baslatir_ve_metni_guvenilmeyen_diye_isaretler(api):
    app, _, istek, _, _ = api
    st, d = istek("POST", "/api/github/issue-gorev", {"no": 7})
    assert st == 200 and d["issue"]["no"] == 7 and d["plan"]["tur"] == "plan"
    gorev = d["plan"]["gorev"]
    assert gorev.startswith("GitHub issue #7: Giris sayfasi hatali") and "GitHub'dan geldi" in gorev and "uymа" not in gorev
    assert "kisaltildi" in gorev and len(gorev) < 7000  # uzun issue govdesi kisaltildi
    assert app.kosu.durum == "plan"  # onay bekliyor: kendiliginden CALISMAZ
    st, _ = istek("POST", "/api/github/issue-gorev", {"no": 7})
    assert st == 409  # zaten bir gorev var


# ---------- klonla -> proje ----------
def test_klonla_projeyi_acar_ve_secer(api, tmp_path):
    app, _, istek, _, _ = api
    hedef_ust = tmp_path / "klonlar"
    hedef_ust.mkdir()
    st, d = istek("POST", "/api/github/klonla", {"depo": "sahte-kullanici/proje-bir", "klasor": str(hedef_ust)})
    assert st == 200 and Path(d["klasor"]) == hedef_ust / "proje-bir"
    assert app.klasor == (hedef_ust / "proje-bir").resolve() and d["durum"]["git"] is True and d["durum"]["golge"] is False
    assert projeler.proje_kimligi(hedef_ust / "proje-bir") in app.oturumlar
    st, d = istek("POST", "/api/github/klonla", {"depo": "sahte-kullanici/proje-bir", "klasor": str(hedef_ust)})
    assert st == 400 and "zaten var" in d["hata"]


def test_klonlanan_ama_acilamayan_depo_icin_anlasilir_hata(api, tmp_path, monkeypatch):
    from aktapokus_ajan import arayuz

    app, _, istek, _, _ = api
    ust = tmp_path / "k2"
    ust.mkdir()

    def reddet(*a, **k):
        raise arayuz.UygulamaHatasi("Bu klasor cok buyuk")

    monkeypatch.setattr(app, "proje_ac", reddet)
    st, d = istek("POST", "/api/github/klonla", {"depo": "sahte-kullanici/proje-iki", "klasor": str(ust)})
    assert st == 400 and "klonlandi" in d["hata"] and "cok buyuk" in d["hata"] and (ust / "proje-iki").is_dir()


def test_arayuz_github_sekmesi_ve_ayar_bolumunu_icerir_ve_onay_ister():
    html = (Path(__file__).resolve().parent.parent / "aktapokus_ajan" / "web" / "index.html").read_text(encoding="utf-8")
    for parca in ('data-p="p-github"', 'id="p-github"', '["github","GitHub"]', "function githubPaneliYukle", "function githubBolumu", "/api/github/commit", "/api/github/push", "/api/github/pr", "/api/github/klonla", "/api/github/issue-gorev"):
        assert parca in html, parca
    govde = html.split("const ghUrlGuvenli")[1].split("(async()=>{if(!T)")[0]
    assert govde.count("confirm(") >= 6  # commit, dal, push, PR, issue-gorev, issue-yorum, klonla: her yazan islemden once onay penceresi
    assert "innerHTML" not in govde  # GitHub'dan gelen metinler (issue basligi, PR) yalniz textContent ile yazilir
    assert "ghUrlGuvenli" in govde  # baglantilar yalniz https://github.com/ adreslerine


def test_e_yardimcisi_mantiksal_ozniteliklerde_false_yazmaz():
    html = (Path(__file__).resolve().parent.parent / "aktapokus_ajan" / "web" / "index.html").read_text(encoding="utf-8")
    assert "a[k]===false||a[k]==null" in html  # disabled:false => 'disabled=\"false\"' (dugme hep devre disi) gercek hatasi
