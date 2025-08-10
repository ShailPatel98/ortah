# Ortahaus Product Guide – Full Stack

## Quick start (local)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export OPENAI_API_KEY=...
export OPENAI_MODEL_CHAT=gpt-4o-mini
export OPENAI_MODEL_EMBED=text-embedding-3-small
export PINECONE_API_KEY=...
export PINECONE_INDEX=ortahaus
export PINECONE_NAMESPACE=prod
export BASE_URL=https://ortahaus.com
export ALLOWED_ORIGINS=*
export PORT=8000

python scraper/scrape_ortahaus.py
python indexer/build_embeddings.py
uvicorn server.app:app --reload --port ${PORT:-8000}
```

Open the UI at: `http://localhost:8000/ui`

## Deploy (Railway)
- Use this repo.
- Add the same env vars above in Railway.
- Railway exposes port 8000 by default via the Dockerfile.
- UI will be at: `https://<your-railway-app>.up.railway.app/ui`

## Notes
- The chat stores a very small in-memory session per `session_id` kept in localStorage by the widget.
- The bot asks for missing info first, then recommends exactly **one** product with an external link.
- `build_embeddings.py` ensures no `null` values get sent to Pinecone metadata.
