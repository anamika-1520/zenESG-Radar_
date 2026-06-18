import json
import re
import sqlite3
from datetime import datetime

import chromadb
from chromadb.errors import NotFoundError
from sentence_transformers import SentenceTransformer

from config import DATABASE


COLLECTION_NAME = "esg_regulations"
CHROMA_PATH = "./chroma_db"

REGULATION_ALIASES = {
    "tcfd": "TCFD",
    "task force on climate-related financial disclosures": "TCFD",
    "csrd": "CSRD",
    "corporate sustainability reporting directive": "CSRD",
    "esrs": "ESRS",
    "issb": "ISSB",
    "ifrs s1": "ISSB",
    "ifrs s2": "ISSB",
    "sdr": "SDR",
    "sustainability disclosure requirements": "SDR",
    "sfdr": "SFDR",
    "taxonomy": "EU Taxonomy",
    "eu taxonomy": "EU Taxonomy",
    "cbam": "CBAM",
    "carbon border adjustment": "CBAM",
    "brsr": "BRSR",
    "business responsibility and sustainability reporting": "BRSR",
    "sb 261": "SB 261",
    "dora": "DORA",
    "paris agreement": "Paris Agreement",
}

REGULATOR_ALIASES = {
    "financial conduct authority": "FCA",
    " fca ": "FCA",
    "sebi": "SEBI",
    "securities and exchange board of india": "SEBI",
    "european commission": "European Commission",
    "efrag": "EFRAG",
    "issb": "ISSB",
    "u.s. sec": "SEC",
    "us sec": "SEC",
    "securities and exchange commission": "SEC",
    "carb": "CARB",
}

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "based",
    "by",
    "company",
    "for",
    "from",
    "in",
    "is",
    "it",
    "its",
    "ltd",
    "of",
    "on",
    "or",
    "the",
    "this",
    "to",
    "with",
}

SECTOR_EXPANSIONS = {
    "investment management": [
        "asset manager",
        "investment",
        "fund",
        "portfolio",
        "investor",
        "finance",
        "financial",
        "banking",
        "insurance",
        "tcfd",
        "sdr",
        "issb",
        "esrs",
        "disclosure",
    ],
    "steel manufacturing": [
        "steel",
        "manufacturing",
        "industrial",
        "metals",
        "iron",
        "mining",
        "energy",
        "emissions",
        "carbon",
        "cbam",
        "supply chain",
        "export",
    ],
    "renewable energy": [
        "renewable",
        "energy",
        "clean energy",
        "electricity",
        "power",
        "grid",
        "climate",
        "transition",
        "utilities",
        "taxonomy",
    ],
}

JURISDICTION_ALIASES = {
    "united kingdom": "UK",
    "great britain": "UK",
    "england": "UK",
    "u.k.": "UK",
    "uk": "UK",
    "european union": "EU",
    "europe": "EU",
    "eu": "EU",
    "u.s.": "US",
    "usa": "US",
    "united states": "US",
    "global": "Global",
    "international": "Global",
    "world": "Global",
    "india": "India",
}


print("Loading embedding model...")
model = SentenceTransformer("all-MiniLM-L6-v2")
print("Model loaded!")

chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
collection = None


def get_collection(recreate=False):
    global collection
    if recreate:
        try:
            chroma_client.delete_collection(COLLECTION_NAME)
        except NotFoundError:
            pass
        collection = None

    if collection is None:
        collection = chroma_client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
    return collection


def clean_tokens(text):
    return {
        token
        for token in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)?", (text or "").lower())
        if token not in STOPWORDS and len(token) > 1
    }


def normalize_jurisdiction(value):
    if not value:
        return "Global"

    raw_parts = re.split(r"[,/;|]|\band\b", str(value), flags=re.I)
    normalized = []
    for part in raw_parts:
        key = part.strip().lower()
        if not key:
            continue
        normalized.append(JURISDICTION_ALIASES.get(key, part.strip()))

    if not normalized:
        return "Global"
    return ", ".join(dict.fromkeys(normalized))


def canonical_regulation_name(name, title="", summary=""):
    if name and str(name).strip().lower() not in {"none", "null", "unknown"}:
        return str(name).strip()

    haystack = f" {title or ''} {summary or ''} ".lower()
    for needle, label in REGULATION_ALIASES.items():
        if needle in haystack:
            return label
    return "General ESG"


def canonical_regulator(regulator, title="", summary="", source=""):
    if regulator and str(regulator).strip().lower() not in {"none", "null", "unknown"}:
        return str(regulator).strip()

    haystack = f" {title or ''} {summary or ''} {source or ''} ".lower()
    padded = f" {haystack} "
    for needle, label in REGULATOR_ALIASES.items():
        if needle.strip() in padded:
            return label
    return "Not specified"


