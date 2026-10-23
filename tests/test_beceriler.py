import pytest

from aktapokus_ajan import beceriler as b


def yeni(**kw):
    v = {"kimlik": "sunum-hazirla", "ad": "Sunum Hazirla", "aciklama": "Kisa sunum taslagi cikarir", "govde": "# Adimlar\n1. Konuyu sor\n2. Taslak yaz", "otomatik": True}
    v.update(kw)
    return b.olustur(**v)


def test_olustur_dosya_yazar_ve_okunur():
    yeni()
    yol = b.kok() / "sunum-hazirla" / "SKILL.md"
    assert yol.is_file()
    ham = yol.read_text(encoding="utf-8")
    assert ham.startswith('---\nname: "Sunum Hazirla"\ndescription: "Kisa sunum taslagi cikarir"\n---\n') and "autoinvoke" not in ham
    s = b.oku("sunum-hazirla")
    assert (s.ad, s.aciklama, s.otomatik) == ("Sunum Hazirla", "Kisa sunum taslagi cikarir", True) and s.govde.startswith("# Adimlar")


def test_otomatik_kapali_metadata_yazilir_ve_geri_okunur():
    yeni(otomatik=False)
    assert "opencode/autoinvoke: false" in (b.kok() / "sunum-hazirla" / "SKILL.md").read_text(encoding="utf-8")
    assert b.oku("sunum-hazirla").otomatik is False


def test_ozel_karakterler_ve_turkce_bozulmadan_gidip_gelir():
    yeni(ad='Tırnaklı "ad": çğş', aciklama="iki nokta: ve # diyez ve 'tek tirnak' \\ ters", govde="---\ngovdede cizgi\n---\nsonra")
    s = b.oku("sunum-hazirla")
    assert s.ad == 'Tırnaklı "ad": çğş' and s.aciklama == "iki nokta: ve # diyez ve 'tek tirnak' \\ ters"
    assert s.govde == "---\ngovdede cizgi\n---\nsonra"  # govdedeki '---' frontmatter sanilmaz


def test_guncelleme_ayni_kimligi_ezer_ve_listelenir():
    yeni()
    yeni(aciklama="degisti")
    liste = b.listele()
    assert [x.kimlik for x in liste] == ["sunum-hazirla"] and liste[0].aciklama == "degisti"


@pytest.mark.parametrize("kotu", ["", "../kacis", "..", "A-Buyuk", "bosluk var", "a/b", "a\\b", "-bas", "son-", "cift--tire", "x" * 65, None, 5])
def test_gecersiz_kimlik_reddedilir_ve_dosya_olusmaz(kotu):
    with pytest.raises(b.BeceriHatasi):
        yeni(kimlik=kotu)
    assert b.listele() == []
    assert not (b.kok().parent / "kacis").exists()


@pytest.mark.parametrize("alan,deger", [("aciklama", ""), ("aciklama", "iki\nsatir"), ("aciklama", "x" * 501), ("ad", "iki\nsatir"), ("govde", "   "), ("govde", "x" * (b.AZAMI_GOVDE + 1)), ("govde", 5)],
                         ids=["aciklama-bos", "aciklama-cok-satir", "aciklama-uzun", "ad-cok-satir", "govde-bos", "govde-uzun", "govde-sayi"])
def test_gecersiz_alanlar_reddedilir(alan, deger):
    with pytest.raises(b.BeceriHatasi):
        yeni(**{alan: deger})
    assert b.listele() == []


def test_ad_bos_ise_kimlik_kullanilir():
    yeni(ad="")
    assert b.oku("sunum-hazirla").ad == "sunum-hazirla"


def test_sil_dosyayi_ve_bos_klasoru_kaldirir():
    yeni()
    b.sil("sunum-hazirla")
    assert b.listele() == [] and not (b.kok() / "sunum-hazirla").exists()
    with pytest.raises(b.BeceriHatasi, match="bulunamadi"):
        b.sil("sunum-hazirla")


def test_sil_klasorde_baska_dosya_varsa_reddeder_ve_dokunmaz():
    yeni()
    (b.kok() / "sunum-hazirla" / "scripts").mkdir()
    (b.kok() / "sunum-hazirla" / "scripts" / "onemli.py").write_text("x")
    with pytest.raises(b.BeceriHatasi, match="baska dosyalar"):
        b.sil("sunum-hazirla")
    assert (b.kok() / "sunum-hazirla" / "SKILL.md").is_file() and (b.kok() / "sunum-hazirla" / "scripts" / "onemli.py").is_file()


def test_listele_yalniz_gecerli_klasorleri_alir_ve_elle_yazilmis_beceriyi_okur():
    yeni()
    (b.kok() / "elle-yazilan").mkdir()
    (b.kok() / "elle-yazilan" / "SKILL.md").write_text("---\nname: Elle\ndescription: elle yazildi\nmetadata:\n  opencode/autoinvoke: false\n---\nGovde", encoding="utf-8")
    (b.kok() / "Buyuk-Klasor").mkdir()
    (b.kok() / "Buyuk-Klasor" / "SKILL.md").write_text("x")
    (b.kok() / "dosya.txt").write_text("x")
    (b.kok() / "skilsiz").mkdir()
    liste = {x.kimlik: x for x in b.listele()}
    assert set(liste) == {"sunum-hazirla", "elle-yazilan"}
    assert liste["elle-yazilan"].ad == "Elle" and liste["elle-yazilan"].otomatik is False and liste["elle-yazilan"].govde == "Govde"


def test_frontmattersiz_dosya_kimligi_ad_olarak_kullanir():
    (b.kok() / "duz").mkdir(parents=True)
    (b.kok() / "duz" / "SKILL.md").write_text("Yalniz govde", encoding="utf-8")
    s = b.oku("duz")
    assert (s.ad, s.aciklama, s.govde) == ("duz", "", "Yalniz govde")


def test_beceri_sayisi_siniri(monkeypatch):
    monkeypatch.setattr(b, "AZAMI_BECERI", 5)  # 200 dosya yazmak yavas; sinir mantigi ayni
    for i in range(b.AZAMI_BECERI):
        yeni(kimlik=f"b{i}")
    with pytest.raises(b.BeceriHatasi, match="En cok"):
        yeni(kimlik="fazla")
    yeni(kimlik="b0", aciklama="guncelleme sinira takilmaz")
