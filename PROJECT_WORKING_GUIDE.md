# ZenESG Regulatory Radar

AI-powered ESG regulatory intelligence system that monitors global ESG regulations, ranks them by relevance, and generates company-specific compliance reports.

---

## One-line mental model

```
Fetch ESG news → parse it → store it → index in ChromaDB → RAG-rank it → show in Daily Radar
```

---

## What it does

- Monitors 20+ global ESG news sources daily
- Extracts 1842+ keywords dynamically from a sustainability PDF — zero hardcoding
- Parses articles into structured regulatory records using Groq LLaMA 3.3 70B
- Indexes everything in ChromaDB for semantic search
- Shows Top 10 ranked ESG updates daily in the dashboard
- Generates company-specific compliance reports with action checklists
- Answers ESG questions via an intelligent chat agent (RAG + web search + LLM)

---

## Daily News Architecture

```
sustainability_keywords.pdf
          |
          v
  keyword_extractor.py
          |
          v
RSS feeds → data_ingestion.py → esg_radar.db (articles)
                                      |
                                      v
                                  parser.py
                                      |
                                      v
                              esg_radar.db (parsed_articles)
                                      |
                                      v
                               rag_pipeline.py
                                      |
                                      v
                                  chroma_db/
                                      |
                                      v
                                  radar.py
                                      |
                                      v
                         dashboard.py → Daily Radar tab

Tavily path:
keywords.pdf → tavily_collector.py → esg_radar.db (tavily_articles) → rag_pipeline.py → chroma_db/
```

---

## Full Project Architecture

```
                        .env (API keys)
                              |
                              v
                        dashboard.py
                              |
        ------------------------------------------------
        |              |              |                |
        v              v              v                v
  Daily Radar    Assessment      ESG Chat          Stats
   radar.py      dashboard.py   qa_rag.py       dashboard.py
        |              |              |
        v              v              v
  rag_pipeline.py  rag_pipeline.py  rag_pipeline.py
        |
        v
    chroma_db/
        ^
        |
  esg_radar.db
  (articles / parsed_articles / tavily_articles)
        ^
        |
  data_ingestion.py + parser.py + tavily_collector.py
```

---

## File Map

| File | What it does |
|------|-------------|
| `dashboard.py` | Main Streamlit app — 5 tabs, entry point |
| `radar.py` | Daily Radar UI — top 10 ESG news, expandable full articles |
| `data_ingestion.py` | Fetches RSS feeds, filters by ESG keywords, saves raw articles to DB |
| `parser.py` | Sends articles to Groq LLaMA, extracts structured regulatory fields |
| `tavily_collector.py` | Searches web via Tavily API, saves regulatory web intelligence |
| `keyword_extractor.py` | Reads sustainability PDF, extracts 1842 ESG keywords dynamically |
| `rag_pipeline.py` | Loads parsed articles into ChromaDB, hybrid scoring for ranking |
| `qa_rag.py` | ESG chat agent — LangGraph + Groq + RAG + DuckDuckGo auto-routing |
| `impact_assessment.py` | CLI tool — takes company profile, generates compliance report |
| `daily_radar.py` | Daily Radar UI component — imported by dashboard |
| `config.py` | All paths and settings — RSS feeds, DB path, PDF path, Chroma path |
| `db_schema.py` | Creates all SQLite tables on fresh setup |
| `esg_radar.db` | Main SQLite database — all articles and assessments |
| `chroma_db/` | ChromaDB vector index used by RAG pipeline |
| `sustainability_keywords.pdf` | ESG keyword source — drives all filtering, no hardcoding |
| `Dockerfile` | Docker image definition |
| `docker-compose.yml` | Docker run configuration |
| `requirements.txt` | Python dependencies |
| `.env.example` | Environment variable template — copy to `.env` |
| `.env` | Local secrets — never commit |

---

## Database Tables

| Table | What it stores |
|-------|---------------|
| `articles` | Raw RSS articles — title, description, URL, source, fetched_at |
| `parsed_articles` | Structured data — regulation name, jurisdiction, impact level, action required |
| `tavily_articles` | Web intelligence — full content, relevance score, query used |
| `fetch_logs` | RSS fetch history — source URL, article count, status, timestamp |
| `impact_assessments` | Saved company compliance reports with regulation list |

---

## Setup

### 1. Create `.env`

```bash
copy .env.example .env
```

Required keys:

```
GROQ_API_KEY=...
TAVILY_API_KEY=...
OPENAI_API_KEY=...
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Build data pipeline

Run in this order:

```bash
python data_ingestion.py
python parser.py
python tavily_collector.py
python rag_pipeline.py
```

### 4. Run dashboard

```bash
streamlit run dashboard.py
```

Open: `http://localhost:8501`

---

## Run with Docker

```bash
docker compose up --build
```

Open: `http://localhost:8501`

Build data inside Docker:

```bash
docker compose run --rm zenesg-radar python data_ingestion.py
docker compose run --rm zenesg-radar python parser.py
docker compose run --rm zenesg-radar python tavily_collector.py
docker compose run --rm zenesg-radar python rag_pipeline.py
```

> Note: `esg_radar.db` and `chroma_db/` must exist in project root for Docker to mount them.

---

## Dashboard Tabs

| Tab | What it shows |
|-----|--------------|
| Daily Radar | Top 10 ranked ESG regulatory updates today — expandable full articles |
| Company Assessment | Enter company profile → personalized compliance report with action checklist |
| Latest Regulations | Browse all regulations filtered by impact level and region |
| System Stats | Pipeline health — article counts, impact distribution, top regulations |
| ESG Chat | Ask any ESG question — auto-routed to RAG, web search, or LLM |

---

## Common Issues

| Problem | Fix |
|---------|-----|
| No Daily Radar data | Check `esg_radar.db`, `parsed_articles` table, and `chroma_db/` |
| RAG results stale after new fetch | Rerun `python rag_pipeline.py` |
| `no such table` error | Run `python db_schema.py` |
| Docker shows empty data | Confirm `esg_radar.db` and `chroma_db/` exist in project root |
| Groq or Tavily errors | Check `.env` keys |
| RSS fetch returns nothing | Check `RSS_FEEDS` in `config.py` and PDF keywords |

---

## What to commit

```
✅ All source code files
✅ Dockerfile + docker-compose.yml
✅ requirements.txt
✅ .env.example
✅ esg_radar.db
✅ chroma_db/
✅ sustainability_keywords.pdf
✅ README.md

❌ .env
❌ venv/
❌ __pycache__/
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Data ingestion | Python, feedparser, requests |
| Web intelligence | Tavily API |
| Keyword extraction | pymupdf — dynamic from PDF, zero hardcoding |
| AI parsing | Groq LLaMA 3.3 70B |
| Vector search | ChromaDB + sentence-transformers (all-MiniLM-L6-v2) |
| Chat agent | LangGraph + Groq + DuckDuckGo |
| Database | SQLite |
| Dashboard | Streamlit |

---

## Accuracy

System achieves **8.5 to 9 out of 10** accuracy on regulatory queries:

| Company type | Correctly identified |
|-------------|---------------------|
| UK investment firms | TCFD, FCA, ESRS |
| India companies | BRSR, SEBI |
| EU companies | ESRS, CSRD, CBAM |
| Singapore | ISSB, SGX mandates |
| Shipping EU | ESRS, IMO, shadow fleet |

---

*Built as Feature 5 — Regulatory Radar — of the ZenESG platform.*
