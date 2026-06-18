import json
import re
import sqlite3
from datetime import datetime

import chromadb
from chromadb.errors import NotFoundError
from sentence_transformers import SentenceTransformer

from config import DATABASE, CHROMA_PATH, COLLECTION_NAME

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "by",
    "for", "from", "in", "is", "of", "on", "or",
    "the", "to", "with",
}

print("Loading embedding model...")
model = SentenceTransformer("all-MiniLM-L6-v2")
print("Model loaded!")

chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)

# ============================================
# COLLECTION
# ============================================

def get_collection(rebuild=False):
    if rebuild:
        try:
            chroma_client.delete_collection(COLLECTION_NAME)
        except NotFoundError:
            pass
    return chroma_client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

# ============================================
# HELPERS
# ============================================

def tokenize(text):
    return {
        token
        for token in re.findall(r"[a-z0-9]+", (text or "").lower())
        if token not in STOPWORDS and len(token) > 1
    }

def parse_json_list(value):
    if not value:
        return []
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    except json.JSONDecodeError:
        pass
    return [str(value)]

def clean_value(value, fallback):
    value = str(value or "").strip()
    if value.lower() in {"", "none", "null", "unknown"}:
        return fallback
    return value

# ============================================
# REGULATION EXTRACTION FROM QUERY
# (Dynamic — no hardcoding!)
# ============================================

def extract_regulation_from_query(query):
    """Query se regulation name dynamically nikalo"""
    if not query:
        return "General ESG"

    reg_keywords = [
        'CSRD', 'TCFD', 'TNFD', 'GRI', 'ISSB',
        'SFDR', 'CBAM', 'CSDDD', 'BRSR', 'SEBI',
        'SEC', 'ESRS', 'SASB', 'CDP', 'SBTi',
        'DORA', 'SFDR', 'EBA', 'ESMA'
    ]

    query_upper = query.upper()
    for reg in reg_keywords:
        if reg in query_upper:
            return reg

    return "General ESG"

def extract_jurisdiction_from_query(query):
    """Query se jurisdiction dynamically nikalo"""
    if not query:
        return "Global"

    # Dynamic mapping — easily extendable
    jurisdiction_map = {
        'india': 'India',
        'brsr': 'India',
        'sebi': 'India',
        'eu ': 'EU',
        'csrd': 'EU',
        'esrs': 'EU',
        'cbam': 'EU',
        'uk': 'UK',
        'tcfd': 'UK/Global',
        'sec': 'US',
        'california': 'US',
        'singapore': 'Singapore',
        'global': 'Global',
    }

    query_lower = query.lower()
    for key, value in jurisdiction_map.items():
        if key in query_lower:
            return value

    return "Global"

# ============================================
# BUILD DOCUMENT — PARSED ARTICLES
# ============================================

def build_document(row):
    (
        parsed_id, article_id, regulation_name,
        jurisdiction, regulator, change_type,
        sectors_json, impact_level, summary,
        action_required, title, source,
    ) = row

    sectors = parse_json_list(sectors_json)
    regulation_name = clean_value(regulation_name, "General ESG")
    jurisdiction = clean_value(jurisdiction, "Global")
    regulator = clean_value(regulator, "Not specified")
    change_type = clean_value(change_type, "other")
    impact_level = clean_value(impact_level, "medium").lower()

    document = f"""
Title: {title or ""}
Regulation: {regulation_name}
Jurisdiction: {jurisdiction}
Regulator: {regulator}
Change type: {change_type}
Impact level: {impact_level}
Affected sectors: {", ".join(sectors) if sectors else "all sectors"}
Summary: {summary or ""}
Action required: {action_required or ""}
Source: {source or ""}
""".strip()

    metadata = {
        "article_id": str(article_id),
        "regulation_name": regulation_name,
        "jurisdiction": jurisdiction,
        "regulator": regulator,
        "change_type": change_type,
        "impact_level": impact_level,
        "affected_sectors": ", ".join(sectors) if sectors else "all sectors",
        "title": str(title or ""),
        "source": str(source or ""),
        "data_type": "parsed"
    }

    return f"parsed_{parsed_id}", document, metadata

# ============================================
# BUILD DOCUMENT — TAVILY ARTICLES
# ============================================

