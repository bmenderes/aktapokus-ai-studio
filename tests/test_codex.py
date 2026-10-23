import copy
import json
import sys
from pathlib import Path

import pytest

from aktapokus_ajan import runners
from aktapokus_ajan.config import BILINEN_CALISTIRICILAR, VARSAYILAN_AYAR, ayar_coz
from aktapokus_ajan.pipeline import calistir_hat
from aktapokus_ajan.runners import CalistiriciHatasi, CodexCalistirici, calistirici_olustur, codex_bul, codex_olaylarini_coz

SAHTE = str(Path(__file__).with_name("sahte_codex.py"))

# Gercek Codex 0.101.0'in (eski surum, yeni modeli reddetti) urettigi satirlar
GERCEK_HATA = "\n".join(
    [
        '{"type":"thread.started","thread_id":"01a163a1"}',
        '{"type":"turn.started"}',
        '{"type":"error","message":"{\\"detail\\":\\"The \'gpt-5.6-terra\' model requires a newer version of Codex. Please upgrade to the latest app or CLI and try again.\\"}"}',
        '{"type":"turn.failed","error":{"message":"{\\"detail\\":\\"The \'gpt-5.6-terra\' model requires a newer version of Codex.\\"}"}}',
    ]
)


# Gercek Codex 0.163.0'in urettigi basarili calisma (kisaltilmis yollarla)
GERCEK_BASARI = "\n".join(
    [
        '{"type":"thread.started","thread_id":"01a163ab"}',
        '{"type":"turn.started"}',
        '{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"Dosyayı oluşturuyorum."}}',
        '{"type":"item.started","item":{"id":"item_1","type":"file_change","changes":[{"path":"C:\\p\\merhaba.txt","kind":"add"}],"status":"in_progress"}}',
        '{"type":"item.completed","item":{"id":"item_1","type":"file_change","changes":[{"path":"C:\\p\\merhaba.txt","kind":"add"}],"status":"completed"}}',
        '{"type":"item.completed","item":{"id":"item_2","type":"agent_message","text":"tamam"}}',
        '{"type":"turn.completed","usage":{"input_tokens":31116,"cached_input_tokens":11008,"cache_write_input_tokens":0,"output_tokens":87,"reasoning_output_tokens":21}}',
    ]
)


def test_gercek_basari_olaylari_0_163():
    r = codex_olaylarini_coz(GERCEK_BASARI)
    assert r.ok and r.metin == "Dosyayı oluşturuyorum.\ntamam"  # dosya degisikligi olayi metne karismaz
    assert (r.token_girdi, r.token_cikti, r.token_onbellek) == (20108, 87, 11008)


def calistirici():
    return CodexCalistirici(komut_oneki=[sys.executable, SAHTE])


def test_gercek_hata_olaylari_ok_false_ve_net_mesaj():
    r = codex_olaylarini_coz(GERCEK_HATA)
    assert not r.ok and "newer version of Codex" in r.hata and r.metin == ""


def test_basari_olaylari_token_ve_son_mesaj_onceligi():
    cikti = "\n".join(
        [
            "gurultu",
            '{"type":"item.completed","item":{"type":"agent_message","text":"ara"}}',
            '{"type":"item.completed","item":{"type":"reasoning","text":"gizli"}}',
            '{"type":"turn.completed","usage":{"input_tokens":100,"cached_input_tokens":30,"output_tokens":10}}',
            '{"type":"turn.completed","usage":{"input_tokens":50,"cached_input_tokens":0,"output_tokens":5}}',
        ]
    )
    r = codex_olaylarini_coz(cikti)
    assert r.ok and r.metin == "ara" and (r.token_girdi, r.token_cikti, r.token_onbellek) == (120, 15, 30)  # girdi = input - cached
    assert codex_olaylarini_coz(cikti, son_mesaj=" nihai cevap ").metin == "nihai cevap"  # -o dosyasi olaylardan uygun


