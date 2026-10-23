import http.client
import json
import subprocess
import threading
import time
from pathlib import Path

import pytest

from aktapokus_ajan import guard
from aktapokus_ajan.arayuz import ArayuzSunucusu, OlayAkisi, Uygulama, gizli_mi, guvenli_goreli
from aktapokus_ajan.runners import Calistirici, CalistirmaSonucu
from conftest import SahteCalistirici, sonuc

BASARILI = lambda k, i, n: sonuc("tamam\nSONUC: BASARILI")  # noqa: E731


def yaz(k, i, n):
    (k / "yeni.txt").write_text("yeni\n", encoding="utf-8")
    return sonuc("yazildi")


class Engelli(Calistirici):
    """Bir olay serbest birakilana (ya da durdur() cagrilana) kadar bekler."""

    ad = "engelli"

    def __init__(self):
        self.serbest = threading.Event()
        self.basladi = threading.Event()
        self.durduruldu = False

    def calistir(self, istem, klasor, **kw):
        self.basladi.set()
        self.serbest.wait(10)
        return CalistirmaSonucu(ok=not self.durduruldu, metin="x", hata="durduruldu" if self.durduruldu else None)

    def durdur(self):
        self.durduruldu = True
        self.serbest.set()
        return True


class Istemci:
    def __init__(self, sunucu, token=None):
        self.s, self.token = sunucu, token if token is not None else sunucu.app.token

    def __call__(self, yontem, yol, veri=None, token="__varsayilan__", host=None):
        c = http.client.HTTPConnection("127.0.0.1", self.s.port, timeout=10)
        basliklar = {"Content-Type": "application/json"}
        t = self.token if token == "__varsayilan__" else token
        if t is not None:
            basliklar["X-Aktapokus-Token"] = t
        if host:
            basliklar["Host"] = host
        c.request(yontem, yol, body=json.dumps(veri) if veri is not None else None, headers=basliklar)
        r = c.getresponse()
        ham = r.read()
        c.close()
        try:
            return r.status, json.loads(ham)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return r.status, ham


def bekle(kosul, sn=10):
    son = time.monotonic() + sn
    while time.monotonic() < son:
        if kosul():
            return True
        time.sleep(0.05)
    return False


@pytest.fixture
def kur(proje):
    acik = []

    def f(senaryo=None, uret=None):
        sahte = SahteCalistirici(senaryo or {"kodcu": yaz, "test": BASARILI})
        app = Uygulama(calistirici_uret=uret or (lambda ad: sahte))
        sv = ArayuzSunucusu(app)
        sv.baslat()
        acik.append(sv)
        return app, sv, Istemci(sv), sahte

    f.proje = proje
    yield f
    for sv in acik:
        sv.kapat()


def klasor_sec(api, proje):
    st, d = api("POST", "/api/klasor", {"yol": str(proje)})
    assert st == 200, d
    return d


def tam_kosu(app, api, proje, karar=True, gorev="yeni.txt ekle"):
    klasor_sec(api, proje)
    st, plan = api("POST", "/api/gorev", {"gorev": gorev})
    assert st == 200
    assert api("POST", f"/api/gorev/{plan['kosu']}/onayla", {})[0] == 200
    assert bekle(lambda: app.kosu.durum == "karar-bekliyor")
    assert api("POST", f"/api/gorev/{plan['kosu']}/karar", {"korunsun": karar})[0] == 200
    assert bekle(lambda: app.kosu.durum == "bitti")
    return plan


# ---------- kimlik / host ----------
def test_token_ve_host_zorunlu(kur):
    app, sv, api, _ = kur()
    assert api("GET", "/api/durum", token=None)[0] == 401
    assert api("GET", "/api/durum", token="yanlis")[0] == 401
    assert api("GET", "/api/durum")[0] == 200
    assert api("GET", "/api/durum", host="evil.example.com")[0] == 403
    assert api("GET", "/api/durum", host=f"localhost:{sv.port + 1}")[0] == 403  # DNS rebinding: port da eslesmeli
    assert api("GET", "/api/durum", host=f"localhost:{sv.port}")[0] == 200
    st, html = api("GET", "/", token=None)
    assert st == 200 and b"<title>Aktapokus</title>" in html
    assert api("GET", "/", token=None, host="evil.example.com")[0] == 403
    assert api("GET", "/baska", token=None)[0] == 404


def test_arayuz_dis_kaynak_yuklemez():
    html = (Path(__file__).resolve().parent.parent / "aktapokus_ajan" / "web" / "index.html").read_text(encoding="utf-8")
    assert "cdn" not in html.lower() and "googleapis" not in html and 'src="http' not in html and "https://" not in html.replace("rel=\"noopener", "")


def test_olay_akisi_kimlik_ve_sinir():
    b = OlayAkisi(azami=3)
    for i in range(5):
        o = b.yayinla({"tur": "x", "i": i})
    assert o["id"] == 5 and [x["id"] for x in b.gecmis] == [3, 4, 5]
    q, tekrar = b.abone_ol(son_id=4)
    assert [x["id"] for x in tekrar] == [5]
    b.yayinla({"tur": "y"})
    assert q.get(timeout=1)["tur"] == "y"
    b.ayril(q)


# ---------- klasor ----------
def test_klasor_secimi(kur, tmp_path):
    app, sv, api, _ = kur()
    st, d = api("GET", "/api/durum")
    assert d["klasor"] is None and d["kosu"] is None
    assert api("POST", "/api/gorev", {"gorev": "x"})[0] == 409  # klasor yok
    assert api("POST", "/api/klasor", {"yol": str(Path.home())})[0] == 400
    gitsiz = tmp_path / "gitsiz"
    gitsiz.mkdir()
    st, d = api("POST", "/api/klasor", {"yol": str(gitsiz)})
    assert st == 428 and "git_gerekli" in d["hata"]
    assert not (gitsiz / ".git").exists()  # onay olmadan git init yapilmadi
    st, d = api("POST", "/api/klasor", {"yol": str(gitsiz), "git_baslat": True})
    assert st == 200 and d["git"] is True and d["koruyucu_eksik"] == []
    assert d["ayar"]["akis"] == ["kodcu", "test"] and d["ayar"]["roller"]["test"]["dogrulama"] is True


