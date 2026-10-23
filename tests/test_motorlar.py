"""Motor denetimi: kurulu CLI'lar, varsayilan rollerin kurulu motora gore uretilmesi, kurulu olmayan CLI'a bagli rollerin gecirilmesi."""

import json
import sys
from pathlib import Path

import pytest

from aktapokus_ajan import clitanim, config, motorlar
from aktapokus_ajan.arayuz import ArayuzSunucusu, Uygulama
from aktapokus_ajan.config import AYAR_KLASORU, ROLLER_DOSYASI, VARSAYILAN_AYAR, ayar_coz
from aktapokus_ajan.proje import hazirla
from test_arayuz import Engelli, Istemci


def kurulu(monkeypatch, opencode=False, claude=False, codex=False, tercih_zorla=False):
    monkeypatch.setattr(motorlar, "opencode_bul", lambda: "C:/x/opencode.exe" if opencode else None)
    monkeypatch.setattr(motorlar, "claude_bul", lambda: "C:/x/claude.exe" if claude else None)
    monkeypatch.setattr(motorlar, "codex_bul", lambda: "C:/x/codex.exe" if codex else None)
    if not tercih_zorla:
        monkeypatch.delenv(motorlar.TERCIH_ORTAMI, raising=False)  # conftest testleri sabitlemek icin koyar; burada gercek mantik sinanir


# ---------- durum / tercih ----------
def test_durum_uc_motoru_ve_kurulum_komutunu_listeler(monkeypatch):
    kurulu(monkeypatch, claude=True)
    d = {m["ad"]: m for m in motorlar.durum()}
    assert list(d) == ["opencode-sunucu", "claude", "codex"]
    assert (d["opencode-sunucu"]["kurulu"], d["claude"]["kurulu"], d["codex"]["kurulu"]) == (False, True, False)
    assert "npm install -g @anthropic-ai/claude-code" in d["claude"]["kurulum"] and "opencode.ai" in d["opencode-sunucu"]["kurulum"]


def test_tercih_sirasi_opencode_claude_codex(monkeypatch):
    kurulu(monkeypatch, opencode=True, claude=True, codex=True)
    assert motorlar.tercih() == "opencode-sunucu"
    kurulu(monkeypatch, claude=True, codex=True)
    assert motorlar.tercih() == "claude"
    kurulu(monkeypatch, codex=True)
    assert motorlar.tercih() == "codex"
    kurulu(monkeypatch)
    assert motorlar.tercih() is None


def test_tercih_ortam_degiskeniyle_zorlanabilir(monkeypatch):
    kurulu(monkeypatch)
    monkeypatch.setenv(motorlar.TERCIH_ORTAMI, "codex")
    assert motorlar.tercih() == "codex"


def test_kurulu_mu_ozel_cli_ve_bilinmeyen_ad(monkeypatch, tmp_path):
    kurulu(monkeypatch)
    clitanim.kaydet(clitanim.tanim_coz({"ad": "ozel", "komut": [sys.executable]}))
    assert motorlar.kurulu_mu("ozel") is True
    assert motorlar.kurulu_mu("hic-yok") is False and motorlar.kurulu_mu("") is False


# ---------- varsayilan ayar uretimi ----------
def test_opencode_ya_da_motor_yoksa_eski_varsayilan_ayar():
    assert motorlar.ayar_uret("opencode-sunucu") == VARSAYILAN_AYAR and motorlar.ayar_uret(None) == VARSAYILAN_AYAR and motorlar.ayar_uret("bilinmeyen") == VARSAYILAN_AYAR
    motorlar.ayar_uret("claude")["roller"]["kodcu"]["talimat"] = "degisti"
    assert VARSAYILAN_AYAR["roller"]["kodcu"]["talimat"] != "degisti"  # derin kopya: orijinal bozulmaz


def test_claude_icin_roller_claude_ve_uygun_modelle_kurulur():
    a = motorlar.ayar_uret("claude")
    assert {r["calistirici"] for r in a["roller"].values()} == {"claude"} and a["roller"]["kodcu"]["model"] == "sonnet" and a["roller"]["test"]["model"] == "haiku"
    assert a["roller"]["test"]["dogrulama"] is True and a["akis"] == ["kodcu", "test"] and a["butce_token"] == VARSAYILAN_AYAR["butce_token"]
    assert a["roller"]["kodcu"]["talimat"] == VARSAYILAN_AYAR["roller"]["kodcu"]["talimat"]


