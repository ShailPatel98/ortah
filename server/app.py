import os
import json
import uuid
import re
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Body, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from pydantic import BaseModel

# --- OpenAI (chat + embeddings) ---
from openai import OpenAI

# --- Pinecone ---
from pinecone import Pinecone

# =========================
# Environment
# =========================
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL_CHAT = os.environ.get("OPENAI_MODEL_CHAT", "gpt-4o-mini")
OPENAI_MODEL_EMBED = os.environ.get("OPENAI_MODEL_EMBED", "text-embedding-3-small")

PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY", "")
PINECONE_ENV = os.environ.get("PINECONE_ENV", "us-east-1")  # not required for serverless v2 but kept
PINECONE_INDEX = os.environ.get("PINECONE_INDEX", "ortahaus")
PINECONE_NAMESPACE = os.environ.get("PINECONE_NAMESPACE", "prod")

BASE_URL = os.environ.get("BASE_URL", "https://ortahaus.com")
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",")]
PORT = int(os.environ.get("PORT", "8000"))

# =========================
# App
# =========================
app = FastAPI(title="Ortahaus Chat")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static UI
if not os.path.isdir("static"):
    os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def root():
    # Redirect to /ui
    return HTMLResponse('<meta http-equiv="refresh" content="0; url=/ui">')

