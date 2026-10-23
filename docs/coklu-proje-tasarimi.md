# Çoklu proje tasarımı (taslak, onay bekliyor)

Amaç: aynı anda birkaç projeyle çalışabilmek. Sol kenarda proje grupları, her projenin kendi görevleri, her biri arka planda
ilerleyebilir; telefondan (Telegram) ve arayüzden aynı yönetim.

Bu belge KOD DEĞİL, karar belgesidir. Kodlamaya geçmeden önce aşağıdaki "Açık kararlar" bölümünü birlikte netleştiriyoruz.

## 1. Bugünkü durum (kodda ölçülen)

Uygulama **tek proje, tek görev** varsayımıyla yazıldı:

| Yer | Sorun |
| --- | --- |
| `Uygulama.klasor`, `.kosu`, `.bus`, `.aktif_calistirici`, `.son_hat` | Tek proje durumu; `arayuz.py` içinde ~50 kullanım |
| `Uygulama.klasor_sec` | Proje değiştirince eski durum atılır (`self.kosu = None`) |
| Olay akışı (`OlayAkisi`) | Tek akış; olaylarda proje kimliği yok |
| `SunucuCalistirici.ilerleme` ve `._aktif_sid` | Tek geri çağrı ve tek "aktif oturum": iki proje aynı anda koşarsa **birbirinin üstüne yazar** (durdurma yanlış oturumu durdurur, canlı olaylar yanlış projeye gider) |
| Önizleme sunucusu | Tek proje klasörünü sunar |
| Telegram `Bot` | Tek `Uygulama` + tek "seçili klasör" |
| `calistirici_olustur("opencode-sunucu")` | Tek ortak OpenCode sunucusu (bu sorun DEĞİL: sunucu zaten `location.directory` ile çok klasör destekler) |

Zaten güvenli olanlar: kayıtlar, koruyucu (`.opencode/opencode.json`), anlık görüntü/geri alma ve `ayar` **proje klasörü başınadır**; iki farklı
klasör birbirini etkilemez. Proje kayıt defteri (`projeler.py`, kalıcı proje kimliği) hazır.

## 2. İlkeler (önerilen kurallar)

