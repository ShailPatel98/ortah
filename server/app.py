# server/app.py
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ===== Env =====
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL_CHAT = os.getenv("OPENAI_MODEL_CHAT", "gpt-4o-mini")
OPENAI_MODEL_EMBED = os.getenv("OPENAI_MODEL_EMBED", "text-embedding-3-small")

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
PINECONE_ENV = os.getenv("PINECONE_ENV", "us-east-1")
PINECONE_INDEX = os.getenv("PINECONE_INDEX", "ortahaus")
PINECONE_NAMESPACE = os.getenv("PINECONE_NAMESPACE", "prod")

BASE_URL = os.getenv("BASE_URL", "https://ortahaus.com")
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",")]
PORT = int(os.getenv("PORT", "8000"))

# ===== Paths =====
THIS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = THIS_DIR.parent
WEB_DIR = PROJECT_ROOT / "web"  # <— uses your existing /web folder

# ===== App =====
app = FastAPI(title="Ortahaus Chat API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if ALLOWED_ORIGINS == ["*"] else ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve /web assets under /static so index.html can load widget.js, etc.
if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

# ----- Models -----
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    user_context: Optional[Dict[str, Any]] = None

# ----- Health -----
@app.get("/healthz")
def health():
    return {"ok": True}

# ----- UI -----
@app.get("/ui")
def ui():
    """
    Serves the chatbot UI from /web/index.html.
    The page should reference assets with /static/*, e.g. /static/widget.js
    """
    index_path = WEB_DIR / "index.html"
    if not index_path.exists():
        return JSONResponse(
            {"detail": "UI not found. Put your index.html under /web."}, status_code=404
        )
    return FileResponse(str(index_path))

# ----- Chat Endpoint -----
# Minimal working example that just echoes with a friendly prefix.
# (Keeps the route stable while you iterate on retrieval later.)
@app.post("/chat")
async def chat(req: ChatRequest):
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not set")

    user_text = ""
    for m in reversed(req.messages):
        if m.role.lower() == "user":
            user_text = m.content.strip()
            break

    reply = (
        "Hi! I’m the Ortahaus Product Guide. "
        "Tell me your hair type and your main concern (e.g., volume, frizz, shine, hold), "
        "and I’ll recommend the best single product. "
        f"You said: {user_text}"
    )

    return {"reply": reply}

# ----- Root -----
@app.get("/")
def root():
    return {"ok": True, "ui": "/ui", "chat": "/chat"}

# ----- Run (local) -----
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=PORT, reload=True)
