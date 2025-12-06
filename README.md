# Tasarim

Bu uygulama artık tamamen ASP.NET Core (IIS in-process) üzerinde çalışan tek bir servis.

## Mimarî Özet
- `ArchiveController`: tasarım/varyant görsellerini ve klasörleri okur, Base64 token oluşturur.
- `TagsController`: `tags_data.json` içindeki etiketleri yönetir (dosya kilidi ve doğrulama ile).
- `CacheController`: `.desenler_cache.json` ve `.varyantlar_cache.json` dosyalarını UNC köklerinden okuyup JSON döner.
- `Views/Home/Index.cshtml`: istemci tarafı galeriyi, etiket yönetimini ve seçili öğe durumunu yönetir.

## Kurulum
1. `appsettings.json` içindeki `DesenKlasoru` ve `VaryantKlasoru` değerlerini paylaşımlarınıza göre güncelleyin.
2. `tags_data.json` dosyasının IIS uygulama havuzunun yazma iznine sahip olduğundan emin olun.
3. IIS web.config zaten `dotnet TasarimWeb.dll` komutunu kullanır; ek servis/scripts gerekmez.

## API Uç Noktaları
| Metot | Yol | Açıklama |
| --- | --- | --- |
| GET | `/archive/samples` | Klasörlerden örnek görseller döner. |
| GET | `/archive/image` | Base64 token ile görsel getirir. |
| GET | `/archive/variants` | Tokene göre varyant klasörünü listeler. |
| GET | `/archive/folders` | Ana klasördeki klasörleri listeler. |
| GET | `/archive/variants-by-folder` | Belirli varyant klasöründeki görselleri döner. |
| GET | `/api/tags/get` | Etiket verisini okur. |
| POST | `/api/tags/save` | Etiket verisini kaydeder. |
| GET | `/api/cache/desenler` | `.desenler_cache.json` verisini döner (opsiyonel `folder`). |
| GET | `/api/cache/varyantlar` | `.varyantlar_cache.json` verisini döner (opsiyonel `folder`). |

## Güncelleme Notları
- Python FastAPI servisi (`variants_api.py`) ve ilgili çalıştırma scriptleri kaldırıldı.
- Tüm etiket ve cache işlemleri artık ASP.NET tarafında.
- Harici port açmaya gerek kalmadan IIS üzerinden tek servis olarak dağıtım yapılabilir.