1. **Proje = klasör.** Kimlik `projeler.proje_kimligi(yol)` (yol özeti; Windows'ta büyük/küçük harf duyarsız). Aynı klasör iki kez eklenmez.
2. **Proje başına aynı anda en fazla 1 görev.** Gerekçe: geri alma git anlık görüntüsüne dayanır ve klasör başınadır; aynı klasörde iki ajan aynı dosyaları ezer.
   (İleride isteğe bağlı: git worktree ile aynı projede paralel görev, Codex gibi. Bu ayrı ve büyük bir iştir.)
3. **Projeler arası en fazla N eşzamanlı görev** (varsayılan 3, Ayarlar > Genel'de değiştirilir). Sınır aşılırsa görev **"sırada"** durumuna girer,
   yer açılınca kendiliğinden başlar. Gerekçe: RAM ve token kaygınız (her koşu OpenCode/Codex/Claude süreçleri açar).
4. **Plan onayı bekleyen görev slot tutmaz**; slot yalnız ÇALIŞAN görev tutar (insan onayını beklerken başka proje koşabilsin).
5. **Bütçe, durdurma, onay, geri alma proje başınadır.** Bir projenin "Durdur"u yalnız onu durdurur.
6. **Tek olay akışı, olaylar proje kimliğiyle etiketli.** Arayüz hepsini alır; yan çubuk her projenin canlı durumunu (çalışıyor / onay bekliyor / karar bekliyor / sırada / hata) gösterir; ortadaki sohbet seçili projeyi gösterir.
7. **Telegram:** her sohbetin "aktif projesi" vardır; `/projeler` kayıt defterinden seçtirir; görev bildirimleri hangi projeden geldiğini yazar. Telefon proje listesini GENİŞLETEMEZ (yalnız izinli köklerin altındakiler).
8. **Güvenlik değişmez:** her proje `guvenli_klasor` denetiminden ve koruyucudan geçer; proje eklemek/kaldırmak yalnız yerel arayüzden olur; kayıt defterinden "unut" klasöre dokunmaz.

## 3. Mimari

```
Uygulama (yonetici)
 ├─ oturumlar: {proje_id: ProjeOturumu}      # yalniz acilmis projeler bellekte
 ├─ kota: ayni anda en cok N calisan gorev + bekleme sirasi (FIFO)
 ├─ bus: tek OlayAkisi (olaylar {"proje": id, ...})
 └─ ortak: calistirici_uret, telegram, saglayici istemcisi

ProjeOturumu (eski Uygulama durumunun proje basina hali)
 ├─ klasor, kosu, son_hat, aktif_calistirici, kilit
 └─ gorev_olustur / onayla / reddet / karar_ver / durdur / fark / ayar...
```

- **API:** `/api/p/<proje_id>/...` (gorev, ayar, dosyalar, ciktilar, gecmis...). Eski `/api/...` yolları "seçili proje" olarak çalışmaya devam eder
  (arayüz ve Telegram kademeli geçer; testler kırılmaz). Genel uçlar (`/api/projeler`, `/api/clilar`, `/api/telegram`, ayarlar) proje dışıdır.
- **`SunucuCalistirici`:** `calistir(..., ilerleme=None)` çağrı başına geri çağrı alır; `_aktif_sid` çağrı başına sözlüğe (`{proje: sid}`) taşınır.
  Ortak OpenCode sunucusu aynen kalır.
- **Önizleme:** önizleme sunucusu "görüntülenen proje"yi sunar (seçili proje değişince değişir); arka plandaki projeler için önizleme gerekmez.
- **Kayıt defteri** `projeler.py` proje listesinin tek kaynağıdır (sol kenar, ortam çipi, Telegram).
- **Eşzamanlılık kilidi:** oturum başına bir kilit; kota için tek global kilit. Kuyruk bir yardımcı iş parçacığı ya da yer açılınca tetiklenen devam ile işler.

## 4. Riskler ve karşı önlemler

| Risk | Önlem |
| --- | --- |
| Çoklu koşuda geri çağrı/oturum karışması (en büyük risk) | Çağrı başına geri çağrı; iki projeyi aynı anda koşturan **izolasyon testleri** (olaylar karışmaz, bir projeyi durdurmak diğerine dokunmaz) + mutasyon |
| RAM/süreç patlaması | Global üst sınır N, kuyruk, ölçüm (süreç sayısı ve bellek) |
| Aynı klasörün iki projede eklenmesi, iç içe klasörler | Kimlik tekilliği; iç içe projeleri uyarı/reddet |
| Proje silinir/taşınır | `var=false` işaretlenir, görev başlatılamaz, "unut" ile temizlenir |
| Telegram'da yanlış projeye görev | Her bildirim ve onay mesajı proje adını taşır; onay düğmeleri proje kimliği içerir |
| Büyük refactor'da gerilemeler | Aşamalı geçiş (aşağıda), her aşamada tüm testler yeşil, eski API korunur |

## 5. Aşamalar (her biri ayrı test + commit)

- **P1 — Oturum ayrıştırma (davranış değişmez):** `ProjeOturumu` çıkar, `Uygulama` onu tek "seçili proje" ile yönetir. Tüm mevcut testler aynen geçmeli.
- **P2 — Çoklu oturum:** birden çok açık oturum, olaylara `proje` etiketi, çağrı başına geri çağrı/oturum (SunucuCalistirici), kota ve kuyruk, `/api/p/<id>/...`.
- **P3 — Arayüz:** sol kenarda proje grupları ve canlı durum rozetleri, proje başına sohbet durumu, ortam çipi proje değiştirir (görev çalışırken de, arka plana bırakarak), "+ Proje ekle".
- **P4 — Telegram:** sohbet başına aktif proje, proje adlı bildirimler.
- **P5 — Cilalama:** önizleme/dosya izleme proje bazlı, Çıktılar ve Kullanım proje seçimi, Ayarlar'da eşzamanlılık sınırı.

## 6. Test planı

- Sahte çalıştırıcılarla iki proje **gerçekten eşzamanlı** (olay karışması yok, durdurma izolasyonu, kota/kuyruk sırası, plan onayı slot tutmaz).
- Gerçek OpenCode ile iki klasörde paralel görev (ücretsiz model).
- Ölçüm: eşzamanlı 3 görevde süreç sayısı ve bellek (README'ye yazılır).
- Mutasyon: her kural (kota, izolasyon, kimlik tekilliği) kaldırılınca test düşmeli.
- Gerçek tarayıcıda: iki proje arası geçiş, arka plandaki görevin bildirimi.

## 6b. Kullanıcı kararı: kenar çubuğu Claude'unki gibi proje grupları (2026-10-23)

Kullanıcı Claude masaüstü kenar çubuğunun ekran görüntüsünü gönderip "buradaki gibi bir sürü ayrı proje oluşturabilmek isterim" dedi. Hedef düzen:

- **Proje grupları**, her grubun başlığında **`+`** (o projede yeni görev başlat) ve açılıp kapanan ok; grubun altında görevleri, uzunsa **"Daha fazla göster"**.
- **Canlı durum noktası** görev satırında (örn. sarı = onay/karar bekliyor ya da okunmamış sonuç, gri = bitti, mavi = çalışıyor).
- Altta **"Son görevler" (Recents)**: tüm projelerden en yeni görevler.
- Üstte **"+ Yeni"** (yeni proje ya da yeni görev) ve arama kutusu (görev/proje ara).
- Bir sürü proje: sınır yok (kayıt defteri şimdilik en çok 60 projeyi tutuyor; bu sınır kaldırılabilir/artırılabilir).
- Gruplamanın anlamı henüz netleşmedi: grup = **bir proje klasörü** (altındaki görevler o projenin oturumları) mu, yoksa projeleri **etiketle gruplama** (örn. "Aktapokus" altında birkaç klasör) mı? Öneri: grup = proje klasörü, ayrıca isteğe bağlı üst grup etiketi.

## 7. Açık kararlar (sizin onayınız gerekiyor)

1. **Proje başına 1 görev** kuralı (önerilen) uygun mu? Yoksa aynı projede de paralel görev (worktree ile) şimdiden istenir mi?
2. **Eşzamanlı görev üst sınırı** varsayılan **3** olsun mu? (RAM/token kaygınıza göre)
3. **Proje listesi:** yalnız sizin eklediğiniz projeler (önerilen) mi, yoksa Telegram kök klasörlerindeki projeler otomatik mi listelensin?
4. ~~Gruplama~~ **Karar verildi:** Claude'daki gibi proje grupları (bkz. 6b). Kalan soru: grup = tek proje klasörü mü, yoksa birkaç klasörü bir araya getiren üst grup etiketi de olsun mu?
5. **Arka plandaki projenin bildirimi:** görev biterken/onay beklerken sol kenarda rozet + (uygulama pencere dışındaysa) Windows bildirimi istenir mi?
6. **Sırayla yapılacak aşamalar** (P1→P5) uygun mu, yoksa önce yalnız P1+P2 (altyapı) yapılıp arayüz sonra mı?

## 8. Verilen kararlar (2026-10-23)

1. Proje başına **1 görev**.
2. Eşzamanlı üst sınır **3**, fazlası sırada bekler.
3. Proje listesi **yalnız kullanıcının eklediği** projeler.
4. **Grup = bir proje klasörü** (üst grup etiketi yok).
5. Arka plan bildirimi: **rozet + Windows bildirimi**.
6. Aşamalar **P1→P5 sırayla**, her biri test + commit.
