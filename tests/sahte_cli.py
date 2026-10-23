"""Tanimla eklenen CLI'lar icin sahte program (yalnizca testler icin).
Argumanlar: --kip metin|json|jsonl, --stdin (istemi stdin'den oku; yoksa son arguman istemdir).
Aldigi her seyi SAHTE_CLI_KAYIT dosyasina yazar. Istemde FAIL -> cikis kodu 3, HATA -> is_error=true."""

import json
import os
import sys

a = sys.argv[1:]
stdin_kipi = "--stdin" in a
istem = sys.stdin.buffer.read().decode("utf-8") if stdin_kipi else a[-1]
kip = a[a.index("--kip") + 1] if "--kip" in a else "metin"
kayit = os.environ.get("SAHTE_CLI_KAYIT")
if kayit:
    with open(kayit, "w", encoding="utf-8") as f:
        json.dump({"args": a, "istem": istem, "cwd": os.getcwd(), "pwd": os.environ.get("PWD")}, f)
if "FAIL" in istem:
    sys.stderr.write("patladi")
    sys.exit(3)
yanit = "yanit: " + istem[:20]
hata = "HATA" in istem
if kip == "metin":
    print(yanit)
elif kip == "json":
    print(json.dumps({"sonuc": {"metin": yanit}, "bayrak": {"hata": hata}, "kullanim": {"gir": 11, "cik": 5, "onb": 40}}))
else:
    print(json.dumps({"tur": "basladi"}))
    print(json.dumps({"tur": "mesaj", "ogeler": [{"metin": yanit}]}))
    print("json olmayan satir")
    print(json.dumps({"tur": "bitti", "kullanim": {"gir": 11, "cik": 5, "onb": 40}, "hata": hata or None}))
