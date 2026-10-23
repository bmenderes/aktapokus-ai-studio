# aktapokus-ajan

OpenCode (ve Claude Code) motorlarını **rol/model bazlı** süren, **git anlık görüntüsü, fark, onay ve geri alma** ekleyen ince katman. Yalnızca standart kütüphane; Docker, Ollama, ek bağımlılık yok. Tasarım: `../aktapokus-orkestrasyon/docs/basit-mimari.md`.

## Kullanım

```bat
python -m aktapokus_ajan ac C:\yol\proje --git-baslat   :: klasörü hazırla (ayar dosyası + git)
python -m aktapokus_ajan calistir "görev metni" --klasor C:\yol\proje
python -m aktapokus_ajan geri-al --klasor C:\yol\proje
python -m aktapokus_ajan durum --klasor C:\yol\proje
```

(`pip install -e .` sonrası `aktapokus ...`.) Roller, modeller, bütçe `<proje>\.aktapokus\roller.json` içinde. Varsayılan hat: **kodcu → test**; test `SONUC: BASARILI/BASARISIZ` demezse düzeltme döngüsü (en fazla `azami_duzeltme`), token bütçesi aşılınca durur, bitişte sesli bildirim.

## Ortak bağlam: hangi model çalışırsa çalışsın aynı kurallar, kaldığı yerden devam

Tek kaynak: `<proje>\.aktapokus\baglam.md` (`aktapokus ac` varsayılanla oluşturur; siz düzenlersiniz, kısa tutun: her adımda modele gider, 2000 karakterle sınırlı). Her çalıştırmadan **önce** (anlık görüntüden önce, yani ajanın değişikliği sayılmaz) şunlar güncellenir: `AGENTS.md` içinde **yönetilen bir blok** (OpenCode ve Codex okur; `CLAUDE.md`/`GEMINI.md` yalnız o CLI'lardan biri rol olarak kullanılıyorsa) ve `.aktapokus\DURUM.md` (son 6 çalıştırmanın model/CLI'dan bağımsız özeti: kim ne yaptı, neler yarım kaldı; git'e girmez). Blok **kararlıdır** (yeni çalıştırma AGENTS.md'yi değiştirmez, git gürültüsü yok); dosyadaki sizin metninize dokunulmaz, blok yoksa sona eklenir. İstem de modele `DURUM.md`'yi okumasını söyler, böylece bağlam dosyasını okumayan bir CLI de devam eder. Elle yenilemek: `aktapokus baglam --klasor <yol>`. Kapatmak: `roller.json` içinde `"baglam": false`.

## Codex çalıştırıcısı (`"calistirici": "codex"`)

`codex exec --json --sandbox workspace-write -C <klasör> -c approval_policy="never" -` (istem **stdin'den**); salt okunur istenirse `read-only`; `danger-full-access`/`--dangerously-bypass...`/`--full-auto` hiç kullanılmaz (testle sabitlendi). Windows'ta npm'in `codex.cmd`/`codex.ps1` sarmalayıcıları kullanılmaz; `node + codex.js` ya da `codex.exe` bulunur (`AKTAPOKUS_CODEX` ile değiştirilir). Bu makinede Codex 0.101.0 → **0.163.0**'a güncellendi.

**Gerçek denemelerle (Codex 0.163.0, ChatGPT girişiyle) doğrulananlar:** (1) olay biçimi (`item.completed/agent_message`, `turn.completed/usage`) kodla eşleşti; (2) tam hat (kodcu ve test rolü Codex, ortak bağlam, onay, fark) çalıştı: ~31k token, iki adım; (3) **kum havuzu klasör dışı YAZMAYI engelledi**: PowerShell, python ve yama aracıyla `..\disari.txt` denemeleri reddedildi (hata mesajlarıyla), klasör içi yazma çalıştı. **Dikkat:** Codex'in `workspace-write` kum havuzu geçici dizine (`%TEMP%`) yazmaya tasarım gereği izin verir; ilk deneme yanlışlıkla orada yapılıp "engellemiyor" sonucu verdi, düzeltilip yeniden yapıldı.

**Codex'in OKUMA kısıtı YOK ve OpenCode koruyucumuz Codex için geçerli değil:** denemede model `.env` dosyasını okudu ve içeriğini yanıtta AYNEN yazdı (içerik OpenAI'a da gider). Bu yüzden: koruyucusuz CLI rolleri (Codex, Claude, Gemini) çalışmadan önce klasör **gizli dosyalar için taranır** (`.env*` [örnekler hariç], `*.pem`, `*.key`, `id_rsa*`, `.npmrc`...); bulunursa görev **hiç başlamaz** ve dosya adları (içeriği değil) söylenir. Çözüm: dosyaları proje dışına taşıyın, rolü OpenCode ile çalıştırın, ya da riski bilerek kabul edip rolde `"okuma_riski_kabul": true` yazın. Tarama yalnız ad desenlerine bakar (içerik taraması yok), 5000 dosya ile sınırlıdır. Olası iyileştirme (denenmedi): Codex'in beta "permission profile" özelliğiyle `**/*.env` okumasını `deny` etmek.