def test_klasorleri_listele(kur, tmp_path):
    app, sv, api, _ = kur()
    (tmp_path / "a").mkdir()
    (tmp_path / ".gizli").mkdir()
    (tmp_path / "dosya.txt").write_text("x")
    st, d = api("GET", "/api/klasorler?yol=" + str(tmp_path).replace("\\", "/"))
    assert st == 200 and "a" in d["klasorler"] and ".gizli" not in d["klasorler"] and "dosya.txt" not in d["klasorler"]
    assert api("GET", "/api/klasorler?yol=" + str(tmp_path / "yok").replace("\\", "/"))[0] in (403, 404)


# ---------- gorev akisi ----------
def test_tam_akis_korunsun(kur):
    app, sv, api, sahte = kur()
    plan = tam_kosu(app, api, kur.proje, karar=True)
    assert plan["adimlar"][0]["rol"] == "kodcu" and plan["butce"] == 200000
    assert (kur.proje / "yeni.txt").exists()
    turler = [o["tur"] for o in app.bus.gecmis]
    assert turler.index("plan") < turler.index("adim-basladi") < turler.index("fark") < turler.index("karar-bekleniyor") < turler.index("bitti")
    assert "dogrulama" in turler
    bitti = [o for o in app.bus.gecmis if o["tur"] == "bitti"][-1]
    assert bitti["durum"] == "onaylandi" and bitti["korundu"] is True and bitti["token_toplam"] == 30
    fark = [o for o in app.bus.gecmis if o["tur"] == "fark"][-1]
    assert fark["degisen"] == {"yeni.txt": "A"}
    st, d = api("GET", "/api/durum")
    assert d["kosu"]["durum"] == "bitti" and d["son_kayit"]["durum"] == "onaylandi"


def test_tam_akis_geri_al(kur):
    app, sv, api, _ = kur()
    tam_kosu(app, api, kur.proje, karar=False)
    assert not (kur.proje / "yeni.txt").exists()
    assert [o for o in app.bus.gecmis if o["tur"] == "bitti"][-1]["durum"] == "geri_alindi"


def test_plan_reddi_ve_tekrar_gorev(kur):
    app, sv, api, sahte = kur()
    klasor_sec(api, kur.proje)
    st, plan = api("POST", "/api/gorev", {"gorev": "g"})
    assert api("POST", "/api/gorev", {"gorev": "ikinci"})[0] == 409  # onay bekleyen gorev varken yenisi olmaz
    assert api("POST", f"/api/gorev/{plan['kosu']}/karar", {"korunsun": True})[0] == 409  # henuz karar asamasinda degil
    assert api("POST", "/api/gorev/abcd1234/onayla", {})[0] == 404
    assert api("POST", f"/api/gorev/{plan['kosu']}/reddet", {})[0] == 200
    assert sahte.cagrilar == []  # hicbir sey calismadi
    assert api("POST", f"/api/gorev/{plan['kosu']}/onayla", {})[0] == 409  # reddedilmis plan onaylanamaz
    assert api("POST", "/api/gorev", {"gorev": "yeni gorev"})[0] == 200  # sonra yenisi acilabilir
    assert api("POST", "/api/gorev", {"gorev": "   "})[0] in (400, 409)


def test_calisirken_ayar_degisemez_ama_ayni_klasoru_yeniden_secmek_gorevi_sifirlamaz(kur):
    e = Engelli()
    app, sv, api, _ = kur(uret=lambda ad: e)
    klasor_sec(api, kur.proje)
    st, plan = api("POST", "/api/gorev", {"gorev": "g"})
    api("POST", f"/api/gorev/{plan['kosu']}/onayla", {})
    assert e.basladi.wait(5)
    assert api("POST", "/api/klasor", {"yol": str(kur.proje)})[0] == 200  # P2: klasor secimi artik engellenmez ama kosan oturum korunur
    assert app.kosu is not None and app.kosu.kimlik == plan["kosu"] and app.kosu.durum == "calisiyor"
    st, ayar = api("GET", "/api/ayar")
    assert api("PUT", "/api/ayar", ayar)[0] == 409
    e.serbest.set()
    bekle(lambda: app.kosu.durum in ("bitti", "karar-bekliyor"))
    if app.kosu.durum == "karar-bekliyor":
        api("POST", f"/api/gorev/{plan['kosu']}/karar", {"korunsun": False})
        bekle(lambda: app.kosu.durum == "bitti")


def test_durdur_calisan_gorevi_iptal_eder(kur):
    e = Engelli()
    app, sv, api, _ = kur(uret=lambda ad: e)
    klasor_sec(api, kur.proje)
    st, plan = api("POST", "/api/gorev", {"gorev": "g"})
    api("POST", f"/api/gorev/{plan['kosu']}/onayla", {})
    assert e.basladi.wait(5)
    st, d = api("POST", f"/api/gorev/{plan['kosu']}/durdur", {})
    assert st == 200 and d["durduruldu"] is True
    assert bekle(lambda: app.kosu.durum == "bitti")
    assert [o for o in app.bus.gecmis if o["tur"] == "bitti"][-1]["durum"] == "iptal"
    assert api("POST", f"/api/gorev/{plan['kosu']}/durdur", {})[0] == 409  # zaten bitti


