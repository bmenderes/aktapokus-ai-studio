"""Otomasyonun 'Yayinla' dugumu: gorev basariyla bitince klasoru hedef depoya kopyalar, kontrolden gecirir, push eder. GOZETIMSIZ oldugu icin yuksek/orta bulgu ya da
yapilamayan yapay zeka kontrolu yayini engeller ve hedef depo eski haline doner."""

import subprocess
import time
import types
from pathlib import Path

import pytest

from aktapokus_ai_studio import gonderme_kontrol as gk, otomasyon as oto, otomasyon_akis as akis_mod, projeler, yayin
from conftest import SahteCalistirici, sonuc
from test_github_api import git, kur_sunucu, ortam  # noqa: F401  (pytest fixture'lari)
from test_yayin import hedef_kur

TOKEN = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"
YAYIN = {"depo": "sahte/hedef", "kaynak": "site", "hedef_yol": "haberler"}


def akis(yayinla=True, bildirim=None, web=False):
    d = [{"id": "t1", "tur": "elle", "x": 0, "y": 0, "ayar": {}}, {"id": "g1", "tur": "gorev", "x": 200, "y": 0, "ayar": {"gorev": "Haber sayfasini uret"}}]
    o = [{"kaynak": "t1", "hedef": "g1"}]
    if yayinla:
        d.append({"id": "y1", "tur": "yayinla", "x": 400, "y": 60, "ayar": dict(yayinla if isinstance(yayinla, dict) else YAYIN)})
        o.append({"kaynak": "g1", "hedef": "y1"})
    if bildirim:
        d.append({"id": "b1", "tur": "bildirim", "x": 400, "y": 0, "ayar": {"metin": bildirim}})
        o.append({"kaynak": "g1", "hedef": "b1"})
    return {"dugumler": d, "oklar": o}


# ---------- akis kurallari ----------
def test_yayinla_dugumu_dogrulanir_ve_ayari_okunur():
    o = oto.kaydet({"ad": "haber", "proje": "a" * 10, "akis": akis()})
    assert akis_mod.yayin_ayari(o.akis) == {"depo": "sahte/hedef", "kaynak": "site", "hedef_yol": "haberler"} and akis_mod.yayin_ayari(None) is None and akis_mod.yayin_ayari(akis(False)) is None
    for kotu in ({**YAYIN, "depo": "kotu depo"}, {**YAYIN, "depo": ""}, {**YAYIN, "kaynak": "../disari"}, {**YAYIN, "kaynak": ""}, {**YAYIN, "kaynak": "C:/x"}, {**YAYIN, "hedef_yol": ".git"},
                 {**YAYIN, "hedef_yol": "../x"}, {"depo": "a/b"}):
        with pytest.raises(oto.OtomasyonHatasi):
            oto.kaydet({"ad": "kotu", "proje": "a" * 10, "akis": akis(kotu)})
    iki = akis()
    iki["dugumler"].append({"id": "y2", "tur": "yayinla", "x": 0, "y": 90, "ayar": dict(YAYIN)})
    with pytest.raises(oto.OtomasyonHatasi, match="en cok bir yayinla"):
        oto.kaydet({"ad": "iki", "proje": "a" * 10, "akis": iki})
    kopuk = akis()
    kopuk["oklar"] = [{"kaynak": "t1", "hedef": "g1"}]
    with pytest.raises(oto.OtomasyonHatasi, match="yayinla dugumune baglanmali"):
        oto.kaydet({"ad": "kopuk", "proje": "a" * 10, "akis": kopuk})
    yanlis = akis()
    yanlis["oklar"].append({"kaynak": "t1", "hedef": "y1"})  # tetikleyici dogrudan yayinla'ya baglanamaz
    with pytest.raises(oto.OtomasyonHatasi):
        oto.kaydet({"ad": "yanlis", "proje": "a" * 10, "akis": yanlis})


