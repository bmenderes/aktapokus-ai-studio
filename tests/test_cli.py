import json
import subprocess

from aktapokus_ajan import cli
from aktapokus_ajan.config import AYAR_KLASORU
from conftest import SahteCalistirici, sonuc


def girdi_ile(*cevaplar):
    kuyruk = list(cevaplar)

    def girdi(_soru):
        if not kuyruk:
            raise EOFError
        return kuyruk.pop(0)

    return girdi


def test_ac_git_yoksa_aciklar_ve_git_baslat_ile_kurar(tmp_path, capsys):
    k = tmp_path / "p"
    k.mkdir()
    assert cli.main(["ac", str(k)]) == cli.CIKIS_KULLANIM
    assert "--git-baslat" in capsys.readouterr().out
    assert not (k / ".git").exists() and not (k / AYAR_KLASORU).exists()
    assert cli.main(["ac", str(k), "--git-baslat"]) == cli.CIKIS_TAMAM
    assert (k / ".git").is_dir() and (k / AYAR_KLASORU / "roller.json").is_file()
    assert f"{AYAR_KLASORU}/" in (k / ".git" / "info" / "exclude").read_text(encoding="utf-8")


def test_ac_mevcut_ayari_ezmez_ve_exclude_tekrarlanmaz(proje, capsys):
    assert cli.main(["ac", str(proje)]) == cli.CIKIS_TAMAM
    yol = proje / AYAR_KLASORU / "roller.json"
    veri = json.loads(yol.read_text(encoding="utf-8"))
    veri["butce_token"] = 777
    yol.write_text(json.dumps(veri), encoding="utf-8")
    assert cli.main(["ac", str(proje)]) == cli.CIKIS_TAMAM
    assert json.loads(yol.read_text(encoding="utf-8"))["butce_token"] == 777
    assert (proje / ".git" / "info" / "exclude").read_text(encoding="utf-8").count(f"{AYAR_KLASORU}/") == 1


def test_ac_tehlikeli_klasoru_reddeder(capsys):
    from pathlib import Path

    assert cli.main(["ac", str(Path.home())]) == cli.CIKIS_HATA
    assert "Ana dizin" in capsys.readouterr().out


def hazirla(proje):
    assert cli.main(["ac", str(proje)]) == cli.CIKIS_TAMAM


def sahte_uretici(senaryo):
    sahte = SahteCalistirici(senaryo)
    return sahte, (lambda ad: sahte)


def yaz(k, istem, n):
    (k / "c.txt").write_text("yeni\n", encoding="utf-8")
    return sonuc("yazildi")


def test_calistir_plan_reddedilirse_hicbir_sey_calismaz(proje, capsys):
    hazirla(proje)
    sahte, uret = sahte_uretici({"kodcu": yaz, "test": lambda k, i, n: sonuc("SONUC: BASARILI")})
    kod = cli.main(["calistir", "c ekle", "--klasor", str(proje)], girdi=girdi_ile("h"), calistirici_uret=uret)
    assert kod == cli.CIKIS_TAMAM and sahte.cagrilar == [] and not (proje / "c.txt").exists()
    assert "Iptal edildi" in capsys.readouterr().out


def test_calistir_onay_ve_ozet(proje, capsys):
    hazirla(proje)
    sahte, uret = sahte_uretici({"kodcu": yaz, "test": lambda k, i, n: sonuc("SONUC: BASARILI")})
    kod = cli.main(["calistir", "c ekle", "--klasor", str(proje)], girdi=girdi_ile("e", "e"), calistirici_uret=uret)
    cikti = capsys.readouterr().out
    assert kod == cli.CIKIS_TAMAM, cikti
    assert (proje / "c.txt").exists()
    assert "Durum: onaylandi" in cikti and "kodcu" in cikti and "Toplam: 30 token" in cikti
    assert "Klasor DISINDAKI etki geri alinamaz" in cikti and "KABUK komutlari" in cikti  # durust uyari her zaman gosterilir


def test_calistir_degisiklik_onaylanmazsa_geri_alinir(proje):
    hazirla(proje)
    _s, uret = sahte_uretici({"kodcu": yaz, "test": lambda k, i, n: sonuc("SONUC: BASARILI")})
    kod = cli.main(["calistir", "g", "--klasor", str(proje)], girdi=girdi_ile("e", "h"), calistirici_uret=uret)
    assert kod == cli.CIKIS_TAMAM and not (proje / "c.txt").exists()


def test_calistir_evet_bayragi_ve_butce_ezme(proje, capsys):
    hazirla(proje)
    _s, uret = sahte_uretici({"kodcu": lambda k, i, n: (yaz(k, i, n), sonuc("x", 900, 900))[1], "test": lambda k, i, n: sonuc("SONUC: BASARILI")})
    kod = cli.main(["calistir", "g", "--klasor", str(proje), "--evet", "--butce", "1000"], calistirici_uret=uret)
    assert kod == cli.CIKIS_HATA  # butce asildi
    assert "butce_asildi" in capsys.readouterr().out
    assert cli.main(["calistir", "g", "--klasor", str(proje), "--evet", "--butce", "0"]) == cli.CIKIS_KULLANIM


def test_calistir_ayar_yoksa_ve_git_yoksa_net_hata(tmp_path, proje, capsys):
    assert cli.main(["calistir", "g", "--klasor", str(proje), "--evet"]) == cli.CIKIS_HATA  # ac calistirilmadi
    assert "aktapokus ac" in capsys.readouterr().out
    k = tmp_path / "gitsiz"
    k.mkdir()
    (k / AYAR_KLASORU).mkdir()
    from aktapokus_ajan.config import VARSAYILAN_AYAR

    (k / AYAR_KLASORU / "roller.json").write_text(json.dumps(VARSAYILAN_AYAR), encoding="utf-8")
    assert cli.main(["calistir", "g", "--klasor", str(k), "--evet"]) == cli.CIKIS_HATA
    assert "git deposu degil" in capsys.readouterr().out


def test_geri_al_komutu(proje, capsys):
    hazirla(proje)
    _s, uret = sahte_uretici({"kodcu": yaz, "test": lambda k, i, n: sonuc("SONUC: BASARILI")})
    cli.main(["calistir", "g", "--klasor", str(proje), "--evet"], calistirici_uret=uret)
    assert (proje / "c.txt").exists()
    assert cli.main(["geri-al", "--klasor", str(proje)], girdi=girdi_ile("h")) == cli.CIKIS_TAMAM
    assert (proje / "c.txt").exists()  # onay verilmedi
    assert cli.main(["geri-al", "--klasor", str(proje), "--evet"]) == cli.CIKIS_TAMAM
    assert not (proje / "c.txt").exists()
    assert cli.main(["geri-al", "--klasor", str(proje), "--evet"]) == cli.CIKIS_HATA  # zaten geri alinmis


def test_durum_komutu(proje, capsys, monkeypatch):
    hazirla(proje)
    monkeypatch.setattr(cli, "opencode_bul", lambda: None)
    assert cli.main(["durum", "--klasor", str(proje)]) == cli.CIKIS_TAMAM
    cikti = capsys.readouterr().out
    assert "OpenCode CLI: bulunamadi" in cikti and "git deposu: evet" in cikti and "kodcu" in cikti