def test_hata_sunucuyu_dusurmez(kur):
    def uret(ad):
        raise RuntimeError("cli yok")

    app, sv, api, _ = kur(uret=uret)
    klasor_sec(api, kur.proje)
    st, plan = api("POST", "/api/gorev", {"gorev": "g"})
    api("POST", f"/api/gorev/{plan['kosu']}/onayla", {})
    assert bekle(lambda: app.kosu.durum == "bitti")
    bitti = [o for o in app.bus.gecmis if o["tur"] == "bitti"][-1]
    assert bitti["durum"] == "basarisiz" and "cli yok" in bitti["mesaj"]
    assert api("GET", "/api/durum")[0] == 200


def test_sse_gecmisi_yeniden_oynatir_ve_canli_akar(kur):
    app, sv, api, _ = kur()
    tam_kosu(app, api, kur.proje)
    gelen = []
    c = http.client.HTTPConnection("127.0.0.1", sv.port, timeout=10)
    c.request("GET", "/api/olaylar?son=0", headers={"X-Aktapokus-Token": app.token})
    r = c.getresponse()
    assert r.status == 200 and r.getheader("Content-Type").startswith("text/event-stream")

    def oku():
        try:
            for satir in r:
                if satir.startswith(b"data:"):
                    gelen.append(json.loads(satir[5:]))
        except Exception:
            pass

    threading.Thread(target=oku, daemon=True).start()
    assert bekle(lambda: any(o["tur"] == "bitti" for o in gelen))  # gecmis geldi
    n = len(gelen)
    app.bus.yayinla({"tur": "gunluk", "mesaj": "canli olay"})
    assert bekle(lambda: len(gelen) > n and gelen[-1]["mesaj"] == "canli olay")
    c.close()
    assert api("GET", "/api/olaylar", token=None)[0] == 401


# ---------- dosyalar ----------
def test_dosya_listesi_ve_okuma_guvenligi(kur):
    app, sv, api, _ = kur()
    p = kur.proje
    (p / ".env").write_text("SECRET=abc123", encoding="utf-8")
    (p / "README.md").write_text("# Baslik\n\nmetin", encoding="utf-8")
    (p / "docs").mkdir()
    (p / "docs" / "kilavuz.md").write_text("# K", encoding="utf-8")
    (p / "node_modules").mkdir()
    (p / "node_modules" / "x.js").write_text("1")
    (p / "anahtar.pem").write_text("SAHTE-ozel-anahtar-icerigi")
    (p / "ikili.bin").write_bytes(b"\x00\x01\x02")
    klasor_sec(api, p)
    st, d = api("GET", "/api/dosyalar")
    yollar = [x["yol"] for x in d["dosyalar"]]
    assert "README.md" in yollar and "docs/kilavuz.md" in yollar and "a.txt" in yollar
    for gizli in (".env", "anahtar.pem", "node_modules/x.js", ".opencode/opencode.json", ".git/HEAD"):
        assert gizli not in yollar, gizli
    assert d["belgeler"][0] == "README.md" and "docs/kilavuz.md" in d["belgeler"]
    assert api("GET", "/api/dosya?yol=README.md")[1]["icerik"].startswith("# Baslik")
    assert api("GET", "/api/dosya?yol=ikili.bin")[1]["ikili"] is True
    for kotu in (".env", "anahtar.pem", ".git/config", ".opencode/opencode.json", "../x", "docs/../../x", "C:/Windows/win.ini", "/etc/passwd", "", "docs/..", ".aktapokus/roller.json"):
        st, y = api("GET", "/api/dosya?yol=" + kotu.replace("\\", "/"))
        assert st in (403, 404), (kotu, st)
        assert "abc123" not in json.dumps(y)
    assert api("GET", "/api/dosya?yol=yok.txt")[0] == 404


def _baglanti_olustur(link: Path, hedef: Path) -> bool:
    """Klasor baglantisi: Windows'ta junction (yonetici gerekmez), digerlerinde sembolik baglanti."""
    try:
        if __import__("os").name == "nt":
            r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(hedef)], capture_output=True)
            return r.returncode == 0
        link.symlink_to(hedef, target_is_directory=True)
        return True
    except OSError:
        return False


def test_proje_disina_cikan_baglanti_okunmaz_ve_listelenmez(kur, tmp_path):
    app, sv, api, _ = kur()
    disari = tmp_path / "disari"
    disari.mkdir()
    (disari / "gizli.txt").write_text("DISARIDAKI-SIR", encoding="utf-8")
    if not _baglanti_olustur(kur.proje / "kopru", disari):
        pytest.skip("klasor baglantisi olusturulamadi")
    klasor_sec(api, kur.proje)
    yollar = [x["yol"] for x in api("GET", "/api/dosyalar")[1]["dosyalar"]]
    assert not any(y.startswith("kopru/") for y in yollar)  # baglanti icine inilmedi
    st, y = api("GET", "/api/dosya?yol=kopru/gizli.txt")
    assert st == 403 and "DISARIDAKI-SIR" not in json.dumps(y)
    st, govde, _ = onizleme(sv, "/kopru/gizli.txt")
    assert st in (403, 404) and b"DISARIDAKI-SIR" not in govde


def test_buyuk_dosya_kisaltilir(kur):
    app, sv, api, _ = kur()
    (kur.proje / "buyuk.txt").write_text("a" * 400_000, encoding="utf-8")
    klasor_sec(api, kur.proje)
    d = api("GET", "/api/dosya?yol=buyuk.txt")[1]
    assert d["kesildi"] is True and len(d["icerik"]) == 300_000


def test_imza_degisimi(kur):
    app, sv, api, _ = kur()
    klasor_sec(api, kur.proje)
    a = api("GET", "/api/imza")[1]["imza"]
    assert api("GET", "/api/imza")[1]["imza"] == a
    time.sleep(0.02)
    (kur.proje / "a.txt").write_text("degisti ve uzadi\n", encoding="utf-8")
    assert api("GET", "/api/imza")[1]["imza"] != a