def test_codex_icin_model_belirtilmez():
    a = motorlar.ayar_uret("codex")
    assert {r["calistirici"] for r in a["roller"].values()} == {"codex"} and all("model" not in r for r in a["roller"].values())


@pytest.mark.parametrize("motor", ["opencode-sunucu", "claude", "codex", None])
def test_uretilen_her_ayar_gecerlidir(motor):
    ayar_coz(motorlar.ayar_uret(motor))


# ---------- eksik roller / gecirme ----------
def _ayar(kodcu="opencode-sunucu", test="claude"):
    a = motorlar.ayar_uret("opencode-sunucu")
    a["roller"]["kodcu"]["calistirici"] = kodcu
    a["roller"]["test"]["calistirici"] = test
    a["butce_token"] = 12345
    return a


def test_eksik_roller_yalniz_kurulu_olmayanlari_bulur(monkeypatch):
    kurulu(monkeypatch, claude=True)
    assert motorlar.eksik_roller(_ayar()) == [{"rol": "kodcu", "calistirici": "opencode-sunucu"}]
    kurulu(monkeypatch, opencode=True, claude=True)
    assert motorlar.eksik_roller(_ayar()) == []
    assert motorlar.eksik_roller({}) == [] and motorlar.eksik_roller({"roller": 5}) == [] and motorlar.eksik_roller(None) == []


def test_rolleri_gecir_yalniz_eksik_rolleri_degistirir_digerlerine_dokunmaz(monkeypatch):
    kurulu(monkeypatch, claude=True)
    a = _ayar(kodcu="opencode-sunucu", test="claude")
    a["roller"]["test"]["model"] = "opus"
    yeni, degisen = motorlar.rolleri_gecir(a, "claude")
    assert degisen == ["kodcu"] and yeni["roller"]["kodcu"]["calistirici"] == "claude" and yeni["roller"]["kodcu"]["model"] == "sonnet"
    assert yeni["roller"]["test"] == a["roller"]["test"] and yeni["butce_token"] == 12345  # test rolu (claude, model opus) ve butce AYNEN
    assert a["roller"]["kodcu"]["calistirici"] == "opencode-sunucu"  # girdi degismedi
    ayar_coz(yeni)


def test_rolleri_gecir_ozel_rolde_kodcunun_modelini_kullanir_codexte_model_siler(monkeypatch):
    kurulu(monkeypatch, claude=True, codex=True)
    a = _ayar()
    a["roller"]["gozden"] = {"calistirici": "opencode", "model": "x/y", "talimat": "t"}
    a["akis"] = ["kodcu", "test", "gozden"]
    yeni, degisen = motorlar.rolleri_gecir(a, "claude")
    assert sorted(degisen) == ["gozden", "kodcu"] and yeni["roller"]["gozden"]["model"] == "sonnet"
    yeni2, _ = motorlar.rolleri_gecir(a, "codex")
    assert "model" not in yeni2["roller"]["kodcu"] and yeni2["roller"]["kodcu"]["calistirici"] == "codex"


def test_rolleri_gecir_kurulu_olmayan_ya_da_bilinmeyen_motoru_reddeder(monkeypatch):
    kurulu(monkeypatch, claude=True)
    for kotu in ("codex", "opencode-sunucu", "bilinmeyen", "", None):
        with pytest.raises(ValueError):
            motorlar.rolleri_gecir(_ayar(), kotu)


# ---------- proje hazirlama ----------
def test_yeni_proje_opencode_yoksa_claude_ile_kurulur(monkeypatch, tmp_path):
    kurulu(monkeypatch, claude=True)
    k = tmp_path / "yeni"
    k.mkdir()
    (k / "a.txt").write_text("a")
    hazirla(k)
    roller = json.loads((k / AYAR_KLASORU / ROLLER_DOSYASI).read_text(encoding="utf-8"))["roller"]
    assert {r["calistirici"] for r in roller.values()} == {"claude"}


def test_yeni_proje_hicbir_motor_yoksa_eski_varsayilanla_kurulur(monkeypatch, tmp_path):
    kurulu(monkeypatch)
    k = tmp_path / "yeni"
    k.mkdir()
    hazirla(k)
    assert json.loads((k / AYAR_KLASORU / ROLLER_DOSYASI).read_text(encoding="utf-8")) == VARSAYILAN_AYAR


