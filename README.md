# Ortahaus Chatbot — OpenAI + Pinecone (Railway-ready)

Recommends **Ortahaus** products only, always returns **at least two** product links.

## Stack
- Scraper: Python + BeautifulSoup (uses sitemap and Shopify `/products/<handle>.js` when available)
- Vector store: Pinecone (serverless)
- Embeddings: OpenAI `text-embedding-3-small` (1536 dims)
- LLM: OpenAI `gpt-4o-mini` (or `gpt-4o`/`gpt-4.1`)
- API: FastAPI
- Widget: Tiny vanilla JS modal

## Quick start (local)
```bash
cp .env.example .env   # add your keys
pip install -r requirements.txt
python scraper/scrape_ortahaus.py
python indexer/build_embeddings.py
uvicorn server.app:app --reload --port 8000
# open web/index.html
```

## Deploy on Railway (drag & drop or from repo)
1) Create a new Railway project and **Deploy** this folder (Dockerfile included).
2) Add Environment Variables (Settings → Variables):
```
OPENAI_API_KEY=sk-...
OPENAI_MODEL_CHAT=gpt-4o-mini
OPENAI_MODEL_EMBED=text-embedding-3-small

PINECONE_API_KEY=pcsk-...
PINECONE_INDEX=ortahaus        # or your index name
PINECONE_ENV=us-east-1
PINECONE_NAMESPACE=prod

BASE_URL=https://ortahaus.com
ALLOWED_ORIGINS=*
```
3) After deploy, copy your Railway public URL (e.g. `https://ortahaus-chat.up.railway.app`).
4) In your staging page (or `web/index.html`) set:
```html
<script>window.WIDGET_API_BASE='https://YOUR-Railway-URL';</script>
<script src="/widget.js"></script>
```

## Important: Pinecone dimension
If you use OpenAI `text-embedding-3-small`, your Pinecone index **must be 1536 dimensions**.  
If your current index is 512 dims, delete it and recreate with:
- Type: Serverless
- Metric: cosine
- Dimension: 1536
- Cloud/Region: AWS / us-east-1

## Cron (optional)
Schedule the scraper + indexer weekly with Railway Cron, or trigger manually.
