# Otomasyon tasarımı (taslak)

Kullanıcı kararları (2026-10-26): **dört tür de** istendi: zamanlanmış görev, olay tetikleyici, şablon/tekrar eden görev, zincirleme iş akışı. Otomasyon sen yokken çalışsa bile **plan onayı yine istenir** (hiçbir otomasyon onaysız dosya değiştirmez).

## İlkeler

1. **Otomasyon yalnızca plan üretir.** Tetiklenince `gorev_olustur` ile bir PLAN oluşur, Telegram/arayüz bildirimi gelir, sen onaylayınca çalışır. Mevcut görev akışı (onay, anlık görüntü, fark, karar, geri alma) aynen geçerlidir; yeni bir "onaysız çalıştırma yolu" eklenmez.
2. **Tanımlar yalnızca kullanıcı klasöründe** (`~/.aktapokus/otomasyonlar.json`). Proje klasöründen ASLA okunmaz: klonlanan bir depo kendi otomasyonunu getiremez (zehirli depo koruması).
3. **Uygulama çalışırken çalışır.** Zamanlayıcı uygulamanın içindedir; uygulama kapalıyken hiçbir şey tetiklenmez (Windows açılışında otomatik başlatma ayrı bir madde). Kaçırılan zamanlar kayda "kaçırıldı" olarak yazılır, varsayılan olarak geriye dönük çalıştırılmaz.
4. **Birikmez.** Bir otomasyonun önceki planı hâlâ onay bekliyorsa ya da projede görev sürüyorsa yeni tetikleme **atlanır** (kayıtta "atlandı: neden") ve kuyruğa yığılmaz. Proje başına tek görev kuralı aynen kalır.
5. **Sınırlar:** en çok 20 otomasyon, en kısa aralık 5 dakika, otomasyon başına en çok 1 bekleyen plan, otomasyonların toplam günlük token tavanı (Ayarlar'da), her görevin kendi bütçesi zaten geçerli.
6. **Uzak politika:** otomasyon oluşturma/düzenleme/silme = "zamanlanmış çalıştırma tanımlamak" → **yönetim** düzeyi, uzaktan varsayılan KAPALI. "Şimdi çalıştır" (yalnız plan üretir, onay ister) uzaktan serbest. Telegram yalnız bildirir ve "şimdi çalıştır"/şablon komutu verir; **tanımlayamaz**.
7. **Telegram'dan tetiklenen şablonlar** yalnızca KAYITLI şablon adlarını çalıştırır; serbest metin alıp zamanlayamaz.

## Veri modeli

```
Otomasyon: id, ad, proje (proje kimliği), acik,
  tur: "sablon" | "zamanli" | "olay" | "zincir"
  gorev: metin ({tarih}, {saat}, {dal} değişkenleri)  -- sablon/zamanli/olay
  adimlar: [metin, ...]                                 -- zincir (her adım ayrı plan, her biri onay ister)
  zamanlama: {tur: "aralik"|"gunluk"|"haftalik", dakika | saat:dakika | gunler}   -- zamanli
  tetikleyici: {tur: "dosya"|"git"|"issue"|"pr"|"gorev-bitti"|"telegram", ...}      -- olay
  son: {zaman, durum, plan_kimligi}, olusturma
Calisma kaydi: zaman, otomasyon, sonuc ("plan-olustu"|"atlandi"|"kacirildi"|"hata"), neden, gorev kimligi
```

## Aşamalar (her biri ayrı test + mutasyon + commit)

- **A. Şablonlar + "Şimdi çalıştır" — VAR (2026-10-26):** kayıt defteri, doğrulama, değişken doldurma, plan üretme, Ayarlar > Otomasyonlar (CRUD), Telegram `/sablon`, uzak politika.
- **B. Zamanlayıcı:** aralık/günlük/haftalık, enjekte edilebilir saat, çalışma kaydı, kaçırılan politikası, atlama kuralları, günlük token tavanı.
- **C. Zincir:** adım bitince (korundu/değişiklik yok) sonraki adımın planı; hata/geri alma/ret zinciri durdurur ve bildirir.
- **D. Olay tetikleyiciler:** dosya değişimi (imza yoklaması + bekleme süresi), yeni commit/uzak değişiklik (git), yeni issue/PR (`gh` yoklaması; webhook yok, yerel çalışır), "görev bitti".
- **E. Cila:** Telegram bildirimi/komutları, geçmiş görünümü, belgeler, güvenlik gözden geçirmesi.

## Açık riskler (bilerek)

- Tetikleyici metni dışarıdan gelebilir (issue başlığı vb.): metin göreve konurken "güvenilmeyen veri" notuyla sarılır (issue→görev ile aynı kural) ve plan onayı ayrıca korur.
- Sıklıkla çalışan otomasyon token tüketir: günlük tavan ve "atla" kuralı bunu sınırlar; Kullanım sayfasında otomasyon harcaması ayrı görünür (Aşama E).
- Saat dilimi/yaz saati: yerel saat kullanılır; yaz saati geçişinde bir tetikleme kaçabilir (kayıtta görünür).