def test_guvenli_goreli_birim(tmp_path):
    for kotu in ("", "..", "a/../../b", ".env", "x/.git/y", "C:/x", "k.PEM", "id_rsa", "id_rsa.pub"):
        with pytest.raises(ValueError):
            guvenli_goreli(tmp_path, kotu)
    assert guvenli_goreli(tmp_path, "a\\b.txt") == (tmp_path / "a" / "b.txt").resolve()
    assert gizli_mi([".git"]) and gizli_mi(["x", ".env.local"]) and not gizli_mi(["site", "index.html"])


# ---------- fark ----------
def test_fark_yamasi_ve_dogrulama(kur):
    app, sv, api, _ = kur()
    tam_kosu(app, api, kur.proje, karar=True)
    f = [o for o in app.bus.gecmis if o["tur"] == "fark"][-1]
    st, d = api("GET", f"/api/fark?once={f['once']}&sonra={f['sonra']}&dosya=yeni.txt")
    assert st == 200 and "+yeni" in d["yama"]
    assert api("GET", f"/api/fark?once={f['once']}&sonra={f['sonra']}")[0] == 200
    for kotu_once in ("HEAD", "--output=x", "zz", "0" * 40, f['once'] + ";calc", ""):
        assert api("GET", f"/api/fark?once={kotu_once}&sonra={f['sonra']}")[0] == 400, kotu_once
    assert api("GET", f"/api/fark?once={f['once']}&sonra={f['sonra']}&dosya=.env")[0] == 403
    assert api("GET", f"/api/fark?once={f['once']}&sonra={f['sonra']}&dosya=../x")[0] == 403


# ---------- ayar ----------
def test_ayar_oku_yaz_dogrula(kur):
    app, sv, api, _ = kur()
    klasor_sec(api, kur.proje)
    st, ayar = api("GET", "/api/ayar")
    assert st == 200
    ayar["roller"]["kodcu"]["model"] = "baska/model"
    assert api("PUT", "/api/ayar", ayar)[0] == 200
    assert api("GET", "/api/durum")[1]["ayar"]["roller"]["kodcu"]["model"] == "baska/model"
    ayar["roller"]["kodcu"]["calistirici"] = "bilinmeyen"
    st, d = api("PUT", "/api/ayar", ayar)
    assert st == 400 and "calistirici" in d["hata"]
    assert api("GET", "/api/ayar")[1]["roller"]["kodcu"]["calistirici"] == "opencode-sunucu"  # bozuk ayar yazilmadi (varsayilan)
    assert api("PUT", "/api/ayar", {"roller": {}})[0] == 400


# ---------- CLI'lar (tanimla eklenenler) ----------
SAHTE_CLI = str(Path(__file__).with_name("sahte_cli.py"))


def cli_tanimi(**ek):
    import sys

    d = {"ad": "sahtecli", "komut": [sys.executable, SAHTE_CLI, "--stdin"], "istem": "stdin", "modeller": ["ucuz", "pahali"], "model_bayragi": "--model"}
    d.update(ek)
    return d


def test_cli_listele_ekle_dene_sil(kur, monkeypatch):
    app, sv, api, _ = kur()
    st, d = api("GET", "/api/clilar")
    assert st == 200 and {"opencode", "claude", "codex"} <= {c["ad"] for c in d["clilar"]}
    assert api("POST", "/api/clilar", cli_tanimi())[0] == 200
    ekli = {c["ad"]: c for c in api("GET", "/api/clilar")[1]["clilar"]}["sahtecli"]
    assert ekli["yerlesik"] is False and ekli["kurulu"] is True and ekli["modeller"] == ["ucuz", "pahali"]
    st, d = api("POST", "/api/clilar/dene", {"ad": "sahtecli"})
    assert st == 200 and d["ok"] and "yanit" in d["metin"]
    assert api("POST", "/api/clilar/sil", {"ad": "sahtecli"})[0] == 200
    assert api("POST", "/api/clilar/sil", {"ad": "sahtecli"})[0] == 404


def test_cli_gecersiz_tanim_ve_yerlesik_silinemez(kur):
    app, sv, api, _ = kur()
    st, d = api("POST", "/api/clilar", cli_tanimi(ad="opencode-x"))
    assert st == 400 and "ayrilmis" in d["hata"]
    st, d = api("POST", "/api/clilar", cli_tanimi(komut=["goreli.exe"]))
    assert st == 400 and "MUTLAK" in d["hata"]
    assert api("POST", "/api/clilar/sil", {"ad": "claude"})[0] == 400
    assert api("POST", "/api/clilar", [1, 2])[0] == 400
    assert api("POST", "/api/clilar/dene", {"ad": 5})[0] == 400


def test_cli_rolde_kullaniliyorsa_silinmez(kur):
    app, sv, api, _ = kur()
    klasor_sec(api, kur.proje)
    api("POST", "/api/clilar", cli_tanimi())
    ayar = api("GET", "/api/ayar")[1]
    ayar["roller"]["kodcu"]["calistirici"] = "sahtecli"
    ayar["roller"]["kodcu"]["model"] = None
    assert api("PUT", "/api/ayar", ayar)[0] == 200
    st, d = api("POST", "/api/clilar/sil", {"ad": "sahtecli"})
    assert st == 409 and "kodcu" in d["hata"]
    ayar["roller"]["kodcu"]["calistirici"] = "opencode"
    assert api("PUT", "/api/ayar", ayar)[0] == 200
    assert api("POST", "/api/clilar/sil", {"ad": "sahtecli"})[0] == 200


