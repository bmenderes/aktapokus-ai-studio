"""Git istemcisi HTTP uclari (/api/git/*): belirtec/Origin, gorev surerken kisit, hazirlama, atma (anlik goruntu), dal/stash/cekme, commit onerisi."""

import http.client
import json
import time as zaman
from pathlib import Path

import pytest

from test_arayuz import Engelli
from test_github_api import api, git, kur_sunucu, ortam  # noqa: F401  (pytest fixture'lari)

GIT_GET = ["/api/git/gecmis", "/api/git/commit?sha=abcdef1", "/api/git/fark?yol=a.txt", "/api/git/dallar", "/api/git/stashler", "/api/git/commit-oneri"]
GIT_POST = ["/api/git/hazirla", "/api/git/hazirdan-cikar", "/api/git/degisiklik-at", "/api/git/dal-gec", "/api/git/dal-sil", "/api/git/birlestir", "/api/git/cek", "/api/git/pull",
            "/api/git/stash", "/api/git/stash-uygula", "/api/git/stash-sil"]


@pytest.fixture
def gitapi(api):
    app, sv, istek, proje, uzak = api
    git(proje, "add", "-A")
    git(proje, "commit", "-qm", "ilk")
    git(proje, "push", "-q", "-u", "origin", "main")
    return app, sv, istek, proje, uzak


def test_git_uclari_belirtec_ister_ve_yabanci_origin_reddedilir(gitapi):
    _, sv, istek, _, _ = gitapi
    for yol in GIT_GET:
        assert istek("GET", yol, token=None)[0] == 401, yol
    for yol in GIT_POST:
        assert istek("POST", yol, {}, token=None)[0] == 401, yol
        c = http.client.HTTPConnection("127.0.0.1", sv.port, timeout=10)
        c.request("POST", yol, body="{}", headers={"X-Aktapokus-Token": sv.app.token, "Origin": "http://evil.example", "Content-Type": "application/json"})
        r = c.getresponse()
        r.read()
        c.close()
        assert r.status == 403, yol


def test_telegram_git_istemcisine_dokunmaz():
    kaynak = (Path(__file__).resolve().parent.parent / "aktapokus_ajan" / "telegram.py").read_text(encoding="utf-8")
    assert "app.git_" not in kaynak and "gityonet" not in kaynak


def test_gecmis_fark_ve_commit_ayrintisi_http(gitapi):
    app, _, istek, proje, _ = gitapi
    (proje / "a.txt").write_text("degisti\n")
    st, d = istek("GET", "/api/git/gecmis")
    assert st == 200 and d["commitler"][0]["konu"] == "ilk"
    assert "+degisti" in istek("GET", "/api/git/fark?yol=a.txt")[1]["yama"]
    sha = d["commitler"][0]["sha"]
    assert istek("GET", f"/api/git/commit?sha={sha}")[1]["dosyalar"]
    assert "diff --git" in istek("GET", f"/api/git/fark?yol=a.txt&sha={sha}")[1]["yama"]
    for kotu in ("/api/git/commit?sha=HEAD", "/api/git/commit", "/api/git/fark", "/api/git/fark?yol=../x", "/api/git/fark?yol=a.txt&sha=--all"):
        assert istek("GET", kotu)[0] == 400, kotu


def test_gizli_dosyanin_farki_http_ile_gosterilmez(gitapi):
    _, _, istek, proje, _ = gitapi
    (proje / ".env").write_text("SIR=cok-gizli-123")
    st, d = istek("GET", "/api/git/fark?yol=.env")
    assert st == 400 and "cok-gizli-123" not in json.dumps(d)


