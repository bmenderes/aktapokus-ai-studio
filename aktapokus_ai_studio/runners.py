"""Calistiricilar: bir kod ajani CLI'ini (OpenCode, Claude Code) tek bir arayuzle surer.

Bir calistirici bir istemi bir klasorde calistirir ve sonucu (metin, token, hata) dondurur.
Model/ajan secimi her cagrida yapilir. Alt surec argüman listesiyle (kabuksuz) baslatilir.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from . import guard
from .config import AYAR_KLASORU

AZAMI_ISTEM_UZUNLUGU = 24_000  # Windows komut satiri siniri (~32k) icin guvenli pay


class CalistiriciHatasi(Exception):
    pass


@dataclass
class CalistirmaSonucu:
    ok: bool
    metin: str = ""
    token_girdi: int = 0
    token_cikti: int = 0
    token_onbellek: int = 0
    sure_sn: float = 0.0
    hata: str | None = None
    oturum: str | None = None  # Claude Code konusma kimligi (kayitta saklanir: 'Claude Code'da devam et')

    @property
    def token_yeni(self) -> int:
        """Butceye sayilan token: girdi + cikti (onbellekten okunan ayri tutulur)."""
        return self.token_girdi + self.token_cikti


class Calistirici:
    ad = ""
    mcp: tuple = ()  # bu calismada ETKIN MCP sunuculari (mcptanim.McpTanim); Uygulama her adimdan once projeye gore atar

    def calistir(
        self,
        istem: str,
        klasor: Path,
        model: str | None = None,
        agent: str | None = None,
        zaman_asimi_sn: int = 900,
        onayli: bool = True,
    ) -> CalistirmaSonucu:
        raise NotImplementedError

    def kapat(self) -> None:
        """Calistiricinin actigi kalici kaynaklari (ornegin sunucu sureci) kapatir."""

    def durdur(self) -> bool:
        """Calisan istegi durdurmayi dener (desteklemeyen calistiricilarda False: iptal bir sonraki adimda gecerli olur)."""
        return False


def _istemi_denetle(istem: str, azami: int = AZAMI_ISTEM_UZUNLUGU) -> None:
    if not istem.strip():
        raise CalistiriciHatasi("Bos istem gonderilemez")
    if len(istem) > azami:
        raise CalistiriciHatasi(f"Istem cok uzun ({len(istem)} karakter, sinir {azami})")
    if istem.lstrip().startswith("-"):
        raise CalistiriciHatasi("Istem '-' ile baslayamaz (secenek sanilirdi)")


def _metin(deger) -> str:
    return deger.decode("utf-8", errors="replace") if isinstance(deger, bytes) else (deger or "")


def _stdinli_calistir(komut, istem: str, klasor: Path, zaman_asimi_sn: int):
    """Istemi UTF-8 BAYT olarak stdin'e verir. text=True kullanilmaz: Windows'ta metin kipi '\n' -> '\r\n' cevirir ve
    yerel kod sayfasi kullanir (gercek test: istem 'aynen' ulasmadi). Ciktilar str'ye cevrilmis halde doner."""
    islem = subprocess.run(
        komut, input=istem.encode("utf-8"), cwd=str(klasor), env=_alt_surec_ortami(Path(klasor)),
        capture_output=True, timeout=zaman_asimi_sn,
    )
    islem.stdout, islem.stderr = _metin(islem.stdout), _metin(islem.stderr)
    return islem


def _alt_surec_ortami(klasor: Path) -> dict[str, str]:
    """cwd= tek basina yetmez: OpenCode calisma klasorunu PWD ortam degiskeninden okuyor (gercek denemede,
    bir kabuktan baslatilinca ajan hedef klasor yerine kabugun klasorune yazdi). PWD'yi hedef klasore ayarla."""
    ortam = os.environ.copy()
    ortam["PWD"] = str(klasor)
    ortam.pop("OLDPWD", None)
    return ortam


def _surum_anahtari(yol: Path) -> tuple[int, ...]:
    sayilar = re.findall(r"\d+", yol.parent.name)
    return tuple(int(s) for s in sayilar)


def opencode_bul() -> str | None:
    """OpenCode CLI yolu: AKTAPOKUS_OPENCODE, PATH, sonra masaustu uygulamasinin paketli CLI'i."""
    ortam = os.environ.get("AKTAPOKUS_OPENCODE")
    if ortam and Path(ortam).is_file():
        return ortam
    yol = shutil.which("opencode")
    if yol:
        return yol
    appdata = os.environ.get("APPDATA")
    if appdata:
        kok = Path(appdata) / "ai.opencode.desktop" / "cli"
        adaylar = [p for p in kok.glob("*/opencode-cli*") if p.is_file() and p.suffix in ("", ".exe")]
        if adaylar:
            return str(sorted(adaylar, key=_surum_anahtari)[-1])
    return None


def opencode_olaylarini_coz(cikti: str) -> CalistirmaSonucu:
    """`opencode run --format json` satirlarindan metin ve token toplamini cikarir."""
    metinler: list[str] = []
    girdi = cikti_t = onbellek = 0
    hata: str | None = None
    for satir in cikti.splitlines():
        satir = satir.strip()
        if not satir.startswith("{"):
            continue
        try:
            olay = json.loads(satir)
        except json.JSONDecodeError:
            continue
        tur = olay.get("type")
        parca = olay.get("part") or {}
        if tur == "text" and isinstance(parca.get("text"), str):
            metinler.append(parca["text"])
        elif tur == "step_finish":
            t = parca.get("tokens") or {}
            girdi += int(t.get("input") or 0)
            cikti_t += int(t.get("output") or 0) + int(t.get("reasoning") or 0)
            onbellek += int((t.get("cache") or {}).get("read") or 0)
        elif tur == "error" and hata is None:
            hata = json.dumps(olay, ensure_ascii=False)[:300]
    return CalistirmaSonucu(
        ok=hata is None,
        metin="\n".join(metinler).strip(),
        token_girdi=girdi,
        token_cikti=cikti_t,
        token_onbellek=onbellek,
        hata=hata,
    )


