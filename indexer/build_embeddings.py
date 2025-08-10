#!/usr/bin/env python3
import os
import json
from typing import Any, Dict, List

from openai import OpenAI
from pinecone import Pinecone

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL_EMBED = os.environ.get("OPENAI_MODEL_EMBED", "text-embedding-3-small")

PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY", "")
PINECONE_INDEX = os.environ.get("PINECONE_INDEX", "ortahaus")
PINECONE_NAMESPACE = os.environ.get("PINECONE_NAMESPACE", "prod")

DATA_PATH = "data/products.json"

def sanitize_metadata(md: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in (md or {}).items():
        if v is None:
            continue
        if isinstance(v, (str, int, float, bool)):
            out[k] = v
        elif isinstance(v, list):
            out[k] = [str(x) for x in v if x is not None]
        else:
            out[k] = str(v)
    return out

def combine_text(r: Dict[str, Any]) -> str:
    parts = [
        r.get("title", ""),
        r.get("description", ""),
        "Bullets: " + ", ".join(r.get("bullets", [])),
        "How to use: " + (r.get("how_to_use") or ""),
        "Ingredients: " + (r.get("ingredients") or ""),
        "Tags: " + ", ".join(r.get("tags", [])),
        r.get("url", ""),
    ]
    text = "\n".join([p for p in parts if p]).strip()
    # embeddings API prefers no newlines
    return text.replace("\n", " ")

def main():
    if not os.path.exists(DATA_PATH):
        raise SystemExit(f"Missing {DATA_PATH}. Run the scraper first.")

    with open(DATA_PATH, "r", encoding="utf-8") as f:
        items = json.load(f)

    if not items:
        raise SystemExit("No items to index.")

    oai = OpenAI(api_key=OPENAI_API_KEY)
    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = pc.Index(PINECONE_INDEX)

    vectors = []
    for rec in items:
        _id = rec.get("id") or rec.get("url")
        if not _id:
            continue
        text = combine_text(rec)
        emb = oai.embeddings.create(model=OPENAI_MODEL_EMBED, input=text).data[0].embedding

        meta = sanitize_metadata({
            "title": rec.get("title") or "",
            "url": rec.get("url") or "",
            "description": rec.get("description") or "",
            "image": rec.get("image") or "",
            "price": rec.get("price") or "",
            "bullets": rec.get("bullets") or [],
            "how_to_use": rec.get("how_to_use") or "",
            "ingredients": rec.get("ingredients") or "",
            "tags": rec.get("tags") or [],
        })

        vectors.append({"id": _id, "values": emb, "metadata": meta})

    # Upsert in chunks
    BATCH = 50
    for i in range(0, len(vectors), BATCH):
        chunk = vectors[i:i+BATCH]
        index.upsert(vectors=chunk, namespace=PINECONE_NAMESPACE)
        print(f"Upserted {len(chunk)} vectors to index '{PINECONE_INDEX}' in namespace '{PINECONE_NAMESPACE}'.")

    print("Done.")

if __name__ == "__main__":
    main()
