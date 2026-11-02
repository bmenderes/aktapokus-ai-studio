"""Ag araci: bilgisayarin adaptorleri, agdaki cihazlari bulma (ping + acik port + ARP/MAC) ve bu bilgisayarin IP'sini degistirme.

Yalniz standart kutuphane + Windows araclari (PowerShell, ping, arp, netsh). Tarama yalniz KOMSU agda, kisa baglantilarla yapilir; cihazlara yazmaz.
Bilgisayarin IP'sini degistirmek yonetici yetkisi ister ve yalniz listelenen adaptorlerde, dogrulanmis adreslerle calisir.
"""
from __future__ import annotations

import base64
import ipaddress
import json
import re
import socket
import struct
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

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


# --- Kablodaki cihazi bulma: farkli agdaki (adresi bilinmeyen) cihaz taramada gorunmez; Ethernet dinlenir, cihaz konusursa IP'si paketten okunur ---
KABLO_SURE_SN = 60  # sessiz cihaz seyrek konusur (gercek durum: 30 sn'de 1 yayin)
_kablo_kilit = threading.Lock()


def kablo_adaptorleri() -> list[dict]:
    """Bagli fiziksel Ethernet adaptorleri: [{ad, mac, agler:[ip/onek]}]. APIPA'dakiler de listelenir (adaptorler()'den farki). Windows disinda bos."""
    if sys.platform != "win32":
        return []
    komut = ("Get-NetAdapter -Physical | Where-Object { $_.Status -eq 'Up' -and $_.MediaType -eq '802.3' } | ForEach-Object { [pscustomobject]@{ad=$_.Name;mac=$_.MacAddress;"
             "agler=@(Get-NetIPAddress -InterfaceIndex $_.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue | ForEach-Object { $_.IPAddress + '/' + $_.PrefixLength })} } | ConvertTo-Json -Compress -Depth 3")
    try:
        r = _calistir(["powershell", "-NoProfile", "-NonInteractive", "-Command", komut])
        veri = json.loads(r.stdout) if r.stdout.strip() else []
    except (OSError, subprocess.SubprocessError, ValueError):
        return []
    veri = [veri] if isinstance(veri, dict) else veri
    return [{"ad": str(v["ad"]), "mac": str(v["mac"]).upper().replace("-", ":"), "agler": [str(x) for x in (v.get("agler") or [])]} for v in veri if isinstance(v, dict) and v.get("ad") and v.get("mac")]


def _pcapng_paketleri(veri: bytes) -> list[bytes]:
    """pcapng icindeki Ethernet cerceveleri (standart kutuphaneyle). Bozuk dosyada okunabilen kadarini dondurur."""
    paketler, i, sira, turler = [], 0, "<", {}
    sayac = 0
    while i + 12 <= len(veri):
        tur = struct.unpack_from("<I", veri, i)[0]
        if tur == 0x0A0D0D0A:
            sira = "<" if veri[i + 8:i + 12] == b"\x4d\x3c\x2b\x1a" else ">"
            turler, sayac = {}, 0
        uzunluk = struct.unpack_from(sira + "I", veri, i + 4)[0]
        if uzunluk < 12 or i + uzunluk > len(veri):
            break
        if tur == 1:  # arayuz tanimi: baglanti turu
            turler[sayac] = struct.unpack_from(sira + "H", veri, i + 8)[0]
            sayac += 1
        elif tur == 6 and uzunluk >= 32:  # ayrintili paket
            arayuz, _, _, alinan = struct.unpack_from(sira + "IIII", veri, i + 8)
            if turler.get(arayuz, 1) == 1:
                paketler.append(veri[i + 28:i + 28 + alinan])
        i += uzunluk
    return paketler


def _mac_metni(b: bytes) -> str:
    return ":".join(f"{x:02X}" for x in b)


