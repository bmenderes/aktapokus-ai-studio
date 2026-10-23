import copy
import hashlib
import json
import subprocess

import pytest

from aktapokus_ajan import baglam, cli
from aktapokus_ajan.config import VARSAYILAN_AYAR, ayar_coz
from aktapokus_ajan.pipeline import calistir_hat, istem_olustur
from aktapokus_ajan.proje import hazirla
from conftest import SahteCalistirici, sonuc


def ayar(**degisim):
    veri = copy.deepcopy(VARSAYILAN_AYAR)
    veri.update(degisim)
    return ayar_coz(veri)


def md5(yol):
    return hashlib.md5(yol.read_bytes()).hexdigest()


def kayit_yaz(klasor, ad, **alanlar):
    d = klasor / ".aktapokus" / "kayit"
    d.mkdir(parents=True, exist_ok=True)
    v = {"id": ad, "zaman": "2026-10-22 10:00:00", "gorev": "ornek gorev", "durum": "onaylandi", "mesaj": "", "degisen": {"a.txt": "M"},
         "adimlar": [{"rol": "kodcu", "calistirici": "opencode", "model": "opencode/deepseek"}]}
    v.update(alanlar)
    (d / f"{ad}.json").write_text(json.dumps(v), encoding="utf-8")


def test_blok_varsayilan_ve_ozel_kurallar(tmp_path):
    b = baglam.blok_uret(tmp_path)
    assert b.startswith(baglam.BASLA_ONEK) and b.endswith(baglam.BITIR) and "Kullanıcıyla Türkçe konuş" in b and ".aktapokus/DURUM.md" in b
    baglam.kaynak_yolu(tmp_path).parent.mkdir()
    baglam.kaynak_yolu(tmp_path).write_text("## Benim kurallarim\n- Acik tema kullan.\n", encoding="utf-8")
    ozel = baglam.blok_uret(tmp_path)
    assert "Acik tema kullan" in ozel and "Kullanıcıyla Türkçe konuş" not in ozel


def test_kurallar_uzunsa_kisaltilir_her_adima_girdigi_icin(tmp_path):
    baglam.kaynak_yolu(tmp_path).parent.mkdir()
    baglam.kaynak_yolu(tmp_path).write_text("x" * 9000, encoding="utf-8")
    k = baglam.kurallar(tmp_path)
    assert len(k) < 2200 and "kısaltıldı" in k


def test_bloku_yaz_olusturur_degistirir_ayni_der(tmp_path):
    d = tmp_path / "AGENTS.md"
    assert baglam.bloku_yaz(d, baglam.blok_uret(tmp_path)) == "olusturuldu"
    assert baglam.bloku_yaz(d, baglam.blok_uret(tmp_path)) == "ayni"
    baglam.kaynak_yolu(tmp_path).parent.mkdir()
    baglam.kaynak_yolu(tmp_path).write_text("- yeni kural", encoding="utf-8")
    assert baglam.bloku_yaz(d, baglam.blok_uret(tmp_path)) == "guncellendi"
    assert "yeni kural" in d.read_text(encoding="utf-8") and d.read_text(encoding="utf-8").count(baglam.BASLA_ONEK) == 1


def test_kullanicinin_kendi_metnine_dokunulmaz(tmp_path):
    d = tmp_path / "AGENTS.md"
    d.write_text("# Benim proje notlarim\nBunu silme.\n", encoding="utf-8")
    assert baglam.bloku_yaz(d, baglam.blok_uret(tmp_path)) == "guncellendi"  # sona eklendi
    metin = d.read_text(encoding="utf-8")
    assert metin.startswith("# Benim proje notlarim\nBunu silme.\n") and baglam.BASLA_ONEK in metin
    # blok guncellenirken bloktan ONCE ve SONRA yazilan metin korunur
    d.write_text("ON METIN\n\n" + metin.split("\n\n", 1)[1].rstrip("\n") + "\n\nSON METIN\n", encoding="utf-8")
    baglam.kaynak_yolu(tmp_path).parent.mkdir()
    baglam.kaynak_yolu(tmp_path).write_text("- degisti", encoding="utf-8")
    baglam.bloku_yaz(d, baglam.blok_uret(tmp_path))
    son = d.read_text(encoding="utf-8")
    assert son.startswith("ON METIN") and son.rstrip().endswith("SON METIN") and "- degisti" in son and son.count(baglam.BASLA_ONEK) == 1


