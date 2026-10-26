"""Hesaplar: hangi hizmette kimin girisi var (yalniz okur; token/orgId sizmaz), kenar cubugu hesap kutusu, uzaktan okuma."""

import json
from pathlib import Path

import pytest

from aktapokus_ai_studio import hesaplar, runners
from aktapokus_ai_studio.arayuz import ArayuzSunucusu, Uygulama
from test_arayuz import Istemci

CLAUDE_CIKTI = json.dumps({
    "loggedIn": True, "authMethod": "claude.ai", "apiProvider": "firstParty", "email": "kisi@example.com", "orgId": "ORG-GIZLI-123",
    "orgName": "Kisi's Organization", "subscriptionType": "pro", "configDirectory": "C:\\gizli\\yol",
})


def test_yerel_kullanici_aktapokus_hesabi_yok(monkeypatch):
    monkeypatch.setattr(hesaplar.getpass, "getuser", lambda: "baris.menderes")
    y = hesaplar.yerel()
    assert y["kullanici"] == "baris.menderes" and y["giris"] is False and y["bilgisayar"] is not None
    monkeypatch.setattr(hesaplar.getpass, "getuser", lambda: (_ for _ in ()).throw(OSError("yok")))
    assert hesaplar.yerel()["kullanici"] == ""  # kullanici adi okunamazsa cokmez


def test_claude_oturumu_okunur_yalniz_gerekli_alanlar_doner_orgid_ve_yollar_sizmaz(monkeypatch):
    monkeypatch.setattr(runners, "claude_bul", lambda: "claude.exe")
    monkeypatch.setattr(hesaplar, "_calistir", lambda argv, zaman_asimi=25: (0, "uyari satiri\n" + CLAUDE_CIKTI + "\n"))
    c = hesaplar.claude()
    assert c == {"kurulu": True, "giris": True, "yontem": "claude.ai", "eposta": "kisi@example.com", "abonelik": "pro"}
    assert "ORG-GIZLI-123" not in json.dumps(c) and "gizli" not in json.dumps(c)


@pytest.mark.parametrize("cikti,beklenen", [
    (json.dumps({"loggedIn": False}), {"kurulu": True, "giris": False, "yontem": None, "eposta": None, "abonelik": None}),
    ("json degil", {"kurulu": True, "giris": False, "hata": "Oturum durumu okunamadi"}),
    ("", {"kurulu": True, "giris": False, "hata": "Oturum durumu okunamadi"}),
    ("{bozuk", {"kurulu": True, "giris": False, "hata": "Oturum durumu okunamadi"}),
    (json.dumps({"loggedIn": True, "email": 5, "subscriptionType": ["x"]}), {"kurulu": True, "giris": True, "yontem": None, "eposta": None, "abonelik": None}),
])
def test_claude_giris_yok_bozuk_cikti_ve_yanlis_tipler(monkeypatch, cikti, beklenen):
    monkeypatch.setattr(runners, "claude_bul", lambda: "claude.exe")
    monkeypatch.setattr(hesaplar, "_calistir", lambda argv, zaman_asimi=25: (0, cikti))
    assert hesaplar.claude() == beklenen


def test_claude_kurulu_degilse_sorgu_yapilmaz(monkeypatch):
    monkeypatch.setattr(runners, "claude_bul", lambda: None)
    monkeypatch.setattr(hesaplar, "_calistir", lambda *a, **k: (_ for _ in ()).throw(AssertionError("calistirilmamali")))
    assert hesaplar.claude() == {"kurulu": False, "giris": False}


@pytest.mark.parametrize("kod,cikti,giris", [(0, "Logged in using ChatGPT\n", True), (1, "Not logged in\n", False), (0, "Not logged in\n", False), (-1, "", False)])
def test_codex_oturumu(monkeypatch, kod, cikti, giris):
    monkeypatch.setattr(runners, "codex_bul", lambda: ["codex"])
    monkeypatch.setattr(hesaplar, "_calistir", lambda argv, zaman_asimi=25: (kod, cikti))
    c = hesaplar.codex()
    assert c["kurulu"] is True and c["giris"] is giris
    if giris:
        assert c["detay"] == "Logged in using ChatGPT"


def test_codex_kurulu_degil(monkeypatch):
    monkeypatch.setattr(runners, "codex_bul", lambda: None)
    assert hesaplar.codex() == {"kurulu": False, "giris": False}


def test_alt_surec_zaman_asimi_ve_olmayan_program_cokmez():
    assert hesaplar._calistir(["bu-program-yok-123"]) == (-1, "")


