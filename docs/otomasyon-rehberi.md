# Otomasyon rehberi (kendi otomasyonunu kurmak için)

> Güncel, resimli rehber uygulamanın içinde: Ayarlar > Otomasyonlar > **?** (yan çerçevede açılır). Kaynağı `docs/yardim-uret.py`; bu dosya eski özet.

## Tek cümle
Otomasyon = **bir tetikleyici** bir **görev** başlatır, görev bitince **bildirim** gider. Aktapokus hepsini senin onayınla yürütür.

```
[Tetikleyici]  ──▶  [Görev]  ──▶  [Bildirim]
 Elle / Zamanlayıcı   ajan işi      Telegram mesajı
```

## Parçalar ve ne işe yaradıkları
| Parça | Ne yapar | Ayar |
|---|---|---|
| **Tetikleyici** | İşi ne zaman başlatır | Elle (sen "Şimdi çalıştır"a basarsın) ya da Zamanlayıcı (her N dakika, her gün saat X, haftanın günleri) |
| **Görev** | Bir kod ajanının (OpenCode, Claude Code, Mistral…) yapacağı iş; düz metinle yazılır | Görev metni (`{tarih} {saat} {proje} {dal}` değişkenleri), **Model** (boş = projenin rol ayarı) |
| **Bildirim** | Görev bitince Telegram'a mesaj | Mesaj metni (`{proje} {durum} {yanit}` değişkenleri) |

Kurulum: Ayarlar > Otomasyonlar > **+ Add template** → tetikleyiciyi seç → görev düğümüne metni yaz (model seçebilirsin) → görev düğümünün sağındaki **+** ile bildirim ekle → **✓**.

## Arkada ne oluyor (bir otomasyon çalışınca)
1. Zaman gelince (ya da "Şimdi çalıştır") Aktapokus görev metnini değişkenlerle doldurur.
2. Projede **bir PLAN** oluşturur ve **onayını bekler**. Onay vermeden hiçbir şey çalışmaz (otomatik onay ayarı otomasyonu atlatamaz).
3. Onaylayınca görev seçtiğin modelle (ya da projenin rolleriyle) çalışır; değişiklikler için "korunsun mu" sorulur.
4. Görev bitince bildirim düğümündeki metin ({durum}, {yanit} dolu) Telegram'a gider.
5. Her çalışma `Ayarlar > Otomasyonlar > Çalışma geçmişi`ne ve projenin `.aktapokus/kayit` klasörüne yazılır.

## Telegram'ı bağlamak (bir kerelik)
1. Telegram'da **@BotFather**'a yaz → `/newbot` → bir ad ve kullanıcı adı ver → sana bir **token** verir (gizli tut, kimseyle paylaşma).
2. Aktapokus: Ayarlar > **Telegram** > Token alanına yapıştır > **Başlat**. "Uygulama açılınca otomatik başlat"ı açarsan bot hep hazır olur.
3. **Yeni eşleştirme kodu** de; ekranda çıkan mesajı (örn. `/eslestir ab12cd34`) telefonda botuna yaz. Bundan sonra bot yalnızca sana yanıt verir.
4. Telefonda `/projeler` projeleri, `/sablon` kayıtlı otomasyonları gösterir. Telegram'dan otomasyon **tanımlanamaz**, yalnızca kayıtlı olanı çalıştırabilirsin.
Not: `telegram-baslat.bat`'ı ayrıca çalıştırma, aynı token iki yerde çalışırsa Telegram çakışma hatası verir.

## Sınırlar (bilinçli)
- **Her çalışma onay ister.** Zamanlanmış bir görev, sen onaylayana kadar bekler.
- **Uygulama açıkken çalışır.** Kapalıyken kaçan zamanlar "kaçırıldı" olarak yazılır, geriye dönük çalıştırılmaz.
- **Aynı projede aynı anda tek görev.** Başka bir görev sürüyorsa tetikleme "atlandı" olur, kuyruğa girmez.
- **En çok 20 otomasyon**, en kısa aralık 5 dakika, günde en çok 12 zamanlanmış plan.
- **Görev bir kod ajanı işidir.** Dosya okur/yazar/komut çalıştırır. "Şu web sitelerini gez, karşılaştır" gibi işler ajanın internet erişimine bağlıdır; ayrı bir "web topla" düğümü henüz yok.
- **Model seçimi** yalnız görev düğümünde ve tüm rollere birden uygulanır; proje ayarlarını değiştirmez. Model kotası/hesabı yine o modelin sağlayıcısına bağlıdır.
- **Yerel model** (Ollama) seçilebilir; ekran kartı yoksa yavaş çalışır, küçük modeller karmaşık işte zorlanır.
- **Bildirim yalnız Telegram** ve yalnız görev bitince gider; bot çalışmıyorsa gönderilmez, geçmişe "atlandı" yazılır.

## Aklında kalsın: ne hayal edebilirsin?
- "Her sabah 9'da projedeki testleri çalıştır, sonucu Telegram'a yaz" ✔ (zamanlayıcı + görev + bildirim; sabah onay gerekir)
- "Her gece yedek al" ✔ görev olarak yazılabilir, ama onay ister.
- "Onaysız, kendi kendine çalışan rapor" ✘ şu an yok. Salt-okunur raporlar için ayrı izin modeli tasarımda bekliyor (kullanıcı kararı).
- "Mail oku / web topla" ✘ ikinci dilim olarak planlı, henüz yok.
