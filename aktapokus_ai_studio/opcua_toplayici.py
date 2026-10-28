"""Surekli OPC UA veri toplama: abonelikle gelen degisimleri SQLite deposuna yazar; baglanti kopunca yeniden dener. Yalniz okur."""
import asyncio
import threading
import time

from . import opcua
from .opcua_depo import Depo


class Toplayici:
    def __init__(self, adres: str, kimlikler: list[str], adlar: dict[str, str], depo: Depo, aralik_ms: int = 500):
        self.adres, self.kimlikler, self.adlar, self.depo, self.aralik_ms = adres, kimlikler, adlar, depo, aralik_ms
        self.bagli = False
        self.yazilan = 0
        self.hata: str | None = None
        self._is_parcacigi: threading.Thread | None = None
        self._dongu: asyncio.AbstractEventLoop | None = None
        self._dur: asyncio.Event | None = None
        self._hazir = threading.Event()

    def baslat(self) -> None:
        opcua._gerek()
        self._is_parcacigi = threading.Thread(target=lambda: asyncio.run(self._ana()), daemon=True, name="opcua-toplayici")
        self._is_parcacigi.start()
        self._hazir.wait(5)

    def durdur(self) -> None:
        if self.calisiyor and self._dongu is not None and self._dur is not None:
            try:
                self._dongu.call_soon_threadsafe(self._dur.set)
            except RuntimeError:  # dongu bu arada kapandi
                pass
        if self._is_parcacigi is not None:
            self._is_parcacigi.join(10)

    @property
    def calisiyor(self) -> bool:
        return self._is_parcacigi is not None and self._is_parcacigi.is_alive()

    def durum(self) -> dict:
        return {"calisiyor": self.calisiyor, "bagli": self.bagli, "adres": self.adres, "kimlikler": self.kimlikler, "yazilan": self.yazilan, "hata": self.hata}

    async def _ana(self) -> None:
        from asyncua import Client

        self._dongu, self._dur = asyncio.get_running_loop(), asyncio.Event()
        self._hazir.set()
        bekleme = 1.0
        toplayici = self

        class Isleyici:
            def datachange_notification(self, node, val, data):
                kimlik = node.nodeid.to_string()
                try:
                    toplayici.depo.ekle(toplayici.adres, [(time.time(), kimlik, toplayici.adlar.get(kimlik), opcua._deger(val))])
                    toplayici.yazilan += 1
                except Exception as h:  # depo hatasi toplamayi durdurmasin
                    toplayici.hata = f"yazilamadi: {h}"

        while not self._dur.is_set():
            try:
                async with Client(self.adres, timeout=5) as istemci:
                    abonelik = await istemci.create_subscription(self.aralik_ms, Isleyici())
                    await abonelik.subscribe_data_change([istemci.get_node(k) for k in self.kimlikler])
                    self.bagli, self.hata, bekleme = True, None, 1.0
                    while not self._dur.is_set():
                        try:
                            await asyncio.wait_for(self._dur.wait(), 1.0)
                        except asyncio.TimeoutError:
                            await istemci.check_connection()  # kopmussa istisna: dis donguye dusup yeniden baglanir
            except Exception as h:
                self.hata = f"baglanti: {type(h).__name__}: {h}"[:200]
            self.bagli = False
            try:
                await asyncio.wait_for(self._dur.wait(), bekleme)
            except asyncio.TimeoutError:
                bekleme = min(bekleme * 2, 15.0)
