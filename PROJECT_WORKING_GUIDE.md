# ZenESG Radar - Detailed Project Working Guide

This document explains how the project works file by file, with special focus on the Daily Radar / top news fetcher flow, the database pipeline, the RAG search flow, and the important functions your teammate should understand first.

## 1. Big Picture

ZenESG Radar is an ESG regulatory intelligence app. It collects ESG-related news and regulatory updates, stores them in SQLite, converts raw news into structured regulatory data using Groq, indexes the structured content into ChromaDB, and exposes everything through a Streamlit dashboard.

The project has five major flows:

1. RSS news collection
   - `data_ingestion.py` reads RSS feeds from `config.py`.
   - It extracts ESG keywords from `sustainability_keywords.pdf`.
   - It saves relevant articles into the SQLite `articles` table.

2. AI parsing / structuring
   - `parser.py` reads unparsed RSS articles.
   - It sends article title + description to Groq.
   - It saves structured ESG regulation details into `parsed_articles`.

3. Tavily web intelligence
   - `tavily_collector.py` builds search queries from the same keyword PDF.
   - It searches the web through Tavily.
   - It saves high-relevance web results into `tavily_articles`.

4. RAG / semantic search
   - `rag_pipeline.py` loads parsed RSS articles and Tavily articles into ChromaDB.
   - It ranks regulations for a company using semantic similarity, keyword overlap, jurisdiction fit, and impact level.

5. Streamlit dashboard
   - `dashboard.py` is the main app.
   - It renders company assessment, latest regulations, database stats, ESG chat, and Daily Radar tabs.
   - `radar.py` specifically renders the Daily Radar / top news page.

## 2. Main Runtime Flow

Typical data preparation order:

```text
keyword_extractor.py
        |
        v
data_ingestion.py  --->  articles table
        |
        v
parser.py          --->  parsed_articles table
        |
        v
tavily_collector.py ---> tavily_articles table
        |
        v
rag_pipeline.py    --->  chroma_db vector index
        |
        v
dashboard.py       --->  Streamlit user interface
```

Typical app user flow:

```text
User opens Streamlit app
        |
        v
dashboard.py main()
        |
        +-- Company Assessment tab
        +-- Latest Regulations tab
        +-- Database Stats tab
        +-- ESG chat tab
        +-- Daily Radar tab -> radar.py render_daily_radar()
```

## 3. Database Tables

The app mainly uses `esg_radar.db`.

### `articles`

Created by `data_ingestion.py`.

Purpose:
- Stores raw RSS articles that matched at least one ESG keyword.

Important columns:
- `title`: RSS article title.
- `description`: cleaned RSS summary or description.
- `url`: article link. It is unique, so duplicates are skipped.
- `source`: RSS feed/source name.
- `published`: source publish date.
- `matched_keywords`: JSON list of matched ESG keywords.
- `relevance_score`: number of keyword matches.
- `fetched_at`: time article was saved.

### `fetch_logs`

Created by `data_ingestion.py`.

Purpose:
- Tracks every RSS feed fetch attempt.

Important columns:
- `source_url`: RSS feed URL.
- `total_articles`: total articles found in the feed.
- `relevant_articles`: articles that matched ESG keywords.
- `status`: success or error message.

### `parsed_articles`

Created by `parser.py`.

Purpose:
- Stores AI-extracted regulatory information from RSS articles.

Important columns:
- `article_id`: links back to `articles.id`.
- `regulation_name`: examples: CSRD, TCFD, BRSR.
- `jurisdiction`: examples: EU, UK, India, Global.
- `regulator`: examples: SEBI, SEC, FCA.
- `change_type`: new rule, rollback, update, proposal, or other.
- `affected_sectors`: JSON list of sectors.
- `deadline`: compliance deadline if available.
- `impact_level`: high, medium, or low.
- `summary`: short explanation of the regulatory update.
- `action_required`: one-sentence recommended action.

### `tavily_articles`

Created by `tavily_collector.py`.

Purpose:
- Stores web search results from Tavily.

Important columns:
- `title`: web result title.
- `content`: Tavily result content/snippet.
- `url`: unique result URL.
- `source`: source domain/name if Tavily provides it.
- `query_used`: search query that produced the result.
- `relevance_score`: Tavily relevance score.
- `fetched_at`: save time.

### `impact_assessments`

Created by `dashboard.py` or `impact_assesment.py`.

Purpose:
- Stores generated company compliance assessments.

Important columns:
- `company_name`
- `company_sector`
- `company_jurisdiction`
- `assessment`
- `regulations_used`
- `assessed_at`

## 4. File-by-File Explanation

## `config.py`

This is the central configuration file.

Important values:

- `RSS_FEEDS`
  - A list of RSS feed URLs.
  - `data_ingestion.py` loops over this list to fetch ESG news.

- `KEYWORDS_PDF`
  - Path to `sustainability_keywords.pdf`.
  - Used by `keyword_extractor.py`, `data_ingestion.py`, and `tavily_collector.py`.

- `DATABASE`
  - SQLite file name: `esg_radar.db`.
  - Most modules import this instead of hardcoding the database name.

- `FETCH_INTERVAL_HOURS`
  - Used by the ingestion scheduler.
  - Current value is `6`, meaning RSS ingestion can run every 6 hours.

