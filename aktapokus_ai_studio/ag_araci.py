"""Ag araci: bilgisayarin adaptorleri, agdaki cihazlari bulma (ping + acik port + ARP/MAC) ve bu bilgisayarin IP'sini degistirme.

Yalniz standart kutuphane + Windows araclari (PowerShell, ping, arp, netsh). Tarama yalniz KOMSU agda, kisa baglantilarla yapilir; cihazlara yazmaz.
Bilgisayarin IP'sini degistirmek yonetici yetkisi ister ve yalniz listelenen adaptorlerde, dogrulanmis adreslerle calisir.
"""
from __future__ import annotations

import ipaddress
import json
import re
import socket
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

AZAMI_ADRES = 512  # /23'ten buyuk tarama reddedilir
PORTLAR = {44818: "EtherNet/IP", 2222: "EtherNet/IP", 102: "S7", 502: "Modbus", 4840: "OPC UA", 80: "HTTP", 443: "HTTPS"}
# Endustriyel uretici onekleri (MAC'in ilk 3 baytı). Yalniz ipucu: "olasi" diye gosterilir.
URETICILER = {
    "00:00:BC": "Rockwell", "00:1D:9C": "Rockwell", "5C:88:16": "Rockwell",
    "00:0E:8C": "Siemens", "08:00:06": "Siemens", "00:1B:1B": "Siemens", "28:63:36": "Siemens",
    "00:80:F4": "Schneider", "00:00:54": "Schneider", "00:00:0A": "Omron", "00:01:05": "Beckhoff",
    "00:A0:45": "Phoenix Contact", "00:90:E8": "Moxa", "00:30:DE": "WAGO", "00:60:65": "B&R",
}
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


class AgHatasi(Exception):
    pass


def _calistir(args: list[str], zaman_asimi: float = 15) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=zaman_asimi,
                          stdin=subprocess.DEVNULL, creationflags=_CREATE_NO_WINDOW)


def adaptorler() -> list[dict]:
    """[{ad, ip, onek, maske, dhcp}] (yalniz IPv4; APIPA 169.254 ve loopback haric). Windows disinda bos."""
    if sys.platform != "win32":
        return []
    komut = ("Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '169.254*' -and $_.IPAddress -ne '127.0.0.1' } | "
             "Select-Object InterfaceAlias,IPAddress,PrefixLength,PrefixOrigin | ConvertTo-Json -Compress")
    try:
        r = _calistir(["powershell", "-NoProfile", "-NonInteractive", "-Command", komut])
        veri = json.loads(r.stdout) if r.stdout.strip() else []
    except (OSError, subprocess.SubprocessError, ValueError):
        return []
    if isinstance(veri, dict):
        veri = [veri]
    sonuc = []
    for v in veri:
        try:
            onek = int(v["PrefixLength"])
            sonuc.append({"ad": str(v["InterfaceAlias"]), "ip": str(v["IPAddress"]), "onek": onek,
                          "maske": str(ipaddress.IPv4Network(f"0.0.0.0/{onek}").netmask), "dhcp": str(v.get("PrefixOrigin")) == "Dhcp"})
        except (KeyError, ValueError, TypeError):
            continue
    return sonuc


def ag_coz(ag: object) -> ipaddress.IPv4Network:
    try:
        n = ipaddress.IPv4Network(str(ag).strip(), strict=False)
    except ValueError:
        raise AgHatasi("Ag adresi gecersiz (ornek: 192.168.1.0/24)") from None
    if n.num_addresses > AZAMI_ADRES:
        raise AgHatasi("Ag cok buyuk (en cok /23)")
    if not n.is_private:
        raise AgHatasi("Yalniz ozel (yerel) aglar taranir")
    return n


def _ping(ip: str) -> bool:
    try:
        return _calistir(["ping", "-n", "1", "-w", "400", ip], 3).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _acik_portlar(ip: str) -> list[int]:
    acik = []
    for p in PORTLAR:
        try:
            with socket.create_connection((ip, p), timeout=0.3):
                acik.append(p)
        except OSError:
            pass
    return acik


