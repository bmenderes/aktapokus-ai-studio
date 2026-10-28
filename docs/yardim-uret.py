"""Otomasyon yardim sayfalarini (TR/EN) uretir: web/yardim/otomasyon.html ve otomasyon-en.html. Resimler satir ici SVG.
Kullanim (depo kokunden): python docs/yardim-uret.py   -> metin/resim degisince bunu calistirip uretilen iki dosyayi commit edin."""
import html
import sys
from pathlib import Path

HEDEF = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "aktapokus_ai_studio" / "web" / "yardim"

E = html.escape


def node(x, y, w, sim, ad, vurgu=False, soluk=False):
    dolgu = "var(--saribg)" if vurgu else "var(--panel)"
    kenar = "var(--sarikoyu)" if vurgu else "var(--line2)"
    return (f'<g opacity="{0.45 if soluk else 1}"><rect x="{x}" y="{y}" width="{w}" height="36" rx="9" fill="{dolgu}" stroke="{kenar}"/>'
            f'<text x="{x + 14}" y="{y + 23}" class="sm">{sim}</text><text x="{x + 36}" y="{y + 23}" class="t">{E(ad)}</text></g>')


def ok(x1, y1, x2, y2):
    return f'<path d="M{x1} {y1} L{x2} {y2}" stroke="var(--tx3)" stroke-width="1.6" fill="none" marker-end="url(#o)"/>'


def yuvarlak(cx, cy, sim, vurgu=False):
    return (f'<circle cx="{cx}" cy="{cy}" r="15" fill="{"var(--saribg)" if vurgu else "var(--panel)"}" stroke="{"var(--sarikoyu)" if vurgu else "var(--line2)"}"/>'
            f'<text x="{cx}" y="{cy + 5}" text-anchor="middle" class="sm">{sim}</text>')


def numara(cx, cy, n):
    return f'<circle cx="{cx}" cy="{cy}" r="10" fill="var(--sari)"/><text x="{cx}" y="{cy + 4}" text-anchor="middle" class="n">{n}</text>'


def metin(x, y, s, sinif="t3", orta=False):
    return f'<text x="{x}" y="{y}" class="{sinif}"{" text-anchor=\"middle\"" if orta else ""}>{E(s)}</text>'


def svg(w, h, icerik, baslik):
    return (f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{E(baslik)}" xmlns="http://www.w3.org/2000/svg">'
            '<defs><marker id="o" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="var(--tx3)"/></marker></defs>'
            f'{icerik}</svg>')


def dugme(x, y, w, ad, ana=False):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="26" rx="13" fill="{"var(--sari)" if ana else "var(--panel)"}" stroke="{"var(--sarikoyu)" if ana else "var(--line2)"}"/>'
            f'<text x="{x + w / 2}" y="{y + 17}" text-anchor="middle" class="t2">{E(ad)}</text>')


def sekil_akis(L):
    g = node(10, 40, 150, "⏱", L["tetik"]) + ok(160, 58, 200, 58) + node(200, 40, 150, "⚙", L["gorev"], True) + ok(350, 58, 390, 58) + node(390, 40, 150, "↗", L["bildirim"])
    g += metin(85, 100, L["f1a"], "t3", True) + metin(275, 100, L["f1b"], "t3", True) + metin(465, 100, L["f1c"], "t3", True)
    return svg(550, 116, g, L["f1"])


def sekil_form(L):
    g = '<rect x="6" y="6" width="538" height="150" rx="12" fill="var(--panel2)" stroke="var(--line)"/>'
    g += '<rect x="20" y="20" width="510" height="78" rx="10" fill="var(--panel)" stroke="var(--line)"/>'
    g += f'<text x="34" y="46" class="b">{E(L["ornek_ad"])}</text><rect x="120" y="32" width="96" height="20" rx="10" fill="var(--accbg)"/><text x="168" y="46" text-anchor="middle" class="t3">⏱ 09:00</text>'
    g += dugme(250, 28, 110, L["simdi"], True) + dugme(366, 28, 74, L["duzenle"]) + dugme(446, 28, 64, L["sil"])
    g += metin(34, 78, L["ornek_gorev"], "t3")
    g += dugme(20, 112, 150, L["sablon_ekle"], True) + numara(188, 125, 1)
    return svg(550, 164, g, L["f2"])


