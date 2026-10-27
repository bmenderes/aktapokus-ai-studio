"""Sahte `tailscale` CLI'i: ag/hesap gerektirmeden uzak.py'yi sinar. AKTAPOKUS_TAILSCALE bu dosyayi gosterir.
SAHTE_TS_MOD: calisiyor (varsayilan) | durdu | oturumsuz | bozuk | ip-yok | hata | serve-kapali (HTTPS etkin degil).
SAHTE_TS_SERVE: `serve` yapilandirmasinin tutuldugu JSON dosyasi (varsayilan: yok -> serve komutlari desteklenmez). SAHTE_TS_IP: `ip -4` ciktisi (varsayilan 127.0.0.2)."""
import json
import os
import sys

mod = os.environ.get("SAHTE_TS_MOD", "calisiyor")
ip = os.environ.get("SAHTE_TS_IP", "127.0.0.2")
a = sys.argv[1:]
if mod == "hata":
    sys.stderr.write("tailscale: hata\n")
    sys.exit(1)
if a[:2] == ["status", "--json"]:
    if mod == "bozuk":
        sys.stdout.write("{bozuk json")
        sys.exit(0)
    durum = {"calisiyor": "Running", "ip-yok": "Running", "durdu": "Stopped", "oturumsuz": "NeedsLogin"}.get(mod, "Running")
    sys.stdout.write(json.dumps({"BackendState": durum, "Self": {"DNSName": "bilgisayarim.tailabc12.ts.net.", "TailscaleIPs": [ip]}}))
    sys.exit(0)
if a[:2] == ["ip", "-4"]:
    if mod == "ip-yok":
        sys.exit(0)
    sys.stdout.write(ip + "\n")
    sys.exit(0)
if a[:1] == ["serve"] and os.environ.get("SAHTE_TS_SERVE"):
    dosya = os.environ["SAHTE_TS_SERVE"]
    try:
        cfg = json.load(open(dosya, encoding="utf-8"))
    except (OSError, ValueError):
        cfg = {"Web": {}}
    if a[1:] == ["status", "--json"]:
        sys.stdout.write(json.dumps(cfg))
        sys.exit(0)
    if mod == "serve-kapali":
        sys.stderr.write("Serve is not enabled on your tailnet.\nTo enable, visit: https://login.tailscale.com/f/serve?node=abc\n")
        sys.exit(1)
    if a[-1] == "off" and a[1] == "--https=443":
        cfg["Web"].pop("bilgisayarim.tailabc12.ts.net:443", None)
    elif "--bg" in a:
        cfg["Web"]["bilgisayarim.tailabc12.ts.net:443"] = {"Handlers": {"/": {"Proxy": a[-1]}}}
    else:
        sys.stderr.write("bilinmeyen serve komutu\n")
        sys.exit(2)
    json.dump(cfg, open(dosya, "w", encoding="utf-8"))
    sys.exit(0)
sys.stderr.write("bilinmeyen komut\n")
sys.exit(2)
