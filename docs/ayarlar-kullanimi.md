# Aktapokus AI Studio: Ayarlar sayfası nasıl kullanılır

Ayarlar, uygulamanın tek merkezi yönetim sayfasıdır. Sağlayıcılar, modeller, CLI'lar, roller, Telegram, uzak erişim ve kullanım istatistiği burada toplanır.

## Açmak ve kapatmak

- **Açmak:** sol kenar çubuğunun en altındaki **⚙ Ayarlar** düğmesi. Yazı kutusunun altındaki rol çipine (`kodcu · model ▾`) tıklamak da **Ayarlar > Roller**'i açar; hızlı model menüsündeki "Tüm modeller ve ayarlar…" ise **Ayarlar > Modeller**'i açar.
- **Kapatmak:** **Esc** tuşu ya da sol menünün üstündeki **← Uygulamaya dön**.
- **Düzen:** solda bölüm menüsü, sağda seçili bölümün içeriği. Dar ekranda (<900 px) menü üste yatay olarak dizilir.
- Uygulama, en son baktığınız bölümü hatırlar.

## Bölümler

| Bölüm | Ne işe yarar |
| --- | --- |
| Genel | Projenin çalışma ayarları |
| Sağlayıcılar | Model sağlayıcılarına API anahtarıyla bağlanma |
| Modeller | Tüm modellerin kataloğu; role atama ve deneme |
| CLI'lar | Modelleri çalıştıran programlar |
| MCP sunucuları | Modellere ek araç ve bilgi veren sunucular |
| Beceriler | Modelin gerektiğinde yüklediği talimat paketleri |
| GitHub | Hesap durumu ve depo klonlama |
| Roller | Görevin hangi rollerden, hangi sırayla, hangi araç ve modelle geçeceği |
| Telegram | Telefondan görev verme ve onaylama |
| Otomasyonlar | Kayıtlı görev şablonları ve zamanlama |
| Uzak erişim | Telefondan/başka bilgisayardan erişim (Tailscale) |
| Kullanım | Token harcaması, hatalar, öneriler |
| Hakkında | Kurulu araçlar ve veri konumları |

## Genel

Bu projenin ayarlarıdır; proje klasöründeki `.aktapokus/roller.json` dosyasına yazılır. Önce bir proje klasörü seçilmiş olmalıdır, yoksa sayfa "Klasör seç" düğmesi gösterir.

| Ayar | Açıklama |
| --- | --- |
| Proje klasörü | Hangi klasörde çalışıldığını gösterir; **Değiştir** ile başka klasör seçilir |
| Token bütçesi | Bir görevin toplam girdi + çıktı token sınırı (adım sonunda denetlenir). **0 = sınırsız.** Claude Code basit bir görevde bile ~50.000 token harcar, çok düşük bir sınır görevi erken durdurur |
| En çok düzeltme turu | Doğrulama (test) başarısız olursa kodcunun en fazla kaç kez daha deneneceği (0-10) |
| Adım zaman aşımı (sn) | Bir adım bu süreyi aşarsa durdurulur (10-7200) |
| Ortak bağlam | Açıkken her çalıştırmadan önce `AGENTS.md` bloğu ve `.aktapokus/DURUM.md` güncellenir; model değişse de konu başa dönmez |
| Planı otomatik onayla | Açıkken yazdığınız görev, plan onay düğmesi beklemeden başlar. Otomasyon ve GitHub issue görevleri yine onay ister; değişiklikleri **koru/geri al** kararı da sizde kalır. Uzaktan değiştirilemez |
| Claude konuşması | Claude Code rolleri için: *Proje başına tek konuşma* (24 saat sonra yenilenir), *Her seferinde yeni konuşma* ya da *Konuşmayı kaydetme* |
| Testi varsayılan olarak atla | Test adımları çalışmaz; her görevin plan kartında yine de açıp kapatabilirsiniz |

