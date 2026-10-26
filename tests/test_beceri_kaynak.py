"""Cevrimici beceri kaynagi: ag SAHTE (`_al` degistirilir); gercek internete cikilmaz."""

import json

import pytest

from aktapokus_ai_studio import beceri_kaynak as k
from aktapokus_ai_studio import beceriler as b

AGAC = {"tree": [
    {"path": "skills/pdf/SKILL.md", "type": "blob"},
    {"path": "skills/pdf/scripts/a.py", "type": "blob"},
    {"path": "skills/not-defteri/SKILL.md", "type": "blob"},
    {"path": "skills/Buyuk_Harf/SKILL.md", "type": "blob"},  # gecersiz kimlik: listelenmez
    {"path": "README.md", "type": "blob"},
]}
SKILL = '---\nname: "PDF"\ndescription: "PDF isler"\n---\n\n# Adimlar\n1. Oku\n'


@pytest.fixture
def ag(monkeypatch):
    istekler = []

    def sahte(url, azami):
        istekler.append(url)
        if "git/trees" in url:
            return json.dumps(AGAC).encode()
        return SKILL.encode()

    monkeypatch.setattr(k, "_al", sahte)
    return istekler


def test_listele_gecerli_becerileri_ve_ek_dosyayi_gosterir(ag):
    d = k.listele("anthropics/skills")
    assert [s["kimlik"] for s in d["beceriler"]] == ["not-defteri", "pdf"]
    assert {s["kimlik"]: s["ek_dosya"] for s in d["beceriler"]} == {"not-defteri": False, "pdf": True}


@pytest.mark.parametrize("kaynak", ["", "tek", "a/b/../c", "https://evil.com/x", "a b/c", None, "a/b/c/d/e/f/g/h/i"])
def test_gecersiz_kaynak_reddedilir(kaynak):
    with pytest.raises(b.BeceriHatasi):
        k.kaynak_coz(kaynak)


def test_indir_yazar_ve_ikinci_kez_onaysiz_reddeder(ag):
    s = k.indir("anthropics/skills", "skills/pdf/SKILL.md")
    assert s["kimlik"] == "pdf" and (b.kok() / "pdf" / "SKILL.md").is_file()
    assert any(u.startswith("https://raw.githubusercontent.com/anthropics/skills/HEAD/") for u in ag)
    with pytest.raises(b.BeceriHatasi, match="zaten kurulu"):
        k.indir("anthropics/skills", "skills/pdf/SKILL.md")
    k.indir("anthropics/skills", "skills/pdf/SKILL.md", True)


@pytest.mark.parametrize("yol", ["../x/SKILL.md", "skills/pdf/README.md", "skills/PDF/SKILL.md", "/etc/passwd", None])
def test_gecersiz_yol_reddedilir(ag, yol):
    with pytest.raises(b.BeceriHatasi):
        k.getir("anthropics/skills", yol)


def test_aciklamasiz_beceri_indirilmez(monkeypatch):
    monkeypatch.setattr(k, "_al", lambda u, a: b"# yalniz govde")
    with pytest.raises(b.BeceriHatasi, match="aciklamasi yok"):
        k.indir("a/b", "x/SKILL.md")


def test_baska_host_reddedilir():
    with pytest.raises(b.BeceriHatasi, match="GitHub"):
        k._al("https://evil.example/x", 10)
    with pytest.raises(b.BeceriHatasi, match="GitHub"):
        k._al("http://api.github.com/x", 10)
