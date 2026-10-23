import os
import time
from pathlib import Path

import pytest

from aktapokus_ajan import ciktilar
from aktapokus_ajan.arayuz import ArayuzSunucusu, Uygulama, guvenli_goreli
from test_arayuz import BASARILI, Istemci, klasor_sec
from conftest import SahteCalistirici, sonuc


def kayit(id, degisen, korundu=True, geri=False, gorev="gorev"):
    return {"id": id, "zaman": f"2026-10-23 10:00:{id[-2:]}", "gorev": gorev, "degisen": degisen, "korundu": korundu, "geri_alindi_sonradan": geri, "durum": "onaylandi"}


def dosya(klasor, ad, icerik="x", dt=None):
    p = Path(klasor) / ad
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(icerik, encoding="utf-8")
    if dt is not None:
        os.utime(p, (dt, dt))
    return p


def topla(klasor, kayitlar):
    return ciktilar.topla(Path(klasor), kayitlar, guvenli_goreli)


def test_tur_bulma():
    assert [ciktilar.tur_bul(a) for a in ("a.HTML", "b.md", "c.PNG", "d.py", "e.xyz", "noktasiz")] == ["html", "md", "gorsel", "kod", "diger", "diger"]


def test_olusan_dosya_yeni_var_olan_degisti_ve_zaman_sirasi(tmp_path):
    dosya(tmp_path, "yeni.txt", dt=2000)
    dosya(tmp_path, "var.txt", dt=3000)
    c = topla(tmp_path, [kayit("20261023-100001", {"yeni.txt": "A", "var.txt": "M"})])
    assert [(x["yol"], x["durum"]) for x in c] == [("var.txt", "degisti"), ("yeni.txt", "yeni")]  # son degisen en ustte


def test_geri_alinan_ve_korunmayan_gorevlerin_dosyalari_cikti_degil(tmp_path):
    for ad in ("a.txt", "b.txt", "c.txt"):
        dosya(tmp_path, ad)
    c = topla(tmp_path, [
        kayit("20261023-100001", {"a.txt": "A"}),
        kayit("20261023-100002", {"b.txt": "A"}, korundu=False),  # geri alindi
        kayit("20261023-100003", {"c.txt": "A"}, geri=True),  # sonradan geri alindi
    ])
    assert [x["yol"] for x in c] == ["a.txt"]


def test_silinen_dosya_listelenmez_ve_ilk_olusturan_korunur(tmp_path):
    dosya(tmp_path, "kal.txt")
    dosya(tmp_path, "gitti.txt")
    c = topla(tmp_path, [
        kayit("20261023-100001", {"kal.txt": "A", "gitti.txt": "A"}, gorev="ilk gorev"),
        kayit("20261023-100002", {"kal.txt": "M", "gitti.txt": "D"}, gorev="ikinci gorev"),
    ])
    assert [x["yol"] for x in c] == ["kal.txt"]
    assert c[0]["gorev"] == "ilk gorev" and c[0]["son_gorev"] == "ikinci gorev" and c[0]["adet"] == 2 and c[0]["durum"] == "yeni"


def test_diskten_silinen_ve_gecersiz_gizli_yollar_atlanir(tmp_path):
    dosya(tmp_path, "var.txt")
    dosya(tmp_path, ".env", "SIR=1")
    dosya(tmp_path, "anahtar.pem", "x")
    c = topla(tmp_path, [kayit("20261023-100001", {
        "var.txt": "A", "yok.txt": "A", ".env": "A", "anahtar.pem": "A", "../disari.txt": "A", "C:/windows/x": "A", "": "A",
    })])
    assert [x["yol"] for x in c] == ["var.txt"]


def test_alt_klasor_ad_ve_klasor_alanlari_ve_sinir(tmp_path):
    dosya(tmp_path, "a/b/c.py")
    c = topla(tmp_path, [kayit("20261023-100001", {"a/b/c.py": "A"})])
    assert (c[0]["ad"], c[0]["klasor"], c[0]["tur"]) == ("c.py", "a/b", "kod")
    for i in range(7):
        dosya(tmp_path, f"d{i}.txt")
    cok = ciktilar.topla(tmp_path, [kayit("20261023-100002", {f"d{i}.txt": "A" for i in range(7)})], guvenli_goreli, azami=4)
    assert len(cok) == 4


def test_bozuk_kayitlar_dusurmez(tmp_path):
    dosya(tmp_path, "x.txt")
    c = topla(tmp_path, [{}, {"korundu": True, "degisen": None}, {"korundu": True, "degisen": {"x.txt": "?", 5: "A"}}, kayit("20261023-100001", {"x.txt": "A"})])
    assert [x["yol"] for x in c] == ["x.txt"]
    klasoru = tmp_path / ".aktapokus" / "kayit"
    klasoru.mkdir(parents=True)
    (klasoru / "1.json").write_text("{bozuk", encoding="utf-8")
    (klasoru / "2.json").write_text("[1]", encoding="utf-8")
    assert ciktilar.kayitlari_oku(tmp_path) == []


def test_http_gercek_gorev_sonrasi_cikti_listesi(proje):
    """Gercek hat: gorev calisir, 'korunsun' denir; dosya Ciktilar'da gorunur. Geri alinan gorevin dosyasi gorunmez."""
    def yaz_n(k, i, n):
        (k / f"cikti{n}.txt").write_text("yeni\n", encoding="utf-8")
        return sonuc("yazildi")

    sahte = SahteCalistirici({"kodcu": yaz_n, "test": BASARILI})
    app = Uygulama(calistirici_uret=lambda ad: sahte)
    sv = ArayuzSunucusu(app)
    sv.baslat()
    try:
        api = Istemci(sv)
        klasor_sec(api, proje)
        assert api("GET", "/api/ciktilar")[1] == {"ciktilar": [], "toplam": 0}

        def kos(karar, gorev):
            st, plan = api("POST", "/api/gorev", {"gorev": gorev})
            assert st == 200
            api("POST", f"/api/gorev/{plan['kosu']}/onayla", {})
            t0 = time.monotonic()
            while app.kosu.durum != "karar-bekliyor" and time.monotonic() - t0 < 15:
                time.sleep(0.05)
            api("POST", f"/api/gorev/{plan['kosu']}/karar", {"korunsun": karar})
            while app.kosu.durum != "bitti" and time.monotonic() - t0 < 30:
                time.sleep(0.05)

        kos(True, "korunan gorev")
        kos(False, "geri alinan gorev")
        st, d = api("GET", "/api/ciktilar")
        assert st == 200 and d["toplam"] == 1 and d["ciktilar"][0]["yol"] == "cikti1.txt"
        assert d["ciktilar"][0]["gorev"] == "korunan gorev" and d["ciktilar"][0]["durum"] == "yeni"
        assert Istemci(sv, token="yanlis")("GET", "/api/ciktilar")[0] == 401
    finally:
        sv.kapat()


def test_http_klasor_secilmeden_hata():
    sv = ArayuzSunucusu(Uygulama())
    sv.baslat()
    try:
        assert Istemci(sv)("GET", "/api/ciktilar")[0] >= 400
    finally:
        sv.kapat()


def test_klasor_yollari_dosya_degildir_ve_listelenmez(tmp_path):
    (tmp_path / "bir_klasor").mkdir()
    dosya(tmp_path, "dosya.txt")
    c = topla(tmp_path, [kayit("20261023-100001", {"bir_klasor": "A", "dosya.txt": "A"})])
    assert [x["yol"] for x in c] == ["dosya.txt"]