def parse_sectors(sectors_json):
    if not sectors_json:
        return []
    try:
        sectors = json.loads(sectors_json)
    except json.JSONDecodeError:
        sectors = [sectors_json]
    return [str(item).strip() for item in sectors if str(item).strip()]


def expand_sector_terms(sector):
    sector_l = (sector or "").lower()
    terms = clean_tokens(sector_l)
    for key, values in SECTOR_EXPANSIONS.items():
        if key in sector_l or any(token in sector_l for token in clean_tokens(key)):
            for value in values:
                terms.update(clean_tokens(value))
    return terms


def company_jurisdiction_targets(company_profile):
    jurisdiction = normalize_jurisdiction(company_profile.get("jurisdiction"))
    description = f"{company_profile.get('description', '')} {company_profile.get('sector', '')}".lower()
    targets = {jurisdiction: 1.0, "Global": 0.65}

    if jurisdiction == "India":
        targets.update({"Asia": 0.45, "Southeast Asia": 0.35})
        if "export" in description or "eu" in description or "europe" in description:
            targets["EU"] = 0.85
    elif jurisdiction == "UK":
        targets.update({"EU": 0.35, "EMEA": 0.35})
    elif jurisdiction == "EU":
        targets.update({"Europe, Middle East and Africa": 0.45, "EMEA": 0.45})
    elif jurisdiction == "US":
        targets.update({"California": 0.45, "New York": 0.35})

    return targets


def jurisdiction_score(article_jurisdiction, targets):
    article = normalize_jurisdiction(article_jurisdiction)
    parts = {part.strip() for part in article.split(",") if part.strip()}
    scores = [targets.get(part, 0.0) for part in parts]
    if "Global" in parts:
        scores.append(targets.get("Global", 0.65))
    return max(scores or [0.0])


def build_article_document(row):
    (
        pid,
        article_id,
        reg_name,
        jurisdiction,
        regulator,
        change_type,
        sectors_json,
        impact_level,
        summary,
        action_required,
        title,
        source,
    ) = row

    sectors = parse_sectors(sectors_json)
    clean_reg_name = canonical_regulation_name(reg_name, title, summary)
    clean_jurisdiction = normalize_jurisdiction(jurisdiction)
    clean_regulator = canonical_regulator(regulator, title, summary, source)

    document = f"""
Title: {title or ""}
Regulation: {clean_reg_name}
Jurisdiction: {clean_jurisdiction}
Regulator: {clean_regulator}
Affected sectors: {", ".join(sectors) if sectors else "all sectors"}
Change type: {change_type or "other"}
Impact: {impact_level or "medium"}
Summary: {summary or ""}
Required action: {action_required or ""}
Source: {source or ""}
""".strip()

    metadata = {
        "parsed_id": str(pid),
        "article_id": str(article_id),
        "regulation_name": clean_reg_name,
        "jurisdiction": clean_jurisdiction,
        "regulator": clean_regulator,
        "change_type": str(change_type or "other"),
        "impact_level": str(impact_level or "medium").lower(),
        "affected_sectors": ", ".join(sectors) if sectors else "all sectors",
        "source": str(source or ""),
        "title": str(title or ""),
    }

    return document, metadata, f"article_{pid}"


def load_articles_to_chroma(force_rebuild=True):
    """Load parsed articles into ChromaDB with normalized metadata."""

    print("\nLoading articles into ChromaDB...")

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            p.id,
            p.article_id,
            p.regulation_name,
            p.jurisdiction,
            p.regulator,
            p.change_type,
            p.affected_sectors,
            p.impact_level,
            p.summary,
            p.action_required,
            a.title,
            a.source
        FROM parsed_articles p
        JOIN articles a ON p.article_id = a.id
        """
    )
    articles = cursor.fetchall()
    conn.close()

    print(f"Total parsed articles: {len(articles)}")
    active_collection = get_collection(recreate=force_rebuild)

    if not articles:
        print("No parsed articles found. Run parser.py first.")
        return

    documents, metadatas, ids = [], [], []
    for row in articles:
        document, metadata, doc_id = build_article_document(row)
        documents.append(document)
        metadatas.append(metadata)
        ids.append(doc_id)

    print("Creating embeddings and normalized metadata...")
    active_collection.upsert(documents=documents, metadatas=metadatas, ids=ids)
    print(f"Loaded {len(documents)} articles into ChromaDB.")


def build_company_query(company_profile):
    sector = company_profile.get("sector", "")
    jurisdiction = normalize_jurisdiction(company_profile.get("jurisdiction"))
    sector_terms = " ".join(sorted(expand_sector_terms(sector)))
    targets = ", ".join(company_jurisdiction_targets(company_profile).keys())

    return f"""
