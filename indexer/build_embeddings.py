# indexer/build_embeddings.py

import os
import json
from typing import List
from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec
from openai import OpenAI

load_dotenv()

# ---- Config from environment ----
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_ENV = os.getenv("PINECONE_ENV", "us-east-1")
PINECONE_INDEX = os.getenv("PINECONE_INDEX", "ortahaus")
PINECONE_NAMESPACE = os.getenv("PINECONE_NAMESPACE", "prod")

OPENAI_MODEL_EMBED = os.getenv("OPENAI_MODEL_EMBED", "text-embedding-3-small")

DATA_PATH = os.path.join("data", "products.json")
EMBED_DIM = 1536  # text-embedding-3-small

# ---- Init clients ----
if not PINECONE_API_KEY:
    raise RuntimeError("PINECONE_API_KEY not set")

pc = Pinecone(api_key=PINECONE_API_KEY)

# Create index if missing, with the correct dimension
existing = {i.name: i for i in pc.list_indexes()}
if PINECONE_INDEX not in existing:
    pc.create_index(
        name=PINECONE_INDEX,
        dimension=EMBED_DIM,
        metric="cosine",
        spec=ServerlessSpec(cloud="aws", region=PINECONE_ENV),
    )

index = pc.Index(PINECONE_INDEX)

client = OpenAI()


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Batch embed texts with OpenAI."""
    out = []
    B = 64
    for i in range(0, len(texts), B):
        chunk = texts[i : i + B]
        resp = client.embeddings.create(model=OPENAI_MODEL_EMBED, input=chunk)
        out.extend([d.embedding for d in resp.data])
    return out


def clean_list_str(x):
    """Ensure list of strings only."""
    if not isinstance(x, list):
        return []
    return [str(t) for t in x if isinstance(t, str) and t.strip()]


def build_vectors(products: List[dict]):
    texts, ids, metas = [], [], []

    for p in products:
        title = (p.get("title") or "").strip()
        desc = (p.get("description") or "").strip()
        tags_list = clean_list_str(p.get("tags") or [])

        # Text used for embedding
        text = "\n".join([title, desc, " ".join(tags_list)]).strip()
        texts.append(text[:5000])

        # Use URL as ID if available
        pid = p.get("url") or f"id-{len(ids)+1}"
        ids.append(pid)

        # Pinecone metadata must be string, number, boolean, or list of strings
        meta = {
            "title": title,
            "url": p.get("url") or "",
        }

        # Only set image if a non-empty string exists
        images = p.get("images") or []
        if isinstance(images, list) and images:
            first_img = images[0]
            if isinstance(first_img, str) and first_img.strip():
                meta["image"] = first_img.strip()

        if tags_list:
            meta["tags"] = tags_list  # list of strings is allowed

        metas.append(meta)

    # Embed and assemble vectors
    embs = embed_texts(texts)
    vectors = [
        {"id": ids[i], "values": embs[i], "metadata": metas[i]}
        for i in range(len(embs))
    ]
    return vectors


def main():
    if not os.path.exists(DATA_PATH):
        raise FileNotFoundError(
            f"{DATA_PATH} not found. Run `python scraper/scrape_ortahaus.py` first."
        )

    with open(DATA_PATH, "r", encoding="utf-8") as f:
        products = json.load(f)

    if not isinstance(products, list) or not products:
        raise ValueError("No products found in products.json")

    vectors = build_vectors(products)

    # Upsert to Pinecone
    index.upsert(vectors=vectors, namespace=PINECONE_NAMESPACE)
    print(
        f"Upserted {len(vectors)} vectors to index '{PINECONE_INDEX}' in namespace '{PINECONE_NAMESPACE}'."
    )


if __name__ == "__main__":
    main()
