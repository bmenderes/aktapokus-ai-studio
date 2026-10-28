"""Gonderme kontrolu: kural tabanli tarama, yapay zeka incelemesi (sirlar maskeli gider), commit/push kapilari, commit mesaji onerisi."""

import json
import time
from pathlib import Path

import pytest

from aktapokus_ai_studio import gonderme_kontrol as gk
from conftest import SahteCalistirici, sonuc
from test_github_api import api, git, kur_sunucu, ortam  # noqa: F401  (pytest fixture'lari)

TOKEN = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"
KART = "4111 1111 1111 1111"


# ---------- kural tabanli tarama ----------
@pytest.mark.parametrize("satir,tur,siddet", [
    ("token=" + TOKEN, "GitHub belirteci", "yuksek"), ("AKIA" + "ABCDEFGHIJKLMNOP", "AWS anahtari", "yuksek"), ("-----BEGIN RSA PRIVATE KEY-----", "ozel anahtar", "yuksek"),
    ("bot=123456789:" + "AAH" + "x" * 32, "Telegram bot belirteci", "yuksek"), ("kart " + KART + " son", "banka karti numarasi", "yuksek"),
    ("TR33 0006 1005 1978 6457 8413 26", "IBAN", "yuksek"), ("tc 10000000146", "T.C. kimlik numarasi", "yuksek"), ("postgres://admin:hunter22@db.local/x", "adres icinde parola", "yuksek"),
    ("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijk", "JWT belirteci", "yuksek"),
    ("bana ulas: baris.m@gmail.com", "e-posta adresi", "orta"), ("ara 0532 123 45 67", "telefon numarasi", "orta"), (r"C:\Users\baris.menderes\Desktop\x", "kullanici klasoru yolu", "orta"),
    ("bilgisayarim.tailabc12.ts.net", "ozel ag adi (Tailscale)", "orta"), ('password = "Sup3rS3cretValue"', "parola/anahtar atamasi", "orta"), ("sunucu 8.8.8.8", "genel IP adresi", "dusuk"),
])
def test_kurallar_gercek_sirlari_yakalar(satir, tur, siddet):
    b = gk.satir_tara(satir, "a.txt", 3)
    assert [(x.tur, x.siddet) for x in b] == [(tur, siddet)], b
    assert b[0].satir == 3 and b[0].dosya == "a.txt"
    assert len(b[0].ornek) < 20 and b[0].ornek.startswith(("***",)) or "…(" in b[0].ornek  # maskeli: deger tam gosterilmez


@pytest.mark.parametrize("satir", [
    "numara 1234 5678 9012 3456", "tc 12345678901", "ornek: user@example.com", "noreply@github.com", r"C:\Users\adiniz\Desktop\proje", 'password = "your_password_here"',
    'token = "${TOKEN}"', 'api_key = "xxxxxxxxxxxxxxxx"', "sunucu 192.168.1.5 ve 127.0.0.1", "versiyon 3.14.0", "def f(): return 42",
])
def test_kurallar_yanlis_alarm_uretmez(satir):
    assert gk.satir_tara(satir, "a.txt", 1) == []


def test_redakte_sirlari_modele_gitmeden_degistirir_gerisine_dokunmaz():
    r = gk.redakte(f"mail baris.m@gmail.com ve {TOKEN} kart {KART}\nnormal satir")
    assert TOKEN not in r and "baris.m@gmail.com" not in r and KART not in r and "normal satir" in r
    assert "[GIZLI:GitHub belirteci]" in r and "[GIZLI:e-posta adresi]" in r and "[GIZLI:banka karti numarasi]" in r


def test_eklenenler_diff_ayristirir_dosya_ve_satir_numarasi():
    diff = "@@@commit abc\ndiff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1,0 +5,2 @@\n+bir\n+iki\n@@ -9 +20 @@\n-eski\n+uc\n--- /dev/null\n+++ /dev/null\n"
    assert gk.eklenenler(diff) == [("x.py", 5, "bir"), ("x.py", 6, "iki"), ("x.py", 20, "uc")]


