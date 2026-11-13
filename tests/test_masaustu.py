"""Masaustu kontrolu: gercek fareye, klavyeye ya da ekrana DOKUNMAZ; Windows katmani sahte."""

import base64
import io
import json
import struct
import zlib
from pathlib import Path

import pytest

from aktapokus_ai_studio import masaustu, masaustu_mcp, mcptanim, uzak


@pytest.fixture
def sahte(monkeypatch):
    girdi = []
    k = {"on": 5, "nokta": 5, "fare": (500, 500), "bilgi": {"pencere": 5, "baslik": "Not Defteri", "program": "notepad.exe", "x": 0, "y": 0, "genislik": 100, "yukseklik": 100, "kucuk": False}}
    monkeypatch.setattr(masaustu.sys, "platform", "win32")
    monkeypatch.setattr(masaustu, "_fare_konumu", lambda: k["fare"])
    monkeypatch.setattr(masaustu, "_sanal_ekran", lambda: (0, 0, 1920, 1080))
    monkeypatch.setattr(masaustu, "_on_pencere", lambda: k["on"])
    monkeypatch.setattr(masaustu, "_nokta_penceresi", lambda x, y: k["nokta"])
    monkeypatch.setattr(masaustu, "pencere_bilgi", lambda h: k["bilgi"])
    monkeypatch.setattr(masaustu, "_girdi", lambda o: girdi.append(o))
    monkeypatch.setattr(masaustu, "_api", lambda: type("W", (), {"u": type("U", (), {"SetCursorPos": staticmethod(lambda x, y: k.__setitem__("imlec", (x, y)))})}))
    monkeypatch.setattr(masaustu.time, "sleep", lambda s: None)
    return k, girdi


def test_yaz_unicode_gonderir_metni_kayda_yazmaz(sahte):
    _, girdi = sahte
    masaustu.yaz("gizli ş\n")
    assert ("k", 0, ord("ş"), 4) in girdi[0] and ("k", 0x0D, 0, 0) in girdi[0]
    assert "gizli" not in json.dumps(masaustu.kayit_oku())


@pytest.mark.parametrize("bilgi", [{"baslik": "Machine Expert", "program": "LogicBuilder.exe"}, {"baslik": "x", "program": "powershell.exe"}, {"baslik": "Aktapokus", "program": "msedge.exe"}, {"baslik": "Node-RED : x", "program": "chrome.exe"}])
def test_engelli_pencereye_girdi_gitmez(sahte, bilgi):
    k, girdi = sahte
    k["bilgi"] = {**k["bilgi"], **bilgi}
    for f in (lambda: masaustu.yaz("a"), lambda: masaustu.tus("enter"), lambda: masaustu.tikla(1, 1), lambda: masaustu.kaydir(1, 1, 1)):
        with pytest.raises(masaustu.MasaustuHatasi, match="girdi"):
            f()
    assert girdi == []


def test_kendi_adini_tasiyan_baska_pencere_engellenmez():
    assert not masaustu.baslik_engelli("aktapokus-ai-studio - Visual Studio Code") and masaustu.baslik_engelli(" Aktapokus ")


def test_acil_durdurma_durdurma_ayari_ve_kilitli_oturum(sahte):
    k, girdi = sahte
    k["fare"] = (0, 1)
    with pytest.raises(masaustu.MasaustuHatasi, match="Acil"):
        masaustu.tikla(1, 1)
    k["fare"] = (500, 500)
    masaustu.ayar_yaz(durduruldu=True)
    with pytest.raises(masaustu.MasaustuHatasi, match="durduruldu"):
        masaustu.yaz("a")
    masaustu.ayar_yaz(durduruldu=False)
    k["on"] = 0
    with pytest.raises(masaustu.MasaustuHatasi, match="kilitli"):
        masaustu.yaz("a")
    assert girdi == []


def test_tus_cozumu_win_yasak():
    assert masaustu.tus_coz("ctrl+s") == [0x11, ord("S")] and masaustu.tus_coz("F4") == [0x73]
    for kotu in ("win+r", "", "ctrl+?", None):
        with pytest.raises(masaustu.MasaustuHatasi):
            masaustu.tus_coz(kotu)


def test_goruntu_koordinati_ekrana_cevrilir():
    s = {"x": 100, "y": 50, "olcek": 0.5}
    assert masaustu.koordinat_coz(10, 20, "goruntu", s) == (120, 90) and masaustu.koordinat_coz(10, 20, "ekran", s) == (10, 20)