**Değişiklikler ancak alttaki Kaydet düğmesine basınca uygulanır;** "kaydedildi" rozeti görünür. **Bir görev çalışırken bu alanlar kilitlidir** ("Görev çalışırken ayarlar değiştirilemez"), görev bitince değiştirin.

## Sağlayıcılar

Model sağlayıcılarına (Google/Gemini, OpenRouter, OpenAI, Anthropic, DeepSeek, Groq, Mistral, xAI...) kendi API anahtarınızla bağlanırsınız. Bu bölüm OpenCode'a özgüdür; OpenCode kurulu değilse çalışmaz.

**+ Model ekle sihirbazı:**

1. Sağlayıcıyı arayıp seçin (önerilenler ve bağlı olanlar başta).
2. API anahtarını yapıştırın. Anahtar yalnızca bu bilgisayardaki OpenCode'a gider; burada saklanmaz, günlüğe yazılmaz, gönderilince kutu boşaltılır.
3. Sağlayıcının modelleri listelenir. **Anahtarı dene** küçük bir istekle anahtarın çalışıp çalışmadığını gösterir (anahtar bağlanırken doğrulanmaz, bu yüzden bu adım önemlidir). **Role ata** modeli bir role bağlar.

Bağlı bir sağlayıcıda **Kaldır** anahtarı OpenCode'dan siler. Yalnızca ortam değişkeni (`env`) ya da `oauth` ile bağlanan sağlayıcılar anahtarla eklenemez.

> İpucu: ücretsiz denemek için Google AI Studio'dan alınan Gemini anahtarı yeterlidir.

## Modeller

Tek katalog: OpenCode'un yerleşik ücretsiz modelleri, bağlı sağlayıcıların modelleri, Codex ve Claude Code modelleri. En sonda, bilgisayarda kurulu yerel Ollama modelleri "Yerel modeller" başlığıyla görünür.

- **Arama kutusu:** ad ya da sağlayıcıya göre süzer.
- **Role ata:** satırdaki rol listesinden bir rol seçip düğmeye basın; o rolün CLI'ı ve modeli ayara yazılır.
- **Dene:** boş geçici klasörde küçük bir istek gönderir (az token harcar) ve "çalışıyor · X sn" ya da hatayı gösterir.
- Aradığınız model yoksa **Sağlayıcılar'a git** düğmesiyle anahtar ekleyin.

OpenCode modelleri ilk açılışta birkaç saniye "yükleniyor" gösterebilir; bu normaldir.

## CLI'lar

Modelleri çalıştıran programlar listelenir: OpenCode, Claude Code, Codex ve kendi eklediklerinizin her biri için **kurulu mu** bilgisi görünür.

- **Dene:** o CLI'ı boş geçici klasörde, yazma izni olmadan, tek küçük istekle sınar.
- **+ CLI ekle:** kod yazmadan yeni bir CLI tanımlarsınız (program yolu, argümanlar, istemin stdin ya da `{istem}` ile verilmesi, model bayrağı, çıktı çözümü). Özel olanlar için **Düzenle/Sil** vardır; bir rolde kullanılan CLI silinemez.
- **Güvenlik:** CLI tanımlamak bu bilgisayarda program çalıştırmak demektir; yalnızca yerel arayüzden yapılır. Program yolu mutlak olmalıdır, `.cmd/.bat/.ps1` sarmalayıcıları reddedilir. Özel CLI'lar OpenCode koruyucusu dışındadır; gizli dosya taraması onlar için de çalışır.

## MCP sunucuları

Modellere ek araç ve bilgi veren sunucular (yerel program ya da uzak HTTP adresi). Bir kez tanımlarsınız, **hangi projelerde açılacağını işaretlersiniz** (varsayılan: hiçbirinde). Görev sırasında sunucu o projenin CLI'larına kendiliğinden aktarılır (OpenCode, Claude Code, Codex); kendi CLI yapılandırmanıza dokunulmaz. **Dene** düğmesi sunucuyu geçici başlatıp bağlanıp bağlanmadığını gösterir.