def test_mevcut_ayar_dosyasi_motor_degisse_de_ezilmez(monkeypatch, tmp_path):
    kurulu(monkeypatch, opencode=True)
    k = tmp_path / "eski"
    k.mkdir()
    hazirla(k)
    yol = k / AYAR_KLASORU / ROLLER_DOSYASI
    yol.write_text(yol.read_text(encoding="utf-8").replace('"butce_token": 200000', '"butce_token": 777'), encoding="utf-8")
    kurulu(monkeypatch, claude=True)  # artik OpenCode yok
    hazirla(k)
    assert json.loads(yol.read_text(encoding="utf-8"))["butce_token"] == 777 and json.loads(yol.read_text(encoding="utf-8"))["roller"]["kodcu"]["calistirici"] == "opencode-sunucu"


# ---------- hata mesajlari ----------
def test_bulunamayan_cli_mesajlari_ne_yapilacagini_soyler(monkeypatch):
    from aktapokus_ajan import runners, sunucu

    monkeypatch.setattr(runners, "claude_bul", lambda: None)
    monkeypatch.setattr(runners, "codex_bul", lambda: None)
    monkeypatch.setattr(runners, "opencode_bul", lambda: None)
    monkeypatch.setattr(sunucu, "opencode_bul", lambda: None)
    for cagri, ipucu in ((lambda: runners.ClaudeCodeCalistirici().komut("a.json", None, True), "Ayarlar > Roller"),
                         (lambda: runners.CodexCalistirici().komut(Path("."), None, True, "s.txt"), "Ayarlar > Roller"),
                         (lambda: runners.OpenCodeCalistirici().komut("g", Path("."), None, None), "Ayarlar > Roller")):
        with pytest.raises(runners.CalistiriciHatasi) as h:
            cagri()
        assert "bulunamadi" in str(h.value) and ipucu in str(h.value)
    with pytest.raises(sunucu.SunucuHatasi, match="bulunamadi.*Ayarlar > Roller"):
        sunucu.Sunucu()._baslat()


# ---------- HTTP ----------
@pytest.fixture
def api(proje, monkeypatch):
    kurulu(monkeypatch, claude=True)
    app = Uygulama()
    sv = ArayuzSunucusu(app)
    sv.baslat()
    yield app, sv, Istemci(sv), proje
    sv.kapat()


def test_motorlar_ucu_belirtec_ister_ve_proje_yokken_eksik_rol_bos(api):
    app, sv, istek, proje = api
    assert istek("GET", "/api/motorlar", token=None)[0] == 401
    st, d = istek("GET", "/api/motorlar")
    assert st == 200 and d["kurulu_sayisi"] == 1 and d["tercih"] == "claude" and d["eksik_roller"] == [] and d["proje_var"] is False


def test_proje_acikken_kurulu_olmayan_cli_a_bagli_roller_listelenir_ve_gecirilir(api):
    app, sv, istek, proje = api
    app.klasor_sec(str(proje))  # hazirla: OpenCode yok, claude var -> yeni proje zaten claude ile kurulur
    assert istek("GET", "/api/motorlar")[1]["eksik_roller"] == []
    a = app.ayar_oku()
    a["roller"]["kodcu"]["calistirici"] = "opencode-sunucu"
    app.ayar_yaz(a)
    d = istek("GET", "/api/motorlar")[1]
    assert d["eksik_roller"] == [{"rol": "kodcu", "calistirici": "opencode-sunucu"}] and d["proje_var"] is True
    st, r = istek("POST", "/api/motorlar/rolleri-gecir", {"calistirici": "claude"})
    assert st == 200 and r["degisen"] == ["kodcu"]
    assert app.ayar_oku()["roller"]["kodcu"]["calistirici"] == "claude" and istek("GET", "/api/motorlar")[1]["eksik_roller"] == []
    assert istek("POST", "/api/motorlar/rolleri-gecir", {"calistirici": "claude"})[0] == 409  # gecirilecek rol kalmadi