def test_komut_guvenli_bayraklar_ve_istem_argumanda_degil(tmp_path):
    c = CodexCalistirici(komut_oneki=["node", "codex.js"])
    k = c.komut(tmp_path, "gpt-x", True, "son.txt")
    assert k[:3] == ["node", "codex.js", "exec"] and k[-1] == "-"  # istem stdin'den
    assert k[k.index("--sandbox") + 1] == "workspace-write" and "--json" in k and "--skip-git-repo-check" in k
    assert k[k.index("-C") + 1] == str(tmp_path) and k[k.index("-m") + 1] == "gpt-x" and 'approval_policy="never"' in k
    assert "danger-full-access" not in k and "--dangerously-bypass-approvals-and-sandbox" not in k and "--full-auto" not in k
    assert c.komut(tmp_path, None, False, "s")[c.komut(tmp_path, None, False, "s").index("--sandbox") + 1] == "read-only"
    assert "-m" not in c.komut(tmp_path, None, True, "s")


def test_istem_stdinden_aynen_gider_ozel_karakterler_dahil(tmp_path, monkeypatch):
    kayit = tmp_path / "kayit.json"
    monkeypatch.setenv("SAHTE_CODEX_KAYIT", str(kayit))
    istem = 'tirnak " ve & | ; $(x) %PATH% -c satir\nsonu ç ğ ş ' + "x" * 30000  # argv sinirini asan uzun istem de calisir
    r = calistirici().calistir(istem, tmp_path)
    assert r.ok
    k = json.loads(kayit.read_text(encoding="utf-8"))
    assert k["istem"] == istem and istem[:40] not in " ".join(k["args"])
    assert k["pwd"] == str(tmp_path) and Path(k["cwd"]) == tmp_path  # PWD alt surece hedef klasor olarak verilir


def test_calistir_basari_metin_token_ve_dosya(tmp_path):
    r = calistirici().calistir("gorev DOSYA:yeni.txt", tmp_path, model="m1")
    assert r.ok and r.metin == "Bitti.\nSONUC: BASARILI"  # -o dosyasindaki nihai mesaj
    assert (r.token_girdi, r.token_cikti, r.token_onbellek) == (80, 30, 40)
    assert (tmp_path / "yeni.txt").read_text(encoding="utf-8") == "codex yazdi\n"


def test_salt_okunur_modda_dosya_yazilmaz(tmp_path):
    r = calistirici().calistir("gorev DOSYA:yeni.txt", tmp_path, onayli=False)
    assert r.ok and not (tmp_path / "yeni.txt").exists()


def test_basarisiz_calisma_hatasi_ve_cikis_kodu(tmp_path):
    r = calistirici().calistir("FAIL", tmp_path)
    assert not r.ok and "newer version of Codex" in r.hata


def test_cikis_kodu_sifir_degilse_ve_olay_yoksa_hata_olur(tmp_path, monkeypatch):
    sahte = tmp_path / "patla.py"
    sahte.write_text("import sys; sys.stdin.read(); sys.stderr.write('ic hata'); sys.exit(7)", encoding="utf-8")
    r = CodexCalistirici(komut_oneki=[sys.executable, str(sahte)]).calistir("x", tmp_path)
    assert not r.ok and "cikis kodu 7" in r.hata and "ic hata" in r.hata


def test_zaman_asimi(tmp_path):
    r = calistirici().calistir("YAVAS", tmp_path, zaman_asimi_sn=1)
    assert not r.ok and "Zaman asimi (1 sn)" in r.hata


def test_gecersiz_istem_ve_cli_yok(tmp_path, monkeypatch):
    with pytest.raises(CalistiriciHatasi):
        calistirici().calistir("   ", tmp_path)
    monkeypatch.setattr(runners, "codex_bul", lambda: None)
    with pytest.raises(CalistiriciHatasi, match="Codex CLI bulunamadi"):
        CodexCalistirici().komut(tmp_path, None, True, "s")


