"""Birden cok GitHub hesabi: ek hesap girisi (varsayilana dokunmadan), depo sahibine gore hesap secimi, klonlama, listeleme, cikis. Sahte gh; gercek oturumlara dokunmaz (conftest)."""

import json
import subprocess
import time
from pathlib import Path

import pytest

from aktapokus_ai_studio import github as g

SAHTE_GH = str(Path(__file__).with_name("sahte_gh.py"))


@pytest.fixture
def gh(monkeypatch, tmp_path):
    log = tmp_path / "gh.log"
    monkeypatch.setenv("AKTAPOKUS_GH", SAHTE_GH)
    monkeypatch.setenv("SAHTE_GH_LOG", str(log))
    monkeypatch.setenv("SAHTE_GH_ONAY", str(tmp_path / "onay"))
    g._sahip_onbellek.clear()
    yield log
    g.giris_iptal()
    g._giris.clear()


def ek_hesap_ekle(ad):
    d = g.hesaplar_dizini() / ad
    d.mkdir(parents=True)
    (d / "hosts.yml").write_text("github.com:\n    user: " + ad + "\n", encoding="utf-8")


def depo_klasoru(tmp_path, url):
    k = tmp_path / ("p" + str(abs(hash(url))))
    k.mkdir()
    subprocess.run(["git", "init", "-q", str(k)], check=True)
    subprocess.run(["git", "-C", str(k), "remote", "add", "origin", url], check=True)
    return k


def bekle_bitsin():
    bitis = time.time() + 15
    while time.time() < bitis:
        d = g.giris_durumu()
        if d["durum"] != "bekliyor":
            return d
        time.sleep(0.1)
    return g.giris_durumu()


def test_ek_giris_varsayilan_hesaba_dokunmaz_ve_kullanici_adiyla_kaydedilir(gh, tmp_path):
    assert g.giris_baslat(ek=True)["kod"] == "ABCD-1234"
    (tmp_path / "onay").write_text("1")
    d = bekle_bitsin()
    assert d == {"durum": "tamam", "giris": True, "hesap": "ikinci-kullanici", "ek": True}
    assert g.ek_hesaplar() == ["ikinci-kullanici"]
    assert not (g.hesaplar_dizini() / g.YENI_HESAP).exists()  # gecici klasor temizlendi
    assert not (g.gh_dizini() / "hosts.yml").exists()  # varsayilan oturum olusmadi/degismedi
    assert g.durum()["ekler"] == ["ikinci-kullanici"]


def test_ek_giris_varsayilanla_ayni_hesapsa_eklenmez(gh, tmp_path, monkeypatch):
    monkeypatch.setenv("SAHTE_GH_YENI", "Sahte-Kullanici")
    g.giris_baslat(ek=True)
    (tmp_path / "onay").write_text("1")
    d = bekle_bitsin()
    assert d["durum"] == "hata" and "zaten varsayilan" in d["hata"]
    assert g.ek_hesaplar() == [] and not (g.hesaplar_dizini() / g.YENI_HESAP).exists()


def test_islem_klasorun_origin_sahibine_gore_hesap_secer(gh, tmp_path):
    ek_hesap_ekle("bmenderes")
    kisisel = depo_klasoru(tmp_path, "https://github.com/BMenderes/bmenderes.github.io.git")
    baska = depo_klasoru(tmp_path, "https://github.com/aktapokus/aktapokus.github.io.git")
    assert json.loads(g._gh("api", "user", klasor=kisisel))["login"] == "bmenderes"  # sahip eslesti: ek hesap (buyuk/kucuk harf farki onemsiz)
    assert json.loads(g._gh("api", "user", klasor=baska))["login"] == "sahte-kullanici"  # eslesmedi: varsayilan
    dizinler = [json.loads(s)["dizin"] for s in gh.read_text(encoding="utf-8").splitlines()]
    assert Path(dizinler[0]) == g.hesaplar_dizini() / "bmenderes"
    assert "-hesaplar" not in dizinler[1]


def test_ek_hesap_yoksa_yonlendirme_yapilmaz(gh, tmp_path):
    k = depo_klasoru(tmp_path, "https://github.com/bmenderes/x.git")
    g._gh("api", "user", klasor=k)
    assert "-hesaplar" not in json.loads(gh.read_text(encoding="utf-8").splitlines()[0])["dizin"]


def test_klonlama_depo_sahibinin_hesabiyla_yapilir(gh, tmp_path):
    ek_hesap_ekle("bmenderes")
    ust = tmp_path / "ust"
    ust.mkdir()
    g.klonla("bmenderes/bmenderes.github.io", str(ust))
    g.klonla("aktapokus/aktapokus.github.io", str(ust))
    kayitlar = [json.loads(s) for s in gh.read_text(encoding="utf-8").splitlines()]
    klonlar = [k for k in kayitlar if k["argv"][:2] == ["repo", "clone"]]
    assert "-hesaplar" in klonlar[0]["dizin"] and "-hesaplar" not in klonlar[1]["dizin"]


def test_depolar_tum_hesaplari_birlestirir(gh, tmp_path):
    ek_hesap_ekle("bmenderes")
    adlar = {d["depo"] for d in g.depolar()}
    assert {"sahte-kullanici/proje-bir", "sahte-org/kurumsal"} <= adlar


def test_ek_hesap_cikisi_yalniz_onu_kapatir(gh, tmp_path):
    ek_hesap_ekle("bmenderes")
    ek_hesap_ekle("diger")
    assert g.cikis("bmenderes") == {"tamam": True}
    assert g.ek_hesaplar() == ["diger"]
    with pytest.raises(g.GithubHatasi):
        g.cikis("yok-boyle")
    with pytest.raises(g.GithubHatasi):
        g.cikis("..")  # yol gezinmesi: ek hesap listesinde olmayan ad reddedilir
    assert g.ek_hesaplar() == ["diger"]
