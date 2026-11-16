"""Gorev sirasinda izin sorusu: model komut calistirmak (ya da dosya duzenlemek) isteyince gorev durur, kullanici
'izin ver / bu gorevde hep / reddet' der. Yalniz OpenCode rolleri sorabilir; seviye proje ayarinda ('izin_sor')."""

import json
import threading

import pytest

from aktapokus_ai_studio import guard
from aktapokus_ai_studio.arayuz import ArayuzSunucusu, Uygulama
from aktapokus_ai_studio.config import AyarHatasi, VARSAYILAN_AYAR, ayar_coz, ayar_yolu
from aktapokus_ai_studio.sunucu import izin_ozeti
from conftest import SahteCalistirici, sonuc
from sahte_sunucu import SahteSunucu
from test_arayuz import Istemci, bekle
from test_sunucu import calistirici


# ---------- koruyucu seviyeleri ----------
def test_seviyeler_yalniz_sorulani_degistirir_yasaklar_kalir(tmp_path):
    assert guard.izin_ayari("hayir") == guard.IZIN_AYARI
    r = guard.izin_ayari("riskli")
    assert r["shell"]["*"] == "ask" and r["webfetch"] == "ask" and r["edit"]["*"] == "allow"
    h = guard.izin_ayari("hepsi")
    assert h["edit"]["*"] == "ask"
    for a in (r, h):  # sormak korumayi gevsetmez
        assert a["external_directory"] == "deny" and a["read"]["*.env"] == "deny" and a["edit"]["*.env"] == "deny" and a["shell"]["*.env*"] == "deny"


def test_kur_seviyeyi_yazar_korur_ve_geri_alir(tmp_path):
    guard.kur(tmp_path)
    assert guard.seviye_oku(tmp_path) == "hayir" and guard.dogrula(tmp_path) == []
    assert guard.kur(tmp_path, "riskli") == "guncellendi"
    assert guard.seviye_oku(tmp_path) == "riskli" and guard.dogrula(tmp_path) == []  # her seviye "koruyucu etkin" sayilir
    assert guard.kur(tmp_path) == "zaten-etkin"  # seviye verilmezse mevcut korunur
    guard.kur(tmp_path, "hepsi")
    assert guard.seviye_oku(tmp_path) == "hepsi"
    guard.kur(tmp_path, "hayir")
    veri = json.loads(guard.koruyucu_yolu(tmp_path).read_text(encoding="utf-8"))
    assert veri["permission"]["shell"]["*"] == "allow" and guard.seviye_oku(tmp_path) == "hayir" and guard.dogrula(tmp_path) == []
    with pytest.raises(guard.KoruyucuHatasi):
        guard.kur(tmp_path, "belki")


# ---------- ayar ----------
def test_ayar_alani_varsayilanlari_ve_dogrulama():
    assert VARSAYILAN_AYAR["izin_sor"] == "riskli"  # yeni proje sorar
    eski = {k: v for k, v in VARSAYILAN_AYAR.items() if k != "izin_sor"}
    assert ayar_coz(eski).izin_sor == "hayir"  # eski projelerin davranisi degismez
    assert ayar_coz({**eski, "izin_sor": "hepsi"}).izin_sor == "hepsi"
    with pytest.raises(AyarHatasi):
        ayar_coz({**eski, "izin_sor": "evet"})


# ---------- OpenCode calistiricisi ----------
def test_izin_ozeti_alanlari():
    assert izin_ozeti({"id": "p1", "action": "shell", "resources": ["npm  install"]}) == {"id": "p1", "arac": "shell", "ozet": "npm install"}
    assert izin_ozeti({"id": "p2", "permission": "edit", "metadata": {"filepath": "a.txt"}})["ozet"] == "a.txt"
    assert izin_ozeti({}) == {"id": "", "arac": "", "ozet": ""}


@pytest.mark.parametrize("karar", ["once", "always", "reject"])
def test_calistirici_soruyu_kullaniciya_iletir_ve_yanitini_gonderir(tmp_path, karar):
    s = SahteSunucu(davranis="izin")
    try:
        c = calistirici(s)
        sorulan = []
        c.izin_sor = lambda iz: sorulan.append(iz) or karar
        assert c.calistir("g", tmp_path).ok
        assert sorulan == [{"id": "per_1", "arac": "external_directory", "ozet": ""}]
        assert s.durum.yanitlar[0][2]["decision"] == karar
    finally:
        s.kapat()


