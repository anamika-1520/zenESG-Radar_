from tavily import TavilyClient
import sqlite3
import json
import os
from datetime import datetime
from dotenv import load_dotenv
from keyword_extractor import extract_keywords_from_pdf
from config import DATABASE, KEYWORDS_PDF

# Setup
load_dotenv()
client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

# ============================================
# DATABASE
# ============================================

def setup_db():
    conn = sqlite3.connect(DATABASE)
    conn.cursor().execute("""
        CREATE TABLE IF NOT EXISTS tavily_articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            content TEXT,
            url TEXT UNIQUE,
            source TEXT,
            query_used TEXT,
            relevance_score REAL,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn

# ============================================
# SMART QUERIES FROM PDF KEYWORDS
# ============================================

def build_search_queries(keywords):
    """
    PDF keywords se smart search queries banao
    No hardcoding — sab dynamic!
    """

    # Most important regulatory keywords
    # Automatically top ones pick karo
    regulatory_keywords = [
        kw for kw in keywords
        if any(term in kw.upper() for term in [
            'CSRD', 'TCFD', 'TNFD', 'GRI', 'ISSB',
            'SFDR', 'CBAM', 'CSDDD', 'BRSR', 'SEBI',
            'SEC', 'ESRS', 'SASB', 'CDP', 'SBTi',
            'REGULATION', 'DIRECTIVE', 'DISCLOSURE',
            'REPORTING', 'COMPLIANCE', 'FRAMEWORK'
        ])
    ][:20]  # Top 20 only — save API calls

    # Search queries banao
    queries = []

    for kw in regulatory_keywords:
        queries.append(f"{kw} latest update 2026")

    # Extra important queries
    queries.extend([
        "ESG regulation changes 2026",
        "climate disclosure requirements 2026",
        "sustainability reporting mandatory 2026",
        "carbon tax policy update 2026",
        "net zero regulation corporate 2026"
    ])

    # Duplicates remove karo
    queries = list(set(queries))

    print(f"✅ {len(queries)} search queries ready!")
    return queries

# ============================================
# TAVILY SEARCH
# ============================================

def search_regulations(query, conn):
    """Ek query search karo aur results save karo"""

    try:
        results = client.search(
            query=query,
            search_depth="advanced",
            max_results=5,
            include_answer=False,
            include_raw_content=False
        )

        saved = 0
        cursor = conn.cursor()

        for result in results.get('results', []):
            title = result.get('title', '')
            content = result.get('content', '')
            url = result.get('url', '')
            source = result.get('source', '')
            score = result.get('score', 0)

            try:
                cursor.execute("""
                    INSERT OR IGNORE INTO tavily_articles
                    (title, content, url, source,
                     query_used, relevance_score)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (title, content, url, source,
                      query, score))
                conn.commit()

                if cursor.rowcount > 0:
                    saved += 1

            except Exception:
                continue

        return saved

    except Exception as e:
        print(f"   ❌ Error: {str(e)[:50]}")
        return 0

# ============================================
# MAIN
# ============================================

def run_tavily_collector():
    print("\n" + "="*55)
    print("🔍 ZenESG — Tavily Regulatory Search")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*55)

    # Step 1: Keywords from PDF
    print("\n📚 Step 1: Loading keywords from PDF...")
    keywords = extract_keywords_from_pdf(KEYWORDS_PDF)
    print(f"✅ {len(keywords)} keywords loaded!")

    # Step 2: Build queries
    print("\n🔧 Step 2: Building search queries...")
    queries = build_search_queries(keywords)

    # Step 3: Database setup
    conn = setup_db()

    # Step 4: Search karo
    print(f"\n🌐 Step 3: Searching {len(queries)} queries...")
    print("(This may take a few minutes...)\n")

    total_saved = 0

    for i, query in enumerate(queries, 1):
        print(f"[{i}/{len(queries)}] 🔍 {query[:50]}...")
        saved = search_regulations(query, conn)
        total_saved += saved
        print(f"   ✅ {saved} new articles saved")

    # Summary
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM tavily_articles")
    total = cursor.fetchone()[0]

    print("\n" + "="*55)
    print("📊 SUMMARY")
    print("="*55)
    print(f"✅ Queries run      : {len(queries)}")
    print(f"✅ New articles     : {total_saved}")
    print(f"✅ Total in DB      : {total}")

    # Top results dikhao
    cursor.execute("""
        SELECT title, source, relevance_score
        FROM tavily_articles
        ORDER BY relevance_score DESC
        LIMIT 5
    """)

    top = cursor.fetchall()
    if top:
        print("\n🏆 TOP 5 MOST RELEVANT:")
        for i, row in enumerate(top, 1):
            print(f"\n{i}. {row[0][:55]}...")
            print(f"   Source: {row[1]}")
            print(f"   Score : {row[2]:.2f}")

    conn.close()
    print("\n✅ Tavily collection complete!")

if __name__ == "__main__":
    run_tavily_collector()