"""Proje yapilandirmasi: roller, akis, butce. Dosya: <klasor>/.aktapokus/roller.json"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

AYAR_KLASORU = ".aktapokus"
ROLLER_DOSYASI = "roller.json"
BILINEN_CALISTIRICILAR = ("opencode", "opencode-sunucu", "claude", "codex")
# Anlik goruntuye girmeyen ve git'e (yerel exclude ile) eklenmeyen yollar
SNAPSHOT_DISI = (AYAR_KLASORU, ".opencode/opencode.json")
VARSAYILAN_MODEL = "opencode/deepseek-v4.1-flash-free"

KODCU_TALIMATI = (
    "Sen kodcusun. Gorevi yerine getirmek icin calisma klasorundeki dosyalari oku ve gerekli "
    "degisiklikleri yap. Yalnizca gerekeni degistir, kucuk ve odakli kal. Bitince yaptigin "
    "degisiklikleri kisaca ozetle."
)
TEST_TALIMATI = (
    "Sen test uzmanisin. Dosyalari DEGISTIRME. Yapilan degisikligi incele; projenin testleri "
    "varsa calistir, yoksa degisikligin gorevi karsilayip karsilamadigini dosyalari okuyarak "
    "denetle. Bulgulari kisaca yaz. Son satirda tam olarak su ikisinden birini yaz: "
    "'SONUC: BASARILI' veya 'SONUC: BASARISIZ'."
)

VARSAYILAN_AYAR: dict = {
    "surum": 1,
    "akis": ["kodcu", "test"],
    "azami_duzeltme": 2,
    "butce_token": 200000,
    "zaman_asimi_sn": 900,
    "baglam": True,
    "roller": {
        "kodcu": {
            "calistirici": "opencode-sunucu",
            "model": VARSAYILAN_MODEL,
            "talimat": KODCU_TALIMATI,
        },
        "test": {
            "calistirici": "opencode-sunucu",
            "model": VARSAYILAN_MODEL,
            "talimat": TEST_TALIMATI,
            "dogrulama": True,
        },
    },
}


class AyarHatasi(Exception):
    pass


@dataclass(frozen=True)
class Rol:
    ad: str
    calistirici: str
    model: str | None
    talimat: str
    agent: str | None = None
    dogrulama: bool = False
    okuma_riski_kabul: bool = False  # koruyucusu olmayan CLI'lar (Codex...) .env gibi gizli dosyalari OKUYABILIR; kullanici bilerek kabul ederse True


@dataclass(frozen=True)
class Ayar:
    akis: tuple[str, ...]
    roller: dict[str, Rol]
    azami_duzeltme: int
    butce_token: int
    zaman_asimi_sn: int
    baglam: bool = True  # ortak baglam dosyalari (AGENTS.md blogu, DURUM.md) calistirmadan once guncellensin mi

    def rol_sirasi(self) -> list[Rol]:
        return [self.roller[ad] for ad in self.akis]


def ayar_yolu(klasor: str | Path) -> Path:
    return Path(klasor) / AYAR_KLASORU / ROLLER_DOSYASI


def _tam_sayi(veri: dict, ad: str, alt: int, ust: int) -> int:
    deger = veri.get(ad)
    if isinstance(deger, bool) or not isinstance(deger, int) or not alt <= deger <= ust:
        raise AyarHatasi(f"'{ad}' {alt} ile {ust} arasinda bir tam sayi olmali (bulunan: {deger!r})")
    return deger


def ayar_coz(veri: object) -> Ayar:
    if not isinstance(veri, dict):
        raise AyarHatasi("Ayar dosyasinin kokunde bir nesne olmali")
    ham_roller = veri.get("roller")
    if not isinstance(ham_roller, dict) or not ham_roller:
        raise AyarHatasi("'roller' bos olmayan bir nesne olmali")
    roller: dict[str, Rol] = {}
    for ad, r in ham_roller.items():
        if not isinstance(r, dict):
            raise AyarHatasi(f"Rol '{ad}' bir nesne olmali")
        calistirici = r.get("calistirici")
        if calistirici not in BILINEN_CALISTIRICILAR:
            from . import clitanim  # tanimla eklenen CLI'lar da gecerli (dairesel ice aktarmayi onlemek icin tembel)

            olabilecekler = clitanim.bilinen_adlar()
            if calistirici not in olabilecekler:
                raise AyarHatasi(f"Rol '{ad}': bilinmeyen calistirici {calistirici!r} (olabilecekler: {', '.join(olabilecekler)})")
        model = r.get("model")
        if model is not None and (not isinstance(model, str) or not model.strip()):
            raise AyarHatasi(f"Rol '{ad}': 'model' bos olmayan metin ya da null olmali")
        talimat = r.get("talimat")
        if not isinstance(talimat, str) or not talimat.strip():
            raise AyarHatasi(f"Rol '{ad}': 'talimat' bos olmayan metin olmali")
        agent = r.get("agent")
        if agent is not None and (not isinstance(agent, str) or not agent.strip()):
            raise AyarHatasi(f"Rol '{ad}': 'agent' bos olmayan metin ya da null olmali")
        dogrulama = r.get("dogrulama", False)
        if not isinstance(dogrulama, bool):
            raise AyarHatasi(f"Rol '{ad}': 'dogrulama' true/false olmali")
        risk = r.get("okuma_riski_kabul", False)
        if not isinstance(risk, bool):
            raise AyarHatasi(f"Rol '{ad}': 'okuma_riski_kabul' true/false olmali")
        roller[ad] = Rol(ad, calistirici, model, talimat, agent, dogrulama, risk)
    akis = veri.get("akis")
    if not isinstance(akis, list) or not akis or not all(isinstance(a, str) for a in akis):
        raise AyarHatasi("'akis' rol adlarindan olusan bos olmayan bir liste olmali")
    for a in akis:
        if a not in roller:
            raise AyarHatasi(f"'akis' icindeki rol '{a}' 'roller' icinde tanimli degil")
    if roller[akis[0]].dogrulama:
        raise AyarHatasi("Akisin ilk rolu dogrulama rolu olamaz (duzeltecek bir onceki adim yok)")
    baglam = veri.get("baglam", True)
    if not isinstance(baglam, bool):
        raise AyarHatasi("'baglam' true/false olmali")
    return Ayar(
        akis=tuple(akis),
        roller=roller,
        azami_duzeltme=_tam_sayi(veri, "azami_duzeltme", 0, 10),
        butce_token=_tam_sayi(veri, "butce_token", 1, 100_000_000),
        zaman_asimi_sn=_tam_sayi(veri, "zaman_asimi_sn", 10, 7200),
        baglam=baglam,
    )


def ayar_yukle(klasor: str | Path) -> Ayar:
    yol = ayar_yolu(klasor)
    if not yol.is_file():
        raise AyarHatasi(f"Ayar dosyasi yok: {yol}. Once 'aktapokus ac <klasor>' calistirin.")
    try:
        veri = json.loads(yol.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as hata:
        raise AyarHatasi(f"Ayar dosyasi okunamadi ({yol}): {hata}") from hata
    return ayar_coz(veri)
