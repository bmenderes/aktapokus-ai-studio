"""BOOTP/DHCP atama araci: IP'si olmayan cihaz (PLC, surucu, ag modulu) MAC adresiyle IP ister; kullanici o MAC'e bir IP atar, arac yanitlar.

GUVENLIK: yalniz kullanicinin ATADIGI MAC'lere yanit verilir (agdaki gercek DHCP sunucusunun yerine gecmez). Standart kutuphane (UDP 67/68).
"""
from __future__ import annotations

import ipaddress
import socket
import struct
import threading
import time

MAGIC = b"\x63\x82\x53\x63"
DHCP_DISCOVER, DHCP_OFFER, DHCP_REQUEST, DHCP_ACK = 1, 2, 3, 5


class BootpHatasi(Exception):
    pass


def mac_coz(mac: object) -> str:
    s = str(mac).strip().upper().replace("-", ":")
    if len(s.replace(":", "")) == 12 and ":" not in s:
        s = ":".join(s[i:i + 2] for i in range(0, 12, 2))
    if len(s) != 17 or any(len(p) != 2 or any(c not in "0123456789ABCDEF" for c in p) for p in s.split(":")):
        raise BootpHatasi("MAC adresi gecersiz (ornek: 00:1D:9C:12:34:56)")
    return s


def istek_coz(veri: bytes) -> dict | None:
    """BOOTP/DHCP istegini cozer; istek degilse ya da bozuksa None."""
    if len(veri) < 240 or veri[0] != 1 or veri[1] != 1:  # yalniz istek (op=1) ve Ethernet (htype=1)
        return None
    hlen = veri[2]
    if hlen != 6:
        return None
    xid = veri[4:8]
    mac = ":".join(f"{b:02X}" for b in veri[28:34])
    tur, i = None, 236
    if veri[i:i + 4] == MAGIC:
        i += 4
        while i < len(veri) and veri[i] != 255:
            if veri[i] == 0:
                i += 1
                continue
            if i + 1 >= len(veri):
                break
            uz = veri[i + 1]
            if veri[i] == 53 and uz == 1 and i + 2 < len(veri):
                tur = veri[i + 2]
            i += 2 + uz
    return {"mac": mac, "xid": xid, "dhcp_tur": tur, "bayrak": veri[10:12]}


def yanit_uret(istek: dict, ip: str, maske: str, gecit: str | None, sunucu_ip: str) -> bytes | None:
    """BOOTP yaniti (ya da DHCP OFFER/ACK) paketi. DHCP istegi ama DISCOVER/REQUEST degilse None."""
    govde = bytearray(236)
    govde[0:4] = bytes([2, 1, 6, 0])
    govde[4:8] = istek["xid"]
    govde[10:12] = istek["bayrak"]
    govde[16:20] = socket.inet_aton(ip)  # yiaddr
    govde[20:24] = socket.inet_aton(sunucu_ip)  # siaddr
    govde[28:34] = bytes(int(p, 16) for p in istek["mac"].split(":"))
    secenek = bytearray(MAGIC)
    tur = istek["dhcp_tur"]
    if tur is not None:
        if tur not in (DHCP_DISCOVER, DHCP_REQUEST):
            return None
        secenek += bytes([53, 1, DHCP_OFFER if tur == DHCP_DISCOVER else DHCP_ACK])
        secenek += bytes([54, 4]) + socket.inet_aton(sunucu_ip)
        secenek += bytes([51, 4]) + struct.pack("!I", 86400)
    secenek += bytes([1, 4]) + socket.inet_aton(maske)
    if gecit:
        secenek += bytes([3, 4]) + socket.inet_aton(gecit)
    secenek += bytes([255])
    return bytes(govde + secenek).ljust(300, b"\x00")