def test_codex_bul_sarmalayici_kullanmaz(tmp_path, monkeypatch):
    monkeypatch.delenv("AKTAPOKUS_CODEX", raising=False)
    npm = tmp_path / "npm"
    (npm / "node_modules" / "@openai" / "codex" / "bin").mkdir(parents=True)
    for ad in ("codex.cmd", "codex.ps1", "codex"):
        (npm / ad).write_text("sarmalayici")  # yalniz sarmalayicilar var, codex.js yok
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(runners.shutil, "which", lambda ad: {"node": "node.exe", "npm": str(npm / "npm.cmd"), "codex": str(npm / "codex.cmd")}.get(ad))
    assert codex_bul() is None  # .cmd/.ps1 asla dondurulmez (cmd.exe arguman yorumlama riski)
    js = npm / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
    js.write_text("//")
    assert codex_bul() == ["node.exe", str(js)]
    ozel = tmp_path / "ozel-codex.js"
    ozel.write_text("//")
    monkeypatch.setenv("AKTAPOKUS_CODEX", str(ozel))
    assert codex_bul() == ["node.exe", str(ozel)]


def test_codex_rolu_kabul_edilir_ve_fabrika():
    assert "codex" in BILINEN_CALISTIRICILAR
    assert isinstance(calistirici_olustur("codex"), CodexCalistirici)
    veri = copy.deepcopy(VARSAYILAN_AYAR)
    veri["roller"]["kodcu"].update(calistirici="codex", model="gpt-x")
    assert ayar_coz(veri).roller["kodcu"].calistirici == "codex"


def test_hat_codex_kodcu_opencode_test_karisik_roller(proje):
    """Ayni projede iki farkli CLI: kodcu=Codex (sahte), test=baska calistirici. Baglam dosyasi ikisi icin de hazir."""
    from conftest import SahteCalistirici, sonuc

    veri = copy.deepcopy(VARSAYILAN_AYAR)
    veri["roller"]["kodcu"].update(calistirici="codex", model=None)
    test_c = SahteCalistirici({"test": lambda k, i, n: sonuc("SONUC: BASARILI")})
    codex_c = calistirici()
    uretilen = []

    def uret(ad):
        uretilen.append(ad)
        return codex_c if ad == "codex" else test_c

    s = calistir_hat(proje, "DOSYA:codex-dosyasi.txt ekle", ayar_coz(veri), uret, lambda q: True)
    assert uretilen == ["codex", "opencode-sunucu"] and s.durum == "onaylandi"  # test rolu varsayilan calistiriciyi kullanir
    assert s.degisen == {"codex-dosyasi.txt": "A"}  # AGENTS.md ajanin degisikligi sayilmadi (snapshot'tan once uretildi)
    assert (proje / "AGENTS.md").is_file() and "aktapokus:basla" in (proje / "AGENTS.md").read_text(encoding="utf-8")


# ---------- Codex'in OpenCode koruyucusu YOK: gizli dosya taramasi (gercek denemede .env okundu ve yanitta gorundu) ----------
from aktapokus_ajan import guard
from aktapokus_ajan.pipeline import HatHatasi


def codex_ayari(**rol_ek):
    veri = copy.deepcopy(VARSAYILAN_AYAR)
    veri["roller"]["kodcu"].update(calistirici="codex", **rol_ek)
    return ayar_coz(veri)


@pytest.mark.parametrize("ad", [".env", ".env.local", ".env.production", "anahtar.pem", "x.KEY", "id_rsa", "id_ed25519.pub", ".npmrc", "credentials.json", "a.pfx", "k.p12", "s.jks", "s.keystore", ".pypirc"])
def test_hassas_dosya_adlari_bulunur(tmp_path, ad):
    (tmp_path / "alt").mkdir()
    (tmp_path / "alt" / ad).write_text("x")
    assert guard.hassas_dosyalar(tmp_path) == [f"alt/{ad}"]