def build_tavily_document(row):
    (tid, title, content, url,
     source, query_used, score) = row

    regulation = extract_regulation_from_query(query_used)
    jurisdiction = extract_jurisdiction_from_query(query_used)

    document = f"""
Title: {title or ""}
Content: {content or ""}
Regulation: {regulation}
Jurisdiction: {jurisdiction}
Query: {query_used or ""}
""".strip()

    metadata = {
        "article_id": str(tid),
        "regulation_name": regulation,
        "jurisdiction": jurisdiction,
        "regulator": "Not specified",
        "change_type": "update",
        "impact_level": "medium",
        "affected_sectors": "all sectors",
        "title": str(title or ""),
        "source": str(source or url or ""),
        "data_type": "tavily"
    }

    return f"tavily_{tid}", document, metadata

# ============================================
# LOAD ALL INTO CHROMADB
# ============================================

def load_articles_to_chroma(rebuild=True):
    print("\nLoading all articles into ChromaDB...")

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Parsed articles
    cursor.execute("""
        SELECT
            p.id, p.article_id, p.regulation_name,
            p.jurisdiction, p.regulator, p.change_type,
            p.affected_sectors, p.impact_level,
            p.summary, p.action_required,
            a.title, a.source
        FROM parsed_articles p
        JOIN articles a ON p.article_id = a.id
    """)
    parsed_rows = cursor.fetchall()
    print(f"📋 Parsed articles : {len(parsed_rows)}")

    # Tavily articles
    cursor.execute("""
        SELECT id, title, content, url,
               source, query_used, relevance_score
        FROM tavily_articles
        WHERE relevance_score >= 0.7
        ORDER BY relevance_score DESC
    """)
    tavily_rows = cursor.fetchall()
    print(f"🌐 Tavily articles : {len(tavily_rows)}")

    conn.close()

    if not parsed_rows and not tavily_rows:
        print("❌ No articles found!")
        return

    ids, documents, metadatas = [], [], []

    # Parsed articles process karo
    for row in parsed_rows:
        doc_id, document, metadata = build_document(row)
        ids.append(doc_id)
        documents.append(document)
        metadatas.append(metadata)

    # Tavily articles process karo
    for row in tavily_rows:
        doc_id, document, metadata = build_tavily_document(row)
        ids.append(doc_id)
        documents.append(document)
        metadatas.append(metadata)

    # ChromaDB mein load karo
    collection = get_collection(rebuild=rebuild)

    batch_size = 50
    for i in range(0, len(ids), batch_size):
        collection.upsert(
            ids=ids[i:i+batch_size],
            documents=documents[i:i+batch_size],
            metadatas=metadatas[i:i+batch_size]
        )
        print(f"   ✅ {min(i+batch_size, len(ids))}/{len(ids)} loaded")

    print(f"\n✅ Total in ChromaDB: {collection.count()}")

# ============================================
# SCORING
# ============================================

def jurisdiction_fit(company_jurisdiction, article_jurisdiction, company_text):
    company_jurisdiction = (company_jurisdiction or "").lower()
    article_jurisdiction = (article_jurisdiction or "").lower()
    company_text = (company_text or "").lower()

    if not article_jurisdiction or article_jurisdiction == "global":
        return 0.65
    if company_jurisdiction and company_jurisdiction in article_jurisdiction:
        return 1.0
    if article_jurisdiction in company_text:
        return 0.85
    if "global" in article_jurisdiction:
        return 0.65
    return 0.25

def keyword_score(company_profile, metadata, document):
    company_text = " ".join([
        company_profile.get("name", ""),
        company_profile.get("sector", ""),
        company_profile.get("jurisdiction", ""),
        company_profile.get("description", ""),
    ])
    article_text = " ".join([
        metadata.get("title", ""),
        metadata.get("regulation_name", ""),
        metadata.get("affected_sectors", ""),
        document,
    ])

    company_tokens = tokenize(company_text)
    article_tokens = tokenize(article_text)
    matched = sorted(company_tokens & article_tokens)

    if not company_tokens:
        return 0.0, []

    score = len(matched) / len(company_tokens)
    return min(score, 1.0), matched[:8]

def hybrid_score(company_profile, metadata, document, distance):
    semantic = max(0.0, 1.0 - distance)
    lexical, matched_terms = keyword_score(
        company_profile, metadata, document
    )

    company_text = " ".join([
        company_profile.get("sector", ""),
        company_profile.get("description", ""),
    ])
    geo = jurisdiction_fit(
        company_profile.get("jurisdiction", ""),
        metadata.get("jurisdiction", ""),
        company_text,
    )

    impact_bonus = {
        "high": 0.05,
        "medium": 0.03,
        "low": 0.0
    }.get(metadata.get("impact_level", "medium"), 0.0)

    score = (
        (semantic * 0.65) +
        (lexical * 0.2) +
        (geo * 0.15) +
        impact_bonus
    )
    return score, semantic, lexical, geo, matched_terms

