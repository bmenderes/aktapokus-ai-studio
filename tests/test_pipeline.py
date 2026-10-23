import copy
import json

import pytest

from aktapokus_ajan.config import VARSAYILAN_AYAR, ayar_coz
from aktapokus_ajan.pipeline import (
    HatHatasi,
    calistir_hat,
    dogrulama_sonucu,
    geri_al,
    istem_olustur,
    son_kayit,
)
from aktapokus_ajan.config import Rol
from conftest import SahteCalistirici, sonuc


def ayar(**degisim):
    veri = copy.deepcopy(VARSAYILAN_AYAR)
    veri.update(degisim)
    return ayar_coz(veri)


def kodcu_yazar(icerik="yeni\n", dosya="c.txt"):
    def f(k, istem, n):
        (k / dosya).write_text(icerik, encoding="utf-8")
        return sonuc("yazildi")

    return f


def test_dogrulama_sonucu_okuma():
    assert dogrulama_sonucu("bulgular\nSONUC: BASARILI") is True
    assert dogrulama_sonucu("bulgular\nSONUÇ: BAŞARILI") is True
    assert dogrulama_sonucu("sonuc: basarisiz") is False
    assert dogrulama_sonucu("SONUC: BASARISIZ\nduzelttim\nSONUC: BASARILI") is True  # sonuncusu gecerli
    assert dogrulama_sonucu("SONUC: BASARILI\nama sonra\nSONUC: BASARISIZ") is False
    assert dogrulama_sonucu("sonuc yok") is None


def test_istem_icerigi_ve_kisaltma():
    rol = Rol("kodcu", "opencode", None, "Kod yaz.")
    i = istem_olustur(rol, "gorev X", "onceki cikti", None)
    assert "ROLUN: kodcu. Kod yaz." in i and "gorev X" in i and "onceki cikti" in i and "KURALLAR" in i
    i2 = istem_olustur(rol, "g", "o", "test bulgusu")
    assert "test bulgusu" in i2 and "ONCEKI ADIMIN CIKTISI" not in i2
    uzun = istem_olustur(rol, "g", "x" * 20000, None)
    assert len(uzun) < 8000 and "karakter atlandi" in uzun


def test_basarili_hat_onaylandi(proje):
    sahte = SahteCalistirici({"kodcu": kodcu_yazar(), "test": lambda k, i, n: sonuc("iyi\nSONUC: BASARILI")})
    sorular = []
    s = calistir_hat(proje, "c.txt ekle", ayar(), lambda ad: sahte, lambda q: sorular.append(q) or True)
    assert s.durum == "onaylandi" and s.korundu
    assert (proje / "c.txt").exists()
    assert s.degisen == {"c.txt": "A"} and "c.txt" in s.fark_ozeti
    assert [a.rol for a in s.adimlar] == ["kodcu", "test"] and s.adimlar[1].dogrulama == "basarili"
    assert s.token_toplam == 30 and len(sorular) == 1
    # ikinci rol, birinci rolun ciktisini goruyor
    assert "yazildi" in sahte.cagrilar[1][2]
    kayit = json.loads(s.kayit_yolu.read_text(encoding="utf-8"))
    assert kayit["durum"] == "onaylandi" and kayit["degisen"] == {"c.txt": "A"}


def test_red_edilirse_geri_alinir(proje):
    sahte = SahteCalistirici(
        {
            "kodcu": lambda k, i, n: ((k / "a.txt").write_text("bozuk", encoding="utf-8"), (k / "yeni.txt").write_text("x"), sonuc())[2],
            "test": lambda k, i, n: sonuc("SONUC: BASARILI"),
        }
    )
    s = calistir_hat(proje, "g", ayar(), lambda ad: sahte, lambda q: False)
    assert s.durum == "geri_alindi" and not s.korundu
    assert (proje / "a.txt").read_text(encoding="utf-8") == "bir\n"
    assert not (proje / "yeni.txt").exists()