@app.get("/ui")
def ui():
    index_path = os.path.join("static", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h1>UI not found</h1><p>Put your index.html under /static.</p>", status_code=200)

@app.get("/healthz")
def healthz():
    return {"ok": True}

# =========================
# Clients
# =========================
if OPENAI_API_KEY:
    oai = OpenAI(api_key=OPENAI_API_KEY)
else:
    oai = None

pc = Pinecone(api_key=PINECONE_API_KEY)
idx = pc.Index(PINECONE_INDEX)

# =========================
# Simple in-memory session
# =========================
# NOTE: This resets on redeploy. If you want persistence, swap for Redis.
SESSION_STORE: Dict[str, Dict[str, Any]] = {}

def get_session(session_id: Optional[str]) -> str:
    if session_id and session_id in SESSION_STORE:
        return session_id
    new_id = str(uuid.uuid4())
    SESSION_STORE[new_id] = {"history": [], "facts": {}}
    return new_id

# =========================
# RAG helpers
# =========================
def sanitize_metadata(meta: Dict[str, Any]) -> Dict[str, Any]:
    """ Pinecone requires string/number/bool or list of strings. No nulls. """
    out: Dict[str, Any] = {}
    for k, v in (meta or {}).items():
        if v is None:
            continue
        if isinstance(v, (str, int, float, bool)):
            out[k] = v
        elif isinstance(v, list):
            # only lists of strings allowed
            out[k] = [str(x) for x in v if x is not None]
        else:
            # coerce to string
            out[k] = str(v)
    return out

def embed_text(text: str) -> List[float]:
    if not oai:
        raise RuntimeError("OpenAI client not configured.")
    text = text.replace("\n", " ")
    emb = oai.embeddings.create(model=OPENAI_MODEL_EMBED, input=text)
    return emb.data[0].embedding

def pinecone_search(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    v = embed_text(query)
    res = idx.query(
        namespace=PINECONE_NAMESPACE,
        vector=v,
        top_k=top_k,
        include_metadata=True,
    )
    # v5 returns dict-like results with "matches"
    matches = getattr(res, "matches", None) or res.get("matches", [])
    out = []
    for m in matches:
        md = sanitize_metadata(m.get("metadata") or {})
        out.append({
            "id": m.get("id"),
            "score": float(m.get("score", 0.0)),
            "metadata": md
        })
    return out

def format_product_card(m: Dict[str, Any]) -> str:
    md = m["metadata"]
    title = md.get("title") or "Product"
    url = md.get("url") or BASE_URL
    desc = md.get("description") or ""
    price = md.get("price")
    price_txt = f" – ${price}" if price else ""
    # open in new tab
    return f'<a href="{url}" target="_blank" rel="noopener noreferrer"><strong>{title}</strong></a>{price_txt}<br/>{desc}'

# =========================
# Prompting / Chat flow
# =========================
SYSTEM_PROMPT = (
    "You are the Ortahaus Product Guide. Talk like a helpful retail associate: concise, friendly, no fluff.\n"
    "Collect only missing info, then make a single confident recommendation.\n"
    "If the user already gave enough info (hair type and main concern), recommend one product.\n"
    "If you are not sure, ask one follow-up question, then recommend.\n"
    "When referencing products, prefer using the exact product titles from context documents.\n"
    "Always keep your answers short (2–5 sentences)."
)

WELCOME_MESSAGE = (
    "Hi! I’m the Ortahaus Product Guide. Tell me your hair type and your top concern "
    "(e.g., volume, frizz, shine, or hold), and I’ll recommend the best product."
)

class ChatIn(BaseModel):
    session_id: Optional[str] = None
    message: str

class ChatOut(BaseModel):
    session_id: str
    reply_html: str

@app.get("/welcome")
def welcome():
    return {"message": WELCOME_MESSAGE}

@app.post("/chat", response_model=ChatOut)
def chat(body: ChatIn):
    session_id = get_session(body.session_id)
    session = SESSION_STORE[session_id]

    user_msg = (body.message or "").strip()
    session["history"].append({"role": "user", "content": user_msg})

    # Simple fact extraction for hair type / concern based on user text (quick rules)
    facts = session.setdefault("facts", {})
    # Extract hair type if mentioned
    hair_types = ["straight", "wavy", "curly", "coily", "fine", "thick"]
    if "hair_type" not in facts:
        for ht in hair_types:
            if re.search(rf"\b{ht}\b", user_msg, re.I):
                facts["hair_type"] = ht
                break
    # Extract main concern
    concerns = ["volume", "frizz", "shine", "hold", "hydration", "definition", "control", "oily", "dry"]
    if "concern" not in facts:
        for c in concerns:
            if re.search(rf"\b{c}\b", user_msg, re.I):
                facts["concern"] = c
                break

    # Decide whether to ask or answer
    missing: List[str] = []
    if "hair_type" not in facts:
        missing.append("hair type")
    if "concern" not in facts:
        missing.append("main concern")

    if missing:
        # Ask for only one missing thing at a time
        ask = missing[0]
        reply = f"Got it. What is your {ask}?"
        session["history"].append({"role": "assistant", "content": reply})
        return ChatOut(session_id=session_id, reply_html=reply)

    # We have both hair_type and concern: search Pinecone and recommend one product
    search_query = f"{facts['hair_type']} hair {facts['concern']} best product site:{BASE_URL}"
    results = pinecone_search(search_query, top_k=4)

    # Build a compact answer using OpenAI with the snippets for tone, but guard if OpenAI down.
    context_snippets = []
    for m in results:
        md = m["metadata"]
        snippet = f"TITLE: {md.get('title','')}\nURL: {md.get('url','')}\nDESC: {md.get('description','')}\nBULLETS: {', '.join(md.get('bullets', [])[:5])}\n"
        context_snippets.append(snippet)
    context = "\n---\n".join(context_snippets) if context_snippets else ""

    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"User hair type: {facts['hair_type']}\n"
        f"User main concern: {facts['concern']}\n\n"
        f"Context (top products):\n{context}\n\n"
        f"Write a short recommendation (2–5 sentences). Mention exactly one product by its exact title "
        f"and why it fits. Do not invent details."
    )

    try:
        ai = oai.chat.completions.create(
            model=OPENAI_MODEL_CHAT,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.6,
        )
        text = ai.choices[0].message.content.strip()
    except Exception:
        # Fallback if OpenAI has a transient issue
        if results:
            top = results[0]
            text = (
                f"For {facts['hair_type']} hair and {facts['concern']}, try "
                f"{top['metadata'].get('title','this product')}. "
                f"It matches what you asked for. "
            )
        else:
            text = "I couldn’t find a match right now. Could you share a bit more about the style or finish you want?"

    # Add a clean HTML product link to open in new tab
    link_html = ""
    if results:
        best = results[0]
        link_html = f"<p>{format_product_card(best)}</p>"

    reply_html = f"<p>{text}</p>{link_html}"
    session["history"].append({"role": "assistant", "content": reply_html})

    return ChatOut(session_id=session_id, reply_html=reply_html)