def test_dosya_adi_bulgusu_ve_tarama_siralamasi():
    t = {"dosyalar": [".env", "a.py"], "eklenen": [("a.py", 1, "ara 0532 123 45 67"), ("a.py", 2, "token=" + TOKEN)]}
    b = gk.tara(t)
    assert [x["siddet"] for x in b] == ["yuksek", "yuksek", "orta"] and b[0]["tur"] in ("gizli gorunen dosya", "GitHub belirteci")  # yuksek once


def test_ai_json_ve_sonuc_dogrulama():
    cikti = 'dusunuyorum {"x":1}\n{"sorunlar":[{"dosya":"a","aciklama":"ad soyad var","siddet":"yuksek"},{"dosya":"b","aciklama":"x","siddet":"garip"}],"commit_mesaji":"```\\nEkle: a\\n```"}'
    s = gk.ai_sonucu(cikti, {})
    assert s["durum"] == "tamam" and [x["siddet"] for x in s["sorunlar"]] == ["yuksek", "orta"] and s["commit_mesaji"] == "Ekle: a"
    assert gk.ai_sonucu("json yok", {})["durum"] == "hata"
    sirli = gk.ai_sonucu('{"sorunlar":[],"commit_mesaji":"Ekle ' + TOKEN + '"}', {})
    assert sirli["commit_mesaji"] is None  # modelin mesaja yazdigi sir kullanilmaz


# ---------- push kapisi ----------
def yaz_ve_commit(proje, ad, icerik, mesaj="m"):
    (proje / ad).write_text(icerik, encoding="utf-8")
    git(proje, "add", ad)
    git(proje, "commit", "-qm", mesaj)


def temiz_ai(istemler):
    def f(k, istem, n):
        istemler.append(istem)
        return sonuc('Inceledim.\n{"sorunlar":[],"commit_mesaji":"Test commit mesaji"}')

    return f


def kur_ai(ortam, istemler, rol="gizlilik denetcisi", islev=None):
    proje, uzak = ortam
    sahte = SahteCalistirici({rol: islev or temiz_ai(istemler), "kodcu": lambda k, i, n: sonuc("x"), "test": lambda k, i, n: sonuc("SONUC: BASARILI")})
    app, sv, istek = kur_sunucu(uret=lambda ad: sahte)
    app.klasor_sec(str(proje))
    return app, sv, istek


def test_kontrolsuz_push_olmaz_temiz_icerik_ai_tamam_push_olur_kontrol_tek_kullanimlik(ortam):
    proje, uzak = ortam
    istemler = []
    app, sv, istek = kur_ai(ortam, istemler)
    try:
        yaz_ve_commit(proje, "a.txt", "merhaba dunya\n")
        assert istek("POST", "/api/github/push", {})[0] == 409
        assert istek("POST", "/api/github/push", {"kontrol": "uydurma"})[0] == 409
        k = istek("POST", "/api/github/gonderme-kontrol", {})[1]
        assert k["bulgular"] == [] and k["ai"]["durum"] == "tamam" and k["commit_sayisi"] == 1 and k["ilk_gonderim"] is True and k["dosya_sayisi"] == 1
        assert any("merhaba dunya" in i for i in istemler)
        st, d = istek("POST", "/api/github/push", {"kontrol": k["kontrol"]})
        assert st == 200 and git(uzak, "log", "-1", "--format=%s", "main").strip() == "m"
        assert istek("POST", "/api/github/push", {"kontrol": k["kontrol"]})[0] == 409  # tek kullanimlik
    finally:
        sv.kapat()