def sekil_tuval(L):
    g = '<rect x="6" y="6" width="538" height="206" rx="12" fill="var(--panel2)" stroke="var(--line)"/>'
    g += node(24, 40, 150, "⏱", L["tetik"]) + ok(174, 58, 214, 58) + node(214, 40, 150, "⚙", L["gorev"], True) + numara(214, 40, 2)
    g += ok(364, 58, 404, 58) + node(404, 40, 130, "↗", L["bildirim"], False, True)
    g += metin(24, 120, L["f3a"], "t3")
    # arac cubugu
    g += '<rect x="24" y="150" width="270" height="44" rx="22" fill="var(--panel)" stroke="var(--line)"/>'
    for i, (sim, n) in enumerate((("↓", 3), ("⇪", 4), ("+", 5), ("✓", 6))):
        cx = 58 + i * 62
        g += yuvarlak(cx, 172, sim, sim == "✓") + numara(cx + 13, 156, n)
    g += metin(310, 160, "③ " + L["b_web"], "t3") + metin(310, 176, "④ " + L["b_yayin"], "t3") + metin(310, 192, "⑤ " + L["b_bildirim"] + "   ⑥ " + L["b_kaydet"], "t3")
    return svg(550, 222, g, L["f3"])


def sekil_dugumler(L):
    g = ""
    satirlar = (("⏱", L["tetik"], L["d_tetik"], False), ("↓", L["web"], L["d_web"], False), ("⚙", L["gorev"], L["d_gorev"], True), ("⇪", L["yayinla"], L["d_yayin"], False), ("↗", L["bildirim"], L["d_bildirim"], False))
    for i, (sim, ad, aciklama, v) in enumerate(satirlar):
        y = 8 + i * 46
        g += node(8, y, 150, sim, ad, v) + metin(172, y + 23, aciklama, "t2")
    return svg(550, 240, g, L["f4"])


def sekil_haber(L):
    g = ""
    adlar = (("⏱", L["zamanlayici"]), ("↓", L["web"]), ("⚙", L["gorev"]), ("⇪", L["yayinla"]), ("↗", L["bildirim"]))
    for i, (sim, ad) in enumerate(adlar):
        x = 6 + i * 108
        g += f'<rect x="{x}" y="30" width="92" height="64" rx="10" fill="{"var(--saribg)" if i == 2 else "var(--panel)"}" stroke="{"var(--sarikoyu)" if i == 2 else "var(--line2)"}"/>'
        g += f'<text x="{x + 46}" y="58" text-anchor="middle" class="big">{sim}</text><text x="{x + 46}" y="80" text-anchor="middle" class="t3">{E(ad)}</text>'
        if i < 4:
            g += ok(x + 92, 62, x + 108, 62)
    sat = (L["h1"], L["h2"], L["h3"], L["h4"], L["h5"])
    for i, s in enumerate(sat):
        g += numara(18 + (i * 108) + 0, 114, i + 1) + metin(34 + i * 108, 118, s, "t3")
    return svg(550, 130, g, L["f5"])


def sekil_onay(L):
    g = '<rect x="6" y="6" width="538" height="150" rx="12" fill="var(--panel)" stroke="var(--line)"/>'
    g += f'<rect x="20" y="20" width="130" height="22" rx="11" fill="var(--warnbg)"/><text x="85" y="35" text-anchor="middle" class="t3">{E(L["plan_bekliyor"])}</text>'
    g += metin(20, 66, L["plan_1"], "t2") + metin(20, 86, L["plan_2"], "t2") + metin(20, 106, L["plan_3"], "t2")
    g += dugme(20, 120, 110, L["onayla"], True) + dugme(138, 120, 110, L["reddet"])
    g += numara(128, 122, 1)
    return svg(550, 164, g, L["f6"])


