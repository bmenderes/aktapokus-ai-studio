"""Beceriler (skills): `~/.agents/skills/<id>/SKILL.md` altinda sizin olusturdugunuz, OpenCode'un (ve uyumlu araclarin) bulup modele sundugu
Markdown talimatlari. Burada yalniz BU klasor yazilir/silinir; OpenCode'un baska yerlerden (ornegin ~/.claude/skills, proje icindeki
.opencode/skills) buldugu beceriler listelenir ama DEGISTIRILMEZ.

Guvenlik: kimlik kucuk-harf-kebab (yol gezintisi imkansiz), tek satirlik ad/aciklama, govde en cok 100 KB; silme yalniz klasorde baska dosya
yoksa yapilir (scripts/ referanslar gibi kullanici dosyalari sessizce silinmez)."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

KOK_ORTAMI = "AKTAPOKUS_BECERILER"
ID_DESENI = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
AZAMI_ID = 64
AZAMI_GOVDE = 100_000
AZAMI_BECERI = 200


class BeceriHatasi(Exception):
    pass


@dataclass(frozen=True)
class Beceri:
    kimlik: str
    ad: str
    aciklama: str
    govde: str
    otomatik: bool = True  # False: modelin listesinde gorunmez (yine de @kimlik ile cagrilabilir)

    def ozet(self) -> dict:
        return {"kimlik": self.kimlik, "ad": self.ad, "aciklama": self.aciklama, "otomatik": self.otomatik}


def kok() -> Path:
    ortam = os.environ.get(KOK_ORTAMI)
    return Path(ortam) if ortam else Path.home() / ".agents" / "skills"


def _beceri_yolu(kimlik: object) -> Path:
    if not isinstance(kimlik, str) or len(kimlik) > AZAMI_ID or not ID_DESENI.match(kimlik):
        raise BeceriHatasi("Kimlik kucuk harf/rakam ve tire icermeli (ornek: sunum-hazirla), en cok 64 karakter")
    return kok() / kimlik / "SKILL.md"


def _tek_satir(deger: object, ad: str, azami: int, bos_olabilir: bool = False) -> str:
    if not isinstance(deger, str):
        raise BeceriHatasi(f"'{ad}' metin olmali")
    d = deger.strip()
    if (not d and not bos_olabilir) or len(d) > azami or "\n" in d or "\r" in d or "\x00" in d:
        raise BeceriHatasi(f"'{ad}' tek satirlik, bos olmayan metin olmali (en cok {azami} karakter)")
    return d


def bicimle(b: Beceri) -> str:
    """SKILL.md icerigi. Degerler JSON dizgesi olarak yazilir (gecerli YAML cift tirnakli dizge)."""
    on = ["---", f"name: {json.dumps(b.ad, ensure_ascii=False)}", f"description: {json.dumps(b.aciklama, ensure_ascii=False)}"]
    if not b.otomatik:
        on += ["metadata:", "  opencode/autoinvoke: false"]
    on.append("---")
    return "\n".join(on) + "\n\n" + b.govde.strip("\n") + "\n"


def _yaml_deger(ham: str) -> str:
    ham = ham.strip()
    if len(ham) >= 2 and ham[0] == ham[-1] and ham[0] in "\"'":
        if ham[0] == '"':
            try:
                return json.loads(ham)
            except json.JSONDecodeError:
                pass
        return ham[1:-1]
    return ham


def coz(kimlik: str, metin: str) -> Beceri:
    """SKILL.md'yi okur (kucuk, tolerant YAML: ad, aciklama, metadata.opencode/autoinvoke)."""
    ad, aciklama, otomatik, govde = kimlik, "", True, metin
    if metin.startswith("---"):
        parcalar = metin.split("\n---", 1)
        if len(parcalar) == 2:
            on, govde = parcalar[0][3:], parcalar[1].lstrip("-").lstrip("\r\n")
            for satir in on.splitlines():
                m = re.match(r"^\s*([A-Za-z0-9_/.-]+)\s*:\s*(.*)$", satir)
                if not m:
                    continue
                anahtar, deger = m.group(1), _yaml_deger(m.group(2))
                if anahtar == "name" and deger:
                    ad = deger
                elif anahtar == "description":
                    aciklama = deger
                elif anahtar in ("opencode/autoinvoke",) and deger.lower() == "false":
                    otomatik = False
                elif anahtar == "disable-model-invocation" and deger.lower() == "true":
                    otomatik = False
    return Beceri(kimlik, ad, aciklama, govde.strip("\n"), otomatik)


def olustur(kimlik: object, ad: object, aciklama: object, govde: object, otomatik: object = True) -> Beceri:
    yol = _beceri_yolu(kimlik)
    if not isinstance(govde, str) or len(govde) > AZAMI_GOVDE or "\x00" in govde:
        raise BeceriHatasi(f"'govde' metin olmali (en cok {AZAMI_GOVDE} karakter)")
    b = Beceri(
        kimlik=str(kimlik), ad=_tek_satir(ad if ad not in (None, "") else kimlik, "ad", 120),
        aciklama=_tek_satir(aciklama, "aciklama", 500), govde=govde, otomatik=bool(otomatik),
    )
    if not b.govde.strip():
        raise BeceriHatasi("Becerinin icerigi (talimatlar) bos olamaz")
    if not yol.exists() and len(listele()) >= AZAMI_BECERI:
        raise BeceriHatasi(f"En cok {AZAMI_BECERI} beceri tutulur")
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_suffix(".tmp")
    gecici.write_text(bicimle(b), encoding="utf-8")
    os.replace(gecici, yol)
    return b


def listele() -> list[Beceri]:
    k = kok()
    sonuc: list[Beceri] = []
    if not k.is_dir():
        return sonuc
    for d in sorted(k.iterdir(), key=lambda p: p.name):
        f = d / "SKILL.md"
        if d.is_dir() and ID_DESENI.match(d.name) and f.is_file():
            try:
                sonuc.append(coz(d.name, f.read_text(encoding="utf-8")))
            except (OSError, UnicodeDecodeError):
                continue
    return sonuc


def oku(kimlik: object) -> Beceri:
    yol = _beceri_yolu(kimlik)
    try:
        return coz(str(kimlik), yol.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        raise BeceriHatasi("Beceri bulunamadi") from None


def sil(kimlik: object) -> None:
    yol = _beceri_yolu(kimlik)
    if not yol.is_file():
        raise BeceriHatasi("Beceri bulunamadi")
    diger = [p.name for p in yol.parent.iterdir() if p.name != "SKILL.md"]
    if diger:
        raise BeceriHatasi(f"Klasorde baska dosyalar var ({', '.join(diger[:3])}); sessizce silinmez, elle silin: {yol.parent}")
    yol.unlink()
    yol.parent.rmdir()
