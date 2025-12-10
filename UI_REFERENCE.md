# UI Reference

- The current UI derived from `origin/main` (commit c2fa46b) is the baseline we must keep unless the user explicitly requests a redesign.

## 2025-12-09 · “Benzer Desen Arama” Regresyonu

- **Belirti:** Sağ panelde tek `🔍 Benzer Desen Arama` butonu görünmesi gerekirken üretim ortamında hâlâ `🔍 Arşivden Ara` + `📷 Resimden Ara` çifti render ediliyordu.
- **Neden:** IIS sitesinin fiziksel yolu `C:\inetpub\wwwroot\Tasarim\publish`, yani Razor görünümleri derlenmiş olarak `TasarimWeb.dll` içinde yükleniyor. Daha önce yayınlanan derleme (07.12.2025 tarihli) yeni “iki butonlu” tasarımı içeriyordu; sadece `Views/Home/Index.cshtml` dosyasını değiştirmek bu derlenmiş DLL’i güncellemedi.
- **Teşhis Adımları:**
	- `Invoke-WebRequest http://localhost/ -OutFile response.html` çıktı­sında `Resimden Ara` stringleri bulundu; yerel `.cshtml` dosyasında bu string olmadığından canlı DLL’in eski olduğu anlaşıldı.
	- `Get-Item publish\TasarimWeb.dll` ile dosya tarihi 07.12.2025 olarak görüldü; `dotnet publish` sonrası üretilen DLL’in 09.12.2025 timestamp’i ile karşılaştırıldı.
	- IIS Sitesi (`Get-Website`) fiziksel yolunun gerçekten `publish/` olduğu doğrulandı.
- **Çözüm:** Derlenmiş Razor içeriğini güncellemek için tam yayın prosedürü koşuldu.
	1. `dotnet clean src\TasarimWeb\TasarimWeb.csproj` (hem Debug hem Release) ile `bin/obj` temizlendi.
	2. `dotnet publish src\TasarimWeb\TasarimWeb.csproj -c Release -o publish-temp` çalıştırılarak yeni DLL’ler üretildi (timestamp ve boyutlar 09.12.2025 23:29:26 / 381.952 byte).
	3. IIS uygulama havuzu durduruldu: `Import-Module WebAdministration; Stop-WebAppPool -Name 'TasarimPool'`.
	4. `robocopy publish-temp publish /MIR` ile geçici yayın klasörü canlı `publish/` içine aynalandı (DLL, deps.json, runtimeconfig ve web.config dahil).
	5. Havuz yeniden başlatıldı: `Start-WebAppPool -Name 'TasarimPool'`.
	6. `Invoke-WebRequest http://localhost/ -OutFile response_after.html` ile son çıktı kontrol edildi; `Benzer Desen Arama` stringi bulundu, `Resimden/Arşivden Ara` stringleri kayboldu.
- **Doğrulama:** Tarayıcıda Ctrl+F5 veya `Invoke-WebRequest` komutu ile tek butonlu UI doğrulandı. Gerekirse `response_after.html` dosyası referans alınabilir.
- **Dersler:**
	- `publish/` klasörüne dosya kopyalamak yetmez; Razor viewları runtime’da compile edildiği için her zaman `dotnet publish` sonrası oluşan DLL’i dağıtmak gerekir.
	- `publish-temp` → `publish` kopyasını otomatikleştiren küçük bir PowerShell script’i ileride vakit kazandıracaktır.

- **Kalıcı Önlem:**
	- `Views/Home/Index.cshtml` tek doğruluk kaynağıdır; eski çift butonlu `Index.backup.cshtml` kaldırıldı ve artık derlenemez.
	- `scripts/DeploySingleButtonUI.ps1` script’i `dotnet clean/publish`, IIS havuzu durdurma/başlatma, `publish-temp` → `publish` mirroring ve HTTP doğrulamasını otomatik yapar. Script, HTML’de `Benzer Desen Arama` bulunmazsa veya `Resimden Ara`/`Arşivden Ara` tekrar ortaya çıkarsa süreci hata ile durdurur.
	- Canlı yayın öncesi yalnızca bu script’i çalıştırarak eski UI’nin yanlışlıkla geri dönmesi önlenir: `powershell.exe -ExecutionPolicy Bypass -File scripts/DeploySingleButtonUI.ps1`.

## 2025-12-10 · Etiket Önizleme Tutarlılığı