def test_soran_taraf_hata_verirse_reddedilir(tmp_path):
    s = SahteSunucu(davranis="izin")
    try:
        c = calistirici(s)

        def bozuk(_iz):
            raise RuntimeError("x")

        c.izin_sor = bozuk
        assert c.calistir("g", tmp_path).ok and s.durum.yanitlar[0][2]["decision"] == "reject"
    finally:
        s.kapat()


# ---------- uygulama akisi ----------
class SoranCalistirici(SahteCalistirici):
    """OpenCode gibi: kodcu adiminda bir kez izin sorar ve yaniti kaydeder."""

    def __init__(self):
        super().__init__({"kodcu": lambda k, i, n: sonuc("x"), "test": lambda k, i, n: sonuc("SONUC: BASARILI")})
        self.izin_sor = None
        self.yanitlar = []

    def calistir(self, istem, klasor, model=None, agent=None, zaman_asimi_sn=900, onayli=True):
        if self.izin_sor is not None and "ROLUN: kodcu." in istem:
            self.yanitlar.append(self.izin_sor({"id": "per_9", "arac": "shell", "ozet": "npm install"}))
        return super().calistir(istem, klasor, model, agent, zaman_asimi_sn, onayli)


@pytest.fixture
def kur(proje):
    acik = []

    def f(seviye="riskli"):
        c = SoranCalistirici()
        app = Uygulama(calistirici_uret=lambda ad: c)
        sv = ArayuzSunucusu(app)
        sv.baslat()
        acik.append(sv)
        app.klasor_sec(str(proje))
        veri = json.loads(ayar_yolu(proje).read_text(encoding="utf-8"))
        veri["izin_sor"] = seviye
        ayar_yolu(proje).write_text(json.dumps(veri), encoding="utf-8")
        return app, Istemci(sv), c

    yield f
    for sv in acik:
        sv.kapat()


def _baslat(app, api):
    st, plan = api("POST", "/api/gorev", {"gorev": "g"})
    assert st == 200
    assert api("POST", f"/api/gorev/{plan['kosu']}/onayla", {})[0] == 200
    return plan["kosu"]


@pytest.mark.parametrize("karar", ["once", "always", "reject"])
def test_gorev_soruyu_bekler_yanitla_devam_eder(kur, proje, karar):
    app, api, c = kur()
    k = _baslat(app, api)
    assert bekle(lambda: app.kosu.izin is not None)
    assert guard.seviye_oku(proje) == "riskli"  # OpenCode'un izin dosyasi ayara esitlendi
    st, d = api("GET", "/api/durum")
    assert d["kosu"]["izin"] == {"id": "per_9", "arac": "shell", "ozet": "npm install", "rol": "kodcu"} and d["kosu"]["durum"] == "calisiyor"
    assert api("POST", f"/api/gorev/{k}/izin", {"karar": karar, "istek": "baska"})[0] == 409  # eski soruya yanit verilmez
    assert api("POST", f"/api/gorev/{k}/izin", {"karar": "belki"})[0] == 400
    assert api("POST", f"/api/gorev/{k}/izin", {"karar": karar, "istek": "per_9"})[0] == 200
    assert bekle(lambda: app.kosu.durum in ("karar-bekliyor", "bitti"))
    assert c.yanitlar == [karar]
    turler = [o["tur"] for o in app.bus.gecmis]
    assert turler.index("izin-bekleniyor") < turler.index("izin-yanitlandi")
    yanit = [o for o in app.bus.gecmis if o["tur"] == "izin-yanitlandi"][-1]
    assert yanit["karar"] == karar and yanit["ozet"] == "npm install"
    assert api("POST", f"/api/gorev/{k}/izin", {"karar": "once"})[0] == 409  # bekleyen soru kalmadi


def test_durdurmak_bekleyen_soruyu_reddeder(kur):
    app, api, c = kur()
    k = _baslat(app, api)
    assert bekle(lambda: app.kosu.izin is not None)
    assert api("POST", f"/api/gorev/{k}/durdur", {})[0] == 200
    assert bekle(lambda: c.yanitlar == ["reject"])


def test_seviye_hayirsa_sorulmaz(kur, proje):
    app, api, c = kur("hayir")
    _baslat(app, api)
    assert bekle(lambda: app.kosu.durum in ("karar-bekliyor", "bitti"))
    assert c.yanitlar == [] and not any(o["tur"] == "izin-bekleniyor" for o in app.bus.gecmis)
    assert guard.seviye_oku(proje) == "hayir"


def test_telefondan_yanitlanabilir_ama_seviye_degistirilemez():
    from aktapokus_ai_studio import uzak

    assert any(__import__("re").match(d, "/api/gorev/abcd1234/izin") for d in uzak.UZAK_DINAMIK_UCLAR)
