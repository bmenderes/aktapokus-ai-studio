"""Gorev = konusma: olay gunlugu saklanir ve AYNEN yeniden oynatilir; sabitle/arsivle/okunmadi/yeniden adlandir/sil; klasoru ac; Claude Code'da devam et."""

import base64
import json
import time
from pathlib import Path

import pytest

from aktapokus_ai_studio import gorevmeta, projeler
from aktapokus_ai_studio.arayuz import ArayuzSunucusu, Uygulama, _olaylar_uret
from conftest import SahteCalistirici, sonuc
from test_arayuz import Istemci, bekle
from test_uzak import ac, sunucu as uzak_sunucu, uzak_istek, ortam  # noqa: F401  (pytest fixture'lari)

OTURUM = "11111111-2222-3333-4444-555555555555"


class AkisliSahte(SahteCalistirici):
    """Canli olay yayar (arac karti + akici metin) ve konusma kimligi dondurur: gercek Claude/OpenCode calistiricisi gibi."""

    ilerleme = None

    def calistir(self, istem, klasor, model=None, agent=None, zaman_asimi_sn=900, onayli=True):
        if self.ilerleme:
            self.ilerleme({"tur": "arac", "ad": "Read", "girdi": {"file_path": "a.txt", "buyuk": "B" * 500}})
            self.ilerleme({"tur": "metin", "parca": "akici metin parcasi"})
            self.ilerleme({"tur": "arac-sonuc"})
        r = super().calistir(istem, klasor, model, agent, zaman_asimi_sn, onayli)
        r.oturum = OTURUM
        return r


@pytest.fixture
def api(proje):
    def uret(ad):
        return AkisliSahte({"kodcu": lambda k, i, n: sonuc("Dosyalari inceledim; sorun yok."), "test": lambda k, i, n: sonuc("SONUC: BASARILI")})

    app = Uygulama(calistirici_uret=uret)
    sv = ArayuzSunucusu(app)
    sv.baslat()
    app.klasor_sec(str(proje))
    yield app, Istemci(sv), proje
    sv.kapat()


def gorev_calistir(app, istek, metin="projeyi incele"):
    st, plan = istek("POST", "/api/gorev", {"gorev": metin})
    istek("POST", f"/api/gorev/{plan['kosu']}/onayla", {})
    assert bekle(lambda: app.kosu and app.kosu.durum == "bitti")
    st, d = istek("GET", "/api/gecmis")
    return d["gecmis"][0]["id"]


def kayit_yaz(proje, kimlik, **ek):
    klasor = proje / ".aktapokus" / "kayit"
    klasor.mkdir(parents=True, exist_ok=True)
    k = {"id": kimlik, "zaman": "2026-10-26 14:21:59", "gorev": "eski gorev", "akis": ["kodcu"], "durum": "degisiklik_yok", "korundu": False, "mesaj": "m", "token_toplam": 30,
         "butce_token": 1000, "once": "a" * 8, "sonra": "b" * 8, "degisen": {}, "adimlar": [{"sira": 1, "rol": "kodcu", "calistirici": "claude", "model": "sonnet", "ok": True,
         "metin": "yanit metni", "token_girdi": 20, "token_cikti": 10, "token_onbellek": 0, "sure_sn": 1.5}]}
    k.update(ek)
    (klasor / f"{kimlik}.json").write_text(json.dumps(k), encoding="utf-8")
    return k


# ---------- olay gunlugu ----------
def test_gorevin_konusmasi_kayitla_saklanir_akici_metin_ve_buyuk_girdiler_saklanmaz(api):
    app, istek, proje = api
    kimlik = gorev_calistir(app, istek)
    yol = proje / ".aktapokus" / "kayit" / "olaylar" / f"{kimlik}.json"
    olaylar = json.loads(yol.read_text(encoding="utf-8"))
    turler = [o["tur"] for o in olaylar]
    assert turler[0] == "plan" and "basladi" in turler and turler.count("adim-basladi") >= 1 and turler[-1] == "bitti"
    arac = next(o for o in olaylar if o["tur"] == "canli")
    assert arac["alt"] == "arac" and arac["ad"] == "Read" and len(arac["girdi"]["buyuk"]) == 200
    assert not any(o["tur"] == "canli" and o.get("alt") != "arac" for o in olaylar) and "akici metin" not in yol.read_text(encoding="utf-8")
    assert "proje" not in olaylar[0]  # akis etiketi saklanmaz


