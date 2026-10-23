import json
import subprocess
import threading
import time

import pytest

from aktapokus_ajan import cli
from aktapokus_ajan import telegram as tg
from aktapokus_ajan.arayuz import Uygulama
from conftest import SahteCalistirici
from sahte_telegram import TOKEN, SahteTelegram
from test_arayuz import BASARILI, Engelli, yaz

UID = 42


def bekle(kosul, sn=10):
    son = time.monotonic() + sn
    while time.monotonic() < son:
        if kosul():
            return True
        time.sleep(0.05)
    return False


@pytest.fixture
def kur(proje, tmp_path):
    acik = []

    def f(izinli=(UID,), uret=None, on_birikim=None, baslat=True, kokler=(), gizli=None):
        fake = SahteTelegram()
        sahte = SahteCalistirici({"kodcu": yaz, "test": BASARILI})
        app = Uygulama(calistirici_uret=uret or (lambda ad: sahte))
        ayar = tmp_path / "telegram.json"
        if izinli:
            veri = {"izinli": list(izinli), "icerik_gonder": False, "kokler": [str(k) for k in kokler]}
            if gizli is not None:
                veri["gizli"] = gizli
            ayar.write_text(json.dumps(veri), encoding="utf-8")
        loglar = []
        bot = tg.Bot(app, tg.TelegramApi(TOKEN, taban=fake.taban, zaman_asimi=10), ayar_yolu=ayar, log=loglar.append, yoklama_sn=1)
        if on_birikim:
            on_birikim(fake, app)
        t = None
        if baslat:
            t = threading.Thread(target=bot.calistir, daemon=True)
            t.start()
            assert bekle(lambda: any(m == "getUpdates" and v.get("offset", 0) != -1 for m, v in fake.cagrilar))
        acik.append((bot, fake, t))
        return bot, fake, app, loglar

    f.proje = proje
    yield f
    for bot, fake, t in acik:
        bot.durdur()
        if t:
            t.join(5)
        fake.kapat()


def son_klavye(fake, onek):
    for v in reversed(fake.gonderilen("sendMessage")):
        for satir in (v.get("reply_markup") or {}).get("inline_keyboard", []):
            for d in satir:
                if d["callback_data"].startswith(onek):
                    return v, {x["text"]: x["callback_data"] for x in satir}
    return None, {}


def tam_kosu_baslat(bot, fake, app, proje, gorev="yeni.txt ekle"):
    fake.mesaj(UID, f"/klasor {proje}")
    assert bekle(lambda: app.klasor is not None)
    fake.mesaj(UID, f"/gorev {gorev}")
    assert bekle(lambda: son_klavye(fake, "o:")[0] is not None)
    return son_klavye(fake, "o:")[1]["Onayla"].split(":")[1]


# ---------- yetki ----------
def test_yetkisiz_kullanici_sessizce_yok_sayilir(kur):
    bot, fake, app, _ = kur()
    fake.mesaj(99, "/durum")
    fake.mesaj(99, "/gorev x")
    fake.mesaj(99, "merhaba")
    fake.dugme(99, "o:abcd1234")
    time.sleep(1.5)
    assert fake.gonderilen("sendMessage") == [] and fake.gonderilen("answerCallbackQuery") == [] and app.kosu is None


def test_grup_ve_baskasi_adina_gelenler_yok_sayilir(kur):
    bot, fake, app, _ = kur()
    fake.mesaj(UID, "/durum", chat_id=-1001, tur="supergroup")
    fake.mesaj(UID, "/durum", chat_id=43)  # ozel ama baska sohbet kimligi
    fake.dugme(UID, "o:abcd1234", chat_id=-1001, tur="supergroup")
    time.sleep(1.5)
    assert fake.gonderilen("sendMessage") == [] and fake.gonderilen("answerCallbackQuery") == []


def test_eslestirme_kodu_tek_kullanimlik_ve_kaydedilir(kur, tmp_path):
    bot, fake, app, _ = kur(izinli=())
    kod = bot.eslestirme_kodu_uret()
    fake.mesaj(7, "/durum")  # eslesmeden komut: yok
    fake.mesaj(7, "/eslestir yanlis")
    assert bekle(lambda: any("Kod yanlis" in m for m in fake.metinler()))
    fake.mesaj(7, f"/eslestir {kod}")
    assert bekle(lambda: any("Eslesti" in m for m in fake.metinler()))
    assert json.loads((tmp_path / "telegram.json").read_text(encoding="utf-8"))["izinli"] == [7]
    assert bot.eslestirme is None
    n = len(fake.gonderilen("sendMessage"))
    fake.mesaj(8, f"/eslestir {kod}")  # ikinci kullanici ayni kodu deneyemez
    time.sleep(1.2)
    assert len(fake.gonderilen("sendMessage")) == n and bot.izinli == [7]
    assert "Durum" not in " ".join(fake.metinler()[:1])  # eslesmeden onceki /durum yanitlanmadi