def test_cli_dene_modelsizse_onerilenlerin_ilkini_kullanir_yazma_izni_vermez(kur, monkeypatch):
    from aktapokus_ajan import arayuz

    gorulen = {}

    class Kayit(Calistirici):
        def calistir(self, istem, klasor, model=None, agent=None, zaman_asimi_sn=900, onayli=True):
            gorulen.update(model=model, onayli=onayli, klasor=Path(klasor))
            return CalistirmaSonucu(ok=True, metin="tamam", token_girdi=3, token_cikti=2)

    monkeypatch.setattr(arayuz, "calistirici_olustur", lambda ad: Kayit())
    app, sv, api, _ = kur()
    api("POST", "/api/clilar", cli_tanimi())
    assert api("POST", "/api/clilar/dene", {"ad": "sahtecli"})[1]["ok"]
    assert gorulen["model"] == "ucuz" and gorulen["onayli"] is False
    assert not gorulen["klasor"].exists()  # gecici klasor temizlendi
    api("POST", "/api/clilar/dene", {"ad": "sahtecli", "model": "pahali"})
    assert gorulen["model"] == "pahali"
    assert api("POST", "/api/clilar/dene", {"ad": "claude"})[1]["ok"] and gorulen["model"] == "haiku"


def test_eklenen_cli_ile_gercek_hat_calisir(kur, tmp_path):
    """Rol ayari eklenen CLI'i secebilir ve hat onu genel calistirici uzerinden surer (sahte yerine gercek calistirici)."""
    from aktapokus_ajan.runners import calistirici_olustur

    app, sv, api, _ = kur(uret=calistirici_olustur)
    klasor_sec(api, kur.proje)
    api("POST", "/api/clilar", cli_tanimi(cikti="json", metin_yolu="sonuc.metin", hata_yolu="bayrak.hata", girdi_yolu="kullanim.gir", cikti_yolu="kullanim.cik",
                                          komut=[__import__("sys").executable, SAHTE_CLI, "--stdin", "--kip", "json"]))
    ayar = api("GET", "/api/ayar")[1]
    ayar["akis"] = ["kodcu"]
    del ayar["roller"]["test"]
    ayar["roller"]["kodcu"].update(calistirici="sahtecli", model=None, okuma_riski_kabul=True)
    assert api("PUT", "/api/ayar", ayar)[0] == 200
    st, plan = api("POST", "/api/gorev", {"gorev": "selam de"})
    assert st == 200 and plan["adimlar"][0]["calistirici"] == "sahtecli"
    api("POST", f"/api/gorev/{plan['kosu']}/onayla", {})
    assert bekle(lambda: app.kosu.durum == "bitti", sn=30)
    adim = [o for o in app.bus.gecmis if o.get("tur") == "adim-bitti"]
    assert len(adim) == 1 and adim[0]["ok"] and adim[0]["metin"].startswith("yanit: KURALLAR")  # hat, rol talimati+kurallarla sarilmis istemi gonderir
    assert (adim[0]["token_girdi"], adim[0]["token_cikti"]) == (11, 5)
    assert [o for o in app.bus.gecmis if o.get("tur") == "adim-basladi"][0]["calistirici"] == "sahtecli"
    assert [o for o in app.bus.gecmis if o.get("tur") == "bitti"][-1]["durum"] == "degisiklik_yok"

# ---------- gorev gecmisi ----------
def test_gecmis_listeler_ve_kaydi_okur(kur):
    def yaz_n(k, i, n):  # her cagrida FARKLI dosya: ikinci kosuda da degisiklik olsun
        (k / f"yeni{n}.txt").write_text("yeni\n", encoding="utf-8")
        return sonuc("yazildi")

    app, sv, api, _ = kur({"kodcu": yaz_n, "test": BASARILI})
    klasor_sec(api, kur.proje)
    assert api("GET", "/api/gecmis")[1] == {"gecmis": []}
    tam_kosu(app, api, kur.proje, karar=True, gorev="ilk gorev")
    tam_kosu(app, api, kur.proje, karar=False, gorev="ikinci gorev")
    st, d = api("GET", "/api/gecmis")
    assert st == 200 and [g["gorev"] for g in d["gecmis"]] == ["ikinci gorev", "ilk gorev"]  # en yeni basta
    assert d["gecmis"][0]["durum"] == "geri_alindi" and d["gecmis"][1]["durum"] == "onaylandi"
    assert d["gecmis"][1]["degisen_sayisi"] == 1 and d["gecmis"][1]["akis"] == ["kodcu", "test"]
    st, k = api("GET", "/api/gecmis?id=" + d["gecmis"][1]["id"])
    assert st == 200 and k["gorev"] == "ilk gorev" and "yeni1.txt" in k["degisen"] and k["adimlar"]


def test_gecmis_gecersiz_kimlik_ve_bozuk_kayit(kur):
    app, sv, api, _ = kur()
    klasor_sec(api, kur.proje)
    tam_kosu(app, api, kur.proje)
    for kotu in ("../roller", "a/b", "..%5Croller", "x" * 70):
        assert api("GET", "/api/gecmis?id=" + kotu)[0] in (400, 404), kotu
    assert api("GET", "/api/gecmis?id=" + "../roller")[0] == 400
    assert api("GET", "/api/gecmis?id=yok123")[0] == 404
    kayitlar = kur.proje / ".aktapokus" / "kayit"
    (kayitlar / "zzz-bozuk.json").write_text("{bozuk", encoding="utf-8")
    assert len(api("GET", "/api/gecmis")[1]["gecmis"]) == 1  # bozuk kayit atlanir, liste dusmez


def test_gecmis_klasor_secilmeden_hata(kur):
    app, sv, api, _ = kur()
    assert api("GET", "/api/gecmis")[0] >= 400


