import json
import os
from pathlib import Path

import pytest

from aktapokus_ajan import projeler
from aktapokus_ajan.arayuz import ArayuzSunucusu, Uygulama
from test_arayuz import Istemci, klasor_sec


def test_ekle_en_son_kullanilan_ustte_ve_tekrar_eklenmez(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(), b.mkdir()
    projeler.ekle_veya_guncelle(a, simdi=100.0)
    projeler.ekle_veya_guncelle(b, simdi=200.0)
    assert [p["ad"] for p in projeler.listele()] == ["b", "a"]
    projeler.ekle_veya_guncelle(a, simdi=300.0)  # a yeniden kullanildi: basa gecer, ikinci kopya olusmaz
    liste = projeler.listele()
    assert [p["ad"] for p in liste] == ["a", "b"] and len(liste) == 2
    assert all(p["var"] for p in liste) and liste[0]["id"] == projeler.proje_kimligi(a)


def test_kimlik_yol_bicimlerinden_bagimsiz(tmp_path):
    a = tmp_path / "Proje"
    a.mkdir()
    assert projeler.proje_kimligi(a) == projeler.proje_kimligi(str(a) + os.sep) == projeler.proje_kimligi(tmp_path / "x" / ".." / "Proje")
    assert projeler.proje_kimligi(a) == projeler.proje_kimligi(str(a).upper())  # Windows: buyuk/kucuk harf ayni klasor


@pytest.mark.skipif(os.name != "nt", reason="Windows'ta yol buyuk/kucuk harf duyarsiz")
def test_kimlik_var_olmayan_yolda_da_buyuk_kucuk_harf_duyarsiz(tmp_path):
    assert projeler.proje_kimligi(tmp_path / "Olmayan" / "Klasor") == projeler.proje_kimligi(tmp_path / "olmayan" / "KLASOR")


def test_silinen_klasor_var_false_ve_sil_klasore_dokunmaz(tmp_path):
    a = tmp_path / "a"
    a.mkdir()
    (a / "dosya.txt").write_text("x")
    projeler.ekle_veya_guncelle(a)
    kimlik = projeler.listele()[0]["id"]
    assert projeler.sil(kimlik) and projeler.listele() == [] and not projeler.sil(kimlik)
    assert (a / "dosya.txt").exists()  # yalniz listeden unutuldu
    projeler.ekle_veya_guncelle(a)
    a_yol = a / "dosya.txt"
    a_yol.unlink()
    a.rmdir()
    assert projeler.listele()[0]["var"] is False  # klasor diskten gitti: liste yine de gosterir, isaretler


def test_bozuk_kayit_defteri_dusurmez_ve_gecersiz_girdileri_atlar(tmp_path):
    yol = projeler.kayit_yolu()
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text("{bozuk", encoding="utf-8")
    assert projeler.listele() == []
    yol.write_text(json.dumps({"projeler": [None, {"yol": ""}, {"ad": "x"}, {"yol": str(tmp_path), "son": "yok"}, {"yol": str(tmp_path)}]}), encoding="utf-8")
    liste = projeler.listele()
    assert len(liste) == 1 and liste[0]["son"] == 0.0  # sayi olmayan 'son' 0; ayni yol bir kez
    projeler.ekle_veya_guncelle(tmp_path / "yeni")  # bozuk/eski dosyanin ustune de yazabilir
    assert len(projeler.listele()) == 2


def test_azami_proje_sayisini_asinca_en_eskiler_silinir(tmp_path):
    for i in range(projeler.AZAMI_PROJE + 5):
        projeler.ekle_veya_guncelle(tmp_path / f"p{i}", simdi=float(i))
    liste = projeler.listele()
    assert len(liste) == projeler.AZAMI_PROJE and liste[0]["ad"] == f"p{projeler.AZAMI_PROJE + 4}"
    assert "p0" not in {p["ad"] for p in liste}


def test_http_klasor_secince_listeye_girer_unut_ve_kisayollar(proje, tmp_path):
    sv = ArayuzSunucusu(Uygulama())
    sv.baslat()
    try:
        api = Istemci(sv)
        assert api("GET", "/api/projeler")[1] == {"projeler": [], "aktif": None}
        klasor_sec(api, proje)
        st, d = api("GET", "/api/projeler")
        assert st == 200 and d["aktif"] == str(proje.resolve()) and [p["ad"] for p in d["projeler"]] == [proje.name]
        kimlik = d["projeler"][0]["id"]
        assert api("POST", "/api/projeler/unut", {"id": "yok"})[0] == 404
        assert api("POST", "/api/projeler/unut", {"id": 5})[0] == 404
        assert api("POST", "/api/projeler/unut", {"id": kimlik})[0] == 200
        assert api("GET", "/api/projeler")[1]["projeler"] == [] and proje.exists()
        assert Istemci(sv, token="yanlis")("GET", "/api/projeler")[0] == 401
        # klasor listesi: kisayollar + buyuk/kucuk harf duyarsiz siralama
        for ad in ("zeta", "Alfa", "beta"):
            (tmp_path / "liste" / ad).mkdir(parents=True)
        st, d = api("GET", "/api/klasorler?yol=" + str(tmp_path / "liste"))
        assert d["klasorler"] == ["Alfa", "beta", "zeta"]
        adlar = [k["ad"] for k in d["kisayollar"]]
        assert adlar[0] == "Ev" and all(Path(k["yol"]).is_dir() for k in d["kisayollar"])
        if os.name == "nt":
            assert any(a.endswith(":") for a in adlar)  # surucu dugmeleri
    finally:
        sv.kapat()


def test_klasor_secimi_basarisiz_olursa_listeye_girmez(tmp_path):
    sv = ArayuzSunucusu(Uygulama())
    sv.baslat()
    try:
        api = Istemci(sv)
        assert api("POST", "/api/klasor", {"yol": str(tmp_path / "yok")})[0] >= 400
        assert api("GET", "/api/projeler")[1]["projeler"] == []
    finally:
        sv.kapat()
