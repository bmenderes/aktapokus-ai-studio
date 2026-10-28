"""Bilgisayar acilinca Aktapokus baslasin: komut, kayit (sahte), API, yerel-yalniz politika. Testler gercek kayit defterine ASLA dokunmaz (conftest sahte kayit)."""

from pathlib import Path

import pytest

from aktapokus_ai_studio import otomatik_baslat as ob, uzak
from conftest import SahteKayit
from test_arayuz import klasor_sec, kur  # noqa: F401  (kur: pytest fixture'i)

HTML = (Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "web" / "index.html").read_text(encoding="utf-8")


def test_komut_konsolsuz_pythonw_proje_klasorunu_yola_ekler_ve_uygulama_modunu_acar(tmp_path):
    (tmp_path / "py").mkdir()
    (tmp_path / "py" / "python.exe").write_text("")
    (tmp_path / "py" / "pythonw.exe").write_text("")
    k = ob.komut_uret(python=str(tmp_path / "py" / "python.exe"), kok=tmp_path / "proje")
    assert k.startswith(f'"{tmp_path / "py" / "pythonw.exe"}" -c "') and "pythonw.exe" in k  # konsol penceresi acmaz
    assert f"os.chdir(r'{tmp_path / 'proje'}')" in k and f"sys.path.insert(0,r'{tmp_path / 'proje'}')" in k  # Run anahtari calisma klasoru vermez: yol gomulu
    assert "'ui','--arka-plan'" in k and "'--uygulama'" not in k and "main_giris()" in k and "aktapokus_ai_studio" in k
    with pytest.raises(ob.OtomatikBaslatHatasi, match="tirnak"):
        ob.komut_uret(python="x", kok=Path("C:/a'b"))  # komut satirini bozacak yol reddedilir


def test_ac_kapat_durum_sahte_kayitla():
    kayit = SahteKayit()
    assert ob.durum(kayit) == {"desteklenir": True, "acik": False}
    assert ob.ayarla(True, kayit, komut='"pythonw" -c "...aktapokus_ai_studio..."') == {"desteklenir": True, "acik": True}
    assert kayit.deger and "aktapokus_ai_studio" in kayit.deger
    assert ob.ayarla(False, kayit) == {"desteklenir": True, "acik": False} and kayit.deger is None
    assert ob.ayarla(False, kayit)["acik"] is False  # ikinci kapatma zararsiz
    kayit.deger = "baska-program.exe"  # ayni adli ama bizim olmayan deger 'acik' sayilmaz
    assert ob.durum(kayit)["acik"] is False
    for kotu in ("evet", 1, None):
        with pytest.raises(ob.OtomatikBaslatHatasi):
            ob.ayarla(kotu, kayit)


def test_yazma_hatasi_anlasilir_hataya_cevrilir():
    class Reddeden(SahteKayit):
        def yaz(self, komut):
            raise PermissionError(5, "Access is denied")

    with pytest.raises(ob.OtomatikBaslatHatasi, match="Kayit defterine yazilamadi"):
        ob.ayarla(True, Reddeden(), komut="x")


def test_api_yerel_arayuzden_calisir_uzaktan_reddedilir(kur):
    app, sv, api, _ = kur()
    klasor_sec(api, kur.proje)
    assert api("GET", "/api/otomatik-baslat", None, token=None)[0] == 401
    st, d = api("GET", "/api/otomatik-baslat")
    assert st == 200 and d["acik"] is False
    assert api("POST", "/api/otomatik-baslat", {"acik": "evet"})[0] == 400
    # sahte kayit conftest'te: gercek makineye yazilmaz; windows disinda desteklenmeyen sistemlerde 400 doner
    st, d = api("POST", "/api/otomatik-baslat", {"acik": True})
    assert (st, d.get("acik")) == (200, True) or st == 400
    for yontem in ("GET", "POST"):
        assert uzak.politika(yontem, "/api/otomatik-baslat", uzak.Ayar(yonetim=True)), yontem


def test_testler_gercek_kayit_defterine_dokunmaz():
    assert isinstance(ob._gercek(), SahteKayit)  # conftest gercek winreg yerine sahteyi koyar


def test_arayuz_genel_ayarlarda_otomatik_baslat_satiri_var():
    assert "async function otomatikBaslatSatiri(h)" in HTML and "await otomatikBaslatSatiri(h)" in HTML and "Bilgisayar açılınca Aktapokus başlasın" in HTML
