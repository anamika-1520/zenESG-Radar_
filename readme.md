# ZenESG Regulatory Radar

AI-powered ESG regulatory intelligence system that collects sustainability news, parses regulatory signals with Groq, stores them in PostgreSQL, indexes them in ChromaDB, and exposes ranked updates through a FastAPI endpoint.

## What This Project Does

ZenESG Regulatory Radar helps track ESG and sustainability regulation updates from RSS feeds and Tavily web search.

It can:

- Fetch ESG news from global RSS sources.
- Extract ESG keywords from `sustainability_keywords.pdf`.
- Store relevant raw articles in PostgreSQL (or SQLite locally).
- Parse articles into structured regulation records using Groq.
- Collect extra web intelligence with Tavily.
- Build a ChromaDB index for RAG-style search and ranking.
- Show daily ranked regulatory updates in Streamlit.
- Expose the daily radar data through a FastAPI endpoint.
- Run the full pipeline automatically every day via GitHub Actions.

## Pipeline

```text
sustainability_keywords.pdf
        |
        v
keyword_extractor.py
        |
        v
data_ingestion.py  ->  PostgreSQL / articles
        |
        v
parser.py          ->  PostgreSQL / parsed_articles
        |
        v
tavily_collector.py -> PostgreSQL / tavily_articles
        |
        v
rag_pipeline.py    ->  chroma_db/
        |
        v
dashboard.py       ->  Streamlit Daily Radar

api.py             ->  FastAPI JSON endpoint
GitHub Actions     ->  runs full pipeline daily at 08:30 IST
```

## Live API

```
Base URL : https://zenesg-radar-1.onrender.com
Endpoint : GET /api/daily-radar
Docs     : https://zenesg-radar-1.onrender.com/docs
```

### Query Parameters

| Parameter | Default | Options |
| --- | --- | --- |
| `region` | `Global` | `India`, `UK`, `EU`, `US`, `Singapore`, `Global` |
| `impact` | `All` | `high`, `medium`, `low`, `All` |
| `limit` | `10` | `1` to `25` |

### Example Request

```
GET https://zenesg-radar-1.onrender.com/api/daily-radar?region=EU&impact=high&limit=10
```

### Response Format

```json
{
  "generated_at": "2026-06-28 08:12:53",
  "region": "EU",
  "impact_filter": "high",
  "rag": {
    "total": 6,
    "error": null,
    "results": [
      {
        "regulation_name": "CSRD",
        "jurisdiction": "EU",
        "impact_level": "high",
        "change_type": "update",
        "action_required": "...",
        "summary": "...",
        "regulator": "European Commission",
        "deadline": "2026",
        "affected_sectors": "[\"Finance\"]",
        "title": "...",
        "source": "...",
        "url": "...",
        "fetched_at": "...",
        "relevance_score": 3,
        "rag_score": 68.6
      }
    ]
  },
  "tavily": {
    "total": 5,
    "error": null,
    "results": [
      {
        "title": "...",
        "content": "...",
        "url": "...",
        "query_used": "...",
        "relevance_score": 0.95,
        "fetched_at": "..."
      }
    ]
  }
}
```

## Main Files

| File | Purpose |
| --- | --- |
| `api.py` | FastAPI endpoint for daily radar results. |
| `scheduler.py` | Runs full pipeline locally. |
| `dashboard.py` | Streamlit app entry point. |
| `radar.py` | Daily Radar UI and filters. |
| `data_ingestion.py` | Fetches RSS feeds and saves relevant articles. |
| `parser.py` | Uses Groq to convert articles into structured regulation records. |
| `tavily_collector.py` | Uses Tavily to collect additional regulatory intelligence. |
| `rag_pipeline.py` | Loads parsed and Tavily articles into ChromaDB and ranks results. |
| `keyword_extractor.py` | Extracts ESG keywords from the sustainability PDF. |
| `db_schema.py` | Ensures database tables exist — supports PostgreSQL and SQLite. |
| `config.py` | Central paths, RSS feeds, and database configuration. |
| `console_utils.py` | Windows console UTF-8 helper. |
| `.env.example` | Environment variable template. |
| `requirements.txt` | Python dependencies. |