def test_gecmis_detayi_olaylari_ve_claude_konusmasini_dondurur_kayit_listesi_olay_dosyasini_saymaz(api):
    app, istek, proje = api
    kimlik = gorev_calistir(app, istek)
    st, d = istek("GET", f"/api/gecmis?id={kimlik}")
    assert st == 200 and d["olaylar"][0]["tur"] == "plan" and d["oturum"] == OTURUM
    assert any(a.get("oturum") == OTURUM for a in d["adimlar"])  # kayitta duran konusma kimligi
    assert len(istek("GET", "/api/gecmis")[1]["gecmis"]) == 1  # olaylar/ alt klasoru ikinci bir kayit gibi listelenmez


def test_olay_gunlugu_olmayan_eski_kayit_konusma_olarak_kayittan_uretilir(api):
    app, istek, proje = api
    kayit_yaz(proje, "eski1", degisen={"a.txt": "M"})
    st, d = istek("GET", "/api/gecmis?id=eski1")
    turler = [o["tur"] for o in d["olaylar"]]
    assert st == 200 and turler == ["plan", "basladi", "adim-basladi", "adim-bitti", "fark", "bitti"]
    assert d["olaylar"][3]["metin"] == "yanit metni" and d["olaylar"][0]["gorev"] == "eski gorev" and d["oturum"] is None


def test_olaylar_uret_dogrulama_ve_hata_adimlarini_da_kapsar():
    k = {"id": "x", "gorev": "g", "durum": "dogrulama_basarisiz", "token_toplam": 5, "adimlar": [
        {"sira": 1, "rol": "kodcu", "ok": True, "metin": "a", "token_girdi": 1, "token_cikti": 1},
        {"sira": 2, "rol": "test", "ok": False, "hata": "patladi", "metin": "", "dogrulama": "basarisiz", "token_girdi": 2, "token_cikti": 1}]}
    turler = [o["tur"] for o in _olaylar_uret(k)]
    assert turler == ["plan", "basladi", "adim-basladi", "adim-bitti", "adim-basladi", "adim-bitti", "dogrulama", "bitti"]


def test_bozuk_olay_dosyasi_kayittan_uretime_duser(api):
    app, istek, proje = api
    kayit_yaz(proje, "bozuk1")
    olay = proje / ".aktapokus" / "kayit" / "olaylar"
    olay.mkdir(parents=True)
    (olay / "bozuk1.json").write_text("{bozuk", encoding="utf-8")
    assert istek("GET", "/api/gecmis?id=bozuk1")[1]["olaylar"][0]["tur"] == "plan"


# ---------- sabitle / arsivle / okunmadi / ad ----------
def gruptaki(istek, proje):
    pid = projeler.proje_kimligi(proje)
    return next(g for g in istek("GET", "/api/proje-gruplari")[1]["projeler"] if g["id"] == pid)