def test_rolleri_gecir_gecersiz_girdiler_ve_yabanci_origin(api):
    import http.client

    app, sv, istek, proje = api
    app.klasor_sec(str(proje))
    for govde in ({}, {"calistirici": 5}, {"calistirici": "codex"}, {"calistirici": "yok"}, {"calistirici": ""}):
        assert istek("POST", "/api/motorlar/rolleri-gecir", govde)[0] in (400, 409), govde
    assert istek("POST", "/api/motorlar/rolleri-gecir", {"calistirici": "claude"}, token=None)[0] == 401
    c = http.client.HTTPConnection("127.0.0.1", sv.port, timeout=10)
    c.request("POST", "/api/motorlar/rolleri-gecir", body='{"calistirici":"claude"}', headers={"X-Aktapokus-Token": app.token, "Origin": "http://evil.example", "Content-Type": "application/json"})
    r = c.getresponse()
    r.read()
    c.close()
    assert r.status == 403


def test_gorev_surerken_roller_gecirilemez(proje, monkeypatch):
    kurulu(monkeypatch, claude=True)
    e = Engelli()
    app = Uygulama(calistirici_uret=lambda ad: e)
    sv = ArayuzSunucusu(app)
    sv.baslat()
    try:
        istek = Istemci(sv)
        app.klasor_sec(str(proje))
        a = app.ayar_oku()
        a["roller"]["kodcu"]["calistirici"] = "opencode-sunucu"
        app.ayar_yaz(a)
        plan = app.gorev_olustur("uzun")
        app.onayla(plan["kosu"])
        assert e.basladi.wait(10)
        st, d = istek("POST", "/api/motorlar/rolleri-gecir", {"calistirici": "claude"})
        assert st == 409 and "calisirken" in d["hata"]
        assert app.ayar_oku()["roller"]["kodcu"]["calistirici"] == "opencode-sunucu"
    finally:
        e.serbest.set()
        sv.kapat()


def test_telegram_motor_gecisine_dokunmaz():
    kaynak = (Path(__file__).resolve().parent.parent / "aktapokus_ajan" / "telegram.py").read_text(encoding="utf-8")
    assert "motor_rolleri_gecir" not in kaynak and "motorlar" not in kaynak


def test_arayuz_motor_uyarisini_icerir():
    html = (Path(__file__).resolve().parent.parent / "aktapokus_ajan" / "web" / "index.html").read_text(encoding="utf-8")
    for parca in ('id="motorUyari"', "function motorUyarisi", "/api/motorlar", "/api/motorlar/rolleri-gecir", "hiçbir ajan CLI'ı bulunamadı", "Yeniden kontrol et"):
        assert parca in html, parca
    govde = html.split("async function motorUyarisi")[1].split("(async()=>{if(!T)")[0]
    assert "confirm(" in govde and "innerHTML" not in govde  # degisiklik onayla yapilir; sunucudan gelen metinler textContent ile


def test_durum_komutu_uc_cli_icin_de_bulunamadiysa_uyarir(monkeypatch, capsys, tmp_path):
    from aktapokus_ajan import cli

    for ad in ("opencode_bul", "claude_bul", "codex_bul"):
        monkeypatch.setattr(cli, ad, lambda: None)
    assert cli.main(["durum", "--arac"]) == cli.CIKIS_TAMAM
    cikti = capsys.readouterr().out
    assert "OpenCode CLI: bulunamadi" in cikti and "Claude Code CLI: bulunamadi" in cikti and "Codex CLI: bulunamadi" in cikti and "UYARI: hicbir ajan CLI" in cikti
    monkeypatch.setattr(cli, "claude_bul", lambda: sys.executable)
    monkeypatch.setattr(cli, "_surum_oku", lambda komut: "9.9")
    assert cli.main(["durum", "--arac"]) == cli.CIKIS_TAMAM
    cikti = capsys.readouterr().out
    assert "Claude Code CLI: " + sys.executable in cikti and "UYARI" not in cikti
    monkeypatch.setattr(cli, "codex_bul", lambda: ["node", "codex.js"])  # gercekte liste doner
    assert cli.main(["durum", "--arac"]) == cli.CIKIS_TAMAM
    assert "Codex CLI: node codex.js  9.9" in capsys.readouterr().out


def test_kur_bat_artik_yalniz_opencode_istemez():
    kur = (Path(__file__).resolve().parent.parent / "kur.bat").read_text(encoding="utf-8")
    assert "En az bir ajan CLI kurulu olmali" in kur and "OpenCode kurulu olmali" not in kur
