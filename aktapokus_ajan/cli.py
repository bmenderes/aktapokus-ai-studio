"""Komut satiri: aktapokus ac | calistir | geri-al | durum | roller"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Callable

from . import __version__, baglam, guard, snapshot
from .config import (
    AYAR_KLASORU,
    VARSAYILAN_AYAR,
    Ayar,
    AyarHatasi,
    ayar_yolu,
    ayar_yukle,
)
from .klasor import KlasorHatasi, guvenli_klasor
from .pipeline import HatHatasi, calistir_hat, geri_al, son_kayit
from .proje import GitGerekli, hazirla as proje_hazirla
from .runners import Calistirici, CalistiriciHatasi, calistirici_olustur, hepsini_kapat, opencode_bul

CIKIS_TAMAM, CIKIS_HATA, CIKIS_KULLANIM = 0, 1, 2


def _soru_sor(soru: str, otomatik_evet: bool, girdi: Callable[[str], str]) -> bool:
    if otomatik_evet:
        print(f"{soru} -> evet (--evet)")
        return True
    try:
        cevap = girdi(f"{soru} [e/H] ").strip().lower()
    except EOFError:
        return False
    return cevap in ("e", "evet", "y", "yes")


def _surum_oku(komut: list[str]) -> str:
    try:
        cikti = subprocess.run(
            komut, capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL, encoding="utf-8", errors="replace"
        )
        return (cikti.stdout or cikti.stderr).strip().splitlines()[0] if (cikti.stdout or cikti.stderr).strip() else "?"
    except Exception as hata:
        return f"okunamadi ({type(hata).__name__})"


def komut_ac(args, girdi) -> int:
    try:
        klasor = guvenli_klasor(args.klasor)
    except KlasorHatasi as hata:
        print(f"HATA: {hata}")
        return CIKIS_HATA
    try:
        sonuc = proje_hazirla(klasor, git_baslat=args.git_baslat)
    except GitGerekli:
        print(
            f"{klasor} bir git deposu degil. Geri alma git'e dayanir.\n"
            f"Baslatmak icin: aktapokus ac \"{klasor}\" --git-baslat (yalnizca bu klasorde 'git init' yapar)"
        )
        return CIKIS_KULLANIM
    except (snapshot.GitHatasi, guard.KoruyucuHatasi) as hata:
        print(f"HATA: {hata}")
        return CIKIS_HATA
    if sonuc["git"] == "baslatildi":
        print("git deposu baslatildi.")
    print(f"Koruyucu ({guard.koruyucu_yolu(klasor).relative_to(klasor)}): {sonuc['koruyucu']}")
    yol = ayar_yolu(klasor)
    if sonuc["ayar"] == "mevcut":
        print(f"Ayar dosyasi zaten var, degistirilmedi: {yol}")
    else:
        print(f"Ayar dosyasi olusturuldu: {yol}")
    print(f"Proje hazir: {klasor}\nRolleri ve modelleri {yol.name} dosyasindan duzenleyebilirsiniz.")
    return CIKIS_TAMAM


def _ayar_goster(ayar: Ayar) -> None:
    print("Plan:")
    for ad in ayar.akis:
        r = ayar.roller[ad]
        print(f"  {ad}: {r.calistirici} / {r.model or 'varsayilan model'}" + ("  (dogrulama)" if r.dogrulama else ""))
    print(f"  butce: {ayar.butce_token} token, en fazla {ayar.azami_duzeltme} duzeltme, adim zaman asimi {ayar.zaman_asimi_sn} sn")


def komut_calistir(args, girdi, calistirici_uret) -> int:
    try:
        klasor = guvenli_klasor(args.klasor)
        ayar = ayar_yukle(klasor)
    except (KlasorHatasi, AyarHatasi) as hata:
        print(f"HATA: {hata}")
        return CIKIS_HATA
    if args.butce is not None:
        from dataclasses import replace

        if args.butce < 1:
            print("HATA: --butce 1 veya daha buyuk olmali")
            return CIKIS_KULLANIM
        ayar = replace(ayar, butce_token=args.butce)
    print(f"Klasor: {klasor}\nGorev: {args.gorev}")
    _ayar_goster(ayar)
    print(
        "Not: ajan bu klasorde komut calistirabilir ve dosya yazabilir (otomatik izinle). OpenCode rollerinde koruyucu "
        "klasor disi okuma/yazmayi, .env ve kendi izin dosyasini engeller; KABUK komutlari yalnizca desen kurallariyla "
        "(.., surucu yolu, ~) sinirlanir, dolayli yontemlerle asilabilir. Klasor DISINDAKI etki geri alinamaz."
    )
    if not _soru_sor("Plan onaylansin ve calistirilsin mi?", args.evet, girdi):
        print("Iptal edildi; hicbir sey calistirilmadi.")
        return CIKIS_TAMAM
    try:
        sonuc = calistir_hat(
            klasor, args.gorev, ayar, calistirici_uret, lambda s: _soru_sor(s, args.evet, girdi), bildir=print
        )
    except (HatHatasi, KlasorHatasi, snapshot.GitHatasi, CalistiriciHatasi) as hata:
        print(f"HATA: {hata}")
        return CIKIS_HATA
    print("\n--- Ozet ---")
    for a in sonuc.adimlar:
        durum = "ok" if a.ok else "HATA"
        dog = f", dogrulama: {a.dogrulama}" if a.dogrulama else ""
        print(f"  {a.sira}. {a.rol} [{durum}] {a.token_girdi}+{a.token_cikti} token (onbellek {a.token_onbellek}), {a.sure_sn} sn{dog}")
        if a.hata:
            print(f"     {a.hata}")
    print(f"Toplam: {sonuc.token_toplam} token. Durum: {sonuc.durum}. {sonuc.mesaj}".rstrip())
    if sonuc.kayit_yolu:
        print(f"Kayit: {sonuc.kayit_yolu}")
    print("\a", end="")  # bitti sesi
    return CIKIS_TAMAM if sonuc.durum in ("onaylandi", "geri_alindi", "degisiklik_yok") else CIKIS_HATA


def komut_geri_al(args, girdi) -> int:
    try:
        sayi = geri_al(args.klasor, lambda s: _soru_sor(s, args.evet, girdi), bildir=print)
    except (HatHatasi, KlasorHatasi, snapshot.GitHatasi) as hata:
        print(f"HATA: {hata}")
        return CIKIS_HATA
    print(f"{sayi} dosya geri alindi." if sayi else "Hicbir sey geri alinmadi.")
    return CIKIS_TAMAM


def komut_durum(args) -> int:
    print(f"aktapokus-ajan {__version__}")
    oc = opencode_bul()
    print(f"OpenCode CLI: {oc + '  ' + _surum_oku([oc, '--version']) if oc else 'bulunamadi'}")
    import shutil

    cl = shutil.which("claude")
    print(f"Claude Code CLI: {cl + '  ' + _surum_oku([cl, '--version']) if cl else 'bulunamadi (kurulu degil ya da PATH disinda)'}")
    if getattr(args, "arac", False):
        return CIKIS_TAMAM
    try:
        klasor = guvenli_klasor(args.klasor)
    except KlasorHatasi as hata:
        print(f"Klasor: {hata}")
        return CIKIS_TAMAM
    print(f"Klasor: {klasor}")
    print(f"  git deposu: {'evet' if snapshot.hazir_mi(klasor) else 'hayir'}")
    eksik = guard.dogrula(klasor)
    print("  koruyucu: " + ("etkin (klasor disi + .env engelli)" if not eksik else "ETKIN DEGIL: " + "; ".join(eksik)))
    try:
        _ayar_goster(ayar_yukle(klasor))
    except AyarHatasi as hata:
        print(f"  ayar: {hata}")
    kayit = son_kayit(klasor)
    if kayit:
        print(f"  son calistirma: {kayit['zaman']} | {kayit['durum']} | {kayit['token_toplam']} token | {kayit['gorev'][:60]}")
    return CIKIS_TAMAM


def kur_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="aktapokus", description="Rol/model bazli kod ajani katmani (OpenCode, Claude Code)")
    alt = p.add_subparsers(dest="komut", required=True)
    a = alt.add_parser("ac", help="Klasoru proje olarak hazirla (ayar dosyasi + git)")
    a.add_argument("klasor")
    a.add_argument("--git-baslat", action="store_true", help="Klasor git deposu degilse 'git init' yap")
    c = alt.add_parser("calistir", help="Gorevi rollere dagitarak calistir")
    c.add_argument("gorev")
    c.add_argument("--klasor", default=".")
    c.add_argument("--butce", type=int, help="Bu calistirma icin token butcesi (ayari ezer)")
    c.add_argument("--evet", action="store_true", help="Sorulari otomatik onayla (dikkat: degisiklikler korunur)")
    g = alt.add_parser("geri-al", help="Son calistirmanin oncesine don")
    g.add_argument("--klasor", default=".")
    g.add_argument("--evet", action="store_true")
    d = alt.add_parser("durum", help="CLI'lar, proje ayari ve son calistirma")
    d.add_argument("--klasor", default=".")
    d.add_argument("--arac", action="store_true", help="Yalniz CLI araclarini (OpenCode, Claude Code) denetle; klasor bilgisi yazma")
    b = alt.add_parser("baglam", help="Ortak baglam dosyalarini (AGENTS.md blogu, .aktapokus/DURUM.md) simdi guncelle")
    b.add_argument("--klasor", default=".")
    t = alt.add_parser("telegram", help="Telegram botunu baslat (token: AKTAPOKUS_TELEGRAM_TOKEN ya da ~/.aktapokus/telegram.token)")
    t.add_argument("--klasor", help="Acilista secilecek proje klasoru")
    t.add_argument("--kok", action="append", help="Telefondan secilebilecek proje kok klasoru (kaydedilir; birden cok kez verilebilir)")
    u = alt.add_parser("ui", help="Canli arayuzu baslat (yalniz bu bilgisayardan erisilir)")
    u.add_argument("--klasor", help="Acilista secilecek proje klasoru")
    u.add_argument("--port", type=int, default=0)
    u.add_argument("--tarayici", action="store_true", help="Varsayilan tarayicida ac")
    u.add_argument("--uygulama", action="store_true", help="Masaustu uygulamasi modu: sessiz sunucu + adres cubugu olmayan kendi penceresi; pencere kapaninca kapanir")
    return p


def main(argv: list[str] | None = None, girdi: Callable[[str], str] = input, calistirici_uret: Callable[[str], Calistirici] = calistirici_olustur) -> int:
    args = kur_parser().parse_args(argv)
    try:
        if args.komut == "ac":
            return komut_ac(args, girdi)
        if args.komut == "calistir":
            return komut_calistir(args, girdi, calistirici_uret)
        if args.komut == "geri-al":
            return komut_geri_al(args, girdi)
        if args.komut == "baglam":
            try:
                klasor = guvenli_klasor(args.klasor)
                for dosya, durum in baglam.guncelle(klasor, ayar_yukle(klasor)).items():
                    print(f"  {dosya}: {durum}")
                print(f"Kurallari duzenlemek icin: {baglam.kaynak_yolu(klasor)}")
                return CIKIS_TAMAM
            except (KlasorHatasi, AyarHatasi, OSError) as hata:
                print(f"HATA: {hata}")
                return CIKIS_HATA
        if args.komut == "telegram":
            from .telegram import telegram_calistir

            return telegram_calistir(args.klasor, kokler=args.kok)
        if args.komut == "ui":
            if args.uygulama:
                from .uygulama import uygulama_calistir

                return uygulama_calistir(args.klasor, args.port)
            from .arayuz import ui_calistir

            return ui_calistir(args.klasor, args.port, args.tarayici)
        return komut_durum(args)
    finally:
        hepsini_kapat()  # acik kalan OpenCode sunucu surecleri biterken kapatilir


def main_giris() -> None:
    for akim in (sys.stdout, sys.stderr):
        try:
            akim.reconfigure(encoding="utf-8")
        except Exception:
            pass
    sys.exit(main())
