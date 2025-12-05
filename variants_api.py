import os
import base64
import json
from pathlib import Path
from urllib.parse import quote
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI()

# CORS: IIS üzerinde çalışan site farklı origin'den çağırıyor
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tüm originlere izin ver (network erişimi için)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Ortamdan veya defaulttan root yolu al
VARYANT_ROOT = os.environ.get("VARYANT_KLASORU", r"\\192.168.1.36\TasarımVeSablonuOlanDesenler\VARYANT - Şablonu Olan Desenler")
DESEN_ROOT = os.environ.get("DESEN_KLASORU", r"\\192.168.1.36\TasarımVeSablonuOlanDesenler\Karakoç Tasarımlar")

def encode_path(p: str) -> str:
    # ASP.NET tarafında kullanılan tokenlarla uyumlu olacak şekilde Base64
    try:
        return base64.b64encode(p.encode('utf-8')).decode('ascii')
    except Exception:
        return p

@app.get("/variants-by-folder")
def variants_by_folder(folder: str = Query(...), limit: int = Query(100)):
    folder_path = os.path.join(VARYANT_ROOT, folder)
    if not os.path.isdir(folder_path):
        return JSONResponse({"error": f"Klasör bulunamadı: {folder}"}, status_code=404)
    items = []
    count = 0
    for name in os.listdir(folder_path):
        if not name.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        if count >= limit:
            break
        file_path = os.path.join(folder_path, name)
        token = encode_path(file_path)
        items.append({
            "token": token,
            "fileName": name,
            "folder": folder,
            "url": f"/archive/image?path={quote(token)}"
        })
        count += 1
    return items

@app.get("/cache/desenler")
def get_desenler_cache(folder: str = Query(None)):
    """Desenler cache'ini oku - desktop app tarafından oluşturulan .desenler_cache.json"""
    cache_file = Path(DESEN_ROOT) / ".desenler_cache.json"
    
    if not cache_file.exists():
        return JSONResponse({"error": "Cache dosyası bulunamadı"}, status_code=404)
    
    try:
        with open(cache_file, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        
        desenler = cache_data.get('desenler', {})
        
        # Belirli klasör istendiyse
        if folder and folder in desenler:
            items = []
            for item in desenler[folder]:
                file_path = item.get('dosya', '')
                if file_path and os.path.exists(file_path):
                    token = encode_path(file_path)
                    items.append({
                        "token": token,
                        "fileName": item.get('ad', ''),
                        "folder": folder,
                        "numara": item.get('numara', ''),
                        "etiketler": item.get('etiketler', ''),
                        "url": f"/archive/image?path={quote(token)}"
                    })
            return items
        
        # Tüm desenler
        all_items = []
        for klasor, items_list in desenler.items():
            for item in items_list:
                file_path = item.get('dosya', '')
                if file_path and os.path.exists(file_path):
                    token = encode_path(file_path)
                    all_items.append({
                        "token": token,
                        "fileName": item.get('ad', ''),
                        "folder": klasor,
                        "numara": item.get('numara', ''),
                        "etiketler": item.get('etiketler', ''),
                        "url": f"/archive/image?path={quote(token)}"
                    })
        return all_items
        
    except Exception as e:
        return JSONResponse({"error": f"Cache okuma hatası: {str(e)}"}, status_code=500)

@app.get("/cache/varyantlar")
def get_varyantlar_cache(folder: str = Query(None)):
    """Varyantlar cache'ini oku - desktop app tarafından oluşturulan .varyantlar_cache.json"""
    cache_file = Path(VARYANT_ROOT) / ".varyantlar_cache.json"
    
    if not cache_file.exists():
        return JSONResponse({"error": "Cache dosyası bulunamadı"}, status_code=404)
    
    try:
        with open(cache_file, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        
        varyantlar = cache_data.get('varyantlar', {})
        
        # Belirli klasör istendiyse
        if folder and folder in varyantlar:
            items = []
            for item in varyantlar[folder]:
                file_path = item.get('dosya', '')
                if file_path and os.path.exists(file_path):
                    token = encode_path(file_path)
                    items.append({
                        "token": token,
                        "fileName": item.get('ad', ''),
                        "folder": folder,
                        "numara": item.get('numara', ''),
                        "url": f"/archive/image?path={quote(token)}"
                    })
            return items
        
        # Tüm varyantlar
        all_items = []
        for klasor, items_list in varyantlar.items():
            for item in items_list:
                file_path = item.get('dosya', '')
                if file_path and os.path.exists(file_path):
                    token = encode_path(file_path)
                    all_items.append({
                        "token": token,
                        "fileName": item.get('ad', ''),
                        "folder": klasor,
                        "numara": item.get('numara', ''),
                        "url": f"/archive/image?path={quote(token)}"
                    })
        return all_items
        
    except Exception as e:
        return JSONResponse({"error": f"Cache okuma hatası: {str(e)}"}, status_code=500)

