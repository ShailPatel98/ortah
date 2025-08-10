import os
import re
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# --- OpenAI (embeddings) ---
try:
    # new SDK
    from openai import OpenAI
    _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    def embed(text: str) -> List[float]:
        resp = _client.embeddings.create(
            model="text-embedding-3-small",
            input=text.strip()
        )
        return resp.data[0].embedding
except Exception:
    # fallback to legacy import name if needed
    import openai
    openai.api_key = os.getenv("OPENAI_API_KEY")
    def embed(text: str) -> List[float]:
        resp = openai.Embedding.create(
            model="text-embedding-3-small",
            input=text.strip()
        )
        return resp["data"][0]["embedding"]

# --- Pinecone ---
from pinecone import Pinecone

PC = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
INDEX_NAME = os.getenv("PINECONE_INDEX", "ortahaus")
NAMESPACE = os.getenv("PINECONE_NAMESPACE", "prod")
INDEX = PC.Index(INDEX_NAME)

# ---------- FastAPI ----------
app = FastAPI(title="Ortahaus Chat API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten if you want
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Simple in-memory session store ----------
# Note: This resets when the server restarts. Good enough for MVP.
SESSIONS: Dict[str, Dict[str, Any]] = {}

# slot vocab
HAIR_TYPES = ["straight", "wavy", "curly", "coily", "fine", "thick"]
CONCERNS = [
    "volume", "frizz", "hold", "shine", "hydration", "definition", "texture", "control"
]

def find_keyword(text: str, options: List[str]) -> Optional[str]:
    t = text.lower()
    for opt in options:
        # allow simple variations like "frizzy" -> "frizz"
        if opt == "frizz" and ("frizz" in t or "frizzy" in t):
            return "frizz"
        if opt in t:
            return opt
    return None

def get_session(session_id: str) -> Dict[str, Any]:
    if session_id not in SESSIONS:
        SESSIONS[session_id] = {
            "hair_type": None,
            "concern": None,
            "history": []  # [{role:"user"/"assistant", "content": "..."}]
        }
    return SESSIONS[session_id]

def reset_session(session_id: str):
    if session_id in SESSIONS:
        SESSIONS.pop(session_id, None)

# ---------- Models ----------
class ChatRequest(BaseModel):
    session_id: str
    message: str

class ChatResponse(BaseModel):
    reply_html: str
    hair_type: Optional[str]
    concern: Optional[str]

# ---------- Health ----------
@app.get("/healthz")
def healthz():
    return {"ok": True}

# ---------- Helpers ----------
def pinecone_search(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    try:
        v = embed(query)
        result = INDEX.query(
            vector=v,
            top_k=top_k,
            include_metadata=True,
            namespace=NAMESPACE
        )
        # normalize into list of {id, score, metadata}
        hits = []
        for m in getattr(result, "matches", []) or []:
            hits.append({
                "id": m.id,
                "score": float(m.score) if m.score is not None else 0.0,
                "metadata": dict(m.metadata or {})
            })
        return hits
    except Exception as e:
        # keep bot alive even if vector search hiccups
        return []

def format_product_card(meta: Dict[str, Any]) -> str:
    title = meta.get("title") or meta.get("name") or "View product"
    url = meta.get("url") or meta.get("link") or "#"
    how_to_use = (meta.get("how_to_use") or "").strip()
    bullets = meta.get("bullets") or []
    ingredients = (meta.get("ingredients") or "").strip()

    # Make sure link opens in a new tab + is safe
    link_html = f'<a href="{url}" target="_blank" rel="noopener noreferrer">{title}</a>'

    # Human‑y single recommendation
    parts = [f"I’d try <strong>{link_html}</strong>."]
    if how_to_use:
        parts.append(f"<br><em>How to use:</em> {how_to_use}")
    elif bullets and isinstance(bullets, list):
        # show a short highlight if available
        parts.append(f"<br>{bullets[0]}")
    if ingredients:
        parts.append(f"<br><em>Key info:</em> {ingredients}")

    return "".join(parts)

def make_query_text(hair_type: str, concern: str) -> str:
    # steer search toward relevant copy
    return (
        f"Ortahaus product best for hair_type={hair_type}, concern={concern}. "
        "Prefer single hero product. Use metadata fields title, url, how_to_use, ingredients, bullets if present."
    )

def needs_more(reply: str) -> bool:
    # If user asked for 'more', 'another', 'second', etc.
    return bool(re.search(r"\b(more|another|second|else)\b", reply.lower()))

# ---------- Chat ----------
INTRO_PROMPT = (
    "Hi! I’m the Ortahaus Product Guide. I can recommend something based on your hair and goals. "
    "Tell me your hair type and your main concern (e.g., volume, strong hold, frizz control, shine, hydration)."
)

@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    # quick resets
    if req.message.strip().lower() in {"reset", "restart", "start over"}:
        reset_session(req.session_id)
        return ChatResponse(reply_html=INTRO_PROMPT, hair_type=None, concern=None)

    session = get_session(req.session_id)
    user_text = req.message.strip()

    # update known slots if the user volunteered them
    if not session["hair_type"]:
        ht = find_keyword(user_text, HAIR_TYPES)
        if ht:
            session["hair_type"] = ht

    if not session["concern"]:
        cz = find_keyword(user_text, CONCERNS)
        if cz:
            session["concern"] = cz

    # slot-filling: only ask what’s missing
    if not session["hair_type"]:
        return ChatResponse(
            reply_html="Got it! What’s your hair type — straight, wavy, curly, coily, fine, or thick?",
            hair_type=None,
            concern=session["concern"]
        )

    if not session["concern"]:
        return ChatResponse(
            reply_html=(
                "Thanks! What’s the main goal today — volume, frizz control, strong hold, shine, hydration, "
                "definition, texture, or overall control?"
            ),
            hair_type=session["hair_type"],
            concern=None
        )

    # We have both slots → search and recommend
    query = make_query_text(session["hair_type"], session["concern"])

    # If the user also typed extra context (“want matte finish” etc.), add it
    extra = user_text.lower()
    if extra and extra not in {"ok", "thanks", "thank you"}:
        query += f" Extra preferences: {extra}"

    hits = pinecone_search(query, top_k=5)

    if not hits:
        # Graceful fallback
        reply = (
            f"Based on **{session['hair_type']}** hair and **{session['concern']}**, "
            "I’d look at our styling and care best‑sellers. Want me to try again with a different priority "
            "(e.g., ‘more shine’, ‘matte finish’, ‘lighter hold’)?"
        )
        return ChatResponse(reply_html=reply, hair_type=session["hair_type"], concern=session["concern"])

    # Choose the single best hit
    top = hits[0]
    product_html = format_product_card(top.get("metadata", {}))

    # conversational, single rec; we’ll only add more if the user asks
    opener = f"Great — for {session['hair_type']} hair and {session['concern']}, here’s what I’d go with:"
    reply_html = f"{opener}<br><br>{product_html}<br><br>Want a second option or something with a different finish?"

    return ChatResponse(
        reply_html=reply_html,
        hair_type=session["hair_type"],
        concern=session["concern"]
    )
