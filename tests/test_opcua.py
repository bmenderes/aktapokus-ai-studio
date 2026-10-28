import asyncio
import socket
import threading

import pytest

pytest.importorskip("asyncua")

from aktapokus_ai_studio import opcua
from aktapokus_ai_studio.opcua_test_sunucusu import TestSunucusu


def _port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _sunucuda(islev):
    """Test sunucusunu ayri bir is parcacigindan kaldirir, senkron islevi calistirir, sonra durdurur."""
    port = _port()
    hazir, dur = threading.Event(), threading.Event()
    kutu = {}

    def kos():
        async def ana():
            async with TestSunucusu(port, 0.05) as s:
                kutu["s"] = s
                hazir.set()
                while not dur.is_set():
                    await asyncio.sleep(0.05)

        asyncio.run(ana())

    t = threading.Thread(target=kos, daemon=True)
    t.start()
    assert hazir.wait(15)
    try:
        return islev(kutu["s"])
    finally:
        dur.set()
        t.join(10)


def test_agac_oku_abone():
    def dene(s):
        agac = opcua.agac(s.adres)
        test = next(d for d in agac if d["ad"] == "Test")
        adlar = {c["ad"]: c["kimlik"] for c in test["cocuklar"]}
        assert {"Sayac", "Sinus", "Bool", "Metin", "Yazilabilir"} <= set(adlar)
        assert isinstance(opcua.oku(s.adres, adlar["Sayac"]), int)
        olaylar = opcua.abone_ol(s.adres, [adlar["Sayac"]], sure_sn=1.0)
        degerler = [o["deger"] for o in olaylar]
        assert len(degerler) >= 2 and degerler == sorted(degerler)

    _sunucuda(dene)


def test_baglanti_hatasi():
    with pytest.raises(opcua.OpcUaHatasi):
        opcua.oku("opc.tcp://127.0.0.1:1/x", "ns=2;i=1")


def test_yazilabilir_dugum_yalniz_testte():
    from asyncua import Client

    def dene(s):
        async def yaz():
            async with Client(s.adres) as c:
                n = c.get_node(s.dugumler["Yazilabilir"].nodeid)
                await n.write_value(42)
                return await n.read_value()

        assert asyncio.run(yaz()) == 42

    _sunucuda(dene)


def test_asyncua_yokken_kurulu_false(monkeypatch):
    monkeypatch.setattr(opcua.importlib.util, "find_spec", lambda ad: None)
    assert opcua.kurulu() is False
    with pytest.raises(opcua.OpcUaHatasi):
        opcua.agac("opc.tcp://127.0.0.1:1/x")
