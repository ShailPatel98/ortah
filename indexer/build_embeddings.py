import os, json, math
from typing import List, Dict, Any

from openai import OpenAI
from pinecone import Pinecone

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL_EMBED = os.getenv("OPENAI_MODEL_EMBED", "text-embedding-3-small")

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
PINECONE_INDEX = os.getenv("PINECONE_INDEX", "ortahaus")
PINECONE_NAMESPACE = os.getenv("PINECONE_NAMESPACE", "prod")

DATA_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "products.json"))

oai = OpenAI(api_key=OPENAI_API_KEY or None)
pc = Pinecone(api_key=PINECONE_API_KEY or None)
index = pc.Index(PINECONE_INDEX)

def embed(text: str) -> List[float]:
    resp = oai.embeddings.create(model=OPENAI_MODEL_EMBED, input=text)
    return resp.data[0].embedding

def normalize_metadata(md: Dict[str, Any]) -> Dict[str, Any]:
    safe: Dict[str, Any] = {}
    for k, v in md.items():
        if v is None:
            safe[k] = ""  # no nulls
        elif isinstance(v, (str, int, float, bool)):
            safe[k] = v
        elif isinstance(v, list):
            safe[k] = [str(x) for x in v][:32]
        else:
            safe[k] = str(v)[:500]
    return safe

def main():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        items = json.load(f)

    vectors = []
    for it in items:
        body = " ".join([
            it.get("title",""),
            it.get("description",""),
            " ".join(it.get("bullets", [])[:12]),
            f"How to use: {it.get('how_to_use','')}",
            f"Ingredients: {it.get('ingredients','')}",
        ])[:7000]

        vec = embed(body)
        md = normalize_metadata({
            "title": it.get("title",""),
            "url": it.get("url",""),
            "how_to_use": it.get("how_to_use",""),
            "ingredients": it.get("ingredients",""),
            "bullets": it.get("bullets", []),
        })

        vectors.append({
            "id": it.get("id") or it.get("url"),
            "values": vec,
            "metadata": md,
        })

    # Upsert in chunks
    BATCH = 50
    for i in range(0, len(vectors), BATCH):
        chunk = vectors[i:i+BATCH]
        index.upsert(vectors=chunk, namespace=PINECONE_NAMESPACE)
        print(f"Upserted {len(chunk)} vectors to index '{PINECONE_INDEX}' in namespace '{PINECONE_NAMESPACE}'.")

if __name__ == "__main__":
    main()