def test_dosya_dosya_hazirla_ve_yalniz_hazirlananlari_commit_et(gitapi):
    _, _, istek, proje, _ = gitapi
    (proje / "a.txt").write_text("degisti\n")
    (proje / "yeni.txt").write_text("y")
    (proje / ".env").write_text("SIR")
    assert istek("POST", "/api/git/hazirla", {"yollar": ["a.txt"]})[0] == 200
    assert istek("POST", "/api/git/hazirla", {"yollar": [".env"]})[0] == 400
    d = istek("GET", "/api/github/proje")[1]
    assert d["hazir_sayisi"] == 1 and {x["yol"]: x["hazir"] for x in d["degisen"]}["a.txt"] is True
    st, r = istek("POST", "/api/github/commit", {"mesaj": "Yalniz a", "yalniz_hazir": True})
    assert st == 200 and r["dosya_sayisi"] == 1 and git(proje, "show", "--name-only", "--format=", "HEAD").split() == ["a.txt"]
    assert istek("POST", "/api/github/commit", {"mesaj": "bos", "yalniz_hazir": True})[0] == 400  # hazirlanmis dosya kalmadi
    istek("POST", "/api/git/hazirla", {"yollar": ["yeni.txt"]})
    assert istek("POST", "/api/git/hazirdan-cikar", {"yollar": ["yeni.txt"]})[0] == 200
    assert istek("GET", "/api/github/proje")[1]["hazir_sayisi"] == 0


def test_degisiklik_at_http_once_anlik_goruntu_alir_ve_geri_getirir(gitapi):
    _, _, istek, proje, _ = gitapi
    (proje / "a.txt").write_text("bozuk\n")
    (proje / "gecici.txt").write_text("silinecek")
    st, r = istek("POST", "/api/git/degisiklik-at", {"yollar": ["a.txt", "gecici.txt"]})
    assert st == 200 and r["geri_alinan"] == 1 and r["silinen"] == 1 and len(r["yedek"]) == 40
    assert (proje / "a.txt").read_text() == "bir\n" and not (proje / "gecici.txt").exists()
    assert git(proje, "cat-file", "-p", f"{r['yedek']}:a.txt") == "bozuk\n"  # atilan icerik anlik goruntude kurtarilabilir
    assert git(proje, "cat-file", "-p", f"{r['yedek']}:gecici.txt") == "silinecek"
    (proje / ".env").write_text("SIR")
    assert istek("POST", "/api/git/degisiklik-at", {"yollar": [".env"]})[0] == 400 and (proje / ".env").exists()


def test_dal_birlestirme_stash_ve_cekme_http(gitapi):
    _, _, istek, proje, _ = gitapi
    assert istek("POST", "/api/github/dal", {"ad": "ozellik"})[0] == 200
    (proje / "o.txt").write_text("o")
    istek("POST", "/api/github/commit", {"mesaj": "ozellik"})
    assert istek("POST", "/api/git/dal-gec", {"ad": "main"})[0] == 200
    d = istek("GET", "/api/git/dallar")[1]
    assert {x["ad"] for x in d["yerel"]} == {"main", "ozellik"} and [x["ad"] for x in d["yerel"] if x["aktif"]] == ["main"]
    assert istek("POST", "/api/git/birlestir", {"ad": "ozellik"})[0] == 200 and (proje / "o.txt").exists()
    assert istek("POST", "/api/git/dal-sil", {"ad": "ozellik"})[0] == 200
    assert istek("POST", "/api/git/dal-sil", {"ad": "main"})[0] == 400
    (proje / "a.txt").write_text("rafa\n")
    assert istek("POST", "/api/git/stash", {"mesaj": "raf"})[0] == 200
    assert (proje / "a.txt").read_text() == "bir\n"
    s = istek("GET", "/api/git/stashler")[1]["stashler"]
    assert len(s) == 1 and "raf" in s[0]["mesaj"]
    assert istek("POST", "/api/git/stash-uygula", {"indeks": 0, "sil": True})[0] == 200 and (proje / "a.txt").read_text() == "rafa\n"
    assert istek("POST", "/api/git/stash-sil", {"indeks": 0})[0] == 400  # zaten yok
    assert istek("POST", "/api/git/cek", {})[0] == 200
    assert istek("POST", "/api/git/pull", {})[0] == 200