def _arp() -> dict[str, str]:
    """{ip: MAC} -- `arp -a` ciktisinda yalniz IP ve MAC desenleri okunur (dilden bagimsiz)."""
    try:
        cikti = _calistir(["arp", "-a"], 10).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    return {m.group(1): m.group(2).upper().replace("-", ":")
            for m in re.finditer(r"(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F]{2}(?:-[0-9a-fA-F]{2}){5})", cikti)}


def uretici(mac: str | None) -> str | None:
    return URETICILER.get((mac or "")[:8].upper())


def tara(ag: object, ping=None, portlar=None, arp=None) -> list[dict]:
    """Agdaki canli cihazlar: [{ip, mac, uretici, portlar:[{no,ad}]}]; IP'ye gore sirali. Parametreler testte degistirilir."""
    ping, portlar, arp = ping or _ping, portlar or _acik_portlar, arp or _arp  # cagri aninda cozulur (testte degistirilebilsin)
    adresler = [str(a) for a in ag_coz(ag).hosts()]
    with ThreadPoolExecutor(64) as havuz:
        canli = [ip for ip, ok in zip(adresler, havuz.map(ping, adresler)) if ok]
        portlu = dict(zip(canli, havuz.map(portlar, canli)))
        mac = arp()  # ping'ten SONRA: ARP onbellegi dolmus olur
        # ping'e yanit vermeyip yalniz ARP'ta gorunen cihazlar da (cogu PLC ICMP'yi kapatabilir) eklenir
        ek = [ip for ip in mac if ip in set(adresler) and ip not in portlu]
        portlu.update(dict(zip(ek, havuz.map(portlar, ek))))
    sonuc = [{"ip": ip, "mac": mac.get(ip), "uretici": uretici(mac.get(ip)), "portlar": [{"no": p, "ad": PORTLAR[p]} for p in acik]} for ip, acik in portlu.items()]
    return sorted(sonuc, key=lambda c: ipaddress.IPv4Address(c["ip"]))


def _adres(deger: object, ad: str) -> str:
    try:
        return str(ipaddress.IPv4Address(str(deger).strip()))
    except ValueError:
        raise AgHatasi(f"{ad} gecersiz") from None


def _adaptoru_bul(ad: object) -> str:
    if not isinstance(ad, str) or ad not in {a["ad"] for a in adaptorler()}:
        raise AgHatasi("Boyle bir adaptor yok")
    return ad


def _netsh(args: list[str]) -> None:
    try:
        r = _calistir(["netsh", *args], 20)
    except (OSError, subprocess.SubprocessError) as h:
        raise AgHatasi(f"netsh calismadi: {h}") from None
    if r.returncode != 0:
        yetki = "yonetici" in (r.stdout + r.stderr).lower() or "elevat" in (r.stdout + r.stderr).lower() or "requires" in (r.stdout + r.stderr).lower()
        raise AgHatasi("Yonetici yetkisi gerekiyor: Aktapokus'u yonetici olarak calistirin" if yetki else ((r.stdout or r.stderr).strip()[:200] or "netsh basarisiz"))


def adaptor_ip_ata(ad: object, ip: object, maske: object, gecit: object = None) -> None:
    ad, ip, maske = _adaptoru_bul(ad), _adres(ip, "IP"), _adres(maske, "Alt ag maskesi")
    try:
        ipaddress.IPv4Network(f"0.0.0.0/{maske}")
    except ValueError:
        raise AgHatasi("Alt ag maskesi gecersiz") from None
    args = ["interface", "ipv4", "set", "address", f"name={ad}", "static", ip, maske]
    if gecit not in (None, ""):
        args.append(_adres(gecit, "Ag gecidi"))
    _netsh(args)


def adaptor_dhcp_yap(ad: object) -> None:
    _netsh(["interface", "ipv4", "set", "address", f"name={_adaptoru_bul(ad)}", "source=dhcp"])
