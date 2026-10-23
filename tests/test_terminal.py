import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from aktapokus_ajan import terminal, uygulama

pytestmark = pytest.mark.skipif(
    not terminal.kontrol(),
    reason="ConPTY bu ortamda calismiyor (Windows 10 1809+/11 gerekir; kisitli/kum havuzlu ortamlarda sahte konsol yok sayilir). Gercek bir terminalden calistirin.",
)

KABUK = ["cmd.exe"]


def topla(t, ifade, sn=12, son=0):
    """Terminal ciktisinda `ifade` gorunene dek okur; (cikti, son_sira) doner."""
    cikti = b""
    bitis = time.monotonic() + sn
    while time.monotonic() < bitis:
        parcalar, bitti = t.bekle(son, 1.0)
        for s, v in parcalar:
            son = s
            cikti += v
        if ifade.encode("utf-8") in cikti or bitti:
            break
    return cikti, son


@pytest.fixture
def acilan():
    liste = []

    def ac(komut=KABUK, klasor=None, satir=24, sutun=80):
        t = terminal.Terminal(komut, klasor, satir, sutun)
        liste.append(t)
        return t

    yield ac
    for t in liste:
        t.kapat()


def test_komut_gercekten_calisir_ve_cikti_gelir(acilan):
    t = acilan()
    t.yaz(b"echo AKTAPOKUS_DENEME_123\r\n")
    cikti, _ = topla(t, "AKTAPOKUS_DENEME_123")
    assert b"AKTAPOKUS_DENEME_123" in cikti


def test_calisma_klasoru_ve_ortam_degiskeni(acilan, tmp_path):
    t = acilan(klasor=tmp_path)
    t.yaz(b"cd\r\n")
    cikti, son = topla(t, str(tmp_path))
    assert str(tmp_path).encode() in cikti  # kabuk istenen klasorde basladi
    t.yaz(b"echo %AKTAPOKUS_TERMINAL%\r\n")
    cikti, _ = topla(t, "\r\n1\r\n", son=son)
    assert b"1" in cikti


def test_boyutlandirma_gercekten_uygulanir(acilan):
    t = acilan(satir=24, sutun=80)
    t.boyutla(30, 111)
    t.yaz(b"mode con\r\n")
    cikti, _ = topla(t, "111")
    assert b"111" in cikti and t.sutun == 111 and t.satir == 30


def test_gecersiz_boyutlar_sinirlanir(acilan):
    t = acilan(satir=-5, sutun=99999)
    assert (t.satir, t.sutun) == (2, 1000)
    t.boyutla(10**6, 0)
    assert (t.satir, t.sutun) == (500, 2)


def test_powershell_turkce_karakter_ve_utf8(acilan):
    t = acilan(komut=terminal.varsayilan_kabuk() + ["-NoProfile"])
    t.yaz("Write-Output ('sek' + 'er çğşıöü')\r\n".encode("utf-8"))
    cikti, _ = topla(t, "çğşıöü", sn=20)
    assert "çğşıöü".encode("utf-8") in cikti


def test_exit_komutu_terminali_bitirir(acilan):
    t = acilan()
    t.yaz(b"exit\r\n")
    bitis = time.monotonic() + 12
    while t.canli and time.monotonic() < bitis:
        t.bekle(0, 0.5)
    assert not t.canli
    parcalar, bitti = t.bekle(10**9, 1.0)  # tum parcalar okunmus: 'bitti' bildirilir
    assert bitti is True and parcalar == []


def test_kapat_sureci_ve_alt_surecleri_oldurur(acilan):
    """Terminal kapaninca kabuk VE onun baslattigi alt surecler (is nesnesi sayesinde) olmeli: yetim surec kalmaz."""
    t = acilan()
    t.yaz(b"ping -n 120 127.0.0.1 > nul\r\n")  # kabugun alt sureci
    cocuk = None
    for _ in range(40):
        cikti = subprocess.run(
            ["powershell", "-NoProfile", "-Command", f"(Get-CimInstance Win32_Process -Filter 'ParentProcessId={t.pid}' | Select-Object -ExpandProperty ProcessId) -join ','"],
            capture_output=True, text=True, timeout=30,
        ).stdout.strip()
        if cikti:
            cocuk = int(cikti.split(",")[0])
            break
        time.sleep(0.25)
    assert cocuk, "kabugun alt sureci (ping) bulunamadi"
    assert uygulama.surec_canli_mi(t.pid) and uygulama.surec_canli_mi(cocuk)
    t.kapat()
    for _ in range(60):
        if not uygulama.surec_canli_mi(t.pid) and not uygulama.surec_canli_mi(cocuk):
            break
        time.sleep(0.25)
    assert not uygulama.surec_canli_mi(t.pid), "kabuk surecı kapanmadi"
    assert not uygulama.surec_canli_mi(cocuk), "alt surec YETIM kaldi"