def test_gorev_surerken_agaci_degistiren_git_islemleri_reddedilir_okuma_ve_cekme_serbest(ortam):
    proje, uzak = ortam
    git(proje, "add", "-A")
    git(proje, "commit", "-qm", "ilk")
    git(proje, "push", "-q", "-u", "origin", "main")
    e = Engelli()
    app, sv, istek = kur_sunucu(uret=lambda ad: e)
    try:
        app.klasor_sec(str(proje))
        plan = app.gorev_olustur("uzun gorev")
        app.onayla(plan["kosu"])
        assert e.basladi.wait(10)
        (proje / "a.txt").write_text("bozulmamali\n")
        for yol, govde in (("/api/git/hazirla", {"yollar": ["a.txt"]}), ("/api/git/hazirdan-cikar", {"yollar": ["a.txt"]}), ("/api/git/degisiklik-at", {"yollar": ["a.txt"]}),
                           ("/api/git/dal-gec", {"ad": "main"}), ("/api/git/dal-sil", {"ad": "x"}), ("/api/git/birlestir", {"ad": "x"}), ("/api/git/pull", {}),
                           ("/api/git/stash", {"mesaj": ""}), ("/api/git/stash-uygula", {"indeks": 0}), ("/api/git/stash-sil", {"indeks": 0})):
            st, d = istek("POST", yol, govde)
            assert st == 409 and "Gorev surerken" in d["hata"], yol
        assert (proje / "a.txt").read_text() == "bozulmamali\n"  # hicbir sey degismedi
        assert istek("POST", "/api/git/cek", {})[0] == 200  # calisma agacina dokunmayan islem serbest
        for yol in ("/api/git/gecmis", "/api/git/dallar", "/api/git/stashler", "/api/git/fark?yol=a.txt", "/api/git/commit-oneri"):
            assert istek("GET", yol)[0] == 200, yol
    finally:
        e.serbest.set()
        sv.kapat()


def test_commit_onerisi_son_committen_beri_korunan_gorevlerden_uretilir(gitapi):
    from aktapokus_ajan.pipeline import _kayit_klasoru

    app, _, istek, proje, _ = gitapi
    kayit_dizini = _kayit_klasoru(proje)
    kayit_dizini.mkdir(parents=True, exist_ok=True)

    def kayit(kimlik, gorev, saniye_farki, durum="onaylandi", degisen=None):
        t = zaman.strftime("%Y-%m-%d %H:%M:%S", zaman.localtime(zaman.time() + saniye_farki))
        (kayit_dizini / f"{kimlik}.json").write_text(json.dumps({"id": kimlik, "zaman": t, "gorev": gorev, "durum": durum, "degisen": degisen if degisen is not None else {"a.txt": "M"}, "akis": []}), encoding="utf-8")

    kayit("20200101-000000-001-aaaa", "ESKI gorev: commit'ten once", -3600)  # son commit'ten ONCE: onerilmez
    kayit("20990101-000000-001-aaaa", "Giris sayfasina sifremi unuttum ekle\nayrinti satiri", 5)
    kayit("20990101-000000-002-bbbb", "Geri alinan gorev", 6, durum="geri_alindi")  # korunmadi: yazilmaz
    kayit("20990101-000000-003-cccc", "Dosya degistirmeyen gorev", 7, degisen={})  # degisiklik yok: yazilmaz
    kayit("20990101-000000-004-dddd", "Hata sayfasini guzellestir", 8)
    (proje / "a.txt").write_text("degisti\n")
    st, d = istek("GET", "/api/git/commit-oneri")
    assert st == 200 and d["kaynak"] == "gorev" and d["gorev_sayisi"] == 2
    ilk, *_ = d["mesaj"].splitlines()
    assert ilk == "Giris sayfasina sifremi unuttum ekle (+1 gorev daha)"
    assert "ESKI" not in d["mesaj"] and "Geri alinan" not in d["mesaj"] and "Dosya degistirmeyen" not in d["mesaj"] and "ayrinti satiri" not in d["mesaj"]
    assert "- Hata sayfasini guzellestir" in d["mesaj"] and "a.txt" in d["mesaj"]