- **Sorun:** Etiket combobox'ından bir etiket seçildiğinde, galeri doğru şekilde filtreleniyordu fakat ana önizleme hâlâ önceki klasörden kalma görseli gösteriyordu; kullanıcı ilk kartın sağdaki preview alanında görünmesini bekliyor.
- **Çözüm:** `Views/Home/Index.cshtml` içindeki `showTaggedDesigns()` fonksiyonu, etiketli diziyi `state.gallery`'ye atar atmaz ilk geçerli token'ı `setMainPreviewFromItem()` ile ana önizlemeye basıyor; ardından `renderGallery()` sonrası `queuePreviewUpdate()` + `applyPendingPreview()` mekanizması aynı öğeyi DOM ile senkron tutuyor. Ek olarak `focusFirstGalleryItem()` gerekirse film şeridindeki ilk kartı otomatik seçiyor ve `highlightGalleryMainSelection()` bu kartı pembe çerçeveye alıyor.
- **Sonuç:** Etiket sekmesi ile sağ panelin tutarsız görüntü vermesi engellendi; kullanıcı tıkladığı etiketin ilk görselini anında büyük önizlemede görüyor.

- **Alt Klasörler:** Sol paneldeki klasör ve alt klasör seçimleri (pill butonları) için `queuePreviewUpdate(null, true)` tetikleniyor; `renderGallery()` içinde `applyPendingPreview()` aktif listeye göre ilk görseli seçerek hem ana önizlemeyi hem de film şeridindeki işaretlemeyi güncelliyor. Ek olarak pill click handler'ları filtreye uyan ilk kaydı hemen `setMainPreviewFromItem()` ile basıyor, böylece fetch tamamlanmadan önce bile preview doğru görünüyor.
- **Alt Klasörler:** Sol paneldeki klasör ve alt klasör seçimleri (pill butonları) için `queuePreviewUpdate(null, true)` tetikleniyor; `renderGallery()` içinde `applyPendingPreview()` aktif listeye göre ilk görseli seçerek hem ana önizlemeyi hem de film şeridindeki işaretlemeyi güncelliyor. Böylece klasör değişimlerinde eski görsel takılı kalmıyor.
- **Etiketler:** Etiket görünümünde queue mekanizması + `focusFirstGalleryItem()` birlikte çalışıyor; sunucudan dönen ilk token `setMainPreviewFromItem()` ile hemen atanıyor, galeri render sırasında eşleşme bulunamazsa ilk kart otomatik seçiliyor. Bu sayede tag seçimleri varyantlarda olduğu gibi ana önizlemeyi anında güncelliyor.

### Logo Kaynağı

- `~/img/orhan-logo.png` yalnızca kök `wwwroot/img` klasöründe tutulduğu için publish çıktısı üretildiğinde dosya kopyalanmıyordu; `scripts/DeploySingleButtonUI.ps1` çalışınca `/MIR` işlemi logoyu da sildi ve IIS kırık görüntü göstermeye başladı.
- `wwwroot/img` içeriği artık `src/TasarimWeb/wwwroot/img` ile senkronize ediliyor (`robocopy wwwroot\img src\TasarimWeb\wwwroot\img /MIR`). Bu sayede `dotnet publish` PNG/SVG dosyalarını kopyalıyor ve script eski logoyu yanlışlıkla kaldırmıyor.

## 2025-12-10 · Giriş Sayfası Yenilemesi

- **Hedef:** Desen arşivine erişimden önce görülen `Account/Login` ekranı, ana uygulamadaki yeni görsel dil ile eşleşmiyordu ve kullanıcılar güvensiz hissettiğini iletti.
- **Çözüm:** `Views/Account/Login.cshtml` tamamen yeniden tasarlandı; iki panelli sahne, neon benzeri gradientler, Space Grotesk tabanlı tipografi ve mevcut desen/varyant/etiket istatistiklerini vurgulayan hero kartları eklendi. Form tarafında validation mesajları sadeleştirildi, placeholder'lar ve odak stilleri iyileştirildi.
- **Not:** Bu sayfa hâlâ layout'tan bağımsız (`Layout = null`) çalışıyor; değişiklikler yalnızca login view'ını etkiliyor ve uygulamanın diğer bölümlerine dokunmuyor.

## 2025-12-10 · Kimlik Doğrulama Yayına Alma