def test_eslestirme_5_yanlis_denemede_kilitlenir_ve_sure_dolar(kur):
    bot, fake, app, _ = kur(izinli=())
    kod = bot.eslestirme_kodu_uret()
    for i in range(5):
        fake.mesaj(7, f"/eslestir x{i}")
    assert bekle(lambda: bot.eslestirme is None)
    fake.mesaj(7, f"/eslestir {kod}")
    time.sleep(1.2)
    assert bot.izinli == []  # dogru kod bile artik kabul edilmez
    kod2 = bot.eslestirme_kodu_uret()
    bot.eslestirme["bitis"] = time.monotonic() - 1  # sure doldu
    fake.mesaj(7, f"/eslestir {kod2}")
    time.sleep(1.2)
    assert bot.izinli == []


def test_baslangictan_onceki_birikim_atlanir(kur):
    def birikim(fake, app):
        app.klasor_sec(str(kur.proje))  # klasor secili: bayat /gorev islenseydi plan olusurdu
        fake.dugme(UID, "o:deadbeef")
        fake.mesaj(UID, "/gorev eski gorev")  # SON bayat guncelleme (gercek Telegram'da onaylanana dek kalir)

    bot, fake, app, _ = kur(on_birikim=birikim)
    fake.mesaj(UID, "/durum")
    assert bekle(lambda: any("Gorev: yok" in m for m in fake.metinler()))
    assert app.kosu is None and not any("Plan" in m for m in fake.metinler())  # bayat komut calismadi


# ---------- akis ----------
def test_tam_akis_korunsun(kur):
    bot, fake, app, _ = kur()
    kosu = tam_kosu_baslat(bot, fake, app, kur.proje)
    plan, dugmeler = son_klavye(fake, "o:")
    assert "Plan" in plan["text"] and "kodcu" in plan["text"] and "Reddet" in dugmeler
    fake.dugme(UID, f"o:{kosu}")
    assert bekle(lambda: son_klavye(fake, "k:")[0] is not None)
    fark, kd = son_klavye(fake, "k:")
    assert "1 dosya degisti" in fark["text"] and "A yeni.txt" in fark["text"] and set(kd) == {"Korunsun", "Geri al"}
    assert any("kodcu" in m and "tamam" in m for m in fake.metinler() + [v["text"] for v in fake.gonderilen("editMessageText")])
    fake.dugme(UID, kd["Korunsun"])
    assert bekle(lambda: any(m.startswith("Bitti: onaylandi") for m in fake.metinler()))
    assert (kur.proje / "yeni.txt").exists()
    assert fake.gonderilen("answerCallbackQuery") and fake.gonderilen("editMessageReplyMarkup")  # dugmeler kaldirildi


def test_geri_al_dugmesi(kur):
    bot, fake, app, _ = kur()
    kosu = tam_kosu_baslat(bot, fake, app, kur.proje)
    fake.dugme(UID, f"o:{kosu}")
    assert bekle(lambda: son_klavye(fake, "k:")[0] is not None)
    fake.dugme(UID, son_klavye(fake, "k:")[1]["Geri al"])
    assert bekle(lambda: any(m.startswith("Bitti: geri_alindi") for m in fake.metinler()))
    assert not (kur.proje / "yeni.txt").exists()


def test_plan_reddi_ve_bayat_dugme(kur):
    bot, fake, app, _ = kur()
    kosu = tam_kosu_baslat(bot, fake, app, kur.proje)
    fake.dugme(UID, f"r:{kosu}")
    assert bekle(lambda: any(m.startswith("Bitti: reddedildi") for m in fake.metinler()))
    n = len(fake.gonderilen("answerCallbackQuery"))
    fake.dugme(UID, f"o:{kosu}")  # reddedilmis plana tekrar basildi
    assert bekle(lambda: len(fake.gonderilen("answerCallbackQuery")) > n)
    assert "artik gecerli degil" in fake.gonderilen("answerCallbackQuery")[-1]["text"]
    assert not (kur.proje / "yeni.txt").exists()
    fake.dugme(UID, "k:abcdef12:1")
    fake.dugme(UID, "z:bozuk")
    assert bekle(lambda: len(fake.gonderilen("answerCallbackQuery")) >= n + 3)


