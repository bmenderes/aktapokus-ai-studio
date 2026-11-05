"""Bilgisayar CPU/GPU kullanimi (kaynak.py): saf ayristirma/hesap fonksiyonlari ve gizlilik (yalniz yuzdeler)."""

from aktapokus_ai_studio import kaynak


def test_cpu_yuzde_iki_olcum_arasindan_hesaplanir():
    assert kaynak.cpu_yuzde(None, (10, 100)) is None  # ilk olcumde fark yok
    assert kaynak.cpu_yuzde((0, 0), (75, 100)) == 25.0  # toplam 100'un 75'i bosta -> %25 kullanim
    assert kaynak.cpu_yuzde((50, 100), (50, 100)) is None  # sure gecmedi
    assert kaynak.cpu_yuzde((0, 0), (200, 100)) == 0.0  # sinirlar: negatif olmaz


def test_nvidia_ayristir_en_yuksek_gpu_ve_toplam_bellek():
    assert kaynak.nvidia_ayristir("55, 4000, 8000\n10, 0, 8000\n") == (55.0, 25.0)
    assert kaynak.nvidia_ayristir("") is None
    assert kaynak.nvidia_ayristir("bozuk, satir\n") is None


def test_typeperf_ayristir_motor_turu_basina_toplar_en_yuksegi_alir():
    cikti = ('"(PDH-CSV 4.0)","\\\\PC\\GPU Engine(pid_1_luid_0_phys_0_eng_0_engtype_3D)\\Utilization Percentage",'
             '"\\\\PC\\GPU Engine(pid_2_luid_0_phys_0_eng_0_engtype_3D)\\Utilization Percentage",'
             '"\\\\PC\\GPU Engine(pid_1_luid_0_phys_0_eng_1_engtype_Copy)\\Utilization Percentage"\n'
             '"11/03/2026 10:00:00.000","30.5","20.0","5.0"\n')
    assert kaynak.typeperf_ayristir(cikti) == 50.5
    assert kaynak.typeperf_ayristir("") is None


def test_izleyici_yalniz_yuzdeler_dondurur(monkeypatch):
    monkeypatch.setattr(kaynak.Izleyici, "_dongu", lambda self: None)  # arka plan olcumu yok
    veri = kaynak.Izleyici().oku()
    assert set(veri) == {"cpu", "gpu", "gpu_bellek", "zaman"}  # surec/kullanici adi/icerik yok