Company: {company_profile.get('name', '')}
Sector: {sector}
Expanded sector terms: {sector_terms}
Operating jurisdictions and exposure: {jurisdiction}, {targets}
Size: {company_profile.get('size', '')}
Description: {company_profile.get('description', '')}
Find concrete ESG regulations, sustainability reporting rules, climate disclosure
requirements, carbon reporting obligations, regulator consultations, compliance
deadlines, and policy updates relevant to this company.
""".strip()


def lexical_score(company_profile, metadata, document):
    company_terms = expand_sector_terms(company_profile.get("sector", ""))
    company_terms.update(clean_tokens(company_profile.get("description", "")))

    article_text = " ".join(
        [
            metadata.get("title", ""),
            metadata.get("regulation_name", ""),
            metadata.get("affected_sectors", ""),
            document,
        ]
    )
    article_terms = clean_tokens(article_text)

    overlap = company_terms & article_terms
    sector_score = min(len(overlap) * 7.5, 25.0)

    regulation = metadata.get("regulation_name", "")
    signal_score = 8.0 if regulation and regulation != "General ESG" else 0.0

    impact_score = {"high": 6.0, "medium": 3.0, "low": 0.0}.get(
        metadata.get("impact_level", "").lower(),
        1.0,
    )

    return sector_score + signal_score + impact_score, sorted(overlap)[:8]


def find_relevant_regulations(company_profile, top_k=10):
    """Return ranked ESG regulatory updates for a company profile."""

    print(f"\nFinding regulations for: {company_profile['name']}")

    active_collection = get_collection()
    total = active_collection.count()
    if total == 0:
        return []

    query = build_company_query(company_profile)
    candidate_count = total if total <= 250 else min(total, max(top_k * 12, 60))

    results = active_collection.query(
        query_texts=[query],
        n_results=candidate_count,
        include=["metadatas", "documents", "distances"],
    )

    targets = company_jurisdiction_targets(company_profile)
    ranked = []

    for i in range(len(results["ids"][0])):
        metadata = results["metadatas"][0][i]
        document = results["documents"][0][i]
        distance = results["distances"][0][i]
        semantic_similarity = max(0.0, (1 - distance) * 100)

        j_score = jurisdiction_score(metadata.get("jurisdiction"), targets)
        if j_score == 0:
            continue

        lex_score, matched_terms = lexical_score(company_profile, metadata, document)
        final_score = (semantic_similarity * 0.55) + (j_score * 30) + lex_score

        ranked.append(
            {
                "semantic_similarity": round(semantic_similarity, 1),
                "similarity": round(min(final_score, 100), 1),
                "jurisdiction_fit": round(j_score * 100, 0),
                "matched_terms": ", ".join(matched_terms),
                "regulation_name": metadata["regulation_name"],
                "jurisdiction": metadata["jurisdiction"],
                "regulator": metadata["regulator"],
                "impact_level": metadata["impact_level"],
                "change_type": metadata["change_type"],
                "affected_sectors": metadata["affected_sectors"],
                "title": metadata["title"],
                "source": metadata["source"],
            }
        )

    ranked.sort(key=lambda item: item["similarity"], reverse=True)
    for rank, item in enumerate(ranked[:top_k], 1):
        item["rank"] = rank
    return ranked[:top_k]


def display_results(company_profile, regulations):
    print("\n" + "=" * 60)
    print(f"COMPANY: {company_profile['name']}")
    print(f"Sector : {company_profile['sector']}")
    print(f"Location: {company_profile['jurisdiction']}")
    print("=" * 60)

    print("\nTOP RELEVANT REGULATIONS FOUND:\n")

    if not regulations:
        print("No relevant regulations found. Try broadening jurisdiction or parsing more articles.")
        return

    for reg in regulations:
        impact_label = {"high": "HIGH", "medium": "MEDIUM", "low": "LOW"}.get(
            reg["impact_level"], reg["impact_level"].upper()
        )

        print(f"{reg['rank']}. [{impact_label}] {reg['regulation_name']}")
        print(f"   Article: {reg['title'][:70]}...")
        print(
            f"   Jurisdiction: {reg['jurisdiction']} "
            f"| Fit: {reg['jurisdiction_fit']:.0f}% "
            f"| Score: {reg['similarity']}%"
        )
        print(f"   Regulator: {reg['regulator']} | Change: {reg['change_type']}")
        if reg["matched_terms"]:
            print(f"   Matched terms: {reg['matched_terms']}")
        print()


def run_rag():
    print("\n" + "=" * 60)
    print("ZenESG - RAG Pipeline")
    print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 60)

    load_articles_to_chroma(force_rebuild=True)

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