class OpenCodeCalistirici(Calistirici):
    ad = "opencode"

    def __init__(self, cli_yolu: str | None = None):
        self.cli_yolu = cli_yolu

    def komut(self, istem: str, model: str | None, agent: str | None, onayli: bool) -> list[str]:
        cli = self.cli_yolu or opencode_bul()
        if not cli:
            raise CalistiriciHatasi(
                "OpenCode CLI bulunamadi. PATH'e ekleyin veya AKTAPOKUS_OPENCODE ortam degiskenini ayarlayin (kurulum: https://opencode.ai). "
                "OpenCode kullanmayacaksaniz Ayarlar > Roller'den kurulu bir CLI (Claude Code, Codex) secin."
            )
        _istemi_denetle(istem)
        komut = [cli, "run", "--standalone", "--format", "json"]
        if onayli:
            komut.append("--auto")
        if model:
            komut += ["--model", model]
        if agent:
            komut += ["--agent", agent]
        komut.append(istem)
        return komut

    def calistir(self, istem, klasor, model=None, agent=None, zaman_asimi_sn=900, onayli=True):
        komut = self.komut(istem, model, agent, onayli)
        baslangic = time.monotonic()
        try:
            islem = subprocess.run(
                komut,
                cwd=str(klasor),
                env=_alt_surec_ortami(Path(klasor)),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdin=subprocess.DEVNULL,
                timeout=zaman_asimi_sn,
            )
        except subprocess.TimeoutExpired:
            return CalistirmaSonucu(False, hata=f"Zaman asimi ({zaman_asimi_sn} sn)", sure_sn=time.monotonic() - baslangic)
        sonuc = opencode_olaylarini_coz(islem.stdout)
        sonuc.sure_sn = time.monotonic() - baslangic
        if islem.returncode != 0 and sonuc.ok:
            sonuc.ok = False
            sonuc.hata = f"OpenCode cikis kodu {islem.returncode}: {(islem.stderr or islem.stdout).strip()[-300:]}"
        return sonuc


# Claude Code'un hassas dosyalari OKUMASINI/DEGISTIRMESINI engelleyen izin kurallari (gercek denemeyle dogrulandi: Read araci reddedildi).
# Not: Bash'e genis izin verilirse `cat .env` bu kurallari atlayabilir; bu yuzden calistirici Bash/PowerShell'i izinlemez.
CLAUDE_YASAK_KURALLARI = [
    f"{arac}({desen})"
    for arac in ("Read", "Edit")
    for desen in (
        "**/.env", "**/.env.*", "**/.netrc",
        "**/id_rsa*", "**/id_ed25519*", "**/.npmrc*", "**/.pypirc*", "**/credentials*",  # guard.hassas_dosyalar'in onek listesi
        "**/*.pem", "**/*.key", "**/*.pfx", "**/*.p12", "**/*.keystore", "**/*.jks",  # ...ve uzanti listesi (testle senkron tutulur)
    )
]