def test_duz_metin_gorev_sayilir_ve_bos_gorev_reddedilir(kur):
    bot, fake, app, _ = kur()
    fake.mesaj(UID, f"/klasor {kur.proje}")
    assert bekle(lambda: app.klasor is not None)
    fake.mesaj(UID, "/gorev")
    assert bekle(lambda: any("bos" in m for m in fake.metinler()))
    fake.mesaj(UID, "ana sayfadaki basligi degistir")  # komut onekisiz
    assert bekle(lambda: any("Gorev: ana sayfadaki basligi degistir" in m for m in fake.metinler()))
    fake.mesaj(UID, "ikinci gorev")  # onay bekleyen gorev varken
    assert bekle(lambda: any("Gorev olusturulamadi" in m for m in fake.metinler()))


def test_durdur_komutu(kur):
    e = Engelli()
    bot, fake, app, _ = kur(uret=lambda ad: e)
    kosu = tam_kosu_baslat(bot, fake, app, kur.proje)
    fake.mesaj(UID, "/durdur")
    assert bekle(lambda: any("Calisan gorev yok" in m or "Durduruluyor" in m or "durumunda" in m for m in fake.metinler()))  # plan asamasinda: durdurulacak calisma yok
    fake.dugme(UID, f"o:{kosu}")
    assert e.basladi.wait(5)
    fake.mesaj(UID, "/durdur")
    assert bekle(lambda: any(m.startswith("Bitti: iptal") for m in fake.metinler()))


def test_goreli_klasor_yolu_reddedilir(kur, tmp_path, monkeypatch):
    """Gercek deneme: '/klasor aktapokus-deneme' botun calistigi klasore gore cozuldu, ajan YANLIS klasorde calisti."""
    bot, fake, app, _ = kur()
    (tmp_path / "goreli-proje").mkdir()
    monkeypatch.chdir(tmp_path)
    fake.mesaj(UID, "/klasor goreli-proje")
    assert bekle(lambda: any("TAM olmali" in m for m in fake.metinler()))
    assert app.klasor is None and not (tmp_path / "goreli-proje" / ".aktapokus").exists()
    fake.mesaj(UID, "/klasor ../baska")
    assert bekle(lambda: sum("TAM olmali" in m for m in fake.metinler()) >= 2)


def test_bilgisayar_tarafinda_ilerleme_gunlugu_yazilir_icerik_ve_token_yazilmaz(kur):
    bot, fake, app, loglar = kur()
    kosu = tam_kosu_baslat(bot, fake, app, kur.proje, gorev="GIZLI-GOREV-METNI yeni.txt ekle")
    fake.dugme(UID, f"o:{kosu}")
    assert bekle(lambda: son_klavye(fake, "k:")[0] is not None)
    fake.dugme(UID, son_klavye(fake, "k:")[1]["Korunsun"])
    assert bekle(lambda: any(" bitti " in l for l in loglar))
    tum = "\n".join(loglar)
    for beklenen in ("telegram komutu: /klasor", "telegram komutu: /gorev", " plan", " adim-basladi kodcu", " adim-bitti test", " fark", " bitti onaylandi"):
        assert beklenen in tum, beklenen
    assert "GIZLI-GOREV-METNI" not in tum and TOKEN not in tum and str(kur.proje) not in tum  # gorev metni/yol/token terminale yazilmaz


# ---------- proje kokleri: /projeler, /yeni, /kokler ----------
def kok_kur(tmp_path):
    """kok1: hazir (git+koruyucu) proje, gitsiz proje, gizli klasor, nokta klasoru, dosya; kok2: bir proje; kok3: bir git deposu (ic ice depo yasagi)."""
    import subprocess as sp
    from aktapokus_ajan import guard

    k1, k2, k3 = tmp_path / "kok1", tmp_path / "kok2", tmp_path / "kok3"
    for p in (k1 / "hazir", k1 / "gitsiz", k1 / "aktapokus-ajan", k1 / ".gizli", k2 / "ikinci", k3 / "ustte-depo-icinde"):
        p.mkdir(parents=True)
    (k1 / "dosya.txt").write_text("x")
    sp.run(["git", "-C", str(k1 / "hazir"), "init", "-q"], check=True)
    guard.kur(k1 / "hazir")
    sp.run(["git", "-C", str(k3), "init", "-q"], check=True)  # kok3'un kendisi depo
    return k1, k2, k3


def dugmeler_of(mesaj):
    return {d["text"]: d["callback_data"] for satir in mesaj["reply_markup"]["inline_keyboard"] for d in satir}