def test_kapatilmis_terminale_yazmak_sessizce_yok_sayilir_ve_kapat_tekrarlanabilir(acilan):
    t = acilan()
    t.kapat()
    t.kapat()
    t.yaz(b"echo x\r\n")  # istisna yok
    assert not t.canli


def test_tampon_sinirlidir_ve_son_parcalar_kalir(acilan):
    t = acilan()
    for _ in range(4):
        t._ekle(b"x" * 400_000)
    t._ekle(b"SON_PARCA")
    assert t._boyut <= terminal.AZAMI_TAMPON + 400_000  # en eski parcalar atildi
    parcalar, _ = t.bekle(0, 0.1)
    assert parcalar[-1][1] == b"SON_PARCA" and len(parcalar) < 6


def test_yeniden_baglanan_istemci_son_ekrani_yeniden_alir(acilan):
    t = acilan()
    t.yaz(b"echo EKRAN_TEKRAR_OYNATMA\r\n")
    topla(t, "EKRAN_TEKRAR_OYNATMA")
    yeni_istemci, _ = topla(t, "EKRAN_TEKRAR_OYNATMA", sn=3, son=0)  # son=0: bastan, yeni baglanan tarayici
    assert b"EKRAN_TEKRAR_OYNATMA" in yeni_istemci


def test_bulunmayan_kabuk_anlasilir_hata(acilan):
    with pytest.raises(terminal.TerminalHatasi, match="Kabuk başlatılamadı"):
        acilan(komut=[str(Path("C:/olmayan/kabuk.exe"))])


def test_uygulama_zorla_oldurulunce_terminal_surecleri_de_olur(tmp_path):
    """Is nesnesinin asil gorevi: arayuz sureci ZORLA (taskkill /F) olurse kabuk ve alt surecleri yetim kalmamali."""
    kok = str(Path(__file__).resolve().parent.parent)
    kod = (
        "import sys, time; sys.path.insert(0, sys.argv[1]);"
        "from aktapokus_ajan import terminal;"
        "t = terminal.Terminal(['cmd.exe']); t.yaz(b'ping -n 120 127.0.0.1 > nul\\r\\n');"
        "print(t.pid, flush=True); time.sleep(120)"
    )
    ana = subprocess.Popen([sys.executable, "-c", kod, kok], stdout=subprocess.PIPE, text=True)
    try:
        kabuk = int(ana.stdout.readline().strip())
        cocuk = None
        for _ in range(40):
            cikti = subprocess.run(
                ["powershell", "-NoProfile", "-Command", f"(Get-CimInstance Win32_Process -Filter 'ParentProcessId={kabuk}' | Select-Object -ExpandProperty ProcessId) -join ','"],
                capture_output=True, text=True, timeout=30,
            ).stdout.strip()
            if cikti:
                cocuk = int(cikti.split(",")[0])
                break
            time.sleep(0.25)
        assert cocuk and uygulama.surec_canli_mi(kabuk) and uygulama.surec_canli_mi(cocuk)
        ana.kill()  # zorla: finally/kapat() CALISMAZ
        ana.wait(10)
        for _ in range(60):
            if not uygulama.surec_canli_mi(kabuk) and not uygulama.surec_canli_mi(cocuk):
                break
            time.sleep(0.25)
        assert not uygulama.surec_canli_mi(kabuk), "kabuk yetim kaldi"
        assert not uygulama.surec_canli_mi(cocuk), "alt surec yetim kaldi"
    finally:
        if ana.poll() is None:
            ana.kill()
