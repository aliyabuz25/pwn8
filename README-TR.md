# remed1st

GTK4 arayüzlü gerçek iPhone algılama ve limera1n/pwned DFU hazırlık aracı. Kompakt gri pencere evasi0n'in klasik Mac düzenini izler. Demo cihaz modu ve şarj sorgusu/gösterimi yoktur.

## Çalıştırma

`BASLA.command` dosyasına çift tıklayın. Eksik GTK bileşenleri için `KUR.command` kullanılır. Bu çalışma alanındaki Legacy-iOS-Kit'in `ideviceinfo`, `ideviceenterrecovery`, `irecovery` ve Apple Silicon uyumlu `ipwnder` araçları kullanılır. Başka araç klasörü için `REMED1ST_TOOLS_DIR` ayarlanabilir.

Cihaz bağlanınca gerçek model ve iOS sürümü okunur. limera1n destekli modelde **“Click jailbreak to begin.”** yazısı ve **Jailbreak** düğmesi görünür. “Cihaz bilgileri” bağlantısı model kodu, sürüm/derleme, seri, ECID, UDID ve aktivasyon durumunu açar. Cihaz çıkarılınca önceki değerler temizlenir. Recovery/DFU'da yüklü iOS sürümü tahmin edilmez.

## Tek pencereden işlem

**Jailbreak** düğmesi hazırlık, DFU yönlendirmesi, limera1n, hacktivation ve `bootlogo.png` ile geçici açılış aşamalarını başlatır. Ayrı terminal komutu gerekmez. “İşlem ayrıntıları” bağlantısı aşama ve hata geçmişini açar. Teşekkür metni:

> Developed by @aliyabuz25 for a simpler jailbreak experience.
> Special thanks to @geohot, creator of limera1n.

Bu birleşik akış şu anda **iPhone3,1 / iOS 5.1.1 / 9B208** için hazırlanmıştır. Normal modda model ve derleme önceden kontrol edilir; DFU'da sürüm okunamadığı için ramdisk üzerinden diskteki SystemVersion.plist ayrıca doğrulanır. Diğer modellerde birleşik işlem düğmesi kapalıdır.

1. Yerel IPSW, anahtarlar, aktivasyon yaması ve logo hazırlanır; önbellekteki dosyaların SHA256 özetleri kontrol edilir.
2. Normal moddaki cihaz Recovery'ye geçirilir. Power/Home için zamanlamalı DFU yönergeleri gösterilir. Gerçek DFU için fiziksel düğmeler gerekir.
3. Tek DFU cihazı, ECID ve çip kontrolünden sonra `ipwnder -pv` çalışır. PWND zaten doğrulanmışsa exploit tekrarlanmaz.
4. Geçici SSH ramdisk açılır. USB yeniden bağlantısı beklenir; gerektiğinde Type-C çıkar/tak yönergesi pencerede gösterilir. SSH tüneli yalnızca localhost'a ve tek USB cihazına bağlanır.
5. Disk sürümü doğrulanır. `lockdownd` yalnızca IPSW'den alınmış özgün dosyanın SHA256 değeriyle eşleşiyorsa yamalanır. Bilinen yamalı dosya tekrar değiştirilmez; tanınmayan dosyada işlem durur. Özgün dosya telefonda `lockdownd.orig`, aktarım öncesi/sonrası kopyalar Mac'te `backups/` altında korunur. Yeni dosya aktarılıp yeniden okunarak doğrulanmadan asıl dosyanın yerine konmaz.
6. kloader ile DFU geçişi denenir. Olmazsa aynı arayüzde fiziksel DFU yönergelerine dönülür. Ardından özel logo, DeviceTree ve kernel RAM'e gönderilir.
7. Başarı için aynı ECID'li iPhone'un 5.1.1 / 9B208 ile normal açılması ve aktivasyon durumunun doğrulanması gerekir. Yalnızca komutun çalışması başarı sayılmaz.

Özel logo **yalnızca bu açılış içindir**; kalıcı NOR/logo yazımı yapılmaz. Restore, baseband yazımı veya kullanıcı verisi silme adımı yoktur. Bu akış Cydia veya untether kurmaz; mevcut jailbreak'i olan bu cihaz için aktivasyon yaması ve boot sağlar. limera1n'in BootROM desteği, özgün limera1n uygulamasının iOS sürümü desteğinden ayrıdır.

İptal ve pencere kapatma, uygulamanın başlattığı süreci sonlandırır; telefon bulunduğu modda kalabilir. Tamamlanmış aktivasyon yaması iptal edilince kendiliğinden geri alınmaz. Geçici sistemde takılırsa Power + Home ile yeniden başlatılabilir.

## Doğrulama ve sınırlar

Dosya hazırlığı tamamlandı; gerçek USB cihazı iPhone3,1 olarak okundu. GTK pencere kontrolü ve 22 akış testi geçti. Testler yanlış ECID, birden fazla DFU cihazı, macOS USB özellikleri, yanlış disk derlemesi, tanınmayan lockdownd, bozuk aktarımda dosyanın değiştirilmemesi, iptal ve önceden pwned cihazda devam davranışını kapsar.

**Birleşik hacktivation ve özel logo boot akışı fiziksel telefonda uçtan uca henüz denenmedi.** kloader, ramdisk veya USB yeniden bağlantısı başarısız olabilir; arayüz ilgili aşamada durur. Otomatik cihaz izleme ve `--smoke-test` exploit veya sistem dosyası değiştirme işlemi başlatmaz; smoke testinde işlem düğmesi devre dışıdır.

```sh
./BASLA.command --probe-json
./BASLA.command --smoke-test 6
python3 -m unittest discover -s tests -v
```

Exploit günlüğü `logs/limera1n-*.log` altında, dosya yedekleri `backups/` altında tutulur. Hazır boot dosyaları `runtime/boot-iPhone3,1-9B208/manifest.json` ile doğrulanır. Logo değişirse yeniden hazırlanırlar.

## limera1n arşivi ve arka uç

`downloads/limera1n.zip`, Web Archive'dan kurtarıldığını belgeleyen DrWhax/limera1n-mirror deposundan indirildi; resmî bağlantı HTTP 403 verdi. ZIP bütünlüğü kontrol edildi; kaynak ve SHA256 `downloads/manifest.json` içinde. Yayıncı imzasıyla bağımsız kaynak doğrulaması yapılmış değildir.

Arşivdeki orijinal Mac uygulaması i386/32 bit olup bu Apple Silicon Mac'te çalışmaz. Eylem düğmesi bu eski uygulamayı açmaz; Legacy-iOS-Kit'teki native `ipwnder` arka ucuna bağlıdır. GTK/PyGObject ve Homebrew expat kuruludur; başlangıç betiği yeni Python'ın sistem libexpat uyumsuzluğunu yalnızca kendi işlem ortamında çözer.

Kaynaklar:

- https://github.com/dora2ios/ipwnder_lite
- https://github.com/LukeZGD/Legacy-iOS-Kit
- https://www.limera1n.com/
- https://github.com/DrWhax/limera1n-mirror
- https://pygobject.gnome.org/getting_started.html

Tasarım referansları `design/` altında; yerel SVG simgesi `assets/remed-mark.svg` içinde.

Güncel İngilizce kullanım ve kloader düzeltmesi için [README.md](README.md) dosyasına bakın. Güncel başlatıcı START.command, kurulum SETUP.command. kloader dosyaları artık /tmp yerine ramdiskte oluşturulan /remed1st-work dizininde doğrulanır.
