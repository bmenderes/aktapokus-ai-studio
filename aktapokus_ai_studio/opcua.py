"""OPC UA istemcisi (istege bagli: asyncua). Kurulu degilse `kurulu()` False doner; modul yine de iceri alinabilir.

Senkron arayuz: her islem kisa omurlu bir olay dongusunde calisir. Abonelik `abone_ol` ile belli sure dinler.
Bu modul PLC'ye YAZMAZ: yalniz gezme, okuma, abonelik.
"""
import asyncio
import contextlib
import contextvars
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


POLITIKALAR = ("None", "Basic128Rsa15", "Basic256", "Basic256Sha256", "Aes128_Sha256_RsaOaep", "Aes256_Sha256_RsaPss")
MODLAR = ("None", "Sign", "SignAndEncrypt")
_AYAR: contextvars.ContextVar = contextvars.ContextVar("opcua_baglanti_ayari", default=None)


@contextlib.contextmanager
def ayar_ile(ayar):
    """Bu blokta yapilan tum baglantilar 'Add Server' ayarini kullanir: {politika, mod, kimlik('anonim'|'kullanici'), kullanici, parola, sertifika, anahtar, oturum_adi}.
    Ayar diske YAZILMAZ (parola yalniz istek suresince bellekte)."""
    belirte = _AYAR.set(ayar or None)
    try:
        yield
    finally:
        _AYAR.reset(belirte)


async def _istemci(adres: str, zaman_asimi: float):
    from asyncua import Client

    c = Client(adres, timeout=zaman_asimi)
    a = _AYAR.get() or {}
    if a.get("oturum_adi"):
        c.name = str(a["oturum_adi"])[:100]
    if a.get("kimlik") == "kullanici":
        c.set_user(str(a.get("kullanici") or ""))
        c.set_password(str(a.get("parola") or ""))
    politika, mod = a.get("politika") or "None", a.get("mod") or "None"
    if politika != "None" and mod != "None":
        if not a.get("sertifika") or not a.get("anahtar"):
            raise OpcUaHatasi("Guvenlik icin istemci sertifikasi ve ozel anahtar yolu gerekli")
        await c.set_security_string(f"{politika},{mod},{a['sertifika']},{a['anahtar']}")
    return c


def _calistir(adres: str, islev, zaman_asimi: float = 5.0):
    _gerek()

    async def is_():
        try:
            async with await _istemci(adres, zaman_asimi) as istemci:
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


def goz(adres: str, kimlik=None, en_cok: int = 300) -> list:
    """Tek seviye gezinme (UaExpert 'Address Space' gibi tembel agac): kimlik yoksa Root. [{kimlik, ad, sinif, cocuk}]"""
    async def is_(c):
        sonuc = []
        for ch in (await c.get_node(kimlik or "i=84").get_children())[:en_cok]:
            ad = (await ch.read_browse_name()).Name
            sinif = (await ch.read_node_class()).name
            sonuc.append({"kimlik": ch.nodeid.to_string(), "ad": ad, "sinif": sinif, "cocuk": sinif not in ("Variable", "Method")})
        return sonuc

    return _calistir(adres, is_)


def ozellik(adres: str, kimlik: str) -> dict:
    """Secili dugumun oznitelikleri ve referanslari (UaExpert 'Attributes' / 'References'). Yalniz okur."""
    async def is_(c):
        n = c.get_node(kimlik)
        liste: list = []

        async def ekle(ad, islev):
            try:
                liste.append([ad, _deger(await islev())])
            except Exception:  # dugumde olmayan oznitelik atlanir
                pass

        sinif = (await n.read_node_class()).name
        liste.append(["NodeId", kimlik])
        liste.append(["NodeClass", sinif])
        await ekle("BrowseName", lambda: _ad(n.read_browse_name()))
        await ekle("DisplayName", lambda: _metin(n.read_display_name()))
        await ekle("Description", lambda: _metin(n.read_description()))
        if sinif == "Variable":
            try:
                dv = await n.read_data_value()
                liste.append(["Value", _deger(dv.Value.Value)])
                liste.append(["StatusCode", str(dv.StatusCode)])
                liste.append(["SourceTimestamp", str(dv.SourceTimestamp)])
                liste.append(["ServerTimestamp", str(dv.ServerTimestamp)])
            except Exception:
                pass
            await ekle("DataType", lambda: _tip(n))
            await ekle("ValueRank", n.read_value_rank)
            await ekle("AccessLevel", lambda: _erisim(n))
        refler = []
        try:
            adlar: dict = {}
            for r in (await n.get_references())[:60]:
                tid = r.ReferenceTypeId.to_string()
                if tid not in adlar:
                    try:
                        adlar[tid] = (await c.get_node(r.ReferenceTypeId).read_display_name()).Text
                    except Exception:
                        adlar[tid] = tid
                refler.append({"tur": adlar[tid], "hedef": r.DisplayName.Text, "ileri": bool(r.IsForward)})
        except Exception:
            pass
        return {"ozellikler": liste, "referanslar": refler}

    return _calistir(adres, is_)


async def _ad(korutin):
    return (await korutin).Name


async def _metin(korutin):
    return (await korutin).Text


async def _tip(n):
    return (await n.read_data_type_as_variant_type()).name


async def _erisim(n):
    return ", ".join(sorted(a.name for a in await n.get_access_level()))


def degerler(adres: str, kimlikler: list[str]) -> list:
    """Veri erisim gorunumu: her dugum icin guncel deger/durum/zaman. Tek dugumdeki hata digerlerini etkilemez."""
    async def is_(c):
        sonuc = []
        for k in kimlikler:
            try:
                dv = await c.get_node(k).read_data_value()
                sonuc.append({"kimlik": k, "deger": _deger(dv.Value.Value), "durum": str(dv.StatusCode), "zaman": str(dv.SourceTimestamp or dv.ServerTimestamp or "")})
            except Exception as h:
                sonuc.append({"kimlik": k, "deger": None, "durum": f"hata: {h}"[:80], "zaman": ""})
        return sonuc

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
