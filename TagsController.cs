using Microsoft.AspNetCore.Mvc;
using System.Net.Http;
using System.Threading.Tasks;
using System.Text;
using System.IO;

namespace TasarimWeb.Controllers
{
    [Route("api/tags")]
    [ApiController]
    public class TagsController : ControllerBase
    {
        private readonly IHttpClientFactory _clientFactory;
        // Python servisi sunucu içinde lokal çalışır
        private const string PythonServiceUrl = "http://127.0.0.1:8001/tags";

        public TagsController(IHttpClientFactory clientFactory)
        {
            _clientFactory = clientFactory;
        }

        [HttpGet("get")]
        public async Task<IActionResult> GetTags()
        {
            var client = _clientFactory.CreateClient();
            try 
            {
                var response = await client.GetAsync($"{PythonServiceUrl}/get");
                if (response.IsSuccessStatusCode)
                {
                    var content = await response.Content.ReadAsStringAsync();
                    return Content(content, "application/json");
                }
                return StatusCode((int)response.StatusCode);
            }
            catch
            {
                return StatusCode(503, "Etiket servisine erişilemiyor");
            }
        }

        [HttpPost("save")]
        public async Task<IActionResult> SaveTags()
        {
            using var reader = new StreamReader(Request.Body);
            var body = await reader.ReadToEndAsync();
            
            var client = _clientFactory.CreateClient();
            var content = new StringContent(body, Encoding.UTF8, "application/json");
            
            try
            {
                var response = await client.PostAsync($"{PythonServiceUrl}/save", content);
                if (response.IsSuccessStatusCode)
                {
                    var responseContent = await response.Content.ReadAsStringAsync();
                    return Content(responseContent, "application/json");
                }
                return StatusCode((int)response.StatusCode);
            }
            catch
            {
                return StatusCode(503, "Etiket servisine erişilemiyor");
            }
        }
    }
}