def test_engel_nedenleri_yuksek_ve_orta_engeller_dusuk_engellemez_ai_hatasi_engeller():
    yuksek = {"dosya": "a.js", "satir": 3, "tur": "GitHub belirteci", "siddet": "yuksek"}
    orta = {"dosya": "b.html", "satir": 1, "tur": "e-posta adresi", "siddet": "orta"}
    dusuk = {"dosya": "c.txt", "satir": 1, "tur": "genel IP adresi", "siddet": "dusuk"}
    assert gk.engel_nedenleri([dusuk]) == [] and len(gk.engel_nedenleri([yuksek, orta, dusuk])) == 2 and "a.js:3 GitHub belirteci (yuksek)" in gk.engel_nedenleri([yuksek])[0]
    assert gk.engel_nedenleri([], {"durum": "tamam", "sorunlar": []}) == []
    assert "yapay zeka kontrolu yapilamadi" in gk.engel_nedenleri([], {"durum": "hata", "neden": "json yok", "sorunlar": []})[0]
    assert len(gk.engel_nedenleri([], {"durum": "tamam", "sorunlar": [{"dosya": "x", "ornek": "ad soyad var", "siddet": "orta"}, {"dosya": "y", "ornek": "kucuk", "siddet": "dusuk"}]})) == 1


def test_geri_alma_yardimcilari(tmp_path):
    k = tmp_path / "depo"
    k.mkdir()
    for a in (["init", "-q"], ["config", "user.name", "T"], ["config", "user.email", "t@t.com"]):
        subprocess.run(["git", "-C", str(k), *a], check=True)
    (k / "a.txt").write_text("a")
    (k / "haberler").mkdir()
    (k / "haberler" / "eski.txt").write_text("eski")
    git(k, "add", "-A")
    git(k, "commit", "-qm", "ilk")
    ilk = git(k, "rev-parse", "HEAD").strip()
    (k / "haberler" / "eski.txt").write_text("degisti")  # izlenen dosya degisti
    (k / "haberler" / "yeni.txt").write_text("yeni")  # yeni dosya
    (k / "baska.txt").write_text("dokunulmaz")
    yayin.calisma_geri_al(k, "haberler")
    assert (k / "haberler" / "eski.txt").read_text() == "eski" and not (k / "haberler" / "yeni.txt").exists() and (k / "baska.txt").exists()
    (k / "haberler" / "yeni.txt").write_text("y")
    git(k, "add", "-A")
    git(k, "commit", "-qm", "bizim")
    yayin.commit_geri_al(k, ilk)
    assert git(k, "rev-parse", "HEAD").strip() == ilk
    git(k, "commit", "--allow-empty", "-qm", "baskasi-1")
    git(k, "commit", "--allow-empty", "-qm", "baskasi-2")
    with pytest.raises(yayin.YayinHatasi, match="bizim degil"):
        yayin.commit_geri_al(k, ilk)  # son commit bizim degil: dokunmaz
    assert git(k, "log", "--format=%s", "-1").strip() == "baskasi-2"


# ---------- calistirma ----------
def kur_otomasyon(tmp_path, ortam, kodcu=None, ai=None, bildirim=None):
    hedef, uzak = hedef_kur(ortam)
    istemler = []

    def varsayilan_ai(k, istem, n):
        istemler.append(istem)
        return sonuc('{"sorunlar":[],"commit_mesaji":"x"}')

    def kodcu_yazar(k, istem, n):
        (k / "site").mkdir(exist_ok=True)
        (k / "site" / "index.html").write_text("<h1>Bugunun haberleri</h1>", encoding="utf-8")
        return sonuc("sayfa uretildi")

    sahte = SahteCalistirici({"gizlilik denetcisi": ai or varsayilan_ai, "kodcu": kodcu or kodcu_yazar, "test": lambda k, i, n: sonuc("SONUC: BASARILI")})
    app, sv, istek = kur_sunucu(uret=lambda ad: sahte)
    kaynak = tmp_path / "haber-projesi"
    (kaynak / "site").mkdir(parents=True)
    app.klasor_sec(str(kaynak))
    app.proje_ac(str(hedef), sec=False)
    pid = projeler.proje_kimligi(kaynak)
    assert istek("POST", "/api/otomasyonlar", {"ad": "haber", "proje": pid, "akis": akis(bildirim=bildirim)})[0] == 200
    assert istek("POST", "/api/otomasyonlar/izin", {"ad": "haber", "onaysiz": True})[0] == 200  # gozetimsiz calissin: plan onayi ve 'koru' sorulmaz
    mesajlar = []
    app.telegram = types.SimpleNamespace(_canli=lambda: True, _bot=types.SimpleNamespace(_herkese=mesajlar.append))
    return app, sv, istek, kaynak, hedef, uzak, istemler, mesajlar


