# Tasarim

Bu uygulama artık tamamen ASP.NET Core (IIS in-process) üzerinde çalışan tek bir servis.

## Mimarî Özet
- `ArchiveController`: tasarım/varyant görsellerini ve klasörleri okur, Base64 token oluşturur.
- `TagsController`: `tags_data.json` içindeki etiketleri yönetir (dosya kilidi ve doğrulama ile).
- `CacheController`: `.desenler_cache.json` ve `.varyantlar_cache.json` dosyalarını UNC köklerinden okuyup JSON döner.
- `Views/Home/Index.cshtml`: istemci tarafı galeriyi, etiket yönetimini ve seçili öğe durumunu yönetir.

## Kurulum
1. `appsettings.json` içindeki `DesenKlasoru`, `VaryantKlasoru` ve `ClipService:BaseUrl` değerlerini ortamınıza göre güncelleyin.
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
| POST | `/api/upload` | Yüklenen görseli CLIP servisine iletir ve benzerlik sonuçlarını döner. |
| GET | `/healthz` | CLIP servisini proxy eden sağlık ucu. |

## Güncelleme Notları
- Python FastAPI servisi (`variants_api.py`) ve ilgili çalıştırma scriptleri kaldırıldı.
- Tüm etiket ve cache işlemleri artık ASP.NET tarafında.
- Harici port açmaya gerek kalmadan IIS üzerinden tek servis olarak dağıtım yapılabilir.

## Benzer Desen (CLIP) Servisi
`clip_service.py` ve `build_clip_index.py` dosyaları, Google Lens benzeri sonuçlar üreten hafif bir CLIP servisi sağlar. Servis, 8001 portunda çalışan etiket servisi ile aynı mantıkta Ayrı bir FastAPI uygulaması olarak 5000 portunda koşturulur.

### Gereksinimler
- Python 3.10+ (CPU modunda çalışır, GPU varsa otomatik kullanır)
- `requirements-clip.txt` içindeki paketler (`pip install -r requirements-clip.txt`)
- `DesenKlasoru` ve `VaryantKlasoru` köklerinde erişilebilir görseller

### 1. Embedding indeksini oluşturma
```
py build_clip_index.py --desen-root "E:\\TasarımVeSablonuOlanDesenler\\Karakoç Tasarımlar" \
	--variant-root "E:\\TasarımVeSablonuOlanDesenler\\VARYANT - Şablonu Olan Desenler" \
	--embed-output clip_embeddings.npy --meta-output clip_metadata.json
```
Komut tüm görselleri CLIP ile vektörleyip `clip_embeddings.npy` ve `clip_metadata.json` dosyalarını oluşturur. Bu iki dosya servis tarafından otomatik okunur.

### 2. Servisi çalıştırma (geliştirme)
```
set CLIP_INDEX_PATH=clip_embeddings.npy
set CLIP_METADATA_PATH=clip_metadata.json
set CLIP_PORT=5000
py clip_service.py
```
Uygulama `/healthz`, `/search` ve `/reload` uç noktalarını sunar. `POST /search` form-data içindeki `file` parametresini kullanır ve `all_results` alanına sahip sonuç listesi döner; ASP.NET tarafındaki `/api/upload` aynı şemayı beklediğinden uyumludur.

### 3. Windows hizmeti olarak kurma
1. NSSM ile servis oluşturun:
	 ```
	 nssm install TasarimClipService "C:\\Path\\to\\python.exe"
	 nssm set TasarimClipService AppDirectory "C:\\inetpub\\wwwroot\\Tasarim"
	 nssm set TasarimClipService AppParameters "clip_service.py"
	 nssm set TasarimClipService AppEnvironmentExtra "CLIP_INDEX_PATH=clip_embeddings.npy" "CLIP_METADATA_PATH=clip_metadata.json" "CLIP_PORT=5000"
	 ```
2. Servisi başlatın: `Start-Service TasarimClipService`
3. Sağlık kontrolü: `Invoke-WebRequest http://localhost:5000/healthz`

### 4. IIS üzerinden proxy
Etiket servisinde olduğu gibi, ARR + URL Rewrite kullanarak dış ağdan gelen `/clip/*` isteklerini `http://localhost:5000/*` adresine yönlendirebilirsiniz. Böylece tarayıcı tarafı yalnızca 80 portu üzerinden konuşur.

### 5. ASP.NET entegrasyonu
- `/api/upload` eylemi CLIP servisine `POST /search` çağrısı yapacak şekilde güncellenmelidir.
- `Views/Home/Index.cshtml` içindeki health check `/healthz` uç noktasını kontrol eder, servis ayakta değilse “CLIP Servisi ulaşılamıyor” uyarısını verir.

### Dosyalar
- `clip_service.py`: FastAPI uygulaması, CLIP modeli yüklü, `/search` ve `/reload` uç noktaları içerir.
- `build_clip_index.py`: Klasörleri tarayıp embedding/metadata çıktısı üretir.
- `requirements-clip.txt`: Servis ve indeks scripti için gereken Python paketleri.