- `MAX_DESCRIPTION_LENGTH`
  - Caps RSS article descriptions before saving.

- `CHROMA_PATH`
  - Folder where ChromaDB stores vector index files.

- `COLLECTION_NAME`
  - Name of the Chroma collection used by the RAG pipeline.

Why this file matters:
- If feed sources, database path, keyword PDF path, or Chroma settings change, this is the first file to check.

## `keyword_extractor.py`

This file extracts ESG keywords from the PDF.

### `extract_keywords_from_pdf(pdf_path=KEYWORDS_PDF)`

Purpose:
- Reads the sustainability keyword PDF.
- Extracts possible keyword phrases.
- Cleans them.
- Returns a list of keywords.

How it works:
1. Opens the PDF using PyMuPDF (`fitz`).
2. Reads text from every page.
3. Looks for table-style text using a pipe-based regex.
4. Also scans each normal line from the PDF.
5. Keeps only valid keyword candidates using `is_valid_keyword`.
6. Cleans the final set using `clean_keywords`.
7. If anything fails, returns fallback ESG keywords.

Why it matters:
- This is the starting point for both RSS filtering and Tavily query generation.
- Better keywords produce better news collection.

### `is_valid_keyword(text)`

Purpose:
- Filters bad PDF text.

Rejects:
- Very short text.
- Very long text.
- Number-only strings.
- Header/junk words like `keyword`, `source`, `search`, `prompt`, etc.

### `clean_keywords(keywords)`

Purpose:
- Normalizes keyword strings.

It:
- Collapses extra spaces.
- Removes surrounding symbols like `|`, `#`, `*`, `_`, `.`, `,`.
- Keeps only meaningful values.

### `get_fallback_keywords()`

Purpose:
- Provides a small hardcoded keyword list if PDF reading fails.

Fallback examples:
- ESG
- CSRD
- TCFD
- GRI
- ISSB
- BRSR

## `data_ingestion.py`

This is the RSS news fetcher. It collects top/raw ESG news from configured RSS feeds.

### `setup_database()`

Purpose:
- Creates the database tables needed for RSS ingestion.

Creates:
- `articles`
- `fetch_logs`

Returns:
- An active SQLite connection.

### `clean_text(text)`

Purpose:
- Cleans RSS descriptions before matching/saving.

It:
- Removes HTML tags using regex.
- Replaces multiple spaces with one space.
- Strips leading/trailing whitespace.

Why it matters:
- RSS descriptions often contain HTML. This makes keyword matching and summaries cleaner.

### `check_relevance(title, description, keywords)`

Purpose:
- Decides whether an RSS article is relevant.

How it works:
1. Combines title and description.
2. Converts everything to lowercase.
3. Checks whether each keyword appears in the combined text.
4. Returns:
   - `matched`: list of matched keywords.
   - `score`: number of matched keywords.

Important detail:
- This is simple substring matching, not AI classification.
- A higher score means more keyword matches, not necessarily better legal relevance.

### `save_article(conn, article)`

Purpose:
- Saves one relevant RSS article into the `articles` table.

Important behavior:
- The `url` column is unique.
- Duplicate URLs raise `sqlite3.IntegrityError`.
- The function catches that and returns `False`.

Returns:
- `True` when a new article is inserted.
- `False` when the article already exists.

### `log_fetch(conn, source_url, total, relevant, status)`

Purpose:
- Records the result of each feed fetch.

Useful for:
- Debugging broken feeds.
- Checking how many relevant articles each source produces.

### `fetch_from_feed(feed_url, keywords, conn)`

Purpose:
- Fetches one RSS feed and saves relevant articles.

Detailed flow:
1. Parses the RSS feed with `feedparser.parse`.
2. Gets the feed/source name.
3. Loops through each feed entry.
4. Extracts:
   - title
   - description or summary
   - URL
   - published date
5. Cleans and trims the description.
6. Calls `check_relevance`.
7. If score is greater than 0, builds an article dictionary.
8. Calls `save_article`.
9. Logs the fetch using `log_fetch`.
10. Prints a source-level summary.

Returns:
- Number of relevant articles found in that feed.

Why it matters:
- This is the main RSS/top-news collection function.

### `run_ingestion()`

Purpose:
- Runs the complete RSS ingestion job.

Detailed flow:
1. Prints a run header.
2. Calls `extract_keywords_from_pdf`.
3. Calls `setup_database`.
4. Loops through every URL in `RSS_FEEDS`.
5. Calls `fetch_from_feed` for each feed.
6. Prints total relevant count.
7. Queries the database for top 5 highest-scoring RSS articles.
8. Prints the top articles and their matched keywords.
9. Closes the database connection.

When run directly:
- The script runs ingestion immediately.
- Then it schedules `run_ingestion` every `FETCH_INTERVAL_HOURS`.
- It stays alive in a loop and checks the schedule every minute.

## `parser.py`

This file converts raw RSS articles into structured ESG regulation records using Groq.

### `setup_db()`

Purpose:
- Creates the `parsed_articles` table if it does not exist.

Important detail:
- `article_id` is unique, so each raw article is parsed only once.

### `parse_article(title, description, retries=3)`