def test_program_cozumu_engel_ve_kisayol(tmp_path):
    lnk = tmp_path / "SOLIDWORKS 2024.lnk"
    with pytest.raises(masaustu.MasaustuHatasi, match="baslatilamaz"):
        masaustu.program_coz("powershell")
    assert masaustu.program_coz("SOLIDWORKS", [lnk], lambda p: r"C:\sw\SLDWORKS.exe") == (r"C:\sw\SLDWORKS.exe", lnk)
    for hedef, hata in ((r"C:\w\cmd.exe", "baslatilamaz"), (r"C:\x\a.bat", "exe")):
        with pytest.raises(masaustu.MasaustuHatasi, match=hata):
            masaustu.program_coz("SOLIDWORKS", [lnk], lambda p, h=hedef: h)
    with pytest.raises(masaustu.MasaustuHatasi, match="Birden"):
        masaustu.program_coz("SOLID", [lnk, tmp_path / "SOLIDWORKS Ayar.lnk"], lambda p: "")
    with pytest.raises(masaustu.MasaustuHatasi, match="bulunamadi"):
        masaustu.program_coz("olmayan-program-xyz", [], lambda p: "")


def test_png_gecerli():
    v = masaustu.png_kodla(bytes([10, 20, 30, 0] * 4), 2, 2)
    uz = struct.unpack(">I", v[8:12])[0]
    assert v[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", v[16:24]) == (2, 2)
    i = v.index(b"IDAT")
    assert zlib.decompress(v[i + 4:i + 4 + struct.unpack(">I", v[i - 4:i])[0]])[1:4] == bytes([30, 20, 10]) and uz == 13


def test_mcp_protokolu_arac_listesi_hata_ve_gorsel(sahte, monkeypatch):
    monkeypatch.setattr(masaustu, "ekran_goruntusu", lambda p=None, e=None: (b"png", {"olcek": 1}))
    giris = io.BytesIO(b"".join(json.dumps(x).encode() + b"\n" for x in (
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}}, {"jsonrpc": "2.0", "method": "notifications/initialized"}, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "tus", "arguments": {"tuslar": "win+r"}}}, {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "ekran_goruntusu", "arguments": {}}}, {"jsonrpc": "2.0", "id": 5, "method": "yok"})) + b"bozuk\n")
    cikis = io.BytesIO()
    assert masaustu_mcp.calistir(giris, cikis) == 0
    y = {r["id"]: r for r in map(json.loads, cikis.getvalue().splitlines())}
    assert y[1]["result"]["protocolVersion"] == "2025-03-26" and {"tikla", "yaz", "program_baslat"} <= {a["name"] for a in y[2]["result"]["tools"]}
    assert y[3]["result"]["isError"] is True and y[5]["error"]["code"] == -32601 and len(y) == 5
    assert y[4]["result"]["content"][0] == {"type": "image", "data": base64.b64encode(b"png").decode(), "mimeType": "image/png"}


def test_proje_bazinda_acilir_ve_kapanir():
    assert mcptanim.proje_icin("a" * 10) == []
    mcptanim.masaustu_ayarla("a" * 10, True)
    t = mcptanim.proje_icin("a" * 10)[0]
    assert t.komut[1:] == ("-m", "aktapokus_ai_studio", "masaustu-mcp") and Path(t.ortam["PYTHONPATH"]).is_dir() and mcptanim.proje_icin("b" * 10) == []
    mcptanim.masaustu_ayarla("a" * 10, False)
    assert mcptanim.proje_icin("a" * 10) == []


def test_uzaktan_acilamaz():
    for a in (uzak.Ayar(yonetim=False), uzak.Ayar(yonetim=True)):
        assert uzak.politika("POST", "/api/masaustu", a) and uzak.politika("GET", "/api/masaustu", a)


def test_arayuzde_bolum_var():
    html = (Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "web" / "index.html").read_text(encoding="utf-8")
    assert '["masaustu","Masaüstü"]' in html and "async function masaustuBolumu(h)" in html


@pytest.mark.parametrize("bilgi", [{"baslik": "Windows Default Lock Screen", "program": "LockApp.exe"}, {"baslik": "", "program": "consent.exe"}])
def test_kilit_ekranina_ve_izin_sorusuna_girdi_gitmez_liste_bosaltilsa_bile(sahte, bilgi):
    k, girdi = sahte
    masaustu.ayar_yaz(programlar=[])
    k["bilgi"] = {**k["bilgi"], **bilgi}
    for f in (lambda: masaustu.yaz("a"), lambda: masaustu.tus("enter"), lambda: masaustu.tikla(1, 1)):
        with pytest.raises(masaustu.MasaustuHatasi, match="kilitli"):
            f()
    assert girdi == []


def _ogeler_betigi(monkeypatch, donus):
    """ogeler()'in PowerShell'e verdigi betigi yakalar; gercek pencereye dokunmaz."""
    import subprocess
    from types import SimpleNamespace
    yakalanan = {}
    monkeypatch.setattr(masaustu, "_hazirlik", lambda: None)
    monkeypatch.setattr(masaustu, "_izin_ver", lambda h: {})
    monkeypatch.setattr(masaustu, "kaydet", lambda *a, **k: None)

    def sahte(komut, **k):
        yakalanan["betik"] = komut[-1]
        return SimpleNamespace(**donus)

    monkeypatch.setattr(subprocess, "run", sahte)
    return yakalanan


