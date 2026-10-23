"""Model ekleme sihirbazinin sunucu tarafi: saglayici listesi, anahtar baglama, modeller, kaldirma. OpenCode yerine sahte istemci kullanilir."""

import json

import pytest

from aktapokus_ajan import sunucu
from aktapokus_ajan.arayuz import ArayuzSunucusu, Uygulama, UygulamaHatasi
from aktapokus_ajan.runners import CalistiriciHatasi
from aktapokus_ajan.sunucu import Istemci, SunucuHatasi
from test_arayuz import Istemci as HttpIstemci  # noqa: F401  (HTTP test istemcisi)

ANAHTAR = "SAHTE-anahtar-0123456789"


class SahteOpenCode:
    """Gercek OpenCode v2'de gozlenen bicim: integration {id,name,methods,connections}; model {providerID,modelID,name}."""

    def __init__(self):
        self.cagrilar = []
        self.baglantilar = {}
        self.hata = None
        self.hata_ek = ""

    def saglayicilar(self):
        def kayit(i, ad, yontemler, **ek):
            return {"id": i, "name": ad, "methods": yontemler, "connections": self.baglantilar.get(i, [])}

        return [
            kayit("zzz-son", "Zzz Son", [{"type": "key"}]),
            kayit("github-copilot", "GitHub Copilot", [{"type": "env", "names": ["GH_TOKEN"]}, {"type": "oauth"}]),
            kayit("google", "Google", [{"type": "key"}, {"type": "env", "names": ["GOOGLE_API_KEY", "GEMINI_API_KEY"]}]),
            kayit("openrouter", "OpenRouter", [{"type": "key"}, {"type": "env", "names": ["OPENROUTER_API_KEY"]}]),
            kayit("aaa-ilk", "Aaa Ilk", [{"type": "key"}]),
        ]

    def modeller(self):
        m = [{"providerID": "opencode", "modelID": "deepseek-v4.1-flash-free", "name": "DeepSeek V4.1 Flash"}]
        if "google" in self.baglantilar:
            m += [{"providerID": "google", "modelID": "gemini-flash", "name": "Gemini Flash"}, {"providerID": "google", "modelID": "gemini-pro"}]
        return m

    def anahtar_baglan(self, saglayici, anahtar, etiket=None):
        self.cagrilar.append(("baglan", saglayici, anahtar, etiket))
        if self.hata:
            raise SunucuHatasi(self.hata + self.hata_ek.replace("{anahtar}", anahtar))
        self.baglantilar[saglayici] = [{"type": "credential", "id": "cred_abc123", "label": etiket or "", "method": "key"}]

    def baglanti_kaldir(self, kimlik):
        self.cagrilar.append(("kaldir", kimlik))
        for k in list(self.baglantilar):
            self.baglantilar[k] = [b for b in self.baglantilar[k] if b["id"] != kimlik]
            if not self.baglantilar[k]:
                del self.baglantilar[k]


@pytest.fixture
def app():
    sahte = SahteOpenCode()
    return Uygulama(saglayici_istemci_uret=lambda: sahte), sahte


def test_saglayicilar_onerilenler_once_baglilar_en_basta_anahtar_sizmaz(app):
    a, sahte = app
    liste = a.saglayicilar()
    assert [c["id"] for c in liste] == ["google", "openrouter", "aaa-ilk", "github-copilot", "zzz-son"]  # oneri sirasi, sonra alfabetik
    g = liste[0]
    assert g["anahtarla"] and g["ortam"] == ["GOOGLE_API_KEY", "GEMINI_API_KEY"] and not g["bagli"]
    assert not next(c for c in liste if c["id"] == "github-copilot")["anahtarla"]  # yalniz env/oauth: anahtarla baglanamaz
    a.saglayici_baglan("zzz-son", ANAHTAR)
    liste = a.saglayicilar()
    assert liste[0]["id"] == "zzz-son" and liste[0]["bagli"] and liste[0]["baglantilar"] == [{"id": "cred_abc123", "label": ""}]
    assert ANAHTAR not in json.dumps(liste)


def test_baglan_anahtari_istemciye_verir_yanitta_geri_vermez(app):
    a, sahte = app
    r = a.saglayici_baglan("google", f"  {ANAHTAR}\n", "benim")
    assert sahte.cagrilar == [("baglan", "google", ANAHTAR, "benim")]  # kenar bosluklari temizlenir
    assert r["tamam"] and r["model_sayisi"] == 2 and "dogrulanmadi" in r["uyari"]
    assert ANAHTAR not in json.dumps(r)
    assert [m["id"] for m in a.modeller()] == ["google/gemini-flash", "google/gemini-pro", "opencode/deepseek-v4.1-flash-free"]
    assert a.modeller()[1]["ad"] == "gemini-pro"  # adi olmayan modelde kimlik gosterilir