Purpose:
- Sends one article to Groq and asks for structured ESG JSON.

Prompt asks for:
- `regulation_name`
- `jurisdiction`
- `regulator`
- `change_type`
- `affected_sectors`
- `deadline`
- `impact_level`
- `summary`
- `action_required`

Detailed flow:
1. Builds a strict JSON-only prompt.
2. Sends it to Groq model `llama-3.3-70b-versatile`.
3. Removes Markdown code fences if the model returns them.
4. Parses the response with `json.loads`.
5. Retries on JSON parsing errors.
6. Waits longer if a rate limit is detected.
7. Returns a Python dictionary if parsing succeeds.
8. Returns `None` if parsing fails.

Why it matters:
- This function turns unstructured news into database fields the dashboard can filter and display.

### `run_parser()`

Purpose:
- Parses all relevant RSS articles that have not been parsed yet.

Detailed flow:
1. Creates/opens `parsed_articles`.
2. Selects RSS articles that:
   - are not already in `parsed_articles`
   - have `relevance_score >= 2`
3. Loops through each article.
4. Calls `parse_article`.
5. Saves the parsed JSON fields into `parsed_articles`.
6. Waits 1 second between requests.
7. Prints a parsing summary.
8. Prints recent high-impact regulations.
9. Closes the database.

Important detail:
- Articles with only 1 matched keyword are not parsed by default.
- That threshold is controlled in the SQL query inside `run_parser`.

## `tavily_collector.py`

This file collects web intelligence using Tavily search. It supports the Daily Radar's "Latest Web Intelligence" section.

### `setup_db()`

Purpose:
- Creates the `tavily_articles` table.

Important detail:
- `url` is unique, so duplicate web results are ignored.

### `build_search_queries(keywords)`

Purpose:
- Converts extracted PDF keywords into Tavily search queries.

Detailed flow:
1. Filters the full keyword list to keep regulatory terms.
2. Keeps terms containing signals like:
   - CSRD
   - TCFD
   - TNFD
   - GRI
   - ISSB
   - SFDR
   - CBAM
   - BRSR
   - SEBI
   - SEC
   - reporting
   - compliance
   - framework
3. Limits to the first 20 regulatory keywords.
4. Converts each keyword into a query like:
   - `{keyword} latest update 2026`
5. Adds extra broad queries:
   - ESG regulation changes 2026
   - climate disclosure requirements 2026
   - sustainability reporting mandatory 2026
   - carbon tax policy update 2026
   - net zero regulation corporate 2026
6. Removes duplicates using `set`.

Returns:
- A list of Tavily search queries.

Why it matters:
- This decides what the app searches beyond RSS feeds.

### `search_regulations(query, conn)`

Purpose:
- Runs one Tavily query and saves results.

Detailed flow:
1. Calls `client.search`.
2. Uses advanced search depth.
3. Requests up to 5 results.
4. Loops through results.
5. Extracts:
   - title
   - content
   - URL
   - source
   - score
6. Inserts each result into `tavily_articles` using `INSERT OR IGNORE`.
7. Counts how many new articles were saved.

Returns:
- Number of new Tavily results saved.

### `run_tavily_collector()`

Purpose:
- Runs the complete Tavily web intelligence job.

Detailed flow:
1. Loads keywords from the PDF.
2. Builds Tavily search queries.
3. Creates/opens `tavily_articles`.
4. Runs `search_regulations` for each query.
5. Counts total saved results.
6. Prints the top 5 most relevant results.
7. Closes the database.

## `rag_pipeline.py`

This is the active RAG pipeline used by `dashboard.py`.

It:
- Loads parsed RSS and Tavily articles into ChromaDB.
- Converts database rows into searchable documents.
- Ranks regulations for a company profile.

Important global objects:

- `model = SentenceTransformer("all-MiniLM-L6-v2")`
  - Embedding model loaded at import time.

- `chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)`
  - Persistent local ChromaDB client.

### `get_collection(rebuild=False)`

Purpose:
- Returns the ChromaDB collection.

Behavior:
- If `rebuild=True`, deletes the existing collection first.
- Then creates or gets the collection named by `COLLECTION_NAME`.
- Uses cosine similarity.

### `tokenize(text)`

Purpose:
- Converts text into normalized tokens for keyword matching.

It:
- Lowercases text.
- Extracts alphanumeric tokens.
- Removes stopwords.
- Removes one-character tokens.

### `parse_json_list(value)`

Purpose:
- Safely parses JSON lists from database fields like `affected_sectors`.

Returns:
- A list if JSON parsing succeeds.
- A one-item list containing the raw value if parsing fails.
- Empty list for empty input.

### `clean_value(value, fallback)`

Purpose:
- Normalizes weak/missing values.

Treats these as missing:
- empty string
- `none`
- `null`
- `unknown`

### `extract_regulation_from_query(query)`

Purpose:
- Infers a regulation name from a Tavily search query.

Example:
- Query containing `CSRD` returns `CSRD`.
- Query without a known regulation returns `General ESG`.

Used by:
- `build_tavily_document`

### `extract_jurisdiction_from_query(query)`

Purpose:
- Infers jurisdiction from a Tavily search query.

