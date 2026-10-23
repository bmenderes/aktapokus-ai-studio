import copy
import json
from pathlib import Path

import pytest

from aktapokus_ajan.config import VARSAYILAN_AYAR, AyarHatasi, ayar_coz, ayar_yukle, ayar_yolu
from aktapokus_ajan.klasor import KlasorHatasi, guvenli_klasor


def ayar(**degisim):
    veri = copy.deepcopy(VARSAYILAN_AYAR)
    veri.update(degisim)
    return veri


def test_varsayilan_ayar_gecerli_ve_siralama():
    a = ayar_coz(VARSAYILAN_AYAR)
    assert a.akis == ("kodcu", "test")
    assert [r.ad for r in a.rol_sirasi()] == ["kodcu", "test"]
    assert a.roller["test"].dogrulama is True and a.roller["kodcu"].dogrulama is False


@pytest.mark.parametrize(
    "degisim",
    [
        {"roller": {}},
        {"roller": []},
        {"akis": []},
        {"akis": ["yok"]},
        {"akis": ["test", "kodcu"]},  # ilk rol dogrulama olamaz
        {"azami_duzeltme": -1},
        {"azami_duzeltme": True},
        {"butce_token": 0},
        {"butce_token": "10"},
        {"zaman_asimi_sn": 5},
    ],
)
def test_gecersiz_ayar_reddedilir(degisim):
    with pytest.raises(AyarHatasi):
        ayar_coz(ayar(**degisim))


def test_rol_alanlari_dogrulanir():
    veri = ayar()
    veri["roller"]["kodcu"]["calistirici"] = "bilinmeyen"
    with pytest.raises(AyarHatasi, match="bilinmeyen calistirici"):
        ayar_coz(veri)
    veri = ayar()
    veri["roller"]["kodcu"]["talimat"] = "  "
    with pytest.raises(AyarHatasi, match="talimat"):
        ayar_coz(veri)
    veri = ayar()
    veri["roller"]["kodcu"]["model"] = ""
    with pytest.raises(AyarHatasi, match="model"):
        ayar_coz(veri)
    veri = ayar()
    veri["roller"]["test"]["dogrulama"] = "evet"
    with pytest.raises(AyarHatasi, match="dogrulama"):
        ayar_coz(veri)


def test_model_null_olabilir_ve_koke_nesne_gerekir():
    veri = ayar()
    veri["roller"]["kodcu"]["model"] = None
    assert ayar_coz(veri).roller["kodcu"].model is None
    with pytest.raises(AyarHatasi):
        ayar_coz([1, 2])


def test_ayar_yukle_dosya_yok_ve_bozuk(tmp_path):
    with pytest.raises(AyarHatasi, match="aktapokus ac"):
        ayar_yukle(tmp_path)
    yol = ayar_yolu(tmp_path)
    yol.parent.mkdir()
    yol.write_text("{bozuk", encoding="utf-8")
    with pytest.raises(AyarHatasi, match="okunamadi"):
        ayar_yukle(tmp_path)
    yol.write_text(json.dumps(VARSAYILAN_AYAR), encoding="utf-8")
    assert ayar_yukle(tmp_path).butce_token == 200000


def test_guvenli_klasor_normal_proje_kabul(tmp_path):
    p = tmp_path / "proje"
    p.mkdir()
    assert guvenli_klasor(p) == p.resolve()


def test_guvenli_klasor_reddedilenler(tmp_path):
    with pytest.raises(KlasorHatasi, match="bulunamadi"):
        guvenli_klasor(tmp_path / "yok")
    with pytest.raises(KlasorHatasi, match="Ana dizin"):
        guvenli_klasor(Path.home())
    with pytest.raises(KlasorHatasi, match="Ana dizin"):
        guvenli_klasor(Path.home().parent)
    with pytest.raises(KlasorHatasi):
        guvenli_klasor(Path(Path.home().anchor))
    dosya = tmp_path / "dosya.txt"
    dosya.write_text("x")
    with pytest.raises(KlasorHatasi, match="bulunamadi"):
        guvenli_klasor(dosya)


def test_guvenli_klasor_sistem_klasoru(monkeypatch, tmp_path):
    sistem = tmp_path / "SistemKlasoru"
    (sistem / "alt").mkdir(parents=True)
    monkeypatch.setenv("SystemRoot", str(sistem))
    with pytest.raises(KlasorHatasi, match="Sistem"):
        guvenli_klasor(sistem)
    with pytest.raises(KlasorHatasi, match="Sistem"):
        guvenli_klasor(sistem / "alt")
