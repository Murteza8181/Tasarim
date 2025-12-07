using Microsoft.AspNetCore.Mvc;
using System.Text;
using System.Web;

namespace Tasarim.Controllers
{
    [ApiController]
    [Route("api/[controller]")]
    public class PdfController : ControllerBase
    {
        // Basit, kütüphanesiz, metin tabanlı minimal PDF üretimi.
        // Gerçek üretim için ileride QuestPDF / iText / DinkToPdf eklenebilir.
        [HttpPost]
        public IActionResult Create([FromBody] PdfRequest request)
        {
            var title = string.IsNullOrWhiteSpace(request.Title) ? "Desen Raporu" : request.Title.Trim();
            var lines = request.Tags ?? Array.Empty<string>();
            var sbText = new StringBuilder();
            sbText.AppendLine(title);
            sbText.AppendLine(new string('-', Math.Min(60, title.Length)));
            if (lines.Length == 0)
                sbText.AppendLine("Etiket yok");
            else
            {
                for (int i = 0; i < lines.Length; i++)
                    sbText.AppendLine($"- {lines[i]}");
            }
            if (!string.IsNullOrWhiteSpace(request.SelectedFileName))
                sbText.AppendLine($"\nSeçili Görsel: {request.SelectedFileName}");
            if (!string.IsNullOrWhiteSpace(request.Category))
                sbText.AppendLine($"Kategori: {request.Category}");
            if (!string.IsNullOrWhiteSpace(request.Folder))
                sbText.AppendLine($"Klasör: {request.Folder}");

            byte[]? imageBytes = null;
            int imgW = 0, imgH = 0;
            // Seçili görsel token'i varsa PDF'e eklemeye çalış
            if (!string.IsNullOrWhiteSpace(request.SelectedToken))
            {
                try
                {
                    var decodedPath = DecodeToken(request.SelectedToken);
                    if (System.IO.File.Exists(decodedPath))
                    {
                        using var fs = System.IO.File.OpenRead(decodedPath);
                        using var ms = new MemoryStream();
                        fs.CopyTo(ms);
                        imageBytes = ms.ToArray();
                        try
                        {
                            using var img = System.Drawing.Image.FromStream(new MemoryStream(imageBytes));
                            imgW = img.Width;
                            imgH = img.Height;
                        }
                        catch { imageBytes = null; }
                    }
                }
                catch { /* token decode sorunları sessiz geç */ }
            }

            // PDF içerik stream'i (görsel + metin)
            var pdfContent = BuildMinimalPdf(sbText.ToString(), imageBytes, imgW, imgH);
            var fileName = $"desen_raporu_{DateTime.UtcNow:yyyyMMdd_HHmmss}.pdf";
            return File(pdfContent, "application/pdf", fileName);
        }

        public class PdfRequest
        {
            public string? Title { get; set; }
            public string[]? Tags { get; set; }
            public string? SelectedFileName { get; set; }
            public string? Category { get; set; }
            public string? Folder { get; set; }
            public string? SelectedToken { get; set; }
        }