def sekil_kapi(L):
    g = ""
    adlar = (L["k1"], L["k2"], L["k3"], L["k4"])
    for i, ad in enumerate(adlar):
        x = 6 + i * 136
        son = i == 3
        g += f'<rect x="{x}" y="24" width="118" height="54" rx="10" fill="{"var(--okbg)" if son else "var(--panel)"}" stroke="{"var(--ok)" if son else "var(--line2)"}"/>'
        satir = ad.split("|")
        for j, sa in enumerate(satir):
            g += f'<text x="{x + 59}" y="{(51 if len(satir) == 2 else 55) + (j * 15 - 7 if len(satir) == 2 else 0)}" text-anchor="middle" class="t2">{E(sa)}</text>'
        if i < 3:
            g += ok(x + 118, 51, x + 136, 51)
    g += f'<path d="M127 78 L127 108 L{6 + 2 * 136 + 59} 108" stroke="var(--err)" stroke-width="1.6" fill="none" stroke-dasharray="4 3"/>'
    g += f'<rect x="150" y="96" width="250" height="26" rx="13" fill="var(--errbg)"/><text x="275" y="113" text-anchor="middle" class="t2">{E(L["k_dur"])}</text>'
    return svg(550, 134, g, L["f7"])


def sekil_izin(L):
    g = '<rect x="6" y="6" width="538" height="112" rx="12" fill="var(--panel)" stroke="var(--line)"/>'
    g += f'<text x="22" y="34" class="b">{E(L["ornek_ad"])}</text>'
    g += '<rect x="22" y="48" width="42" height="24" rx="12" fill="var(--sari)"/><circle cx="52" cy="60" r="9" fill="#fff"/>'
    g += metin(76, 65, L["izin_ac"], "t2") + metin(22, 98, L["izin_not"], "t3") + numara(22, 48, 1)
    return svg(550, 126, g, L["f8"])


def sekil_telegram(L):
    g = ""
    for i, (a, b) in enumerate(((L["tg1"], L["tg1b"]), (L["tg2"], L["tg2b"]), (L["tg3"], L["tg3b"]))):
        x = 6 + i * 182
        g += f'<rect x="{x}" y="14" width="168" height="84" rx="10" fill="var(--panel)" stroke="var(--line2)"/>' + numara(x + 18, 32, i + 1)
        g += metin(x + 34, 36, a, "b2") + metin(x + 14, 62, b, "t3")
        if i < 2:
            g += ok(x + 168, 56, x + 182, 56)
    return svg(550, 112, g, L["f9"])


def sekil_hesap(L):
    g = '<rect x="6" y="10" width="170" height="64" rx="10" fill="var(--panel)" stroke="var(--line2)"/>' + metin(91, 34, L["hesap_a"], "b2", True) + metin(91, 54, "@bmenderes", "t2", True)
    g += '<rect x="6" y="96" width="170" height="44" rx="10" fill="var(--panel)" stroke="var(--line2)"/>' + metin(91, 115, L["hesap_b"], "t3", True) + metin(91, 131, "@ikinci-hesap", "t2", True)
    for y, ad, v in ((10, "bmenderes/bmenderes.github.io", True), (56, "baska-sahip/depo", False), (102, "ikinci-hesap/site", True)):
        g += f'<rect x="270" y="{y}" width="274" height="34" rx="10" fill="{"var(--saribg)" if v else "var(--panel)"}" stroke="{"var(--sarikoyu)" if v else "var(--line2)"}"/>' + metin(407, y + 22, ad, "t2", True)
    g += ok(176, 30, 270, 27) + f'<path d="M176 50 L270 73" stroke="var(--tx3)" stroke-width="1.6" fill="none" stroke-dasharray="4 3" marker-end="url(#o)"/>' + ok(176, 118, 270, 119)
    g += metin(182, 92, L["hesap_yok"], "t3")
    return svg(550, 150, g, L["f10"])