**Diğer sınırlar:** Codex her adımda ~15k+ girdi token'ı harcıyor (OpenCode ~4-5k); token hesabında `girdi = input - cached` ve `reasoning ⊂ output` varsayımdır. Windows'ta Codex kum havuzu kurulumu `config.toml` içinde `[windows] sandbox = "elevated"` ile yapılmıştı (Codex Desktop kurmuş); başka bir bilgisayarda kum havuzunun aynı şekilde çalıştığı **ayrıca doğrulanmalı** (ev bilgisayarı için `kur.bat` bunu denetlemez).

## Claude Code çalıştırıcısı (`"calistirici": "claude"`)

`claude -p --output-format json --settings <geçici ayar> [--model m] [--permission-mode acceptEdits]` (istem **stdin'den**, UTF-8 bayt olarak). Windows'ta npm'in `claude.cmd`/`claude.ps1` sarmalayıcıları kullanılmaz; paketin içindeki yerel `claude.exe` bulunur (`AKTAPOKUS_CLAUDE` ile değiştirilir). Bu makinede Claude Code **2.1.308**, Claude.ai **Pro** girişiyle (kota abonelikten düşer; ücretsiz claude.ai planı Claude Code'u kapsamaz).

**Gerçek denemelerle doğrulananlar:** (1) `--output-format json` tek bir sonuç nesnesi verir (`result`, `is_error`, `usage`, `total_cost_usd`, `permission_denials`); (2) `acceptEdits` ile klasör içi yazma çalışır, **klasör dışı yazma reddedilir** (`permission_denials` içinde `Write`); (3) kural verilmezse Claude `.env` dosyasını **okur ve yazar**; (4) çalıştırıcının her çağrıda yazdığı geçici ayar dosyasındaki `permissions.deny` kuralları (`Read/Edit(**/.env)`, `*.pem`, `*.key`, `id_rsa`...) `.env` okumasını **engeller**; Bash/PowerShell ile dolaylı okuma da `-p` kipinde (onay gerektiği için) reddedildi; (5) Türkçe karakterli çok satırlı istem aynen ulaştı. Token: `girdi = input + cache_creation`, `onbellek = cache_read` (Anthropic usulü; önbellek girdiye dahil değildir).

**Sınırlar:** `-p` kipinde onay gerektiren her şey (Bash dahil) reddedilir; yani Claude bu çalıştırıcıyla komut/test **çalıştıramaz**, yalnız dosya okur/yazar. Bash'e geniş izin verilirse `cat .env` deny kurallarını atlayabilir; bu yüzden izin verilmiyor. Yerel Windows'ta Claude Code kum havuzu (sandbox) desteklemiyor. `acceptEdits`, `cp`/`mv` gibi dosya komutlarını onaysız çalıştırır; bu yüzden gizli dosya ön denetimi (yukarıdaki `okuma_riski_kabul`) Claude için de **korunuyor**. Hızlı model takma adı `haiku` denendi; her çağrı ~15k+ girdi token'ı (çoğu önbellek) harcıyor.

## Her CLI'ı kodla değil TANIMLA ekleyin (arayüz: "Ajanlar" sekmesi)

Yeni bir kod ajanı CLI'ı için kod yazmak gerekmez: `~/.aktapokus/clilar.json` içine (arayüzdeki **+ CLI ekle** formu yazar) bir tanım verilir; genel `TanimliCalistirici` onu çalıştırır. Tanım: program (mutlak yol), sabit argümanlar, istem **stdin** ya da tek bir `{istem}` argümanı, model bayrağı, yazma/salt-okunur argümanları ve çıktı çözümü (`metin`, tek `json` ya da satır satır `jsonl`; yanıt/hata/token alanları için noktalı yollar, örn. `usage.input_tokens`). Örnek (Claude Code'un kendi çıktısına göre): `cikti: json`, `metin_yolu: result`, `hata_yolu: is_error`, `girdi_yolu: usage.input_tokens`, `cikti_yolu: usage.output_tokens`.

**Ayarlar > Roller:** rolleri çalışma sırasıyla listeler; her rolde CLI seçici + modeller için öneri listeli model kutusu, doğrulama rolü kutusu, talimat, ↑/↓ sıralama, rol ekle/sil. Altında tüm CLI'lar (yerleşik + özel), kurulu mu, **Dene** (boş geçici klasörde, yazma izni olmadan, önerilen ilk modelle tek küçük istek), özel olanlar için Düzenle/Sil (bir rolde kullanılan silinemez).

