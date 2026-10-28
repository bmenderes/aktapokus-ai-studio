"""Onerilenler: topluluk becerileri / araclari icin SABIT, elle derlenmis liste (Ayarlar > Onerilenler). Yalniz veri; aga cikmaz, kendiliginden kurmaz.

Her giris bir GitHub deposudur (adres `sahip/depo`; arayuz sayfayi acar). `tur`:
- `beceri`: depoda SKILL.md becerileri var; arayuz mevcut 'cevrimici kaynak' akisini acar (listele > onizle > onayla > indir: icerik guvenilmeyen veridir).
- `arac`: beceri degil (eklenti/proxy/CLI/MCP); yalniz baglanti, kurulum depodaki yonergelerle elle yapilir.
- `uygulama`: ayri bir masaustu uygulamasi.
Yildiz sayilari 2026-10-28 tarihli (bin); depo adlari GitHub'in yonlendirdigi guncel adlardir. Liste degisince `tests/test_oneriler.py` bicimi denetler."""

from __future__ import annotations

TURLER = ("beceri", "arac", "uygulama")

KATEGORILER = (
    ("Kıdemli gibi kod yaz", (
        ("Superpowers", "obra/superpowers", "beceri", 306, "Plan, test ve kontrol"),
        ("Matt Pocock Skills", "mattpocock/skills", "beceri", 305, "Planı sorgular, testlerle kurar"),
        ("ECC", "affaan-m/ECC", "beceri", 291, "Beceri, hafıza ve güvenlik bir arada"),
        ("Karpathy Skills", "multica-ai/andrej-karpathy-skills", "beceri", 225, "Tek CLAUDE.md ile daha iyi kod"),
        ("Ponytail", "DietrichGebert/ponytail", "beceri", 178, "Az kod, en basit düzeltme kazanır"),
        ("Agent Skills", "addyosmani/agent-skills", "beceri", 111, "Kıdemli mühendislik alışkanlıkları"),
    )),
    ("Araştırma ve anlama", (
        ("REA", "morluto/rea", "beceri", 398, "Bir uygulamanın gerçekte nasıl çalıştığını gösterir"),
        ("Graphify", "Graphify-Labs/graphify", "arac", 137, "Belge ve kodu bilgi haritasına çevirir"),
        ("Agent Reach", "Panniantong/Agent-Reach", "beceri", 105, "X, Reddit ve YouTube'u ücretsiz okur"),
        ("Understand Anything", "Egonex-AI/Understand-Anything", "beceri", 88, "Kod tabanını görsel anlatır"),
        ("Career Ops", "career-ops-hq/career-ops", "beceri", 77, "İş ilanlarını özgeçmişine göre puanlar"),
        ("Last 30 Days", "mvanhorn/last30days-skill", "beceri", 65, "Reddit, X, YouTube ve daha fazlasını araştırır"),
    )),
    ("Büyük projeler, az token", (
        ("gstack", "garrytan/gstack", "beceri", 137, "CEO, tasarımcı ve QA ekibi"),
        ("Caveman", "JuliusBrussee/caveman", "beceri", 115, "Kısa cevap, az token"),
        ("Claude-Mem", "thedotmack/claude-mem", "beceri", 103, "Önceki oturumları hatırlar"),
        ("Headroom", "headroomlabs-ai/headroom", "arac", 78, "Dosyaları modele gitmeden küçültür"),
        ("GSD", "gsd-build/get-shit-done", "arac", 64, "Büyük işleri planlar, kaymayı önler"),
        ("BMAD Method", "bmad-code-org/BMAD-METHOD", "beceri", 55, "Çevik yapay zekâ ekibi yöntemi"),
    )),
    ("Tasarım ve görsel", (
        ("UI UX Pro Max", "nextlevelbuilder/ui-ux-pro-max-skill", "beceri", 142, "Uygulama ve siteler için tasarımcı gözü"),
        ("Taste", "Leonxlnx/taste-skill", "beceri", 104, "Modele sanat yönü kazandırır"),
        ("Archify", "tt-a1i/archify", "beceri", 91, "Her fikri diyagrama çevirir"),
        ("Impeccable", "pbakaus/impeccable", "beceri", 91, "Modele tasarım dili verir"),
        ("PPT Master", "hugohe3/ppt-master", "beceri", 70, "Gerçek, düzenlenebilir PowerPoint sunumları"),
        ("Diagram Design", "cathrynlavery/diagram-design", "beceri", 62, "Temiz, editoryal diyagramlar"),
    )),
    ("Yazı ve video", (
        ("Skills (Anthropic)", "anthropics/skills", "beceri", 184, "Word, Excel, PowerPoint ve PDF"),
        ("OpenMontage", "calesthio/OpenMontage", "beceri", 73, "Tam bir yapay zekâ video stüdyosu"),
        ("HyperFrames", "heygen-com/hyperframes", "beceri", 74, "HTML'i videoya çevirir"),
        ("Humanizer", "blader/humanizer", "beceri", 62, "Yazıdaki yapay zekâ izlerini siler"),
        ("I Have ADHD", "ayghri/i-have-adhd", "beceri", 59, "Cevabı en başa koyar"),
        ("Marketing Skills", "coreyhaines31/marketingskills", "beceri", 57, "Yazarlık, SEO ve dönüşüm"),
    )),
    ("Ses", (
        ("Voicebox", "jamiepine/voicebox", "uygulama", 59, "Açık kaynak yapay zekâ ses stüdyosu"),
    )),
    ("MCP sunucuları", (
        ("MCP sunucuları (resmi)", "modelcontextprotocol/servers", "arac", 0, "Resmi örnek MCP sunucuları; Ayarlar › MCP'den tanımlanır"),
    )),
)


def liste() -> list[dict]:
    """Arayuz icin: [{ad, ogeler: [{ad, depo, url, tur, yildiz, aciklama}]}]."""
    return [{"ad": ad, "ogeler": [{"ad": o[0], "depo": o[1], "url": "https://github.com/" + o[1], "tur": o[2], "yildiz": o[3], "aciklama": o[4]} for o in ogeler]} for ad, ogeler in KATEGORILER]
