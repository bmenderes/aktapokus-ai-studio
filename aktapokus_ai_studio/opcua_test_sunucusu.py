"""Yerel OPC UA TEST sunucusu (asyncua gerekir): gercek PLC olmadan istemciyi denemek icin.

Calistir: python -m aktapokus_ai_studio.opcua_test_sunucusu [--port 4840]
Dugumler: Test/Sayac, Test/Sinus, Test/Bool, Test/Metin, Test/Yazilabilir (yazilabilir).
"""
import argparse
import asyncio
import math

AD_ALANI = "urn:aktapokus:test"
ADRES = "opc.tcp://127.0.0.1:{port}/aktapokus/test"


class TestSunucusu:
    """Arka plan dongusuyle degerleri guncelleyen sunucu; `async with` ile kullanilir."""

    __test__ = False  # pytest sinif sanmasin

    def __init__(self, port: int = 4840, aralik_sn: float = 0.2):
        self.port = port
        self.aralik_sn = aralik_sn
        self.adres = ADRES.format(port=port)
        self.dugumler: dict = {}
        self._gorev = None

    async def __aenter__(self):
        from asyncua import Server

        self.sunucu = Server()
        await self.sunucu.init()
        self.sunucu.set_endpoint(self.adres)
        self.sunucu.set_server_name("Aktapokus Test Sunucusu")
        idx = await self.sunucu.register_namespace(AD_ALANI)
        klasor = await self.sunucu.nodes.objects.add_object(idx, "Test")
        self.dugumler["Sayac"] = await klasor.add_variable(idx, "Sayac", 0)
        self.dugumler["Sinus"] = await klasor.add_variable(idx, "Sinus", 0.0)
        self.dugumler["Bool"] = await klasor.add_variable(idx, "Bool", False)
        self.dugumler["Metin"] = await klasor.add_variable(idx, "Metin", "merhaba")
        self.dugumler["Yazilabilir"] = await klasor.add_variable(idx, "Yazilabilir", 0)
        await self.dugumler["Yazilabilir"].set_writable()
        await self.sunucu.start()
        self._gorev = asyncio.create_task(self._dongu())
        return self

    async def __aexit__(self, *a):
        self._gorev.cancel()
        try:
            await self._gorev
        except asyncio.CancelledError:
            pass
        await self.sunucu.stop()

    async def _dongu(self):
        n = 0
        while True:
            n += 1
            await self.dugumler["Sayac"].write_value(n)
            await self.dugumler["Sinus"].write_value(math.sin(n / 10))
            await self.dugumler["Bool"].write_value(n % 10 < 5)
            await self.dugumler["Metin"].write_value(f"tik {n}")
            await asyncio.sleep(self.aralik_sn)


async def _calistir(port: int):
    async with TestSunucusu(port) as s:
        print(f"OPC UA test sunucusu: {s.adres}  (durdur: Ctrl+C)", flush=True)
        await asyncio.Event().wait()


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--port", type=int, default=4840)
    try:
        asyncio.run(_calistir(p.parse_args().port))
    except KeyboardInterrupt:
        pass
    except ImportError:
        raise SystemExit("asyncua kurulu degil: pip install asyncua")


if __name__ == "__main__":
    main()