Dikkat: MCP sunucusu bilgisayarınızda program çalıştırır ve proje klasör korumasının dışındadır. Yalnızca güvendiğiniz sunucuları ekleyin. Anahtar/başlık değerleri arayüze geri gösterilmez.

## Beceriler

`~/.agents/skills/<kimlik>/SKILL.md` dosyalarıdır (OpenCode okur). Arayüzden oluşturur, düzenler, silersiniz. Başka yerlerden (örn. `~/.claude/skills`) bulunanlar yalnızca listelenir, değiştirilemez. Klasörde başka dosya (scripts vb.) varsa silme reddedilir.

## GitHub

Bilgisayardaki `gh` (GitHub CLI) girişini kullanır; uygulama token'ı görmez ya da saklamaz. Önce bir terminalde `gh auth login` yapın. Bu bölümde hangi hesabın etkin olduğu görünür ve **depo klonlayıp proje olarak açabilirsiniz** (yalnız `sahip/depo` biçimi). Commit, push, pull request ve issue işlemleri bu sayfada değil, **proje panelindeki GitHub sekmesindedir**; yazan her işlem açık onay penceresiyle yapılır.

## Roller

Bir görevin hangi rollerden, hangi sırayla geçeceğini belirler. Varsayılan hat: **kodcu → test**.

- Her rolde: **CLI seçici**, model kutusu (öneri listeli), doğrulama rolü kutusu ve **talimat** metni.
- **↑ / ↓** ile çalışma sırası değiştirilir; **rol ekle / sil** yapılabilir.
- Test rolü `SONUC: BASARILI` demezse düzeltme döngüsü çalışır (üst sınır: Genel > "En çok düzeltme turu").
- Rolün bağlı olduğu CLI kurulu değilse arayüz uyarır ve onayınızla kurulu olana geçirmeyi önerir; hiçbir ayar kendiliğinden değişmez.

## Telegram

Bot arayüzle **aynı süreçte** çalışır; telefon ve arayüz aynı proje ve görevleri görür.

1. Token'ı **siz** `~/.aktapokus/telegram.token` dosyasına (ya da `AKTAPOKUS_TELEGRAM_TOKEN` ortam değişkenine) yazın. Token'ı BotFather verir (`/newbot`). Arayüz token'ı hiç göstermez, yalnızca "var/yok" der.
2. Bölümde **Başlat**'a basın (durum: çalışıyor / durduruluyor / kapalı).
3. Eşleşmediyseniz görünen kodu/bağlantıyı telefonda açın ya da botunuza `/eslestir KOD` yazın. İkinci cihaz için **Yeni eşleştirme kodu**.
4. **Uygulama açılınca otomatik başlat** kutusu, kısayolla açılışta botu kendiliğinden başlatır.
5. **Proje kökleri:** telefondan seçilebilecek klasörlerin kapsamı. Buradan eklenip kaldırılır; çalışan bota hemen yansır.
6. Altta son 60 satır günlük görünür.

`telegram-baslat.bat`'ı aynı anda çalıştırmayın (iki yoklayıcı Telegram 409 çakışması verir). Dosya içeriği ve fark metni Telegram'a varsayılan olarak **gönderilmez**; bu, telefondaki `/gizlilik acik` ile açılır.

## Otomasyonlar

Sık yaptığınız işi **şablon** olarak kaydedin: ad, proje, görev metni (`{tarih}`, `{saat}`, `{proje}`, `{dal}` değişkenleri doldurulur).

