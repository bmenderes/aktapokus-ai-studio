"""Dosyalar agaci: tumunu daralt / genislet; klasor durumu yenilemede korunur."""

from pathlib import Path


def test_dosya_agaci_tumunu_daralt_ve_genislet_dugmeleri_ve_durum_korunur():
    html = (Path(__file__).parent.parent / "aktapokus_ai_studio" / "web" / "index.html").read_text(encoding="utf-8")
    assert 'id="agacDaralt"' in html and 'title="Tümünü daralt"' in html and 'id="agacAc"' in html and 'title="Tümünü genişlet"' in html
    assert "function agacTumu(ac)" in html and "agacTumu(false)" in html and "agacTumu(true)" in html
    # liste yenilense de kullanicinin actigi/kapattigi klasorler korunur (yol -> acik)
    assert "S.agacAcik[yol]=ac" in html and "ayarla(yol in S.agacAcik?S.agacAcik[yol]:d<1)" in html