Examples:
- `brsr` or `sebi` -> India
- `csrd`, `esrs`, `cbam` -> EU
- `sec` -> US
- `tcfd` -> UK/Global

### `build_document(row)`

Purpose:
- Converts one `parsed_articles` database row into:
  - Chroma document text
  - Chroma metadata
  - Chroma document ID

Document includes:
- title
- regulation
- jurisdiction
- regulator
- change type
- impact level
- affected sectors
- summary
- action required
- source

Metadata includes:
- article ID
- regulation name
- jurisdiction
- regulator
- change type
- impact level
- sectors
- title
- source
- `data_type = parsed`

Why it matters:
- The document is what semantic search reads.
- The metadata is what the dashboard displays after search.

### `build_tavily_document(row)`

Purpose:
- Converts one `tavily_articles` row into a Chroma document.

Important detail:
- Tavily results do not already have parsed regulation fields.
- The function derives regulation and jurisdiction from `query_used`.

Metadata defaults:
- regulator: `Not specified`
- change type: `update`
- impact level: `medium`
- affected sectors: `all sectors`
- `data_type = tavily`

### `load_articles_to_chroma(rebuild=True)`

Purpose:
- Loads database articles into ChromaDB.

Detailed flow:
1. Opens SQLite.
2. Reads all parsed RSS articles by joining `parsed_articles` and `articles`.
3. Reads Tavily articles with `relevance_score >= 0.7`.
4. Builds Chroma documents for parsed RSS rows.
5. Builds Chroma documents for Tavily rows.
6. Gets the Chroma collection.
7. Upserts documents in batches of 50.
8. Prints total collection count.

Important detail:
- `dashboard.py` calls this through `load_rag()` with `rebuild=False`.
- Running `rag_pipeline.py` directly calls it with `rebuild=True`.

### `jurisdiction_fit(company_jurisdiction, article_jurisdiction, company_text)`

Purpose:
- Scores how well an article jurisdiction matches a company.

Scoring logic:
- Global/no jurisdiction: `0.65`
- Direct company jurisdiction match: `1.0`
- Article jurisdiction appears in company text: `0.85`
- Global appears in article jurisdiction: `0.65`
- Otherwise: `0.25`

### `keyword_score(company_profile, metadata, document)`

Purpose:
- Measures lexical overlap between company profile and regulation article.

Detailed flow:
1. Builds company text from name, sector, jurisdiction, and description.
2. Builds article text from title, regulation name, sectors, and document.
3. Tokenizes both.
4. Finds common tokens.
5. Score = matched terms / company tokens.
6. Returns score and up to 8 matched terms.

### `hybrid_score(company_profile, metadata, document, distance)`

Purpose:
- Combines semantic, keyword, geography, and impact signals.

Formula:

```text
score =
  semantic similarity * 0.65
  + lexical keyword score * 0.20
  + jurisdiction score * 0.15
  + impact bonus
```

Impact bonus:
- high: `0.05`
- medium: `0.03`
- low: `0.0`

Why it matters:
- This decides which regulations appear at the top of a company assessment.

### `build_query(company_profile)`

Purpose:
- Converts a company profile into a detailed RAG search query.

Includes:
- company name
- sector
- jurisdiction
- size
- description
- ESG/regulatory search intent text

### `find_relevant_regulations(company_profile, top_k=10)`

Purpose:
- Finds and ranks regulations relevant to a company.

Detailed flow:
1. Gets the Chroma collection.
2. Checks if it has documents.
3. Builds a query from the company profile.
4. Retrieves more candidates than needed:
   - `max(top_k * 5, 20)`
5. For each candidate:
   - calculates hybrid score
   - stores semantic score
   - stores keyword score
   - stores jurisdiction fit
   - keeps matched terms and metadata
6. Sorts by final score descending.
7. Returns the top `top_k`.

Used by:
- `dashboard.py`
- `impact_assesment.py`

### `display_results(company_profile, regulations)`

Purpose:
- CLI-only helper to print ranked results.

Used when:
- Running `rag_pipeline.py` directly for testing.

### `run_rag()`

Purpose:
- Test runner for the RAG pipeline.

It:
- Rebuilds ChromaDB.
- Tests three sample company profiles.
- Prints top regulations for each.

## `qa_rag.py`

This file powers the ESG chat tab in Streamlit.

It uses LangGraph with two tools:
- ChromaDB RAG search.
- DuckDuckGo web search through `ddgs`.

### `hybrid_search(query: str, top_k: int = 5)`

Purpose:
- Queries ChromaDB directly for top matching ESG documents.

Returns:
- List of dictionaries containing metadata, document summary, and similarity score.

Important difference from `rag_pipeline.find_relevant_regulations`:
- This function is simpler.
- It does not apply the full company-specific hybrid scoring formula.
- It mostly uses vector distance from ChromaDB.

### `esg_rag_tool(query: str)`

Purpose:
- LangChain tool that searches the ESG knowledge base.

Used for:
- company-specific questions
- compliance analysis
- jurisdiction-specific ESG requirements
- regulations affecting companies

Returns:
- A compact list of result dictionaries with title, regulation, jurisdiction, regulator, summary, and score.

### `duckduckgo_tool(query: str)`

Purpose:
- LangChain tool that searches the public web.

