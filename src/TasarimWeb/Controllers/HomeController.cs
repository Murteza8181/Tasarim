using Microsoft.AspNetCore.Mvc;

namespace TasarimWeb.Controllers
{
    public class HomeController : Controller
    {
        public IActionResult Index()
        {
            return View();
        }
    }
}
