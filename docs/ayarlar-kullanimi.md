# Ayarlar kılavuzu: adım adım nasıl yapılır

Bu kılavuz "bu bölüm nedir"den çok **"şunu nasıl yaparım"** sorusuna cevap verir. Her bölümde önce ne işe yaradığı bir cümleyle, sonra numaralı adımlar ve örnekler var. Sayfanın sonunda en sık yapılan işlerin hazır tarifleri ve sorun giderme tablosu bulunur.

## 0. Ayarlar sayfasını açmak, gezmek, kapatmak

1. Sol kenar çubuğunun en altındaki **⚙ Ayarlar** düğmesine tıklayın. (Kısayollar: yazı kutusunun altındaki bir rol çipine tıklamak **Ayarlar > Roller**'i, hızlı model menüsündeki "Tüm modeller ve ayarlar…" **Ayarlar > Modeller**'i açar. Kenar çubuğundaki **kullanıcı kutusuna** tıklamak **Ayarlar > Hesaplar**'ı açar.)
2. Solda bölüm menüsü, sağda seçili bölümün içeriği görünür. Bölümler: Hesaplar, Genel, Sağlayıcılar, Modeller, CLI'lar, MCP sunucuları, Beceriler, GitHub, Roller, Telegram, Otomasyonlar, Uzak erişim, Kullanım, Hakkında. Uygulama en son baktığınız bölümü hatırlar.
3. Kapatmak için **Esc** tuşuna ya da sol menünün üstündeki **← Uygulamaya dön**'e basın.
4. **Önemli iki kural:** (a) Bir **görev çalışırken** Genel ve Roller ayarları kilitlidir ("Görev çalışırken ayarlar değiştirilemez"); görev bitince ya da **Durdur**'dan sonra değiştirin. (b) Genel ve Roller'deki değişiklikler yalnızca alttaki **Kaydet** / **Rolleri kaydet** düğmesine basınca uygulanır.

---

## 1. Hesaplar: kim olarak giriş yaptım?

**Ne işe yarar:** Aktapokus'un kendi kullanıcı hesabı yoktur; bilgisayarınızda yerel çalışır ve giriş istemez. "Giriş" dediğimiz şey, Aktapokus'un kullandığı araçlardaki kimliklerinizdir. Bu bölüm hepsini tek yerde gösterir.

**Nasıl bakarım:**
1. Kenar çubuğunun altındaki kutuya (Windows kullanıcı adınız ve "yerel · hesap girişi yok" yazar) ya da **Ayarlar > Hesaplar**'a tıklayın.
2. Kartları okuyun: **GitHub** (hangi `@hesap`), **Claude Code** (e-posta ve abonelik), **Codex** (giriş yöntemi), **Telegram botu**, **Uzak erişim**. Rozet yeşilse giriş var, kırmızıysa yok.
3. Bir hizmette giriş yoksa kartın yazdığı komutu **bir terminalde** çalıştırın: `claude auth login`, `codex login`, `gh auth login`. Sonra **Yenile**'ye basın.

**Birden çok GitHub hesabınız varsa:** Bilgisayarda hangisinin etkin olduğu burada görünür. Değiştirmek için terminalde `gh auth switch` çalıştırıp **Yenile**'ye basın.

---

## 2. Genel: bu projenin çalışma ayarları

**Ne işe yarar:** Seçili projenin klasöründeki `.aktapokus/roller.json` dosyasına yazılır. Önce bir proje açık olmalıdır (yoksa sayfa **Klasör seç** düğmesi gösterir).

**Nasıl değiştiririm:**
1. **Ayarlar > Genel**'i açın.
2. İstediğiniz alanı değiştirin (aşağıdaki tablo), **Kaydet**'e basın, "kaydedildi" rozetini bekleyin.

| Alan | Ne yapar | Ne yazmalıyım |
| --- | --- | --- |
| Token bütçesi | Bir görevin toplam girdi + çıktı token sınırı; adım bitince denetlenir | **0 = sınırsız.** Claude Code basit bir görevde bile ~50.000 token harcar, çok düşük sınır görevi erken durdurur |
| En çok düzeltme turu | Test başarısız olursa kodcunun kaç kez daha deneyeceği | 0 ile 10 arası. 0 = hiç tekrar denemez |
| Adım zaman aşımı (sn) | Bir adım bu süreyi aşarsa durdurulur | 10 ile 7200 arası |
| Ortak bağlam | Her çalıştırmadan önce `AGENTS.md` bloğu ve `.aktapokus/DURUM.md` güncellenir; model değişince konu başa dönmez | Genelde açık bırakın |
| Planı otomatik onayla | Yazdığınız görev, plan onayı beklemeden başlar | Açarsanız onay düğmesi çıkmaz. Otomasyon ve GitHub issue görevleri **yine onay ister**; görev bitince "değişiklikler korunsun mu" kararı da sizde kalır. Uzaktan değiştirilemez |
| Claude konuşması | Claude Code rolleri için konuşma kaydı | **Proje başına tek konuşma:** tüm görevler Claude Code'da tek konuşmaya yazılır (24 saat sonra yenilenir). **Her seferinde yeni:** her görev ayrı konuşma. **Kaydetme:** konuşma saklanmaz |
| Testi varsayılan olarak atla | Test (doğrulama) adımları çalışmaz | Her görevin plan kartındaki "Test adımını atla" kutusuyla görev bazında yine değiştirebilirsiniz |

---

## 3. Sağlayıcılar: API anahtarıyla bir model sağlayıcısına bağlanmak

**Ne işe yarar:** OpenCode'un kullanacağı modellerin sağlayıcılarına (Google/Gemini, OpenRouter, OpenAI, Anthropic, DeepSeek, Groq, Mistral, xAI…) kendi anahtarınızla bağlanırsınız. OpenCode kurulu değilse bu bölüm çalışmaz.

**Nasıl yeni sağlayıcı eklerim:**
1. **Ayarlar > Sağlayıcılar** > **+ Model ekle**.
2. Sağlayıcıyı arayıp seçin (önerilenler ve bağlı olanlar başta çıkar).
3. API anahtarını yapıştırın. Anahtar yalnızca bu bilgisayardaki OpenCode'a gider; Aktapokus'ta saklanmaz, günlüğe yazılmaz, gönderilince kutu boşaltılır.
4. Sağlayıcının modelleri listelenir. Önce **Anahtarı dene**'ye basın: anahtar bağlanırken doğrulanmaz, bu adım çalışıp çalışmadığını gösterir. Sonra **Role ata** ile modeli bir role bağlayın.

**Nasıl kaldırırım:** Bağlı sağlayıcı satırında **Kaldır**. Yalnızca ortam değişkeni ya da `oauth` ile bağlanan sağlayıcılar anahtarla eklenemez.

**Ücretsiz denemek için:** Google AI Studio'dan alınan bir Gemini anahtarı yeterlidir.

---

## 4. Modeller: bir modeli role atamak ya da denemek

**Ne işe yarar:** OpenCode'un yerleşik ücretsiz modelleri, bağlı sağlayıcıların modelleri, Codex ve Claude Code modelleri tek katalogda. En sonda bilgisayarda kurulu yerel Ollama modelleri görünür.

**Nasıl yaparım:**
1. **Ayarlar > Modeller**. İlk açılışta OpenCode modelleri birkaç saniye "yükleniyor" gösterebilir; bu normaldir.
2. Üstteki kutuya modelin ya da sağlayıcının adını yazarak süzün.
3. **Bir role atamak için:** satırdaki rol listesinden rolü (örn. `kodcu`) seçin, **Role ata**'ya basın. O rolün CLI'ı ve modeli ayara yazılır.
4. **Denemek için:** **Dene**. Boş bir geçici klasörde küçük bir istek gönderir (az token harcar) ve "çalışıyor · X sn" ya da hatayı gösterir.
5. Aradığınız model listede yoksa **Sağlayıcılar'a git** ile anahtar ekleyin.

---

## 5. CLI'lar: modelleri çalıştıran programlar

**Ne işe yarar:** OpenCode, Claude Code, Codex ve kendi eklediğiniz programların her biri için "kurulu mu" bilgisi.

**Nasıl denerim:** Satırdaki **Dene**: o CLI'ı boş geçici klasörde, yazma izni olmadan tek küçük istekle sınar.

**Nasıl yeni bir CLI eklerim (kod yazmadan):**
1. **+ CLI ekle**.
2. Alanları doldurun. Örnek, `aider` için:
   - **Ad:** `aider` (küçük harf)
   - **Görünen ad:** `Aider`
   - **Program (tam yol, .exe):** `C:\Araclar\aider.exe`
   - **Sabit argümanlar:** her satıra bir tane. İstem argüman olarak verilecekse bir satıra `{istem}` yazın; yazmazsanız istem standart girdiden (stdin) gider.
   - **Model bayrağı:** örn. `--model` (boşsa model seçimi yok)
   - **Yazma izinli / Salt okunur çalışma argümanları:** satır satır; görev yazma iznine göre hangisi kullanılacak
   - **Yanıt metni yolu:** çıktı JSON ise yanıtın bulunduğu alan (örn. `result`); ayrıca hata bayrağı ve token alanlarının yolları
   - **Önerilen modeller:** virgülle
3. **Kaydet**. Sonra satırdaki **Dene** ile sınayın.

**Kısıtlar:** Program yolu mutlak olmalı; `.cmd`, `.bat`, `.ps1` sarmalayıcıları reddedilir. Bir rolde kullanılan CLI silinemez. CLI tanımlamak bu bilgisayarda program çalıştırmak demektir, bu yüzden yalnızca yerel arayüzden yapılır. Özel CLI'lar OpenCode'un klasör koruyucusunun dışındadır.

---

## 6. MCP sunucuları: modellere ek araç vermek

**Ne işe yarar:** Bir kez tanımlarsınız, **hangi projelerde açılacağını işaretlersiniz** (varsayılan: hiçbirinde). Görev sırasında sunucu o projenin CLI'larına (OpenCode, Claude Code, Codex) kendiliğinden aktarılır; kendi CLI yapılandırmanıza dokunulmaz.

**Nasıl yerel (program olarak çalışan) bir MCP eklerim:** Örnek, bu bilgisayardaki bir Python sunucusu:
1. **+ MCP sunucusu ekle**.
2. **Ad:** `sokrates` (küçük harf). **Tür:** yerel.
3. **Komut:** her satıra bir parça yazın. İlk satır program, sonrakiler argümandır:
   ```
   C:\Python314\python.exe
   C:\Users\siz\Desktop\aktapokus\aktapokus-sokrates-mcp\server.py
   ```
   (npx ile bir paket için: ilk satır `npx`, ikinci satır `-y`, üçüncü satır paket adı.)
4. Anahtar gerekiyorsa **Ortam değişkenleri**'ne her satıra `ANAHTAR=değer` yazın. Kaydedilen değer sonra `••••` görünür; değiştirmezseniz korunur.
5. **Kaydet**, sonra **Dene**: sunucuyu seçili projede geçici başlatıp bağlanıp bağlanmadığına bakar.
6. Satırdaki proje listesinden **hangi projelerde açık olacağını işaretleyin**.

**Nasıl uzak (HTTP) bir MCP eklerim:** **Tür:** uzak, **Adres:** `https://…` ile başlayan tam adres, gerekirse **Başlıklar:** her satıra `Ad: değer` (örn. `Authorization: Bearer …`). Kaydedip **Dene**.

**Dene "needs_auth" derse:** Sunucu OAuth girişi istiyor demektir. Aktapokus yalnızca sabit başlık/anahtar gönderebilir. Çözüm: sunucunun herkese açık olması, bir API anahtarı sunması (başlığa ekleyin) ya da sunucu sizdeyse kimlik doğrulamayı kapatmak.

**Dikkat:** MCP sunucusu bilgisayarınızda program çalıştırır ve proje klasör korumasının dışındadır. Yalnızca güvendiğiniz sunucuları ekleyin.

---

## 7. Beceriler: modele hazır talimat paketleri vermek

**Ne işe yarar:** `~/.agents/skills/<kimlik>/SKILL.md` dosyalarıdır; OpenCode bulur, ilgili olduğunda yükler. Başka yerlerden bulunanlar (örn. `~/.claude/skills`) yalnızca listelenir, değiştirilemez.

**Nasıl beceri oluştururum:**
1. **Ayarlar > Beceriler** > **+ Beceri ekle**.
2. **Kimlik:** küçük harf ve tire, örn. `sunum-hazirla`. **Görünen ad:** `Sunum Hazırla`.
3. **Açıklama:** modelin "bunu ne zaman yükleyeyim" diye baktığı cümle. Örn. `Kısa bir sunum taslağı çıkarmak istendiğinde kullan`. Açık ve spesifik yazın; belirsiz açıklama becerinin hiç yüklenmemesine yol açar.
4. **İçerik:** modele verilecek talimatlar, Markdown. Adımları numaralayın.
5. "Modele kendiliğinden sunulsun" kutusu kapalıysa beceri yalnızca `@kimlik` yazılarak çağrılır.
6. **Kaydet**. Düzenlemek için satırdaki **Düzenle**, silmek için **Sil**. Klasörde başka dosya (scripts vb.) varsa silme reddedilir.

---

## 8. GitHub

**Ne işe yarar:** Bilgisayardaki `gh` oturumunu kullanır; Aktapokus token'ı görmez ya da saklamaz. Hangi hesabın etkin olduğu burada ve **Hesaplar**'da görünür.

**Nasıl depo klonlarım:**
1. Önce giriş: terminalde `gh auth login` (giriş yoksa bu bölüm bunu söyler).
2. **Ayarlar > GitHub**'da liste kendiliğinden yüklenir: kendi hesabınızın **ve üyesi olduğunuz organizasyonların** depoları. Üstteki **sahip** listesinden birini seçin, **Depo ara** kutusuna yazdıkça liste süzülür.
3. **Üst klasör**'ün (varsayılan Masaüstü) doğru olduğundan emin olun.
4. İstediğiniz depoda **Klonla**, onay penceresinde onaylayın. Depo klonlanır ve proje olarak açılır.

Klonlanan depodaki talimat dosyaları (`AGENTS.md`, `.opencode/`) ajanın davranışını etkileyebilir; yalnızca güvendiğiniz depoları açın.

**Commit, push, pull request, issue:** bu sayfada değil, **proje panelindeki GitHub ve Git sekmelerindedir**. Yazan her işlem açık onay penceresiyle yapılır.

---

## 9. Roller: görev hangi adımlardan geçsin?

**Ne işe yarar:** Bir görevin hangi rollerden, hangi sırayla, hangi CLI ve modelle geçeceğini belirler. Varsayılan hat: **kodcu → test**.

**Nasıl bir rolün modelini değiştiririm:**
1. **Ayarlar > Roller**. Rolün kartında **CLI seçici**'den programı (OpenCode, Claude, Codex…), **model** kutusundan modeli seçin ya da yazın (boş = CLI'ın varsayılanı).
2. **Rolleri kaydet**.

