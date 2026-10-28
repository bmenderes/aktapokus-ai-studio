# Yol haritası (canlı belge)

Durumlar: **VAR** (yapıldı ve denendi) · **YAPILACAK** (sıraya alındı) · **SONRA** (değerli, sırası gelmedi) · **KARAR** (kullanıcı kararı bekliyor) · **ÖNERİLMİYOR** (gerekçesiyle).
Bu belge, kullanıcının listelediği fikirlerin **hiçbirini düşürmemek** için tutulur; bir madde ÖNERİLMİYOR ise nedeni yazılıdır ve itiraz edilebilir.

## Önerilen sıra

1. **Eski süreçleri temizle ve Telegram `/projeler`'i doğrula** — eski bot (22 Ekim) ve eski arayüz sunucuları (23 Ekim) kapatıldı; kullanıcının telefondan `/projeler`'i denemesi bekleniyor.
2. Ad: **Aktapokus AI Studio** (repo `aktapokus-ai-studio`) — **VAR** (repo adlandırıldı).
3. **Güvenli uzak erişim** (Tailscale, açık-kapalı seçenek, token + Origin kontrolü korunur, terminal uzak erişimde varsayılan kapalı) ve **telefonda kullanılabilir düzen** — **VAR** (gerçek Tailscale ile denenmedi; sahte CLI ve loopback ile test edildi).
4. **Cihazlarım / eşleştirme:** her bilgisayar kendi örneğini çalıştırır; adres, ad, durum listelenir; aracı bulut yok.
5. **Telegram:** `/model` ve `/roller`, dolar maliyeti özeti, bütçe uyarısı.
6. **Denetim günlüğü** ve **"ne oldu?" özet kartı** (modelsiz: git farkı + görev kayıtlarından).
7. Sonra: ses girişi, komut paleti, şablonlar, çevrimdışı kuyruk, yerel model eki.

## Fikir → durum

