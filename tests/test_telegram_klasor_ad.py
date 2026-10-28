"""Telegram /klasor: kisa ad (kayitli proje adi ya da izinli klasorun altindaki klasor), anlasilir hata; goreli yol botun calistigi klasore gore COZULMEZ."""

from aktapokus_ai_studio import projeler
from test_telegram import UID, aktif_klasor, bekle, kok_kur, kur  # noqa: F401  (kur: pytest fixture'i)


def metin(fake):
    return "\n".join(fake.metinler())


def test_kisa_ad_izinli_klasorun_altindaki_klasoru_secer_buyuk_kucuk_harf_onemsiz(kur, tmp_path):
    k1, k2, k3 = kok_kur(tmp_path)
    bot, fake, app, _ = kur(kokler=(k1,))
    fake.mesaj(UID, "/klasor HAZIR")
    assert bekle(lambda: aktif_klasor(bot) == (k1 / "hazir").resolve())


def test_on_ek_tek_eslesme_secilir_birden_fazla_eslesmede_adaylar_listelenir(kur, tmp_path):
    k1, k2, k3 = kok_kur(tmp_path)  # k1: hazir, gitsiz, aktapokus-ajan (+ gizli/dosya)
    (k1 / "hazir-2").mkdir()
    bot, fake, app, _ = kur(kokler=(k1,))
    fake.mesaj(UID, "/klasor gits")  # tek on ek eslesmesi
    assert bekle(lambda: aktif_klasor(bot) == (k1 / "gitsiz").resolve())
    fake.mesaj(UID, "/klasor haz")  # hazir ve hazir-2
    assert bekle(lambda: any("birden fazla klasorle eslesiyor" in m and "hazir-2" in m for m in fake.metinler()))
    assert aktif_klasor(bot) == (k1 / "gitsiz").resolve()  # belirsiz secim bir sey degistirmedi
    fake.mesaj(UID, "/klasor hazir")  # tam eslesme belirsizligi cozer
    assert bekle(lambda: aktif_klasor(bot) == (k1 / "hazir").resolve())


def test_kayitli_proje_adiyla_secilir(kur, tmp_path):
    k1, k2, k3 = kok_kur(tmp_path)
    bot, fake, app, _ = kur(kokler=(k1, k2))
    app.proje_ac(str(k2 / "ikinci"), sec=False)  # kayitli proje
    kayit = next(p for p in projeler.listele() if p["yol"] == str((k2 / "ikinci").resolve()) or p["ad"] == "ikinci")
    fake.mesaj(UID, f"/klasor {kayit['ad']}")
    assert bekle(lambda: aktif_klasor(bot) == (k2 / "ikinci").resolve())


def test_bulunamayinca_mevcut_adlar_ve_tam_yol_ornegi_gosterilir_gizli_klasor_secilemez(kur, tmp_path):
    k1, k2, k3 = kok_kur(tmp_path)
    bot, fake, app, _ = kur(kokler=(k1,))
    fake.mesaj(UID, "/klasor yokboyle")
    assert bekle(lambda: any("Klasor bulunamadi: 'yokboyle'" in m and "Mevcut:" in m and "hazir" in m and "TAM olmali" in m for m in fake.metinler()))
    fake.mesaj(UID, "/klasor .gizli")  # nokta klasoru aday degil
    fake.mesaj(UID, "/klasor")  # bos: kullanim + mevcut adlar
    assert bekle(lambda: any("Klasor adi ya da tam yolu yazin" in m and "hazir" in m for m in fake.metinler()))
    assert aktif_klasor(bot) is None and ".gizli" not in metin(fake).split("Mevcut:", 1)[1].split(".")[0]


def test_goreli_yol_botun_calistigi_klasore_gore_cozulmez_koksuz_kisa_ad_bulunamaz(kur, tmp_path, monkeypatch):
    bot, fake, app, _ = kur()  # kok yok, kayitli proje adi da eslesmiyor
    (tmp_path / "goreli-proje").mkdir()
    monkeypatch.chdir(tmp_path)
    fake.mesaj(UID, "/klasor goreli-proje")
    fake.mesaj(UID, "/klasor ../baska")
    assert bekle(lambda: sum("TAM olmali" in m for m in fake.metinler()) >= 2)
    assert aktif_klasor(bot) is None and not (tmp_path / "goreli-proje" / ".aktapokus").exists()


def test_kokun_altinda_goreli_yol_calisir_yukari_cikan_yol_ve_kok_disi_reddedilir(kur, tmp_path):
    k1, k2, k3 = kok_kur(tmp_path)
    (k1 / "hazir" / "alt").mkdir()
    bot, fake, app, _ = kur(kokler=(k1,))
    fake.mesaj(UID, "/klasor ../kok2/ikinci")
    assert bekle(lambda: sum("TAM olmali" in m for m in fake.metinler()) >= 1)
    assert aktif_klasor(bot) is None
    fake.mesaj(UID, "/klasor hazir/alt")
    assert bekle(lambda: aktif_klasor(bot) == (k1 / "hazir" / "alt").resolve())