# ---------- API ----------
@pytest.fixture
def api(proje, monkeypatch):
    monkeypatch.setattr(hesaplar, "claude", lambda: {"kurulu": True, "giris": True, "yontem": "claude.ai", "eposta": "kisi@example.com", "abonelik": "pro"})
    monkeypatch.setattr(hesaplar, "codex", lambda: {"kurulu": True, "giris": False, "detay": "Not logged in"})
    app = Uygulama()
    sv = ArayuzSunucusu(app)
    sv.baslat()
    app.klasor_sec(str(proje))
    yield app, Istemci(sv)
    sv.kapat()


def test_hesaplar_ucu_tum_hizmetleri_ve_aktapokus_hesabi_olmadigini_dondurur(api, monkeypatch):
    app, istek = api
    monkeypatch.setattr("aktapokus_ai_studio.arayuz.github.durum", lambda: {"kurulu": True, "giris": True, "hesap": "bmenderes", "ad": "Baris", "hata": None})
    st, d = istek("GET", "/api/hesaplar")
    assert st == 200
    assert d["yerel"]["giris"] is False and d["yerel"]["kullanici"]
    assert d["github"]["hesap"] == "bmenderes" and d["claude"]["eposta"] == "kisi@example.com" and d["codex"]["giris"] is False
    assert set(d["telegram"]) == {"calisiyor", "bot", "eslesmis"} and d["uzak"] == {"acik": False}


def test_hesaplar_bir_kaynak_hata_verirse_digerleri_yine_gelir(api, monkeypatch):
    app, istek = api
    monkeypatch.setattr("aktapokus_ai_studio.arayuz.github.durum", lambda: {"kurulu": False, "giris": False, "hesap": None, "hata": "gh yok"})
    monkeypatch.setattr(Uygulama, "_telegram", lambda self: (_ for _ in ()).throw(RuntimeError("telegram bozuk")))
    st, d = istek("GET", "/api/hesaplar")
    assert st == 200 and d["telegram"] == {"calisiyor": False, "bot": None, "eslesmis": 0} and d["github"]["kurulu"] is False and d["claude"]["giris"] is True


def test_belirtec_ister_ve_durum_yerel_kullaniciyi_icerir(api):
    app, istek = api
    assert istek("GET", "/api/hesaplar", token=None)[0] == 401
    st, d = istek("GET", "/api/durum")
    assert st == 200 and d["yerel"]["giris"] is False and "kullanici" in d["yerel"]


def test_arayuz_hesap_kutusu_ve_bolumu_var():
    html = (Path(__file__).parent.parent / "aktapokus_ai_studio" / "web" / "index.html").read_text(encoding="utf-8")
    assert 'id="hesapChip"' in html and "yerel · hesap girişi yok" in html and 'ayarAc("hesaplar")' in html
    assert 'const AYAR_BOLUMLERI=[["hesaplar","Hesaplar"],' in html and "async function hesaplarBolumu" in html
    assert "Aktapokus'un kendi kullanıcı hesabı yoktur" in html and "claude auth login" in html and "codex login" in html


def test_sol_panelin_alti_sabit_ust_kismi_kayar_hesap_kutusu_giris_yapilani_gosterir():
    """Gercek sikayet: Ayarlar/Terminal dugmelerine asagi kaydirarak ulasiliyordu; giris yapilan kullanici kutuda gorunmuyordu."""
    html = (Path(__file__).parent.parent / "aktapokus_ai_studio" / "web" / "index.html").read_text(encoding="utf-8")
    assert '<div id="solKaydir">' in html and '<div id="solAlt"><button id="hesapChip"' in html
    assert "#solKaydir{flex:1;min-height:0;overflow:auto}#solAlt{flex:none;" in html and "padding:8px 10px;overflow:hidden;min-height:0}" in html
    assert 'ad=c.eposta;else if(g.giris&&g.hesap)ad="@"+g.hesap' in html and 'alt="giriş: "+girisler.join(" · ")' in html
    assert "async function hesapOzetYukle" in html and "hesapOzetYukle()})();" in html


def test_ust_cubukta_terminal_ayarlar_ve_sag_panel_sekmeleri_kapatilip_acilabilir():
    html = (Path(__file__).parent.parent / "aktapokus_ai_studio" / "web" / "index.html").read_text(encoding="utf-8")
    assert 'id="terminalUst"' in html and 'id="ayarUst"' in html and 'ev.key==="`"||ev.code==="Backquote"' in html
    for parca in ("function sekmeleriCiz", "function sekmeKapat", 'id:"sekmeEkle"', 'id:"sagGenis"', 'text:"✕",onclick:sagDegis', "if(acik.length<=1)return;"):
        assert parca in html, parca
    assert "d.sagGenis?sagEnCok:" in html and "(S.gizliSekme||[]).includes(id)" in html  # programatik sekme acma kapali sekmeyi geri getirir