def claude_bul() -> str | None:
    """claude.exe yolu. AKTAPOKUS_CLAUDE ile degistirilebilir. Windows'ta npm'in claude.cmd/claude.ps1 sarmalayicilari
    KULLANILMAZ (arguman/istem cmd.exe tarafindan yorumlanirdi); npm paketinin icindeki yerel claude.exe dogrudan calistirilir."""
    ortam = os.environ.get("AKTAPOKUS_CLAUDE")
    if ortam and Path(ortam).is_file():
        return ortam
    adaylar: list[Path] = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        adaylar.append(Path(appdata) / "npm" / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe")
    npm_kok = shutil.which("npm")
    if npm_kok:
        adaylar.append(Path(npm_kok).resolve().parent / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe")
    adaylar.append(Path.home() / ".local" / "bin" / "claude.exe")  # yerel kurucu
    for aday in adaylar:
        if aday.is_file():
            return str(aday)
    bulunan = shutil.which("claude")
    if bulunan and Path(bulunan).suffix.lower() == ".exe":
        return bulunan
    if bulunan and os.name != "nt":
        return bulunan
    return None


GOREV_AYRACI = "\n\nGOREV:\n"  # pipeline.istem_olustur: [GENEL_KURAL] + [ROLUN: ...] + AYRAC + gorev (+ onceki cikti)


def istemi_ayir(istem: str) -> tuple[str | None, str]:
    """(sistem metni | None, kullanici mesaji). Aktapokus istemi 'KURALLAR: ... ROLUN: ...' ile baslar; Claude'un konusmasinda kullanici mesaji
    olarak SENIN ISTEGIN gorunsun diye kurallar/rol talimati sistem istemine tasinir. Bicim tanidik degilse istem oldugu gibi gider."""
    if istem.startswith("KURALLAR:") and GOREV_AYRACI in istem:
        i = istem.index(GOREV_AYRACI)
        sistem, kullanici = istem[:i].strip(), istem[i + len(GOREV_AYRACI):].strip()
        if sistem and kullanici:
            return sistem, kullanici
    return None, istem


class ClaudeCodeCalistirici(Calistirici):
    """`claude -p` ile Claude Code (2.1.308 ile GERCEK denendi). Istem STDIN'den gider (komut satiri sorunu yok).
    Cikti `stream-json`: her mesaj/arac cagrisi CANLI gelir (ilerleme geri cagrisi); son satir {type: result} (result, is_error, usage,
    total_cost_usd, permission_denials, session_id). acceptEdits modunda klasor DISINA yazma reddedilir; `permissions.deny` Read(**/.env)
    .env okumasini engeller; -p kipinde onay gerektiren her sey reddedilir.

    Oturum kipi (`oturum_kipi`, Ayarlar > Genel > Claude konusmasi): 'tek' = proje basina TEK Claude Code konusmasi (sonraki calistirmalar
    --resume ile ayni konusmaya yazar; Claude Code'da tek satir gorunur), 'yeni' = her calistirmada yeni konusma (eski davranis),
    'hic' = konusma kaydedilmez (--no-session-persistence)."""

    ad = "claude"
    oturum_kipi = "yeni"  # CLI/testlerde eski davranis; arayuz proje ayarindan (varsayilan 'tek') atar
    sohbet = None  # verilirse oturum SOHBET basina tutulur (proje+sohbet); None: eski proje basina tek oturum
    ilerleme = None  # canli olay geri cagrisi: {"tur": "metin"|"arac"|"arac-sonuc", ...} (OpenCode sunucu calistiricisiyla ayni bicim)
    OTURUM_OMRU_SN = 14 * 24 * 3600  # bundan eski konusma surdurulmez; sohbetler kalici oldugu icin uzun

    def __init__(self, cli_yolu: str | None = None):
        self.cli_yolu = cli_yolu
        self._islem = None
        self._durduruldu = False

    def komut(self, ayar_dosyasi: str, model: str | None, onayli: bool, mcp_dosyasi: str | None = None, mcp_adlari: tuple[str, ...] = (), oturum: str | None = None, kalici: bool = True, sistem_dosyasi: str | None = None) -> list[str]:
        cli = self.cli_yolu or claude_bul()
        if not cli:
            raise CalistiriciHatasi(
                "Claude Code CLI bulunamadi (npm install -g @anthropic-ai/claude-code) ya da AKTAPOKUS_CLAUDE ile yol verin. "
                "Baska bir CLI kullanmak icin Ayarlar > Roller'e bakin."
            )
        komut = [cli, "-p", "--output-format", "stream-json", "--verbose", "--settings", ayar_dosyasi]
        if not kalici:
            komut += ["--no-session-persistence"]
        if sistem_dosyasi:
            komut += ["--append-system-prompt-file", sistem_dosyasi]
        if oturum:
            komut += ["--resume", oturum]
        if model:
            komut += ["--model", model]
        if getattr(self, "dusunme", None) in ("low", "medium", "high", "xhigh", "max"):
            komut += ["--effort", self.dusunme]
        if onayli:
            komut += ["--permission-mode", "acceptEdits"]
        if mcp_dosyasi and mcp_adlari:
            # Kullanicinin bu projede etkinlestirdigi sunucularin TUM araclari onaysiz (-p kipinde onay sorulamaz); baska MCP araci acilmaz
            komut += ["--mcp-config", mcp_dosyasi, "--allowedTools", *[f"mcp__{ad}" for ad in mcp_adlari]]
        return komut

    @staticmethod
    def cikti_coz(cikti: str) -> CalistirmaSonucu:
        try:
            veri = json.loads(cikti)
        except json.JSONDecodeError:
            return CalistirmaSonucu(False, hata=f"Claude Code ciktisi JSON degil: {cikti.strip()[:200]}")
        kullanim = veri.get("usage") or {}
        hata_var = bool(veri.get("is_error"))
        # Anthropic usulu: input_tokens onbellek HARICtir; yeni girdi = input + cache_creation, okunan onbellek ayri sayilir.
        girdi = int(kullanim.get("input_tokens") or 0) + int(kullanim.get("cache_creation_input_tokens") or 0)
        metin = str(veri.get("result") or "").strip()
        reddedilen = veri.get("permission_denials") or []
        if reddedilen and not hata_var:
            araclar = sorted({str(r.get("tool_name")) for r in reddedilen if isinstance(r, dict)})
            metin += f"\n[izin reddedildi: {', '.join(araclar)}]"
        return CalistirmaSonucu(
            ok=not hata_var,
            metin=metin,
            token_girdi=girdi,
            token_cikti=int(kullanim.get("output_tokens") or 0),
            token_onbellek=int(kullanim.get("cache_read_input_tokens") or 0),
            hata=str(veri.get("result"))[:300] if hata_var else None,
        )

    # ---- proje basina tek konusma ------------------------------------------------------------------------------------------
    @staticmethod
    def _oturum_yolu(klasor, sohbet: str | None = None) -> Path:
        ek = f"-{sohbet}" if sohbet and re.fullmatch(r"[0-9a-z-]{1,40}", sohbet) else ""
        return Path(klasor) / AYAR_KLASORU / f"claude-oturum{ek}.json"

    def _oturum_oku(self, klasor) -> str | None:
        try:
            d = json.loads(self._oturum_yolu(klasor, self.sohbet).read_text(encoding="utf-8"))
            kimlik, zaman = d["oturum"], float(d["zaman"])
        except (OSError, ValueError, KeyError, TypeError):
            return None
        if not isinstance(kimlik, str) or not re.fullmatch(r"[0-9a-fA-F-]{36}", kimlik) or time.time() - zaman > self.OTURUM_OMRU_SN:
            return None  # proje klasorundeki dosya guvenilmez: yalniz UUID bicimi komuta girer
        return kimlik

    def _oturum_yaz(self, klasor, kimlik: str) -> None:
        try:
            yol = self._oturum_yolu(klasor, self.sohbet)
            yol.parent.mkdir(parents=True, exist_ok=True)
            yol.write_text(json.dumps({"oturum": kimlik, "zaman": time.time()}), encoding="utf-8")
        except OSError:
            pass

    def _oturum_sil(self, klasor) -> None:
        try:
            self._oturum_yolu(klasor, self.sohbet).unlink(missing_ok=True)
        except OSError:
            pass

    # ---- canli akis ----------------------------------------------------------------------------------------------------------
    @staticmethod
    def _girdi_ozeti(girdi) -> dict:
        """Arac girdisinden arayuze yalniz kisa, duz degerler gider (buyuk dosya icerikleri/diff'ler akisa tasinmaz)."""
        if not isinstance(girdi, dict):
            return {}
        return {str(k): (v[:200] if isinstance(v, str) else v) for k, v in list(girdi.items())[:8] if isinstance(v, (str, int, float, bool))}

    def _olay_bildir(self, olay: dict) -> None:
        bildir = self.ilerleme
        if bildir is None:
            return
        try:  # arayuz geri cagrisi (ve olay bicimi) hicbir zaman calistirmayi bozmaz: Claude bazi olaylarda "message"i duz metin gonderir
            mesaj = olay.get("message")
            icerik = mesaj.get("content") if isinstance(mesaj, dict) else None
            if not isinstance(icerik, list):
                return
            for c in icerik:
                if not isinstance(c, dict):
                    continue
                if olay.get("type") == "assistant" and c.get("type") == "text" and c.get("text"):
                    bildir({"tur": "metin", "parca": str(c["text"]) + "\n"})
                elif olay.get("type") == "assistant" and c.get("type") == "tool_use":
                    bildir({"tur": "arac", "ad": c.get("name"), "girdi": self._girdi_ozeti(c.get("input"))})
                elif olay.get("type") == "user" and c.get("type") == "tool_result":
                    bildir({"tur": "arac-sonuc", "hata": bool(c.get("is_error"))})
        except Exception:
            pass  # arayuz geri cagrisi hicbir zaman calistirmayi bozmaz

    @staticmethod
    def _surec_oldur(islem) -> None:
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/PID", str(islem.pid), "/T", "/F"], capture_output=True, timeout=15)  # alt surecler de
            else:
                islem.kill()
        except Exception:
            try:
                islem.kill()
            except Exception:
                pass

    def durdur(self) -> bool:
        islem = self._islem
        if islem is None or islem.poll() is not None:
            return False
        self._durduruldu = True
        self._surec_oldur(islem)
        return True

    def _akis(self, komut, istem: str, klasor, zaman_asimi_sn: int):
        """Claude'u baslatir, stdout'u SATIR SATIR okuyup canli bildirir. (cikis_kodu, result olayi | None, stderr metni, zaman_asimi_oldu_mu)."""
        islem = subprocess.Popen(
            komut, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(klasor), env=_alt_surec_ortami(Path(klasor)),
        )
        self._islem = islem
        hatalar: list[bytes] = []
        hata_is = threading.Thread(target=lambda: hatalar.append(islem.stderr.read()), daemon=True)  # stderr dolup tikamasin
        hata_is.start()
        zaman = {"asildi": False}
        son_hareket = [time.monotonic()]  # akistan her satir (arac, metin, sonuc) sureyi yeniden baslatir: ilerleyen gorev zaman asimiyla oldurulmez
        bitti_olayi = threading.Event()

        def bekci() -> None:
            mutlak = time.monotonic() + min(zaman_asimi_sn * 4, 14400)  # mutlak ust sinir: 4 kat (en cok 4 saat)
            aralik = min(2.0, max(0.05, zaman_asimi_sn / 4))
            while not bitti_olayi.wait(aralik):
                simdi = time.monotonic()
                if simdi - son_hareket[0] > zaman_asimi_sn or simdi > mutlak:
                    zaman["asildi"] = True
                    self._surec_oldur(islem)
                    return

        sayac = threading.Thread(target=bekci, daemon=True)
        sayac.start()
        sonuc_olayi = None
        try:
            try:
                islem.stdin.write(istem.encode("utf-8"))  # UTF-8 BAYT: Windows metin kipi '\n' -> '\r\n' cevirirdi
                islem.stdin.close()
            except OSError:
                pass
            for ham in islem.stdout:
                son_hareket[0] = time.monotonic()
                satir = ham.decode("utf-8", errors="replace").strip()
                if not satir.startswith("{"):
                    continue
                try:
                    olay = json.loads(satir)
                except ValueError:
                    continue
                if isinstance(olay, dict) and olay.get("type") == "result":
                    sonuc_olayi = olay
                elif isinstance(olay, dict):
                    self._olay_bildir(olay)
            islem.wait()
        finally:
            bitti_olayi.set()
            self._islem = None
        hata_is.join(2)
        return islem.returncode, sonuc_olayi, b"".join(hatalar).decode("utf-8", errors="replace"), zaman["asildi"]

    def calistir(self, istem, klasor, model=None, agent=None, zaman_asimi_sn=900, onayli=True):
        if not istem.strip():
            raise CalistiriciHatasi("Bos istem gonderilemez")
        if len(istem) > 1_000_000:
            raise CalistiriciHatasi("Istem cok uzun (1 milyon karakter siniri)")
        import tempfile

        baslangic = time.monotonic()
        self._durduruldu = False
        with tempfile.TemporaryDirectory(prefix="aktapokus-claude-") as gecici:
            ayar = Path(gecici) / "ayar.json"
            yasak = list(CLAUDE_YASAK_KURALLARI)
            if guard.hassas_dosyalar(klasor):
                # GERCEK denemeyle dogrulandi: Read kurallari varken bile `Get-ChildItem -Recurse | Select-String` .env icerigini yazdirdi.
                # Gizli dosya olan klasorde kabuk araclari tumden kapali; model yalniz Read/Glob/Grep (yasak kurallarina uyar) kullanir.
                yasak += ["Bash", "PowerShell"]
            ayar.write_text(json.dumps({"permissions": {"deny": yasak}}), encoding="utf-8")
            mcp_dosyasi = None
            if self.mcp:
                from . import mcptanim

                mcp_dosyasi = str(Path(gecici) / "mcp.json")
                Path(mcp_dosyasi).write_text(json.dumps(mcptanim.claude_ayari(list(self.mcp))), encoding="utf-8")
            sistem, kullanici = istemi_ayir(istem)
            sistem_dosyasi = None
            if sistem:
                sistem_dosyasi = str(Path(gecici) / "sistem.txt")
                Path(sistem_dosyasi).write_text(sistem, encoding="utf-8")
            oturum = self._oturum_oku(klasor) if self.oturum_kipi == "tek" else None
            while True:
                komut = self.komut(str(ayar), model, onayli, mcp_dosyasi, tuple(t.ad for t in self.mcp), oturum=oturum, kalici=self.oturum_kipi != "hic", sistem_dosyasi=sistem_dosyasi)
                kod, olay, hata_metni, asildi = self._akis(komut, kullanici, klasor, zaman_asimi_sn)
                kayip = oturum and "no conversation found" in (hata_metni + str((olay or {}).get("result", ""))).lower()
                if kayip:  # konusma silinmis: yeni baslat (bir kez)
                    self._oturum_sil(klasor)
                    oturum = None
                    continue
                break
        sure = time.monotonic() - baslangic
        if asildi:
            return CalistirmaSonucu(False, hata=f"Zaman asimi ({zaman_asimi_sn} sn)", sure_sn=sure)
        if self._durduruldu:
            return CalistirmaSonucu(False, hata="Durduruldu", sure_sn=sure)
        if olay is None:
            return CalistirmaSonucu(False, hata=f"Claude Code sonuc dondurmedi (cikis kodu {kod}): {hata_metni.strip()[-300:]}", sure_sn=sure)
        sonuc = self.cikti_coz(json.dumps(olay))
        sonuc.sure_sn = sure
        if kod != 0 and sonuc.ok:
            sonuc.ok = False
            sonuc.hata = f"Claude Code cikis kodu {kod}: {hata_metni.strip()[-300:]}"
        kimlik = olay.get("session_id")
        if isinstance(kimlik, str) and re.fullmatch(r"[0-9a-fA-F-]{36}", kimlik) and self.oturum_kipi != "hic":
            sonuc.oturum = kimlik  # kaydedilen konusma: kayitta durur, Claude Code'da --resume ile surdurulebilir
            if self.oturum_kipi == "tek":
                self._oturum_yaz(klasor, kimlik)
        return sonuc


def codex_bul() -> list[str] | None:
    """Codex'i baslatacak komut oneki: [node, codex.js] ya da dogrudan codex.exe. AKTAPOKUS_CODEX ile degistirilebilir.
    Windows'ta npm'in codex.cmd/codex.ps1 sarmalayicilari KULLANILMAZ: istem/arguman cmd.exe tarafindan yorumlanirdi."""
    ortam = os.environ.get("AKTAPOKUS_CODEX")
    if ortam and Path(ortam).is_file():
        return [ortam] if Path(ortam).suffix.lower() == ".exe" else [shutil.which("node") or "node", ortam]
    node = shutil.which("node")
    adaylar = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        adaylar.append(Path(appdata) / "npm" / "node_modules" / "@openai" / "codex" / "bin" / "codex.js")
    npm_kok = shutil.which("npm")
    if npm_kok:
        adaylar.append(Path(npm_kok).resolve().parent / "node_modules" / "@openai" / "codex" / "bin" / "codex.js")
    if node:
        for js in adaylar:
            if js.is_file():
                return [node, str(js)]
    exe = shutil.which("codex")
    if exe and Path(exe).suffix.lower() == ".exe":
        return [exe]
    return None


def codex_olaylarini_coz(cikti: str, son_mesaj: str = "") -> CalistirmaSonucu:
    """`codex exec --json` JSONL ciktisi. GERCEK CODEX'LE DOGRULANDI (0.163.0): thread.started, turn.started,
    item.completed (agent_message), item.started/completed (file_change), turn.completed {usage: input_tokens, cached_input_tokens,
    output_tokens, reasoning_output_tokens}; hata: error + turn.failed (0.101). 'cached ⊂ input' ve 'reasoning ⊂ output' VARSAYIMDIR.
    Son mesaj icin `-o` dosyasi (varsa) olaylardan daha guvenilirdir."""
    metinler: list[str] = []
    girdi = cikti_t = onbellek = 0
    hata: str | None = None
    for satir in cikti.splitlines():
        satir = satir.strip()
        if not satir.startswith("{"):
            continue
        try:
            olay = json.loads(satir)
        except json.JSONDecodeError:
            continue
        tur = olay.get("type")
        if tur == "item.completed":
            oge = olay.get("item") or {}
            if oge.get("type") == "agent_message" and isinstance(oge.get("text"), str):
                metinler.append(oge["text"])
        elif tur == "turn.completed":
            u = olay.get("usage") or {}
            toplam_girdi, onb = int(u.get("input_tokens") or 0), int(u.get("cached_input_tokens") or 0)
            girdi += max(0, toplam_girdi - onb)  # OpenAI usulu: input_tokens onbellekten gelenleri de icerir; butceye YENI girdi sayilir (OpenCode ile tutarli)
            cikti_t += int(u.get("output_tokens") or 0)  # reasoning_output_tokens output'un parcasi sayildi (cift sayilmaz); varsayim
            onbellek += onb
        elif tur in ("turn.failed", "error"):
            ham = (olay.get("error") or {}).get("message") if tur == "turn.failed" else olay.get("message")
            if hata is None and ham:
                hata = str(ham)[:300]
    metin = son_mesaj.strip() or "\n".join(metinler).strip()
    return CalistirmaSonucu(ok=hata is None, metin=metin, token_girdi=girdi, token_cikti=cikti_t, token_onbellek=onbellek, hata=hata)


class CodexCalistirici(Calistirici):
    """`codex exec` ile OpenAI Codex CLI. Istem STDIN'den verilir (komut satiri uzunlugu/tirnak sorunu yok).
    Guvenlik: --sandbox workspace-write (yalniz calisma klasorune yazar; salt okunur istenirse read-only) ve approval_policy=never."""

    ad = "codex"

    def __init__(self, komut_oneki: list[str] | None = None):
        self.komut_oneki = komut_oneki

    def komut(self, klasor: Path, model: str | None, onayli: bool, son_mesaj_dosyasi: str) -> list[str]:
        onek = self.komut_oneki or codex_bul()
        if not onek:
            raise CalistiriciHatasi("Codex CLI bulunamadi (npm install -g @openai/codex) ya da AKTAPOKUS_CODEX ile yol verin. Baska bir CLI kullanmak icin Ayarlar > Roller'e bakin.")
        komut = [
            *onek, "exec", "--json", "--sandbox", "workspace-write" if onayli else "read-only",
            "--skip-git-repo-check", "-C", str(klasor), "-o", son_mesaj_dosyasi, "-c", 'approval_policy="never"',
        ]
        if model:
            komut += ["-m", model]
        if getattr(self, "dusunme", None) in ("low", "medium", "high"):  # Codex'te xhigh/max yok
            komut += ["-c", f'model_reasoning_effort="{self.dusunme}"']
        if self.mcp:
            from . import mcptanim

            komut += mcptanim.codex_gecersiz_kilmalari(list(self.mcp))  # kullanicinin config.toml'una dokunmadan, yalniz bu calisma
        komut.append("-")  # istem stdin'den
        return komut

    def calistir(self, istem, klasor, model=None, agent=None, zaman_asimi_sn=900, onayli=True):
        # Istem stdin'den gittigi icin komut satiri sinirlari (uzunluk, '-' ile baslama) gecerli degil; yalniz bos/asiri buyuk reddedilir
        if not istem.strip():
            raise CalistiriciHatasi("Bos istem gonderilemez")
        if len(istem) > 1_000_000:
            raise CalistiriciHatasi("Istem cok uzun (1 milyon karakter siniri)")
        import tempfile

        baslangic = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="aktapokus-codex-") as gecici:
            son = str(Path(gecici) / "son-mesaj.txt")
            komut = self.komut(Path(klasor), model, onayli, son)
            try:
                islem = _stdinli_calistir(komut, istem, Path(klasor), zaman_asimi_sn)
            except subprocess.TimeoutExpired:
                return CalistirmaSonucu(False, hata=f"Zaman asimi ({zaman_asimi_sn} sn)", sure_sn=time.monotonic() - baslangic)
            try:
                son_metin = Path(son).read_text(encoding="utf-8")
            except OSError:
                son_metin = ""
        sonuc = codex_olaylarini_coz(islem.stdout, son_metin)
        sonuc.sure_sn = time.monotonic() - baslangic
        if islem.returncode != 0 and sonuc.ok:
            sonuc.ok = False
            sonuc.hata = f"Codex cikis kodu {islem.returncode}: {(islem.stderr or islem.stdout).strip()[-300:]}"
        return sonuc


def gemini_bul() -> list[str] | None:
    """Gemini CLI'yi baslatacak komut oneki: [node, gemini.js] ya da dogrudan gemini.exe. AKTAPOKUS_GEMINI ile degistirilebilir.
    Windows'ta npm'in gemini.cmd/gemini.ps1 sarmalayicilari KULLANILMAZ (istem cmd.exe tarafindan yorumlanirdi)."""
    ortam = os.environ.get("AKTAPOKUS_GEMINI")
    if ortam and Path(ortam).is_file():
        return [ortam] if Path(ortam).suffix.lower() == ".exe" else [shutil.which("node") or "node", ortam]
    node = shutil.which("node")
    kokler = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        kokler.append(Path(appdata) / "npm" / "node_modules" / "@google" / "gemini-cli")
    npm = shutil.which("npm")
    if npm:
        kokler.append(Path(npm).resolve().parent / "node_modules" / "@google" / "gemini-cli")
    if node:
        for kok in kokler:
            for goreli in ("bundle/gemini.js", "dist/index.js"):
                if (kok / goreli).is_file():
                    return [node, str(kok / goreli)]
    exe = shutil.which("gemini")
    if exe and Path(exe).suffix.lower() == ".exe":
        return [exe]
    return None


def _sayi_bul(veri: object, anahtarlar: tuple[str, ...], derinlik: int = 0) -> int:
    """Ic ice sozlukte, verilen anahtar adlarindan ilk sayisal degeri bulur (surum/sema degisimine dayanikli); yoksa 0."""
    if derinlik > 6:
        return 0
    if isinstance(veri, dict):
        for k in anahtarlar:
            v = veri.get(k)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return int(v)
        for v in veri.values():
            n = _sayi_bul(v, anahtarlar, derinlik + 1)
            if n:
                return n
    elif isinstance(veri, list):
        for v in veri[:50]:
            n = _sayi_bul(v, anahtarlar, derinlik + 1)
            if n:
                return n
    return 0


def gemini_ciktisini_coz(cikti: str) -> CalistirmaSonucu:
    """`gemini -p ... --output-format json`: {response, stats, error?}. BELGEYE GORE yazildi (gercek CLI ile denenmedi, kurulu degildi).
    Token: stats.models.<ad>.tokens {prompt, candidates, cached}; bulunamazsa 0 (butce o rolde islemez)."""
    i, j = cikti.find("{"), cikti.rfind("}")
    try:
        d = json.loads(cikti[i:j + 1]) if i >= 0 and j > i else None
    except json.JSONDecodeError:
        d = None
    if not isinstance(d, dict):
        return CalistirmaSonucu(False, hata=f"Gemini ciktisi JSON degil: {cikti.strip()[:200]}")
    hata = d.get("error")
    girdi = cikti_t = onbellek = 0
    modeller = ((d.get("stats") or {}).get("models") or {}) if isinstance(d.get("stats"), dict) else {}
    for m in modeller.values() if isinstance(modeller, dict) else []:
        t = m.get("tokens") if isinstance(m, dict) and isinstance(m.get("tokens"), dict) else {}
        onb = _sayi_bul(t, ("cached",))
        girdi += max(0, _sayi_bul(t, ("prompt", "input")) - onb)
        cikti_t += _sayi_bul(t, ("candidates", "output"))
        onbellek += onb
    metin = d.get("response") if isinstance(d.get("response"), str) else ""
    if hata:
        mesaj = hata.get("message") if isinstance(hata, dict) else str(hata)
        return CalistirmaSonucu(False, metin=metin.strip(), hata=str(mesaj or "Gemini hatasi")[:300], token_girdi=girdi, token_cikti=cikti_t, token_onbellek=onbellek)
    return CalistirmaSonucu(True, metin=metin.strip(), token_girdi=girdi, token_cikti=cikti_t, token_onbellek=onbellek)


class GeminiCalistirici(Calistirici):
    """Google Gemini CLI (`gemini -p`). Istem STDIN'den verilir; -p yalniz kisa bir yonerge tasir (Gemini stdin'e ekler).
    Onayli calisma `--approval-mode yolo` (araclar sormadan calisir; Gemini'nin kendi sandbox'i kapali: KORUYUCUSUZ), salt okunur `--approval-mode plan`.
    BELGEYE GORE yazildi; kurulu olmadigi icin gercek CLI ile denenmedi."""

    ad = "gemini"
    YONERGE = "Yukaridaki istegi (standart girdi) yerine getir."

    def __init__(self, komut_oneki: list[str] | None = None):
        self.komut_oneki = komut_oneki

    def komut(self, model: str | None, onayli: bool) -> list[str]:
        onek = self.komut_oneki or gemini_bul()
        if not onek:
            raise CalistiriciHatasi("Gemini CLI bulunamadi (npm install -g @google/gemini-cli) ya da AKTAPOKUS_GEMINI ile yol verin.")
        komut = [*onek, "-p", self.YONERGE, "--output-format", "json", "--approval-mode", "yolo" if onayli else "plan"]
        if model:
            if model.startswith("-"):
                raise CalistiriciHatasi("Model adi '-' ile baslayamaz")
            komut += ["-m", model]
        return komut

    def calistir(self, istem, klasor, model=None, agent=None, zaman_asimi_sn=900, onayli=True):
        if not istem.strip():
            raise CalistiriciHatasi("Bos istem gonderilemez")
        if len(istem) > 1_000_000:
            raise CalistiriciHatasi("Istem cok uzun (1 milyon karakter siniri)")
        komut = self.komut(model, onayli)
        baslangic = time.monotonic()
        try:
            islem = _stdinli_calistir(komut, istem, Path(klasor), zaman_asimi_sn)
        except subprocess.TimeoutExpired:
            return CalistirmaSonucu(False, hata=f"Zaman asimi ({zaman_asimi_sn} sn)", sure_sn=time.monotonic() - baslangic)
        except OSError as hata:
            return CalistirmaSonucu(False, hata=f"Gemini baslatilamadi: {hata}", sure_sn=time.monotonic() - baslangic)
        sonuc = gemini_ciktisini_coz(islem.stdout)
        sonuc.sure_sn = time.monotonic() - baslangic
        if islem.returncode != 0 and (sonuc.ok or not islem.stdout.strip()):  # cikti yoksa asil bilgi cikis kodu ve stderr'dir
            sonuc.ok = False
            sonuc.hata = f"Gemini cikis kodu {islem.returncode}: {(islem.stderr or islem.stdout).strip()[-300:]}"
        return sonuc


def vibe_bul() -> str | None:
    """Mistral Vibe (`vibe`) programi: AKTAPOKUS_VIBE, PATH'te vibe.exe, uv'nin arac klasoru (~/.local/bin). Yalniz .exe (sarmalayici .cmd/.bat degil)."""
    ortam = os.environ.get("AKTAPOKUS_VIBE")
    if ortam and Path(ortam).is_file():
        return ortam
    yol = shutil.which("vibe")
    if yol and Path(yol).suffix.lower() == ".exe":
        return yol
    for aday in (Path.home() / ".local" / "bin" / "vibe.exe", Path.home() / ".local" / "bin" / "vibe"):
        if aday.is_file():
            return str(aday)
    return None


_VIBE_OKUNUR_AJAN: dict[str, str] = {}


def _vibe_okunur_ajan(program: list[str]) -> str:
    """Salt okunur kip icin Vibe ajan adi: eski surumlerde 'plan'; Vibe 3'te yerlesik ajanlar ask/accept-edits/smart-approve/auto-approve ('plan' yok).
    `vibe --help` bir kez okunur (yoksa/okunamazsa 'plan'); sonuc program yolu basina onbellege alinir."""
    anahtar = program[0]
    if anahtar not in _VIBE_OKUNUR_AJAN:
        ad = "plan"
        try:
            yardim = _metin(subprocess.run([*program, "--help"], capture_output=True, stdin=subprocess.DEVNULL, timeout=30).stdout)
            if "accept-edits" in yardim and "plan" not in yardim.split("--agent", 1)[-1][:400] and "ask" in yardim.split("--agent", 1)[-1][:400]:
                ad = "ask"
        except (OSError, subprocess.TimeoutExpired):
            pass
        _VIBE_OKUNUR_AJAN[anahtar] = ad
    return _VIBE_OKUNUR_AJAN[anahtar]


class VibeCalistirici(Calistirici):
    """Mistral Vibe CLI (`vibe -p`). Istem gecici bir dosyadan verilir (--prompt-file; komut satiri uzunlugu/tirnak sorunu yok), cikti duz metin.
    Onayli calisma `--agent accept-edits` (yalniz dosya duzenlemeleri otomatik onaylanir; baska arac cagrilari programli kipte onay bekler/reddedilir),
    salt okunur `--agent plan` (Vibe 3'te `ask`: bkz. _vibe_okunur_ajan). Model secimi Vibe'in kendi ayarindadir (active_model): rolde model verilirse hata. KORUYUCUSUZ.
    Token kullanimi `--output-dir` ile yazilan export.json'dan okunur (sema belgelenmemis: bulunamazsa 0).
    BELGEYE GORE yazildi; kurulu olmadigi icin gercek CLI ile denenmedi."""

    ad = "mistral"

    def __init__(self, komut_oneki: list[str] | None = None):
        self.komut_oneki = komut_oneki

    def komut(self, istem_dosyasi: str, cikti_klasoru: str, model: str | None, onayli: bool) -> list[str]:
        program = self.komut_oneki or ([vibe_bul()] if vibe_bul() else None)
        if not program:
            raise CalistiriciHatasi("Mistral Vibe bulunamadi (uv tool install mistral-vibe) ya da AKTAPOKUS_VIBE ile yol verin.")
        if model:
            raise CalistiriciHatasi("Mistral Vibe'de model Vibe'in kendi ayarindan (~/.vibe/config.toml active_model) secilir; rolde 'model'i bos birakin")
        return [*program, "--prompt-file", istem_dosyasi, "--output", "text", "--agent", "accept-edits" if onayli else (_vibe_okunur_ajan(program) if not self.komut_oneki else "plan"), "--output-dir", cikti_klasoru]

    def calistir(self, istem, klasor, model=None, agent=None, zaman_asimi_sn=900, onayli=True):
        if not istem.strip():
            raise CalistiriciHatasi("Bos istem gonderilemez")
        if len(istem) > 1_000_000:
            raise CalistiriciHatasi("Istem cok uzun (1 milyon karakter siniri)")
        import tempfile

        baslangic = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="aktapokus-vibe-") as gecici:
            istem_yolu = Path(gecici) / "istem.txt"
            from . import baglam as _baglam

            istem_yolu.write_bytes((_baglam.istem_baglami(klasor) + istem).encode("utf-8"))  # Vibe guvenilmeyen klasorde AGENTS.md'yi yok sayar: baglam istemle gider
            komut = self.komut(str(istem_yolu), str(Path(gecici) / "cikti"), model, onayli)
            try:
                islem = subprocess.run(komut, cwd=str(klasor), env=_alt_surec_ortami(Path(klasor)), capture_output=True, stdin=subprocess.DEVNULL, timeout=zaman_asimi_sn)
            except subprocess.TimeoutExpired:
                return CalistirmaSonucu(False, hata=f"Zaman asimi ({zaman_asimi_sn} sn)", sure_sn=time.monotonic() - baslangic)
            except OSError as hata:
                return CalistirmaSonucu(False, hata=f"Mistral Vibe baslatilamadi: {hata}", sure_sn=time.monotonic() - baslangic)
            girdi = cikti_t = 0
            try:
                disa = json.loads((Path(gecici) / "cikti" / "export.json").read_text(encoding="utf-8"))
                girdi = _sayi_bul(disa, ("prompt_tokens", "input_tokens", "session_prompt_tokens"))
                cikti_t = _sayi_bul(disa, ("completion_tokens", "output_tokens", "session_completion_tokens"))
            except (OSError, ValueError):
                pass
        stdout, stderr = _metin(islem.stdout), _metin(islem.stderr)
        sure = time.monotonic() - baslangic
        # cikis kodlari (belgeye gore): 0 bitti; 1 kullanim/ayar hatasi; 2 altyapi hatasi; 3 ajan bitirmeden durdu (tur/token/fiyat siniri...)
        if islem.returncode != 0:
            return CalistirmaSonucu(False, metin=stdout.strip(), token_girdi=girdi, token_cikti=cikti_t, sure_sn=sure,
                                    hata=f"Mistral Vibe cikis kodu {islem.returncode}: {(stderr or stdout).strip()[-300:]}")
        return CalistirmaSonucu(True, metin=stdout.strip(), token_girdi=girdi, token_cikti=cikti_t, sure_sn=sure)