def _yerel_ip(hedef: str) -> str:
    """`hedef` IP'sine giderken kullanilacak yerel adres (paket gondermez)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect((hedef, 9))
            return s.getsockname()[0]
        except OSError:
            return "0.0.0.0"


class Sunucu:
    def __init__(self, port: int = 67, yanit_hedef: tuple[str, int] | None = ("255.255.255.255", 68)):
        """yanit_hedef None ise yanit istegin geldigi adrese gider (testte)."""
        self.port, self.yanit_hedef = port, yanit_hedef
        self.atamalar: dict[str, dict] = {}
        self.istekler: dict[str, dict] = {}
        self.hata: str | None = None
        self.yerel_ip: str | None = None  # dinlenen adaptorun adresi: Wi-Fi'daki cihazlarin istekleri gelmez, yanit da bu adaptorden cikar
        self.adaptor: str | None = None
        self._kilit = threading.Lock()
        self._dur = threading.Event()
        self._soket: socket.socket | None = None
        self._is: threading.Thread | None = None

    @property
    def calisiyor(self) -> bool:
        return self._is is not None and self._is.is_alive()

    def baslat(self, yerel_ip: str | None = None, adaptor: str | None = None) -> None:
        if self.calisiyor:
            return
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.bind((yerel_ip or "", self.port))
        except OSError as h:
            s.close()
            raise BootpHatasi(f"{self.port}. port acilamadi (baska bir DHCP/BOOTP programi acik olabilir): {h}") from None
        s.settimeout(0.5)
        self._soket, self.hata, self.yerel_ip, self.adaptor = s, None, yerel_ip, adaptor
        with self._kilit:
            self.istekler.clear()  # onceki oturumun (baska adaptorun) istekleri yanlis cihaz sectirmesin
        self._dur.clear()
        self._is = threading.Thread(target=self._dongu, daemon=True, name="bootp")
        self._is.start()

    def durdur(self) -> None:
        self._dur.set()
        if self._is is not None:
            self._is.join(5)
        if self._soket is not None:
            self._soket.close()
            self._soket = None

    @property
    def gercek_port(self) -> int:
        return self._soket.getsockname()[1] if self._soket else self.port

    def ata(self, mac: object, ip: object, maske: object = "255.255.255.0", gecit: object = None) -> dict:
        try:
            a = {"ip": str(ipaddress.IPv4Address(str(ip).strip())), "maske": str(ipaddress.IPv4Address(str(maske).strip())),
                 "gecit": str(ipaddress.IPv4Address(str(gecit).strip())) if gecit not in (None, "") else None}
            ipaddress.IPv4Network(f"0.0.0.0/{a['maske']}")
        except ValueError:
            raise BootpHatasi("IP, maske ya da gecit gecersiz") from None
        m = mac_coz(mac)
        with self._kilit:
            self.atamalar[m] = a
        return {"mac": m, **a}

    def kaldir(self, mac: object) -> None:
        with self._kilit:
            self.atamalar.pop(mac_coz(mac), None)

    def durum(self) -> dict:
        with self._kilit:
            return {"calisiyor": self.calisiyor, "hata": self.hata, "adaptor": self.adaptor if self.calisiyor else None,
                    "atamalar": [{"mac": m, **a} for m, a in self.atamalar.items()],
                    "istekler": sorted(({"mac": m, **v} for m, v in self.istekler.items()), key=lambda x: -x["son"])[:50]}

    def _dongu(self) -> None:
        while not self._dur.is_set():
            try:
                veri, kaynak = self._soket.recvfrom(1500)
            except socket.timeout:
                continue
            except OSError:
                break
            istek = istek_coz(veri)
            if istek is None:
                continue
            with self._kilit:
                kayit = self.istekler.setdefault(istek["mac"], {"adet": 0, "yanit": 0, "ilk": time.time(), "son": 0.0, "tur": "DHCP" if istek["dhcp_tur"] else "BOOTP"})
                kayit["adet"] += 1
                kayit["son"] = time.time()
                atama = self.atamalar.get(istek["mac"])
            if atama is None:
                continue
            paket = yanit_uret(istek, atama["ip"], atama["maske"], atama["gecit"], self.yerel_ip or _yerel_ip(atama["ip"]))
            if paket is None:
                continue
            try:
                self._soket.sendto(paket, self.yanit_hedef or kaynak)
                with self._kilit:
                    kayit["yanit"] += 1
            except OSError as h:
                self.hata = f"yanit gonderilemedi: {h}"
