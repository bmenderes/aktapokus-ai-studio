# Değişiklik günlüğü

Biçim [Keep a Changelog](https://keepachangelog.com/tr-TR/1.1.0/) esinlidir; sürümler [SemVer](https://semver.org/lang/tr/) izler.
1.0'a kadar küçük sürümler (0.x) uyumsuz değişiklik içerebilir.

## [0.2.0] - 2026-11-23

İlk etiketli sürüm. 23 Ekim 2026'daki ilk commit'ten bu yana yapılan işi özetler (0.1.0 hiç etiketlenmedi).
Ayrıntı için `git log`; bilinen sınırlar için README'deki **Bilinen sınırlar** bölümü.

### Öne çıkanlar

- **Kalıcı çoklu sohbet:** proje başına birden çok sohbet, sohbet başına oturum ve hafıza (`KONUSMA-OZETI.md`, `.aktapokus/hafiza/`),
  alt sohbet, ortak bağlam, sohbet başına Kararlar; model/araç değişince ve uygulama yeniden açılınca hafıza bir kez okutulur;
  bağlam taşınca yeni oturumla yeniden deneme.
- **Google bağlantısı (salt okunur):** PKCE ile giriş; Gmail, Drive ve Takvim okuma; otomasyon düğümü. Yenileme anahtarı DPAPI ile saklanır.
- **OPC UA ve ağ aracı:** test sunucusu ve istemci (ağaç, okuma, abonelik; yazma yok), sürekli veri toplama ve SQLite deposu,
  saklama süresi; Ayarlar içinde ağ aracı (tarama, IP profilleri, BOOTP/DHCP, kablodaki cihazı bulma, EtherNet/IP ve Beckhoff ADS keşfi).
- **Yeni çalıştırıcılar:** Antigravity CLI (`agy`, abonelik modelleri listesi), DeepSeek Harness (masaüstü uygulamasının içindeki CLI),
  Gemini CLI ve Mistral Vibe; kurulu olmayan CLI plan onayından önce bildirilir, CLI kartında durum ışığı ve kurulum komutu.
- **Canlı akış:** metin, düşünce, araç ve komut çıktıları tek, zaman sıralı akışta; Claude, OpenCode ve Mistral için canlı sinyaller
  ve hareketsizliğe dayalı zaman aşımı (ilerleyen görev öldürülmez).
- **Sırlar diskte DPAPI ile:** uzak erişim anahtarı ve Telegram token'ı yalnız bu Windows kullanıcısının açabileceği biçimde saklanır;
  eski düz metin değerler okunur ve ilk yazımda korumalı biçime geçirilir.
- **İlk açılış rehberi:** yapay zekâ aracı, proje klasörü ve ilk görev; üç tek satır, sıradaki adım düğmeli, tamamlanınca gizlenir.

### Eklenenler

- Çoklu proje: eş zamanlı projeler, proje başına önizleme sunucusu, kenar çubuğu proje grupları, Telegram'da sohbet başına aktif proje.
- Geri alma: git deposu gerekmez (gölge yedek); büyük ve hassas dosyalar `.gitignore`'a kendiliğinden eklenir; 260 karakterden uzun Windows yolları.
- Git sekmesi (değişiklikler, otomatik commit mesajı, geçmiş, dallar, stash) ve GitHub: klonlama, PR, issue → görev,
  Aktapokus'a özel oturum, birden çok hesap, gönderme kontrolü (sır/kişisel veri taraması + yapay zekâ incelemesi), Yayınla.
- Otomasyonlar: şablonlar, zamanlayıcı, akış tuvali, Web getir / Yayınla / bildirim düğümleri, otomasyon bazında onaysız çalıştırma izni,
  yapay zekâsız veri akışı motoru.
- MCP sunucuları ve Beceriler (ortak MCP, proje bazlı açma, çevrimiçi beceri kaynağı), Önerilenler listesi.
- Uzak erişim (Tailscale, varsayılan kapalı), telefon düzeni, PWA; telefondan plan onayı/reddi, koru/geri al ve durdur.
- Telegram botu arayüzle aynı süreçte; eşleşmeler arayüzden kaldırılabilir.
- Masaüstü kontrolü (MCP; proje bazında kapalı başlar, engel listesi ve kayıt), Node-RED (yalnız 127.0.0.1), uygulama içi terminal (ConPTY).
- Görev sırasında izin sorusu, görev ekleri (resim, CAD dosyaları), kapanışta görev kurtarma, kuyruk, görev süresi, CPU/GPU göstergesi.
- Penceresiz arka plan modu ve Windows açılışında başlatma; uykudan uyanınca sunucu kapanmaz.
- Arayüz dili Türkçe + İngilizce; Lora yazı tipi ve yeni ahtapot simgesi.
- Kurulum: `setup.bat` (Python/git denetimi, `.venv`, isteğe bağlı QR/OPC UA/test araçları), `kisayol-olustur.bat`.

### Değişenler

- Python paketi `aktapokus_ajan` → `aktapokus_ai_studio`; depo `aktapokus-ajan` → `aktapokus-ai-studio` (`aktapokus` komutu aynı).
- Kodcu kendi işini doğrular; ayrı test adımı yeni projelerde kapalı gelir.
- Plan onayı tek okunur cümle: kim, hangi modelle, ne yapacak, en çok ne harcar.
- `kur.bat` sadeleşti ve `setup.bat`'a yönlendirir.

### Güvenlik

- Güvenlik denetimi G-00..G-07 düzeltmeleri ve regresyon testleri (`docs/guvenlik-denetimi.md`).
- Uzak erişim: gönderme ve yıkıcı Git işlemleri yönetim izni ister, bilinen uç listesi dışındaki uçlar reddedilir,
  Aktapokus sırları ajan ortamından çıkarılır; kök seçilmemişse yalnız açık proje gezilir.

### Geliştirme

- GitHub Actions iş akışı (`.github/workflows/test.yml`): Windows, Python 3.12 ve 3.14, test dosyaları dört parçaya bölünür,
  `pytest-timeout` ile test başına 300 sn sınırı.

[0.2.0]: https://github.com/bmenderes/aktapokus-ai-studio/releases/tag/v0.2.0
