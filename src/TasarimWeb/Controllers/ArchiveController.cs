using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using System.Text;

namespace TasarimWeb.Controllers
{
    [ApiController]
    [Route("archive")]
    [Authorize]
    public class ArchiveController : ControllerBase
    {
        private readonly IConfiguration _config;

        public ArchiveController(IConfiguration config)
        {
            _config = config;
        }

        [HttpGet("samples")]
        public IActionResult GetSamples([FromQuery] int? take = null, [FromQuery] string? category = null, [FromQuery] string? folder = null)
        {
            var basePath = _config["DesenKlasoru"];
            if (string.IsNullOrWhiteSpace(basePath) || !Directory.Exists(basePath))
                return NotFound(new { error = "Arşiv klasörü bulunamadı" });

            var searchPath = basePath;
            if (!string.IsNullOrWhiteSpace(category))
            {
                searchPath = Path.Combine(basePath, category);
                if (!Directory.Exists(searchPath))
                    return NotFound(new { error = $"Kategori bulunamadı: {category}" });
            }

            if (!string.IsNullOrWhiteSpace(folder))
            {
                searchPath = Path.Combine(searchPath, folder);
                if (!Directory.Exists(searchPath))
                    return NotFound(new { error = $"Klasör bulunamadı: {folder}" });
            }

            var extensions = new[] { ".jpg", ".jpeg", ".png", ".bmp", ".gif" };
            var fileQuery = Directory.EnumerateFiles(searchPath, "*.*", SearchOption.AllDirectories)
                .Where(f => extensions.Contains(Path.GetExtension(f).ToLowerInvariant()));

            if (take.HasValue && take.Value > 0)
            {
                fileQuery = fileQuery.Take(take.Value);
            }

            var files = fileQuery
                .Select(fullPath =>
                {
                    var token = Convert.ToBase64String(Encoding.UTF8.GetBytes(fullPath));
                    var fileName = Path.GetFileName(fullPath);
                    var folderName = Path.GetFileName(Path.GetDirectoryName(fullPath)) ?? "";
                    return new
                    {
                        token,
                        fileName,
                        folder = folderName,
                        url = $"/archive/image?path={Uri.EscapeDataString(token)}"
                    };
                })
                .ToList();

            return Ok(files);
        }

        [HttpGet("image")]
        public IActionResult GetImage([FromQuery] string path)
        {
            if (string.IsNullOrWhiteSpace(path))
                return BadRequest(new { error = "Token eksik" });

            try
            {
                var bytes = Convert.FromBase64String(path);
                var decodedPath = Encoding.UTF8.GetString(bytes);

                if (!System.IO.File.Exists(decodedPath))
                    return NotFound(new { error = "Dosya bulunamadı" });

                var ext = Path.GetExtension(decodedPath).ToLowerInvariant();
                var contentType = ext switch
                {
                    ".jpg" or ".jpeg" => "image/jpeg",
                    ".png" => "image/png",
                    ".gif" => "image/gif",
                    ".bmp" => "image/bmp",
                    _ => "application/octet-stream"
                };

                var fileBytes = System.IO.File.ReadAllBytes(decodedPath);
                return File(fileBytes, contentType);
            }
            catch
            {
                return BadRequest(new { error = "Geçersiz token" });
            }
        }