- **Belirti:** `http://192.168.1.36/` adresi hâlâ doğrudan ana uygulamayı gösteriyordu; `/Account/Login` zorlanmadığı için kullanıcılar oturumsuz erişebiliyordu.
- **Neden 1:** `scripts/DeploySingleButtonUI.ps1` yalnızca `src/TasarimWeb` içindeki `appsettings.json` dosyasını `publish/` klasörüne taşır. `Auth:DefaultUser` bloğu sadece kök `appsettings.json` dosyasında bulunduğundan yayınlanan DLL gerekli kimlik bilgilerini alamadı ve `ISimpleAuthService` sürekli false döndürdü.
- **Neden 2:** Giriş zorunlu hale getirildiğinde `/Account/Login` isteği 500 veriyordu; çünkü Login view dosyası yalnızca kök `Views/Account` dizininde tutulmuş, projeye dahil edilmemişti. Razor runtime dizinde dosya bulamayınca view render edilemedi.
- **Çözüm:**
	- `src/TasarimWeb/appsettings.json` içine `Auth:DefaultUser` ayarları eklendi ve `dotnet publish` sonrası `publish/appsettings.json`'da yer aldığından emin olundu.
	- Eksik `Models/LoginViewModel` tekrar eklendi; `AccountController` derlenirken artık view model bulunuyor.
	- `Views/Account/Login.cshtml` dosyası projedeki `src/TasarimWeb/Views/Account` altına kopyalandı ve Razor'ın `@import` satırını çift `@@` ile escape edecek biçimde düzeltildi.
- **Dağıtım:** `dotnet publish -c Release -o publish-temp` sonrası `Stop-WebAppPool TasarimPool`, `robocopy publish-temp publish /MIR`, `Start-WebAppPool TasarimPool` akışı manuel yürütüldü. Yayın sonrası `Invoke-WebRequest -MaximumRedirection 0 http://localhost/` çıktısı `302 -> /Account/Login` döndürerek giriş zorunluluğunu doğruladı. `http://localhost/Account/Login` isteği artık tasarlanan formu render ediyor.
- **Script Notu:** `scripts/DeploySingleButtonUI.ps1` doğrulama adımında hâlâ `Benzer Desen Arama` metnini arıyor; kimlik doğrulama devrede olduğundan script login sayfasını indiriyor ve regex başarısız oluyor. Script güncellenene kadar yayın sonrası doğrulamayı manuel yapmak gerekiyor (302 ve login HTML kontrolü).

### 2025-12-10 · Login Form Rendering Bug

- **Belirti:** Kullanıcılar formda yazdıkları karakterleri göremiyor, gönderim sonrası herhangi bir hata mesajı çıkmıyordu. HTTP yakalama, view çıktısında `asp-for` / `asp-validation-summary` gibi TagHelper niteliklerinin aynen kaldığını gösterdi; bu yüzden input'lar `name` üretmedi ve model bağlanmadığı için kimlik bilgileri sunucuya hiç ulaşmadı.
- **Neden:** `src/TasarimWeb/Views` klasöründe `_ViewImports.cshtml` bulunmadığından Razor TagHelper'ları kayıtlı değildi. Giriş sayfasını projeye kopyalarken sadece `.cshtml` dosyası taşındı, `_ViewImports` taşınmadığı için MVC nesneleri derlenmedi.
- **Çözüm:** `Views/_ViewImports.cshtml` dosyası eklendi (`@addTagHelper *, Microsoft.AspNetCore.Mvc.TagHelpers`). Ardından yayın tekrar alındı (`dotnet publish ...` + `robocopy`) ve login sayfası artık gerçek `<label for="UserName">`, `<input name="UserName" type="text">` alanları üretiyor. Yanlış şifre gönderildiğinde `Kullanıcı adı veya şifre hatalı.` mesajı `validation-summary-errors` kutusunda görünüyor.
- **Ek:** Input alanlarına `font-weight:600`, `caret-color: var(--accent)` ve daha okunaklı placeholder renkleri eklendi; böylece kullanıcı yazdığı karakteri anında fark ediyor.

## 2025-12-10 · Desen/Varyant Limitlerinin Kaldırılması

- **Talep:** Sağ paneldeki “Desenler” ve “Varyantlar” listelerinde sadece ilk 12 kayıt görünüyordu; ayrıca yeni klasör eklendiğinde UI’da ancak limit içine girerse görünüyordu.
- **Değişiklik:** `ArchiveController` içindeki `GetSamples`, `GetVariants` ve `GetVariantsByFolder` aksiyonları artık isteğe bağlı (`int? take/limit`) parametre kullanıyor. Parametre gönderilmezse LINQ sorgusunda `.Take()` uygulanmıyor ve ilgili klasördeki tüm görseller JSON’a dahil ediliyor.
- **Yeni Klasörler:** API her çağrıda `Directory.EnumerateDirectories/Files` kullandığı için herhangi bir önbellek yok; klasör/dosya eklendiği anda sonraki HTTP isteğinde otomatik listeleniyor. Limit kaldırılması sayesinde yeni gelen kayıtların “ilk 12”ye girip girmediğini beklemek gerekmiyor.
- **Yayın:** Değişiklik sonrası `dotnet publish -c Release -o publish-temp` + `robocopy publish-temp publish /MIR` + `Start-WebAppPool TasarimPool` adımları izlenmeli ki limit kaldırılmış DLL canlıda yerini alsın.