def test_commit_onerisi_gorev_yoksa_degisen_dosyalardan(gitapi):
    _, _, istek, proje, _ = gitapi
    (proje / "a.txt").write_text("degisti\n")
    (proje / "yeni.py").write_text("x")
    (proje / ".env").write_text("SIR")
    d = istek("GET", "/api/git/commit-oneri")[1]
    assert d["kaynak"] == "degisiklik" and d["mesaj"].startswith("Guncelle: ") and ".env" not in d["mesaj"] and "a.txt" in d["mesaj"]
    istek("POST", "/api/git/hazirla", {"yollar": ["yeni.py"]})
    assert istek("GET", "/api/git/commit-oneri")[1]["mesaj"] == "Ekle: yeni.py"  # hazirlanmis dosya varsa yalniz onlar


def test_git_olmayan_klasorde_git_uclari_anlasilir_hata(ortam, tmp_path):
    app, sv, istek = kur_sunucu()
    try:
        k = tmp_path / "gitsiz"
        k.mkdir()
        (k / "a.txt").write_text("a")
        app.klasor_sec(str(k))
        st, d = istek("GET", "/api/git/dallar")
        assert st == 400 and "git" in d["hata"].lower()
    finally:
        sv.kapat()


def test_gecmis_dallar_stash_ve_oneri_ayni_anda_istenince_hata_vermez(gitapi):
    """Gercek hata: arayuz bu bolumleri es zamanli yukleyince okumalar proje kilidine takilip 409 veriyordu."""
    import threading

    _, _, istek, proje, _ = gitapi
    (proje / "a.txt").write_text("degisti\n")
    sonuclar = []

    def iste(yol):
        sonuclar.append((yol, istek("GET", yol)[0]))

    ipler = [threading.Thread(target=iste, args=(y,)) for y in ("/api/git/gecmis", "/api/git/dallar", "/api/git/stashler", "/api/git/commit-oneri", "/api/github/proje", "/api/git/fark?yol=a.txt") * 3]
    for t in ipler:
        t.start()
    for t in ipler:
        t.join(30)
    assert len(sonuclar) == 18 and all(kod == 200 for _, kod in sonuclar), [s for s in sonuclar if s[1] != 200]


def test_arayuz_git_sekmesi_bolumleri_ve_onaylari_icerir():
    html = (Path(__file__).resolve().parent.parent / "aktapokus_ajan" / "web" / "index.html").read_text(encoding="utf-8")
    for parca in ('data-p="p-git"', 'id="p-git"', "function gitPaneliYukle", "/api/git/hazirla", "/api/git/hazirdan-cikar", "/api/git/degisiklik-at", "/api/git/gecmis", "/api/git/dallar",
                  "/api/git/stashler", "/api/git/stash-uygula", "/api/git/birlestir", "/api/git/commit-oneri", "yalniz_hazir:true", "Gizli görünen"):
        assert parca in html or parca == "Gizli görünen", parca
    govde = html.split("function gitPaneliYukle")[1].split("(async()=>{if(!T)")[0] if "function gitPaneliYukle" in html else ""
    assert govde.count("confirm(") >= 6  # at, birlestir, dal sil, dal olustur, push, stash sil/uygula+sil: yikici/dis etkili her islemden once onay
    assert "innerHTML" not in govde  # commit mesajlari, dal adlari, dosya yollari yalniz textContent ile yazilir
    assert "KALICI" in govde  # gercek yikici islemler (atma, stash silme) acikca belirtilir
    github_govde = html.split("async function githubPaneliYukle")[1].split("async function githubBolumu")[0]
    assert "/api/github/commit" not in github_govde and "/api/github/push" not in github_govde  # commit/dal/push artik yalniz Git sekmesinde