# ============================================
# FIND REGULATIONS
# ============================================

def build_query(company_profile):
    return f"""
Company: {company_profile.get("name", "")}
Sector: {company_profile.get("sector", "")}
Jurisdiction: {company_profile.get("jurisdiction", "")}
Size: {company_profile.get("size", "")}
Description: {company_profile.get("description", "")}
Relevant ESG regulations, sustainability reporting,
climate disclosure, compliance obligations,
regulator updates and deadlines.
""".strip()

def find_relevant_regulations(company_profile, top_k=10):
    print(f"\nFinding regulations for: {company_profile['name']}")

    collection = get_collection()
    total = collection.count()
    if total == 0:
        print("❌ ChromaDB empty! Run load first.")
        return []

    query = build_query(company_profile)
    n_results = min(total, max(top_k * 5, 20))

    results = collection.query(
        query_texts=[query],
        n_results=n_results,
        include=["metadatas", "documents", "distances"],
    )

    ranked = []
    for metadata, document, distance in zip(
        results["metadatas"][0],
        results["documents"][0],
        results["distances"][0],
    ):
        score, semantic, lexical, geo, matched_terms = hybrid_score(
            company_profile, metadata, document, distance
        )

        ranked.append({
            "score": round(score * 100, 1),
            "semantic": round(semantic * 100, 1),
            "keyword": round(lexical * 100, 1),
            "jurisdiction_fit": round(geo * 100, 1),
            "matched_terms": ", ".join(matched_terms),
            "regulation_name": metadata["regulation_name"],
            "jurisdiction": metadata["jurisdiction"],
            "regulator": metadata["regulator"],
            "impact_level": metadata["impact_level"],
            "change_type": metadata["change_type"],
            "affected_sectors": metadata["affected_sectors"],
            "title": metadata["title"],
            "source": metadata["source"],
            "data_type": metadata.get("data_type", "parsed")
        })

    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked[:top_k]

# ============================================
# DISPLAY
# ============================================

def display_results(company_profile, regulations):
    print("\n" + "=" * 60)
    print(f"COMPANY : {company_profile['name']}")
    print(f"Sector  : {company_profile['sector']}")
    print(f"Location: {company_profile['jurisdiction']}")
    print("=" * 60)

    if not regulations:
        print("No relevant regulations found.")
        return

    print("\nTOP RELEVANT REGULATIONS:\n")

    for index, reg in enumerate(regulations, 1):
        source_tag = "📡" if reg['data_type'] == "parsed" else "🌐"
        impact_emoji = {
            "high": "🔴", "medium": "🟡", "low": "🟢"
        }.get(reg['impact_level'], "⚪")

        print(f"{index}. {impact_emoji} [{reg['impact_level'].upper()}] "
              f"{reg['regulation_name']} {source_tag}")
        print(f"   📰 {reg['title'][:65]}...")
        print(f"   Score: {reg['score']}% "
              f"| Semantic: {reg['semantic']}% "
              f"| Keyword: {reg['keyword']}% "
              f"| Geo: {reg['jurisdiction_fit']}%")
        print(f"   🌍 {reg['jurisdiction']} "
              f"| {reg['regulator']} "
              f"| {reg['change_type']}")
        if reg["matched_terms"]:
            print(f"   🔑 Matched: {reg['matched_terms']}")
        print()

# ============================================
# MAIN
# ============================================

def run_rag():
    print("\n" + "=" * 60)
    print("ZenESG — Hybrid RAG Pipeline v2")
    print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 60)

    load_articles_to_chroma(rebuild=True)

    # Test companies — config se load hongi production mein
    # Ab ke liye 3 test cases
    test_companies = [
        {
            "name": "ABC Investment Management",
            "sector": "investment management",
            "jurisdiction": "UK",
            "size": "large",
            "description": "UK based asset manager managing investment products",
        },
        {
            "name": "XYZ Steel India",
            "sector": "steel manufacturing",
            "jurisdiction": "India",
            "size": "large",
            "description": "Indian steel company exporting to EU markets",
        },
        {
            "name": "GreenTech Solutions",
            "sector": "renewable energy",
            "jurisdiction": "EU",
            "size": "medium",
            "description": "European renewable energy company",
        },
    ]

    for company in test_companies:
        regulations = find_relevant_regulations(company, top_k=5)
        display_results(company, regulations)
        print("-" * 60)

if __name__ == "__main__":
    run_rag()