Used for:
- general ESG concepts
- latest ESG news
- questions like "What is TCFD?"

Returns:
- List of title/body result dictionaries.

### `ChatState`

Purpose:
- Defines LangGraph state.

It stores:
- `messages`: the conversation history.

### `SYSTEM_PROMPT`

Purpose:
- Tells the chat agent when to use RAG vs web search.
- Defines the expected compliance report format.

### `chat_node(state: ChatState)`

Purpose:
- Main LLM node in the LangGraph agent.

Detailed flow:
1. Prepends the system prompt.
2. Adds conversation messages.
3. Calls the Groq LLM with tools bound.
4. Returns the model response into graph state.

### `agent = graph.compile()`

Purpose:
- Compiles the LangGraph workflow.

Graph flow:

```text
START -> chat_node
chat_node -> tools if tool call is needed
tools -> chat_node
chat_node -> final answer
```

Used by:
- `dashboard.py` ESG chat tab.

## `radar.py`

This file renders the Daily Radar tab. This is the closest thing to the "top news fetcher" display layer.

Important idea:
- `radar.py` does not collect news itself.
- It reads already-saved RSS and Tavily data from `esg_radar.db`.
- Collection happens in `data_ingestion.py` and `tavily_collector.py`.

### Constants

### `REGIONS`

Purpose:
- Dropdown options for filtering Daily Radar updates.

Values:
- All
- India
- UK
- EU
- US
- Singapore
- Global

### `IMPACTS`

Purpose:
- Dropdown options for filtering by impact level.

Values:
- All
- High
- Medium
- Low

### `IMPACT_LABELS`

Purpose:
- Converts database impact values into display labels.

Example:
- `high` -> `High impact - Critical`
- `medium` -> `Medium impact - Watch`
- `low` -> `Low impact - Monitor`

### `IMPACT_CLASS`

Purpose:
- Maps impact levels to CSS classes.

Example:
- `high` -> `impact-high`

### `inject_radar_css()`

Purpose:
- Adds custom CSS for the Daily Radar UI.

Styles:
- hero banner
- chips
- impact colors
- news brief boxes
- source text boxes
- expanders
- Streamlit metrics

Why it matters:
- This makes the Daily Radar tab look more like a polished news briefing page instead of plain Streamlit output.

### `fetch_rows(query, params=())`

Purpose:
- Small database helper.

How it works:
1. Opens SQLite connection using `DATABASE`.
2. Executes the SQL query with parameters.
3. Fetches all rows.
4. Automatically closes the connection using `closing`.

Used by:
- `render_daily_radar`

### `fetch_source_text(url)`

Purpose:
- Attempts to fetch the full article body from a source URL.

Important details:
- Decorated with `@st.cache_data(ttl=3600)`, so results are cached for one hour.
- Uses `requests` to download the page.
- Uses BeautifulSoup to parse HTML.
- Removes noisy tags:
  - script
  - style
  - nav
  - footer
  - header
  - aside
- Looks for:
  - `<article>`
  - or `<main>`
  - or page body
- Extracts paragraph text.
- Keeps paragraphs longer than 35 characters.
- Returns up to 6000 characters only.
- Returns `None` if the extracted text is too short or any error occurs.

Why it matters:
- In Daily Radar, the database usually contains RSS summary text only.
- This function lets the user optionally fetch the fuller source article when available.

### `clean_text(value, fallback="N/A")`

Purpose:
- Normalizes values before display.

Returns:
- stripped string if present
- fallback if empty

### `impact_text(impact)`

Purpose:
- Converts raw impact value into a readable label.

Example:
- Input: `high`
- Output: `High impact - Critical`

### `chip(label, css_class="")`

Purpose:
- Builds one HTML chip/badge.

Important detail:
- Uses `html.escape` to avoid injecting raw unsafe text into HTML.

### `format_sectors(raw_value)`

Purpose:
- Converts `affected_sectors` database value into readable text.

Detailed flow:
1. If empty, returns `Not specified`.
2. Tries to parse JSON.
3. If JSON is a list, joins list items with commas.
4. If parsing fails, returns raw string.

### `render_chip_row(*items)`

Purpose:
- Renders multiple chips in one row.

Input:
- Pairs of `(label, css_class)`.

Used for:
- impact
- jurisdiction
- change type
- source
- Tavily score

### `render_full_news_brief(...)`

Purpose:
- Renders a structured news-style briefing for one regulatory update.

Sections displayed:
1. Title
2. What happened
3. Regulatory meaning
4. Who should care
5. Compliance action
6. Tracking details

Inputs:
- `title`
- `description`
- `summary`
- `action`
- `reg_name`
- `jurisdiction`
- `regulator`
- `sectors`
- `deadline`
- `change_type`

Why it matters:
- This is the function that makes parsed database fields understandable to non-technical users.

### `render_daily_radar()`

Purpose:
- Renders the full Daily Radar tab.

This is the main top-news display function.

Detailed flow:

1. Inject CSS
   - Calls `inject_radar_css`.

2. Render hero/header
   - Shows current date.
   - Explains that the tab uses saved RSS articles and Tavily web intelligence.

3. Render filters
   - Region dropdown.
   - Impact dropdown.
   - Limit slider.
   - Refresh button.

