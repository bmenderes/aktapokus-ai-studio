import asyncio
import threading
import time

import pytest

from aktapokus_ai_studio.opcua_depo import Depo


def test_depo_yazar_okur_ve_siler(tmp_path):
    d = Depo(tmp_path / "x.db")
    d.ekle("k", [(1.0, "ns=2;i=1", "Sayac", 5), (2.0, "ns=2;i=1", "Sayac", 6), (3.0, "ns=2;i=2", "Bool", True), (4.0, "ns=2;i=3", "Metin", "a")])
    assert d.say() == 4
    assert [o["deger"] for o in d.son("ns=2;i=1")] == [6.0, 5.0]
    assert d.son("ns=2;i=2")[0]["deger"] == 1.0 and d.son("ns=2;i=3")[0]["deger"] == "a"
    assert d.sil_eski(2.5) == 2 and d.say() == 2
    d.kapat()
    assert Depo(tmp_path / "x.db").say() == 2  # kalici


def test_depo_yolu_ortamdan(tmp_path, monkeypatch):
    from aktapokus_ai_studio import opcua_depo

    monkeypatch.setenv(opcua_depo.DB_ORTAMI, str(tmp_path / "a" / "b.db"))
    assert opcua_depo.db_yolu() == tmp_path / "a" / "b.db"


def test_toplayici_sunucu_sonradan_acilsa_da_yazar(tmp_path):
    pytest.importorskip("asyncua")
    from aktapokus_ai_studio.opcua_test_sunucusu import TestSunucusu
    from aktapokus_ai_studio.opcua_toplayici import Toplayici
    from test_opcua import _port

    port = _port()
    depo = Depo(tmp_path / "t.db")
    adres = f"opc.tcp://127.0.0.1:{port}/aktapokus/test"
    kimlik = "ns=2;s=Sayac"  # sunucu kurulunca gercek kimlik okunacak; once sunucu kapaliyken toplayici hata verir
    t = Toplayici(adres, [], {}, depo)
    t.baslat()
    for _ in range(100):
        if t.hata:
            break
        time.sleep(0.1)
    assert t.calisiyor and not t.bagli and t.hata  # sunucu yok: yeniden deniyor

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

    th = threading.Thread(target=kos, daemon=True)
    th.start()
    assert hazir.wait(15)
    try:
        t.durdur()  # kimlikler sunucu kalkinca belli oldu: yeni toplayici ayni depoya yazar
        s = kutu["s"]
        kimlik = s.dugumler["Sayac"].nodeid.to_string()
        t = Toplayici(adres, [kimlik], {kimlik: "Sayac"}, depo)
        t.baslat()
        for _ in range(100):
            if t.yazilan >= 3:
                break
            time.sleep(0.1)
        assert t.bagli and t.yazilan >= 3
        deger = [o["deger"] for o in depo.son(kimlik, 10)]
        assert len(deger) >= 3 and deger == sorted(deger, reverse=True)
        assert depo.son(kimlik, 1)[0]["ad"] == "Sayac"
    finally:
        t.durdur()
        dur.set()
        th.join(10)
    assert not t.calisiyor
