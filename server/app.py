import os, json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from pinecone import Pinecone
from openai import OpenAI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

load_dotenv()

OPENAI_MODEL_CHAT = os.getenv("OPENAI_MODEL_CHAT", "gpt-4o-mini")
OPENAI_MODEL_EMBED = os.getenv("OPENAI_MODEL_EMBED", "text-embedding-3-small")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX = os.getenv("PINECONE_INDEX", "ortahaus")
PINECONE_NAMESPACE = os.getenv("PINECONE_NAMESPACE", "prod")
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",")]

pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(PINECONE_INDEX)

client = OpenAI()

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if ALLOWED_ORIGINS != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the simple UI
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
    "You are the Ortahaus Product Guide. Only answer about Ortahaus products. "
    "Always recommend at least two different products, with links. "
    "Ask brief follow-ups if hair info is missing: hair type, main concern, finish/hold."
)

TEMPLATE = (
    "User profile: {profile}\n\n"
    "Top candidate products (JSON):\n"
    "{products}\n\n"
    "Task: Based on the user message, write a short reply that mentions at least 2 different products. "
    "For each product, include a one-line reason and the product URL. Keep it concise and friendly. "
    "If the user asks about non-product topics, refuse and pivot back.\n\n"
    "User message: {message}\n"
)

def embed(text: str):
    return client.embeddings.create(model=OPENAI_MODEL_EMBED, input=text).data[0].embedding

def search_products(query: str, top_k=6):
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
        temperature=0.2,
        max_tokens=350,
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
        "hair_type": body.context.get("hair_type") if body.context else None,
        "concern": body.context.get("concern") if body.context else None,
        "finish": body.context.get("finish") if body.context else None,
    }

    products = search_products(msg)
    if not products:
        return {"reply": "I can help with Ortahaus products. Tell me your hair type and main goal, and I’ll suggest two options."}

    prompt = TEMPLATE.format(
        profile=json.dumps(profile),
        products=json.dumps(products[:6], ensure_ascii=False),
        message=msg,
    )
    text = chat_openai(SYSTEM, prompt)
    return {"reply": text}
