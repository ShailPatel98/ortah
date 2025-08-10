import os
import re
import json
import time
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, Request, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

import requests

# OpenAI (python SDK v1.x)
from openai import OpenAI

# Pinecone v3
from pinecone import Pinecone

# ---------------- Env ----------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL_CHAT = os.getenv("OPENAI_MODEL_CHAT", "gpt-4o-mini")
OPENAI_MODEL_EMBED = os.getenv("OPENAI_MODEL_EMBED", "text-embedding-3-small")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
PINECONE_INDEX = os.getenv("PINECONE_INDEX", "ortahaus")
PINECONE_NAMESPACE = os.getenv("PINECONE_NAMESPACE", "prod")
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",")]
BASE_URL = os.getenv("BASE_URL", "https://ortahaus.com")

# ---------------- Clients ----------------
oai = OpenAI(api_key=OPENAI_API_KEY or None)
pc = Pinecone(api_key=PINECONE_API_KEY or None)
index = pc.Index(PINECONE_INDEX)

# ---------------- App ----------------
app = FastAPI(title="Ortahaus Product Guide")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if ALLOWED_ORIGINS != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# serve static UI from /web
static_dir = os.path.join(os.path.dirname(__file__), "..", "web")
static_dir = os.path.abspath(static_dir)
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# simple in-memory session store
SESSIONS: Dict[str, Dict[str, Any]] = {}

def get_session(session_id: str) -> Dict[str, Any]:
    if session_id not in SESSIONS:
        SESSIONS[session_id] = {
            "created_at": time.time(),
            "hair_type": None,
            "concern": None,
            "finish_or_hold": None,
            "history": [],
        }
    return SESSIONS[session_id]

@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.get("/ui")
def ui():
    # Lightweight guard to help devs if /static/index.html is missing
    index_path = os.path.join(static_dir, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path, media_type="text/html")
    return HTMLResponse("<h1>UI not found</h1><p>Put your <code>index.html</code> under <code>/web</code>.</p>", status_code=404)

# ---------------- Helpers ----------------

HAIR_TYPES = {"straight","wavy","curly","coily","fine","thick","thin","medium"}
CONCERNS = {
    "volume":"volume",
    "volumize":"volume",
    "hold":"hold",
    "strong hold":"hold",
    "matte":"matte",
    "shine":"shine",
    "gloss":"shine",
    "frizz":"frizz",
    "definition":"definition",
    "hydrate":"hydration",
    "hydration":"hydration",
    "moisture":"hydration",
    "oily":"oil control",
    "greasy":"oil control",
    "sweat":"sweat",
    "texture":"texture",
}

def pick_hair_type(text: str) -> Optional[str]:
    t = text.lower()
    for h in sorted(HAIR_TYPES, key=len, reverse=True):
        if re.search(rf"\\b{re.escape(h)}\\b", t):
            return "thin" if h == "fine" else h
    return None

def pick_concern(text: str) -> Optional[str]:
    t = text.lower()
    for k,v in CONCERNS.items():
        if re.search(rf"\\b{re.escape(k)}\\b", t):
            return v
    return None

def embedding(text: str) -> List[float]:
    resp = oai.embeddings.create(model=OPENAI_MODEL_EMBED, input=text)
    return resp.data[0].embedding

def search_products(query: str, top_k: int = 6) -> List[Dict[str, Any]]:
    vec = embedding(query)
    res = index.query(
        namespace=PINECONE_NAMESPACE,
        vector=vec,
        top_k=top_k,
        include_metadata=True,
    )
    hits = []
    for m in res.matches or []:
        md = m.get("metadata", {}) if isinstance(m, dict) else (m.metadata or {})
        hits.append({
            "id": getattr(m, "id", None) or md.get("url") or "",
            "score": m.get("score") if isinstance(m, dict) else getattr(m, "score", None),
            "title": md.get("title") or "",
            "url": md.get("url") or "",
            "how_to_use": md.get("how_to_use") or "",
            "ingredients": md.get("ingredients") or "",
            "bullets": md.get("bullets") or [],
        })
    return hits

def craft_reply(name: str, url: str, how_to: str = "", ingredients: str = "") -> str:
    link = f'<a href="{url}" target="_blank" rel="noopener" class="rec-link">{name}</a>'
    parts = [f"I'd go with {link}."]
    if how_to:
        parts.append(f"How to use: {how_to.strip()}")
    if ingredients:
        parts.append(f"Key ingredients: {ingredients.strip()}")
    parts.append("Want a different finish or hold? I can tweak the rec.")
    return " ".join(parts)

SYSTEM_PROMPT = (
    "You are the Ortahaus Product Guide. Be concise, friendly, and helpful. "
    "Only recommend a single product when ready. Ask follow-up questions when details are missing. "
    "Never mention that you will recommend 'two' products. Links should be returned as plain text; "
    "the server will format them."
)

# ---------------- Routes ----------------
@app.post("/chat")
async def chat(payload: Dict[str, Any] = Body(...)):
    message = (payload.get("message") or "").strip()
    session_id = payload.get("session_id") or "default"
    state = get_session(session_id)
    state["history"].append({"role": "user", "content": message})

    # Extract signals
    htype = pick_hair_type(message) or state.get("hair_type")
    concern = pick_concern(message) or state.get("concern")
    state["hair_type"] = htype
    state["concern"] = concern

    # Ask for missing info (one at a time)
    if not htype:
        return {"reply": "Got it! What’s your hair type (straight, wavy, curly, or coily)?", "session_id": session_id}
    if not concern:
        return {"reply": "What’s your main goal today—volume, hold, frizz control, hydration, or shine?", "session_id": session_id}

    # We have enough to search
    query = f"Ortahaus product for {htype} hair; primary concern: {concern}. Return best match."
    hits = search_products(query, top_k=5)

    # pick first strong match with a product URL
    candidate = next((h for h in hits if h["url"].startswith("https://")), hits[0] if hits else None)

    # Fallback text if no index yet
    if not candidate:
        return {
            "reply": (
                "I don't see the product index yet. Try running the scraper and indexer, "
                "then ask me again. In the meantime: tell me if you prefer matte or shine?"
            ),
            "session_id": session_id,
        }

    reply = craft_reply(candidate["title"], candidate["url"], candidate.get("how_to_use",""), candidate.get("ingredients",""))
    state["history"].append({"role": "assistant", "content": reply})
    return {"reply": reply, "session_id": session_id, "debug": {"htype": htype, "concern": concern}}