        private static byte[] BuildMinimalPdf(string text, byte[]? imageBytes, int imgW, int imgH)
        {
            // PDF koordinatları içinde her satırı aşağı kaydırarak yaz.
            var lines = text.Replace("\r", "").Split('\n');
            var contentBuilder = new StringBuilder();
            contentBuilder.AppendLine("BT");
            contentBuilder.AppendLine("/F1 12 Tf");
            int yStart = 770;
            int y = yStart; // başlangıç (A4 792pt yüksekliğinde)
            bool drawImage = imageBytes != null && imgW > 0 && imgH > 0;
            if (drawImage)
            {
                // Görseli üstte yer açmak için metni biraz aşağı kaydır
                // Görseli sayfanın üstüne yerleştir (maks genişlik 468pt, soldan 72pt)
                int maxWidth = 468; // 612 - 72*2
                double scale = imgW > maxWidth ? (double)maxWidth / imgW : 1.0;
                int drawW = (int)(imgW * scale);
                int drawH = (int)(imgH * scale);
                // İçerik stream'de resim çizimi (q ... Q blok)
                contentBuilder.AppendLine("q");
                contentBuilder.AppendLine($"{drawW} 0 0 {drawH} 72 {yStart - drawH - 20} cm");
                contentBuilder.AppendLine("/Im1 Do");
                contentBuilder.AppendLine("Q");
                y = yStart - drawH - 40; // Metin başlangıç y
            }
            foreach (var line in lines)
            {
                var safe = EscapePdfText(line);
                contentBuilder.AppendLine($"72 {y} Td ({safe}) Tj");
                contentBuilder.AppendLine("T* "); // Text satır feed
                y -= 14; // satır aralığı
                if (y < 40) break; // sayfa alt sınırı (tek sayfa basit)
            }
            contentBuilder.AppendLine("ET");
            var contentStream = contentBuilder.ToString();
            var bytesStream = Encoding.ASCII.GetBytes(contentStream);

            // Nesneler
            var sb = new StringBuilder();
            sb.AppendLine("%PDF-1.4");
            // 1 Catalog
            var obj1 = "1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n";
            // 2 Pages
            var obj2 = "2 0 obj << /Type /Pages /Count 1 /Kids [3 0 R] >> endobj\n";
            // 3 Page (Resources içine font + (opsiyonel) image)
            var resources = drawImage
                ? "<< /Font << /F1 5 0 R >> /XObject << /Im1 6 0 R >> >>"
                : "<< /Font << /F1 5 0 R >> >>";
            var obj3 = $"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources {resources} /Contents 4 0 R >> endobj\n";
            // 4 Contents
            var obj4Header = $"4 0 obj << /Length {bytesStream.Length} >> stream\n";
            var obj4Footer = "\nendstream\nendobj\n";
            // 5 Font
            var obj5 = "5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n";
            // 6 Image (opsiyonel)
            string obj6 = string.Empty;
            if (drawImage)
            {
                // Basit JPEG tespiti: FF D8 FF
                bool isJpeg = imageBytes!.Length > 3 && imageBytes[0] == 0xFF && imageBytes[1] == 0xD8 && imageBytes[2] == 0xFF;
                // Eğer PNG ise yeniden JPEG'e dönüştürmeye çalış (basit)
                if (!isJpeg)
                {
                    try
                    {
                        using var img = System.Drawing.Image.FromStream(new MemoryStream(imageBytes));
                        using var msJ = new MemoryStream();
                        img.Save(msJ, System.Drawing.Imaging.ImageFormat.Jpeg);
                        imageBytes = msJ.ToArray();
                        isJpeg = true;
                    }
                    catch { /* dönüştürülemedi, ham kullanılamaz -> vazgeç */ imageBytes = null; }
                }
                if (isJpeg && imageBytes != null)
                {
                    obj6 = $"6 0 obj << /Type /XObject /Subtype /Image /Width {imgW} /Height {imgH} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length {imageBytes.Length} >> stream\n";
                    obj6 += Encoding.ASCII.GetString(imageBytes) + "\nendstream\nendobj\n"; // binary unsafe ancak basit kullanım için
                }
            }

            sb.Append(obj1); sb.Append(obj2); sb.Append(obj3); sb.Append(obj4Header); sb.Append(contentStream); sb.Append(obj4Footer); sb.Append(obj5); if (!string.IsNullOrEmpty(obj6)) sb.Append(obj6);

            // xref yapısı
            // Basit offset hesaplama:
            var full = sb.ToString();
            var offsets = new List<int>();
            using (var ms = new MemoryStream(Encoding.ASCII.GetBytes(full)))
            using (var reader = new StreamReader(ms))
            {
                int pos = 0;
                string? line;
                while ((line = reader.ReadLine()) != null)
                {
                    if (line.EndsWith(" obj") || line.Contains(" obj <<"))
                        offsets.Add(pos);
                    pos += Encoding.ASCII.GetByteCount(line + "\n");
                }
            }
            // Yöntem sadeleştirilmiş, cross-reference tam doğru olmayabilir; viewer'ların çoğu tolere eder.
            var xrefStart = Encoding.ASCII.GetByteCount(full);
            var xref = new StringBuilder();
            xref.AppendLine("xref");
            xref.AppendLine($"0 {offsets.Count + 1}");
            xref.AppendLine("0000000000 65535 f ");
            foreach (var off in offsets)
                xref.AppendLine(off.ToString("D10") + " 00000 n ");
            xref.AppendLine("trailer << /Size " + (offsets.Count + 1) + " /Root 1 0 R >>");
            xref.AppendLine("startxref");
            xref.AppendLine(xrefStart.ToString());
            xref.AppendLine("%%EOF");

            var finalBytes = Encoding.ASCII.GetBytes(full + xref.ToString());
            return finalBytes;
        }

        private static string EscapePdfText(string raw)
        {
            return raw.Replace("(", "\\(").Replace(")", "\\)").Replace("\\", "\\\\");
        }

        private static string DecodeToken(string token)
        {
            var bytes = Convert.FromBase64String(token);
            return Encoding.UTF8.GetString(bytes);
        }
    }
}