        [HttpGet("variants")]
        public IActionResult GetVariants([FromQuery] string path, [FromQuery] int? take = null)
        {
            if (string.IsNullOrWhiteSpace(path))
                return BadRequest(new { error = "Token eksik" });

            try
            {
                var bytes = Convert.FromBase64String(path);
                var decodedPath = Encoding.UTF8.GetString(bytes);

                if (!System.IO.File.Exists(decodedPath))
                        return NotFound(new { error = "Dosya bulunamadı" });

                // Ana klasör adını al (ör: "Leopar Desenler")
                var parentFolder = Path.GetFileName(Path.GetDirectoryName(decodedPath));
                
                // Varyant klasörü yolunu oluştur
                var variantBasePath = _config["VaryantKlasoru"];
                if (string.IsNullOrWhiteSpace(variantBasePath) || !Directory.Exists(variantBasePath))
                    return Ok(new List<object>()); // Varyant klasörü yoksa boş liste dön

                // Klasör eşleşmesi: "Leopar Desenler" → "Leopar Desen Varyantları"
                var variantFolderName = parentFolder?.Replace("Desenler", "Desen Varyantları") ?? "";
                var variantFolderPath = Path.Combine(variantBasePath, variantFolderName);
                
                if (!Directory.Exists(variantFolderPath))
                {
                    // Alternatif eşleşme dene
                    variantFolderPath = Directory.EnumerateDirectories(variantBasePath)
                        .FirstOrDefault(d => Path.GetFileName(d).Contains(parentFolder?.Split(' ')[0] ?? "", StringComparison.OrdinalIgnoreCase));
                    
                    if (string.IsNullOrEmpty(variantFolderPath) || !Directory.Exists(variantFolderPath))
                        return Ok(new List<object>());
                }

                // Varyant klasöründeki TÜM görsel dosyaları döndür (kategori bazlı varyantlar)
                var variantQuery = Directory.EnumerateFiles(variantFolderPath)
                    .Where(f => IsImageExtension(f));

                if (take.HasValue && take.Value > 0)
                {
                    variantQuery = variantQuery.Take(take.Value);
                }

                var candidates = variantQuery
                    .Select(f => new
                    {
                        token = Convert.ToBase64String(Encoding.UTF8.GetBytes(f)),
                        fileName = Path.GetFileName(f),
                            folder = Path.GetFileName(variantFolderPath),
                        url = $"/archive/image?path={Convert.ToBase64String(Encoding.UTF8.GetBytes(f))}"
                    })
                    .ToList();

                return Ok(candidates);
            }
            catch
            {
                return BadRequest(new { error = "Geçersiz token" });
            }
        }

        private static bool IsImageExtension(string path)
        {
            var ext = Path.GetExtension(path).ToLowerInvariant();
            return ext == ".jpg" || ext == ".jpeg" || ext == ".png" || ext == ".gif" || ext == ".bmp";
        }

        [HttpGet("folders")]
        public IActionResult GetFolders([FromQuery] string? category = null)
        {
            var basePath = _config["DesenKlasoru"];
            if (string.IsNullOrWhiteSpace(basePath) || !Directory.Exists(basePath))
                return NotFound(new { error = "Arşiv klasörü bulunamadı" });

            var searchPath = basePath;
            if (!string.IsNullOrWhiteSpace(category))
            {
                searchPath = Path.Combine(basePath, category);
                if (!Directory.Exists(searchPath))
                    return NotFound(new { error = $"Kategori bulunamadı: {category}" });
            }

            var folders = Directory.EnumerateDirectories(searchPath, "*", SearchOption.TopDirectoryOnly)
                .Select(Path.GetFileName)
                .Where(name => !string.IsNullOrEmpty(name))
                .ToList();

            return Ok(folders);
        }

        [HttpGet("variants-by-folder")]
        public IActionResult GetVariantsByFolder([FromQuery] string folder, [FromQuery] int? limit = null)
        {
            if (string.IsNullOrWhiteSpace(folder))
                return BadRequest(new { error = "Klasör adı eksik" });

            var variantBasePath = _config["VaryantKlasoru"];
            if (string.IsNullOrWhiteSpace(variantBasePath) || !Directory.Exists(variantBasePath))
                return NotFound(new { error = "Varyant klasörü bulunamadı" });

            var folderPath = Path.Combine(variantBasePath, folder);
            if (!Directory.Exists(folderPath))
                return NotFound(new { error = $"Klasör bulunamadı: {folder}" });

            var extensions = new[] { ".jpg", ".jpeg", ".png" };
            var itemQuery = Directory.EnumerateFiles(folderPath)
                .Where(f => extensions.Contains(Path.GetExtension(f).ToLowerInvariant()));

            if (limit.HasValue && limit.Value > 0)
            {
                itemQuery = itemQuery.Take(limit.Value);
            }

            var items = itemQuery
                .Select(fullPath =>
                {
                    var token = Convert.ToBase64String(Encoding.UTF8.GetBytes(fullPath));
                    var fileName = Path.GetFileName(fullPath);
                    return new
                    {
                        token,
                        fileName,
                        folder,
                        url = $"/archive/image?path={Uri.EscapeDataString(token)}"
                    };
                })
                .ToList();

            return Ok(items);
        }
    }
}