def test_projeler_dugmeleri_gizli_ve_dosyalari_gostermez(kur, tmp_path):
    k1, k2, k3 = kok_kur(tmp_path)
    bot, fake, app, _ = kur(kokler=(k1, k2))
    fake.mesaj(UID, "/projeler")
    assert bekle(lambda: any(v.get("reply_markup") for v in fake.gonderilen("sendMessage")))
    d = dugmeler_of(fake.gonderilen("sendMessage")[-1])
    assert set(d) == {"hazir", "gitsiz (git yok)", "ikinci (git yok)"}  # gizli, nokta klasoru ve dosya yok
    assert all(v.startswith("p:") and len(v) < 10 for v in d.values())  # callback_data kisa, yol icermez


def test_projeye_dokununca_secilir_gitsizde_git_baslat_sorulur(kur, tmp_path):
    k1, k2, k3 = kok_kur(tmp_path)
    bot, fake, app, _ = kur(kokler=(k1, k2))
    fake.mesaj(UID, "/projeler")
    assert bekle(lambda: any(v.get("reply_markup") for v in fake.gonderilen("sendMessage")))
    d = dugmeler_of(fake.gonderilen("sendMessage")[-1])
    fake.dugme(UID, d["hazir"])
    assert bekle(lambda: app.klasor == (k1 / "hazir").resolve())
    assert bekle(lambda: any("Klasor secildi: hazir" in m for m in fake.metinler()))
    fake.dugme(UID, d["gitsiz (git yok)"])
    assert bekle(lambda: son_klavye(fake, "g:")[0] is not None)
    assert not (k1 / "gitsiz" / ".git").exists() and app.klasor == (k1 / "hazir").resolve()  # onay verilmeden git init yok
    fake.dugme(UID, son_klavye(fake, "g:")[1]["Git baslat"])
    assert bekle(lambda: (k1 / "gitsiz" / ".git").exists() and app.klasor == (k1 / "gitsiz").resolve())
    assert (k1 / "gitsiz" / ".opencode" / "opencode.json").exists()  # koruyucu da kuruldu


def test_ust_depo_icindeki_klasorde_git_baslat_yok(kur, tmp_path):
    k1, k2, k3 = kok_kur(tmp_path)
    bot, fake, app, _ = kur(kokler=(k3,))
    fake.mesaj(UID, "/projeler")
    assert bekle(lambda: any(v.get("reply_markup") for v in fake.gonderilen("sendMessage")))
    d = dugmeler_of(fake.gonderilen("sendMessage")[-1])
    fake.dugme(UID, d["ustte-depo-icinde (git yok)"])
    assert bekle(lambda: any("ic ice depo" in m for m in fake.metinler()))
    assert son_klavye(fake, "g:")[0] is None and not (k3 / "ustte-depo-icinde" / ".git").exists()
    # elle gonderilen g: dugmesi de ic ice depo olusturamaz
    bot.proje_tablosu = [k3 / "ustte-depo-icinde"]
    fake.dugme(UID, "g:0")
    time.sleep(1.2)
    assert not (k3 / "ustte-depo-icinde" / ".git").exists()


def test_klasor_komutu_koklerle_sinirlanir(kur, tmp_path):
    k1, k2, k3 = kok_kur(tmp_path)
    disari = tmp_path / "disarida"
    disari.mkdir()
    bot, fake, app, _ = kur(kokler=(k1,))
    for yol in (disari, k1, k1 / "aktapokus-ajan", k1 / ".gizli", str(k1 / "hazir") + "\\..\\..\\disarida", k2 / "ikinci"):
        fake.mesaj(UID, f"/klasor {yol}")
    assert bekle(lambda: sum("izinli proje klasorlerinin altinda degil" in m for m in fake.metinler()) >= 6)
    assert app.klasor is None
    fake.mesaj(UID, f"/klasor {k1 / 'hazir'}")  # izinli
    assert bekle(lambda: app.klasor == (k1 / "hazir").resolve())


def test_yeni_proje_olusturur_git_ve_koruyucu_kurar(kur, tmp_path):
    k1, k2, k3 = kok_kur(tmp_path)
    bot, fake, app, _ = kur(kokler=(k1, k2))
    fake.mesaj(UID, "/yeni blog-1")
    assert bekle(lambda: app.klasor == (k1 / "blog-1").resolve())
    assert (k1 / "blog-1" / ".git").exists() and (k1 / "blog-1" / ".opencode" / "opencode.json").exists()
    assert not (k2 / "blog-1").exists()  # yalniz ILK kokte
    fake.mesaj(UID, "/yeni blog-1")
    assert bekle(lambda: any("zaten var" in m for m in fake.metinler()))