TR = dict(
    dil="tr", baslik="Otomasyon rehberi", kapat="Kapat", icindekiler="İçindekiler",
    tetik="Tetikleyici", gorev="Görev", bildirim="Bildirim", web="Web getir", yayinla="Yayınla", zamanlayici="Zamanlayıcı",
    f1="Otomasyonun üç parçası", f1a="ne zaman başlar", f1b="ajan işi yapar", f1c="Telegram mesajı",
    f2="Otomasyonlar sayfası", ornek_ad="haber", ornek_gorev="Bugünün haberlerini topla ve sayfayı güncelle", simdi="Şimdi çalıştır", duzenle="Düzenle", sil="Sil", sablon_ekle="+ Şablon ekle",
    f3="Tuval ve araç çubuğu", f3a="Düğmelerle düğüm ekler, düğüme tıklayıp ayarını yazarsınız.", b_web="Web getir ekle", b_yayin="Yayınla ekle", b_bildirim="Bildirim ekle", b_kaydet="Kaydet",
    f4="Düğümler", d_tetik="İşi başlatır: elle ya da zamanlı", d_web="Sayfaları görevden önce okur", d_gorev="Ajanın yapacağı iş (düz metin, model seçilebilir)", d_yayin="Klasörü GitHub deposuna gönderir", d_bildirim="Bitince Telegram'a yazar",
    f5="Haber sayfası örneği", h1="her sabah", h2="siteleri oku", h3="sayfayı yaz", h4="siteye gönder", h5="telefona haber",
    f6="Plan onayı", plan_bekliyor="Plan onay bekliyor", plan_1="1. Haber sitelerini oku", plan_2="2. haberler/index.html dosyasını güncelle", plan_3="3. Testleri çalıştır", onayla="Onayla", reddet="Reddet",
    f7="Yayın güvenlik kapısı", k1="Klasörü|kopyala", k2="Gizli veri|taraması", k3="Yapay zekâ|incelemesi", k4="GitHub'a|gönder", k_dur="Bulgu varsa durur, hiçbir şey gönderilmez",
    f8="İzinler", izin_ac="Onay beklemeden çalışsın", izin_not="Kapalıyken her çalışma plan onayı bekler.",
    f9="Telegram bağlama", tg1="BotFather", tg1b="/newbot yazın, token alın", tg2="Aktapokus", tg2b="Ayarlar > Telegram > Başlat", tg3="Eşleştir", tg3b="Kodu botunuza yazın",
    f10="İki GitHub hesabı", hesap_a="Varsayılan hesap", hesap_a2="", hesap_b="Eklenen hesap", hesap_yok="eşleşme yok → varsayılan",
    s_nedir="Otomasyon nedir?",
    p_nedir="Bir tetikleyici bir görevi başlatır; görev bitince istersen siteye yayın ve Telegram bildirimi gider. Hepsi tek akışta, tuval üzerinde kurulur.",
    s_ilk="İlk otomasyonunu kur", ilk_1="Ayarlar > Otomasyonlar sayfasında <b>+ Şablon ekle</b>'ye bas.", ilk_2="<b>Görev</b> düğümüne tıkla ve işi düz metinle yaz. İstersen model seç; boş bırakırsan projenin rol ayarı kullanılır.",
    ilk_3="Gerekirse <b>↓</b> ile web sayfası okut, <b>⇪</b> ile yayın ekle, <b>+</b> ile bildirim ekle.", ilk_4="Tetikleyiciyi seç: elle ya da zamanlayıcı (her N dakika, her gün saat X, haftanın günleri).", ilk_5="<b>✓</b> ile kaydet. Sonra <b>Şimdi çalıştır</b>'la dene.",
    s_dugum="Düğümler", dugum_not="Oklar yalnızca şu yönde çizilir: tetikleyici → (web getir) → görev → (yayınla | bildirim). Bir akışta tek tetikleyici ve tek görev olur.",
    gorev_degisken="Görev ve bildirim metinlerinde değişken kullanabilirsin:", degiskenler="{tarih} {saat} {proje} {dal} · bildirimde ek olarak {durum} {yanit} {yayin}",
    s_haber="Örnek: haber sayfası", haber_p="Zamanlayıcı her sabah çalışır. Web getir sayfaları okur, görev haberlerden sayfayı yazar, Yayınla klasörü siteye gönderir, bildirim sonucu telefona yazar.",
    haber_ayar="Yayınla düğümünde şunları doldur: <b>kaynak klasör</b> (projedeki sayfa klasörü), <b>hedef depo</b> (örn. bmenderes/bmenderes.github.io), <b>depodaki klasör</b> (örn. haberler). Otomasyonda klasör adı zorunludur.",
    s_onay="Onay ve izinler", onay_p="Varsayılan olarak her çalışma önce bir <b>plan</b> çıkarır ve senin onayını bekler. Onaylayana kadar hiçbir şey çalışmaz.",
    onay_p2="Güvendiğin bir otomasyon için <b>Ayarlar > İzinler</b>'den onaysız çalışmasına izin verebilirsin. Onaysız çalışan otomasyonda da yayın güvenlik kapısından geçer.",
    s_yayin="Yayın nasıl güvenli yapılır", yayin_p="Yayını ajan değil Aktapokus yapar. Ajan GitHub'a erişemez. Her yayın şu kapıdan geçer:",
    yayin_p2="Yüksek ya da orta riskli bulgu (anahtar, kişisel veri gibi) varsa ya da yapay zekâ incelemesi yapılamazsa otomatik yayın <b>durur</b> ve içerik gönderilmez. Elle yayınlarken bulguları görüp karar verirsin.",
    yayin_kok="Elle yayınlarken <b>Depodaki klasör</b>'ü boş bırakırsan dosyalar deponun <b>köküne</b> eklenir (kişisel index sayfası gibi). Hiçbir dosya silinmez; aynı adlı dosyalar (örn. index.html) değişir ve önceden onay istenir. Klasör adı verirsen o klasörün önceki içeriği yenisiyle değişir.",
    s_telegram="Telegram'ı bağla", telegram_p="Bir kerelik kurulum. Bot yalnızca seninle konuşur.",
    tg_a="Telegram'da <b>@BotFather</b>'a <code>/newbot</code> yaz; sana bir token verir (gizli tut).", tg_b="Aktapokus'ta Ayarlar > <b>Telegram</b> > token'ı yapıştır > <b>Başlat</b>.", tg_c="<b>Yeni eşleştirme kodu</b> de, çıkan mesajı (örn. <code>/eslestir ab12cd34</code>) botuna yaz.",
    s_hesap="İki GitHub hesabı", hesap_p="Aktapokus birden çok GitHub hesabıyla çalışabilir. Ayarlar > Hesaplar > GitHub kartında <b>Hesap ekle</b>'ye bas, kodu gir.",
    hesap_p2="Hesabı sen seçmezsin: deponun sahibi eklediğin hesabın adıyla aynıysa o hesap kullanılır. Aksi halde (örn. başka bir kuruluşun deposu) varsayılan hesap kullanılır.",
    s_sinir="Sınırlar", sinirlar=("Uygulama açıkken çalışır. Kapalıyken kaçan zamanlar kaçırıldı olarak yazılır.", "Aynı projede aynı anda tek görev çalışır; çakışan tetikleme atlanır.", "En çok 20 otomasyon, en kısa aralık 5 dakika.",
                                  "Bildirim yalnızca Telegram'a gider; bot çalışmıyorsa gönderilmez ve geçmişe yazılır.", "Her çalışma Ayarlar > Otomasyonlar > Çalışma geçmişi'nde görünür."),
)

