# Güvenlik denetimi (uygulama güvenliği, saldırgan gözüyle)

Kapsam: uzak erişim ve kimlik doğrulama, dosya yolu geçişi, komut/argüman enjeksiyonu, SSRF, gizli bilgi sızıntısı, Google bağlantısı, çoklu sohbet,
otomasyon, Telegram, beceri indirme, OPC UA / ağ aracı, HTTP sunucusu ve arayüz XSS'i. Her bulgunun regresyon testi
`tests/test_guvenlik_denetimi.py` içindedir (bulgu numarası test adında: `test_g01_...`). Bu belge sır, gerçek yol veya kimlik bilgisi içermez.

## Özet

| No | Önem | Bulgu | Durum |
|----|------|-------|-------|
| G-00 | Yüksek (kullanılabilirlik) | Dinleyici kurulurken ters DNS sorgusu arayüzü kilitliyordu; uzak erişim testleri doğrulanamıyordu | Düzeltildi |
| G-01 | Yüksek | Gizli dosya denetimi istenen ada bakıyordu: `ENV~1`, `x.pem.`, `x.pem ` ile `.env`/anahtar dosyaları okunabiliyordu | Düzeltildi |
| G-02 | Orta | Yayın (`yayin.py`) Windows junction'ı izliyordu: proje dışı dosyalar herkese açık depoya kopyalanabilirdi | Düzeltildi |
| G-03 | Orta | Rol `model`/`agent` değeri CLI'ya argüman olarak gidiyordu: `-` ile başlayan değer seçenek enjeksiyonu | Düzeltildi |
| G-04 | Düşük | Web getir: yavaş damlatan sunucu işi sonsuza kadar tutabiliyordu | Düzeltildi |
| G-05 | Orta | Prompt injection: e-posta/web metni "VERİ BİTİŞ" satırını taklit edip veri bloğundan çıkabiliyordu | Düzeltildi |
| G-06 | Orta | İstek çerçevelemesi: gövdede `Transfer-Encoding`, negatif/yinelenen `Content-Length` kabul ediliyordu (request smuggling, bloke eden okuma) | Düzeltildi |
| G-07 | Orta | Depo yapılandırmasındaki `core.fsmonitor=<komut>` Aktapokus'un `git status` çağrısında çalışırdı (ajan korumalarının dışında kod çalıştırma) | Düzeltildi |
| K-01 | Orta | Uzak kimlik doğrulamalı istemci GitHub'a push / PR / Git yıkıcı işlemleri yapabilir (politika kara listesi) | Düzeltildi (2026-11-01): yönetim izni ister |
| K-02 | Orta | Uzak istemci görev verip onaylayabilir (= ajan aracılığıyla bu bilgisayarda kod çalıştırma) | **Karar bekliyor** |
| K-03 | Düşük | Kara liste politikası: yeni uç eklendiğinde varsayılan izinli | Düzeltildi (2026-11-01): `uzak.UZAK_BILINEN_UCLAR` dışındaki uç reddedilir, eşitlik testi var |
| K-04 | Düşük | Ağ aracı yazan işlemlerinde (IP değiştirme, BOOTP) sunucu tarafı ikinci onay yok | **Karar bekliyor** |
| K-05 | Düşük | Ajan alt süreçleri kullanıcının tüm ortam değişkenlerini devralır | Kısmen (2026-11-01): Aktapokus'un `AKTAPOKUS_*` sırları çıkarıldı; CLI anahtarları gerektiği için geçer |
| K-06 | Bilgi | OpenCode koruyucusunun kabuk kuralları yalnız desen eşleştirmesidir (kendi belgesinde belirtilmiş) | Bilinen sınır |

## G-00 — Dinleyici kurulurken ters DNS kilitlenmesi (Bölüm A: bozuk uzak erişim testlerinin kök nedeni)

