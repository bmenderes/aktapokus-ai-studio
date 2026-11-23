"""Sirlar (uzak erisim anahtari, Telegram token'i) diskte DPAPI ile korunur; eski duz metin okunur ve korumali bicime gecirilir."""

import json
import os

import pytest

from aktapokus_ai_studio import gizli, telegram, uzak

windows = pytest.mark.skipif(os.name != "nt", reason="DPAPI yalniz Windows")


@windows
def test_koru_ac_gidis_donus_ve_bozuk_deger():
    k = gizli.koru("gizli-deger")
    assert gizli.korumali_mi(k) and "gizli-deger" not in k and gizli.ac(k) == "gizli-deger"
    assert gizli.ac("duz-metin") == "duz-metin" and gizli.ac("dpapi:bozuk!") is None and gizli.ac(None) is None


@windows
def test_uzak_anahtar_diskte_duz_metin_degil_ve_eski_dosya_gecirilir(tmp_path, monkeypatch):
    monkeypatch.setenv(uzak.AYAR_ORTAMI, str(tmp_path / "uzak.json"))
    _, cihaz, anahtar = uzak.cihaz_ekle("telefon")
    ham = (tmp_path / "uzak.json").read_text(encoding="utf-8")
    assert anahtar not in ham and cihaz.ozet not in ham and '"ozet": "dpapi:' in ham and uzak.cihaz_bul(uzak.oku(), anahtar)[0].kimlik == cihaz.kimlik
    eski = "a" * 40
    (tmp_path / "uzak.json").write_text(json.dumps({"acik": True, "port": 47650, "anahtar": eski}), encoding="utf-8")
    assert uzak.cihaz_bul(uzak.oku(), eski)[0].ad == uzak.ESKI_CIHAZ_ADI  # eski duz anahtar calismaya devam eder (telefon yeniden eslestirilmez)
    ham = (tmp_path / "uzak.json").read_text(encoding="utf-8")
    assert eski not in ham and uzak.ozet(eski) not in ham and '"anahtar"' not in ham  # yalniz korumali ozeti kalir
    duz = json.loads(ham)
    duz["cihazlar"][0]["ozet"] = uzak.ozet(eski)  # duz metin ozet de korumali bicime gecirilir
    (tmp_path / "uzak.json").write_text(json.dumps(duz), encoding="utf-8")
    assert uzak.cihaz_bul(uzak.oku(), eski)[0] is not None and uzak.ozet(eski) not in (tmp_path / "uzak.json").read_text(encoding="utf-8")


@windows
def test_telegram_token_dosyasi_korumali_bicime_gecirilir(tmp_path, monkeypatch):
    monkeypatch.setattr(telegram.Path, "home", lambda: tmp_path)
    monkeypatch.delenv(telegram.TOKEN_ORTAMI, raising=False)
    (tmp_path / ".aktapokus").mkdir()
    dosya = tmp_path / ".aktapokus" / "telegram.token"
    dosya.write_text("123:ABC-token\n", encoding="utf-8")
    assert telegram.token_oku() == "123:ABC-token"
    assert "123:ABC-token" not in dosya.read_text(encoding="utf-8") and telegram.token_oku() == "123:ABC-token"
