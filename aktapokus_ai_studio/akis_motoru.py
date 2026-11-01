"""Yapay zeka gerektirmeyen veri akisi motoru (PLC/OPC UA otomasyonlarinin altyapisi; Node-RED mantigi, ek kurulum yok).

Dugum turu kayit defterine yazilir (tur, cikislar, ayar dogrulama, calistirma). Akis {dugumler, oklar} JSON'dur; mesaj (dict) oklar boyunca kopyalanarak tasinir.
Kapsam su an: dogrulama, calistirma, temel mantik dugumleri. Tuval baglantisi ve OPC UA dugumleri sonraki asama (docs/denetim-2026-11-01.md, madde 7).

PLC'ye YAZAN dugum bilerek yoktur: eklenecekse varsayilan kapali, etiket izin listeli, aralik sinirli, gunluklu ve uzaktan yasak olmali; model ciktisi dogrudan yazamaz.
Bu motor PLC'nin guvenlik mantiginin yerine gecmez.
"""

from __future__ import annotations

import copy
import re
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Callable

AZAMI_DUGUM = 200
AZAMI_OK = 500
AZAMI_ADIM = 5000  # dongu olmasa da dallanma patlamasina karsi calistirma basina sinir
KIMLIK_DESENI = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$")


class AkisMotoruHatasi(ValueError):
    pass


@dataclass(frozen=True)
class DugumTuru:
    ad: str
    cikislar: tuple[str, ...]
    calistir: Callable[[dict, dict, "Baglam"], list[tuple[str, dict]]]  # (ayar, mesaj, baglam) -> [(cikis, mesaj), ...]
    ayar_coz: Callable[[dict], dict] = lambda a: {}
    giris: bool = True  # False: tetikleyici, akis buradan baslar


@dataclass
class Baglam:
    gunluk: list[dict] = field(default_factory=list)
    iptal: threading.Event | None = None


TURLER: dict[str, DugumTuru] = {}


def kaydet(tur: DugumTuru) -> DugumTuru:
    if tur.ad in TURLER:
        raise ValueError(f"Dugum turu zaten kayitli: {tur.ad}")
    TURLER[tur.ad] = tur
    return tur


def _alan_adi(a: dict, anahtar: str = "alan") -> str:
    v = a.get(anahtar, "deger")
    if not isinstance(v, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,39}", v):
        raise AkisMotoruHatasi(f"'{anahtar}' gecersiz alan adi")
    return v


def _sayi(a: dict, anahtar: str) -> float:
    v = a.get(anahtar)
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise AkisMotoruHatasi(f"'{anahtar}' sayi olmali")
    return v


_KARSILASTIRMA = {">": lambda x, y: x > y, ">=": lambda x, y: x >= y, "<": lambda x, y: x < y, "<=": lambda x, y: x <= y, "==": lambda x, y: x == y, "!=": lambda x, y: x != y}


def _esik_coz(a: dict) -> dict:
    if a.get("islec") not in _KARSILASTIRMA:
        raise AkisMotoruHatasi("Esik isleci gecersiz")
    return {"alan": _alan_adi(a), "islec": a["islec"], "deger": _sayi(a, "deger")}


def _esik(a: dict, m: dict, b: Baglam) -> list[tuple[str, dict]]:
    v = m.get(a["alan"])
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise AkisMotoruHatasi(f"'{a['alan']}' sayi degil")  # okunamayan deger 'hayir' sayilmaz: hata olarak gorunur
    return [("evet" if _KARSILASTIRMA[a["islec"]](v, a["deger"]) else "hayir", m)]


def _ata_coz(a: dict) -> dict:
    v = a.get("deger")
    if not isinstance(v, (str, int, float, bool)) and v is not None:
        raise AkisMotoruHatasi("Atanacak deger metin, sayi ya da mantiksal olmali")
    return {"alan": _alan_adi(a), "deger": v}


def _gunluk_coz(a: dict) -> dict:
    v = a.get("etiket", "")
    if not isinstance(v, str) or len(v) > 100:
        raise AkisMotoruHatasi("Etiket en cok 100 karakter metin olmali")
    return {"etiket": v}


def _gunluge_yaz(a: dict, m: dict, b: Baglam) -> list[tuple[str, dict]]:
    b.gunluk.append({"etiket": a["etiket"], "mesaj": copy.deepcopy(m)})
    return [("cikis", m)]


kaydet(DugumTuru("baslat", ("cikis",), lambda a, m, b: [("cikis", m)], giris=False))
kaydet(DugumTuru("esik", ("evet", "hayir"), _esik, _esik_coz))
kaydet(DugumTuru("ata", ("cikis",), lambda a, m, b: [("cikis", {**m, a["alan"]: a["deger"]})], _ata_coz))
kaydet(DugumTuru("gunluk", ("cikis",), _gunluge_yaz, _gunluk_coz))


