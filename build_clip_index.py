import argparse
import json
import os
from pathlib import Path
from typing import Iterable, List

import numpy as np
import open_clip
import torch
from PIL import Image

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp"}
DEFAULT_MODEL = os.getenv("CLIP_MODEL", "ViT-B-32")
DEFAULT_PRETRAINED = os.getenv("CLIP_PRETRAINED", "laion2b_s34b_b79k")
DEFAULT_DEVICE = os.getenv("CLIP_DEVICE", "cuda" if torch.cuda.is_available() else "cpu")


def iter_images(root: Path) -> Iterable[Path]:
    if not root or not root.exists():
        return []
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in IMAGE_EXT:
            yield path


def load_model(model_name: str, pretrained: str, device: str):
    model, _, preprocess = open_clip.create_model_and_transforms(model_name, pretrained=pretrained)
    model.eval()
    model.to(device)
    return model, preprocess


def encode_image(model, preprocess, device: str, image_path: Path) -> np.ndarray:
    image = Image.open(image_path).convert("RGB")
    tensor = preprocess(image).unsqueeze(0).to(device)
    with torch.no_grad():
        feats = model.encode_image(tensor)
    feats = feats / feats.norm(dim=-1, keepdim=True)
    return feats.cpu().numpy().astype("float32")[0]


def main() -> None:
    parser = argparse.ArgumentParser(description="Desen görselleri için CLIP index oluşturur")
    parser.add_argument("--desen-root", type=Path, required=True, help="Desen klasörü")
    parser.add_argument("--variant-root", type=Path, help="Varyant klasörü")
    parser.add_argument("--embed-output", type=Path, default=Path("clip_embeddings.npy"))
    parser.add_argument("--meta-output", type=Path, default=Path("clip_metadata.json"))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--pretrained", default=DEFAULT_PRETRAINED)
    parser.add_argument("--device", default=DEFAULT_DEVICE)
    args = parser.parse_args()

    model, preprocess = load_model(args.model, args.pretrained, args.device)
    embeddings: List[np.ndarray] = []
    metadata: List[dict] = []

    roots = [args.desen_root]
    if args.variant_root:
        roots.append(args.variant_root)

    for root in roots:
        for image_path in iter_images(root):
            vector = encode_image(model, preprocess, args.device, image_path)
            embeddings.append(vector)
            rel = image_path.relative_to(root)
            metadata.append(
                {
                    "path": str(image_path),
                    "folder": rel.parts[0] if len(rel.parts) > 1 else root.name,
                    "fileName": image_path.name,
                }
            )

    if not embeddings:
        raise SystemExit("Görsel bulunamadı, index oluşturulamadı")

    stack = np.stack(embeddings).astype("float32")
    np.save(args.embed_output, stack)
    with args.meta_output.open("w", encoding="utf-8") as fh:
        json.dump(metadata, fh, ensure_ascii=False, indent=2)
    print(f"Kaydedildi: {len(metadata)} görsel, {args.embed_output}, {args.meta_output}")


if __name__ == "__main__":
    main()