EN = dict(
    dil="en", baslik="Automation guide", kapat="Close", icindekiler="Contents",
    tetik="Trigger", gorev="Task", bildirim="Notification", web="Fetch web", yayinla="Publish", zamanlayici="Timer",
    f1="The three parts of an automation", f1a="when it starts", f1b="the agent does the work", f1c="Telegram message",
    f2="The Automations page", ornek_ad="news", ornek_gorev="Collect today's news and update the page", simdi="Run now", duzenle="Edit", sil="Delete", sablon_ekle="+ Add template",
    f3="Canvas and toolbar", f3a="Buttons add nodes; click a node to write its settings.", b_web="Add Fetch web", b_yayin="Add Publish", b_bildirim="Add Notification", b_kaydet="Save",
    f4="Nodes", d_tetik="Starts the work: manual or timed", d_web="Reads pages before the task", d_gorev="The agent's job (plain text, model selectable)", d_yayin="Sends a folder to a GitHub repository", d_bildirim="Writes to Telegram when done",
    f5="News page example", h1="every morning", h2="read the sites", h3="write the page", h4="send to site", h5="news on phone",
    f6="Plan approval", plan_bekliyor="Plan waiting for approval", plan_1="1. Read the news sites", plan_2="2. Update haberler/index.html", plan_3="3. Run the tests", onayla="Approve", reddet="Reject",
    f7="Publish safety gate", k1="Copy|folder", k2="Secret|scan", k3="AI|review", k4="Send to|GitHub", k_dur="If anything is found, it stops and nothing is sent",
    f8="Permissions", izin_ac="Run without waiting for approval", izin_not="When off, every run waits for plan approval.",
    f9="Connecting Telegram", tg1="BotFather", tg1b="Send /newbot, get a token", tg2="Aktapokus", tg2b="Settings > Telegram > Start", tg3="Pair", tg3b="Send the code to your bot",
    f10="Two GitHub accounts", hesap_a="Default account", hesap_a2="", hesap_b="Added account", hesap_yok="no match → default",
    s_nedir="What is an automation?",
    p_nedir="A trigger starts a task; when it finishes you can publish to a site and get a Telegram notification. It is all one flow, built on the canvas.",
    s_ilk="Build your first automation", ilk_1="On Settings > Automations press <b>+ Add template</b>.", ilk_2="Click the <b>Task</b> node and write the job in plain text. Pick a model if you like; if empty, the project's role setting is used.",
    ilk_3="If needed, add <b>↓</b> to read web pages, <b>⇪</b> to publish, <b>+</b> for a notification.", ilk_4="Choose the trigger: manual or timer (every N minutes, daily at X, days of the week).", ilk_5="Save with <b>✓</b>, then try <b>Run now</b>.",
    s_dugum="Nodes", dugum_not="Arrows only go one way: trigger → (fetch web) → task → (publish | notification). A flow has one trigger and one task.",
    gorev_degisken="You can use variables in task and notification texts:", degiskenler="{tarih} {saat} {proje} {dal} · in notifications also {durum} {yanit} {yayin}",
    s_haber="Example: a news page", haber_p="The timer runs every morning. Fetch web reads the pages, the task writes the page from the news, Publish sends the folder to the site, the notification writes the result to your phone.",
    haber_ayar="In the Publish node fill in: <b>source folder</b> (the page folder in the project), <b>target repository</b> (e.g. bmenderes/bmenderes.github.io), <b>folder in the repository</b> (e.g. haberler). In an automation the folder name is required.",
    s_onay="Approval and permissions", onay_p="By default every run first makes a <b>plan</b> and waits for your approval. Nothing runs until you approve.",
    onay_p2="For an automation you trust, allow it to run without approval in <b>Settings > Permissions</b>. An unattended publish still goes through the safety gate.",
    s_yayin="How publishing stays safe", yayin_p="Aktapokus publishes, not the agent. The agent cannot reach GitHub. Every publish goes through this gate:",
    yayin_p2="If there is a high or medium risk finding (keys, personal data) or the AI review cannot run, an automatic publish <b>stops</b> and nothing is sent. When publishing by hand you see the findings and decide.",
    yayin_kok="When publishing by hand, if you leave <b>Folder in the repository</b> empty, the files are added to the repository <b>root</b> (like a personal index page). Nothing is deleted; files with the same name (e.g. index.html) are replaced, and you are asked first. If you give a folder name, that folder's previous content is replaced.",
    s_telegram="Connect Telegram", telegram_p="One-time setup. The bot only talks to you.",
    tg_a="In Telegram send <code>/newbot</code> to <b>@BotFather</b>; it gives you a token (keep it secret).", tg_b="In Aktapokus: Settings > <b>Telegram</b> > paste the token > <b>Start</b>.", tg_c="Say <b>New pairing code</b>, then send the message shown (e.g. <code>/eslestir ab12cd34</code>) to your bot.",
    s_hesap="Two GitHub accounts", hesap_p="Aktapokus can work with more than one GitHub account. On Settings > Accounts > GitHub press <b>Add account</b> and enter the code.",
    hesap_p2="You do not pick the account: if the repository owner has the same name as an added account, that account is used. Otherwise (e.g. another organization's repository) the default account is used.",
    s_sinir="Limits", sinirlar=("It runs while the app is open. Times missed while closed are recorded as missed.", "One task runs per project at a time; a colliding trigger is skipped.", "At most 20 automations, shortest interval 5 minutes.",
                                "Notifications go to Telegram only; if the bot is not running nothing is sent and the history says so.", "Every run shows in Settings > Automations > Run history."),
)