def dogrula(akis: object) -> dict:
    """Akisi dogrular, temiz kopyasini doner. Dongu kabul edilmez (tarama cevrimi tetikleyicinin isidir, akisin degil)."""
    if not isinstance(akis, dict) or not isinstance(akis.get("dugumler"), list):
        raise AkisMotoruHatasi("Akis {dugumler, oklar} olmali")
    ham_d, ham_o = akis["dugumler"], akis.get("oklar", [])
    if not ham_d or len(ham_d) > AZAMI_DUGUM:
        raise AkisMotoruHatasi(f"Akis 1-{AZAMI_DUGUM} dugum icermeli")
    if not isinstance(ham_o, list) or len(ham_o) > AZAMI_OK:
        raise AkisMotoruHatasi(f"En cok {AZAMI_OK} ok olabilir")
    dugumler: dict[str, dict] = {}
    for d in ham_d:
        kimlik, tur = d.get("id") if isinstance(d, dict) else None, d.get("tur") if isinstance(d, dict) else None
        if not isinstance(kimlik, str) or not KIMLIK_DESENI.fullmatch(kimlik) or kimlik in dugumler:
            raise AkisMotoruHatasi("Dugum kimligi gecersiz ya da tekrarli")
        if not isinstance(tur, str) or tur not in TURLER:
            raise AkisMotoruHatasi(f"Bilinmeyen dugum turu: {tur}")
        ayar = d.get("ayar") if isinstance(d.get("ayar"), dict) else {}
        dugumler[kimlik] = {"id": kimlik, "tur": tur, "ayar": TURLER[tur].ayar_coz(ayar)}
    if not any(not TURLER[d["tur"]].giris for d in dugumler.values()):
        raise AkisMotoruHatasi("Akista en az bir baslangic dugumu olmali")
    oklar: list[dict] = []
    for o in ham_o:
        if not isinstance(o, dict) or o.get("kaynak") not in dugumler or o.get("hedef") not in dugumler:
            raise AkisMotoruHatasi("Ok bilinen iki dugumu baglamali")
        k, h = dugumler[o["kaynak"]], dugumler[o["hedef"]]
        cikis = o.get("cikis", TURLER[k["tur"]].cikislar[0] if TURLER[k["tur"]].cikislar else None)
        if cikis not in TURLER[k["tur"]].cikislar:
            raise AkisMotoruHatasi(f"'{k['id']}' dugumunde '{cikis}' cikisi yok")
        if not TURLER[h["tur"]].giris:
            raise AkisMotoruHatasi(f"'{h['id']}' baslangic dugumu: oka hedef olamaz")
        yeni = {"kaynak": k["id"], "cikis": cikis, "hedef": h["id"]}
        if yeni in oklar:
            raise AkisMotoruHatasi("Ayni ok iki kez cizilemez")
        oklar.append(yeni)
    _dongu_denetle(dugumler, oklar)
    return {"dugumler": list(dugumler.values()), "oklar": oklar}


def _dongu_denetle(dugumler: dict[str, dict], oklar: list[dict]) -> None:
    derece = {k: 0 for k in dugumler}
    komsu: dict[str, list[str]] = {k: [] for k in dugumler}
    for o in oklar:
        derece[o["hedef"]] += 1
        komsu[o["kaynak"]].append(o["hedef"])
    kuyruk = deque(k for k, v in derece.items() if v == 0)
    gorulen = 0
    while kuyruk:
        gorulen += 1
        for h in komsu[kuyruk.popleft()]:
            derece[h] -= 1
            if derece[h] == 0:
                kuyruk.append(h)
    if gorulen != len(dugumler):
        raise AkisMotoruHatasi("Akista dongu olamaz")


def calistir(akis: dict, mesaj: dict | None = None, baglam: Baglam | None = None) -> dict:
    """Dogrulanmis akisi baslangic dugumlerinden calistirir. Bir dugumun hatasi yalniz o dali durdurur ve raporlanir: {durum, adim, hatalar, gunluk}."""
    akis = dogrula(akis)
    baglam = baglam or Baglam()
    dugumler = {d["id"]: d for d in akis["dugumler"]}
    kuyruk = deque((d["id"], copy.deepcopy(mesaj or {})) for d in akis["dugumler"] if not TURLER[d["tur"]].giris)
    hatalar: list[dict] = []
    adim = 0
    durum = "bitti"
    while kuyruk:
        if baglam.iptal is not None and baglam.iptal.is_set():
            durum = "iptal"
            break
        if adim >= AZAMI_ADIM:
            durum = "sinir"
            break
        kimlik, m = kuyruk.popleft()
        adim += 1
        d = dugumler[kimlik]
        try:
            ciktilar = TURLER[d["tur"]].calistir(d["ayar"], m, baglam)
        except Exception as hata:  # dugum hatasi motoru dusurmez, ama sessizce de gecmez
            hatalar.append({"dugum": kimlik, "hata": f"{type(hata).__name__}: {hata}"})
            continue
        for cikis, yeni in ciktilar:
            for o in akis["oklar"]:
                if o["kaynak"] == kimlik and o["cikis"] == cikis:
                    kuyruk.append((o["hedef"], copy.deepcopy(yeni)))  # dallar birbirinin mesajini degistiremez
    return {"durum": "hata" if durum == "bitti" and hatalar else durum, "adim": adim, "hatalar": hatalar, "gunluk": baglam.gunluk}
