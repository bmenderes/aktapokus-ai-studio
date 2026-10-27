"""Dosyalar agaci: tumunu daralt / genislet; klasor durumu yenilemede korunur."""

from pathlib import Path


def test_dosya_agaci_tumunu_daralt_ve_genislet_dugmeleri_ve_durum_korunur():
    html = (Path(__file__).parent.parent / "aktapokus_ai_studio" / "web" / "index.html").read_text(encoding="utf-8")
    assert 'id="agacDaralt"' in html and 'title="Tümünü daralt"' in html and 'id="agacAc"' in html and 'title="Tümünü genişlet"' in html
    assert "function agacTumu(ac)" in html and "agacTumu(false)" in html and "agacTumu(true)" in html
    # liste yenilense de kullanicinin actigi/kapattigi klasorler korunur (yol -> acik)
    assert "S.agacAcik[yol]=ac" in html and "ayarla(yol in S.agacAcik?S.agacAcik[yol]:d<1)" in html


def test_arayuz_kendi_kimligine_sahip_marka_renkleri_maskot_ve_bagimsizlik_notu():
    """Baska urunlerin gorunumunu taklit etmeyiz: marka paleti (maskot sarisi + murekkep yesili), maskotlu bos ekran, bagimsizlik notu."""
    kok = Path(__file__).parent.parent
    html = (kok / "aktapokus_ai_studio" / "web" / "index.html").read_text(encoding="utf-8")
    assert "--sari:#f5c400" in html and "--bg:#f7f5f1" in html and "--bg:#edf2ec" not in html  # krem zemin + sari vurgu; yesil zemin ve koyu ust cubuk yok
    assert "#top{display:flex;align-items:center;justify-content:space-between;padding:7px 12px;background:var(--panel)" in html
    assert "html,body{height:100dvh}" in html and "#mobilGezinme{order:99" in html  # telefon: adres cubugu altı kesmez, gezinme en altta
    assert "button.pri{background:var(--sari)" in html and "#akis:empty{background:var(--maskot)" in html and "marka-logo" in html
    assert "Bağımsızlık ve ticari markalar" in html and "ilgili sahiplerinin ticari markalarıdır" in html
    readme = (kok / "README.md").read_text(encoding="utf-8")
    assert "## Bağımsızlık ve ticari markalar" in readme and "Hermes" not in readme and "Claude uygulaması gibi" not in readme
    assert "Hermes" not in html and "Claude gibi" not in html and "OpenCode Desktop gibi" not in html