# ---------- ayarlar sayfasi (iskelet) ----------
def test_arayuz_sayfasi_ayarlar_iskeletini_icerir():
    html = (Path(__file__).parent.parent / "aktapokus_ajan" / "web" / "index.html").read_text(encoding="utf-8")
    assert 'id="ayarlar"' in html and 'id="ayarDugme"' in html and 'id="ayarMenu"' in html and 'id="ayarIcerik"' in html
    for bolum in ("genel", "saglayicilar", "modeller", "clilar", "roller", "kullanim", "hakkinda"):
        assert f'["{bolum}",' in html, bolum
    assert "p-ajanlar" not in html and "p-istatistik" not in html  # eski dagnik sekmeler kalktı: her sey Ayarlar'da


def test_ana_ekran_hermes_duzeni_ogelerini_icerir():
    html = (Path(__file__).parent.parent / "aktapokus_ajan" / "web" / "index.html").read_text(encoding="utf-8")
    for kimlik in ("yeniGorev", "ortamCipi", "gecmis", "rolCipleri", "durumCubugu", "durumMetni", "tokenYazi", "baglanti", "gitRozet", "korRozet", "ayarDugme"):
        assert f'id="{kimlik}"' in html, kimlik
    assert 'id="roller"' not in html and 'id="akisCipi"' not in html  # eski rol listesi ve duz yazi cipi kalktı
    assert 'id="projeAd"' not in html and 'id="klasorDegistir"' not in html  # proje/klasor artik yazi kutusundaki ortam cipinde
    assert html.index('id="ortamCipi"') > html.index('id="orta"') and html.index('id="ortamCipi"') < html.index('id="rolCipleri"')
    assert html.index('id="durumCubugu"') > html.index('id="main"')  # durum cubugu ana alanin ALTINDA


def test_favicon_tokensiz_servis_edilir_ve_sayfa_ona_baglanir(kur):
    app, sv, api, _ = kur()
    st, ham = api("GET", "/favicon.ico", token=None)  # token YOK: tarayici simgeyi belirtecsiz ister
    assert st == 200 and isinstance(ham, bytes) and ham[:4] == bytes([0, 0, 1, 0])  # gecerli ICO baslik
    html = (Path(__file__).parent.parent / "aktapokus_ajan" / "web" / "index.html").read_text(encoding="utf-8")
    assert '<link rel="icon" href="/favicon.ico"' in html
    assert api("GET", "/favicon.ico", token=None, host="evil.example")[0] == 403  # Host denetimi simge icin de gecerli
    assert api("GET", "/baska.ico", token=None)[0] == 404


# ---------- onizleme sunucusu ----------
def onizleme(sv, yol, host=None):
    c = http.client.HTTPConnection("127.0.0.1", sv.onizleme_port, timeout=10)
    c.request("GET", yol, headers={"Host": host} if host else {})
    r = c.getresponse()
    return r.status, r.read(), dict(r.getheaders())


def test_onizleme_sunar_ve_yalitir(kur):
    app, sv, api, _ = kur()
    p = kur.proje
    (p / "index.html").write_text("<h1>Merhaba</h1>", encoding="utf-8")
    (p / "site").mkdir()
    (p / "site" / "stil.css").write_text("h1{color:red}", encoding="utf-8")
    (p / ".env").write_text("SECRET=abc123", encoding="utf-8")
    assert onizleme(sv, "/")[0] == 404  # klasor henuz secilmedi
    klasor_sec(api, p)
    st, govde, h = onizleme(sv, "/")
    assert st == 200 and govde == b"<h1>Merhaba</h1>"
    assert "Content-Security-Policy" not in h  # CSP sandbox/frame-ancestors uygulama icindeki tarayici panelinde cerceveyi bos birakiyordu (denendi)
    assert sv.onizleme_port != sv.port  # yalitim: ayri port = ayri koken
    assert h["X-Content-Type-Options"] == "nosniff" and h["Cache-Control"] == "no-store"
    assert onizleme(sv, "/site/stil.css")[2]["Content-Type"].startswith("text/css")
    for kotu in ("/.env", "/.git/config", "/.opencode/opencode.json", "/%2e%2e/%2e%2e/windows/win.ini", "/site/%2e%2e/.env", "/..%5c..%5cx", "/site/", "/yok.html"):
        st, govde, _ = onizleme(sv, kotu)
        assert st in (403, 404) and b"abc123" not in govde, kotu
    assert onizleme(sv, "/", host="evil.example.com")[0] == 403
    assert onizleme(sv, "/", host=f"127.0.0.1:{sv.port}")[0] == 403  # uygulama portuyla degil, onizleme portuyla eslesmeli
    st, d = api("GET", "/api/onizleme")
    assert d["url"] == f"http://127.0.0.1:{sv.onizleme_port}/" and sv.onizleme_port != sv.port


def test_onizleme_proje_degisince_yeni_klasoru_sunar(kur, tmp_path):
    app, sv, api, _ = kur()
    klasor_sec(api, kur.proje)
    (kur.proje / "index.html").write_text("bir", encoding="utf-8")
    ikinci = tmp_path / "ikinci"
    ikinci.mkdir()
    (ikinci / "index.html").write_text("iki", encoding="utf-8")
    assert onizleme(sv, "/")[1] == b"bir"
    st, _ = api("POST", "/api/klasor", {"yol": str(ikinci), "git_baslat": True})
    assert st == 200 and onizleme(sv, "/")[1] == b"iki"


def test_cikti_sekmesi_ve_paneli_sayfada_var():
    html = (Path(__file__).parent.parent / "aktapokus_ajan" / "web" / "index.html").read_text(encoding="utf-8")
    assert 'data-p="p-ciktilar"' in html and 'id="p-ciktilar"' in html and "function ciktilariYukle" in html and "/api/ciktilar" in html