4. Build SQL query for parsed RSS articles
   - Joins `parsed_articles p` with `articles a`.
   - Starts with `WHERE 1=1`.
   - Adds jurisdiction filter if region is not `All`.
   - Adds impact filter if impact is not `All`.
   - Orders by impact priority:
     - high first
     - medium second
     - low third
   - Then orders by newest `fetched_at`.
   - Limits by slider value.

5. Fetch rows
   - Uses `fetch_rows(query, params)`.
   - Handles SQLite errors.

6. Handle empty state
   - Shows info message if no matching updates exist.

7. Show high-impact warning
   - Counts rows where impact is `high`.
   - Shows a red alert if any high-impact regulations are present.

8. Render each regulatory update
   - Each update appears inside a Streamlit expander.
   - The heading includes rank, regulation name, and title.
   - Shows chips for impact, jurisdiction, change type, and source.
   - Shows metrics for regulation, jurisdiction, and impact.
   - Shows source/fetch metadata.

9. Render tabs per article
   - `Overview`
     - summary
     - action required
   - `Full News Brief`
     - calls `render_full_news_brief`
     - shows original saved RSS text
     - offers `Fetch full source text`
   - `Compliance`
     - regulator
     - deadline
     - affected sectors
     - recommended next step

10. Link to source
   - If URL exists, shows an "Open source article" link button.

11. Render Latest Web Intelligence
   - Queries `tavily_articles`.
   - Only shows results with `relevance_score >= 0.85`.
   - Orders by relevance score and fetch time.
   - Limits to 5.
   - Shows title, score, source, query, saved content, and source link.

Why it matters:
- This function is the main Daily Radar experience.
- It combines structured RSS regulation data and Tavily web intelligence into one readable view.

## `dashboard.py`

This is the main Streamlit app.

It imports:
- `render_daily_radar` from `radar.py`
- RAG functions from `rag_pipeline.py`
- chat agent from `qa_rag.py`

### Global constants

### `SYSTEM_PROMPT`

Purpose:
- Used for company assessment generation.
- Tells the LLM to behave like a senior ESG regulatory compliance advisor.

### `SECTORS`

Purpose:
- Dropdown options for company sector.

### `JURISDICTIONS`

Purpose:
- Dropdown options for company location.

### `IMPACT_DOT`

Purpose:
- Maps impact levels to color words for display.

Example:
- high -> Red
- medium -> Yellow
- low -> Green

### `llm`

Purpose:
- Groq chat model used to generate company assessment reports.

Model:
- `llama-3.3-70b-versatile`

### `load_rag()`

Purpose:
- Loads the RAG pipeline when the app starts.

Important detail:
- Decorated with `@st.cache_resource`, so Streamlit does not reload ChromaDB on every rerun.
- Calls `load_articles_to_chroma(rebuild=False)`.

Returns:
- `True` if loading succeeds.
- `False` if loading fails.

### `find_regulations(company, top_k)`

Purpose:
- Wrapper around `rag_pipeline.find_relevant_regulations`.

Why it exists:
- Keeps Streamlit error handling inside the app.

### `fetch_all(query, params=())`

Purpose:
- SQLite helper used across dashboard stats and lists.

### `fetch_count(table, where="")`

Purpose:
- Counts rows in a database table.

Used by:
- `get_stats`

### `get_stats()`

Purpose:
- Returns system-wide counts for the sidebar and stats page.

Returns:
- RSS article count
- parsed article count
- high-impact parsed article count
- Tavily article count

### `get_past_assessments(limit=5)`

Purpose:
- Reads recent company assessments from the database.

Used by:
- sidebar

### `save_assessment(company, assessment, regulations)`

Purpose:
- Saves a generated company assessment.

Important detail:
- Creates `impact_assessments` if missing.
- Stores only regulation names in `regulations_used`.

### `build_regulation_context(regulations)`

Purpose:
- Converts retrieved regulation dictionaries into prompt text for the LLM.

Includes:
- regulation name
- jurisdiction
- regulator
- impact level
- article title
- match score

### `assess_impact(company, regulations)`

Purpose:
- Generates an ESG compliance assessment for a company.

Detailed flow:
1. Builds a prompt containing company profile.
2. Adds relevant regulations from `build_regulation_context`.
3. Asks the LLM for:
   - overall risk level
   - top 3 urgent regulations
   - immediate action checklist
   - deadline summary
   - estimated compliance effort
4. Calls Groq.
5. Returns the LLM response text or an error string.

### `render_header()`

Purpose:
- Renders app title and subtitle.

### `render_sidebar()`

Purpose:
- Renders sidebar branding, stats, and recent assessments.

Detailed flow:
1. Calls `get_stats`.
2. Displays metrics.
3. Calls `get_past_assessments`.
4. Displays recent assessment history.

### `company_form()`

Purpose:
- Renders the company profile input form.

Fields:
- company name
- sector
- jurisdiction
- company size
- description
- number of regulations to analyze

Returns:
- A dictionary containing all form values.

### `form_is_valid(data)`

Purpose:
- Validates required form inputs.

Required:
- company name
- selected sector
- selected jurisdiction
- selected size

### `render_regulation_matches(regulations)`

Purpose:
- Shows the matched regulations before the final assessment report.

