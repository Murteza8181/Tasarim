using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using System.Net.Http;
using System.Threading.Tasks;

namespace TasarimWeb.Controllers
{
    [ApiController]
    [Route("healthz")]
    [AllowAnonymous]
    public class HealthController : ControllerBase
    {
        private readonly IHttpClientFactory _httpClientFactory;
        private readonly IConfiguration _config;

        public HealthController(IHttpClientFactory httpClientFactory, IConfiguration config)
        {
            _httpClientFactory = httpClientFactory;
            _config = config;
        }

        [HttpGet]
        public async Task<IActionResult> Get()
        {
            var clipBase = _config["ClipService:BaseUrl"]?.TrimEnd('/') ?? "http://localhost:5000";
            var client = _httpClientFactory.CreateClient();

            try
            {
                var clipResponse = await client.GetAsync($"{clipBase}/healthz");
                if (!clipResponse.IsSuccessStatusCode)
                {
                    return StatusCode(503, new { status = "degraded", clip = clipResponse.StatusCode.ToString() });
                }
            }
            catch
            {
                return StatusCode(503, new { status = "degraded", clip = "unreachable" });
            }

            return Ok(new { status = "ok" });
        }
    }
}
