# Arayüz stilleri (kullanıcının geri bildirimlerinden)

Her yeni arayüz parçası bu kurallara göre yapılır ve değiştirilir. Kural değişirse önce bu belge güncellenir. Amaç: **okunaklı, basit, kullanıcı hiçbir işte zorlanmaz; karmaşıklık mümkün olduğunca az.**

## Biçim
1. **Açıklama yok.** Düğmenin/kutunun altına açıklama cümlesi yazılmaz; ayrıntı `title` ipucunda ya da kapalı bir bölümde.
2. **Tek satır.** Bir satırda durması gereken öğeler her genişlikte tek satırda kalır; sığmazsa yana kayar.
3. **Düğmeler büyümez.** `width:100%`/`flex:1` yok. Tek simgeli düğmeler **yuvarlak** ve sabit boyutlu (22–34 px). Etiketler kısa.
4. **Tekrar yok.** Aynı bilgi iki yerde gösterilmez (örn. değişen dosya listesi yalnız Değişiklikler sekmesinde; akışta "N dosya değişti" tek satır). Her görevde değişmeyen bilgi varsayılan gizli.
5. **Kimlik = baş harfler** (yuvarlak).

## Geri bildirim akışı (görev çıktısı)
- Claude uygulamasındaki gibi: **düz metin** akışı; araç/komut adımları adım başına **tek kapalı satır** ("7 araç adımı", tıklayınca açılır).
- Yanıtın altında küçük **yuvarlak simge** eylemleri (kopyala). Canlı durum **tek satır** (son satır).
- Hata kırmızıdır, başka her şey sakin (gri/krem). Hata mesajı çözümü söyler (örn. desteklenen türleri sayar).

## Yazı
- Yazı tipi: **Lora** (ilk seçenek; yoksa Georgia), **Inter** yedek (2026-10-30: kullanıcı Inter'i keskin ve küçük buldu, Lora istedi; önceki "Inter ilk, Segoe asla" kuralı bununla değişti). Lora dosyaları `web/vendor/Lora/` içinde (Google Fonts değişken TTF, OFL lisansı aynı klasörde). Kod: Cascadia Mono.
- Gövde **15 px**. İkincil metin **en az 12 px**. Başlık en çok 15 px (ayar başlığı), içerik başlıkları 13–14 px. Tek istisna: eşleştirme kodu (18 px). Ağırlık 400/500/600; 700 yok.
- Mobilde `input/textarea/select` 16 px kalır (iOS yakınlaştırmasını önler).

## Renk
- Krem zemin, sarı vurgu. Geniş koyu/siyah ya da yeşil alan yok.

## Süreç
- Her kural **test edilir** (`tests/test_stiller.py` yazı boyutu sınırlarını, `tests/test_sade_akis.py` akış kurallarını korur).
- Eklemeden önce "bunu çıkarsam ne kaybederim?" diye sorulur; cevap "pek bir şey" ise eklenmez.
- Uygulamadan sonra dar (~400 px) ve geniş ekranda tek satır ve taşma kontrol edilir.
