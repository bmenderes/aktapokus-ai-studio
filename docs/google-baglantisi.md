# Google hesabı bağlantısı (Ayarlar > Bağlayıcılar)

Gmail, Google Takvim ve Google Drive'ı **yalnızca okuma** izniyle bağlar. Kod: `aktapokus_ai_studio/google_giris.py`. Testler: `tests/test_google_giris.py`.

## Kurulum (bir kez, uygulamayı dağıtan kişi)
1. https://console.cloud.google.com > yeni proje.
2. **APIs & Services > Library**: Gmail API, Google Calendar API, Google Drive API'yi etkinleştirin.
3. **OAuth consent screen**: uygulama adı, destek e-postası. Kullanıcı türü *External*. Kapsamlar (yalnızca okuma): `gmail.readonly`, `calendar.readonly`, `drive.readonly`.
4. **Credentials > Create credentials > OAuth client ID > Desktop app**. İndirilen JSON'u `~/.aktapokus/google-istemci.json` olarak kaydedin (Aktapokus bunu önce okur; git'e/kayıtlara/arayüze çıkmaz). Alternatif: Client ID'yi Ayarlar > Bağlayıcılar'daki forma girin.

## Okuma (salt okunur) ve otomasyon
- `google_oku.py`: Gmail (son/aranan e-postalar, sınırlı gövde), Drive (arama, metin dosyası içeriği sınırlı), Takvim (yaklaşan 7 gün). Yalnızca GET.
- Otomasyon tuvalinde **G** düğmesi: Google düğümü (servis + arama); akışta web getir ile birlikte en çok bir veri düğümü. Metin göreve *talimat değil veri* uyarısıyla eklenir; içerik HTTP API'sinden verilmez.
- Testler: `tests/test_google_oku.py` (sahte yerel Google sunucusu).

## Kurulum devamı
   Dağıtımda kimliği her kullanıcıya girdirmemek için ortam değişkeni: `AKTAPOKUS_GOOGLE_ISTEMCI_ID`.
5. Uygulama **Testing** aşamasında en çok 100 test kullanıcısı alır ve girişler 7 günde bir sona erer. Herkese açmak için Google'ın uygulama doğrulaması gerekir
   (Gmail/Drive okuma izinleri "kısıtlı" sayılır; güvenlik değerlendirmesi isteyebilir). Bu süreç Google'dadır, kodla çözülmez.

## Güvenlik tasarımı
- Giriş: OAuth 2.0 masaüstü akışı, **PKCE (S256)**, rastgele `state`, yalnızca `127.0.0.1` üzerinde dinleyen geçici (tek kullanımlık, 5 dk) sunucu, Host denetimi.
- Anahtarlar: yenileme anahtarı ve istemci sırrı **Windows DPAPI** ile şifrelenir (`~/.aktapokus/google-token.json`; yalnızca aynı Windows kullanıcısı açar).
  Windows dışında anahtar saklanmaz (açık metin dosya yazılmaz).
- Anahtarlar arayüze, API yanıtlarına ve günlüğe verilmez. Durum yanıtı yalnızca `{bagli, eposta, baglayicilar}`.
- Yönetim yalnızca bu bilgisayardan: Tailscale/uzak istekler Google bağlantısını kuramaz, koparamaz (`arayuz.py` reddeder).
- İzinler en az ayrıcalıkla: yalnızca okuma, bağlayıcı başına ayrı istenir. Çıkışta Google'a iptal isteği gönderilir, yerel kayıt silinir.
- Çok kullanıcı: her kullanıcı kendi Windows hesabında kendi Google hesabıyla girer; kayıtlar paylaşılmaz.
