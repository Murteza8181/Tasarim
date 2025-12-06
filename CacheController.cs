using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging;
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Text.Json;

namespace TasarimWeb.Controllers
{
    [ApiController]
    [Route("api/cache")]
    public class CacheController : ControllerBase
    {
        private readonly string _desenRoot;
        private readonly string _varyantRoot;
        private readonly ILogger<CacheController> _logger;

        public CacheController(IConfiguration configuration, ILogger<CacheController> logger)
        {
            _logger = logger;
            _desenRoot = configuration["DesenKlasoru"] ?? string.Empty;
            _varyantRoot = configuration["VaryantKlasoru"] ?? string.Empty;
        }

        [HttpGet("desenler")]
        public IActionResult GetDesenCache([FromQuery] string? folder)
        {
            return ReadCache(_desenRoot, ".desenler_cache.json", "desenler", folder, includeTags: true);
        }

        [HttpGet("varyantlar")]
        public IActionResult GetVaryantCache([FromQuery] string? folder)
        {
            return ReadCache(_varyantRoot, ".varyantlar_cache.json", "varyantlar", folder, includeTags: false);
        }

        private IActionResult ReadCache(string rootPath, string cacheFileName, string sectionName, string? folder, bool includeTags)
        {
            if (string.IsNullOrWhiteSpace(rootPath))
            {
                return StatusCode(500, new { error = $"{sectionName} kök klasörü ayarlanmamış" });
            }

            var cachePath = Path.Combine(rootPath, cacheFileName);
            if (!System.IO.File.Exists(cachePath))
            {
                return NotFound(new { error = "Cache dosyası bulunamadı" });
            }

            try
            {
                using var stream = System.IO.File.OpenRead(cachePath);
                using var doc = JsonDocument.Parse(stream);
                if (!doc.RootElement.TryGetProperty(sectionName, out var section) || section.ValueKind != JsonValueKind.Object)
                {
                    return Ok(Array.Empty<object>());
                }

                var result = new List<object>();
                foreach (var folderEntry in section.EnumerateObject())
                {
                    if (!string.IsNullOrEmpty(folder) && !folderEntry.Name.Equals(folder, StringComparison.OrdinalIgnoreCase))
                    {
                        continue;
                    }

                    foreach (var item in folderEntry.Value.EnumerateArray())
                    {
                        if (!item.TryGetProperty("dosya", out var fileProp))
                        {
                            continue;
                        }

                        var filePath = fileProp.GetString();
                        if (string.IsNullOrWhiteSpace(filePath) || !System.IO.File.Exists(filePath))
                        {
                            continue;
                        }

                        var token = Convert.ToBase64String(Encoding.UTF8.GetBytes(filePath));
                        var fileName = item.TryGetProperty("ad", out var nameProp) ? nameProp.GetString() ?? string.Empty : Path.GetFileName(filePath) ?? string.Empty;
                        var number = item.TryGetProperty("numara", out var numberProp) ? numberProp.GetString() : null;
                        var tags = includeTags && item.TryGetProperty("etiketler", out var tagsProp) ? tagsProp.ToString() : null;

                        var payload = new Dictionary<string, object?>
                        {
                            ["token"] = token,
                            ["fileName"] = fileName,
                            ["folder"] = folderEntry.Name,
                            ["numara"] = number,
                            ["url"] = $"/archive/image?path={Uri.EscapeDataString(token)}"
                        };

                        if (includeTags)
                        {
                            payload["etiketler"] = tags;
                        }

                        result.Add(payload);
                    }

                    if (!string.IsNullOrEmpty(folder))
                    {
                        break;
                    }
                }

                return Ok(result);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Cache dosyası okunamadı: {Path}", cachePath);
                return StatusCode(500, new { error = "Cache okuma hatası" });
            }
        }
    }
}