CSS = """
@font-face{font-family:"Inter";font-style:normal;font-weight:100 900;font-display:swap;src:url(/vendor/inter-latin-ext-wght-normal.woff2) format("woff2");unicode-range:U+0100-02BA,U+02BD-02C5,U+02C7-02CC,U+02CE-02D7,U+02DD-02FF,U+0304,U+0308,U+0329,U+1D00-1DBF,U+1E00-1E9F,U+1EF2-1EFF,U+2020,U+20A0-20AB,U+20AD-20C0,U+2113,U+2C60-2C7F,U+A720-A7FF}
@font-face{font-family:"Inter";font-style:normal;font-weight:100 900;font-display:swap;src:url(/vendor/inter-latin-wght-normal.woff2) format("woff2");unicode-range:U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD}
:root{--bg:#f7f5f1;--panel:#fff;--panel2:#f1efe8;--line:#d3d1c7;--line2:#b4b2a9;--tx:#2c2c2a;--tx2:#5f5e5a;--tx3:#888780;--sari:#f5c400;--sarikoyu:#d9aa00;--saribg:#fff5c9;--accbg:#fff5c9;--ok:#3b6d11;--okbg:#eaf3de;--warnbg:#faeeda;--err:#a32d2d;--errbg:#fcebeb}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--tx);font:14px/1.6 Inter,Arial,sans-serif}
main{max-width:620px;margin:0 auto;padding:18px 16px 60px}
h1{font-size:20px;margin:0 0 10px}h2{font-size:16px;margin:30px 0 8px;scroll-margin-top:12px}
p,li{color:var(--tx2)}ol,ul{padding-left:20px}li{margin:4px 0}
nav{display:flex;flex-wrap:wrap;gap:6px;margin:4px 0 6px}
nav a{background:var(--panel);border:1px solid var(--line);border-radius:999px;padding:3px 11px;font-size:12px;color:var(--tx);text-decoration:none}
nav a:hover{background:var(--saribg);border-color:var(--sarikoyu)}
figure{margin:12px 0;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:10px}
figure svg{display:block;width:100%;height:auto}
figcaption{font-size:12px;color:var(--tx3);margin-top:4px;text-align:center}
code{background:var(--panel2);border-radius:5px;padding:1px 5px;font-size:12.5px}
b{color:var(--tx)}
svg text{font-family:Inter,Arial,sans-serif;fill:var(--tx)}
.t{font-size:13px;font-weight:600}.t2{font-size:12.5px}.t3{font-size:11.5px;fill:var(--tx2)}.b{font-size:14px;font-weight:700}.b2{font-size:12.5px;font-weight:700}.sm{font-size:15px}.big{font-size:22px}.n{font-size:11px;font-weight:700;fill:#2c2c2a}
"""