**Güvenlik:** tanım eklemek bu bilgisayarda program çalıştırmak demektir; bu yüzden yalnızca yerel, belirteçli arayüzden yapılır (Telegram'dan değil). Program yolu mutlak ve var olan bir dosya olmalı; `.cmd/.bat/.ps1` sarmalayıcıları reddedilir (cmd.exe istemi yorumlardı); kabuk kullanılmaz; istem argümanla verilecekse `-` ile başlayamaz; ad `opencode` ile başlayamaz ve yerleşik adlar alınamaz (ad koruyucu kapsamı anlamına gelirdi). **Özel CLI'lar koruyucusuzdur:** gizli dosya taraması (okuma_riski_kabul) onlar için de çalışır. Doğrulama: 28 birim testi + 6 mutasyon (her güvenlik denetimi kaldırılınca test düştü) + arayüzde gerçek tarayıcı denemesi. Sınırlar: `jsonl` çözümü her alan için SON dolu değeri alır (toplam almaz); canlı ilerleme yalnızca `opencode-sunucu` çalıştırıcısında var.

## Model ekle sihirbazı (Ayarlar > Roller > Modeller): sağlayıcı seç, anahtarı yapıştır, modeli role ata

OpenCode v2 235 sağlayıcıyı tanır (Google/Gemini, OpenRouter, OpenAI, Anthropic, DeepSeek, Groq, Mistral, xAI...). Sihirbaz: (1) sağlayıcıyı ara/seç (önerilenler ve bağlı olanlar başta; yalnız `env`/`oauth` ile bağlananlar anahtarla eklenemez), (2) API anahtarını yapıştır → OpenCode'un `/api/integration/{id}/connect/key` ucuna iletilir, (3) o sağlayıcının modelleri listelenir; **Anahtarı dene** (boş geçici klasörde küçük istek) ve **Role ata** (rol OpenCode'a çevrilir, model `saglayici/model` yazılır). Bağlı sağlayıcıda **Kaldır** anahtarı OpenCode'dan siler. Rol ayarındaki model kutusunun öneri listesi canlı modellerle dolar.

**Anahtar güvenliği:** anahtar yalnız yerel, belirteçli arayüzden gelir ve doğrudan yerel OpenCode'a gider; burada saklanmaz, günlüğe/olaylara yazılmaz, yanıtta ve hata iletisinde geri verilmez (hata iletisinde maskelenir), kutu gönderilince boşaltılır, Telegram'dan erişilemez. OpenCode'un `GET /api/credential` ucu anahtarı düz metin döndürür; **hiç çağrılmaz**. Kimlikler yola eklenmeden önce desen denetiminden geçer.

