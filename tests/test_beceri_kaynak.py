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


@pytest.mark.parametrize("girdi,beklenen", [
    ("anthropics/skills", ("anthropics", "skills", "")),
    ("https://github.com/anthropics/skills", ("anthropics", "skills", "")),
    ("github.com/anthropics/skills.git", ("anthropics", "skills", "")),
    ("https://github.com/anthropics/skills/tree/main/skills", ("anthropics", "skills", "skills/")),
    ("https://www.github.com/anthropics/skills/?tab=readme#x", ("anthropics", "skills", "")),
])
def test_github_adresi_yapistirilabilir(girdi, beklenen):
    assert k.kaynak_coz(girdi) == beklenen


def test_baska_host_adresi_hala_reddedilir():
    for kotu in ("https://evil.example/anthropics/skills", "https://github.com.evil.example/a/b", "https://github.com/"):
        with pytest.raises(b.BeceriHatasi):
            k.kaynak_coz(kotu)


def test_yazim_hatasi_yalniz_onerilen_listeden_onerilir(monkeypatch):
    """Gercek durum: kullanici 'anthropic/skills' yazdi (GitHub organizasyonu 'anthropics'); bos liste yerine duzeltme onerilir."""
    def yok(url, azami):
        raise b.BeceriHatasi("Depo ya da dosya bulunamadi (ozel depo olabilir)")

    monkeypatch.setattr(k, "_al", yok)
    with pytest.raises(b.BeceriHatasi, match="Bunu mu demek istediniz: anthropics/skills"):
        k.listele("anthropic/skills")
    with pytest.raises(b.BeceriHatasi) as h:
        k.listele("bambaska/depo")  # ilgisiz ad: oneri yok, baska depoya gecilmez
    assert "Bunu mu demek" not in str(h.value)
    with pytest.raises(b.BeceriHatasi) as h:
        k.listele("anthropics/skills")  # dogru yazilmis ama yok: kendisini onermez
    assert "Bunu mu demek" not in str(h.value)


def test_arayuz_beceri_kaynagi_kendiliginden_listeler():
    from pathlib import Path

    html = (Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "web" / "index.html").read_text(encoding="utf-8")
    assert 'const ilkKaynak=ilk||"anthropics/skills"' in html and 'kaynak.value=ilkKaynak;listele()' in html and "Bunu mu demek istediniz" in html


def test_http_ucu_listeler_ve_onizler_gercek_hata_NameError_sorgu(monkeypatch, tmp_path):
    """Gercek hata: /api/beceri-kaynak ucu tanimsiz bir degisken ('sorgu') kullaniyordu; arayuzde 'NameError: name sorgu is not defined' cikiyor, hic beceri gelmiyordu."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent))
    import http.client

    from aktapokus_ai_studio.arayuz import ArayuzSunucusu, Uygulama

    agac = json.dumps({"tree": [{"path": "skills/frontend-design/SKILL.md", "type": "blob"}, {"path": "skills/frontend-design/x.py", "type": "blob"}]}).encode()
    skill = b"---\nname: frontend-design\ndescription: Guzel arayuz\n---\nGovde"

    def sahte(url, azami):
        return agac if "api.github.com" in url else skill

    monkeypatch.setattr(k, "_al", sahte)
    monkeypatch.setenv("AKTAPOKUS_PROJELER", str(tmp_path / "p.json"))
    app = Uygulama()
    sv = ArayuzSunucusu(app)
    sv.baslat()
    try:
        def get(yol):
            c = http.client.HTTPConnection("127.0.0.1", sv.port, timeout=10)
            c.request("GET", yol, headers={"X-Aktapokus-Token": app.token, "Host": f"127.0.0.1:{sv.port}"})
            r = c.getresponse()
            return r.status, json.loads(r.read())

        st, d = get("/api/beceri-kaynak?kaynak=anthropics/skills")
        assert st == 200 and [x["kimlik"] for x in d["beceriler"]] == ["frontend-design"]
        st, d = get("/api/beceri-kaynak/onizle?kaynak=anthropics/skills&yol=skills/frontend-design/SKILL.md")
        assert st == 200 and d["aciklama"] == "Guzel arayuz"
    finally:
        sv.kapat()