@pytest.mark.parametrize("anahtar", ["", "   ", "iki kelime", "satir\nsonu", "ctrl\x01x", "a" * 4097, None, 5, ["x"]])
def test_gecersiz_anahtar_istemciye_hic_gitmez(app, anahtar):
    a, sahte = app
    with pytest.raises(Exception) as e:
        a.saglayici_baglan("google", anahtar)
    assert getattr(e.value, "kod", 400) == 400
    assert sahte.cagrilar == []


@pytest.mark.parametrize("saglayici", ["", "../etc", "a/b", "a b", "-x", None, 3, "x" * 102])
def test_gecersiz_saglayici_kimligi_reddedilir(app, saglayici):
    a, sahte = app
    with pytest.raises(Exception) as e:
        a.saglayici_baglan(saglayici, ANAHTAR)
    assert getattr(e.value, "kod", 400) == 400 and sahte.cagrilar == []


def test_hata_mesajinda_anahtar_maskelenir(app):
    a, sahte = app
    sahte.hata, sahte.hata_ek = "HTTP 400 POST /x: gecersiz anahtar ", "{anahtar}"
    with pytest.raises(Exception) as e:
        a.saglayici_baglan("google", ANAHTAR)
    assert e.value.kod == 502 and ANAHTAR not in str(e.value) and "***" in str(e.value)


def test_etiket_denetlenir(app):
    a, sahte = app
    for kotu in (5, "e" * 81):
        with pytest.raises(Exception):
            a.saglayici_baglan("google", ANAHTAR, kotu)
    assert sahte.cagrilar == []


def test_kaldir_baglanti_kimligini_istemciye_iletir(app):
    a, sahte = app
    a.saglayici_baglan("google", ANAHTAR)
    assert a.saglayici_kaldir("cred_abc123")["tamam"]
    assert sahte.cagrilar[-1] == ("kaldir", "cred_abc123") and not a.saglayicilar()[0]["bagli"]
    with pytest.raises(Exception):
        a.saglayici_kaldir(7)


def test_sunucuya_ulasilamazsa_anlamli_hata():
    def uret():
        raise CalistiriciHatasi("OpenCode baslamadi")

    a = Uygulama(saglayici_istemci_uret=uret)
    for islem in (a.saglayicilar, a.modeller, lambda: a.saglayici_kaldir("cred_a1"), lambda: a.saglayici_baglan("google", ANAHTAR)):
        with pytest.raises(UygulamaHatasi) as e:
            islem()
        assert e.value.kod == 502 and "OpenCode baslamadi" in str(e.value) and ANAHTAR not in str(e.value)


def test_istemci_kimlik_desenleri_yola_enjeksiyonu_onler():
    """Gecersiz kimlikte HICBIR istek gitmemeli (adres ulasilamaz oldugu icin hata zaten olusurdu: bu yuzden istegin kendisi izlenir)."""
    ist = Istemci("http://127.0.0.1:1", "p")
    gidenler = []
    ist._istek = lambda yontem, yol, veri=None, zaman_asimi=None: gidenler.append((yontem, yol))
    for kotu in ("../x", "a/b", "x?y", ""):
        with pytest.raises(SunucuHatasi, match="Gecersiz"):
            ist.anahtar_baglan(kotu, ANAHTAR)
    for kotu in ("cred_/../x", "abc", "cred_", "cred_a/b"):
        with pytest.raises(SunucuHatasi, match="Gecersiz"):
            ist.baglanti_kaldir(kotu)
    assert gidenler == []
    ist.anahtar_baglan("google", ANAHTAR)
    ist.baglanti_kaldir("cred_abc123")
    assert gidenler == [("POST", "/api/integration/google/connect/key"), ("DELETE", "/api/credential/cred_abc123")]


def test_http_uclari_belirtec_ister_ve_anahtari_gunluge_yazmaz(app, capsys):
    a, sahte = app
    sv = ArayuzSunucusu(a)
    sv.baslat()
    try:
        api = HttpIstemci(sv)
        st, d = api("POST", "/api/saglayicilar/baglan", {"saglayici": "google", "anahtar": ANAHTAR, "etiket": "x"})
        assert st == 200 and d["tamam"] and ANAHTAR not in json.dumps(d)
        assert api("GET", "/api/saglayicilar")[0] == 200 and api("GET", "/api/modeller")[0] == 200
        st, d = api("POST", "/api/saglayicilar/baglan", {"saglayici": "google", "anahtar": "iki kelime"})
        assert st == 400 and "iki kelime" not in json.dumps(d)
        assert api("POST", "/api/saglayicilar/kaldir", {"baglanti": "cred_abc123"})[0] == 200
        yok = HttpIstemci(sv, token="yanlis")
        assert yok("POST", "/api/saglayicilar/baglan", {"saglayici": "google", "anahtar": ANAHTAR})[0] == 401
    finally:
        sv.kapat()
    cikti = capsys.readouterr()
    assert ANAHTAR not in cikti.out and ANAHTAR not in cikti.err