def test_esnek_paneller_bolucu_dugme_ve_izgara_yerlesimi():
    html = (Path(__file__).parent.parent / "aktapokus_ajan" / "web" / "index.html").read_text(encoding="utf-8")  # text modu satir sonlarini zaten LF yapar
    for kimlik in ("solDugme", "sagDugme", "bolucuSol", "bolucuSag", "onizAyri"):
        assert f'id="{kimlik}"' in html, kimlik
    # izgara sirasi: sol | bolucu | orta | bolucu | sag (bolucular ARADA)
    sira = [html.index(f'id="{k}"') for k in ("sol", "bolucuSol", "orta", "bolucuSag", "sag")]
    assert sira == sorted(sira)
    assert "grid-template-columns:var(--sol-w) var(--b1) minmax(0,1fr) var(--b2) var(--sag-w)" in html
    # GERCEK HATA: kapali bolucu display:none olursa izgara sutunlari kayar (iki panel kapaninca orta alan 1 piksele cokuyordu)
    kural = html[html.index("#main.sol-kapali #bolucuSol"):].split("}")[0]
    assert "visibility:hidden" in kural and "display:none" not in kural
    assert "aktapokus.duzen" in html and "pointer-events:none" in html  # boyutlar hatirlanir; surukleme sirasinda iframe fareyi calmaz
    assert "if(g<400)return" in html  # gizli/cok kucuk pencerede kayitli duzen bozulmaz


def test_ayarlar_telegram_bolumu_sayfada_var():
    html = (Path(__file__).parent.parent / "aktapokus_ajan" / "web" / "index.html").read_text(encoding="utf-8")
    assert '["telegram","Telegram"]' in html and "function telegramBolumu" in html and "/api/telegram" in html
    assert "clearInterval(S.telegramZ)" in html  # bolumden cikinca yoklama durur (arka planda bosuna istek atmaz)