def test_ornek_dosyalar_ve_atlanan_klasorler_sayilmaz(tmp_path):
    for ad in (".env.example", ".env.sample", ".env.template", "readme.md", "anahtar.txt", "keyboard.py"):
        (tmp_path / ad).write_text("x")
    for kl in ("node_modules", ".git", ".venv", "dist"):
        (tmp_path / kl).mkdir()
        (tmp_path / kl / ".env").write_text("x")
    assert guard.hassas_dosyalar(tmp_path) == []


def test_hassas_tarama_sinirli(tmp_path):
    for i in range(30):
        (tmp_path / f".env.{i}").write_text("x")
    assert len(guard.hassas_dosyalar(tmp_path, azami_sonuc=5)) == 5
    for i in range(50):
        (tmp_path / f"d{i}.txt").write_text("x")
    assert guard.hassas_dosyalar(tmp_path, azami_tarama=10, azami_sonuc=100) != guard.hassas_dosyalar(tmp_path, azami_tarama=10_000, azami_sonuc=100)  # tarama siniri isliyor


def test_codex_rolu_hassas_dosya_varken_calismaz_hicbir_sey_baslamaz(proje):
    from conftest import SahteCalistirici, sonuc

    (proje / ".env").write_text("SECRET=abc123", encoding="utf-8")
    c = SahteCalistirici({"kodcu": lambda *a: sonuc("x"), "test": lambda *a: sonuc("SONUC: BASARILI")})
    mesajlar = []
    with pytest.raises(HatHatasi, match=r"\.env.*codex.*OKUYUP") as h:
        calistir_hat(proje, "g", codex_ayari(), lambda ad: c, lambda q: True, mesajlar.append)
    assert "abc123" not in str(h.value) and "okuma_riski_kabul" in str(h.value)  # dosya ADI gosterilir, ICERIGI degil
    assert c.cagrilar == [] and any("OpenCode koruyucusu" in m for m in mesajlar)  # hicbir rol calismadi; uyari verildi


def test_risk_kabul_edilirse_calisir_ve_gizli_dosya_yoksa_zaten_calisir(proje):
    from conftest import SahteCalistirici, sonuc

    c = SahteCalistirici({"kodcu": lambda *a: sonuc("x"), "test": lambda *a: sonuc("SONUC: BASARILI")})
    assert calistir_hat(proje, "g", codex_ayari(), lambda ad: c, lambda q: True).durum == "degisiklik_yok"  # .env yok: engel yok
    (proje / ".env").write_text("SECRET=abc123", encoding="utf-8")
    c2 = SahteCalistirici({"kodcu": lambda *a: sonuc("x"), "test": lambda *a: sonuc("SONUC: BASARILI")})
    s = calistir_hat(proje, "g", codex_ayari(okuma_riski_kabul=True), lambda ad: c2, lambda q: True)  # bilerek kabul
    assert s.durum == "degisiklik_yok" and len(c2.cagrilar) == 2


def test_opencode_rolleri_bu_denetimden_etkilenmez_claude_etkilenir(proje):
    from conftest import SahteCalistirici, sonuc

    (proje / ".env").write_text("SECRET=abc123", encoding="utf-8")
    c = SahteCalistirici({"kodcu": lambda *a: sonuc("x"), "test": lambda *a: sonuc("SONUC: BASARILI")})
    assert calistir_hat(proje, "g", ayar_coz(VARSAYILAN_AYAR), lambda ad: c, lambda q: True).durum == "degisiklik_yok"  # OpenCode: koruyucu .env'i engelliyor
    veri = copy.deepcopy(VARSAYILAN_AYAR)
    veri["roller"]["test"]["calistirici"] = "claude"
    with pytest.raises(HatHatasi, match="claude"):
        calistir_hat(proje, "g", ayar_coz(veri), lambda ad: c, lambda q: True)


def test_okuma_riski_alani_dogrulanir():
    veri = copy.deepcopy(VARSAYILAN_AYAR)
    veri["roller"]["kodcu"]["okuma_riski_kabul"] = "evet"
    with pytest.raises(Exception, match="okuma_riski_kabul"):
        ayar_coz(veri)