def test_bozuk_isaret_varsa_ustune_yazmaz_sona_ekler_ve_crlf_korunur(tmp_path):
    d = tmp_path / "AGENTS.md"
    d.write_bytes(("satir1\r\n" + baglam.BASLA_ONEK + " yarim kalmis blok, bitis isareti yok\r\nkullanici metni\r\n").encode())
    baglam.bloku_yaz(d, baglam.blok_uret(tmp_path))
    ham = d.read_bytes().decode()
    assert "kullanici metni" in ham and ham.count(baglam.BITIR) == 1
    assert "\n" not in ham.replace("\r\n", "")  # satir sonu stili (CRLF) korundu


def test_dosya_adlari_rollere_gore():
    assert baglam.dosya_adlari(ayar()) == ["AGENTS.md"]
    v = copy.deepcopy(VARSAYILAN_AYAR)
    v["roller"]["test"]["calistirici"] = "claude"
    assert baglam.dosya_adlari(ayar_coz(v)) == ["AGENTS.md", "CLAUDE.md"]


def test_durum_metni_bos_siralama_yarim_ve_bozuk_kayit(tmp_path):
    assert "Henüz" in baglam.durum_metni(tmp_path)
    kayit_yaz(tmp_path, "20261022-100000-aaaa", gorev="ilk is")
    kayit_yaz(tmp_path, "20261022-110000-bbbb", gorev="ikinci is", durum="butce_asildi", mesaj="Token butcesi asildi", degisen={"b.txt": "A"})
    (tmp_path / ".aktapokus" / "kayit" / "bozuk.json").write_text("{bozuk", encoding="utf-8")
    m = baglam.durum_metni(tmp_path)
    assert m.index("ikinci is") < m.index("ilk is")  # en yeni ustte
    assert "YARIM/SORUNLU: Token butcesi asildi" in m and "b.txt (A)" in m and "kodcu(opencode/deepseek)" in m


def test_durum_metni_sinirli(tmp_path):
    for i in range(20):
        kayit_yaz(tmp_path, f"2026102{i % 10}-1000{i:02d}-x{i}", gorev="g" * 500, degisen={f"dosya{j}.txt": "M" for j in range(30)})
    m = baglam.durum_metni(tmp_path)
    assert len(m) <= baglam.AZAMI_DURUM + 40 and m.count("- 2026") <= baglam.SON_CALISTIRMA


def test_guncelle_idempotent_ve_blok_kararli(tmp_path):
    a = ayar()
    assert baglam.guncelle(tmp_path, a)["AGENTS.md"] == "olusturuldu"
    onceki = md5(tmp_path / "AGENTS.md")
    kayit_yaz(tmp_path, "20261022-100000-aaaa")
    s = baglam.guncelle(tmp_path, a)
    assert s["AGENTS.md"] == "ayni" and md5(tmp_path / "AGENTS.md") == onceki  # yeni calistirma AGENTS.md'yi DEGISTIRMEZ (git gurultusu yok)
    assert s[".aktapokus/DURUM.md"] == "guncellendi" and "ornek gorev" in (tmp_path / ".aktapokus" / "DURUM.md").read_text(encoding="utf-8")
    assert baglam.guncelle(tmp_path, a)[".aktapokus/DURUM.md"] == "ayni"


