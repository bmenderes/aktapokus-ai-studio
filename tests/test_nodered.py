"""Node-RED yonetimi: yalniz yerel, uzaktan yonetilemez, arayuz icinde acilir, testte gercek kurulum yapmaz."""

import json
from pathlib import Path

import pytest

from aktapokus_ai_studio import nodered, uzak


def test_ayar_yalniz_yerel_dinler_ve_yonetim_yolu_gizlidir(tmp_path):
    m = nodered.ayar_metni(1234, "/r-gizli", tmp_path, "sir")
    d = json.loads(m.split("=", 1)[1].rsplit(";", 1)[0])
    assert d["uiHost"] == "127.0.0.1" and d["httpAdminRoot"] == "/r-gizli" and d["httpNodeRoot"].startswith("/r-gizli")


def test_kurulu_degilken_baslamaz_ve_durum_bildirir():
    y = nodered.Yonetici()
    d = y.durum()
    assert d["kurulu"] is False and d["calisiyor"] is False and d["adres"] is None and d["surum"] == nodered.SURUM
    with pytest.raises(nodered.NodeRedHatasi):
        y.baslat()


def test_npm_yoksa_anlasilir_hata(monkeypatch):
    monkeypatch.setattr(nodered.shutil, "which", lambda ad: None)
    with pytest.raises(nodered.NodeRedHatasi, match="Node.js"):
        nodered.Yonetici().kur()


def test_uzaktan_yonetim_izniyle_bile_kapali():
    for a in (uzak.Ayar(yonetim=False), uzak.Ayar(yonetim=True)):
        for yontem, yol in (("GET", "/api/nodered"), ("POST", "/api/nodered/kur"), ("POST", "/api/nodered/baslat"), ("POST", "/api/nodered/durdur")):
            assert uzak.politika(yontem, yol, a), yol


def test_arayuzde_ayarlar_icinde_cerceve():
    html = (Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "web" / "index.html").read_text(encoding="utf-8")
    assert '["nodered","Node-RED"]' in html and "async function noderedBolumu(h)" in html and 'e("iframe",{title:"Node-RED"' in html
    assert 'window.open("http://127.0.0.1' not in html