Display:
- regulation name
- score
- jurisdiction
- impact label

### `render_report(company, form_data, assessment)`

Purpose:
- Displays the final generated assessment report.

Also:
- Creates downloadable `.txt` report through `st.download_button`.

### `render_company_assessment()`

Purpose:
- Full UI flow for company compliance assessment.

Detailed flow:
1. Renders form.
2. Waits for "Run Regulatory Assessment" button.
3. Validates form.
4. Converts form data into company profile.
5. Shows progress bar.
6. Calls `find_regulations`.
7. Shows matched regulations.
8. Calls `assess_impact`.
9. Saves assessment if successful.
10. Displays final report.

### `render_latest_regulations()`

Purpose:
- Shows latest parsed regulations from RSS articles.

Detailed flow:
1. Provides impact filter.
2. Provides result limit slider.
3. Queries `parsed_articles` joined with `articles`.
4. Orders by latest fetched articles.
5. Displays each result in an expander.

Difference from Daily Radar:
- This is a simpler latest-regulations list.
- Daily Radar in `radar.py` is richer and more news-brief oriented.

### `render_database_stats()`

Purpose:
- Shows database-level system statistics.

Sections:
- total RSS articles
- AI parsed articles
- high impact count
- Tavily article count
- impact distribution
- top regulations in database

### `main()`

Purpose:
- Main Streamlit entry point.

Detailed flow:
1. Calls `load_rag`.
2. Renders header.
3. Renders sidebar.
4. Creates five tabs:
   - Company Assessment
   - Latest Regulations
   - Database Stats
   - ESG chat
   - Daily Radar
5. Calls the correct renderer inside each tab.

## `impact_assesment.py`

This is a command-line version of company impact assessment.

Note:
- The filename has a spelling mistake: `assesment` instead of `assessment`.
- The Streamlit app has its own similar assessment logic inside `dashboard.py`.

### `assess_impact(company_profile, regulations)`

Purpose:
- Generates an AI assessment from a company profile and RAG results.

Similar to:
- `dashboard.py` `assess_impact`.

### `setup_db()`

Purpose:
- Creates `impact_assessments`.

Note:
- Its schema includes `risk_level`, but `save_assessment` does not insert `risk_level`.

### `save_assessment(conn, company, assessment, regulations)`

Purpose:
- Saves one CLI-generated assessment.

### `run_impact_assessment(company_profile)`

Purpose:
- Full command-line flow.

Detailed flow:
1. Finds relevant regulations using `find_relevant_regulations`.
2. Generates assessment using Groq.
3. Saves result to database.
4. Prints final report.

When run directly:
- Loads ChromaDB.
- Asks user for company details in terminal.
- Runs assessment.

## `demo.py`

This is a small database inspection script.

It:
- Counts total parsed articles.
- Counts high, medium, and low impact articles.
- Prints distinct jurisdictions from `parsed_articles`.

Purpose:
- Quick debugging / demo script.

It is not used by the Streamlit app.

## `file1.py`

This appears to be an older or alternate RAG pipeline implementation.

Important:
- `dashboard.py` imports from `rag_pipeline.py`, not `file1.py`.
- So `rag_pipeline.py` is the active app pipeline.

What `file1.py` contains:
- More extensive normalization helpers.
- Regulation alias mapping.
- Regulator alias mapping.
- Sector expansion logic.
- Jurisdiction alias logic.
- ChromaDB loading and ranking.

Useful functions in `file1.py`:
- `normalize_jurisdiction`
- `canonical_regulation_name`
- `canonical_regulator`
- `expand_sector_terms`
- `company_jurisdiction_targets`
- `jurisdiction_score`
- `build_article_document`
- `find_relevant_regulations`

How to treat it:
- Keep it as reference unless the team intentionally decides to replace `rag_pipeline.py` with this richer implementation.
- Do not assume changes here affect the app.

## `chroma_db/`

This is generated ChromaDB vector index data.

Purpose:
- Stores embeddings and vector search index files.

Important:
- Do not manually edit these files.
- They are produced by `rag_pipeline.py`.
- If the index becomes stale, rerun the RAG loading step.

## `esg_radar.db`

This is the SQLite database.

Purpose:
- Stores raw RSS articles, parsed regulations, Tavily results, fetch logs, and assessments.

Important:
- The app depends heavily on this file.
- If it is deleted, the pipeline must be rerun from ingestion/parser/Tavily steps.

## `esg_articles.json`

This looks like a saved/exported article data file.

Current app usage:
- It is not imported by the active Python files inspected here.

How to treat it:
- Likely historical/export/demo data.
- Confirm before deleting.

## `sustainability_keywords.pdf`

This is the keyword source document.

Used by:
- `keyword_extractor.py`
- `data_ingestion.py`
- `tavily_collector.py`

Why it matters:
- It controls what the collector considers ESG-relevant.

## `__pycache__/`

Generated Python bytecode cache.

Important:
- Not hand-written source.
- Safe to ignore for understanding project logic.

## 5. Daily Radar / Top News Fetcher Deep Dive

The phrase "top news fetcher" maps to two separate responsibilities:

1. Fetching news/data
   - RSS fetching: `data_ingestion.py`
   - Tavily fetching: `tavily_collector.py`

