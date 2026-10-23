"""Motor (ajan CLI) denetimi: bu bilgisayarda hangi kod ajani CLI'lari kurulu, yeni projelerin varsayilan rolleri hangisiyle kurulsun,
mevcut projede kurulu olmayan bir CLI'a bagli roller hangisine gecirilebilir.

Neden: varsayilan roller OpenCode'u kullanir; OpenCode kurulu olmayan (ama Claude Code ya da Codex kurulu olan) bir bilgisayarda ilk gorev
hataya dusmesin. Hicbir sey kendiliginden DEGISTIRILMEZ: yalniz YENI olusturulan proje ayari kurulu motora gore uretilir; mevcut projede
roller yalniz kullanici dugmeye basinca gecirilir. Hicbir alt surec baslatilmaz (yalniz dosya/PATH aramasi)."""

from __future__ import annotations

import copy
import os

from .config import VARSAYILAN_AYAR, VARSAYILAN_MODEL
from .runners import claude_bul, codex_bul, opencode_bul

TERCIH_ORTAMI = "AKTAPOKUS_MOTOR_TERCIH"  # testler/ileri kullanim: varsayilan motoru zorla (kurulu olup olmadigina bakmaz)

MOTORLAR = (
    {"ad": "opencode-sunucu", "gorunen": "OpenCode", "kurulum": "https://opencode.ai (masaustu uygulamasi ya da: npm install -g opencode-ai)", "modeller": {"kodcu": VARSAYILAN_MODEL, "test": VARSAYILAN_MODEL}},
    {"ad": "claude", "gorunen": "Claude Code", "kurulum": "npm install -g @anthropic-ai/claude-code  (sonra terminalde bir kez 'claude' yazip giris yapin)", "modeller": {"kodcu": "sonnet", "test": "haiku"}},
    {"ad": "codex", "gorunen": "Codex", "kurulum": "npm install -g @openai/codex  (sonra terminalde 'codex login')", "modeller": {}},
)
_BULUCULAR = {
    "opencode-sunucu": lambda: opencode_bul(),
    "opencode": lambda: opencode_bul(),
    "claude": lambda: claude_bul(),
    "codex": lambda: codex_bul(),
}


def kurulu_mu(calistirici: str) -> bool:
    """Yerlesik CLI'lar icin PATH/arac yolu; ozel (tanimli) CLI'lar icin programin dosya olarak var olmasi. Bilinmeyen ad: False."""
    bul = _BULUCULAR.get(calistirici)
    if bul is not None:
        return bool(bul())
    from . import clitanim

    t = clitanim.yukle().get(calistirici)
    return bool(t and os.path.isfile(t.komut[0]))


def durum() -> list[dict]:
    return [{"ad": m["ad"], "gorunen": m["gorunen"], "kurulu": kurulu_mu(m["ad"]), "kurulum": m["kurulum"]} for m in MOTORLAR]


def tercih() -> str | None:
    """Yeni projelerin varsayilan motoru: ortam degiskeni, yoksa kurulu olanlardan ilki (OpenCode > Claude Code > Codex); hicbiri yoksa None."""
    zorla = os.environ.get(TERCIH_ORTAMI)
    if zorla:
        return zorla
    return next((m["ad"] for m in MOTORLAR if kurulu_mu(m["ad"])), None)


def _motor(ad: str | None) -> dict | None:
    return next((m for m in MOTORLAR if m["ad"] == ad), None)


def ayar_uret(motor: str | None) -> dict:
    """Yeni proje icin roller.json icerigi. OpenCode (ya da motor yoksa) -> eski varsayilan; Claude Code/Codex -> roller o motorla."""
    ayar = copy.deepcopy(VARSAYILAN_AYAR)
    m = _motor(motor)
    if m is None or m["ad"] == "opencode-sunucu":
        return ayar
    for rol, r in ayar["roller"].items():
        r["calistirici"] = m["ad"]
        model = m["modeller"].get(rol)
        if model:
            r["model"] = model
        else:
            r.pop("model", None)
    return ayar


def eksik_roller(ayar: dict) -> list[dict]:
    """Ayardaki rollerden, calistiricisi bu bilgisayarda KURULU olmayanlar: [{rol, calistirici}]."""
    roller = ayar.get("roller") if isinstance(ayar, dict) else None
    if not isinstance(roller, dict):
        return []
    return [{"rol": ad, "calistirici": r.get("calistirici")} for ad, r in roller.items() if isinstance(r, dict) and not kurulu_mu(str(r.get("calistirici")))]


def rolleri_gecir(ayar: dict, motor: str) -> tuple[dict, list[str]]:
    """Kurulu olmayan CLI'a bagli rolleri `motor`a gecirir (kurulu CLI'a bagli roller ve kullanicinin diger ayarlari AYNEN kalir).
    Doner: (yeni ayar, degisen rol adlari). Gecersiz motor/kurulu degilse ValueError."""
    m = _motor(motor)
    if m is None or not kurulu_mu(m["ad"]):
        raise ValueError("Bu motor kurulu degil ya da desteklenmiyor")
    yeni = copy.deepcopy(ayar)
    degisen = []
    for rol in (e["rol"] for e in eksik_roller(ayar)):
        r = yeni["roller"][rol]
        r["calistirici"] = m["ad"]
        model = m["modeller"].get(rol) or m["modeller"].get("kodcu")
        if model:
            r["model"] = model
        else:
            r.pop("model", None)
        degisen.append(rol)
    return yeni, degisen