## Requirements

- Python 3.11 recommended.
- Do not use Python 3.14 — `tokenizers` and `pydantic-core` will fail.
- Groq API key.
- Tavily API key.
- PostgreSQL database (Render free tier recommended for production).

## Setup On Windows

```powershell
py -3.11 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Environment Variables

Copy the example file:

```powershell
Copy-Item .env.example .env
```

Add real keys:

```env
GROQ_API_KEY=gsk_your_groq_key_here
TAVILY_API_KEY=tvly_your_tavily_key_here

# PostgreSQL (production)
DATABASE_URL=postgresql://user:password@host/dbname

# SQLite (local fallback — used if DATABASE_URL is not set)
DATABASE_PATH=esg_radar.db

# ChromaDB
CHROMA_PATH=chroma_db
```

## Database

The project supports both PostgreSQL and SQLite:

| Environment | Database |
| --- | --- |
| Production (Render) | PostgreSQL — set `DATABASE_URL` |
| Local development | SQLite — `esg_radar.db` |

Auto-detection — if `DATABASE_URL` is set, PostgreSQL is used. Otherwise SQLite.

## Run The Full Pipeline Locally

```powershell
python scheduler.py
```

Or run steps manually:

```powershell
python data_ingestion.py
python parser.py
python tavily_collector.py
python rag_pipeline.py
```

## Run The Dashboard Locally

```powershell
streamlit run dashboard.py
```

## Run The API Locally

```powershell
uvicorn api:app --reload
```

```
GET http://127.0.0.1:8000/api/daily-radar
GET http://127.0.0.1:8000/docs
```

## Deployment

### API — Render Web Service

| Setting | Value |
| --- | --- |
| Runtime | Python 3.11 |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn api:app --host 0.0.0.0 --port $PORT` |

Environment variables to set on Render:

```
GROQ_API_KEY
TAVILY_API_KEY
DATABASE_URL  (Render PostgreSQL Internal URL)
```

### Automated Pipeline — GitHub Actions

Pipeline runs automatically every day at 08:30 IST via `.github/workflows/daily_pipeline.yml`.

GitHub Secrets required:

```
DATABASE_URL
GROQ_API_KEY
TAVILY_API_KEY
```

Manual trigger available from GitHub → Actions → Daily ESG Pipeline → Run workflow.

## Database Tables

| Table | Description |
| --- | --- |
| `articles` | Raw RSS articles. |
| `parsed_articles` | Groq-parsed regulatory fields. |
| `tavily_articles` | Tavily web intelligence results. |
| `fetch_logs` | RSS fetch history. |
| `impact_assessments` | Saved assessment/report data. |

## Common Issues

| Problem | Fix |
| --- | --- |
| `No module named pydantic_core` | Use Python 3.11, not 3.14. |
| `Invalid API Key` from Groq | Replace `GROQ_API_KEY` in `.env`. |
| Tavily requests fail | Check `TAVILY_API_KEY` in `.env`. |
| `no such table` error | Run `python db_schema.py`. |
| Dashboard has no data | Run `python scheduler.py`. |
| RAG results look stale | Run `python rag_pipeline.py`. |
| PostgreSQL connection fails | Check `DATABASE_URL` in `.env` or Render environment. |

## Tech Stack

| Layer | Technology |
| --- | --- |
| Language | Python 3.11 |
| API | FastAPI |
| Dashboard | Streamlit |
| Database | PostgreSQL (production) / SQLite (local) |
| RSS parsing | feedparser |
| Web intelligence | Tavily |
| LLM parsing | Groq |
| Vector store | ChromaDB |
| PDF keyword extraction | PyMuPDF |
| Scheduling | GitHub Actions |
| Deployment | Render |