def test_yuksek_bulgu_pushu_engeller_kabul_edilince_gecer_yapay_zekaya_sir_gitmez(ortam):
    proje, uzak = ortam
    istemler = []
    app, sv, istek = kur_ai(ortam, istemler)
    try:
        yaz_ve_commit(proje, "ayar.py", f'# kart {KART}\nTOKEN = "{TOKEN}"\n')
        k = istek("POST", "/api/github/gonderme-kontrol", {})[1]
        yuksek = [b for b in k["bulgular"] if b["siddet"] == "yuksek"]
        assert {b["tur"] for b in yuksek} == {"GitHub belirteci", "banka karti numarasi"} and all(b["dosya"] == "ayar.py" for b in yuksek)
        assert all(TOKEN not in json.dumps(b) and KART not in json.dumps(b) for b in k["bulgular"])  # arayuze maskeli doner
        tum = "\n".join(istemler)
        assert istemler and TOKEN not in tum and KART not in tum and "[GIZLI:GitHub belirteci]" in tum  # bulutta bir modele sir gitmedi
        st, d = istek("POST", "/api/github/push", {"kontrol": k["kontrol"]})
        assert st == 409 and "yuksek riskli bulgu kabul edilmedi" in d["hata"] and "ayar.py" in d["hata"]
        assert istek("POST", "/api/github/push", {"kontrol": k["kontrol"], "kabul": [yuksek[0]["id"]]})[0] == 409  # hepsi kabul edilmeli
        assert istek("POST", "/api/github/push", {"kontrol": k["kontrol"], "kabul": [b["id"] for b in yuksek]})[0] == 200
    finally:
        sv.kapat()


def test_yapay_zeka_yuksek_bulgusu_da_engeller_hata_olursa_ai_atla_gerekir(ortam):
    proje, uzak = ortam
    app, sv, istek = kur_ai(ortam, [], islev=lambda k, i, n: sonuc('{"sorunlar":[{"dosya":"a.txt","aciklama":"musteri adi ve adresi var","siddet":"yuksek"}]}'))
    try:
        yaz_ve_commit(proje, "a.txt", "Ahmet Yilmaz, Cankaya Mah. 5\n")
        k = istek("POST", "/api/github/gonderme-kontrol", {})[1]
        assert k["ai"]["durum"] == "tamam" and k["ai"]["sorunlar"][0]["siddet"] == "yuksek" and k["ai"]["model"]
        assert istek("POST", "/api/github/push", {"kontrol": k["kontrol"]})[0] == 409
        assert istek("POST", "/api/github/push", {"kontrol": k["kontrol"], "kabul": [k["ai"]["sorunlar"][0]["id"]]})[0] == 200
    finally:
        sv.kapat()
    app2, sv2, istek2 = kur_ai(ortam, [], islev=lambda k, i, n: sonuc("json yok"))
    try:
        yaz_ve_commit(proje, "b.txt", "b\n")
        k = istek2("POST", "/api/github/gonderme-kontrol", {})[1]
        assert k["ai"]["durum"] == "hata"
        st, d = istek2("POST", "/api/github/push", {"kontrol": k["kontrol"]})
        assert st == 409 and "Yapay zeka kontrolu yapilamadi" in d["hata"]
        assert istek2("POST", "/api/github/push", {"kontrol": k["kontrol"], "ai_atla": True})[0] == 200
    finally:
        sv2.kapat()


def test_yapay_zeka_dosyalari_degistirirse_kontrol_gecersiz(ortam):
    proje, uzak = ortam

    def bozucu(k, i, n):
        (k / "ai-yazdi.txt").write_text("izinsiz", encoding="utf-8")
        return sonuc('{"sorunlar":[]}')

    app, sv, istek = kur_ai(ortam, [], islev=bozucu)
    try:
        yaz_ve_commit(proje, "a.txt", "a\n")
        k = istek("POST", "/api/github/gonderme-kontrol", {})[1]
        assert k["ai"]["durum"] == "hata" and "DEGISTIRDI" in k["ai"]["neden"]
        assert istek("POST", "/api/github/push", {"kontrol": k["kontrol"]})[0] == 409
    finally:
        sv.kapat()


def test_kontrolden_sonra_yeni_commit_ya_da_sure_dolarsa_push_reddedilir(ortam, monkeypatch):
    proje, uzak = ortam
    app, sv, istek = kur_ai(ortam, [])
    try:
        yaz_ve_commit(proje, "a.txt", "a\n")
        k = istek("POST", "/api/github/gonderme-kontrol", {})[1]
        yaz_ve_commit(proje, "b.txt", "kontrol sonrasi eklendi\n")
        st, d = istek("POST", "/api/github/push", {"kontrol": k["kontrol"], "ai_atla": True})
        assert st == 409 and "commit/dal degisti" in d["hata"]
        k2 = istek("POST", "/api/github/gonderme-kontrol", {})[1]
        gercek = time.time
        monkeypatch.setattr(time, "time", lambda: gercek() + 3600)
        st, d = istek("POST", "/api/github/push", {"kontrol": k2["kontrol"]})
        assert st == 409 and "suresi doldu" in d["hata"]
    finally:
        sv.kapat()