**Gerçek OpenCode 2.0.30 ile (izole veri klasöründe, sahte anahtarla) doğrulananlar:** bağlama `204` döner; `connections` içinde yalnız `{id, label, method}` görünür; **anahtar doğrulanmaz** (sahte anahtarla bile Google'ın 32 modeli listelendi), bu yüzden sihirbaz "Anahtarı dene" adımını sunar. Gerçek bir anahtarla uçtan uca deneme kullanıcıdadır. Gemini için ücretsiz Google AI Studio anahtarı yeterli (resmî sayfa: günde ~250 istek, yalnız Flash). **Sınırlar:** özel OpenAI-uyumlu adres ve Ollama için form yok (OpenCode listesinde ayrı ele alınır; model listesinde `ollama` sağlayıcısı görünebilir); çoklu kimlikli sağlayıcıda etiketle ayırt edilir. Bu işte bulunan gerçek hata: arayüz iki isteği aynı anda atınca OpenCode sunucusu iki kez başlıyordu (yetim süreç + taze veri klasöründe çökme); `Sunucu.baslat` kilitlendi.

## Hibrit arayüz: Claude Code'un akıcı sohbeti + Codex'in görev geçmişi ve değişiklik incelemesi

Kopya değil, ikisinin en iyi yanları: **sohbet** (Claude Code'dan): araç kartları (Oku gri, Yaz sarı, Komut kırmızı; ilk gerçek olaylarla doğrulandı), satır içi plan/onay/karar kartları, yazı kutusunun altında **rol akışı çipi** (`kodcu · model → test · model ▾`, tıklayınca Ayarlar > Roller). **Görev geçmişi ve inceleme** (Codex'ten): sol kenarda önceki görevler (`/api/gecmis`, `.aktapokus/kayit` kayıtlarından, yalnız okunur; bozuk kayıt atlanır, kimlik deseni denetlenir), tıklayınca özet + adım çıktıları; sağda **Değişiklikler** sekmesi: dosya listesi (A/M/D), dosyaya tıklayınca diff, görev karar beklerken Korunsun/Geri al. Önizleme, Belgeler, Dosyalar ve Ajanlar sekmeleri korunur.

**Varsayılan çalıştırıcı artık `opencode-sunucu`** (yeni projelerde; mevcut projelerin `roller.json`'u değişmez): kalıcı OpenCode sunucusu canlı olay verir, araç kartları kendiliğinden görünür; sunucu arayüz/Telegram kapanınca kapanır. **Sınır:** araç kartları yalnız `opencode-sunucu` çalıştırıcısında görünür (canlı olay yalnız o veriyor); `opencode`, `codex`, `claude` ve özel CLI'lar adım sonunda tek çıktı verir. Dosya başına geri alma/koruma yok, karar görev bazında. Çok görevli paralel çalışma ve satır içi yorum yok.

## Ayarlar > Kullanım: ne kadar harcadım, ne durumdayım, model limite takıldıysa ne yapayım

Kaynak: her görevin `.aktapokus/kayit/*.json` kaydı (adım başına rol, çalıştırıcı, model, girdi/çıktı/önbellek token, süre, hata); yeni veri toplanmaz, hiçbir şey gönderilmez. Sekme: **Bugün / Son 7 gün / Toplam** token (girdi + çıktı; önbellek ayrı), 14 günlük çubuk grafik, model/rol (ve "Tüm projeler"de proje) dökümü, hata sınıfları (limit/kota, anahtar/giriş, zaman aşımı, bütçe) ve son hatalar. **Öneriler:** son 48 saatte bir model limit/kota hatası verdiyse, o modeli kullanan roller için bağlı/kurulu seçeneklerden (önce ücretsizler, sonra aynı CLI) tek tıkla "rol → model" değişikliği sunulur (ayara yazar); bütçe aşımı ve anahtar hatası için de açıklayıcı öneri çıkar. Kapsam: **Bu proje** ya da **Tüm projeler** (açık proje + Telegram proje köklerinin doğrudan alt klasörleri; gizli ve noktalı klasörler taranmaz).

**Sınırlar:** abonelik kotalarının (Claude Pro, ChatGPT/Codex) KALAN miktarı CLI'lardan güvenilir okunamıyor (doğrulanmadı): yalnız harcanan token ve limite takılma anı görünür. Limit tespiti hata metnindeki desenlere dayanır (429, "usage limit", "quota", "rate limit" vb.); CLI farklı bir ifade kullanırsa "diğer" sınıfına düşer. Öneri adayları kurulu CLI'ların kayıtlı model listelerinden gelir (canlı OpenCode modelleri dahil değil). Gerçek bir limit hatası bu makinede henüz yaşanmadı; sınıflandırma sentetik kayıtlarla ve gerçek kayıtlarla (hatasız) denendi.

## Ayarlar (üst çubukta "⚙ Ayarlar"): her şey tek yerde

OpenCode Desktop'taki gibi sol menülü tam sayfa; Esc ya da "← Uygulamaya dön" ile kapanır. Eski dağınık "Ajanlar" ve "İstatistik" sekmeleri kalktı, hepsi buraya taşındı:

| Bölüm | Ne yapar |
| --- | --- |
| **Genel** | Proje klasörü, token bütçesi, en çok düzeltme turu, adım zaman aşımı, ortak bağlam açık/kapalı (`roller.json`'a yazar; görev çalışırken kilitli) |
| **Sağlayıcılar** | Bağlı sağlayıcılar + **+ Model ekle** sihirbazı (sağlayıcı seç, anahtarı yapıştır, anahtarı dene); Kaldır |
| **Modeller** | Tek katalog: OpenCode'un yerleşik ücretsiz modelleri, bağlı sağlayıcıların modelleri, Codex/Claude Code modelleri; arama, **Role ata** (rolün CLI'ını ve modelini yazar), **Dene**. Bu bilgisayarda kurulu yerel Ollama modelleri OpenCode tarafından otomatik bulunur ve listenin SONUNDA "Yerel modeller" diye görünür |
| **CLI'lar** | Yerleşik + tanımla eklenen CLI'lar, kurulu mu, Dene/Düzenle/Sil, **+ CLI ekle** |
| **Roller** | Rol sırası (↑/↓), rol ekle/sil, araç + model seçici, doğrulama rolü, talimat |
| **Kullanım** | Token harcaması, hatalar, model değiştirme önerileri (bu proje / tüm projeler) |
| **Hakkında** | Kurulu araçlar ve veri konumları |

Yazı kutusunun altındaki rol akışı çipine ve sol listedeki rollere tıklamak Ayarlar > Roller'i açar. **Sınırlar:** Telegram ayarı (proje kökleri, eşleşme) henüz Ayarlar'da yok, yalnız bilgisayardan (`telegram-baslat.bat --kok`); tema/dil seçeneği yok; ana ekranın Hermes tarzı yeniden düzeni ayrı bir iştir.

## Ana ekran (Hermes tarzı düzen)

- **Ortam çipi (yazı kutusunun altında, rol çiplerinin solunda):** `⌂ proje · …\klasör ▾`: o an hangi projenin hangi klasörde çalıştığı HER ZAMAN görünür (üzerine gelince tam yol). Tıklayınca **proje menüsü**: arama, son projeler (en son kullanılan üstte; tam yol, ✓ mevcut, × listeden unut, klasör silinmişse soluk), **Klasöre gözat…**. Git deposu olmayan klasörde "git init yapılsın mı" sorulur. Görev çalışırken proje değiştirilemez. Kayıt defteri `~/.aktapokus/projeler.json` (`projeler.py`; arayüzden ya da Telegram'dan seçilen her klasör eklenir; unutmak klasöre dokunmaz; en çok 60 proje).
- **Klasör seçici (yeniden yazıldı):** ortada pencere; **harf yazınca o klasöre ATLAR** (içine girmez; küçük/büyük harf ve Türkçe karakter duyarsız: `o` → Önemli), **↑↓** gezinme, **Enter** seçili klasörün içine girer, **Backspace** üst klasör, **Esc** kapatır, çift tıklama içine girer, tek tıklama yalnız işaretler; yol kutusuna yazıp Enter'la doğrudan gidilir; hızlı düğmeler: Ev, Masaüstü, Belgeler, İndirilenler ve sürücüler (C:, V:...); son projeler düğmeleri; "Seçilecek: <tam yol>" her zaman gösterilir. Gerçek klasörlerle (AI_Projeler) denendi.
- **Sol kenar:** **+ Yeni görev** (sohbeti temizler, yazı kutusuna odaklanır; çalışan görevi etkilemez), **Görevler** (üstte çalışan/onay bekleyen görev canlı durumuyla, altında geçmiş; tıklayınca özet ve Değişiklikler sekmesinde diff), Klon bildirimi ve en altta **⚙ Ayarlar**.
- **Yazı kutusunda rol/model çipleri:** her rol için `● kodcu · model ▾` (nokta rolün durumunu gösterir: çalışıyor/bitti/hata). Çipe tıklayınca **hızlı model menüsü**: arama kutusu, OpenCode ücretsiz modelleri, Codex, Claude Code (haiku/sonnet/opus), en sonda yerel Ollama modelleri; seçince o rolün CLI'ı ve modeli ayara yazılır (✓ mevcut seçim). Görev çalışırken değiştirilemez. "Tüm modeller ve ayarlar…" Ayarlar > Modeller'i açar.
- **Alt durum çubuğu:** solda git ve koruyucu durumu + canlı durum metni ("Hazır", "Plan onayınızı bekliyor", "Çalışıyor: kodcu · model (çalıştırıcı)", "Değişiklikler için kararınız bekleniyor"); sağda token çubuğu ve bağlantı.
- **Çıktılar (Outputs) sekmesi:** o projede görevlerle **oluşan/değişen tüm dosyaların** birleşik listesi (`ciktilar.py`; sekme adında sayı: `Çıktılar (3)`). Yalnız **kalıcı** olanlar: "Korunsun" denen ve sonradan geri alınmayan görevlerin dosyaları; geri alınan görevin dosyası, sonradan silinen ya da diskte olmayan dosya, gizli/hassas (`.env`, `*.pem`...) ve proje dışına çıkan yollar listelenmez. Her satır: tür rozeti (html/md/img/kod/dosya), ad, klasör, değişme zamanı, boyut, "yeni" (görevle oluştu) ya da "değişti" (var olan dosya değişti); üzerine gelince oluşturan görev. **Tıklayınca:** html/resim → Önizleme'de, md → Belgeler'de, diğerleri → Dosyalar'da açılır. İlk 15 gösterilir, "Daha fazla göster". Gerçek görevle denendi (dosya oluşturuldu, Korunsun, listede göründü, tıklayınca önizlemede açıldı).
- Sağ panel: Önizleme, Değişiklikler, Çıktılar, Belgeler, Dosyalar, Günlük.
- **Esnek paneller:** sol ve sağ panelin genişliği, aralarındaki **bölücü sürüklenerek** değiştirilir (sol 140-420 px, sağ en az 280 px; çift tıklama varsayılana döndürür). Üst çubuktaki **◧ / ◨** düğmeleri (ya da **Alt+1 / Alt+2**) sol/sağ paneli açıp kapatır; ikisi kapanınca sohbet tüm genişliği kaplar. Boyutlar ve açık/kapalı durum tarayıcıda (localStorage) hatırlanır; pencere gizliyken/çok küçükken kayıtlı düzen bozulmaz. Bir görev sonucu (değişiklik, çıktı, önizleme) bir sekmeyi öne çıkarınca kapalı sağ panel **kendiliğinden açılır**. Önizleme araç çubuğundaki **↗ Ayrı pencere** önizlemeyi ayrı bir pencerede açar. Dar ekranda (<900 px) tek sütun, bölücüler yok. Gerçek tarayıcıda (1400 px) sürükleme, sınırlar, düğmeler, kısayollar ve kalıcılık ölçülerek doğrulandı; bu sırada ikisi birden kapatılınca orta alanın çöktüğü bir ızgara hatası bulunup düzeltildi.

**Sınırlar:** hızlı menüdeki OpenCode modelleri ilk açılışta OpenCode sunucusunu başlattığı için birkaç saniye "yükleniyor" gösterir; sohbet geçmişi yalnız görev özeti olarak saklanır (konuşmanın tamamı değil); "Yeni görev" yalnız ekranı temizler, kayıtlı geçmişi silmez.

## Masaüstü uygulaması modu (kendi penceresi, kısayol)

`kisayol-olustur.bat` masaüstüne **Aktapokus** kısayolu koyar (kendi simgesiyle). Çift tıklayınca: siyah pencere olmadan arayüz sunucusu arka planda başlar, Edge (yoksa Chrome) adres çubuğu olmayan **kendi uygulama penceresinde** açar; **pencereyi kapatınca sunucu ve alttaki OpenCode süreci de kapanır**. Elle: `python -m aktapokus_ajan ui --uygulama [--klasor C:\proje]`.

- **Son proje hatırlanır** (`~/.aktapokus/uygulama.json`); `--klasor` verilmezse o açılır.
- **Tek kopya:** kısayola ikinci kez tıklanırsa "zaten açık" bilgisi gösterilir (aynı tarayıcı profiline bağlanıp anında kapanan ikinci sunucuyu önler). Kilit dosyası `~/.aktapokus/uygulama.kilit`; ölü süreçten kalan kilit yok sayılır. Yanlışlıkla "zaten açık" derse o dosyayı silin.
- **Pencere kapanışı sayfa bağlantısından anlaşılır** (tarayıcı sürecinden değil): arayüz sayfası sunucuyla canlı bir olay akışı bağlantısı tutar; en az bir kez bağlandıktan sonra bağlantı 20 sn boyunca yoksa pencere kapanmış sayılır ve sunucu kapanır (yenileme/kısa kopmalar tolere edilir; kapanış pencereyi kapattıktan ~20-30 sn sonra olur). 90 sn içinde hiç bağlanılmazsa hata kutusu gösterilir. **Gerçek hata (2026-10-23):** önceki sürüm tarayıcı sürecinin bitmesini bekliyordu; Edge, aynı profille çalışan bir sürece devredip hemen çıkınca sunucu 1 sn sonra kapanıyor, pencere "127.0.0.1 bağlanmayı reddetti" gösteriyordu. Test: `test_tarayici_sureci_hemen_cikarsa_bile_sunucu_baglanti_suresince_acik_kalir` ve gerçek Edge'de devir yeniden üretilip doğrulandı.
- **Tek pencere (gerçek hata, 2026-10-23):** yeni bir Edge profilinde Edge, uygulama penceresinin yanında ikinci bir pencere açıyordu (`edge://sync-confirmation-dialog`: "We are now syncing your browsing data..."), ayrıca bir "Translate page from Turkish?" kutusu çıkıyordu. Çözüm: `--disable-sync`, `--disable-features=Translate,TranslateUI,msImplicitSignin` bayrakları ve sayfada `translate="no"`; gerçek Edge'de 2-3 pencere → 1 olarak ölçüldü. Pencere simgesi `/favicon.ico` ile verilir (görev çubuğunda dünya yerine Aktapokus simgesi; Windows'tan okunan pencere simgesi 16/32 px koyu zeminli Aktapokus simgesiydi).
- **Ayrı tarayıcı profili** (`~/.aktapokus/uygulama-profil`): normal tarayıcınıza/sekmelerinize dokunmaz. Hatalar `~/.aktapokus/uygulama.log` dosyasına yazılır, Windows'ta ayrıca kutuyla gösterilir.
- Konsolsuz (`pythonw`) çalıştığı için alt süreçlerin (OpenCode, git, codex...) siyah pencere açmaması için bu modda Windows'ta `CREATE_NO_WINDOW` bayrağı eklenir.
- Başka bilgisayarda: `kur.bat`, sonra `kisayol-olustur.bat`.

**Doğrulanan (gerçek Edge, Windows 11):** pencere açıldı (başlık "Aktapokus", `--app`, ayrı profil), `CloseMainWindow` ile kapatılınca pythonw, Edge, kilit ve OpenCode süreci kalmadı, son klasör kaydedildi; gerçek masaüstü kısayoluyla ve **tarayıcı devri (bayat pencere açıkken ikinci başlatma)** durumunda da aynısı. **Doğrulanmayan:** pencerenin görsel düzeni (ekran görüntüsü alınamadı), ikinci tıklamada çıkan "zaten açık" kutusu (yalnız testle), Chrome yolu, tarayıcı güncellemesinin `--app` davranışını değiştirmesi, Windows başlangıcında otomatik açılma (yapılmadı).

## Başka bir bilgisayara kurulum (örn. ev bilgisayarı)

1. `aktapokus-ajan` klasörünü kopyalayın (`.venv`, `.git`, `__pycache__` hariç).
2. Python 3.10+ ve git kurulu olmalı; **OpenCode** kurulu ve bir modelle ayarlı olmalı (https://opencode.ai).
3. `kur.bat` dosyasına çift tıklayın: Python/git'i denetler (eksikse indirme adresini verir), klasörde `.venv` kurar, isteğe bağlı QR paketini (segno) sorar, OpenCode'u bulup bulmadığını yazar. Yönetici izni gerekmez, başka yere dosya yazmaz.
4. **Her bilgisayar için ayrı Telegram botu açın** (BotFather → `/newbot`); token'ı o bilgisayarda `%USERPROFILE%\.aktapokus\telegram.token` dosyasına yazın. Aynı token iki bilgisayarda aynı anda çalışmaz (Telegram çakışma hatası verir).
5. `telegram-baslat.bat --kok C:\yol\projeler` (kökler kaydedilir), telefondan bağlantıyı açıp eşleşin. Canlı arayüz: `arayuz-baslat.bat`.

Bilgisayara özgü olanlar (taşınmaz, her yerde ayrı kurulur): Telegram token'ı ve eşleşme (`~\.aktapokus\telegram.*`), proje kökleri, `aktapokus-klon` bilgi birikimi (`~\.aktapokus\klon`). Başlatma dosyaları klasörün kendi `.venv`'ini kullanır, sabit yol yoktur. Test: kopya bir klasörde dört senaryo denendi (temiz kurulum, tekrar çalıştırma + QR paketi, git yok, python yok).

## Canlı arayüz: `python -m aktapokus_ajan ui [--klasor C:\proje] [--tarayici]`

Terminalde yazdırılan adresi (`http://127.0.0.1:PORT/#t=TOKEN`) tarayıcıda açın; yalnızca bu bilgisayardan erişilir. Düzen: solda roller/model/klon, ortada görev akışı (plan kartı → **Onayla** → canlı ilerleme → fark kartı → **Korunsun / Geri al**), sağda **Önizleme** (proje dosyaları ya da yerel sunucu URL'si; dosya değişince kendiliğinden yenilenir), **Belgeler** (işlenmiş Markdown), **Dosyalar** (değişenler M/A işaretli, tıklayınca içerik), **Günlük**. Rol/model değiştirmek için soldaki role tıklayın.

Güvenlik: tüm API çağrıları rastgele token ister; `Host` yalnız 127.0.0.1/localhost (DNS rebinding'e karşı); dosya okuma proje klasörüyle sınırlı, nokta ile başlayan yollar, `.env`, anahtar dosyaları ve klasör dışına çıkan bağlantılar reddedilir (mutasyonla doğrulandı); Markdown HTML'e çevrilmeden önce kaçışlanır; arayüz dışarıdan hiçbir kaynak yüklemez. **Önizleme AYRI portta** sunulur (ayrı köken: uygulamanın token'ına erişemez) ve iframe sandbox'lıdır (üst sayfaya gitme/açılır pencere yok); tarayıcı `allow-scripts + allow-same-origin` uyarısı verebilir — çerçeve uygulamayla aynı kökende olmadığı için bu uyarı burada geçerli değil. Gerçek tarayıcı panelinde denendi: plan → onay → canlı ilerleme → fark → korunsun çalıştı, önizleme dosya değişince yenilendi.

Sınırlar: tek görev aynı anda; sayfa yenilenince geçmiş olaylar (bellekteki son 800) yeniden oynatılır, sunucu yeniden başlarsa geçmiş silinir (kalıcı kayıt `.aktapokus/kayit/` altında); önizleme sunucusunu (npm run dev vb.) arayüz **başlatmaz**, siz çalıştırıp URL'yi yazarsınız; klon önerileri yalnız sayılır (onay `aktapokus-klon` komutuyla); görsel/ses rolleri için özel panel yok; Windows'ta arayüz zorla kapatılsa bile OpenCode sunucusu (job nesnesiyle) yetim kalmaz.

## Telegram botu: `python -m aktapokus_ajan telegram [--klasor C:\proje]`

Telefondan görev ver, planı/farkı onayla, ilerlemeyi izle. Aynı motoru (`Uygulama`) kullanır, yani arayüzle birlikte aynı görevi yönetebilirsiniz. Bilgisayar açık olmalı (bot onda çalışır).

**Kurulum (token'ı SİZ girersiniz, bana/komut satırına yazmayın):**
1. Telegram'da `@BotFather` → `/newbot` → verdiği token'ı kopyalayın.
2. Token'ı ortam değişkenine (`AKTAPOKUS_TELEGRAM_TOKEN`) ya da `%USERPROFILE%\.aktapokus\telegram.token` dosyasına (tek satır) yazın.
3. `python -m aktapokus_ajan telegram` → token'ı doğrular (bot adını yazar) ve eşleştirme verir: **telefonda açacağınız bir `t.me` bağlantısı** (Telegram botun sohbetini kod hazır yazılmış açar, "Başlat"a basmanız yeter). İsteğe bağlı `segno` paketi kuruluysa (`pip install segno`) aynı bağlantı **QR kod** olarak tarayıcıda açılır, telefonla okutursunuz; eşleşince sayfa silinir. Elle yöntem de var: botunuza `/eslestir KOD` yazın (10 dk, tek kullanımlık). Eşleşen kullanıcı `~/.aktapokus/telegram.json` içine kaydedilir. **BotFather adımı atlanamaz:** Telegram her botun token'ını yalnızca oradan verir; QR yalnızca eşleştirmeyi kolaylaştırır.
4. Komutlar: `/projeler` (proje klasörlerini **düğme** olarak gösterir, dokunup seçersiniz; git'siz klasörde "Git başlat" düğmesi sorar), `/yeni <ad>` (ilk proje köküne yeni klasör açar, git + koruyucu kurar), `/kokler`, `/klasor <tam yol>`, `/gorev <metin>` (düz metin de görev sayılır), `/durum`, `/durdur`, `/fark <dosya>`, `/gizlilik acik|kapali`. Plan ve fark **Onayla/Reddet** ve **Korunsun/Geri al** düğmeleriyle gelir.
5. **Proje kökleri** (telefondan seçilebilecek klasörlerin kapsamı): bilgisayarda `telegram-baslat.bat --kok C:\yol\kok1 --kok C:\yol\kok2` ile eklenir (kaydedilir). Telefon bu kapsamı **genişletemez**; `/klasor` ve düğmeler yalnız köklerin altındakini kabul eder (kökün kendisi, nokta ile başlayanlar ve `gizli` listesi — varsayılan `aktapokus-ajan`, botun kendi kodu — hariç). `/yeni` yalnız git deposu olmayan ilk kökte çalışır; iç içe git deposu oluşturulmaz. Ad: harf/rakam/-/_ (en çok 41), `con`/`nul` gibi Windows aygıt adları ve yol işaretleri reddedilir.

Güvenlik: bot Telegram'ı uzun yoklama ile dinler (dışarıdan bağlantı/port açılmaz); yalnız eşleşmiş kullanıcının **özel** sohbetindeki mesajlar/düğmeler işlenir, gerisi sessizce yok sayılır (altı mutasyonla doğrulandı); başlangıçtan önce biriken komutlar atlanır; token hata/günlüklerden ayıklanır; `/klasor` git deposu olmayan klasöre `git init` yapmaz. **Gizlilik varsayılanı:** dosya içeriği ve fark metni Telegram'a (bulut, uçtan uca şifreli değil) **gönderilmez**; yalnız dosya adları, sayılar ve durum gider. `/gizlilik acik` ile siz açarsınız.

Sınırlar (dürüstçe): **gerçek Telegram ile denenmedi** (token bende olmamalı); Bot API'yi taklit eden yerel sunucuyla ve gerçek davranışa göre (son güncelleme onaylanana dek kalır) test edildi. Tek kullanıcı. Telegram'dan klasör içeriği gezme/dosya gönderme yok. Bot, onay istemeyen bir işi kendiliğinden başlatmaz ama planı onaylayan kişi bilgisayardaki ajana klasör içinde komut çalıştırma yetkisi vermiş olur (aynı koruyucu kuralları geçerli).

## OpenCode sunucu istemcisi (SDK): `aktapokus_ajan/sunucu.py`

`opencode serve` sürecini yönetir (yalnız 127.0.0.1, rastgele port, rastgele parola — parola komut satırında değil ortam değişkeninde) ve v2 HTTP API'sini sürer: `Istemci` (oturum aç/sil, mesaj gönder, aktif oturumlar, durdur, izinleri listele/yanıtla, SSE olay akışı), `Sunucu` (süreç yaşam döngüsü, ağaç sonlandırma), `SunucuCalistirici` (kalıcı sunucu; her çağrı yeni oturum; izin sorularını reddeder; zaman aşımında oturumu durdurur; `ilerleme` geri çağırımı canlı metin/araç/bitiş olayları verir — UI ve Telegram bunun üstüne kurulacak). Rolde `"calistirici": "opencode-sunucu"` yazın. Sunucu çağrılar arası açık kalır (süreç başı ~5 sn başlatma bedeli ödenmez) ve program çıkışında kapatılır.

**Önemli:** sunucu modunda koruyucu yoksa klasör dışı yazma SORUSUZ gerçekleşir (denendi); bu yüzden `calistir`, `opencode-*` rolleri için koruyucuyu zorunlu doğrular. v2 API 118 uç nokta sunuyor (yalnız kullanılanlar sarıldı); OpenAPI: `opencode-cli api --standalone GET /openapi.json`.

## Bilinen sınırlar (dürüstçe)

- **Koruyucu (yalnız OpenCode rolleri):** `ac`, `<proje>\.opencode\opencode.json` içine OpenCode'un yerel izin kurallarını yazar: klasör dışı okuma/yazma (`external_directory`) ve `.env`/anahtar dosyaları engelli, ajan kendi izin dosyasını, `.git`'i ve `.aktapokus`'u değiştiremez. Koruyucu eksik/kurcalanmışsa `calistir` hiç başlamaz. Gerçek OpenCode + model ile doğrulandı (`AKTAPOKUS_GERCEK=1 python -m pytest tests/test_guard.py`); koruyucu kapatılınca aynı test başarısız oluyor.
- **Kabuk komutları yalnızca en iyi çabayla sınırlı:** `..`, sürücü yolu (`C:\`), `~`, `$HOME`, `.env` geçen komutlar reddedilir; ama bir yorumlayıcıyla (python, node...) yolu dolaylı oluşturan komut bunu aşabilir. Tam kabuk yalıtımı konteyner/sanal makine ister. Klasör **dışındaki** etki geri alınamaz.
- **Claude Code rolleri OpenCode koruyucusu kapsamında değil** (kendi `deny` kuralları geçici ayarla verilir, yukarıya bakın); plan uyarı verir.
- Kullanıcının kendi `.opencode/opencode.json` dosyası varsa `permission` bölümü birleştirilir, özgün dosya `.aktapokus/opencode.json.yedek` olarak saklanır.
- Geri alma git'e dayanır ve `.gitignore`'daki dosyaları kapsamaz. Anlık görüntü her seferinde klasörü tarar: **büyük ikili dosyalı** projelerde (videolar) yavaş ve `.git` büyür; medyayı `.gitignore`'a koyun.
- Ajan CLI'ları `--auto` ile izinleri otomatik onaylar.
- Test rolü bir modeldir; "başarılı" demesi gerçek doğrulama değildir (gerçek komut çıkışına dayalı doğrulama sonraki iş).
- OpenCode 2.0.30 ile denendi; çalışma klasörünü `PWD` ortam değişkeninden okuyor (bu yüzden alt sürece `PWD` açıkça verilir).

## Test

```bat
python -m pytest
```
