import json
import asyncio
from pathlib import Path
from typing import List, Dict
from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI(title="Tasarim Tags Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"]
)

TAGS_FILE = Path(__file__).with_name("tags_data.json")
_file_lock = asyncio.Lock()


def _ensure_payload(data: Dict):
    tags = data.get("tags")
    if not isinstance(tags, list):
        tags = []
    clean_tags = []
    seen = set()
    for tag in tags:
        if isinstance(tag, str):
            formatted = tag.strip()
            if formatted and formatted.lower() not in seen:
                seen.add(formatted.lower())
                clean_tags.append(formatted)
    tagged_designs = data.get("taggedDesigns")
    if not isinstance(tagged_designs, dict):
        tagged_designs = {}
    valid = {tag: [] for tag in clean_tags}
    for tag, items in tagged_designs.items():
        if tag not in valid or not isinstance(items, list):
            continue
        dedup = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            token = item.get("token")
            if not isinstance(token, str) or not token:
                continue
            if token in dedup:
                continue
            dedup[token] = {
                "token": token,
                "fileName": item.get("fileName") or "",
                "folder": item.get("folder") or "",
                "numara": item.get("numara")
            }
        valid[tag] = list(dedup.values())
    return {"tags": clean_tags, "taggedDesigns": valid}


async def _load_tags():
    async with _file_lock:
        if not TAGS_FILE.exists():
            return {"tags": [], "taggedDesigns": {}}
        try:
            text = TAGS_FILE.read_text(encoding="utf-8")
            data = json.loads(text)
            return _ensure_payload(data)
        except Exception:
            return {"tags": [], "taggedDesigns": {}}


async def _save_tags(payload: Dict):
    async with _file_lock:
        TAGS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


@app.get("/tags/get")
async def get_tags():
    data = await _load_tags()
    return JSONResponse(data)


@app.post("/tags/save")
async def save_tags(tags: List[str] = Body(...), taggedDesigns: Dict[str, List[dict]] = Body(...)):
    payload = _ensure_payload({"tags": tags, "taggedDesigns": taggedDesigns})
    await _save_tags(payload)
    return {"success": True, "message": "Etiketler kaydedildi"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