def test_hazirla_kural_dosyasini_olusturur_ama_ezmez(tmp_path):
    k = tmp_path / "p"
    k.mkdir()
    subprocess.run(["git", "-C", str(k), "init", "-q"], check=True)
    assert hazirla(k)["baglam"] == "olusturuldu"
    baglam.kaynak_yolu(k).write_text("- benim kuralim", encoding="utf-8")
    assert hazirla(k)["baglam"] == "mevcut" and baglam.kaynak_yolu(k).read_text(encoding="utf-8") == "- benim kuralim"


def test_istem_durum_dosyasini_gosterir():
    from aktapokus_ajan.config import Rol

    assert ".aktapokus/DURUM.md" in istem_olustur(Rol("kodcu", "opencode", None, "Kod yaz."), "g", None, None)


def _yaz(k, i, n):
    (k / "c.txt").write_text("x")
    return sonuc("yazildi")


def basarili():
    return SahteCalistirici({"kodcu": _yaz, "test": lambda k, i, n: sonuc("SONUC: BASARILI")})


def test_hat_baglami_snapshottan_once_uretir_ve_kaldigi_yeri_aktarir(proje):
    s1 = calistir_hat(proje, "ilk gorev", ayar(), lambda ad: basarili(), lambda q: True)
    assert s1.degisen == {"c.txt": "A"}  # AGENTS.md / DURUM.md ajanin degisikligi sayilmadi
    assert (proje / "AGENTS.md").is_file() and "aktapokus:basla" in (proje / "AGENTS.md").read_text(encoding="utf-8")
    c = SahteCalistirici({"kodcu": lambda k, i, n: sonuc("hicbir sey yapmadim"), "test": lambda k, i, n: sonuc("SONUC: BASARILI")})
    calistir_hat(proje, "ikinci gorev", ayar(), lambda ad: c, lambda q: True)
    durum = (proje / ".aktapokus" / "DURUM.md").read_text(encoding="utf-8")
    assert "ilk gorev" in durum  # ikinci calistirma baslarken ilk calistirmanin ozeti hazirdi (baska model devam edebilir)
    assert ".aktapokus/DURUM.md" in c.cagrilar[0][2]  # istem de modele DURUM.md'yi okumasini soyler


def test_baglam_kapaliysa_dosya_yazilmaz(proje):
    s = calistir_hat(proje, "gorev", ayar(baglam=False), lambda ad: basarili(), lambda q: True)
    assert s.durum == "onaylandi" and not (proje / "AGENTS.md").exists() and not (proje / ".aktapokus" / "DURUM.md").exists()


def test_baglam_yazilamazsa_gorev_dusmez(proje, monkeypatch):
    mesajlar = []
    monkeypatch.setattr(baglam, "guncelle", lambda k, a: (_ for _ in ()).throw(OSError("disk dolu")))
    s = calistir_hat(proje, "gorev", ayar(), lambda ad: basarili(), lambda q: True, mesajlar.append)
    assert s.durum == "onaylandi" and any("baglam dosyalari yazilamadi" in m for m in mesajlar)


def test_ayar_baglam_alani_dogrulanir():
    v = copy.deepcopy(VARSAYILAN_AYAR)
    v["baglam"] = "evet"
    with pytest.raises(Exception, match="baglam"):
        ayar_coz(v)
    v2 = copy.deepcopy(VARSAYILAN_AYAR)
    del v2["baglam"]
    assert ayar_coz(v2).baglam is True  # eski ayar dosyalari bozulmaz


def test_cli_baglam_komutu(proje, capsys):
    assert cli.main(["ac", str(proje)]) == cli.CIKIS_TAMAM
    assert cli.main(["baglam", "--klasor", str(proje)]) == cli.CIKIS_TAMAM
    cikti = capsys.readouterr().out
    assert "AGENTS.md: olusturuldu" in cikti and "baglam.md" in cikti
    assert cli.main(["baglam", "--klasor", str(proje)]) == cli.CIKIS_TAMAM and "AGENTS.md: ayni" in capsys.readouterr().out