def test_degisiklik_yoksa_soru_sorulmaz(proje):
    sahte = SahteCalistirici({"kodcu": lambda k, i, n: sonuc("bir sey yapmadim"), "test": lambda k, i, n: sonuc("SONUC: BASARILI")})
    sorular = []
    s = calistir_hat(proje, "g", ayar(), lambda ad: sahte, lambda q: sorular.append(q) or True)
    assert s.durum == "degisiklik_yok" and sorular == []
    assert "hicbir dosya degismedi" in s.mesaj.lower() and "disinda" in s.mesaj  # sessizce basari sanilmasin


def test_dogrulama_basarisiz_duzeltme_dongusu(proje):
    sayac = {"test": 0}

    def test_rolu(k, istem, n):
        sayac["test"] += 1
        return sonuc("hata var\nSONUC: BASARISIZ" if n == 1 else "duzeldi\nSONUC: BASARILI")

    def kodcu(k, istem, n):
        (k / "c.txt").write_text(f"deneme {n}\n", encoding="utf-8")
        return sonuc(f"deneme {n}")

    sahte = SahteCalistirici({"kodcu": kodcu, "test": test_rolu})
    s = calistir_hat(proje, "g", ayar(), lambda ad: sahte, lambda q: True)
    assert s.durum == "onaylandi"
    assert [a.rol for a in s.adimlar] == ["kodcu", "test", "kodcu", "test"]
    ikinci_kodcu_istemi = [c for c in sahte.cagrilar if c[0] == "kodcu"][1][2]
    assert "hata var" in ikinci_kodcu_istemi  # test bulgulari kodcuya iletildi
    assert (proje / "c.txt").read_text(encoding="utf-8") == "deneme 2\n"


def test_dogrulama_surekli_basarisiz_azami_duzeltmede_durur(proje):
    sahte = SahteCalistirici({"kodcu": kodcu_yazar(), "test": lambda k, i, n: sonuc("SONUC: BASARISIZ")})
    sorular = []
    s = calistir_hat(proje, "g", ayar(azami_duzeltme=1), lambda ad: sahte, lambda q: sorular.append(q) or False)
    assert s.durum == "dogrulama_basarisiz"
    assert len([a for a in s.adimlar if a.rol == "test"]) == 2  # ilk + 1 duzeltme
    assert "UYARI: dogrulama_basarisiz" in sorular[0]
    assert not (proje / "c.txt").exists()  # onaylanmadi, geri alindi


def test_dogrulama_belirsizse_dongu_yok_ama_uyari(proje):
    sahte = SahteCalistirici({"kodcu": kodcu_yazar(), "test": lambda k, i, n: sonuc("sonuc satiri yazmadim")})
    s = calistir_hat(proje, "g", ayar(), lambda ad: sahte, lambda q: True)
    assert s.durum == "onaylandi" and "belirsiz" in s.mesaj
    assert s.adimlar[1].dogrulama == "belirsiz" and len(s.adimlar) == 2


def test_butce_asilirsa_durur(proje):
    sahte = SahteCalistirici({"kodcu": lambda k, i, n: (kodcu_yazar()(k, i, n), sonuc("x", girdi=500, cikti=600))[1], "test": lambda k, i, n: sonuc("SONUC: BASARILI")})
    s = calistir_hat(proje, "g", ayar(butce_token=1000), lambda ad: sahte, lambda q: False)
    assert s.durum == "butce_asildi" and [a.rol for a in s.adimlar] == ["kodcu"]
    assert not (proje / "c.txt").exists()


def test_calistirici_hatasi_adimi_durdurur(proje):
    sahte = SahteCalistirici({"kodcu": lambda k, i, n: sonuc(ok=False, hata="model yok"), "test": lambda k, i, n: sonuc("SONUC: BASARILI")})
    s = calistir_hat(proje, "g", ayar(), lambda ad: sahte, lambda q: True)
    assert s.durum == "basarisiz" and "model yok" in s.mesaj and len(s.adimlar) == 1


def test_calistirici_istisnasi_yakalanir(proje):
    def uret(ad):
        raise RuntimeError("cli yok")

    s = calistir_hat(proje, "g", ayar(), uret, lambda q: True)
    assert s.durum == "basarisiz" and "RuntimeError: cli yok" in s.mesaj


