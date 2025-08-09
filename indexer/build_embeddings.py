# indexer/build_embeddings.py

import os, json
from typing import List
from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec
from openai import OpenAI

load_dotenv()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_ENV = os.getenv("PINECONE_ENV", "us-east-1")
PINECONE_INDEX = os.getenv("PINECONE_INDEX", "ortahaus")
PINECONE_NAMESPACE = os.getenv("PINECONE_NAMESPACE", "prod")
OPENAI_MODEL_EMBED = os.getenv("OPENAI_MODEL_EMBED", "text-embedding-3-small")

DATA_PATH = os.path.join("data", "products.json")
EMBED_DIM = 1536

if not PINECONE_API_KEY:
    raise RuntimeError("PINECONE_API_KEY not set")

pc = Pinecone(api_key=PINECONE_API_KEY)

# Ensure index exists with correct dim
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
    out = []
    B = 64
    for i in range(0, len(texts), B):
        chunk = texts[i:i+B]
        resp = client.embeddings.create(model=OPENAI_MODEL_EMBED, input=chunk)
        out.extend([d.embedding for d in resp.data])
    return out

def list_str(lst):
    return [str(x) for x in (lst or []) if isinstance(x, str) and x.strip()]

def build_vectors(products: List[dict]):
    texts, ids, metas = [], [], []

    for p in products:
        title = (p.get("title") or "").strip()
        desc = (p.get("description") or "").strip()
        bullets = list_str(p.get("bullets"))
        attrs = p.get("attributes") or {}
        how_to = (p.get("how_to_use") or "").strip()
        ingred = (p.get("ingredients") or "").strip()

        # Build a semantically rich text blob for retrieval
        attr_text = " ".join([
            " ".join(list_str(attrs.get("hair_type") or [])),
            " ".join(list_str(attrs.get("concern") or [])),
            " ".join(list_str(attrs.get("finish") or [])),
            " ".join(list_str(attrs.get("hold") or [])),
        ]).strip()

        text = "\n".join(filter(None, [
            title, desc, attr_text, " | ".join(bullets), f"How to use: {how_to}" if how_to else "", f"Ingredients: {ingred}" if ingred else ""
        ]))

        texts.append(text[:6000])
        ids.append(p.get("url") or f"id-{len(ids)+1}")

        meta = {
            "title": title,
            "url": p.get("url") or "",
        }
        img = None
        imgs = p.get("images") or []
        if isinstance(imgs, list) and imgs:
            img = imgs[0]
        if img:
            meta["image"] = img

        # Store structured bits as lists of strings (Pinecone requirement)
        meta["tags"] = list_str(p.get("tags"))
        meta["bullets"] = bullets
        meta["how_to_use"] = how_to or ""
        meta["ingredients"] = ingred or ""
        # attributes as "key:value" strings
        attr_lines = []
        for k, vs in (attrs or {}).items():
            for v in (vs or []):
                if isinstance(v, str) and v.strip():
                    attr_lines.append(f"{k}:{v}")
        if attr_lines:
            meta["attributes"] = attr_lines

        metas.append(meta)

    embs = embed_texts(texts)
    vectors = [{"id": ids[i], "values": embs[i], "metadata": metas[i]} for i in range(len(embs))]
    return vectors

def main():
    if not os.path.exists(DATA_PATH):
        raise FileNotFoundError("data/products.json not found. Run the scraper first.")
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        products = json.load(f)
    if not isinstance(products, list) or not products:
        raise ValueError("No products found in products.json")

    vectors = build_vectors(products)
    index.upsert(vectors=vectors, namespace=PINECONE_NAMESPACE)
    print(f"Upserted {len(vectors)} vectors to index '{PINECONE_INDEX}' in namespace '{PINECONE_NAMESPACE}'.")

if __name__ == "__main__":
    main()