2. Displaying top news
   - Daily Radar display: `radar.py`

### RSS top news pipeline

```text
RSS_FEEDS in config.py
        |
        v
data_ingestion.py run_ingestion()
        |
        v
extract_keywords_from_pdf()
        |
        v
fetch_from_feed()
        |
        v
check_relevance()
        |
        v
save_article()
        |
        v
articles table
```

How RSS articles become "top":
- During ingestion, each article gets a `relevance_score`.
- This score is the number of matched keywords.
- `run_ingestion()` prints the top 5 by `relevance_score`.
- Later, `parser.py` only parses articles with `relevance_score >= 2`.

### Parsed regulation pipeline

```text
articles table
        |
        v
parser.py run_parser()
        |
        v
parse_article()
        |
        v
parsed_articles table
```

How parsed regulations become top Daily Radar updates:
- `radar.py` joins `parsed_articles` with `articles`.
- It orders by impact level first:
  - high
  - medium
  - low
- Then it orders by `a.fetched_at DESC`.
- So a high-impact older item can appear above a newer low-impact item.

### Tavily latest web intelligence pipeline

```text
sustainability_keywords.pdf
        |
        v
tavily_collector.py build_search_queries()
        |
        v
search_regulations()
        |
        v
tavily_articles table
        |
        v
radar.py Latest Web Intelligence section
```

How Tavily results become top:
- Tavily gives each result a `relevance_score`.
- Daily Radar only displays results with `relevance_score >= 0.85`.
- It orders by:
  - highest relevance score
  - newest fetch time
- It displays the top 5.

## 6. Important App Screens and Where They Come From

### Company Assessment tab

File:
- `dashboard.py`

Main function:
- `render_company_assessment`

Backend functions:
- `find_regulations`
- `rag_pipeline.find_relevant_regulations`
- `assess_impact`
- `save_assessment`

### Latest Regulations tab

File:
- `dashboard.py`

Main function:
- `render_latest_regulations`

Data source:
- `parsed_articles` joined with `articles`

### Database Stats tab

File:
- `dashboard.py`

Main function:
- `render_database_stats`

Data source:
- SQLite table counts and grouped queries

### ESG chat tab

Files:
- `dashboard.py`
- `qa_rag.py`

Main object:
- `agent`

Tools:
- `esg_rag_tool`
- `duckduckgo_tool`

### Daily Radar tab

Files:
- `dashboard.py`
- `radar.py`

Main function:
- `render_daily_radar`

Data source:
- `parsed_articles`
- `articles`
- `tavily_articles`

## 7. How to Run the Project

There is no requirements file in the current repository, so dependencies must already be installed in the local virtual environment or installed manually.

Typical commands:

```powershell
python data_ingestion.py
python parser.py
python tavily_collector.py
python rag_pipeline.py
streamlit run dashboard.py
```

Recommended order:

1. Run `data_ingestion.py`
2. Run `parser.py`
3. Run `tavily_collector.py`
4. Run `rag_pipeline.py`
5. Run `streamlit run dashboard.py`

## 8. External Services and Keys

The project uses:

- Groq
  - Used by `parser.py`, `dashboard.py`, `impact_assesment.py`, and `qa_rag.py`.
  - Generates structured parsed data and compliance reports.

- Tavily
  - Used by `tavily_collector.py`.
  - Fetches web intelligence.

- DuckDuckGo via `ddgs`
  - Used by `qa_rag.py`.
  - Supports general ESG chat questions.

Important security note:
- Some files currently contain hardcoded Groq API keys.
- For team/project safety, these should be moved into `.env` and loaded with `os.getenv`.

## 9. Common Debugging Guide

### No articles in dashboard

Check:
- Did `data_ingestion.py` run?
- Does `articles` table have rows?
- Are keywords being extracted from the PDF?
- Are RSS feeds reachable?

### Daily Radar shows no regulatory updates

Check:
- Does `parsed_articles` have rows?
- Did `parser.py` run successfully?
- Did articles have `relevance_score >= 2`?
- Are filters too narrow?

### Tavily section is empty

Check:
- Did `tavily_collector.py` run?
- Is `TAVILY_API_KEY` available?
- Are results below `0.85` relevance score?

### Company assessment finds no regulations

Check:
- Did `rag_pipeline.py` load articles into ChromaDB?
- Does `chroma_db` contain indexed data?
- Does the company profile have enough sector/jurisdiction/description detail?

### ESG chat fails

Check:
- Is Groq key valid?
- Is ChromaDB loaded?
- Is `ddgs` installed?
- Is network access available for DuckDuckGo queries?

## 10. Key Things a Teammate Should Remember

- `dashboard.py` is the main Streamlit entry point.
- `radar.py` renders the Daily Radar tab but does not fetch RSS/Tavily data itself.
- `data_ingestion.py` collects RSS articles.
- `parser.py` converts raw RSS articles into structured regulations.
- `tavily_collector.py` collects web intelligence.
- `rag_pipeline.py` is the active vector search / company matching pipeline.
- `qa_rag.py` powers the chat agent.
- `file1.py` looks like an alternate or older RAG implementation and is not used by the main app.
- `esg_radar.db` and `chroma_db/` are generated data stores, not primary source code.

