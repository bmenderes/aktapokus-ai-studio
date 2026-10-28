"""Onerilenler listesi: bicim, benzersizlik, Ingilizce karsiliklar, API ve arayuz baglantisi."""

import json
from pathlib import Path

from aktapokus_ai_studio import beceri_kaynak, oneriler
from test_otomasyon import api  # noqa: F401  (api: pytest fixture'i)

WEB = Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "web"


def _hepsi():
    return [(k, o) for k, ogeler in oneriler.KATEGORILER for o in ogeler]


def test_liste_bicimi_gecerli_depolar_benzersiz_ve_beklenen_girisler_var():
    ogeler = [o for _, o in _hepsi()]
    depolar = [o[1] for o in ogeler]
    assert len(depolar) == len({d.lower() for d in depolar}) and len({o[0] for o in ogeler}) == len(ogeler)
    for ad, depo, tur, yildiz, aciklama in ogeler:
        assert beceri_kaynak.KAYNAK_DESENI.fullmatch(depo) and ".." not in depo, depo  # arayuz bu adresi aciyor / kaynak olarak veriyor
        assert tur in oneriler.TURLER and isinstance(yildiz, int) and yildiz >= 0 and 0 < len(aciklama) <= 70 and ad.strip() == ad
    adlar = {o[0] for o in ogeler}
    for beklenen in ("Superpowers", "Graphify", "Claude-Mem", "gstack", "Skills (Anthropic)", "Voicebox", "PPT Master", "Caveman", "REA"):
        assert beklenen in adlar, beklenen
    assert len(ogeler) >= 31 and next(o for o in ogeler if o[0] == "Voicebox")[1] == "jamiepine/voicebox"
    assert {o[1] for o in ogeler if o[2] == "arac"} >= {"Graphify-Labs/graphify", "headroomlabs-ai/headroom", "gsd-build/get-shit-done"}  # SKILL.md'si olmayanlar yalniz baglanti


def test_her_metnin_ingilizce_karsiligi_var():
    tam = json.loads((WEB / "diller" / "en.json").read_text(encoding="utf-8"))["tam"]
    for kategori, ogeler in oneriler.KATEGORILER:
        assert kategori in tam, kategori
        for o in ogeler:
            assert o[4] in tam, o[4]


def test_api_listeyi_verir_belirtec_ister(api):
    app, sv, istek, proje, ikinci, sayac = api
    assert istek("GET", "/api/oneriler", None, token=None)[0] == 401
    st, d = istek("GET", "/api/oneriler")
    assert st == 200 and [k["ad"] for k in d["kategoriler"]][0] == "Kıdemli gibi kod yaz" and len(d["kategoriler"]) == len(oneriler.KATEGORILER)
    o = next(x for k in d["kategoriler"] for x in k["ogeler"] if x["ad"] == "Voicebox")
    assert o["url"] == "https://github.com/jamiepine/voicebox" and o["tur"] == "uygulama"
    assert all(x["url"].startswith("https://github.com/") for k in d["kategoriler"] for x in k["ogeler"])


def test_arayuz_onerilenler_sekmesi_baglidir_ve_mevcut_kaynak_akisini_kullanir():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert '["onerilenler","Önerilenler"]' in html and "async function onerilenlerBolumu(h)" in html and '"/api/oneriler"' in html
    assert "beceriKaynakFormu(form,()=>{},x.depo)" in html and "function beceriKaynakFormu(kap,bitti,ilk)" in html  # kurulum: listele > onizle > onayla > indir
    assert "ghUrlGuvenli(x.url)" in html and 'noopener,noreferrer' in html