def test_gorev_meta_sabit_ustte_arsiv_ayri_okunmadi_ve_ozel_ad(api):
    app, istek, proje = api
    for i in ("g1", "g2", "g3"):
        kayit_yaz(proje, i, zaman=f"2026-10-26 14:2{i[-1]}:00", gorev=f"gorev {i}")
    assert [t["id"] for t in gruptaki(istek, proje)["gorevler"]] == ["g3", "g2", "g1"]  # yeniden eskiye
    assert istek("POST", "/api/gorev-meta", {"id": "g1", "sabit": True})[0] == 200
    assert [t["id"] for t in gruptaki(istek, proje)["gorevler"]][0] == "g1" and gruptaki(istek, proje)["gorevler"][0]["sabit"] is True  # sabit en uste
    assert istek("POST", "/api/gorev-meta", {"id": "g2", "arsiv": True})[0] == 200
    g = gruptaki(istek, proje)
    assert [t["id"] for t in g["gorevler"]] == ["g1", "g3"] and [t["id"] for t in g["arsiv"]] == ["g2"]
    assert all(t["id"] != "g2" for t in istek("GET", "/api/proje-gruplari")[1]["son"])  # arsivlenen 'Son gorevler'de yok
    istek("POST", "/api/gorev-meta", {"id": "g3", "okunmadi": True, "ad": "Benim adim"})
    t3 = next(t for t in gruptaki(istek, proje)["gorevler"] if t["id"] == "g3")
    assert t3["okunmadi"] is True and t3["ozel_ad"] == "Benim adim"
    istek("POST", "/api/gorev-meta", {"id": "g3", "okunmadi": False, "ad": ""})  # geri al / varsayilan ad
    t3 = next(t for t in gruptaki(istek, proje)["gorevler"] if t["id"] == "g3")
    assert t3["okunmadi"] is False and t3["ozel_ad"] is None
    istek("POST", "/api/gorev-meta", {"id": "g2", "arsiv": False})
    assert "g2" in [t["id"] for t in gruptaki(istek, proje)["gorevler"]]


def test_gorev_meta_gecersiz_girdiler_reddedilir_ve_proje_klasorunden_okunmaz(api, tmp_path):
    app, istek, proje = api
    kayit_yaz(proje, "g1")
    for govde in ({"id": "g1", "sabit": "evet"}, {"id": "g1", "ad": "iki\nsatir"}, {"id": "g1", "ad": "x" * 121}, {"id": "g1", "bilinmeyen": True}, {"id": "g1"}):
        assert istek("POST", "/api/gorev-meta", govde)[0] == 400, govde
    assert istek("POST", "/api/gorev-meta", {"id": "yok", "sabit": True})[0] == 404
    assert istek("POST", "/api/gorev-meta", {"id": "../x", "sabit": True})[0] == 400
    # zehirli depo: proje klasorune konan meta dosyasi gorev listesini gizleyemez
    (proje / ".aktapokus" / "gorev-meta.json").write_text(json.dumps({"g1": {"arsiv": True}}), encoding="utf-8")
    assert [t["id"] for t in gruptaki(istek, proje)["gorevler"]] == ["g1"]


def test_gorevmeta_modulu_sinirlar_ve_temizlik(tmp_path):
    p = "a" * 10
    assert gorevmeta.ayarla(p, "g1", sabit=True) == {"sabit": True}
    assert gorevmeta.ayarla(p, "g1", sabit=False) == {} and gorevmeta.proje_icin(p) == {}  # bos kayit silinir
    for kotu in ("A" * 10, "xyz", None, "../etc"):
        with pytest.raises(gorevmeta.GorevMetaHatasi):
            gorevmeta.ayarla(kotu, "g1", sabit=True)
    dosya = gorevmeta.dosya_yolu()
    dosya.write_text(json.dumps({p: {"../x": {"arsiv": True}, "ok": {"sabit": "true", "ad": 5}, "iyi": {"sabit": True}}}), encoding="utf-8")
    assert gorevmeta.proje_icin(p) == {"iyi": {"sabit": True}}  # bozuk girdiler yok sayilir
    dosya.write_text("{bozuk", encoding="utf-8")
    assert gorevmeta.proje_icin(p) == {}


# ---------- sil ----------
def test_gorev_sil_kayit_olaylar_ve_metayi_kaldirir(api):
    app, istek, proje = api
    kimlik = gorev_calistir(app, istek)
    istek("POST", "/api/gorev-meta", {"id": kimlik, "sabit": True})
    assert istek("POST", "/api/gorev-sil", {"id": kimlik})[0] == 200
    assert not (proje / ".aktapokus" / "kayit" / f"{kimlik}.json").exists() and not (proje / ".aktapokus" / "kayit" / "olaylar" / f"{kimlik}.json").exists()
    assert gorevmeta.proje_icin(projeler.proje_kimligi(proje)) == {}
    assert istek("POST", "/api/gorev-sil", {"id": kimlik})[0] == 404 and istek("GET", f"/api/gecmis?id={kimlik}")[0] == 404
    assert istek("POST", "/api/gorev-sil", {"id": "../x"})[0] == 400