def calistir_ve_bekle(istek, sonuclar=("yayinlandi", "yayin-engellendi", "yayin-yok", "yayin-hata", "atlandi")):
    st, r = istek("POST", "/api/otomasyon-calistir", {"ad": "haber"})
    assert st == 200 and r["plan"]["otomatik"] is True
    son = time.monotonic() + 40
    while time.monotonic() < son:
        g = [x for x in oto.gecmis_oku(50) if x["otomasyon"] == "haber" and x["tetikleyen"] == "yayin" and x["sonuc"] in sonuclar]
        if g:
            return g[-1]
        time.sleep(0.1)
    raise AssertionError("yayin sonucu gecmise yazilmadi: " + str(oto.gecmis_oku(10)))


def test_gorev_basarili_bitince_temiz_icerik_yayinlanir_bildirime_sonuc_eklenir(tmp_path, ortam):
    app, sv, istek, kaynak, hedef, uzak, istemler, mesajlar = kur_otomasyon(tmp_path, ortam, bildirim="Bitti: {durum}")
    try:
        g = calistir_ve_bekle(istek)
        assert g["sonuc"] == "yayinlandi" and "sahte.github.io/hedef/haberler/" in g["neden"]
        dosyalar = git(uzak, "ls-tree", "-r", "--name-only", git(hedef, "branch", "--show-current").strip()).split()
        assert "haberler/index.html" in dosyalar and (hedef / "haberler" / "index.html").read_text(encoding="utf-8") == "<h1>Bugunun haberleri</h1>"
        assert any("Bugunun haberleri" in i for i in istemler)  # yapay zeka gonderilecek icerigi inceledi
        son = time.monotonic() + 10
        while time.monotonic() < son and not mesajlar:
            time.sleep(0.1)
        assert mesajlar and mesajlar[0].startswith("Bitti:") and "Yayin: yayinlandi -> https://sahte.github.io/hedef/haberler/" in mesajlar[0] and mesajlar[0].count("Yayin:") == 1
    finally:
        sv.kapat()


def test_metinde_yayin_degiskeni_varsa_satir_tekrar_eklenmez(tmp_path, ortam):
    app, sv, istek, kaynak, hedef, uzak, istemler, mesajlar = kur_otomasyon(tmp_path, ortam, bildirim="Sonuc -> {yayin}")
    try:
        calistir_ve_bekle(istek)
        son = time.monotonic() + 10
        while time.monotonic() < son and not mesajlar:
            time.sleep(0.1)
        assert mesajlar and mesajlar[0].startswith("Sonuc -> Yayin: yayinlandi") and mesajlar[0].count("Yayin:") == 1
    finally:
        sv.kapat()


