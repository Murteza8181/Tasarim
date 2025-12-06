using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;

namespace TasarimWeb.Controllers
{
    [Route("api/tags")]
    [ApiController]
    public class TagsController : ControllerBase
    {
        private static readonly SemaphoreSlim FileLock = new(1, 1);
        private readonly string _tagsFilePath;
        private readonly ILogger<TagsController> _logger;
        private readonly JsonSerializerOptions _serializerOptions = new()
        {
            Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
            WriteIndented = true,
            DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull
        };

        public TagsController(IConfiguration configuration, IWebHostEnvironment env, ILogger<TagsController> logger)
        {
            _logger = logger;

            var configuredPath = configuration?["TagsFilePath"];
            if (!string.IsNullOrWhiteSpace(configuredPath))
            {
                _tagsFilePath = Path.IsPathRooted(configuredPath)
                    ? configuredPath
                    : Path.Combine(env.ContentRootPath, configuredPath);
            }
            else
            {
                _tagsFilePath = Path.Combine(env.ContentRootPath, "tags_data.json");
            }
        }

        [HttpGet("get")]
        public async Task<IActionResult> GetTags()
        {
            try
            {
                var payload = await ReadTagsAsync();
                return Ok(payload);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Etiketler okunurken hata oluştu");
                return StatusCode(500, new { error = "Etiketler yüklenemedi" });
            }
        }

        [HttpPost("save")]
        public async Task<IActionResult> SaveTags([FromBody] TagPayload payload)
        {
            if (payload == null)
            {
                return BadRequest(new { error = "Geçersiz istek gövdesi" });
            }

            try
            {
                NormalizePayload(payload);
                await PersistAsync(payload);
                return Ok(new { success = true, message = "Etiketler kaydedildi" });
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Etiketler kaydedilirken hata oluştu");
                return StatusCode(500, new { error = "Etiketler kaydedilemedi" });
            }
        }

        private async Task<TagPayload> ReadTagsAsync()
        {
            await FileLock.WaitAsync();
            try
            {
                if (!System.IO.File.Exists(_tagsFilePath))
                {
                    return TagPayload.Empty();
                }

                await using var stream = System.IO.File.OpenRead(_tagsFilePath);
                var payload = await JsonSerializer.DeserializeAsync<TagPayload>(stream, _serializerOptions)
                              ?? TagPayload.Empty();
                payload.EnsureCollections();
                return payload;
            }
            catch (JsonException jsonEx)
            {
                _logger.LogWarning(jsonEx, "Etiket dosyası bozuk, varsayılan veri ile devam ediliyor");
                return TagPayload.Empty();
            }
            finally
            {
                FileLock.Release();
            }
        }

        private async Task PersistAsync(TagPayload payload)
        {
            await FileLock.WaitAsync();
            try
            {
                var directory = Path.GetDirectoryName(_tagsFilePath);
                if (!string.IsNullOrWhiteSpace(directory))
                {
                    Directory.CreateDirectory(directory);
                }

                await using var stream = System.IO.File.Create(_tagsFilePath);
                await JsonSerializer.SerializeAsync(stream, payload, _serializerOptions);
            }
            finally
            {
                FileLock.Release();
            }
        }

        private static void NormalizePayload(TagPayload payload)
        {
            payload.EnsureCollections();

            var distinctTags = payload.Tags!
                .Where(t => !string.IsNullOrWhiteSpace(t))
                .Select(t => t.Trim())
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .Take(200)
                .ToList();

            payload.Tags!.Clear();
            payload.Tags.AddRange(distinctTags);

            var validTagSet = new HashSet<string>(payload.Tags, StringComparer.OrdinalIgnoreCase);
            var keys = payload.TaggedDesigns!.Keys.ToList();
            foreach (var key in keys)
            {
                if (!validTagSet.Contains(key))
                {
                    payload.TaggedDesigns.Remove(key);
                    continue;
                }

                var designs = payload.TaggedDesigns[key];
                if (designs == null || designs.Count == 0)
                {
                    payload.TaggedDesigns[key] = new List<TaggedDesign>();
                    continue;
                }

                var cleaned = designs
                    .Where(d => d != null && !string.IsNullOrWhiteSpace(d.Token))
                    .GroupBy(d => d!.Token!, StringComparer.Ordinal)
                    .Select(g => g.First()!)
                    .Take(1000)
                    .ToList();

                payload.TaggedDesigns[key] = cleaned;
            }
        }

        public class TagPayload
        {
            public List<string>? Tags { get; set; }
            public Dictionary<string, List<TaggedDesign>>? TaggedDesigns { get; set; }

            [JsonExtensionData]
            public Dictionary<string, JsonElement>? ExtensionData { get; set; }

            public static TagPayload Empty() => new()
            {
                Tags = new List<string>(),
                TaggedDesigns = new Dictionary<string, List<TaggedDesign>>()
            };

            public void EnsureCollections()
            {
                Tags ??= new List<string>();
                TaggedDesigns ??= new Dictionary<string, List<TaggedDesign>>();
            }
        }

        public class TaggedDesign
        {
            public string? Token { get; set; }
            public string? FileName { get; set; }
            public string? Folder { get; set; }
            public string? Numara { get; set; }

            [JsonExtensionData]
            public Dictionary<string, JsonElement>? ExtensionData { get; set; }
        }
    }
}
