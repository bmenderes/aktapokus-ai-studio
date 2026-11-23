# İki bilgisayar, tek telefon (kendi bilgisayarın + server)

Her kurulum bağımsızdır: kendi adresi, kendi cihaz anahtarları, kendi proje klasörleri. Telefondan ikisini **ayrı sekmelerde** açarsınız. İş aktarma GitHub üzerinden yapılır.

## Bir kez
1. Her iki bilgisayarda ve telefonda Tailscale'e **aynı hesapla** girin.
2. Her bilgisayarda Ayarlar > **Uzak erişim** > "Uzak erişim açık". Durum "dinliyor" olunca "Cihaz ekle" ile telefon için bir anahtar oluşturun ve bağlantıyı (ya da QR'ı) telefonda açın.
   Bağlantı yalnızca bir kez gösterilir ve o telefona özel anahtarı içerir: başka cihazla paylaşmayın; her cihaz için ayrı "Cihaz ekle" yapın.
   Anahtar varsayılan 90 gün geçerlidir; süresi dolmadan yeni anahtar ekleyin. Telefon kaybolursa iki bilgisayarda da o cihazı ✕ ile iptal edin.
3. Telefonda iki bağlantıyı ayrı sekmelerde açın (istersen her biri için "Ana ekrana ekle": iki ayrı simge olur). İsim karışmasın diye tarayıcıda sekmeleri adlandırın ya da yer imine "Ev" / "Server" yazın.

## GitHub (iki bilgisayar, iki ayrı oturum)
- Uygulama GitHub'ı bilgisayarın genel `gh` girişiyle değil kendi oturum klasörüyle (`~/.aktapokus/gh`, kullanıcı klasörünün içinde) kullanır. Aynı bilgisayarda aynı anda tek giriş geçerlidir.
- Server'da birden fazla kişi varsa **her kişi kendi Windows hesabından** Aktapokus'u çalıştırmalı: böylece her birinin oturum klasörü ve GitHub girişi ayrı kalır. Sizin GitHub hesabınız yalnızca sizin Windows hesabınızda açık olur.
- Aynı Windows hesabını birden fazla kişi kullanıyorsa GitHub girişi paylaşılmış olur; bunu yapmayın.

## Akış
1. Bir bilgisayarda çalışın, commit + push (Panel > Git / GitHub).
2. Öbür bilgisayarda aynı projeyi klonlayın ya da `pull` edin.
3. Klasör yolları iki bilgisayarda farklı olabilir; önemli olan GitHub'daki depodur.

## Güvenlik
- İki kurulum birbirine komut göndermez. Her işlemi, ilgili bilgisayarın kendi sekmesinden siz yaparsınız.
- Uzak erişim internete açılmaz; yalnızca Tailscale ağınızdaki cihazlar bağlanır.
