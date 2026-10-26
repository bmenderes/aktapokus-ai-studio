"""Claude Code <-> Aktapokus haberlesmesi: canli durum dosyasi, kanca ozeti, oturum basina 'yeni olan' isareti, Claude konusma okuyucu."""

import json
import os
import time

from aktapokus_ai_studio import canli, claude_oturumlari, haber, projeler


def _gorev(proje="p1"):
    canli.olay(proje, "demo", "C:/demo", {"tur": "plan", "gorev": "Giris sayfasini ekle"})
    canli.olay(proje, "demo", "C:/demo", {"tur": "adim-basladi", "rol": "kodlayici", "sira": 1, "model": "m1"})
    canli._son_yazma = 0.0  # arac olaylari araliklidir: testte hemen yazilsin
    canli.olay(proje, "demo", "C:/demo", {"tur": "canli", "alt": "arac", "ad": "Edit", "girdi": {"file_path": "a.py"}})


def test_canli_olay_durumu_ve_son_araci_yazar():
    _gorev()
    v = canli.oku()
    d = v["projeler"]["p1"]
    assert d["durum"] == "calisiyor" and d["rol"] == "kodlayici" and d["son_arac"].startswith("Edit a.py")
    assert v["pid"] == os.getpid()
    canli.olay("p1", "demo", "C:/demo", {"tur": "karar-bekleniyor"})
    assert canli.oku()["projeler"]["p1"]["durum"] == "karar-bekliyor"


def test_ozet_calisan_gorevi_gosterir_bayat_dosyayi_yoksayar(monkeypatch):
    _gorev()
    metin, _ = haber.ozet(None)
    assert "CALISIYOR" in metin and "Giris sayfasini ekle" in metin and "kodlayici" in metin
    v = canli.oku()
    v["guncelleme"] = time.time() - 4000  # uygulama kapanmis: bayat
    canli.dosya_yolu().write_text(json.dumps(v), encoding="utf-8")
    assert haber.ozet(None)[0] == ""
    v["guncelleme"] = time.time()
    v["pid"] = 2 ** 22 + 12345  # olu surec
    canli.dosya_yolu().write_text(json.dumps(v), encoding="utf-8")
    monkeypatch.setattr("aktapokus_ai_studio.uygulama.surec_canli_mi", lambda pid: False)
    assert haber.ozet(None)[0] == ""


def test_kanca_ayni_durumu_tekrar_vermez_yeni_olani_verir():
    _gorev()
    ilk = haber.kanca("oturum-a")
    assert "CALISIYOR" in ilk
    assert haber.kanca("oturum-a") == ""  # degisen yok: baglam sismez
    assert "CALISIYOR" in haber.kanca("oturum-b")  # baska oturum kendi isaretini tasir
    canli.olay("p1", "demo", "C:/demo", {"tur": "karar-bekleniyor"})
    assert "KARAR BEKLIYOR" in haber.kanca("oturum-a")


def test_kanca_biten_gorevi_kayittan_bildirir_bir_kez(tmp_path):
    klasor = tmp_path / "proje"
    (klasor / ".aktapokus" / "kayit").mkdir(parents=True)
    projeler.ekle_veya_guncelle(klasor)
    (klasor / ".aktapokus" / "kayit" / "k1.json").write_text(json.dumps({"gorev": "Hata duzelt", "durum": "tamam", "zaman": "2026-10-26 10:15:00", "token_toplam": 4200, "adimlar": [{"metin": "Duzeltildi"}], "degisen": {"a.py": "x"}}), encoding="utf-8")
    metin = haber.kanca("o1")
    assert "BITTI" in metin and "Hata duzelt" in metin and "a.py" in metin and "Duzeltildi" in metin
    assert haber.kanca("o1") == ""


def test_kanca_hatada_bos_doner_ve_gecersiz_kimlikle_calisir(monkeypatch):
    assert haber.kanca(None) == "" and haber.kanca(123) == ""
    haber.durum_yolu().write_text("{bozuk", encoding="utf-8")
    assert haber.kanca("x") == ""


def test_claude_konusmalari_listelenir_ve_okunur(tmp_path, monkeypatch):
    klasor = tmp_path / "Demo Proje"
    klasor.mkdir()
    kok = claude_oturumlari.kok()
    d = kok / claude_oturumlari.klasor_kodu(klasor)
    d.mkdir(parents=True)
    kimlik = "11111111-2222-3333-4444-555555555555"
    satirlar = [
        {"type": "user", "message": {"role": "user", "content": "Merhaba, testleri calistir"}, "timestamp": "t1"},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "Calistiriyorum"}, {"type": "tool_use", "name": "Bash", "input": {"command": "pytest"}}]}, "timestamp": "t2"},
        {"type": "user", "message": {"content": "<system-reminder>x</system-reminder>"}, "timestamp": "t3"},
    ]
    (d / f"{kimlik}.jsonl").write_text("\n".join(json.dumps(s) for s in satirlar), encoding="utf-8")
    (d / "not-a-session.jsonl").write_text("{}", encoding="utf-8")
    liste = claude_oturumlari.listele(klasor)
    assert [x["kimlik"] for x in liste] == [kimlik] and liste[0]["baslik"].startswith("Merhaba") and liste[0]["canli"]
    k = claude_oturumlari.konusma(klasor, kimlik)
    assert [o["tur"] for o in k["olaylar"]] == ["claude-kullanici", "claude-yanit", "claude-arac"]
    assert claude_oturumlari.var_mi(klasor, kimlik) and not claude_oturumlari.var_mi(klasor, "../x")
    for kotu in ("../../etc", "abc", None):
        try:
            claude_oturumlari.konusma(klasor, kotu)
            assert False
        except ValueError:
            pass