def test_sir_varsa_yayin_engellenir_hedef_eski_haline_doner_sonra_duzelince_yayinlanir(tmp_path, ortam):
    def sirli(k, istem, n):
        (k / "site").mkdir(exist_ok=True)
        (k / "site" / "index.html").write_text("<h1>Haber</h1>", encoding="utf-8")
        (k / "site" / "ayar.js").write_text(f'const t = "{TOKEN}";', encoding="utf-8")
        return sonuc("uretildi")

    app, sv, istek, kaynak, hedef, uzak, istemler, mesajlar = kur_otomasyon(tmp_path, ortam, kodcu=sirli, bildirim="Bitti")
    try:
        onceki = git(hedef, "rev-parse", "HEAD").strip()
        g = calistir_ve_bekle(istek)
        assert g["sonuc"] == "yayin-engellendi" and "GitHub belirteci" in g["neden"] and TOKEN not in g["neden"]
        assert git(hedef, "rev-parse", "HEAD").strip() == onceki and not (hedef / "haberler").exists() and git(hedef, "status", "--porcelain", "--", "haberler").strip() == ""  # hedef eski hali
        assert git(uzak, "branch", "--list").strip() == ""  # hicbir sey uzaga gitmedi
        assert istemler == []  # yapay zekaya bile gitmedi (kural tabani zaten engelledi)
        son = time.monotonic() + 10
        while time.monotonic() < son and not mesajlar:
            time.sleep(0.1)
        assert mesajlar and "Yayin ENGELLENDI" in mesajlar[0] and TOKEN not in mesajlar[0]  # bildirim engeli haber verir, sir icermez
        (kaynak / "site" / "ayar.js").unlink()  # kaynak duzeltildi: bir sonraki calisma yayinlar (hedef kirli kalmadigi icin 'commit edilmemis degisiklik' hatasi YOK)
        (kaynak / "site" / "index.html").write_text("<h1>Haber</h1>", encoding="utf-8")
        mesajlar.clear()
        oto.gecmis_yolu().write_text("", encoding="utf-8")
        app.oturumlar[app.secili_kimlik].kosu = None

        def temiz(k, istem, n):  # ajan artik yalniz temiz sayfa yazar
            (k / "site" / "index.html").write_text("<h1>Haber 2</h1>", encoding="utf-8")
            return sonuc("tamam")

        app.calistirici_uret = lambda ad: SahteCalistirici({"gizlilik denetcisi": lambda k, i, n: sonuc('{"sorunlar":[]}'), "kodcu": temiz, "test": lambda k, i, n: sonuc("SONUC: BASARILI")})
        g2 = calistir_ve_bekle(istek)
        assert g2["sonuc"] == "yayinlandi"
    finally:
        sv.kapat()


def test_yapay_zeka_bulgusu_yayini_engeller_commit_geri_alinir(tmp_path, ortam):
    app, sv, istek, kaynak, hedef, uzak, istemler, mesajlar = kur_otomasyon(tmp_path, ortam, ai=lambda k, i, n: sonuc('{"sorunlar":[{"dosya":"site/index.html","aciklama":"musteri adi ve adresi var","siddet":"orta"}]}'))
    try:
        onceki = git(hedef, "rev-parse", "HEAD").strip()
        g = calistir_ve_bekle(istek)
        assert g["sonuc"] == "yayin-engellendi" and "yapay zeka" in g["neden"]
        assert git(hedef, "rev-parse", "HEAD").strip() == onceki and not (hedef / "haberler").exists()  # bizim commit'imiz geri alindi, kopya silindi
        assert git(uzak, "branch", "--list").strip() == ""  # hicbir sey uzaga gitmedi
    finally:
        sv.kapat()


def test_yapay_zeka_kontrolu_yapilamazsa_yayin_engellenir(tmp_path, ortam):
    app, sv, istek, kaynak, hedef, uzak, istemler, mesajlar = kur_otomasyon(tmp_path, ortam, ai=lambda k, i, n: sonuc("json yok"))
    try:
        onceki = git(hedef, "rev-parse", "HEAD").strip()
        g = calistir_ve_bekle(istek)
        assert g["sonuc"] == "yayin-engellendi" and "yapay zeka kontrolu yapilamadi" in g["neden"]
        assert git(hedef, "rev-parse", "HEAD").strip() == onceki and git(uzak, "branch", "--list").strip() == ""
    finally:
        sv.kapat()


