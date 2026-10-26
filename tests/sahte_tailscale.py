"""Sahte `tailscale` CLI'i: ag/hesap gerektirmeden uzak.py'yi sinar. AKTAPOKUS_TAILSCALE bu dosyayi gosterir.
SAHTE_TS_MOD: calisiyor (varsayilan) | durdu | oturumsuz | bozuk | ip-yok | hata. SAHTE_TS_IP: `ip -4` ciktisi (varsayilan 127.0.0.2)."""
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
sys.stderr.write("bilinmeyen komut\n")
sys.exit(2)
