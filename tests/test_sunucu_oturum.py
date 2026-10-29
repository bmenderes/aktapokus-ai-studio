"""OpenCode (sunucu) oturum surekliligi: ayni projede konusurken her gorev yeni sayfa (oturum) acmaz."""

import json
import time

from sahte_sunucu import SahteSunucu
from test_sunucu import calistirici, sahte  # noqa: F401  (pytest fixture'i)

from aktapokus_ai_studio.sunucu import SunucuCalistirici


def _tek(sahte):
    c = calistirici(sahte)
    c.oturum_kipi = "tek"
    return c


def test_varsayilan_kip_her_cagrida_yeni_oturum(sahte, tmp_path):
    c = calistirici(sahte)
    assert c.oturum_kipi == "yeni"
    c.calistir("bir", tmp_path, model="opencode/m1")
    c.calistir("iki", tmp_path, model="opencode/m1")
    assert len(sahte.durum.oturumlar) == 2


def test_tek_kipte_ayni_proje_ve_rol_ayni_oturumu_surdurur(sahte, tmp_path):
    c = _tek(sahte)
    r1 = c.calistir("bir", tmp_path, model="opencode/m1", agent="build")
    r2 = c.calistir("iki", tmp_path, model="opencode/m1", agent="build")
    assert r1.ok and r2.ok
    assert len(sahte.durum.oturumlar) == 1
    assert next(iter(sahte.durum.oturumlar.values()))["istemler"] == ["bir", "iki"]
    assert SunucuCalistirici.oturum_yolu(tmp_path).is_file()


def test_farkli_rol_modeli_ayri_oturum_acar(sahte, tmp_path):
    c = _tek(sahte)
    c.calistir("kod", tmp_path, model="opencode/m1", agent="build")
    c.calistir("test", tmp_path, model="opencode/m2", agent="plan")
    c.calistir("kod 2", tmp_path, model="opencode/m1", agent="build")
    assert len(sahte.durum.oturumlar) == 2  # rol basina bir konusma; gorev basina degil


def test_eski_ya_da_bozuk_kayit_yeni_oturum_acar(sahte, tmp_path):
    c = _tek(sahte)
    c.calistir("bir", tmp_path, model="opencode/m1")
    yol = SunucuCalistirici.oturum_yolu(tmp_path)
    d = json.loads(yol.read_text(encoding="utf-8"))
    d["opencode/m1|"]["zaman"] = time.time() - 15 * 24 * 3600  # 14 gunden eski
    yol.write_text(json.dumps(d), encoding="utf-8")
    c.calistir("iki", tmp_path, model="opencode/m1")
    assert len(sahte.durum.oturumlar) == 2
    yol.write_text(json.dumps({"opencode/m1|": {"id": "../../etc/passwd", "zaman": time.time()}}), encoding="utf-8")  # URL'ye girecek kimlik dogrulanir
    c.calistir("uc", tmp_path, model="opencode/m1")
    assert len(sahte.durum.oturumlar) == 3
    assert all(not k.startswith("..") for k in sahte.durum.oturumlar)


def test_silinmis_oturum_yerine_yenisi_acilir_ve_basarisiz_oturum_birakilir(tmp_path):
    s = SahteSunucu()
    try:
        c = _tek(s)
        c.calistir("bir", tmp_path, model="opencode/m1")
        s.durum.oturumlar.clear()  # kullanici OpenCode'da oturumu sildi
        assert c.calistir("iki", tmp_path, model="opencode/m1").ok
        assert len(s.durum.oturumlar) == 1
    finally:
        s.kapat()
    s = SahteSunucu(davranis="basarisiz")
    try:
        c = _tek(s)
        assert not c.calistir("bir", tmp_path / "x", model="opencode/m1").ok
        assert not SunucuCalistirici.oturum_yolu(tmp_path / "x").exists() or "opencode/m1|" not in json.loads(SunucuCalistirici.oturum_yolu(tmp_path / "x").read_text(encoding="utf-8"))
    finally:
        s.kapat()


def test_surdurulen_oturumda_yalniz_yeni_token_sayilir(sahte, tmp_path):
    c = _tek(sahte)
    r1 = c.calistir("bir", tmp_path, model="opencode/m1")
    o = next(iter(sahte.durum.oturumlar.values()))
    o["sayac"] = 40  # oturum sayaci birikimli (onceki cagrilardan 140); bu cagri sahte sunucuda token harcamaz
    r2 = c.calistir("iki", tmp_path, model="opencode/m1")
    assert (r1.token_girdi, r2.token_girdi) == (100, 0)  # birikimli 140 degil: yalniz bu cagrinin farki (butce dogru sayilir)
