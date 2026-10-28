"""Kapanista yarim kalan gorev satiri ('Yarim kaldi · gorev'): sohbet gecmisi yuklenince onay cubugu temizlenir; satir bu yuzden SILINMEMELI
(gercek kayip: karar bekleyen son gorev, uygulama yeniden acilinca ekranda gorunmuyordu)."""

from pathlib import Path

HTML = (Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "web" / "index.html").read_text(encoding="utf-8")


def test_yarim_kalan_gorev_satiri_gecmis_yuklenince_yeniden_cizilir():
    assert "S.yarim=d.yarim;yarimCiz(d.yarim)" in HTML  # son durum saklanir
    assert '$("#onayBar").textContent="";yarimCiz(S.yarim)' in HTML  # gecmis yuklemesi cubugu temizledikten sonra satir geri gelir
    assert "function yarimCiz" in HTML and "/api/yarim" in HTML
