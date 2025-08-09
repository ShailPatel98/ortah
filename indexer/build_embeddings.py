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

pc = Pinecone(api_key=PINECONE_API_KEY)

indexes = {i.name: i for i in pc.list_indexes()}
if PINECONE_INDEX not in indexes:
    pc.create_index(
        name=PINECONE_INDEX,
        dimension=1536,
        metric="cosine",
        spec=ServerlessSpec(cloud="aws", region=PINECONE_ENV),
    )
index = pc.Index(PINECONE_INDEX)

client = OpenAI()

def embed_texts(texts: List[str]) -> List[List[float]]:
    embs = []
    B = 64
    for i in range(0, len(texts), B):
        chunk = texts[i:i+B]
        resp = client.embeddings.create(model=OPENAI_MODEL_EMBED, input=chunk)
        embs.extend([d.embedding for d in resp.data])
    return embs

def main():
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        products = json.load(f)

    texts, ids, metas = [], [], []
    for p in products:
        text = "\n".join(filter(None, [p.get("title"), p.get("description"), " ".join(p.get("tags", []))]))
        texts.append(text[:5000])
        ids.append(p["url"])
        metas.append({
            "title": p.get("title"),
            "url": p.get("url"),
            "image": (p.get("images") or [None])[0],
            "tags": ",".join(p.get("tags", [])),
        })

    embs = embed_texts(texts)
    vectors = [{"id": ids[i], "values": embs[i], "metadata": metas[i]} for i in range(len(embs))]
    index.upsert(vectors=vectors, namespace=PINECONE_NAMESPACE)
    print(f"Upserted {len(vectors)} vectors to {PINECONE_INDEX}/{PINECONE_NAMESPACE}")

if __name__ == "__main__":
    main()