def test_ikinci_gonderimde_yalniz_yeni_commitler_taranir(ortam):
    proje, uzak = ortam
    app, sv, istek = kur_ai(ortam, [])
    try:
        yaz_ve_commit(proje, "eski.txt", f"TOKEN={TOKEN}\n")
        k = istek("POST", "/api/github/gonderme-kontrol", {})[1]
        assert istek("POST", "/api/github/push", {"kontrol": k["kontrol"], "kabul": [b["id"] for b in k["bulgular"]]})[0] == 200  # ilk gonderim tum gecmisi tarar
        yaz_ve_commit(proje, "yeni.txt", "temiz\n")
        k2 = istek("POST", "/api/github/gonderme-kontrol", {})[1]
        assert k2["ilk_gonderim"] is False and k2["commit_sayisi"] == 1 and k2["bulgular"] == [] and k2["dosya_sayisi"] == 1  # upstream'e gitmis eski commit tekrar taranmaz
    finally:
        sv.kapat()


# ---------- commit kapisi ve mesaj onerisi ----------
def test_commit_kapisi_yuksek_bulguyu_engeller_kabulle_gecer_mesajdaki_sir_da_engellenir(ortam):
    proje, uzak = ortam
    app, sv, istek = kur_ai(ortam, [])
    try:
        (proje / "k.py").write_text(f'KEY = "{TOKEN}"\nmail = "baris.m@gmail.com"\n', encoding="utf-8")
        git(proje, "add", "k.py")
        st, ky = istek("POST", "/api/github/commit-kontrol", {"yalniz_hazir": True})
        assert st == 200 and {b["siddet"] for b in ky["bulgular"]} == {"yuksek", "orta"} and TOKEN not in json.dumps(ky)
        st, d = istek("POST", "/api/github/commit", {"mesaj": "Ekle", "yalniz_hazir": True})
        assert st == 409 and "Commit yapilmadi" in d["hata"] and "k.py" in d["hata"]
        yuksek = [b["id"] for b in ky["bulgular"] if b["siddet"] == "yuksek"]
        st, d = istek("POST", "/api/github/commit", {"mesaj": "Ekle " + TOKEN, "yalniz_hazir": True, "kabul": yuksek})
        assert st == 409  # mesajin kendisindeki sir kabul listesinde degil
        assert istek("POST", "/api/github/commit", {"mesaj": "Ekle k.py", "yalniz_hazir": True, "kabul": yuksek})[0] == 200
    finally:
        sv.kapat()


def test_temiz_commit_engellenmez_gizli_dosya_adlari_commit_taramasinda_alarm_vermez(ortam):
    proje, uzak = ortam
    app, sv, istek = kur_ai(ortam, [])
    try:
        (proje / "a.txt").write_text("a", encoding="utf-8")
        (proje / ".env").write_text("SIR=1", encoding="utf-8")  # commit bunu kendiliginden atlar
        st, d = istek("POST", "/api/github/commit", {"mesaj": "Ekle a"})
        assert st == 200 and d["atlanan_gizli"] == [".env"]
    finally:
        sv.kapat()


def test_commit_mesaji_onerisi_yapay_zekayla_icerige_gore_yazilir_olmazsa_busbutun_oneri_kalir(ortam):
    proje, uzak = ortam
    istemler = []
    app, sv, istek = kur_ai(ortam, istemler, islev=lambda k, i, n: (istemler.append(i), sonuc('{"sorunlar":[],"commit_mesaji":"Giris sayfasina parola sifirlama ekle"}'))[1])
    try:
        (proje / "giris.py").write_text(f'def sifirla():\n    return "{TOKEN}"\n', encoding="utf-8")
        git(proje, "add", "giris.py")
        st, r = istek("GET", "/api/git/commit-oneri?yz=1")
        assert st == 200 and r["mesaj"] == "Giris sayfasina parola sifirlama ekle" and r["kaynak"] == "yapay zeka" and r["yapay_zeka"]
        assert "def sifirla" in "\n".join(istemler) and TOKEN not in "\n".join(istemler)  # icerik gider, sir gitmez
        st, r = istek("GET", "/api/git/commit-oneri")  # yapay zekasiz: eskisi gibi hizli oneri
        assert st == 200 and r["kaynak"] == "degisiklik" and "yapay_zeka" not in r
    finally:
        sv.kapat()
    app2, sv2, istek2 = kur_ai(ortam, [], islev=lambda k, i, n: sonuc("json yok"))
    try:
        st, r = istek2("GET", "/api/git/commit-oneri?yz=1")
        assert st == 200 and r["kaynak"] == "degisiklik" and r["yapay_zeka_hata"]
    finally:
        sv2.kapat()