def test_degisiklik_yoksa_yayin_yok(tmp_path, ortam):
    app, sv, istek, kaynak, hedef, uzak, istemler, mesajlar = kur_otomasyon(tmp_path, ortam)
    try:
        (hedef / "haberler").mkdir()  # hedefte ayni icerik zaten commit'li
        (hedef / "haberler" / "index.html").write_text("<h1>Bugunun haberleri</h1>", encoding="utf-8")
        git(hedef, "add", "-A")
        git(hedef, "commit", "-qm", "ayni icerik")
        g = calistir_ve_bekle(istek)
        assert g["sonuc"] == "yayin-yok" and "site zaten guncel" in g["neden"] and git(uzak, "branch", "--list").strip() == ""
    finally:
        sv.kapat()


def test_gorev_basarisiz_bitince_yayin_atlanir(tmp_path, ortam):
    app, sv, istek, kaynak, hedef, uzak, istemler, mesajlar = kur_otomasyon(tmp_path, ortam, kodcu=lambda k, i, n: sonuc("yazamadim", ok=False, hata="model hatasi"))
    try:
        g = calistir_ve_bekle(istek)
        assert g["sonuc"] == "atlandi" and "gorev basarili bitmedi" in g["neden"] and git(uzak, "branch", "--list").strip() == "" and not (hedef / "haberler").exists()
    finally:
        sv.kapat()


def test_arayuz_yayinla_dugumu_baglidir():
    html = (Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "web" / "index.html").read_text(encoding="utf-8")
    for parca in ('yayinla:"⇪"', 'n.tur==="yayinla"', "const yayinEkle=()=>", 'b.tur==="yayinla"', "yayinBtn", "otoYayinDepolar", "her çalışmada"):
        assert parca in html, parca


def test_yayinla_kaynagi_projede_yoksa_kayit_uyarir_ama_engellemez_dogruysa_uyari_yok(tmp_path, ortam):
    """GERCEK HATA: kaynak 'haberler' yazilmisti, sayfa projede 'bmenderes.github.io/haberler' altindaydi; yayin ilk calismada 'Kaynak klasor bulunamadi' ile dururdu."""
    app, sv, istek = kur_sunucu(uret=lambda ad: SahteCalistirici({"kodcu": lambda k, i, n: sonuc("x")}))
    proje = tmp_path / "haber-projesi"
    (proje / "bmenderes.github.io" / "haberler").mkdir(parents=True)
    (proje / "bmenderes.github.io" / "haberler" / "index.html").write_text("<h1>x</h1>", encoding="utf-8")
    (proje / "aktapokus.github.io" / "haberler").mkdir(parents=True)
    (proje / "aktapokus.github.io" / "haberler" / "index.html").write_text("<h1>y</h1>", encoding="utf-8")
    app.klasor_sec(str(proje))
    pid = projeler.proje_kimligi(proje)
    try:
        yanlis = {**YAYIN, "kaynak": "haberler"}
        st, d = istek("POST", "/api/otomasyonlar", {"ad": "haber", "proje": pid, "akis": akis(yayinla=yanlis)})
        assert st == 200 and d["ad"] == "haber"  # kayit engellenmedi
        assert len(d["uyarilar"]) == 1 and "haberler" in d["uyarilar"][0] and "bmenderes.github.io/haberler" in d["uyarilar"][0] and "aktapokus.github.io/haberler" in d["uyarilar"][0]
        dogru = {**YAYIN, "kaynak": "bmenderes.github.io/haberler"}
        st, d = istek("POST", "/api/otomasyonlar", {"ad": "haber", "proje": pid, "akis": akis(yayinla=dogru)})
        assert st == 200 and "uyarilar" not in d
        st, d = istek("POST", "/api/otomasyonlar", {"ad": "haber", "proje": pid, "akis": akis(yayinla=False)})
        assert st == 200 and "uyarilar" not in d  # yayinla dugumu yoksa uyari yok
        olusacak = {**YAYIN, "kaynak": "henuz-yok"}
        st, d = istek("POST", "/api/otomasyonlar", {"ad": "haber", "proje": pid, "akis": akis(yayinla=olusacak)})
        assert st == 200 and "projede bulunamadi" in d["uyarilar"][0]  # uyari, hata degil: gorev klasoru olusturabilir
    finally:
        sv.kapat()