def _kullanilir_ip(b: bytes) -> str | None:
    ip = ipaddress.IPv4Address(b)
    return None if ip.is_unspecified or ip.is_multicast or ip.is_loopback or str(ip) == "255.255.255.255" else str(ip)


def cerceveleri_coz(paketler: list[bytes], kendi_mac: str, agler: list[str] | None = None) -> list[dict]:
    """Cercevelerden cihazlar: [{mac, uretici, ipler, adet, ag_disi}]. Kendi kartimiz ve grup adresleri elenir; IP'si okunamayan cihaz da MAC'iyle listelenir."""
    kendi = kendi_mac.upper().replace("-", ":")
    cihaz: dict[str, dict] = {}
    for p in paketler:
        if len(p) < 14:
            continue
        kaynak, tip, ofs = p[6:12], p[12:14], 14
        if tip == b"\x81\x00" and len(p) >= 18:  # VLAN etiketi
            tip, ofs = p[16:18], 18
        mac = _mac_metni(kaynak)
        if mac == kendi or kaynak[0] & 1 or kaynak == bytes(6):
            continue
        k = cihaz.setdefault(mac, {"arp": [], "ip": [], "adet": 0})
        k["adet"] += 1
        if tip == b"\x08\x06" and len(p) >= ofs + 28 and p[ofs + 2:ofs + 6] == b"\x08\x00\x06\x04":
            ip = _kullanilir_ip(p[ofs + 14:ofs + 18]) or (_kullanilir_ip(p[ofs + 24:ofs + 28]) if p[ofs + 7] == 1 else None)  # 0.0.0.0 gonderen: sahiplenmek istedigi adres
            if ip and ip not in k["arp"]:
                k["arp"].append(ip)
        elif tip == b"\x08\x00" and len(p) >= ofs + 20:
            ip = _kullanilir_ip(p[ofs + 12:ofs + 16])
            if ip and ip not in k["ip"] and len(k["ip"]) < 8:
                k["ip"].append(ip)
    aglar = []
    for a in agler or []:
        try:
            aglar.append(ipaddress.IPv4Interface(a).network)
        except ValueError:
            pass
    sonuc = []
    for mac, k in cihaz.items():
        ipler = k["arp"] or k["ip"]  # ARP cihazin kendi adresidir; IP basligi yonlendiriciden gecen baskasinin adresi olabilir
        sonuc.append({"mac": mac, "uretici": uretici(mac), "ipler": ipler, "adet": k["adet"], "portlar": [], "ag_disi": bool(ipler) and not any(ipaddress.IPv4Address(ip) in n for ip in ipler for n in aglar)})
    return sorted(sonuc, key=lambda c: (not c["ipler"], -c["adet"]))


def _dinleme_betigi(mac: str, klasor: str, sure: int) -> str:
    desen = "[-:]".join(mac.split(":"))
    return f"""$p = "$env:WINDIR\\System32\\pktmon.exe"; $d = '{klasor.replace("'", "''")}'
& $p stop *> $null
$l = & $p list 2>&1 | Out-String
$ids = @([regex]::Matches($l, '(?mi)^\\s*(\\d+)\\s+{desen}\\b') | ForEach-Object {{ $_.Groups[1].Value }})
if (-not $ids.Count) {{ exit 3 }}
& $p start --capture --comp $ids --pkt-size 128 --file-name "$d\\k.etl" *> "$d\\baslat.txt"
if ($LASTEXITCODE -ne 0) {{ exit 4 }}
Start-Sleep -Seconds {int(sure)}
& $p stop *> "$d\\dur.txt"
& $p etl2pcap "$d\\k.etl" --out "$d\\k.pcapng" *> "$d\\cevir.txt"
exit $LASTEXITCODE
"""


def _agi_yokla(agler: list[str]) -> list[dict]:
    """Adaptorun kendi agini tarar (APIPA ve cok genis aglar haric); bilgisayarin kendi adresi elenir."""
    kendi, sonuc = set(), []
    for a in agler:
        try:
            i = ipaddress.IPv4Interface(a)
            kendi.add(str(i.ip))
            if not i.network.is_link_local and i.network.num_addresses <= AZAMI_ADRES:
                sonuc += tara(str(i.network))
        except (ValueError, AgHatasi):
            continue
    return [c for c in sonuc if c["ip"] not in kendi]


