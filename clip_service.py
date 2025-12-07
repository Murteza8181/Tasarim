import asyncio
import base64
import io
import json
import os
from pathlib import Path
from typing import List, Optional

import numpy as np
import open_clip
import torch
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image

INDEX_EMBED_PATH = Path(os.getenv("CLIP_INDEX_PATH", "clip_embeddings.npy"))
INDEX_META_PATH = Path(os.getenv("CLIP_METADATA_PATH", "clip_metadata.json"))
MODEL_NAME = os.getenv("CLIP_MODEL", "ViT-B-32")
MODEL_PRETRAINED = os.getenv("CLIP_PRETRAINED", "laion2b_s34b_b79k")
BATCH_SIZE = int(os.getenv("CLIP_BATCH", "32"))
TOP_K_DEFAULT = int(os.getenv("CLIP_TOP_K", "8"))
DEVICE = os.getenv("CLIP_DEVICE", "cuda" if torch.cuda.is_available() else "cpu")


def _make_token(path: str) -> str:
    return base64.b64encode(path.encode("utf-8")).decode("ascii")


class ClipIndexer:
    def __init__(self) -> None:
        self._model: Optional[torch.nn.Module] = None
        self._preprocess = None
        self._lock = asyncio.Lock()
        self._embeddings: Optional[np.ndarray] = None
        self._meta: List[dict] = []

    def _load_model(self) -> None:
        if self._model is not None:
            return
        model, _, preprocess = open_clip.create_model_and_transforms(
            MODEL_NAME, pretrained=MODEL_PRETRAINED
        )
        model.eval()
        model.to(DEVICE)
        self._model = model
        self._preprocess = preprocess

    def _ensure_index(self) -> None:
        if not INDEX_EMBED_PATH.exists() or not INDEX_META_PATH.exists():
            raise FileNotFoundError(
                "Embedding veya metadata dosyası bulunamadı. build_clip_index.py çalıştırın."
            )
        self._embeddings = np.load(INDEX_EMBED_PATH).astype("float32")
        with INDEX_META_PATH.open("r", encoding="utf-8") as fh:
            self._meta = json.load(fh)
        if self._embeddings.shape[0] != len(self._meta):
            raise RuntimeError("Embedding ve metadata sayıları eşleşmiyor")

    async def reload(self) -> None:
        async with self._lock:
            self._embeddings = None
            self._meta = []
            self._load_model()
            self._ensure_index()

    async def ensure_ready(self) -> None:
        if self._model is None or self._preprocess is None:
            self._load_model()
        if self._embeddings is None:
            await self.reload()

    def _encode_image(self, data: bytes) -> np.ndarray:
        if self._model is None or self._preprocess is None:
            raise RuntimeError("Model hazır değil")
        image = Image.open(io.BytesIO(data)).convert("RGB")
        tensor = self._preprocess(image).unsqueeze(0).to(DEVICE)
        with torch.no_grad():
            feats = self._model.encode_image(tensor)
        feats = feats / feats.norm(dim=-1, keepdim=True)
        return feats.cpu().numpy().astype("float32")[0]

    def search(self, vector: np.ndarray, top_k: int) -> List[dict]:
        if self._embeddings is None:
            raise RuntimeError("Index hazır değil")
        top_k = max(1, min(top_k, self._embeddings.shape[0]))
        scores = self._embeddings @ vector
        idx = np.argpartition(-scores, top_k - 1)[:top_k]
        sorted_idx = idx[np.argsort(-scores[idx])]
        results = []
        for i in sorted_idx:
            meta = self._meta[i]
            results.append(
                {
                    "path": meta["path"],
                    "token": meta.get("token") or _make_token(meta["path"]),
                    "folder": meta.get("folder"),
                    "fileName": meta.get("fileName"),
                    "score": float(scores[i]),
                }
            )
        return results


indexer = ClipIndexer()
app = FastAPI(title="Tasarim CLIP Service", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)


@app.on_event("startup")
async def startup_event() -> None:
    await indexer.ensure_ready()


@app.get("/healthz")
async def healthz() -> dict:
    status = "ok"
    message = ""
    try:
        await indexer.ensure_ready()
    except Exception as exc:
        status = "error"
        message = str(exc)
    return {"status": status, "message": message}


@app.post("/search")
async def search_endpoint(
    file: UploadFile = File(...),
    top_k: int = TOP_K_DEFAULT
) -> dict:
    await indexer.ensure_ready()
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Dosya boş")
    try:
        vector = indexer._encode_image(data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Embedding üretilemedi: {exc}") from exc
    try:
        results = indexer.search(vector, top_k)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Arama hatası: {exc}") from exc
    return {"results": results, "all_results": results}


@app.post("/reload")
async def reload_endpoint() -> dict:
    await indexer.reload()
    return {"status": "reloaded", "count": len(indexer._meta)}


if __name__ == "__main__":
    port = int(os.getenv("CLIP_PORT", "5000"))
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=port)