def test_basarisiz_ama_degisiklik_varsa_kullaniciya_sorulur(proje):
    sahte = SahteCalistirici({"kodcu": lambda k, i, n: (kodcu_yazar()(k, i, n), sonuc(ok=False, hata="yarida kaldi"))[1], "test": lambda k, i, n: sonuc()})
    s = calistir_hat(proje, "g", ayar(), lambda ad: sahte, lambda q: True)
    assert s.durum == "basarisiz" and s.korundu and (proje / "c.txt").exists()


def test_roller_ayri_calistirici_ve_modelle_cagrilir(proje):
    veri = copy.deepcopy(VARSAYILAN_AYAR)
    veri["roller"]["kodcu"].update(calistirici="opencode", model="sonnet-benzeri")
    veri["roller"]["test"].update(calistirici="claude", model="opus-benzeri")
    kullanilan = []
    sahte = SahteCalistirici({"kodcu": kodcu_yazar(), "test": lambda k, i, n: sonuc("SONUC: BASARILI")})
    calistir_hat(proje, "g", ayar_coz(veri), lambda ad: (kullanilan.append(ad), sahte)[1], lambda q: True)
    assert kullanilan == ["opencode", "claude"]
    assert [(c[0], c[1]) for c in sahte.cagrilar] == [("kodcu", "sonnet-benzeri"), ("test", "opus-benzeri")]


def test_git_deposu_degilse_ve_bos_gorev_reddedilir(tmp_path):
    k = tmp_path / "d"
    k.mkdir()
    with pytest.raises(HatHatasi, match="git deposu degil"):
        calistir_hat(k, "g", ayar(), lambda ad: None, lambda q: True)
    with pytest.raises(HatHatasi, match="bos"):
        calistir_hat(k, "  ", ayar(), lambda ad: None, lambda q: True)


def test_geri_al_son_calistirmayi_geri_alir(proje):
    sahte = SahteCalistirici({"kodcu": kodcu_yazar(), "test": lambda k, i, n: sonuc("SONUC: BASARILI")})
    calistir_hat(proje, "g", ayar(), lambda ad: sahte, lambda q: True)
    assert (proje / "c.txt").exists()
    mesajlar = []
    assert geri_al(proje, lambda q: True, mesajlar.append) == 1
    assert not (proje / "c.txt").exists()
    assert any("c.txt" in m for m in mesajlar)
    assert son_kayit(proje)["geri_alindi_sonradan"] is True
    with pytest.raises(HatHatasi, match="zaten geri alinmis"):
        geri_al(proje, lambda q: True)


def test_geri_al_onay_verilmezse_dokunmaz(proje):
    sahte = SahteCalistirici({"kodcu": kodcu_yazar(), "test": lambda k, i, n: sonuc("SONUC: BASARILI")})
    calistir_hat(proje, "g", ayar(), lambda ad: sahte, lambda q: True)
    assert geri_al(proje, lambda q: False) == 0
    assert (proje / "c.txt").exists()
    assert son_kayit(proje)["geri_alindi_sonradan"] is False


def test_geri_al_kayit_yoksa_ve_zaten_geri_alinmissa(proje):
    with pytest.raises(HatHatasi, match="kaydi yok"):
        geri_al(proje, lambda q: True)
    sahte = SahteCalistirici({"kodcu": kodcu_yazar(), "test": lambda k, i, n: sonuc("SONUC: BASARILI")})
    calistir_hat(proje, "g", ayar(), lambda ad: sahte, lambda q: False)  # reddedildi -> geri_alindi
    with pytest.raises(HatHatasi, match="zaten geri alinmis"):
        geri_al(proje, lambda q: True)


def test_kayit_kimlikleri_ayni_saniyede_bile_olusturma_sirasiyla_siralanir():
    """GERCEK HATA: kimlik saniye cozunurlukluydu + rastgele ek; ayni saniyedeki iki kayit rastgele siralaniyor, son_kayit/geri-al yanlis kaydi secebiliyordu."""
    import time as zaman

    from aktapokus_ajan import pipeline

    idler = []
    for _ in range(40):
        idler.append(pipeline._yeni_kayit_kimligi())
        zaman.sleep(0.003)
    assert idler == sorted(idler), "kimlikler olusturma sirasini korumali"
    assert len(set(idler)) == 40