def _birlestir(dinlenen: list[dict], yoklanan: list[dict]) -> list[dict]:
    """Ayni cihaz iki kaynaktan gelirse tek satir: MAC'e gore birlesir, IP ve portlar eklenir."""
    sonuc = list(dinlenen)
    for c in yoklanan:
        var = next((x for x in sonuc if c.get("mac") and x["mac"] == c["mac"]), None)
        if var is None:
            sonuc.append({"mac": c.get("mac"), "uretici": c.get("uretici"), "ipler": [c["ip"]], "adet": 0, "portlar": c.get("portlar") or [], "ag_disi": False})
        else:
            var["portlar"] = c.get("portlar") or []
            var["ag_disi"] = False
            if c["ip"] not in var["ipler"]:
                var["ipler"].insert(0, c["ip"])
    return sorted(sonuc, key=lambda c: (not c["ipler"], -c["adet"]))


def kablo_dinle(ad: object, sure: int = KABLO_SURE_SN, calistir=None, adaptor_listesi=None, yokla=None) -> list[dict]:
    """Secili Ethernet adaptorunu `sure` saniye dinler. Yonetici izni ister (UAC); betik acik metin dosyasi olarak birakilmaz, tek kullanimlik gecici klasore yalniz cikti yazilir."""
    a = next((x for x in (adaptor_listesi or kablo_adaptorleri)() if x["ad"] == ad), None)
    if a is None:
        raise AgHatasi("Boyle bagli bir Ethernet adaptoru yok")
    if not re.fullmatch(r"[0-9A-F]{2}(:[0-9A-F]{2}){5}", a["mac"]):
        raise AgHatasi("Adaptorun MAC adresi okunamadi")
    if not _kablo_kilit.acquire(blocking=False):
        raise AgHatasi("Dinleme zaten suruyor")
    try:
        yoklanan: list[dict] = []
        yoklayici = threading.Thread(target=lambda: yoklanan.extend((yokla or _agi_yokla)(a["agler"])), daemon=True)
        yoklayici.start()
        with tempfile.TemporaryDirectory(prefix="aktapokus-kablo-") as klasor:
            kod = (calistir or _yonetici_calistir)(_dinleme_betigi(a["mac"], klasor, sure), sure + 120)
            if kod == 1223:
                raise AgHatasi("Yonetici izni verilmedi")
            if kod == 3:
                raise AgHatasi("pktmon bu adaptoru listelemedi")
            yol = Path(klasor) / "k.pcapng"
            if kod != 0 or not yol.is_file():
                raise AgHatasi(f"Dinleme tamamlanamadi (kod {kod})")
            dinlenen = cerceveleri_coz(_pcapng_paketleri(yol.read_bytes()), a["mac"], a["agler"])
            yoklayici.join(60)
            return _birlestir(dinlenen, list(yoklanan))
    finally:
        _kablo_kilit.release()


def _yonetici_calistir(betik: str, zaman_asimi: float) -> int:
    kodlu = base64.b64encode(betik.encode("utf-16-le")).decode("ascii")
    komut = (f"try {{ $s = Start-Process powershell -Verb RunAs -WindowStyle Hidden -Wait -PassThru -ArgumentList '-NoProfile','-NonInteractive','-EncodedCommand','{kodlu}' -ErrorAction Stop; exit $s.ExitCode }} catch {{ exit 1223 }}")
    try:
        return _calistir(["powershell", "-NoProfile", "-NonInteractive", "-Command", komut], zaman_asimi).returncode
    except (OSError, subprocess.SubprocessError) as hata:
        raise AgHatasi(f"Dinleme baslatilamadi: {hata}") from None