@pytest.mark.parametrize("ad", ["../kacis", "a/b", "a b", "con", "NUL", "nul.txt", "", "x" * 60, "-bas", ".gizli", "a\\b", "ç"])
def test_yeni_gecersiz_adlari_reddeder(kur, tmp_path, ad):
    k1, k2, k3 = kok_kur(tmp_path)
    bot, fake, app, _ = kur(kokler=(k1,))
    onceki = sorted(p.name for p in tmp_path.iterdir()) + sorted(p.name for p in k1.iterdir())
    fake.mesaj(UID, f"/yeni {ad}")
    assert bekle(lambda: any("Gecersiz ad" in m for m in fake.metinler()))
    assert sorted(p.name for p in tmp_path.iterdir()) + sorted(p.name for p in k1.iterdir()) == onceki  # hicbir sey olusmadi


def test_yeni_ilk_kok_depo_icindeyse_reddeder_ve_kok_yoksa_yonlendirir(kur, tmp_path):
    k1, k2, k3 = kok_kur(tmp_path)
    bot, fake, app, _ = kur(kokler=(k3,))  # kok3 bir git deposu
    fake.mesaj(UID, "/yeni yeniproje")
    assert bekle(lambda: any("ic ice depo" in m for m in fake.metinler()))
    assert not (k3 / "yeniproje").exists()
    bot2, fake2, app2, _ = kur()  # kok tanimsiz
    fake2.mesaj(UID, "/yeni x")
    fake2.mesaj(UID, "/projeler")
    assert bekle(lambda: sum("Proje klasoru tanimli degil" in m for m in fake2.metinler()) >= 2)


def test_eskimis_ve_yetkisiz_proje_dugmeleri(kur, tmp_path):
    k1, k2, k3 = kok_kur(tmp_path)
    bot, fake, app, _ = kur(kokler=(k1,))
    fake.dugme(UID, "p:0")  # /projeler hic yazilmadi: tablo bos
    fake.dugme(UID, "p:99")
    assert bekle(lambda: sum("Liste eskimis" in v.get("text", "") for v in fake.gonderilen("answerCallbackQuery")) >= 2)
    bot.proje_tablosu = [k1 / "hazir"]
    fake.dugme(99, "p:0")  # yetkisiz kullanici
    time.sleep(1.2)
    assert app.klasor is None
    bot.proje_tablosu = [tmp_path]  # tablo koklerin disina isaret etse bile secilemez
    fake.dugme(UID, "p:0")
    assert bekle(lambda: sum("Liste eskimis" in v.get("text", "") for v in fake.gonderilen("answerCallbackQuery")) >= 3)
    assert app.klasor is None


def test_kokler_komutu_ve_kok_ekle(kur, tmp_path, monkeypatch):
    k1, k2, k3 = kok_kur(tmp_path)
    bot, fake, app, _ = kur(kokler=(k1,))
    fake.mesaj(UID, "/kokler")
    assert bekle(lambda: any(str(k1) in m and "aktapokus-ajan" in m for m in fake.metinler()))
    # kok yalniz bilgisayardan eklenir; guvensiz klasorler reddedilir
    ayar = tmp_path / "kok-ayar.json"
    assert tg.kok_ekle(str(k2), ayar_yolu=ayar) == k2.resolve()
    assert tg.kok_ekle(str(k2), ayar_yolu=ayar) == k2.resolve()  # tekrar eklenmez
    v = json.loads(ayar.read_text(encoding="utf-8"))
    assert v["kokler"] == [str(k2.resolve())] and v["gizli"] == ["aktapokus-ajan"]
    from pathlib import Path
    with pytest.raises(Exception):
        tg.kok_ekle(str(Path.home()), ayar_yolu=ayar)


def test_klasor_git_degilse_telegramdan_git_init_yapilmaz(kur, tmp_path):
    bot, fake, app, _ = kur()
    k = tmp_path / "gitsiz"
    k.mkdir()
    fake.mesaj(UID, f"/klasor {k}")
    assert bekle(lambda: any("aktapokus ac" in m for m in fake.metinler()))
    assert not (k / ".git").exists() and app.klasor is None
    fake.mesaj(UID, "/klasor C:/yok/boyle/bir/yer")
    assert bekle(lambda: any("Klasor secilemedi" in m for m in fake.metinler()))


