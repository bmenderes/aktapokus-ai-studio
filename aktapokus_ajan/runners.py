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
import threading
import time
from dataclasses import dataclass
from pathlib import Path

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


def _istemi_denetle(istem: str) -> None:
    if not istem.strip():
        raise CalistiriciHatasi("Bos istem gonderilemez")
    if len(istem) > AZAMI_ISTEM_UZUNLUGU:
        raise CalistiriciHatasi(f"Istem cok uzun ({len(istem)} karakter, sinir {AZAMI_ISTEM_UZUNLUGU})")
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
    for desen in ("**/.env", "**/.env.*", "**/*.pem", "**/*.key", "**/id_rsa", "**/id_ed25519", "**/.npmrc", "**/.netrc")
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


class ClaudeCodeCalistirici(Calistirici):
    """`claude -p` ile Claude Code (2.1.308 ile GERCEK denendi). Istem STDIN'den gider (komut satiri sorunu yok).
    Dogrulananlar: --output-format json tek bir sonuc nesnesi verir (result, is_error, usage, total_cost_usd, permission_denials);
    acceptEdits modunda klasor DISINA yazma reddedilir; `permissions.deny` Read(**/.env) .env okumasini engeller;
    -p kipinde onay gerektiren her sey (Bash/PowerShell dahil) reddedilir."""

    ad = "claude"

    def __init__(self, cli_yolu: str | None = None):
        self.cli_yolu = cli_yolu

    def komut(self, ayar_dosyasi: str, model: str | None, onayli: bool, mcp_dosyasi: str | None = None, mcp_adlari: tuple[str, ...] = ()) -> list[str]:
        cli = self.cli_yolu or claude_bul()
        if not cli:
            raise CalistiriciHatasi(
                "Claude Code CLI bulunamadi (npm install -g @anthropic-ai/claude-code) ya da AKTAPOKUS_CLAUDE ile yol verin. "
                "Baska bir CLI kullanmak icin Ayarlar > Roller'e bakin."
            )
        komut = [cli, "-p", "--output-format", "json", "--settings", ayar_dosyasi]
        if model:
            komut += ["--model", model]
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

    def calistir(self, istem, klasor, model=None, agent=None, zaman_asimi_sn=900, onayli=True):
        if not istem.strip():
            raise CalistiriciHatasi("Bos istem gonderilemez")
        if len(istem) > 1_000_000:
            raise CalistiriciHatasi("Istem cok uzun (1 milyon karakter siniri)")
        import tempfile

        baslangic = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="aktapokus-claude-") as gecici:
            ayar = Path(gecici) / "ayar.json"
            ayar.write_text(json.dumps({"permissions": {"deny": CLAUDE_YASAK_KURALLARI}}), encoding="utf-8")
            mcp_dosyasi = None
            if self.mcp:
                from . import mcptanim

                mcp_dosyasi = str(Path(gecici) / "mcp.json")
                Path(mcp_dosyasi).write_text(json.dumps(mcptanim.claude_ayari(list(self.mcp))), encoding="utf-8")
            komut = self.komut(str(ayar), model, onayli, mcp_dosyasi, tuple(t.ad for t in self.mcp))
            try:
                islem = _stdinli_calistir(komut, istem, Path(klasor), zaman_asimi_sn)
            except subprocess.TimeoutExpired:
                return CalistirmaSonucu(False, hata=f"Zaman asimi ({zaman_asimi_sn} sn)", sure_sn=time.monotonic() - baslangic)
        sonuc = self.cikti_coz(islem.stdout)
        sonuc.sure_sn = time.monotonic() - baslangic
        if islem.returncode != 0 and sonuc.ok:
            sonuc.ok = False
            sonuc.hata = f"Claude Code cikis kodu {islem.returncode}: {(islem.stderr or islem.stdout).strip()[-300:]}"
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


CALISTIRICILAR = {"opencode": OpenCodeCalistirici, "claude": ClaudeCodeCalistirici, "codex": CodexCalistirici}
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
