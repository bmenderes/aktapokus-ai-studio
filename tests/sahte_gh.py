"""Sahte `gh` (GitHub CLI): ag ve hesap gerektirmeden github.py'yi sinar. AKTAPOKUS_GH bu dosyayi gosterir.
Cagrilar SAHTE_GH_LOG dosyasina JSON satiri olarak yazilir. Davranis ortam degiskenleriyle: SAHTE_GH_GIRIS=0 (giris yok),
SAHTE_GH_PR_YOK=1 (PR yok), SAHTE_GH_HATA=1 (her komut hata verir ve stderr'e token benzeri dizge yazar)."""

import json
import os
import subprocess
import sys

a = sys.argv[1:]
log = os.environ.get("SAHTE_GH_LOG")
if log:
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps({"argv": a, "cwd": os.getcwd(), "dizin": os.environ.get("GH_CONFIG_DIR")}) + "\n")

TOKEN = "ghp_" + "A" * 36


def bitir(metin="", kod=0, hata=""):
    sys.stdout.write(metin)
    sys.stderr.write(hata)
    sys.exit(kod)


if a[:2] == ["auth", "login"]:  # cihaz kodu akisi: SAHTE_GH_ONAY dosyasi olusunca (kullanici tarayicida onaylamis gibi) basariyla biter
    sys.stderr.write("! First copy your one-time code: ABCD-1234\nPress Enter to open github.com in your browser...\n")
    sys.stderr.flush()
    onay = os.environ.get("SAHTE_GH_ONAY", "")
    for _ in range(100):
        if onay and os.path.exists(onay):
            cfg = os.environ.get("GH_CONFIG_DIR")
            if cfg:
                os.makedirs(cfg, exist_ok=True)
                with open(os.path.join(cfg, "hosts.yml"), "w", encoding="utf-8") as f:
                    f.write("github.com:" + chr(10) + "    user: sahte" + chr(10))
            bitir()
        import time
        time.sleep(0.1)
    bitir(kod=1, hata="zaman asimi")
if a[:2] == ["auth", "logout"]:
    bitir()
if os.environ.get("SAHTE_GH_HATA") == "1":
    bitir(kod=1, hata=f"gh: beklenmeyen hata, kimlik {TOKEN}")
if a[:2] == ["api", "user"]:
    if os.environ.get("SAHTE_GH_GIRIS") == "0":
        bitir(kod=4, hata="To get started with GitHub CLI, please run:  gh auth login")
    cfg = os.environ.get("GH_CONFIG_DIR", "")
    if os.path.basename(os.path.dirname(cfg)).endswith("-hesaplar"):  # ek hesap oturumu: kullanici adi klasor adidir (_yeni: yeni giris yapilan hesap)
        ad = os.path.basename(cfg)
        bitir(json.dumps({"login": os.environ.get("SAHTE_GH_YENI", "ikinci-kullanici") if ad == "_yeni" else ad, "name": "Ek Kisi"}))
    bitir(json.dumps({"login": os.environ.get("SAHTE_GH_VARSAYILAN", "sahte-kullanici"), "name": "Sahte Kisi"}))
if a[:2] == ["api", "user/orgs?per_page=100"]:
    if os.environ.get("SAHTE_GH_ORG_HATA") == "1":
        bitir(kod=1, hata="orgs hatasi")
    bitir(json.dumps([{"login": "sahte-org"}, {"login": "bos-org"}]))
if a[:2] == ["repo", "list"] and len(a) > 2 and not a[2].startswith("--"):
    if a[2] == "bos-org":
        bitir("[]")
    bitir(json.dumps([
        {"nameWithOwner": "sahte-org/kurumsal", "description": "org deposu", "isPrivate": True, "updatedAt": "2026-10-05T00:00:00Z", "url": "https://github.com/sahte-org/kurumsal"},
        {"nameWithOwner": "sahte-kullanici/proje-bir", "description": "ilk", "isPrivate": True, "updatedAt": "2026-10-01T00:00:00Z", "url": "https://github.com/sahte-kullanici/proje-bir"},
    ]))
if a[:2] == ["repo", "list"]:
    bitir(json.dumps([
        {"nameWithOwner": "sahte-kullanici/proje-bir", "description": "ilk", "isPrivate": True, "updatedAt": "2026-10-01T00:00:00Z", "url": "https://github.com/sahte-kullanici/proje-bir"},
        {"nameWithOwner": "sahte-kullanici/proje-iki", "description": None, "isPrivate": False, "updatedAt": "2026-09-01T00:00:00Z", "url": "https://github.com/sahte-kullanici/proje-iki"},
    ]))
if a[:2] == ["repo", "clone"]:
    depo, hedef = a[2], a[3]
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(["git", "init", "-q", hedef], check=True)
    with open(os.path.join(hedef, "README.md"), "w", encoding="utf-8") as f:
        f.write("# " + depo + "\n")
    subprocess.run([*git, "-C", hedef, "add", "-A"], check=True)
    subprocess.run([*git, "-C", hedef, "commit", "-qm", "ilk"], check=True)
    subprocess.run(["git", "-C", hedef, "remote", "add", "origin", f"https://github.com/{depo}.git"], check=True)
    bitir()
if a[:2] == ["issue", "list"]:
    bitir(json.dumps([{"number": 7, "title": "Giris sayfasi hatali", "state": "OPEN", "labels": [{"name": "bug"}], "url": "https://github.com/sahte-kullanici/proje-bir/issues/7", "updatedAt": "2026-10-02T00:00:00Z"}]))
if a[:2] == ["issue", "view"]:
    bitir(json.dumps({"number": int(a[2]), "title": "Giris sayfasi hatali", "body": "Adimlar:\n1. Ac\n" + "uzun " * 3000, "url": "https://github.com/sahte-kullanici/proje-bir/issues/" + a[2], "state": "OPEN"}))
if a[:2] == ["issue", "comment"]:
    bitir("https://github.com/sahte-kullanici/proje-bir/issues/" + a[2] + "#issuecomment-1\n")
if a[:2] == ["pr", "create"]:
    bitir("\nCreating pull request...\nhttps://github.com/sahte-kullanici/proje-bir/pull/12\n")
if a[:2] == ["pr", "view"]:
    if os.environ.get("SAHTE_GH_PR_YOK") == "1":
        bitir(kod=1, hata='no pull requests found for branch "ozellik"')
    bitir(json.dumps({"number": 12, "title": "Ozellik", "state": "OPEN", "url": "https://github.com/sahte-kullanici/proje-bir/pull/12", "isDraft": False, "reviewDecision": "",
                      "statusCheckRollup": [{"conclusion": "SUCCESS", "status": "COMPLETED"}, {"conclusion": "FAILURE", "status": "COMPLETED"}, {"conclusion": "", "status": "IN_PROGRESS"}]}))
bitir(kod=2, hata="sahte gh: bilinmeyen komut " + " ".join(a))