# ---------- gizlilik ----------
def test_icerik_varsayilan_olarak_telegrama_gitmez(kur, tmp_path):
    bot, fake, app, _ = kur()
    kosu = tam_kosu_baslat(bot, fake, app, kur.proje)
    fake.dugme(UID, f"o:{kosu}")
    assert bekle(lambda: son_klavye(fake, "k:")[0] is not None)
    n = len(fake.metinler())
    fake.mesaj(UID, "/fark yeni.txt")
    assert bekle(lambda: len(fake.metinler()) > n)  # /fark'a gelen YANIT
    assert fake.metinler()[-1].startswith("Dosya icerigi gonderimi kapali")
    tum = " ".join(fake.metinler() + [v["text"] for v in fake.gonderilen("editMessageText")])
    assert "+yeni" not in tum and "diff --git" not in tum


def test_gizlilik_acilinca_fark_gonderilir_ve_kalici(kur, tmp_path):
    bot, fake, app, _ = kur()
    fake.mesaj(UID, "/gizlilik acik")
    assert bekle(lambda: any("ACIK" in m for m in fake.metinler()))
    assert json.loads((tmp_path / "telegram.json").read_text(encoding="utf-8"))["icerik_gonder"] is True
    kosu = tam_kosu_baslat(bot, fake, app, kur.proje)
    fake.dugme(UID, f"o:{kosu}")
    assert bekle(lambda: son_klavye(fake, "k:")[0] is not None)
    fake.mesaj(UID, "/fark yeni.txt")
    assert bekle(lambda: any("+yeni" in m for m in fake.metinler()))
    fake.mesaj(UID, "/fark .env")
    assert bekle(lambda: any("Fark alinamadi" in m for m in fake.metinler()))  # gizli dosya yine reddedilir
    fake.mesaj(UID, "/gizlilik kapali")
    assert bekle(lambda: any("kapali" in m and "gonderimi" in m for m in fake.metinler()[-2:]))


# ---------- sertlestirme ----------
def test_token_hatalarda_sizmaz():
    fake = SahteTelegram(token="BASKA:TOKEN")
    try:
        api = tg.TelegramApi(TOKEN, taban=fake.taban, zaman_asimi=5)  # yanlis token -> 401
        with pytest.raises(tg.TelegramHatasi) as h:
            api.cagir("getUpdates")
        assert TOKEN not in str(h.value) and "401" in str(h.value)
    finally:
        fake.kapat()
    kapali = tg.TelegramApi(TOKEN, taban="http://127.0.0.1:1", zaman_asimi=2)
    with pytest.raises(tg.TelegramHatasi) as h2:
        kapali.cagir("sendMessage", {"chat_id": 1, "text": "x"})
    assert TOKEN not in str(h2.value) and h2.value.__cause__ is None


def test_uzun_metin_kesilir(kur):
    bot, fake, app, _ = kur()
    fake.mesaj(UID, f"/klasor {kur.proje}")
    assert bekle(lambda: app.klasor is not None)
    fake.mesaj(UID, "/gorev " + "x" * 10_000)
    assert bekle(lambda: son_klavye(fake, "o:")[0] is not None)
    assert len(son_klavye(fake, "o:")[0]["text"]) <= 3500


def test_yardim_durum_ve_bilinmeyen_komut(kur):
    bot, fake, app, _ = kur()
    fake.mesaj(UID, "/start")
    fake.mesaj(UID, "/durum")
    fake.mesaj(UID, "/bilinmez")
    assert bekle(lambda: len(fake.metinler()) >= 3)
    m = fake.metinler()
    assert "Aktapokus botu" in m[0] and "Klasor secilmedi" in m[1] and "Bilinmeyen komut" in m[2]


def test_api_hatasi_bot_dongusunu_dusurmez(kur):
    bot, fake, app, loglar = kur()
    fake.kapat()  # Telegram'a erisim kesildi
    assert bekle(lambda: any("yoklama hatasi" in l for l in loglar), 15)
    assert not any(TOKEN in l for l in loglar)


def test_start_kodu_ile_eslesme_baglanti_veya_qr_yolu(kur, tmp_path):
    bot, fake, app, _ = kur(izinli=())
    kod = bot.eslestirme_kodu_uret()
    fake.mesaj(7, "/start")  # kodsuz /start eslesmeden: sessiz
    fake.mesaj(7, "/start yanlis")
    assert bekle(lambda: any("Kod yanlis" in m for m in fake.metinler()))
    fake.mesaj(7, f"/start {kod}")  # t.me/<bot>?start=<kod> baglantisinin gonderdigi mesaj
    assert bekle(lambda: any("Eslesti" in m for m in fake.metinler()))
    assert bot.izinli == [7]
    fake.mesaj(8, f"/start {kod}")
    time.sleep(1.2)
    assert bot.izinli == [7]  # tek kullanimlik
    n = len(fake.metinler())
    fake.mesaj(7, "/start")  # eslesmis kullanici: yardim
    assert bekle(lambda: len(fake.metinler()) > n) and "Aktapokus botu" in fake.metinler()[-1]


