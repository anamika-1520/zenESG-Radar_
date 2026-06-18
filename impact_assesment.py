from langchain_groq import ChatGroq

import sqlite3
import json
import os
from datetime import datetime
from dotenv import load_dotenv
from rag_pipeline import find_relevant_regulations, load_articles_to_chroma
from config import DATABASE

# Setup
load_dotenv()
llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    groq_api_key=os.getenv("GROQ_API_KEY"),
    temperature=0.2,
    max_tokens=1000,
)

# ============================================
# IMPACT ASSESSMENT WITH OPENAI
# ============================================

def assess_impact(company_profile, regulations):
    """
    Company + Regulations do
    Groq se impact assessment lo
    """

    reg_text = ""
    for i, reg in enumerate(regulations, 1):
        reg_text += f"""
{i}. {reg['regulation_name']}
   Jurisdiction: {reg['jurisdiction']}
   Regulator: {reg['regulator']}
   Change Type: {reg['change_type']}
   Impact Level: {reg['impact_level']}
   Article: {reg['title']}
   Match Score: {reg['score']}%
"""

    prompt = f"""You are a senior ESG regulatory compliance advisor.

COMPANY PROFILE:
- Name: {company_profile.get('name')}
- Sector: {company_profile.get('sector')}
- Location: {company_profile.get('jurisdiction')}
- Size: {company_profile.get('size')}
- Description: {company_profile.get('description')}

RELEVANT REGULATIONS FOUND:
{reg_text}

Please provide:
1. OVERALL RISK LEVEL: (Critical/High/Medium/Low)
2. TOP 3 MOST URGENT REGULATIONS for this company specifically
3. IMMEDIATE ACTION CHECKLIST (5-7 specific actions this company must take NOW)
4. DEADLINE SUMMARY (what needs to be done by when)
5. ESTIMATED COMPLIANCE EFFORT (Low/Medium/High effort required)

Be specific to this company's sector and jurisdiction.
Focus on actionable, practical advice.
"""

    try:
        response = llm.invoke([
            (
                "system",
                "You are a senior ESG regulatory compliance advisor. Give specific, actionable advice based on the company profile and regulations provided."
            ),
            ("human", prompt)
        ])

        return response.content

    except Exception as e:
        print(f"❌ Groq Error: {e}")
        return None
# ============================================
# SAVE TO DATABASE
# ============================================

def setup_db():
    conn = sqlite3.connect(DATABASE)
    conn.cursor().execute("""
        CREATE TABLE IF NOT EXISTS impact_assessments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT,
            company_sector TEXT,
            company_jurisdiction TEXT,
            risk_level TEXT,
            assessment TEXT,
            regulations_used TEXT,
            assessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn

def save_assessment(conn, company, assessment, regulations):
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO impact_assessments
        (company_name, company_sector, company_jurisdiction,
         assessment, regulations_used)
        VALUES (?, ?, ?, ?, ?)
    """, (
        company.get('name'),
        company.get('sector'),
        company.get('jurisdiction'),
        assessment,
        json.dumps([r['regulation_name'] for r in regulations])
    ))
    conn.commit()

# ============================================
# MAIN
# ============================================

def run_impact_assessment(company_profile):
    """
    Ek company ka impact assessment karo
    """

    print("\n" + "="*60)
    print("⚡ ZenESG — Impact Assessment Engine")
    print(f"🏢 Company: {company_profile['name']}")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)

    # Step 1: RAG se regulations fetch karo
    print("\n🔍 Step 1: Finding relevant regulations...")
    regulations = find_relevant_regulations(
        company_profile,
        top_k=5
    )

    if not regulations:
        print("❌ No regulations found!")
        return

    print(f"✅ Found {len(regulations)} relevant regulations")

    # Step 2: Impact assess karo
    print("\n🤖 Step 2: Assessing impact with AI...")
    assessment = assess_impact(company_profile, regulations)

    # Step 3: Save karo
    print("\n💾 Step 3: Saving assessment...")
    conn = setup_db()
    save_assessment(conn, company_profile, assessment, regulations)
    conn.close()

    # Step 4: Display karo
    print("\n" + "="*60)
    print("📊 IMPACT ASSESSMENT REPORT")
    print("="*60)
    print(f"\n🏢 Company  : {company_profile['name']}")
    print(f"🏭 Sector   : {company_profile['sector']}")
    print(f"🌍 Location : {company_profile['jurisdiction']}")
    print("\n" + "-"*60)
    print(assessment)
    print("="*60)

    return assessment

# ============================================
# TEST
# ============================================

if __name__ == "__main__":

    # ChromaDB load karo pehle
    print("Loading ChromaDB...")
    load_articles_to_chroma(rebuild=False)

    # Test companies — terminal se input lo!
    print("\n" + "="*60)
    print("🏢 Enter Company Details")
    print("="*60)

    company = {
        "name": input("Company name: "),
        "sector": input("Sector (e.g. steel, investment, renewable energy): "),
        "jurisdiction": input("Country/Region (e.g. India, UK, EU): "),
        "size": input("Size (small/medium/large): "),
        "description": input("Brief description: ")
    }

    # Assessment run karo
    run_impact_assessment(company)