- **Şimdi çalıştır** ya da Telegram'da `/sablon` ile tetiklenir.
- Otomasyon **yalnızca plan üretir**; plan yine sizin onayınızı bekler.
- **Zamanlama:** her N dakikada bir (en az 5), her gün SS:DD ya da haftanın seçili günleri. Zamanlayıcı yalnızca **uygulama açıkken** çalışır; kaçan zamanlar geriye dönük çalıştırılmaz ("kaçırıldı" olarak görünür).
- Projede görev sürüyorsa ya da bir plan onay bekliyorsa tetikleme atlanır, birikmez. Günlük en çok 12 plan üretilir.

## Uzak erişim

**Varsayılan KAPALI.** Arayüze Tailscale özel ağındaki cihazlarınızdan (ör. telefon) ulaşmanızı sağlar; internete açılmaz.

1. Bu bilgisayara ve telefona Tailscale kurup ikisinde **aynı hesapla** giriş yapın.
2. "Uzak erişim açık"ı işaretleyin; durum "dinliyor" olunca gösterilen bağlantıyı telefonda açın. Bağlantı anahtarı içerir, yalnız kendi cihazlarınızda kullanın.
3. Şüphe halinde **Anahtarı yenile**: eski anahtarı ve açık uzak oturumları anında geçersiz kılar.

Uzak istemcinin yetkisi daraltılmıştır: görev verip onaylayabilir, dosya/fark/Git işlerini görebilir; ancak varsayılan olarak terminal, CLI/MCP/sağlayıcı tanımlama ve klonlama yapamaz. "Uzaktan terminal" ve "uzaktan yönetim" anahtarlarını bilerek ve ayrı ayrı açarsınız. **Uzak erişim ayarlarının kendisi uzaktan değiştirilemez**; bu sayfa uzak bağlantıdan açılırsa yalnızca bir uyarı gösterir.

## Kullanım

Her görevin `.aktapokus/kayit/*.json` kaydından hesaplanır; yeni veri toplanmaz, hiçbir şey gönderilmez.

- **Bugün / Son 7 gün / Toplam** token, 14 günlük çubuk grafik, model/rol dökümü, hata sınıfları (limit/kota, anahtar/giriş, zaman aşımı, bütçe) ve son hatalar.
- **Kapsam:** *Bu proje* ya da *Tüm projeler*.
- **Öneriler:** son 48 saatte bir model limit/kota hatası verdiyse, o modeli kullanan roller için tek tıkla "rol → model" değişikliği sunulur. Bu düğme ayara yazar, basmadan değişiklik olmaz.
- Abonelik kotalarının (Claude Pro, ChatGPT) **kalan** miktarı okunamaz; yalnızca harcanan token görünür.

## Hakkında

Hangi CLI'ların kurulu olduğunu ve veri konumlarını gösterir:

- Kullanıcı verisi: `~/.aktapokus` (`clilar.json`, `telegram.json`, `uygulama.log`)
- Proje ayarı ve kayıtlar: `<proje>\.aktapokus` (`roller.json`, `kayit/`)

## Sık karşılaşılan durumlar

| Durum | Ne yapmalı |
| --- | --- |
| "Ayarları görmek için önce bir proje klasörü seçin" | **Klasör seç** ile bir proje açın |
| Genel'deki alanlar soluk/değiştirilemiyor | Bir görev çalışıyor; bitmesini bekleyin ya da **Durdur** |
| Modeller listesi boş / "OpenCode modelleri alınamadı" | OpenCode kurulu mu, Hakkında'dan bakın; ilk açılışta birkaç saniye bekleyin |
| Rolün CLI'ı kurulu değil uyarısı | Roller bölümünde kurulu bir CLI seçin ya da uyarıdaki geçiş düğmesini onaylayın |
| Görev token bütçesi yüzünden durdu | Genel > Token bütçesi'ni yükseltin (0 = sınırsız) |
| Telegram 409 hatası | Aynı token'ı kullanan ikinci bir bot/bat dosyası çalışıyor; birini kapatın |

Ayrıntılı arka plan için bkz. [README.md](../README.md).