def test_eslestirme_baglantisi_dogrulanir():
    assert tg.eslestirme_baglantisi("aktapokus_bot", "a1b2c3d4") == "https://t.me/aktapokus_bot?start=a1b2c3d4"
    for kotu in (("x", "a1b2c3d4"), ("bot adi", "a1b2c3d4"), ("ok_bot", "XYZ"), ("ok_bot", "a1b2c3d4/../"), ("a" * 40, "a1b2c3d4"), ("", "a1b2c3d4")):
        with pytest.raises(ValueError):
            tg.eslestirme_baglantisi(*kotu)


def test_qr_sayfasi_segno_yoksa_none_varsa_html_yazar(monkeypatch):
    import sys
    import types

    monkeypatch.setitem(sys.modules, "segno", None)  # import segno -> ImportError
    assert tg.eslestirme_sayfasi("https://t.me/x_bot?start=a1b2c3d4") is None

    class SahteQR:
        def svg_inline(self, **kw):
            return f'<svg data-scale="{kw["scale"]}"></svg>'

    sahte = types.ModuleType("segno")
    sahte.make = lambda veri, error: (setattr(sahte, "son", (veri, error)), SahteQR())[1]
    monkeypatch.setitem(sys.modules, "segno", sahte)
    link = 'https://t.me/x_bot?start=a1b2c3d4"><script>1</script>'  # kotu niyetli girdi sayfaya ham girmemeli
    yol = tg.eslestirme_sayfasi(link)
    try:
        icerik = yol.read_text(encoding="utf-8")
        assert sahte.son == (link, "m") and '<svg data-scale="6">' in icerik
        assert "<script>1</script>" not in icerik and "&lt;script&gt;" in icerik
    finally:
        yol.unlink(missing_ok=True)


def test_qr_sayfasi_gercek_segno_ile():
    segno = pytest.importorskip("segno")
    link = tg.eslestirme_baglantisi("aktapokus_deneme_bot", "a1b2c3d4")
    yol = tg.eslestirme_sayfasi(link)
    try:
        icerik = yol.read_text(encoding="utf-8")
        assert "<svg" in icerik and "</svg>" in icerik and link in icerik
        qr = segno.make(link, error="m")
        assert qr.error == "M" and qr.version <= 5  # bot adi en uzun 32 karakterde bile kucuk, kolay okunur QR
        uzun = segno.make(tg.eslestirme_baglantisi("a" * 32, "a1b2c3d4"), error="m")
        assert uzun.version <= 6
    finally:
        yol.unlink(missing_ok=True)


def test_telegram_komutu_baglanti_yazar_qr_acar_ve_eslesince_siler(monkeypatch, capsys):
    import sys
    import types
    import webbrowser

    fake = SahteTelegram()
    orijinal = tg.TelegramApi.__init__
    monkeypatch.setattr(tg.TelegramApi, "__init__", lambda self, token, taban=fake.taban, zaman_asimi=35.0: orijinal(self, token, taban=taban, zaman_asimi=zaman_asimi))
    monkeypatch.setenv(tg.TOKEN_ORTAMI, TOKEN)
    monkeypatch.setenv(tg.AYAR_ORTAMI, str(__import__("pathlib").Path(__import__("tempfile").mkdtemp()) / "t.json"))
    sahte = types.ModuleType("segno")
    sahte.make = lambda veri, error: types.SimpleNamespace(svg_inline=lambda **kw: "<svg></svg>")
    monkeypatch.setitem(sys.modules, "segno", sahte)
    acilan = []
    monkeypatch.setattr(webbrowser, "open", lambda url: acilan.append(url))
    olusan = {}

    def bot_calistir(self):  # dongu yerine: esle, sayfanin silindigini dogrula
        yol = self.eslesince.__closure__[0].cell_contents
        olusan["yol"], olusan["var_once"] = yol, yol.exists()
        self._eslestir(7, self.eslestirme["kod"])
        olusan["var_sonra"] = yol.exists()

    monkeypatch.setattr(tg.Bot, "calistir", bot_calistir)
    try:
        assert tg.telegram_calistir() == 0
    finally:
        fake.kapat()
    cikti = capsys.readouterr().out
    assert "https://t.me/sahte_bot?start=" in cikti and "/eslestir " in cikti and TOKEN not in cikti
    assert acilan and acilan[0].startswith("file:") and olusan["var_once"] is True and olusan["var_sonra"] is False