# ---------- coklu proje P1: oturumlar ----------
def _ikinci_proje(tmp_path):
    k = tmp_path / "ikinci"
    k.mkdir()
    subprocess.run(["git", "-C", str(k), "init", "-q"], check=True)
    (k / "x.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(k), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(k), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "ilk"], check=True)
    return k


def test_olaylar_proje_kimligiyle_etiketlenir(kur):
    from aktapokus_ajan import projeler

    app, sv, api, _ = kur()
    tam_kosu(app, api, kur.proje)
    kimlik = projeler.proje_kimligi(kur.proje)
    _, olaylar = app.bus.abone_ol(0)
    assert olaylar and all(o.get("proje") == kimlik for o in olaylar), [o for o in olaylar if o.get("proje") != kimlik]


def test_kosu_baslatildigi_projeye_bagli_kalir_secili_proje_degisse_bile(kur, tmp_path):
    from aktapokus_ajan import projeler

    serbest, basladi = threading.Event(), threading.Event()

    def bekleyen(k, i, n):
        basladi.set()
        serbest.wait(15)
        (k / "a_yeni.txt").write_text("a\n", encoding="utf-8")
        return sonuc("yazildi")

    app, sv, api, _ = kur({"kodcu": bekleyen, "test": BASARILI})
    ikinci = _ikinci_proje(tmp_path)
    klasor_sec(api, kur.proje)
    a_kimlik = projeler.proje_kimligi(kur.proje)
    plan = api("POST", "/api/gorev", {"gorev": "a gorevi"})[1]
    assert api("POST", f"/api/gorev/{plan['kosu']}/onayla", {})[0] == 200
    assert basladi.wait(10)
    a_oturum = app.secili
    app.klasor = ikinci  # secili proje B'ye gecti (P2'de arayuz bunu kosu surerken yapabilecek)
    assert app.secili is not a_oturum and app.kosu is None
    serbest.set()
    assert bekle(lambda: a_oturum.kosu.durum == "karar-bekliyor")
    a_oturum.kosu.karar = True  # farki koru (secili proje B oldugu icin API karari B'ye giderdi; A'nin kosusuna dogrudan verilir)
    a_oturum.kosu.karar_olayi.set()
    assert bekle(lambda: a_oturum.kosu.durum == "bitti")
    assert bekle(lambda: a_oturum.aktif_calistirici is None)  # kosunun 'finally' blogu da bitti
    assert a_oturum.son_hat and app.secili.son_hat == {} and app.secili.kosu is None  # B'ye hicbir sey sizmadi
    _, olaylar = app.bus.abone_ol(0)
    gorev_olaylari = [o for o in olaylar if o.get("kosu") == plan["kosu"]]
    assert gorev_olaylari and all(o["proje"] == a_kimlik for o in gorev_olaylari)
    api_a = a_oturum.klasor
    assert (api_a / "a_yeni.txt").exists() and not (ikinci / "a_yeni.txt").exists()  # dosya dogru klasore yazildi


def test_ayni_klasor_yeniden_secilince_yeni_bos_oturum_olur(kur):
    app, sv, api, _ = kur()
    tam_kosu(app, api, kur.proje)
    assert app.kosu is not None
    klasor_sec(api, kur.proje)
    assert app.kosu is None and app.son_hat == {} and len(app.oturumlar) == 1


# ---------- coklu proje P2: es zamanli projeler ----------
def _iki_proje_calisan(kur, tmp_path):
    """A ve B projelerinde ayni anda birer gorev baslatir; her gorevin kendi (ayri) calistirici ornegi vardir."""
    from aktapokus_ajan import projeler

    ornekler = []

    def uret(ad):
        e = Engelli()
        ornekler.append(e)
        return e

    app, sv, api, _ = kur(uret=uret)
    ikinci = _ikinci_proje(tmp_path)
    klasor_sec(api, kur.proje)
    a = projeler.proje_kimligi(kur.proje)
    plan_a = api("POST", "/api/gorev", {"gorev": "a gorevi"})[1]
    assert api("POST", f"/api/gorev/{plan_a['kosu']}/onayla", {})[0] == 200
    assert bekle(lambda: len(ornekler) == 1 and ornekler[0].basladi.is_set())
    st, _ = api("POST", "/api/klasor", {"yol": str(ikinci)})  # A kosarken B'ye gecmek artik serbest
    assert st == 200
    b = projeler.proje_kimligi(ikinci)
    plan_b = api("POST", "/api/gorev", {"gorev": "b gorevi"})[1]
    assert api("POST", f"/api/gorev/{plan_b['kosu']}/onayla", {})[0] == 200
    assert bekle(lambda: len(ornekler) == 2 and ornekler[1].basladi.is_set())
    return app, api, ornekler, (a, plan_a["kosu"]), (b, plan_b["kosu"])


def test_iki_proje_ayni_anda_calisir_ve_durumlari_ayridir(kur, tmp_path):
    app, api, ornekler, (a, ka), (b, kb) = _iki_proje_calisan(kur, tmp_path)
    try:
        d = {o["proje"]: o for o in api("GET", "/api/oturumlar")[1]["oturumlar"]}
        assert d[a]["durum"] == "calisiyor" and d[b]["durum"] == "calisiyor"
        assert d[a]["gorev"] == "a gorevi" and d[b]["gorev"] == "b gorevi" and d[b]["secili"] and not d[a]["secili"]
        assert api("GET", f"/api/p/{a}/durum")[1]["kosu"]["gorev"] == "a gorevi"  # secili proje B iken A'nin durumu
        assert api("GET", "/api/durum")[1]["kosu"]["gorev"] == "b gorevi"
        assert api("GET", f"/api/p/{a}/durum")[1]["klasor"] != api("GET", f"/api/p/{b}/durum")[1]["klasor"]
    finally:
        for e in ornekler:
            e.serbest.set()


def test_bir_projeyi_durdurmak_digerini_durdurmaz(kur, tmp_path):
    app, api, ornekler, (a, ka), (b, kb) = _iki_proje_calisan(kur, tmp_path)
    try:
        st, _ = api("POST", f"/api/p/{a}/gorev/{ka}/durdur", {})
        assert st == 200
        assert ornekler[0].durduruldu is True and ornekler[1].durduruldu is False  # yalniz A'nin calistiricisi durduruldu
        assert bekle(lambda: app.oturumlar[a].kosu.durum in ("bitti", "karar-bekliyor"))
        assert app.oturumlar[b].kosu.durum == "calisiyor"  # B hala kosuyor
        st, _ = api("POST", f"/api/gorev/{kb}/durdur", {})  # B secili: onek olmadan da B'yi durdurur
        assert st == 200 and ornekler[1].durduruldu is True
    finally:
        for e in ornekler:
            e.serbest.set()


def test_calisan_projeye_geri_donunce_oturum_korunur(kur, tmp_path):
    app, api, ornekler, (a, ka), (b, kb) = _iki_proje_calisan(kur, tmp_path)
    try:
        st, _ = api("POST", "/api/klasor", {"yol": str(kur.proje)})
        assert st == 200 and app.secili_kimlik == a
        assert app.kosu is not None and app.kosu.kimlik == ka and app.kosu.durum == "calisiyor"  # sifirlanmadi
    finally:
        for e in ornekler:
            e.serbest.set()


def test_proje_oneki_bilinmeyen_projeye_404_ve_klasor_secemez(kur):
    app, sv, api, _ = kur()
    klasor_sec(api, kur.proje)
    assert api("GET", "/api/p/0123456789/durum")[0] == 404
    assert api("GET", "/api/p/ZZZ/durum")[0] == 404
    from aktapokus_ajan import projeler

    a = projeler.proje_kimligi(kur.proje)
    assert api("POST", f"/api/p/{a}/klasor", {"yol": str(kur.proje)})[0] == 400
    assert api("GET", f"/api/p/{a}/oturumlar")[0] == 200  # onek yalniz yolu yeniden yazar, belirtec denetimi yine gecerli
    assert api("GET", f"/api/p/{a}/durum", token=None)[0] == 401


def test_proje_baglami_secili_projeyi_degistirmez(kur, tmp_path):
    from aktapokus_ajan import projeler

    app, sv, api, _ = kur()
    ikinci = _ikinci_proje(tmp_path)
    klasor_sec(api, kur.proje)
    klasor_sec(api, ikinci)
    a = projeler.proje_kimligi(kur.proje)
    with app.proje_baglami(a):
        assert app.klasor == kur.proje
    assert app.klasor == ikinci


def test_projenin_sonraki_adimi_secili_proje_baskayken_basliyorsa_yine_kendi_oturumuna_baglanir(kur, tmp_path):
    """A'nin ilk adimi B secili iken biter; ikinci adimin calistiricisi A'nin oturumuna yazilmali (durdur A'yi, B'yi degil durdurur)."""
    app, api, ornekler, (a, ka), (b, kb) = _iki_proje_calisan(kur, tmp_path)
    try:
        ornekler[0].serbest.set()  # A'nin ilk adimi biter -> ikinci adim yeni calistirici ornegiyle baslar (secili proje: B)
        assert bekle(lambda: len(ornekler) >= 3 and ornekler[2].basladi.is_set(), 15), f"ikinci adim baslamadi ({len(ornekler)} ornek)"
        assert app.oturumlar[a].aktif_calistirici is ornekler[2]
        assert app.oturumlar[b].aktif_calistirici is ornekler[1]
        assert api("POST", f"/api/p/{a}/gorev/{ka}/durdur", {})[0] == 200
        assert ornekler[2].durduruldu is True and ornekler[1].durduruldu is False
    finally:
        for e in ornekler:
            e.serbest.set()