**Nasıl rol eklerim / silerim / sırasını değiştiririm:**
- Eklemek için alttaki kutuya yeni rol adını yazıp **Rol ekle**. Silmek için rolün **Sil** düğmesi.
- Sıra için rolün **↑ / ↓** düğmeleri. İlk rol doğrulama rolü olamaz.
- Bir rolü **doğrulama rolü** yapmak için kutusunu işaretleyin: bu rol yanıtının son satırına `SONUC: BASARILI` ya da `SONUC: BASARISIZ` yazmalıdır. Başarısızsa kodcu Genel'deki "En çok düzeltme turu" kadar yeniden dener.
- **Talimat** kutusu o role verilen yönergedir. Kısa ve odaklı tutarsanız ajan da kısa ve odaklı çalışır; ayrıntılı belge/analiz görevleri için "ayrıntılı ol, adım adım yaz, örnek ver" gibi cümleler ekleyin.

Rolün bağlı olduğu CLI kurulu değilse arayüz uyarır ve onayınızla kurulu olana geçirmeyi önerir; hiçbir ayar kendiliğinden değişmez.

---

## 10. Telegram: telefondan görev vermek

**Ne işe yarar:** Telefondan görev başlatma, onay ve takip. Bot bu uygulamayla aynı süreçte çalışır; telefon ve arayüz aynı proje ve görevleri görür. Telegram'dan hiçbir şey tanımlanamaz (CLI/MCP/otomasyon tanımı yalnızca bilgisayardan).