`http.server.HTTPServer.server_bind` her bağlanışta `socket.getfqdn(host)` çağırır. Windows'ta `127.0.0.1` dışındaki adreslerde (Tailscale `100.x`,
test için `127.0.0.2`) bu ters DNS/NetBIOS sorgusu saniyelerce sürebilir. Uzak dinleyici yerel arayüzün istek iş parçacığında kurulduğundan
`POST /api/uzak` yanıtı gecikiyor, istemci `TimeoutError` alıyor, kapanışta kalan daemon iş parçacıkları
`Fatal Python error ... daemon threads` hatasına yol açıyordu. Aralıklıdır (sorgu önbelleğe/ağa bağlı), bu yüzden aynı test bazen geçiyordu.
Bu gerçek bir uygulama hatasıydı: kullanıcı da Tailscale adresine bağlanırken arayüzün birkaç saniye donmasını yaşayabilirdi.

Düzeltme: `YerelSunucu` (ad araması yapmayan `server_bind`); yerel arayüz, önizleme ve uzak dinleyici bunu kullanır.
Doğrulama: `tests/test_uzak.py` (60 test: Host/Origin/anahtar/yetki daraltma/akışların kesilmesi dahil) artık kararlı geçer; yani uzak kimlik doğrulaması bu testlerle
gerçekten doğrulanıyor. Regresyon: `test_dinleyici_kurarken_ters_dns_sorgusu_yapilmaz`.
Ayrıca `test_arayuz_uzak_erisim_bolumu_ve_telefon_duzeni` testinin kesme işareti dosya sonuna kadar uzanıp sonradan eklenen sabit simge tablosunu
(`innerHTML`) kapsıyordu; kesme `uzakBolumu` gövdesine daraltıldı (denetim gevşetilmedi).

## G-01 — Gizli dosya denetimi çözülmüş yola bakmıyordu (Yüksek)

`guvenli_goreli` yalnızca istenen ad parçalarını `gizli_mi` ile denetliyordu. Windows'ta `ENV~1` (8.3 kısa ad) `.env`, `a.pem.` ve `a.pem ` (sondaki nokta/boşluk)
`a.pem` dosyasına çözülür; proje içindeki bir sembolik bağlantı da gizli dosyayı gösterebilir. `GET /api/dosya`, önizleme sunucusu ve fark uçları bu yolu kullanır;
deneyle doğrulandı: `ENV~1` → `.env`.
Düzeltme: yol çözüldükten sonra proje köküne göre gerçek ad parçaları yeniden `gizli_mi` ile denetlenir.

## G-02 — Yayında junction kaçışı (Orta)

`yayin.dosyalari_listele`, `Path.is_symlink()` ile sembolik bağlantıları atlıyordu; Windows junction'ları (`mklink /J`, ayrıcalık gerektirmez) `is_symlink()` ile görünmez.
Deneyle doğrulandı: junction altındaki proje dışı dosya yayın listesine giriyordu. Ardından kural tabanlı tarama, yapay zeka denetimi ve kullanıcı onayı vardır,
ama içeriğin hiç listeye girmemesi gerekir. Düzeltme: gerçek yol kaynak kökünün dışına çıkan klasör/dosya atlanır.

## G-03 — Model/agent değeri ile seçenek enjeksiyonu (Orta)

`PUT /api/ayar` (uzaktan da izinli) rol `model`/`agent` alanlarını yalnızca "boş olmayan metin" diye doğruluyordu; bunlar CLI'ya `--model <değer>` / `--agent <değer>` olarak gider.
`-` ile başlayan ya da kontrol karakteri içeren değerler reddedilir (ayar yüklemede ve görev başına model seçiminde).

## G-04 — Web getir yavaş damlatma (Düşük)

