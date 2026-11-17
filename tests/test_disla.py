"""Buyuk ve hassas dosyalar .gitignore'a kendiliginden eklenir; kullanici sildigi satiri geri bulmaz; gorev bundan haberdar olur."""

import json

from aktapokus_ai_studio import disla, snapshot
from aktapokus_ai_studio.proje import hazirla

M = 2**20


def test_tarama_buyuk_klasorleri_dar_secer_ve_hassas_belgeleri_bulur():
    f = {
        "SampleProject/a/x.bin": 300 * M, "SampleProject/b/y.bin": 115 * M,  # iki buyuk alt klasor -> ust klasor
        "docs/PacDrive/p.zip": 864 * M, "docs/01.md": 1, "docs/HMI/h.pdf": 26 * M,  # yalniz docs/PacDrive, docs degil
        "big.iso": 60 * M, "plc/PRG.st": 1,
        "docs/Musteri_Sozlesmesi_2026.pdf": 1, "ozel/fatura-ocak.xlsx": 1, "Bordro Mart.docx": 1, ".env": 1,
        ".env.example": 1, "tanda.pdf": 1, "rapor.pdf": 1, "sozlesme.md": 1,  # yanlis pozitif olmamali
    }
    sonuc = {s["desen"]: s["neden"] for s in disla.tara(list(f), f.get)}
    assert set(sonuc) == {"/SampleProject/", "/docs/PacDrive/", "/big.iso", "/docs/Musteri_Sozlesmesi_2026.pdf", "/ozel/fatura-ocak.xlsx", "/Bordro Mart.docx", "/.env"}
    assert sonuc["/SampleProject/"] == "buyuk klasor" and "sozlesme" in sonuc["/docs/Musteri_Sozlesmesi_2026.pdf"] and sonuc["/.env"].startswith("gizli")


def test_desen_ozel_karakterleri_kacirir():
    assert disla._desen("a[1]*.pdf", False) == "/a\\[1\\]\\*.pdf" and disla._desen("klasor", True) == "/klasor/"


def test_uygula_gitignorea_blok_yazar_tekrar_eklemez_ve_silineni_geri_getirmez(tmp_path):
    k = tmp_path / "p"
    k.mkdir()
    (k / ".gitignore").write_text("bin/\n", encoding="utf-8")
    (k / "Sozlesme_ABC.pdf").write_bytes(b"x")
    (k / "kod.py").write_text("print(1)")
    hazirla(k)  # git istenmez: golge depo; tarama hazirlikta yapilir
    metin = (k / ".gitignore").read_text(encoding="utf-8")
    assert metin.startswith("bin/\n") and disla.BLOK_BASI in metin and "/Sozlesme_ABC.pdf" in metin and disla.BLOK_SONU in metin
    assert "Sozlesme_ABC.pdf" not in snapshot._git(k, "ls-files", "-o", "--exclude-standard")  # artik dislanmis
    assert disla.uygula(k) == []  # ikinci kez eklenmez
    # kullanici satiri siler: bir daha eklenmez
    (k / ".gitignore").write_text("bin/\n", encoding="utf-8")
    assert disla.uygula(k) == []
    # yeni hassas dosya sonradan gelir: blok yeniden kurulur, yalniz yenisi eklenir
    (k / "fatura_2026.xlsx").write_bytes(b"x")
    eklenen = disla.uygula(k)
    assert [s["desen"] for s in eklenen] == ["/fatura_2026.xlsx"]
    assert "/Sozlesme_ABC.pdf" not in (k / ".gitignore").read_text(encoding="utf-8")
    assert json.loads((k / ".aktapokus" / disla.KAYIT).read_text(encoding="utf-8"))["eklenen"] == ["/Sozlesme_ABC.pdf", "/fatura_2026.xlsx"]
    assert "fatura_2026.xlsx" in disla.bildirim(eklenen) and "Aktapokus blogundan silin" in disla.bildirim(eklenen)


def test_buyuk_klasor_sinira_takilmadan_dislanir(tmp_path, monkeypatch):
    """Gercek durum: SampleProject + PacDrive 1 GB'i asti; gorev modelden once 'klasor cok buyuk' ile durdu."""
    k = tmp_path / "p"
    (k / "SampleProject" / "a").mkdir(parents=True)
    (k / "SampleProject" / "a" / "x.bin").write_bytes(b"x" * 3000)
    (k / "kod.st").write_text("PROGRAM P END_PROGRAM")
    monkeypatch.setattr(snapshot, "AZAMI_GOLGE_BAYT", 1000)
    monkeypatch.setattr(disla, "BUYUK_KLASOR", 1000)
    sonuc = hazirla(k)
    assert sonuc["git"] == "golge" and [s["desen"] for s in sonuc["dislanan"]] == ["/SampleProject/a/"]  # en dar buyuk klasor
    snapshot.anlik_goruntu(k, "deneme")  # boyut denetimi artik gecer