# ---------- klasoru ac ----------
def test_klasor_ac_gezgin_ve_vscode_yalniz_kayitli_proje_klasorunu_acar(api, monkeypatch, tmp_path):
    app, istek, proje = api
    acilan = []
    monkeypatch.setattr(Uygulama, "_gezgini_ac", staticmethod(lambda yol: acilan.append(("gezgin", yol))))
    monkeypatch.setattr(Uygulama, "_program_ac", staticmethod(lambda argv: acilan.append(("program", argv))))
    assert istek("POST", "/api/klasor-ac", {"hedef": "gezgin", "yol": "C:/baska"})[0] == 200  # istemci yol veremez: yok sayilir
    assert acilan == [("gezgin", str(proje.resolve()))]
    sahte_code = tmp_path / "Code.exe"
    sahte_code.write_text("")
    monkeypatch.setenv("AKTAPOKUS_VSCODE", str(sahte_code))
    assert istek("POST", "/api/klasor-ac", {"hedef": "vscode"})[0] == 200
    assert acilan[-1] == ("program", [str(sahte_code), str(proje.resolve())])
    monkeypatch.setenv("AKTAPOKUS_VSCODE", str(tmp_path / "yok.exe"))
    monkeypatch.setattr("aktapokus_ai_studio.arayuz.shutil.which", lambda a: None)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "bos"))
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path / "bos"))
    st, d = istek("POST", "/api/klasor-ac", {"hedef": "vscode"})
    assert st == 404 and "VS Code" in d["hata"]
    assert istek("POST", "/api/klasor-ac", {"hedef": "cmd"})[0] == 400 and istek("POST", "/api/klasor-ac", {})[0] == 400


# ---------- Claude Code'da devam et ----------
def test_claude_devam_terminalde_ayni_konusmayi_surdurur(api, monkeypatch):
    app, istek, proje = api
    kimlik = gorev_calistir(app, istek)
    girdiler = []
    monkeypatch.setattr(app, "terminal_ac", lambda *a, **k: {"id": "t1"})
    monkeypatch.setattr(app, "terminal_girdi", lambda tid, b64: girdiler.append((tid, base64.b64decode(b64).decode())) or {"tamam": True})
    monkeypatch.setattr("aktapokus_ai_studio.arayuz.claude_bul", lambda: r"C:\Program Files\o'brien\claude.exe")
    st, d = istek("POST", "/api/claude-devam", {"id": kimlik})
    assert st == 200 and d == {"terminal": "t1"}
    assert girdiler == [("t1", "& 'C:\\Program Files\\o''brien\\claude.exe' --resume " + OTURUM + "\r")]  # tirnak kacirilir


def test_claude_devam_konusma_yoksa_ya_da_kayit_zehirliyse_calistirmaz(api, monkeypatch):
    app, istek, proje = api
    girdiler = []
    monkeypatch.setattr(app, "terminal_ac", lambda *a, **k: {"id": "t1"})
    monkeypatch.setattr(app, "terminal_girdi", lambda tid, b64: girdiler.append(b64))
    kayit_yaz(proje, "yok1")  # Claude konusmasi kaydi yok
    assert istek("POST", "/api/claude-devam", {"id": "yok1"})[0] == 404
    k = kayit_yaz(proje, "zehir1")
    k["adimlar"][0]["oturum"] = "x'; calc.exe; '"  # proje klasorundeki kayit guvenilmez
    (proje / ".aktapokus" / "kayit" / "zehir1.json").write_text(json.dumps(k), encoding="utf-8")
    assert istek("POST", "/api/claude-devam", {"id": "zehir1"})[0] == 404 and girdiler == []
    assert istek("POST", "/api/claude-devam", {"id": "bulunmayan"})[0] == 404


