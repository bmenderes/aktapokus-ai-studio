# Yol haritası (canlı belge)

Durumlar: **VAR** (yapıldı ve denendi) · **YAPILACAK** (sıraya alındı) · **SONRA** (değerli, sırası gelmedi) · **KARAR** (kullanıcı kararı bekliyor) · **ÖNERİLMİYOR** (gerekçesiyle).
Bu belge, kullanıcının listelediği fikirlerin **hiçbirini düşürmemek** için tutulur; bir madde ÖNERİLMİYOR ise nedeni yazılıdır ve itiraz edilebilir.

## Önerilen sıra

1. **Eski süreçleri temizle ve Telegram `/projeler`'i doğrula** — eski bot (22 Ekim) ve eski arayüz sunucuları (23 Ekim) kapatılacak. *Kullanıcı onayı bekliyor.*
2. Ad: **Aktapokus AI Studio** (repo `aktapokus-ai-studio`) — **VAR** (repo adlandırıldı).
3. **Güvenli uzak erişim** (Tailscale, açık-kapalı seçenek, token + Origin kontrolü korunur, terminal uzak erişimde varsayılan kapalı) ve **telefonda kullanılabilir düzen (PWA)**.
4. **Cihazlarım / eşleştirme:** her bilgisayar kendi örneğini çalıştırır; adres, ad, durum listelenir; aracı bulut yok.
5. **Telegram:** `/model` ve `/roller`, dolar maliyeti özeti, bütçe uyarısı.
6. **Denetim günlüğü** ve **"ne oldu?" özet kartı** (modelsiz: git farkı + görev kayıtlarından).
7. Sonra: ses girişi, komut paleti, şablonlar, çevrimdışı kuyruk, yerel model eki.

## Fikir → durum

| Fikir | Durum | Not |
| --- | --- | --- |
| Uzak erişim ("uzak masaüstü gibi") | YAPILACAK (3) | Uzak masaüstü değil, güvenli web erişimi. Arayüz şu an yalnız `127.0.0.1`. Terminal+MCP = uzaktan komut çalıştırma; internete doğrudan açılmaz |
| Terminal WebSocket proxy, FastAPI, tmux | ÖNERİLMİYOR | Standart kütüphane + SSE + Windows ConPTY zaten var; yeniden yazım ve Windows'ta olmayan tmux gereksiz |
| Mobilde xterm.js terminal | VAR / YAPILACAK | Terminal sekmesi var; dar ekran düzeni (3) |
| Mobil PWA: terminal modu / komut paleti (`/yeni-proje`, `/model-degistir`, `/geri-al`) | SONRA | Palet küçük bir ek |
| GitHub entegrasyonu (basit + derin: PR, issue) | VAR | Git sekmesi + GitHub sekmesi + Ayarlar |
| Google ile giriş | YAPILACAK (sonra) | Önce Tailscale + token; Google OAuth için kullanıcının bir OAuth istemcisi oluşturması gerekir |
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
| Kimlik doğrulama: Tailscale + token | YAPILACAK (3) | Token VAR; Tailscale uzak erişim modu eklenecek |
| Telegram'da model seçimi | YAPILACAK (5) | Yalnız kurulu CLI/modeller arasından düğmeyle |
| Telegram `/projeler` çalışmadı | NEDEN BULUNDU | Eski bot ayarı açılışta bir kez okuyor; süreç kapatılıp yeniden başlatılacak (1) |
| Windows açılışında otomatik başlatma | YAPILACAK | Onaylı ve geri alınabilir |
| Temiz bilgisayarda kurulum denemesi | KULLANICI | Hafta başı kullanıcı yapacak |
| OpenCode olmadan çalışma | VAR | Motor denetimi; temiz bilgisayarda gerçek deneme bekliyor |
