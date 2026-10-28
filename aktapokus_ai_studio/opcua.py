"""OPC UA istemcisi (istege bagli: asyncua). Kurulu degilse `kurulu()` False doner; modul yine de iceri alinabilir.

Senkron arayuz: her islem kisa omurlu bir olay dongusunde calisir. Abonelik `abone_ol` ile belli sure dinler.
Bu modul PLC'ye YAZMAZ: yalniz gezme, okuma, abonelik.
"""
import asyncio
import importlib.util
import time


class OpcUaHatasi(Exception):
    pass


def kurulu() -> bool:
    return importlib.util.find_spec("asyncua") is not None


def _gerek():
    if not kurulu():
        raise OpcUaHatasi("asyncua kurulu degil (pip install aktapokus-ai-studio[opcua])")


def _deger(v):
    return v if isinstance(v, (int, float, str, bool)) or v is None else str(v)


async def _agac(dugum, derinlik: int, sinir: list) -> list:
    sonuc = []
    if derinlik <= 0:
        return sonuc
    for c in await dugum.get_children():
        if sinir[0] <= 0:
            break
        sinir[0] -= 1
        ad = (await c.read_browse_name()).Name
        sinif = (await c.read_node_class()).name
        sonuc.append({"kimlik": c.nodeid.to_string(), "ad": ad, "sinif": sinif, "cocuklar": await _agac(c, derinlik - 1, sinir)})
    return sonuc


def _calistir(adres: str, islev, zaman_asimi: float = 5.0):
    _gerek()
    from asyncua import Client

    async def is_():
        try:
            async with Client(adres, timeout=zaman_asimi) as istemci:
                return await islev(istemci)
        except (OSError, asyncio.TimeoutError) as h:
            raise OpcUaHatasi(f"baglanilamadi: {h}") from None

    return asyncio.run(is_())


def agac(adres: str, derinlik: int = 3, en_cok: int = 500) -> list:
    """Objects altindaki dugum agaci: [{kimlik, ad, sinif, cocuklar}]."""
    return _calistir(adres, lambda c: _agac(c.nodes.objects, derinlik, [en_cok]))


def oku(adres: str, kimlik: str):
    async def is_(c):
        return _deger(await c.get_node(kimlik).read_value())

    return _calistir(adres, is_)


def abone_ol(adres: str, kimlikler: list[str], sure_sn: float = 2.0, aralik_ms: int = 100) -> list:
    """Sure boyunca degisimleri toplar: [{kimlik, deger, zaman}] (ilk deger dahil)."""
    olaylar: list = []

    class Isleyici:
        def datachange_notification(self, node, val, data):
            olaylar.append({"kimlik": node.nodeid.to_string(), "deger": _deger(val), "zaman": time.time()})

    async def is_(c):
        abonelik = await c.create_subscription(aralik_ms, Isleyici())
        await abonelik.subscribe_data_change([c.get_node(k) for k in kimlikler])
        await asyncio.sleep(sure_sn)
        await abonelik.delete()
        return olaylar

    return _calistir(adres, is_)