CALISTIRICILAR = {"opencode": OpenCodeCalistirici, "claude": ClaudeCodeCalistirici, "codex": CodexCalistirici, "gemini": GeminiCalistirici, "mistral": VibeCalistirici}
_KALICI: dict[str, object] = {}  # kalici kaynak (tek OpenCode sunucusu, cagrilar arasi acik); calistiriciler ise cagri basina AYRI ornektir
_KALICI_KILIT = threading.Lock()


def calistirici_olustur(ad: str) -> Calistirici:
    if ad == "opencode-sunucu":
        from .sunucu import SunucuCalistirici  # dairesel ice aktarmayi onlemek icin tembel

        from .sunucu import Sunucu

        with _KALICI_KILIT:
            if ad not in _KALICI:
                _KALICI[ad] = Sunucu()
        # Her koşu kendi ornegini alir (ilerleme geri cagrisi ve 'aktif oturum' ORNEGE ozel): iki proje ayni anda kosarsa birbirinin
        # canli ciktisini/durdurmasini karistirmaz. Yalniz sunucu sureci ortaktir.
        return SunucuCalistirici(sunucu=_KALICI[ad], paylasilan=True)
    if ad in CALISTIRICILAR:
        return CALISTIRICILAR[ad]()
    from . import clitanim  # tanimla eklenen (ozel) CLI'lar; dairesel ice aktarmayi onlemek icin tembel

    tanim = clitanim.yukle().get(ad)
    if tanim is None:
        raise CalistiriciHatasi(f"Bilinmeyen calistirici: {ad}")
    return clitanim.TanimliCalistirici(tanim)


def hepsini_kapat() -> None:
    """Kalici calistiricilari (acik sunucu surecleri) kapatir. Program cikisinda cagrilir."""
    while _KALICI:
        with _KALICI_KILIT:
            if not _KALICI:
                break
            _ad, c = _KALICI.popitem()
        try:
            c.kapat()
        except Exception:
            pass