**Nasıl kurarım:**
1. Telegram'da **@BotFather**'a `/newbot` yazın, adı seçin; size bir **token** verir.
2. Token'ı **siz** `C:\Users\<kullanıcı adınız>\.aktapokus\telegram.token` dosyasına yazın (içinde yalnızca token olsun). Token'ı sohbete ya da bana yazmayın; arayüz onu hiç göstermez, yalnızca "var/yok" der.
3. **Ayarlar > Telegram** > **Başlat**. Durum "çalışıyor" olmalı.
4. **Eşleştirme:** görünen tek kullanımlık kodu (10 dk geçerli) botunuza `/eslestir KOD` diye yazın ya da gösterilen bağlantıyı telefonda açın. İkinci bir cihaz için **Yeni eşleştirme kodu**.
5. **Proje kökleri:** telefondan `/projeler` ile hangi klasörlerin altındaki projelerin listeleneceğini belirler. Örn. `C:\Users\siz\Desktop\projeler` yazıp **Kök ekle**; kaldırmak için **Kaldır**. Değişiklik çalışan bota hemen yansır.
6. Kısayolla açtığınızda botun kendiliğinden başlaması için **Uygulama açılınca otomatik başlat** kutusunu işaretleyin. Telefondan kullanmak için bilgisayarın açık olması gerekir.