Her okuma 10 sn zaman aşımı alıyor, toplam süre sınırsızdı. Toplam 30 sn sınırı eklendi; `read1` kullanılır (`read(n)` n bayt dolana kadar bloklar).
SSRF savunması (genel IP zorunluluğu, doğrulanan IP'ye bağlanma, elle yönlendirme izleme, yalnız 80/443) incelendi, sorun bulunmadı.

## G-05 — Veri bloğu ayırıcısı taklidi (Orta)

Google (Gmail/Drive/Takvim) ve web verisi göreve `--- ... VERİSİ BAŞLANGIÇ/BİTİŞ ---` ile sarılıp "talimat değil veri" uyarısı eklenir. Ancak e-posta/sayfa metni
`--- GOOGLE GMAIL VERISI BITIS ---` satırını içerirse blok erken kapanıyor, sonrası güvenilir talimat gibi görünüyordu. Güvenilmeyen metindeki `---` dizileri kısaltılır.
Bu bir azaltmadır (modelin talimat/veri ayrımı olasılıksaldır); asıl koruma otomasyon planının onay istemesi ve ajanın klasör sınırıdır.

## G-06 — HTTP çerçeveleme (Orta)

Sunucu `Transfer-Encoding: chunked` gövdesini okumaz; veri sonraki istek sanılırdı (Tailscale `serve` gibi bir vekilin arkasında request smuggling/desenkronizasyon).
Negatif `Content-Length` doğrulanmış istemcide `rfile.read(-n)` ile bağlantı kapanana kadar bloklardı. Artık gövdede `Transfer-Encoding`, yinelenen ya da
sayısal olmayan `Content-Length` 400 ile reddedilir ve bağlantı kapanır. Uzak dinleyicide boşta bağlantılara 300 sn okuma zaman aşımı konuldu.

## G-07 — `core.fsmonitor` ile kod çalıştırma (Orta)

Bir deponun `.git/config` dosyasında `core.fsmonitor=<komut>` varsa (klonlanan depo ya da proje klasöründe çalışan bir ajanın yazdığı dosya) Aktapokus'un yaptığı
`git status/diff/add` çağrıları bu komutu çalıştırır; yani ajanın klasör/izin sınırının dışında, kullanıcı yetkisiyle. Tüm Aktapokus git çağrılarına komut satırından
`-c core.fsmonitor=false` eklendi (komut satırı yapılandırması depo yapılandırmasını geçersiz kılar). `core.sshCommand`, `core.hooksPath` gibi diğer
yapılandırma/kanca yolları kullanıcının meşru ayarlarını bozabileceğinden değiştirilmedi (bkz. K-05 ve aşağıdaki öneri).

## İncelenen ve sorun bulunmayan alanlar

- **Uzak kimlik doğrulama:** Host/Origin yalnız dinleyici adreslerinden, anahtar/belirteç `hmac.compare_digest`, uzak anahtar yerel dinleyicide geçmez, `/api/uzak*` uzaktan kapalı,
  dinleyici yalnız Tailscale/loopback adresine bağlanır (`0.0.0.0` reddedilir), kapatma/anahtar yenileme açık akışları keser. Testlerle doğrulandı.
- **DNS rebinding / CSRF:** Yerel Host yalnız `127.0.0.1`/`localhost` + port; durum değiştiren isteklerde Origin denetimi; tüm `/api/` uçları özel başlıkla belirteç ister (tarayıcı çapraz kaynaktan gönderemez).
- **XSS:** `md()` önce HTML'i kaçışlar, bağlantılar yalnız `http(s)://`/`#`, tırnaklar kodlanır; `innerHTML` yalnız `md()` çıktısı ve sabit simge tablosunda; GitHub/yayın bağlantıları şema/host denetiminden geçer.
- **Komut enjeksiyonu:** `shell=True` yok; git yolları `--literal-pathspecs` ve `--pathspec-from-file` ile; dal adları `[A-Za-z0-9]` ile başlar; ağ aracı adaptör adını yerel adaptör listesiyle eşler, `netsh` argüman listesiyle çağrılır; CLI tanımları `.cmd/.bat/.ps1` reddeder.
- **Beceri indirme:** yalnız iki sabit host, yönlendirme izlenmez, kaynak ve yol desenleri sıkı, yalnız `SKILL.md`.
- **Google:** PKCE (S256) + `state` (sabit süreli karşılaştırma, tek kullanımlık, 5 dk), yalnız `127.0.0.1` geri dönüşü, yenileme anahtarı/istemci sırrı DPAPI ile, durum çıktısında anahtar yok, yalnız `*.readonly` izinler, Google uçları uzaktan değiştirilemez.
- **Çoklu sohbet:** sohbet kimliği `sohbetler.json` listesine karşı doğrulanır; proje bağlamı kayıtlı projelere (`/api/p/<10 hex>`) bağlıdır.
- **Telegram:** tek kullanımlık eşleştirme kodu, 5 yanlışta kilit, belirteç hata metinlerinde maskelenir, geri çağrılar yalnız özel sohbette ve izinli kullanıcıdan.
- **OPC UA:** yazma/metod çağrısı kodu yok (okuma, gezme, abonelik). **BOOTP:** yalnız açıkça atanmış MAC'lere yanıt verir.
- **Ekler:** yalnız izinli uzantılar, rastgele alt klasör, `resolve()` ile kök denetimi, geri okuma yalnız `.aktapokus/ekler/` altı ve katı desen.

## Kullanıcı kararı bekleyenler (tasarım kararı gerektirir, değiştirilmedi)

**K-01 — Uzaktan GitHub push/PR/Git yıkıcı işlemleri.** `uzak.politika` kara listedir. `POST /api/github/push`, `/api/github/pr`, `/api/github/dal`, `/api/git/degisiklik-at`,
`/api/git/pull`, `/api/git/birlestir`, `/api/git/dal-sil` yönetim kapalıyken de uzaktan çalışır (testlerde `/api/github/commit` bilerek izinli). Gönderme öncesi
kontrol akışı vardır ama onayı aynı uzak istemci verebilir. Öneri: push/PR/değişiklik-at/dal-sil'i `YONETIM_KAPALIYKEN_YASAK` listesine almak.

**K-02 — Uzaktan görev verme ve onaylama.** Tasarım gereği uzak istemci görev verip planı onaylayabilir; bu, ajan üzerinden bu bilgisayarda dosya yazma ve komut çalıştırma demektir
(ajan izinleri `acceptEdits`/sandbox ile sınırlı). Anahtarı ele geçiren herkes Tailscale ağı içinde bu yetkiyi kazanır. Öneri: "uzaktan onay" için ayrı bir anahtar (varsayılan kapalı)
ya da uzaktan verilen görevlerin planını yalnız yerel arayüzden onaylanabilir yapmak.

**K-03 — Kara liste yerine izin listesi.** Yeni bir `/api/...` ucu eklendiğinde uzaktan varsayılan olarak erişilebilir olur. Öneri: uzak politikayı izin listesine (yalnız bilinen güvenli uçlar) çevirmek;
bu, mevcut uçların hepsinin elden geçirilmesini gerektirdiğinden yapılmadı. Mevcut kara listeyi tamamlayan bir "uç listesi eşitliği" testi eklenebilir.

**K-04 — Ağ aracında ikinci onay.** `/api/ag/adaptor-ip`, `adaptor-dhcp`, `bootp/*` yalnız yerel belirteçle korunur (uzaktan yönetim kapalıyken reddedilir); onay iletişim kutusu arayüzdedir,
sunucu tarafında tek kullanımlık onay yoktur. Belirteci ele geçiren yerel bir süreç IP değiştirebilir. Öneri: durum değiştiren ağ işlemleri için sunucu tarafı tek kullanımlık onay belirteci.

**K-05 — Ajan ortamı ve depo yapılandırması.** Ajan alt süreçleri kullanıcının tüm ortam değişkenlerini devralır (CLI'lar API anahtarlarını bu yolla okur). Git için ek sertleştirme
(`core.hooksPath`, `core.sshCommand`, `credential.helper` yok sayma) kullanıcının meşru ayarlarını bozabilir. Öneri: yalnız izinli ortam değişkenlerini aktaran bir "temiz ortam" seçeneği ve
güvenilmeyen depolar için git yapılandırmasını yok sayan bir kip.

**K-06 — OpenCode kabuk kuralları** yalnızca desen eşleştirmesidir (`guard.py` belgesi); tam yalıtım için konteyner/sanal makine gerekir.

## Bilinçli olarak yapılmayanlar / sınırlar

- `google_giris.py` geri dönüş sunucusu `http.server.HTTPServer` kullanır; yalnız `127.0.0.1`'e bağlandığı için ters DNS gecikmesi görülmez, değiştirilmedi (başka oturumun dosyası).
- Windows ayrılmış aygıt adları (`CON`, `NUL`) ek adı olarak yazılabilir; yalnız hata/boş dosya üretir, güvenlik etkisi yok.
- Tam test takımında `tests/test_web_getir.py` içindeki iki test (Google veri düğümü mesajı, arayüz parçası) bu denetimden bağımsız, Google bağlantısı çalışmasından kalmadır.