def sayfa(L):
    bolumler = [("nedir", L["s_nedir"]), ("ilk", L["s_ilk"]), ("dugum", L["s_dugum"]), ("haber", L["s_haber"]), ("onay", L["s_onay"]), ("yayin", L["s_yayin"]), ("telegram", L["s_telegram"]), ("hesap", L["s_hesap"]), ("sinir", L["s_sinir"])]
    fig = lambda svg_, ad: f"<figure>{svg_}<figcaption>{E(ad)}</figcaption></figure>"
    g = []
    g.append(f'<h1>{E(L["baslik"])}</h1><nav aria-label="{E(L["icindekiler"])}">' + "".join(f'<a href="#{i}">{E(a)}</a>' for i, a in bolumler) + "</nav>")
    g.append(f'<h2 id="nedir">{E(L["s_nedir"])}</h2><p>{L["p_nedir"]}</p>' + fig(sekil_akis(L), L["f1"]))
    g.append(f'<h2 id="ilk">{E(L["s_ilk"])}</h2>' + fig(sekil_form(L), L["f2"]) + "<ol>" + "".join(f"<li>{L[k]}</li>" for k in ("ilk_1", "ilk_2", "ilk_3", "ilk_4", "ilk_5")) + "</ol>" + fig(sekil_tuval(L), L["f3"]))
    g.append(f'<h2 id="dugum">{E(L["s_dugum"])}</h2>' + fig(sekil_dugumler(L), L["f4"]) + f'<p>{L["dugum_not"]}</p><p>{L["gorev_degisken"]} <code>{E(L["degiskenler"])}</code></p>')
    g.append(f'<h2 id="haber">{E(L["s_haber"])}</h2><p>{L["haber_p"]}</p>' + fig(sekil_haber(L), L["f5"]) + f'<p>{L["haber_ayar"]}</p>')
    g.append(f'<h2 id="onay">{E(L["s_onay"])}</h2><p>{L["onay_p"]}</p>' + fig(sekil_onay(L), L["f6"]) + f'<p>{L["onay_p2"]}</p>' + fig(sekil_izin(L), L["f8"]))
    g.append(f'<h2 id="yayin">{E(L["s_yayin"])}</h2><p>{L["yayin_p"]}</p>' + fig(sekil_kapi(L), L["f7"]) + f'<p>{L["yayin_p2"]}</p><p>{L["yayin_kok"]}</p>')
    g.append(f'<h2 id="telegram">{E(L["s_telegram"])}</h2><p>{L["telegram_p"]}</p>' + fig(sekil_telegram(L), L["f9"]) + "<ol>" + "".join(f"<li>{L[k]}</li>" for k in ("tg_a", "tg_b", "tg_c")) + "</ol>")
    g.append(f'<h2 id="hesap">{E(L["s_hesap"])}</h2><p>{L["hesap_p"]}</p>' + fig(sekil_hesap(L), L["f10"]) + f'<p>{L["hesap_p2"]}</p>')
    g.append(f'<h2 id="sinir">{E(L["s_sinir"])}</h2><ul>' + "".join(f"<li>{E(s)}</li>" for s in L["sinirlar"]) + "</ul>")
    return (f'<!doctype html><html lang="{L["dil"]}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{E(L["baslik"])}</title><style>{CSS}</style></head>'
            f'<body><main>{"".join(g)}</main></body></html>')


HEDEF.mkdir(parents=True, exist_ok=True)
(HEDEF / "otomasyon.html").write_text(sayfa(TR), encoding="utf-8", newline="\n")
(HEDEF / "otomasyon-en.html").write_text(sayfa(EN), encoding="utf-8", newline="\n")
print("tamam")
