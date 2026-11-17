"""Buyuk ve hassas dosyalari projenin .gitignore'una kendiliginden ekler (ve kullaniciya ne eklendigini soyler).

Neden: geri alma noktasi (git anlik goruntusu) modelden ONCE alinir. Klasorde 1 GB'lik ornek proje ya da sozlesme/fatura gibi
belgeler varsa ya gorev hic baslamiyordu (gercek durum: Machine Expert SampleProject + PacDrive belgeleri) ya da bu belgeler
geri alma kopyasina, oradan da Yayinla/push ile GitHub'a gidebiliyordu. Model bunu duzeltemez: hata ondan once olusur.

Kurallar:
- Yalniz IZLENMEYEN ve henuz dislanmamis dosyalara bakilir (git zaten izliyorsa .gitignore onu cikarmaz; dokunulmaz).
- Eklenenler .gitignore'da isaretli bir blokta durur; kullanici bir satiri silerse bir daha EKLENMEZ (`.aktapokus/disla.json`).
- Hassas belge tespiti ad tabanlidir (icerik okunmaz): yanlis pozitif olabilir, bu yuzden her ekleme nedeniyle bildirilir.
- Model dislanan dosyalari yine OKUYABILIR; yalniz geri alma kopyasina ve git'e girmezler.
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path

from .config import AYAR_KLASORU

BUYUK_KLASOR = 100 * 2**20  # bir klasor (ilk iki seviye) bu boyutu asarsa butun olarak dislanir
BUYUK_DOSYA = 50 * 2**20
AZAMI_EKLEME = 40  # tek seferde; gerisi bir sonraki gorevde
BLOK_BASI = "# >>> Aktapokus (otomatik): buyuk ve hassas dosyalar. Bir satiri silerseniz Aktapokus onu bir daha eklemez."
BLOK_SONU = "# <<< Aktapokus"
KAYIT = "disla.json"

BELGE_UZANTILARI = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".xlsm", ".ppt", ".pptx", ".odt", ".ods", ".rtf", ".msg", ".eml", ".zip", ".7z", ".rar")
# Turkce harfler katlanarak (s, c, g, i, o, u) aranir; sozcuk dosya adinin herhangi bir yerinde gecebilir
HASSAS_SOZCUKLER = (
    "sozlesme", "contract", "agreement", "nda", "gizli", "confidential", "teklif", "quotation", "fatura", "invoice",
    "maas", "bordro", "payroll", "salary", "kimlik", "pasaport", "passport", "iban", "dekont", "vergi", "tax",
    "dava", "avukat", "lawsuit", "kvkk", "gdpr", "personel", "ozluk", "fiyat listesi", "fiyatlistesi", "price list", "pricelist",
    "lisans anahtari", "license key", "musteri listesi", "customer list",
)
SIR_ONEKLERI = (".env", "id_rsa", "id_ed25519", ".npmrc", ".pypirc", "credentials")
SIR_UZANTILARI = (".pem", ".key", ".pfx", ".p12", ".keystore", ".jks")
SIR_ORNEKLERI = (".env.example", ".env.sample", ".env.template", ".env.dist")


def _katla(metin: str) -> str:
    metin = metin.lower().replace("ı", "i").replace("İ", "i")
    return "".join(c for c in unicodedata.normalize("NFKD", metin) if not unicodedata.combining(c))


def _hassas_nedeni(yol: str) -> str | None:
    ad = yol.rsplit("/", 1)[-1]
    k = ad.lower()
    if k in SIR_ORNEKLERI:
        return None
    if k.startswith(SIR_ONEKLERI) or k.endswith(SIR_UZANTILARI):
        return "gizli anahtar/parola dosyasi"
    if not k.endswith(BELGE_UZANTILARI):
        return None
    katli = _katla(ad).replace("_", " ").replace("-", " ").replace(".", " ")
    sade = katli.replace(" ", "")
    for s in HASSAS_SOZCUKLER:
        if (" " in s and s in katli) or (len(s) <= 4 and s in katli.split()) or (len(s) > 4 and s in sade):
            return f"hassas/ticari/yasal belge olabilir ('{s}')"
    return None


def _desen(yol: str, klasor_mu: bool) -> str:
    """Kokten baglanmis, ozel karakterleri kacirilmis .gitignore satiri."""
    kacik = "".join("\\" + c if c in "*?[]\\" else c for c in yol)
    if kacik.endswith(" "):
        kacik = kacik[:-1] + "\\ "
    return "/" + kacik + ("/" if klasor_mu else "")


def tara(dosyalar: list[str], boyut) -> list[dict]:
    """Izlenmeyen dosya listesinden dislanacaklar: [{desen, yol, neden, boyut}]. `boyut(yol) -> int` (bulunamazsa 0)."""
    boyutlar = {d: boyut(d) for d in dosyalar}
    gruplar: dict[str, int] = {}
    for d, b in boyutlar.items():
        parca = d.split("/")
        for derinlik in (1, 2):
            if len(parca) > derinlik:
                anahtar = "/".join(parca[:derinlik])
                gruplar[anahtar] = gruplar.get(anahtar, 0) + b
    secilen: list[dict] = []
    alinan: list[str] = []
    # Once 2. seviye (daha dar), sonra 1. seviye: 'docs/PacDrive' buyukse yalniz o dislanir; 'docs' ancak GERI KALANI da buyukse
    for anahtar, toplam in sorted(gruplar.items(), key=lambda x: (-x[0].count("/"), -x[1])):
        kalan = toplam - sum(gruplar[a] for a in alinan if a.startswith(anahtar + "/"))
        if kalan < BUYUK_KLASOR:
            continue
        alinan.append(anahtar)
        secilen.append({"desen": _desen(anahtar, True), "yol": anahtar + "/", "neden": "buyuk klasor", "boyut": toplam})
    # ayni ust klasorden iki ya da daha cok alt klasor secildiyse ust klasorun kendisi dislanir (SampleProject/a, SampleProject/b -> SampleProject/)
    for ust in {a.split("/")[0] for a in alinan if "/" in a}:
        if ust not in alinan and sum(1 for a in alinan if a.startswith(ust + "/")) >= 2:
            alinan.append(ust)
            secilen.append({"desen": _desen(ust, True), "yol": ust + "/", "neden": "buyuk klasor", "boyut": gruplar[ust]})
    # ust klasor secildiyse altindaki girdiler gereksiz
    secilen = [s for s in secilen if not any(s["yol"].startswith(a + "/") and s["yol"] != a + "/" for a in alinan if "/" not in a)]
    alinan = [s["yol"][:-1] for s in secilen]
    for d, b in sorted(boyutlar.items(), key=lambda x: -x[1]):
        if any(d.startswith(a + "/") for a in alinan):
            continue
        neden = "buyuk dosya" if b >= BUYUK_DOSYA else _hassas_nedeni(d)
        if neden:
            secilen.append({"desen": _desen(d, False), "yol": d, "neden": neden, "boyut": b})
    return secilen


def _kayit_yolu(klasor: Path) -> Path:
    return klasor / AYAR_KLASORU / KAYIT


def _onceki(klasor: Path) -> set[str]:
    try:
        v = json.loads(_kayit_yolu(klasor).read_text(encoding="utf-8"))
        return set(v.get("eklenen", [])) if isinstance(v, dict) else set()
    except (OSError, json.JSONDecodeError):
        return set()


def gitignore_ekle(klasor: Path, desenler: list[str]) -> None:
    yol = klasor / ".gitignore"
    try:
        metin = yol.read_text(encoding="utf-8")
    except FileNotFoundError:
        metin = ""
    nl = "\r\n" if "\r\n" in metin else "\n"
    satirlar = metin.splitlines()
    if BLOK_BASI in satirlar and BLOK_SONU in satirlar[satirlar.index(BLOK_BASI):]:
        i = satirlar.index(BLOK_SONU, satirlar.index(BLOK_BASI))
        satirlar[i:i] = desenler
    else:
        if satirlar and satirlar[-1].strip():
            satirlar.append("")
        satirlar += [BLOK_BASI, *desenler, BLOK_SONU]
    yol.write_text(nl.join(satirlar) + nl, encoding="utf-8")


def uygula(klasor: str | Path) -> list[dict]:
    """Taramayi yapar, YENI desenleri .gitignore'a ekler, eklenenleri dondurur. Hata olursa bos liste (gorevi durdurmaz)."""
    from . import snapshot

    klasor = Path(klasor)
    try:
        cikti = snapshot._git(klasor, "ls-files", "-o", "--exclude-standard", "-z", kontrol=False)
    except Exception:
        return []
    dosyalar = [d for d in cikti.split("\0") if d and not d.endswith("/") and not d.startswith(AYAR_KLASORU + "/")]

    def boyut(d: str) -> int:
        try:
            return (klasor / d).stat().st_size
        except OSError:
            return 0

    onceki = _onceki(klasor)
    yeni = [s for s in tara(dosyalar, boyut) if s["desen"] not in onceki][:AZAMI_EKLEME]
    if not yeni:
        return []
    try:
        gitignore_ekle(klasor, [s["desen"] for s in yeni])
        _kayit_yolu(klasor).parent.mkdir(parents=True, exist_ok=True)
        _kayit_yolu(klasor).write_text(json.dumps({"eklenen": sorted(onceki | {s["desen"] for s in yeni})}, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        return []
    return yeni


def bildirim(eklenen: list[dict]) -> str:
    def boyut(b: int) -> str:
        return f"{b / 2**30:.1f} GB" if b >= 2**30 else f"{b // 2**20} MB"

    parcalar = [f"{s['yol']} ({s['neden']}" + (f", {boyut(s['boyut'])}" if s["neden"].startswith("buyuk") else "") + ")" for s in eklenen[:8]]
    ek = f" ve {len(eklenen) - 8} dosya daha" if len(eklenen) > 8 else ""
    return (".gitignore'a eklendi (geri alma kopyasina ve GitHub'a girmez; model yine okuyabilir): " + "; ".join(parcalar) + ek
            + ". Istemediginiz satiri .gitignore'daki Aktapokus blogundan silin; bir daha eklenmez.")