def test_ogeler_betigi_powershellde_ayristirilir(monkeypatch):
    """GERCEK HATA: betikte sozdizimi hatasi vardi, arac her zaman bos liste donuyordu. Betik gercek PowerShell ayristiricisindan gecmeli."""
    import shutil
    import subprocess
    import sys
    if sys.platform != "win32" or not shutil.which("powershell"):
        pytest.skip("PowerShell yok")
    gercek = subprocess.run
    y = _ogeler_betigi(monkeypatch, {"returncode": 0, "stdout": '[{"ad":"Tamam","tur":"Button"}]', "stderr": ""})
    assert masaustu.ogeler(123) == [{"ad": "Tamam", "tur": "Button"}]
    denetim = "$h=$null;[void][Management.Automation.Language.Parser]::ParseInput($env:AKTAPOKUS_BETIK,[ref]$null,[ref]$h);if($h.Count){$h|%{$_.Message};exit 1}"
    import os
    r = gercek(["powershell", "-NoProfile", "-NonInteractive", "-Command", denetim], capture_output=True, text=True, timeout=60, env={**os.environ, "AKTAPOKUS_BETIK": y["betik"]})
    assert r.returncode == 0, r.stdout + r.stderr


def test_ogeler_powershell_hatasi_bos_liste_degil_hatadir(monkeypatch):
    _ogeler_betigi(monkeypatch, {"returncode": 1, "stdout": "", "stderr": "Unexpected token"})
    with pytest.raises(masaustu.MasaustuHatasi, match="Unexpected token"):
        masaustu.ogeler(123)


def _sahte_cekim(monkeypatch, ekranlar):
    """ekran_goruntusu'nun hangi alani cektigini yakalar (gercek ekrana dokunmaz)."""
    import ctypes
    from types import SimpleNamespace
    cekilen = {}

    def blt(hedef, hx, hy, tg, ty, kaynak, x, y, gen, yuk, kip):
        cekilen.update(x=x, y=y, gen=gen, yuk=yuk, tg=tg, ty=ty)
        return 1

    g = SimpleNamespace(CreateCompatibleDC=lambda k: 1, CreateCompatibleBitmap=lambda k, a, b: 1, SelectObject=lambda a, b: 1, SetStretchBltMode=lambda a, b: 1, StretchBlt=blt,
                        GetDIBits=lambda h, b, a, ty, t, bi, z: ty, DeleteObject=lambda b: 1, DeleteDC=lambda h: 1)
    u = SimpleNamespace(GetDC=lambda h: 1, ReleaseDC=lambda h, k: 1)
    monkeypatch.setattr(masaustu, "_api", lambda: SimpleNamespace(u=u, g=g, c=ctypes))
    monkeypatch.setattr(masaustu, "_hazirlik", lambda: None)
    monkeypatch.setattr(masaustu, "kaydet", lambda *a, **k: None)
    monkeypatch.setattr(masaustu, "_ekranlar", lambda: list(ekranlar))
    return cekilen


def test_ekran_goruntusu_tek_monitor_ceker_ve_koordinat_o_monitore_gore_cevrilir(monkeypatch):
    """GERCEK HATA: iki monitor (3840x1200) tek goruntuye sigdirilinca olcek 0.33 oluyor, yazilar okunmuyordu."""
    c = _sahte_cekim(monkeypatch, [(0, 0, 1920, 1200), (1920, 0, 1920, 1200)])
    _, bilgi = masaustu.ekran_goruntusu()
    assert (c["x"], c["gen"], c["tg"]) == (0, 1920, 1280) and bilgi["ekran"] == 1 and bilgi["ekran_sayisi"] == 2 and bilgi["olcek"] == round(1280 / 1920, 4)
    _, bilgi = masaustu.ekran_goruntusu(None, 2)
    assert (c["x"], c["y"], c["gen"], c["yuk"]) == (1920, 0, 1920, 1200) and bilgi["ekran"] == 2
    assert masaustu.koordinat_coz(640, 400) == (1920 + 960, 600)  # ikinci monitorun ortasi
    for kotu in (0, 3, "x"):
        with pytest.raises(masaustu.MasaustuHatasi):
            masaustu.ekran_goruntusu(None, kotu)


def test_ekran_goruntusu_monitor_okunamazsa_tum_ekrana_duser(monkeypatch):
    c = _sahte_cekim(monkeypatch, [])
    monkeypatch.setattr(masaustu, "_sanal_ekran", lambda: (0, 0, 1920, 1080))
    _, bilgi = masaustu.ekran_goruntusu()
    assert (c["gen"], c["yuk"]) == (1920, 1080) and bilgi["ekran_sayisi"] == 1