| Fikir | Durum | Not |
| --- | --- | --- |
| Uzak erişim ("uzak masaüstü gibi") | VAR (3) | Uzak masaüstü değil, güvenli web erişimi. Arayüz şu an yalnız `127.0.0.1`. Terminal+MCP = uzaktan komut çalıştırma; internete doğrudan açılmaz |
| Terminal WebSocket proxy, FastAPI, tmux | ÖNERİLMİYOR | Standart kütüphane + SSE + Windows ConPTY zaten var; yeniden yazım ve Windows'ta olmayan tmux gereksiz |
| Mobilde xterm.js terminal | VAR / YAPILACAK | Terminal sekmesi var; dar ekran düzeni (3) |
| Mobil arayüz: tek panelli telefon düzeni | VAR (3) | Görevler · Sohbet · Panel alt gezinmesi. PWA (ana ekrana ekleme, push) ve komut paleti SONRA |
| GitHub entegrasyonu (basit + derin: PR, issue) | VAR | Git sekmesi + GitHub sekmesi + Ayarlar |
| Google ile giriş (Aktapokus hesabı) | YAPILACAK (sıraya alındı 2026-10-26) | Aktapokus'un kendi kullanıcı hesabı yok; Hesaplar bölümü bunu açıkça gösteriyor. Google OAuth için bir OAuth istemcisi gerekir (kullanıcı oluşturur); önce kapsam ve veri sahipliği (yerel mi bulut mu) kararı |
| GitHub: uygulamaya özel giriş | YAPILACAK (sıraya alındı, karar: tek hesap) | `gh`'ın ayrı ayar klasörüyle (GH_CONFIG_DIR) bilgisayardaki gh girişinden bağımsız oturum; tarayıcıda tek seferlik kodla giriş (gerçek gh ile doğrulandı: ayrı klasör giriş yok görünüyor); git push/pull kimlik yardımcısı da bu hesapla; uzaktan giriş/çıkış kapalı |
| Aktapokus ↔ Claude Code karşılıklı haberdarlık | KISMEN HAZIR | Claude'a: `UserPromptSubmit` kancası (`haber_kancasi.py`, `~/.claude/settings.json`) her mesajdan önce yalnız YENİ olan Aktapokus olaylarını bağlama ekler (canlı durum `~/.aktapokus/canli.json`, biten görevler proje kayıtlarından). Aktapokus'a: kenar çubuğunda her projenin altında 'Claude Code (n)' bölümü; konuşma salt okunur oynatılır, canlıysa 3 sn'de bir yenilenir, 'Terminalde sürdür' ile devam edilir. Uzaktan kapalı. Kalan: kancanın yeni bir Claude Code oturumunda doğrulanması. |
| Önizleme tarayıcı menüsü (⋮) | HAZIR (2026-10-26) | Varsayılan tarayıcıda aç, URL kopyala, ekran görüntüsü kaydet (başsız Edge/Chrome; yalnız yerel adresler), HTML dosyası aç, görünüm (duyarlı/mobil/tablet), ajan yazdığı HTML/SVG/görseli otomatik aç (varsayılan açık), görev sonrası ekran görüntüsüyle doğrula (varsayılan kapalı), önizleme verilerini temizle (`Clear-Site-Data`). Uzaktan kapalı. Not: Edge başlatıcısı hemen döner, PNG ~1 sn sonra belirir (dosya beklenir). Yapılmadı: ek açıklama araçları, 'bağlantıları yerleşik tarayıcıda aç' anahtarı (önizleme zaten çerçevede açılır). |
| Core ile birleşme (hibrit: Studio kontrol katmanı, Core 'Araçlar') | KARAR | Karşılaştırma yapıldı; kullanıcı kararı bekleniyor (docs/ içinde ayrıca yazılmadı) |
| Uygulamayı farklı bilgisayarlara kurup eşleştirme | YAPILACAK (4) | "Cihazlarım" |
| Kimi Claw benzeri taşınabilirlik | KARAR | Kimi Claw doğrulanmadı. "Tek tık bulut deploy" önerilmiyor (kod ve anahtarlar buluta gider); taşınabilirlik = eşleştirme + uzak erişim |
| Repo adı | VAR | `aktapokus-ai-studio` (eski adres yönlendirilir) |
| Oturum kalıcılığı ve kurtarma | KISMEN VAR | Görev ve terminal bağlantı kopsa da sürer, yeniden bağlanınca geri oynatılır. Eksik: "kaldığın yerden devam / sıfırdan başla" seçeneği. LangGraph/TimescaleDB ÖNERİLMİYOR (görev kayıtları dosyada) |
| Maliyet takibi, günlük/haftalık/aylık, görev başına, bütçe uyarısı | YAPILACAK (5) | Token takibi ve Kullanım sayfası var; Claude çıktısında dolar bilgisi var; uyarı Telegram'dan |
| Bildirim sistemi | KISMEN VAR | Telegram + pencere bildirimi var. PWA push (HTTPS gerekir; Tailscale `serve` ile) SONRA; e-posta/SMS SONRA |
| Denetim günlüğü (eylem bazlı) + "son 24 saat" özeti | YAPILACAK (6) | Görev kayıtları ve fark var; eylem düzeyinde günlük eksik. Eylem başına geri al SONRA (görev başına geri al VAR) |
| Çevrimdışı mod / yerel model / kuyruk | KARAR | 21 Ekim'de "yerel model kullanılmayacak" demiştin; "yerel LLM'de CLI" fikrine ilgi gösterdin. Kuyruk fikri uyuyor. Küçük bir "yerel model" ön ayarı önerildi |
| Ses girişi (Web Speech API) | SONRA | Tarayıcıya bağlı; ses bulutta işlenebilir (gizlilik notu gerekir) |
| Özel MCP araçları (PLC, SCADA, servo...) | SONRA | MCP altyapısı VAR; alan araçları `aktapokus-klon` (PLC bilgisi) ile birlikte ele alınmalı |
| Çok cihazdan aynı oturum, çakışan komutları kuyruğa alma | KISMEN VAR | Olay akışı çok istemciye yayınlanır; çakışan komut kuyruğu yapılacak (3-4 ile) |
| Dağıtım hattı (CI/CD, mobil onay) | SONRA | PR'ın CI sonucunu görme VAR; deploy onayı sonra |
| Şablon kütüphanesi | SONRA | |
| Performans metrikleri | SONRA | Kullanım sayfası temel |
| Sandbox / Docker izolasyonu | ÖNERİLMİYOR (şimdilik) | Windows'ta ağır; klasör sınırı, gizli dosya koruması, MCP/proje bazlı açma VAR. Kuru çalıştırma (dry-run) SONRA |
| Bulut barındırma (Oracle/Railway/Fly/Render) | ÖNERİLMİYOR | Ajan CLI'ları, kod ve anahtarlar yerelde kalmalı; ücretsiz katmanlar ağır işe uygun değil |
| Kesintisiz akış, yeniden bağlanınca son durum | VAR | SSE + halka tampon + olay geri oynatma |
| "Ne oldu?" özet kartı (Llama ile) | YAPILACAK (6) | Model çağırmadan: git farkı + görev kayıtları (commit önerisi gibi). İstenirse sonra modelle |
| Uygulama kapalıyken bildirim (Telegram) | VAR | |
| Kimlik doğrulama: Tailscale + token | VAR (3) | Sabit, yenilenebilir uzak anahtar; yetki daraltma; Tailscale yoksa açılmaz |
| Telegram'da model seçimi | YAPILACAK (5) | Yalnız kurulu CLI/modeller arasından düğmeyle |
| Telegram `/projeler` çalışmadı | NEDEN BULUNDU | Eski bot ayarı açılışta bir kez okuyor; süreç kapatılıp yeniden başlatılacak (1) |
| Otomasyon: şablon + "Şimdi çalıştır" + Telegram `/sablon` | VAR (A) | Yalnız plan üretir, onay ister. Tasarım: `otomasyon-tasarimi.md` |
| Otomasyon: zamanlayıcı (aralık/günlük/haftalık, kaçırılan kaydı, günlük tavan) | VAR (B) | Yalnız uygulama açıkken; günlük tavan = plan sayısı (12), token tavanı değil |
| Otomasyon: zincir, olay tetikleyici, bildirim/geçmiş cilası | YAPILACAK (C–E) | Kullanıcı dördünü de istedi; onay her zaman şart |
| Otomasyon: Web getir düğümü | VAR (2026-10-28) | Siteleri Aktapokus okur (ajan web aracı onayı beklemez); SSRF korumalı. `otomasyon-akis-tasarimi.md` |
| Otomasyon: Ayarlar › İzinler (onaysız çalıştırma) | VAR (2026-10-28) | Otomasyon bazında, varsayılan KAPALI, yalnız yerel arayüz; önceki "onay her zaman şart" kuralı kullanıcı kararıyla değişti |
| Sohbet başlığı (proje · görev adı) | VAR (2026-10-28) | Sohbet alanının üstünde; telefonda kenar çubuğu kapalıyken de görünür |
| Ayarlar › Önerilenler (32 depo, bağlantılı) | VAR (2026-10-28) | `oneriler.py`: beceri depoları için mevcut çevrimiçi kaynak akışı (önizle > onayla > indir); diğerleri bağlantı. Voicebox listede |
| Voicebox entegrasyonu (sesle yaz / seslendirme) | YAPILACAK | Şimdilik yalnız Önerilenler'de bağlantı olarak |
| Her sohbetin kendi hafızası (model değişince otomatik okunur) | VAR (2026-10-28) | Sohbet = "Yeni" sınırları arası görevler. `.aktapokus/hafiza/<sohbet>.md` her sohbete ayrı; güncel sohbet ayrıca `KONUSMA-OZETI.md`'de. Model/araç değişince hafıza parçası isteme eklenir (değişmediyse eklenmez). ↺ düğmesi açık sohbetin hafızasını verir |
| Ayarlar › İzinler: değişiklikleri her projede otomatik koru | VAR (2026-10-28) | `izinler.py`; varsayılan kapalı, yalnız yerel arayüz. Keep/Undo sorusu işi bekletmesin diye |
| Windows açılışında otomatik başlatma | YAPILACAK | Onaylı ve geri alınabilir |
| Temiz bilgisayarda kurulum denemesi | KULLANICI | Hafta başı kullanıcı yapacak |
| OpenCode olmadan çalışma | VAR | Motor denetimi; temiz bilgisayarda gerçek deneme bekliyor |
| Düğüm tabanlı otomasyon (agentic orkestrasyon / n8n benzeri) | YAPILACAK (2026-10-26) | Mevcut zamanlanmış otomasyonlar üstüne görsel düğüm editörü: tetikleyici (zaman, elle, dosya değişimi), eylem (görev/plan çalıştır, Git, bekleme), onay düğümü (her zaman onay), çıktı düğümü (HTML rapor sayfası, e-posta). Çalışma geçmişi düğüm düğüm izlenir. Önce veri modeli ve çalıştırıcı, sonra editör. |
| E-posta (SMTP) ayarları sayfası | YAPILACAK (2026-10-26) | Ayarlar'da sunucu/port/güvenlik/kullanıcı/gönderen; parola düz metin saklanmaz (Windows DPAPI ile şifrelenir), arayüze geri gösterilmez; 'test e-postası gönder'; uzaktan kapalı. Çıktı düğümü bunu kullanır. |
| Veritabanı | KARAR (2026-10-26) | Şimdilik gerekmiyor (JSON dosyaları yetiyor). Düğüm tabanlı iş akışı gelince çalışma geçmişi ve arama için SQLite (Python'a gömülü, sunucu/kurulum gerektirmez, tek dosya) eklenir; ayrı bir veritabanı sunucusu eklenmez. |
| Tek `kur.bat` ile kurulum | YAPILACAK (2026-10-26) | Python/sanal ortam/bağımlılık denetimi, kısayol ve (varsa) Edge penceresi tek betikle; temiz PC testi sonrası kesinleşir. |
| Codex ve OpenCode eşleşmesi (Claude Code'daki gibi) | HAZIR (2026-10-26) | Konuşmalar Aktapokus kenar çubuğunda ('Codex (n)', 'OpenCode (n)'), salt okunur oynatma, canlı izleme, terminalde sürdür. Aktapokus durumu araca: Codex için `~/.codex/hooks.json` kancası (Codex'te bir kez `/hooks` ile güvenilmeli), OpenCode için `~/.config/opencode/opencode.json` `instructions` + `~/.aktapokus/haber.md` (OpenCode her istemde yeniden okur; denendi). Kurulum: `aktapokus haber --kur claude|codex|opencode|hepsi` (yedek alır). OpenCode 2.x eklenti biçimi değişti (varsayılan dışa aktarım + id), bu yüzden eklenti yerine talimat dosyası seçildi. Okuma biçimleri araçların sürümüne bağlı: okunamayan kayıt atlanır. |
| Mistral AI CLI (Mistral Vibe) ve Google Gemini CLI desteği | KISMEN HAZIR (2026-10-26) | İkisi de yerleşik çalıştırıcı (`gemini`, `mistral`): CLI'lar sayfasında kurulu/giriş rozeti, rollerde seçilebilir, plan onayı ve geri alma ortak. Gemini: `-p` + stdin, `--output-format json`, onaylı `--approval-mode yolo` / salt okunur `plan`. Vibe: `--prompt-file`, `--output text`, `--agent accept-edits` / `plan`, token `--output-dir` export.json'dan. İkisi de KORUYUCUSUZ (klasör dışı/gizli dosya engeli yok; mevcut uyarı ve .env engeli devrede). **Belgeye göre yazıldı, ikisi de bu makinede kurulu olmadığı için gerçek CLI ile DENENMEDİ** (sahte CLI testleri var). Kalan: gerçek CLI ile doğrulama, Gemini/Vibe konuşma eşleşmesi (kanca/talimat dosyası), Vibe model seçimi. |
| Görev geri bildirimi sadeleştirme (Claude uygulamasındaki gibi) | HAZIR (2026-10-27: araçlar tek kapalı satır, yanıt düz metin, dosya listesi tek satır, canlı durum tek satır, yuvarlak kopyala düğmesi; tarayıcıda görsel doğrulama bekliyor) | Kullanıcı ekran görüntüsüyle istedi: düz metin akışı, araç/komut adımları tek satır "Ran a command" olarak kapalı (tıklayınca ayrıntı), sade eylem simgeleri, arka plan işi için tek satır durum. Mevcut geri bildirim çok karmaşık bulunuyor. Önce mevcut olay/mesaj türlerinin envanteri, sonra gruplama kuralları. |
| Çıktılar: yeni çerçeve (frame) oluşturma | HAZIR (2026-10-27, 119d61a: seçilen çıktı listenin altında ayrı çerçevede açılır; tarayıcıda görsel doğrulama bekliyor) | Çıktılar bölümünde yeni çerçeve oluşturma işi tamamlanmadıysa sıraya alındı; mevcut Çıktılar alt çerçevesi çalışması başka oturumda, önce onun durumu kontrol edilecek. |
| Dosyalar sekmesi: dosyalar tıklanamıyor | DÜZELTİLDİ (2026-10-27; tarayıcıda doğrulanmadı) | Kullanıcı ekran görüntüsüyle bildirdi: Files sekmesindeki ağaçta (çok kökte: BIM_Kremali, observing-existence, SmartMerge...) dosya adlarına tıklayınca bir şey olmuyor. Önce hata ayıklama: tıklama olayı hangi öğelere bağlı, hangi kökte/dosya türünde oluşuyor, konsol hatası var mı; sonra düzeltme + test. |
| Kapanma/yeniden açılışta görev kurtarma | YAPILACAK (2026-10-27) | Görevler uygulama içindeki iş parçacığında çalışır; uygulama kapanırsa çalışan görev ölür, kayıt (`.aktapokus/kayit`) yalnız görev bitince yazılır, onay bekleyen plan ve kuyruk yalnız bellekte. Yapılacak: çalışan/bekleyen görev durumunu diske yaz, açılışta "yarım kaldı: devam / geri al / yok say" sor, kuyruğu ve planı geri yükle. |