def test_arayuz_gonderme_kontrol_diyalogu_ve_yapay_zeka_oneri_dugmesi_bagli():
    html = (Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "web" / "index.html").read_text(encoding="utf-8")
    for parca in ("/api/github/gonderme-kontrol", "/api/github/commit-kontrol", "function gondermeDiyalogu(o)", "ai_atla", '"/api/git/commit-oneri"+(yz?"?yz=1":"")'):
        assert parca in html, parca


def test_ai_parcalari_uzun_icerigi_calistirici_siniri_altinda_bolen_dosya_basligi_tasir():
    satirlar = [("a.html", i, "x" * 300) for i in range(1, 121)] + [("b.html", 1, "kisa")]
    parcalar, kesildi = gk.ai_parcalari({"eklenen": satirlar})
    assert not kesildi and len(parcalar) >= 2 and all(len(p) <= gk.AI_PARCA_AZAMI for p in parcalar)
    assert all(p.startswith("### ") for p in parcalar)  # her parca hangi dosyanin satirlari oldugunu bilir
    toplam = sum(len(p.split(chr(10))) for p in parcalar)
    assert toplam >= 121  # hicbir satir kaybolmadi (basliklar dahil fazlasi olabilir)
    assert any("kisa" in p for p in parcalar)
    assert len(gk.ai_istemi(parcalar[0], [], False)) < 24_000  # runners.AZAMI_ISTEM_UZUNLUGU altinda
    cok = {"eklenen": [("c.html", i, "y" * 400) for i in range(1, 2000)]}
    parcalar, kesildi = gk.ai_parcalari(cok)
    assert kesildi and len(parcalar) == gk.AI_PARCA_ADET
    assert gk.ai_parcalari({"eklenen": []}) == ([], False)
    kisa, k = gk.ai_parcalari({"eklenen": [("k.txt", 1, "merhaba")]})
    assert kisa == ["### k.txt" + chr(10) + "1: merhaba"] and not k


def test_uzun_icerik_parcalara_bolunerek_incelenir_istem_siniri_asilmaz_bulgular_birlesir(ortam):
    proje, uzak = ortam
    istemler = []

    def f(k, istem, n):
        assert len(istem) < 24_000  # gercek calistirici bundan uzun istemi reddeder
        istemler.append(istem)
        sorun = '{"dosya":"uzun.html","aciklama":"ornek bulgu %d","siddet":"dusuk"}' % len(istemler)
        return sonuc('Inceledim.' + chr(10) + '{"sorunlar":[' + sorun + '],"commit_mesaji":"Uzun sayfa ekle"}')

    app, sv, istek = kur_ai(ortam, istemler, islev=f)
    try:
        yaz_ve_commit(proje, "uzun.html", chr(10).join("satir %d " % i + "x" * 200 for i in range(240)) + chr(10))  # ~52 KB: calistiricinin 24.000 sinirini asar, parca sinirina sigar
        k = istek("POST", "/api/github/gonderme-kontrol", {})[1]
        assert k["ai"]["durum"] == "tamam" and len(istemler) >= 3  # parcalara bolundu
        assert len(k["ai"]["sorunlar"]) == len(istemler)  # her parcanin bulgusu birlesti
        assert "satir 0 " in istemler[0] and "satir 239 " in istemler[-1]  # bastan sona her satir bir incelemeye girdi
        assert istek("GET", "/api/git/commit-oneri?yz=1")[0] in (200, 409)
    finally:
        sv.kapat()