**Telefonda komutlar:** `/projeler`, `/gorev <metin>`, `/sablon` (kayıtlı otomasyon şablonlarını listeler), `/gizlilik acik` (dosya içeriği ve fark metninin Telegram'a gönderilmesini açar; varsayılan kapalı).

**Sorun:** "409" hatası, aynı token'ı kullanan ikinci bir bot (örn. `telegram-baslat.bat`) çalışıyor demektir; birini kapatın.

---

## 11. Otomasyonlar: sık işi şablon yapmak, zamanlamak

**Ne işe yarar:** Bir otomasyon **yalnızca plan üretir**; plan yine sizin onayınızı bekler, onaysız dosya değişmez.

**Nasıl şablon oluştururum (örnek: haftalık bağımlılık kontrolü):**
1. **Ayarlar > Otomasyonlar** > **+ Şablon ekle**.
2. **Ad:** `haftalik-kontrol` (küçük harf, rakam, tire, en çok 31 karakter).
3. **Proje:** listeden seçin (kayıtlı olmalı).
4. **Görev metni:** `Bağımlılıkları kontrol et ve güncel olmayanları listele. Tarih: {tarih}`. Kullanabileceğiniz değişkenler: `{tarih}` `{saat}` `{proje}` `{dal}`.
5. İsterseniz **Açıklama** (tek satır) yazın. "Açık" kutusu Telegram'dan çalıştırılabilmeyi belirler.
6. **Kaydet**.

**Nasıl çalıştırırım:** Şablon kartında **Şimdi çalıştır** (seçili projeyi değiştirmeden o projede bir plan oluşturur), ya da telefonda `/sablon`.

**Nasıl zamanlarım:** Formda **Zamanlanmış çalıştır**'ı işaretleyin ve birini seçin: *her N dakikada bir* (en az 5), *her gün* (SS:DD), ya da *haftanın seçili günleri*. Kaydedin. Kartta ⏱ satırı çıkar.
- Zamanlayıcı yalnızca **uygulama açıkken** çalışır. Uygulama kapalıyken kaçan zamanlar geriye dönük çalıştırılmaz; geçmişte "kaçırıldı" görünür.
- Projede görev sürüyorsa ya da bir plan onay bekliyorsa tetikleme **atlanır** (birikmez). Günde en çok 12 zamanlanmış plan üretilir.
- **Çalışma geçmişi** bölümü her tetiklemenin sonucunu gösterir: plan oluştu, atlandı, kaçırıldı, hata.

---

## 12. Uzak erişim: telefondan ya da başka bilgisayardan arayüze ulaşmak

**Ne işe yarar:** Arayüze **Tailscale** özel ağındaki cihazlarınızdan ulaşırsınız; internete açılmaz. **Varsayılan KAPALI**: kapalıyken hiçbir ağ dinleyicisi açılmaz.

**Nasıl açarım:**
1. Bu bilgisayara ve telefona **Tailscale** kurun, ikisinde **aynı hesapla** giriş yapın.
2. **Ayarlar > Uzak erişim**: "Tailscale" satırında adresin göründüğünden emin olun (yoksa **Yeniden kontrol et**).
3. Uzak erişim anahtarını açın, istenirse **Port** yazıp **Kaydet**. Durum "dinliyor" olunca gösterilen bağlantılardan birini telefonda tarayıcıda açın. **Kopyala** ile panoya alabilirsiniz. Bağlantı gizli anahtar içerir; yalnızca kendi cihazlarınızda kullanın.
4. Telefonda alt çubuktan **Görevler / Sohbet / Panel** arasında geçersiniz. (Ana ekrana uygulama olarak ekleme henüz yok.)

**Güvenlik anahtarları (hepsi varsayılan kapalı, ayrı ayrı bilerek açılır):** "Uzaktan terminal" (tam komut çalıştırma yetkisi) ve "Uzaktan yönetim" (CLI, MCP, sağlayıcı, Telegram, beceri tanımlama; klasör gezme; depo klonlama). Kapalıyken uzak cihaz yalnızca görev verip onaylayabilir, dosya/fark/Git bilgilerini görebilir.

**Şüphelenirseniz:** **Anahtarı yenile**. Eski anahtar ve açık uzak bağlantılar anında geçersiz olur.

**Not:** Uzak erişim ayarlarının kendisi uzaktan değiştirilemez; bu sayfa uzak bağlantıdan açılırsa yalnızca bir uyarı gösterir.

---

## 13. Kullanım: ne kadar harcadım?

**Ne işe yarar:** Her görevin `.aktapokus/kayit/*.json` kaydından hesaplanır; yeni veri toplanmaz, hiçbir şey gönderilmez.

**Nasıl okurum:**
1. **Ayarlar > Kullanım**. Üstten **Bu proje** ya da **Tüm projeler** kapsamını seçin; **Yenile** ile tazeleyin.
2. **Bugün / Son 7 gün / Toplam** token, 14 günlük grafik, model ve rol dökümü, hata sınıfları (limit/kota, anahtar/giriş, zaman aşımı, bütçe) ve son hatalar görünür.
3. **Öneriler:** son 48 saatte bir model limit/kota hatası verdiyse, o modeli kullanan roller için tek tıkla "rol → başka model" değişikliği sunulur. Düğmeye basmadan hiçbir şey değişmez.

Abonelik kotalarının (Claude Pro, ChatGPT) **kalan** miktarı okunamaz; yalnızca harcanan token görünür.

---

## 14. Hakkında

Hangi CLI'ların kurulu olduğunu ve verilerin nerede durduğunu gösterir:
- Kullanıcı verisi: `~/.aktapokus` (`clilar.json`, `mcp.json`, `otomasyonlar.json`, `gorev-meta.json`, `telegram.json`, `uygulama.log`)
- Proje ayarı ve kayıtlar: `<proje>\.aktapokus` (`roller.json`, `kayit/` ve görev konuşmaları `kayit/olaylar/`)

---

## Hazır tarifler

**Ücretsiz modelle ilk görevi vermek:** Ayarlar > Roller'de `kodcu` için OpenCode + ücretsiz model (varsayılan) kalsın → **Test adımını atla**'yı kapatmak istemiyorsanız olduğu gibi bırakın → yazı kutusuna görevi yazın → plan kartında **Onayla**.

**Claude Code'u kodcu yapmak:** Ayarlar > Roller > `kodcu` > CLI olarak **Claude**, model `sonnet` (ya da `opus`/`haiku`) > **Rolleri kaydet**. Önce Hesaplar'da Claude Code'un "giriş yapıldı" olduğunu görün.

**Onay düğmesine basmadan görev vermek:** Ayarlar > Genel > **Planı otomatik onayla** > **Kaydet**. Yine de değişiklikleri korumak/geri almak sizin kararınızdır.

**Testi her seferinde çalıştırmamak:** Ayarlar > Genel > **Testi varsayılan olarak atla** (hepsi için), ya da tek görev için plan kartındaki **Test adımını atla** kutusu, ya da çalışırken üstteki **Testi atla** düğmesi.

**Token bütçesi yüzünden görev durduysa:** Genel > Token bütçesi'ni yükseltin ya da `0` yazın.

**Bir görevi Claude Code'da sürdürmek:** Soldaki görev satırına sağ tıklayın (ya da ⋯) > **Claude Code'da devam et**. Terminal proje klasöründe açılır ve aynı konuşma `claude --resume` ile sürer.

## Sorun giderme

| Belirti | Ne yapmalı |
| --- | --- |
| "Ayarları görmek için önce bir proje klasörü seçin" | **Klasör seç** ile bir proje açın |
| Genel/Roller alanları soluk, değişmiyor | Bir görev çalışıyor; bitmesini bekleyin ya da **Durdur** |
| Modeller listesi boş / "OpenCode modelleri alınamadı" | OpenCode kurulu mu, Hakkında'dan bakın; ilk açılışta birkaç saniye bekleyin |
| Rolün CLI'ı kurulu değil uyarısı | Roller'de kurulu bir CLI seçin ya da uyarıdaki geçiş düğmesini onaylayın |
| Görev token bütçesi yüzünden durdu | Genel > Token bütçesi'ni yükseltin (0 = sınırsız) |
| GitHub'da yanlış hesap görünüyor | Terminalde `gh auth switch`, sonra Hesaplar'da **Yenile** |
| MCP "needs_auth" | Sunucu OAuth istiyor; herkese açık yapın ya da başlığa API anahtarı ekleyin |
| Telegram 409 | Aynı token'ı kullanan ikinci bir bot çalışıyor; birini kapatın |
| Uygulama "zaten açık" diyor | Pencere kapandıktan birkaç saniye sonra yeniden açmayı deneyin; açık bir pencere varsa öne getirilir |
| Claude/Codex "giriş yok" | Terminalde `claude auth login` / `codex login`, sonra Hesaplar'da **Yenile** |

Arka plan ayrıntıları için bkz. [README.md](../README.md).