def test_ctrl_c_uzun_yoklamayi_beklemeden_cikar(monkeypatch, capsys):
    """Gercek deneme: Ctrl+C, 25 sn'lik engelleyen Telegram yoklamasi bitene dek etki etmiyordu."""
    fake = SahteTelegram()
    orijinal = tg.TelegramApi.__init__
    monkeypatch.setattr(tg.TelegramApi, "__init__", lambda self, token, taban=fake.taban, zaman_asimi=35.0: orijinal(self, token, taban=taban, zaman_asimi=zaman_asimi))
    monkeypatch.setenv(tg.TOKEN_ORTAMI, TOKEN)
    monkeypatch.setenv(tg.AYAR_ORTAMI, str(__import__("pathlib").Path(__import__("tempfile").mkdtemp()) / "t.json"))
    engel = threading.Event()
    monkeypatch.setattr(tg.Bot, "calistir", lambda self: engel.wait(30))  # uzun, engelleyen ag cagrisi
    sayac = {"n": 0}

    def sahte_bekle(sn):
        sayac["n"] += 1
        if sayac["n"] >= 3:
            raise KeyboardInterrupt  # kullanici Ctrl+C'ye bastı
        time.sleep(0.01)

    kapandi = []
    from aktapokus_ajan import runners

    monkeypatch.setattr(runners, "hepsini_kapat", lambda: kapandi.append(1))
    basla = time.monotonic()
    try:
        assert tg.telegram_calistir(bekle=sahte_bekle) == 0
        assert time.monotonic() - basla < 5  # 30 sn'lik engelleyen is parcacigini BEKLEMEDEN dondu
        assert "Durduruluyor" in capsys.readouterr().out and kapandi == [1]
    finally:
        engel.set()
        fake.kapat()


def test_baslarken_token_dogrulanir_ve_yanlis_token_net_hata_verir(monkeypatch, capsys, tmp_path, tarayici_acilmaz):
    monkeypatch.setenv(tg.AYAR_ORTAMI, str(tmp_path / "izole-ayar.json"))  # gercek eslesme/ayar dosyasindan bagimsiz (hermetik)
    fake = SahteTelegram()
    orijinal = tg.TelegramApi.__init__
    monkeypatch.setattr(tg.TelegramApi, "__init__", lambda self, token, taban=fake.taban, zaman_asimi=35.0: orijinal(self, token, taban=taban, zaman_asimi=zaman_asimi))
    try:
        monkeypatch.setenv(tg.TOKEN_ORTAMI, "yanlis:TOKEN-DEGERI")
        assert tg.telegram_calistir() == 1
        cikti = capsys.readouterr().out
        assert "Token dogrulanamadi" in cikti and "yanlis:TOKEN-DEGERI" not in cikti and "401" in cikti
        monkeypatch.setenv(tg.TOKEN_ORTAMI, TOKEN)
        monkeypatch.setattr(tg.Bot, "calistir", lambda self: None)  # dongu baslamadan don
        assert tg.telegram_calistir() == 0
        cikti = capsys.readouterr().out
        assert "@sahte_bot" in cikti and "/eslestir " in cikti and TOKEN not in cikti
        # segno kuruluysa QR sayfasi 'acilirdi': tarayici GERCEKTEN acilmadi, yalniz kayda gecti
        assert all(u.startswith("file:") for u in tarayici_acilmaz)
    finally:
        fake.kapat()


def test_token_yoksa_komut_yonerge_verir(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv(tg.TOKEN_ORTAMI, raising=False)
    monkeypatch.setattr(tg.Path, "home", classmethod(lambda c: tmp_path))
    assert tg.token_oku() is None
    assert cli.main(["telegram"]) == 2
    cikti = capsys.readouterr().out
    assert "BotFather" in cikti and "SIZ" in cikti and TOKEN not in cikti
    (tmp_path / ".aktapokus").mkdir()
    (tmp_path / ".aktapokus" / "telegram.token").write_text(TOKEN + "\n", encoding="utf-8")
    assert tg.token_oku() == TOKEN
    monkeypatch.setenv(tg.TOKEN_ORTAMI, "ortam:token")
    assert tg.token_oku() == "ortam:token"  # ortam degiskeni dosyadan oncelikli