# ---------- uzak politika ----------
def test_uzaktan_silme_klasor_acma_ve_claude_devam_kapali_meta_serbest(uzak_sunucu):
    app, sv, yerel, proje = uzak_sunucu
    port, _ = ac(yerel)
    for yol, govde in (("/api/gorev-sil", {"id": "x"}), ("/api/klasor-ac", {"hedef": "gezgin"}), ("/api/claude-devam", {"id": "x"})):
        st, d = uzak_istek(port, "POST", yol, govde)
        assert st == 403 and "uzaktan kapali" in d["hata"], yol
    st, _ = uzak_istek(port, "POST", "/api/gorev-meta", {"id": "yok", "sabit": True})
    assert st == 404  # yetki engeli yok: gorev bulunamadi (telefondan sabitle/arsivle serbest)


# ---------- Claude konusma kimligi ----------
def test_claude_calistirici_konusma_kimligini_sonuca_koyar_hic_kipinde_koymaz(monkeypatch, tmp_path):
    from aktapokus_ai_studio import runners
    from sahte_popen import claude_taklit, sonuc_olayi

    claude_taklit(monkeypatch, runners, olaylar=[sonuc_olayi("x", oturum=OTURUM)])
    for kip, beklenen in (("tek", OTURUM), ("yeni", OTURUM), ("hic", None)):
        c = runners.ClaudeCodeCalistirici(cli_yolu="cl")
        c.oturum_kipi = kip
        assert c.calistir("istem", tmp_path).oturum == beklenen, kip


# ---------- Claude Code konusmalari (kullanicinin kendi etkilesimli konusmalari dahil) ----------
def _claude_konusmasi_yaz(proje):
    from aktapokus_ai_studio import claude_oturumlari as co

    d = co.kok() / co.klasor_kodu(proje.resolve())
    d.mkdir(parents=True, exist_ok=True)
    kimlik = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    satirlar = [{"type": "user", "message": {"content": "Selam, dosyalari listele"}, "timestamp": "t1"},
                {"type": "assistant", "message": {"content": [{"type": "text", "text": "Tamam"}]}, "timestamp": "t2"}]
    (d / f"{kimlik}.jsonl").write_text("\n".join(json.dumps(s) for s in satirlar), encoding="utf-8")
    return kimlik


def test_claude_konusmalari_listelenir_okunur_ve_terminalde_surdurulur(api, monkeypatch):
    app, istek, proje = api
    kimlik = _claude_konusmasi_yaz(proje)
    st, d = istek("GET", "/api/claude-oturumlari")
    assert st == 200 and d["oturumlar"][0]["kimlik"] == kimlik and d["oturumlar"][0]["baslik"].startswith("Selam")
    st, d = istek("GET", "/api/claude-konusma?id=" + kimlik)
    assert st == 200 and [o["tur"] for o in d["olaylar"]] == ["claude-kullanici", "claude-yanit"]
    assert istek("GET", "/api/claude-konusma?id=../x")[0] == 400 and istek("GET", "/api/claude-konusma?id=" + "0" * 8 + kimlik[8:])[0] == 404
    girdiler = []
    monkeypatch.setattr(app, "terminal_ac", lambda *a, **k: {"id": "t9"})
    monkeypatch.setattr(app, "terminal_girdi", lambda tid, b64: girdiler.append(base64.b64decode(b64).decode()) or {"tamam": True})
    monkeypatch.setattr("aktapokus_ai_studio.arayuz.claude_bul", lambda: r"C:\c\claude.exe")
    assert istek("POST", "/api/claude-surdur", {"id": kimlik})[1] == {"terminal": "t9"} and girdiler == [r"& 'C:\c\claude.exe' --resume " + kimlik + "\r"]
    assert istek("POST", "/api/claude-surdur", {"id": "x'; calc; '"})[0] == 404 and len(girdiler) == 1


def test_uzaktan_claude_konusmalari_kapali(uzak_sunucu):
    app, sv, yerel, proje = uzak_sunucu
    port, _ = ac(yerel)
    for yontem, yol, govde in (("GET", "/api/claude-oturumlari", None), ("GET", "/api/claude-konusma?id=x", None), ("POST", "/api/claude-surdur", {"id": "x"})):
        st, d = uzak_istek(port, yontem, yol, govde)
        assert st == 403 and "uzaktan kapali" in d["hata"], yol
