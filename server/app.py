import os
import json
import re
from typing import List, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from pinecone import Pinecone
from openai import OpenAI

load_dotenv()

OPENAI_MODEL_CHAT = os.getenv("OPENAI_MODEL_CHAT", "gpt-4o-mini")
OPENAI_MODEL_EMBED = os.getenv("OPENAI_MODEL_EMBED", "text-embedding-3-small")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX = os.getenv("PINECONE_INDEX", "ortahaus")
PINECONE_NAMESPACE = os.getenv("PINECONE_NAMESPACE", "prod")
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",")]

if not PINECONE_API_KEY:
    raise RuntimeError("PINECONE_API_KEY is not set")

pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(PINECONE_INDEX)
client = OpenAI()

app = FastAPI(title="Ortahaus Chatbot API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if ALLOWED_ORIGINS != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the demo UI from /ui and redirect root -> /ui
app.mount("/ui", StaticFiles(directory="web", html=True), name="ui")

@app.get("/")
def root():
    return RedirectResponse(url="/ui")

class ChatIn(BaseModel):
    message: str
    context: dict | None = None

class ChatOut(BaseModel):
    reply: str

SYSTEM = (
    "You are the Ortahaus Product Guide. Only answer about Ortahaus products sold on ortahaus.com. "
    "Be warm, concise, and human. Ask ONE brief follow-up if key info is missing (hair type / main concern / finish-hold). "
    "If there’s a clear best match recommend ONE product; otherwise recommend TWO max. "
    "Return SHORT HTML lines. For each product: "
    "<a href=\"URL\" target=\"_blank\" rel=\"noopener\">Product Name</a> — why it fits. "
    "Optionally add: <span class=\"hint\">How to use: …</span>."
)

TEMPLATE = (
    "User profile (may be None): {profile}\n\n"
    "Candidate products (JSON list, each has title,url,tags plus scraped fields like attributes, bullets, how_to_use, ingredients):\n"
    "{products}\n\n"
    "Task:\n"
    "1) If missing hair info, start with ONE short follow-up question.\n"
    "2) Then recommend ONE best product; if ambiguous recommend TWO max.\n"
    "3) Use the scraped fields to justify (hair type/concern/finish/hold/benefits). Keep it short and human.\n"
    "4) Output HTML only, with one line per product:\n"
    "   <a href=\"URL\" target=\"_blank\" rel=\"noopener\">Product Name</a> — why it fits. <span class=\"hint\">How to use: …</span>\n\n"
    "User message: {message}\n"
)

def embed(text: str) -> List[float]:
    return client.embeddings.create(model=OPENAI_MODEL_EMBED, input=text).data[0].embedding

def search_products(query: str, top_k=8) -> List[Dict[str, Any]]:
    qvec = embed(query)
    res = index.query(
        namespace=PINECONE_NAMESPACE,
        vector=qvec,
        top_k=top_k,
        include_values=False,
        include_metadata=True,
    )
    items = []
    for m in res.matches:
        md = m["metadata"]
        items.append({
            "title": md.get("title"),
            "url": md.get("url"),
            "image": md.get("image"),
            "tags": md.get("tags"),
            # parsed enrichments (may be absent)
            "attributes": md.get("attributes"),
            "bullets": md.get("bullets"),
            "how_to_use": md.get("how_to_use"),
            "ingredients": md.get("ingredients"),
            "score": m.get("score"),
        })
    return items

def chat_openai(system: str, prompt: str) -> str:
    resp = client.chat.completions.create(
        model=OPENAI_MODEL_CHAT,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        temperature=0.4,
        max_tokens=380,
    )
    return resp.choices[0].message.content

@app.get("/healthz")
def health():
    return {"ok": True}

@app.post("/api/chat", response_model=ChatOut)
def chat(body: ChatIn):
    msg = (body.message or "").strip()
    if not msg:
        raise HTTPException(400, "message is required")

    profile = {
        "hair_type": (body.context or {}).get("hair_type"),
        "concern":   (body.context or {}).get("concern"),
        "finish":    (body.context or {}).get("finish"),
    }

    products = search_products(msg)
    if not products:
        return {"reply": "I can help with Ortahaus products. Tell me your hair type and main goal, and I’ll suggest a product."}

    prompt = TEMPLATE.format(
        profile=json.dumps(profile),
        products=json.dumps(products[:8], ensure_ascii=False),
        message=msg,
    )
    text = chat_openai(SYSTEM, prompt)
    return {"reply": text}
