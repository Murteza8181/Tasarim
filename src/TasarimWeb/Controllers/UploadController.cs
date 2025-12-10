using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Data.SqlClient;
using System.Text;
using System.Text.Json;

namespace TasarimWeb.Controllers
{
    [ApiController]
    [Route("api/upload")]
    [Authorize]
    public class UploadController : ControllerBase
    {
        private readonly IHttpClientFactory _httpClientFactory;
        private readonly IConfiguration _config;
        private readonly ILogger<UploadController> _logger;
        private readonly string _clipBaseUrl;

        public UploadController(IHttpClientFactory httpClientFactory, IConfiguration config, ILogger<UploadController> logger)
        {
            _httpClientFactory = httpClientFactory;
            _config = config;
            _logger = logger;
            _clipBaseUrl = config["ClipService:BaseUrl"]?.TrimEnd('/') ?? "http://localhost:5000";
        }

        [HttpPost]
        public async Task<IActionResult> Post(IFormFile file, [FromQuery] int topK = 8)
        {
            if (file == null || file.Length == 0)
            {
                return BadRequest(new { error = "Dosya seçilmedi" });
            }

            try
            {
                using var ms = new MemoryStream();
                await file.CopyToAsync(ms);
                ms.Position = 0;

                var content = new MultipartFormDataContent();
                var streamContent = new StreamContent(ms);
                streamContent.Headers.ContentType = new System.Net.Http.Headers.MediaTypeHeaderValue(file.ContentType ?? "application/octet-stream");
                content.Add(streamContent, "file", file.FileName);

                var client = _httpClientFactory.CreateClient();
                var url = $"{_clipBaseUrl}/search?top_k={Math.Max(1, topK)}";
                var response = await client.PostAsync(url, content);
                var payload = await response.Content.ReadAsStringAsync();
                if (!response.IsSuccessStatusCode)
                {
                    _logger.LogWarning("CLIP servisi hata döndürdü: {Status} - {Body}", response.StatusCode, payload);
                    return StatusCode((int)response.StatusCode, payload);
                }

                try
                {
                    using var json = JsonDocument.Parse(payload);
                    var topPath = ExtractTopPath(json.RootElement);
                    if (!string.IsNullOrWhiteSpace(topPath))
                    {
                        _ = Task.Run(() => TryLogToSqlAsync(topPath!));
                    }
                }
                catch (JsonException jsonEx)
                {
                    _logger.LogWarning(jsonEx, "CLIP yanıtı parse edilemedi");
                }

                var contentType = response.Content.Headers.ContentType?.ToString() ?? "application/json";
                return Content(payload, contentType, Encoding.UTF8);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "CLIP servisine yükleme başarısız");
                return StatusCode(500, new { error = "Benzerlik servisine ulaşılamadı", detail = ex.Message });
            }
        }

        private static string? ExtractTopPath(JsonElement root)
        {
            if (root.ValueKind == JsonValueKind.Array && root.GetArrayLength() > 0)
            {
                return ExtractTopPath(root[0]);
            }

            if (root.ValueKind == JsonValueKind.Object)
            {
                if (root.TryGetProperty("path", out var pathEl))
                {
                    return pathEl.GetString();
                }
                if (root.TryGetProperty("token", out var tokenEl))
                {
                    return tokenEl.GetString();
                }
                if (root.TryGetProperty("best", out var bestEl))
                {
                    return ExtractTopPath(bestEl);
                }
                if (root.TryGetProperty("results", out var resultsEl) && resultsEl.ValueKind == JsonValueKind.Array && resultsEl.GetArrayLength() > 0)
                {
                    return ExtractTopPath(resultsEl[0]);
                }
            }

            return null;
        }

        private async Task TryLogToSqlAsync(string imagePath)
        {
            try
            {
                var connStr = _config.GetConnectionString("Default");
                if (string.IsNullOrWhiteSpace(connStr)) return;

                await using var conn = new SqlConnection(connStr);
                await conn.OpenAsync();
                await using var cmd = new SqlCommand(
                    "INSERT INTO SearchLog (SearchDate, ImagePath) VALUES (GETDATE(), @path)",
                    conn
                );
                cmd.Parameters.AddWithValue("@path", imagePath);
                await cmd.ExecuteNonQueryAsync();
            }
            catch (Exception ex)
            {
                _logger.LogDebug(ex, "SearchLog kaydedilemedi");
            }
        }
    }
}
