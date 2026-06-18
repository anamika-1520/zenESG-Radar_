import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime
from radar import render_daily_radar
import streamlit as st
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from qa_rag import hybrid_search,agent
from config import DATABASE
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage


SYSTEM_PROMPT = (
    "You are a senior ESG regulatory compliance advisor. Give specific, "
    "actionable advice based on the company profile and regulations provided."
)

SECTORS = [
    "Select sector...",
    "Steel Manufacturing",
    "Investment Management",
    "Renewable Energy",
    "Banking & Finance",
    "Insurance",
    "Shipping & Maritime",
    "Oil & Gas",
    "Real Estate",
    "Technology",
    "Retail & Consumer",
    "Healthcare",
    "Other",
]

JURISDICTIONS = [
    "Select location...",
    "India",
    "United Kingdom",
    "European Union",
    "United States",
    "Singapore",
    "Australia",
    "Global",
    "Other",
]

IMPACT_DOT = {"high": "Red", "medium": "Yellow", "low": "Green"}


load_dotenv()
llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    groq_api_key=os.getenv("GROQ_API_KEY"),
    temperature=0.2,
)


st.set_page_config(
    page_title="ZenESG - Regulatory Radar",
    page_icon="🌍",
    layout="wide",
)

st.markdown(
    """
<style>
.main-header {
    font-size: 2.5rem;
    font-weight: 700;
    color: #1a5276;
    text-align: center;
    margin-bottom: .35rem;
}
.sub-header {
    font-size: 1rem;
    color: #666;
    text-align: center;
    margin-bottom: 1.5rem;
}
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_resource
def load_rag():
    try:
        from rag_pipeline import load_articles_to_chroma

        with st.spinner("Loading RAG pipeline..."):
            load_articles_to_chroma(rebuild=False)
        return True
    except Exception as exc:
        st.error(f"RAG pipeline load failed: {exc}")
        return False


def find_regulations(company, top_k):
    try:
        from rag_pipeline import find_relevant_regulations

        return find_relevant_regulations(company, top_k=top_k)
    except Exception as exc:
        st.error(f"Regulation search failed: {exc}")
        return []


def fetch_all(query, params=()):
    with closing(sqlite3.connect(DATABASE)) as conn:
        return conn.cursor().execute(query, params).fetchall()


def fetch_count(table, where=""):
    try:
        query = f"SELECT COUNT(*) FROM {table} {where}"
        return fetch_all(query)[0][0]
    except sqlite3.Error:
        return 0


def get_stats():
    return {
        "rss": fetch_count("articles"),
        "parsed": fetch_count("parsed_articles"),
        "high": fetch_count("parsed_articles", "WHERE impact_level = 'high'"),
        "tavily": fetch_count("tavily_articles"),
    }


def get_past_assessments(limit=5):
    try:
        return fetch_all(
            """
            SELECT company_name, company_sector, company_jurisdiction, assessed_at
            FROM impact_assessments
            ORDER BY assessed_at DESC
            LIMIT ?
            """,
            (limit,),
        )
    except sqlite3.Error:
        return []


def save_assessment(company, assessment, regulations):
    with closing(sqlite3.connect(DATABASE)) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS impact_assessments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT,
                company_sector TEXT,
                company_jurisdiction TEXT,
                assessment TEXT,
                regulations_used TEXT,
                assessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            INSERT INTO impact_assessments
                (company_name, company_sector, company_jurisdiction,
                 assessment, regulations_used)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                company.get("name"),
                company.get("sector"),
                company.get("jurisdiction"),
                assessment,
                json.dumps([r.get("regulation_name") for r in regulations]),
            ),
        )
        conn.commit()


def build_regulation_context(regulations):
    lines = []
    for index, reg in enumerate(regulations, 1):
        lines.append(
            f"""
{index}. {reg.get('regulation_name')}
   Jurisdiction: {reg.get('jurisdiction')}
   Regulator: {reg.get('regulator')}
   Impact Level: {reg.get('impact_level')}
   Article: {reg.get('title')}
   Match Score: {reg.get('score')}%
""".strip()
        )
    return "\n\n".join(lines)


def assess_impact(company, regulations):
    if llm is None:
        return "Error: GROQ_API_KEY is missing in your .env file."

    prompt = f"""
COMPANY PROFILE:
- Name: {company.get('name')}
- Sector: {company.get('sector')}
- Location: {company.get('jurisdiction')}
- Size: {company.get('size')}
- Description: {company.get('description')}

RELEVANT REGULATIONS FOUND:
{build_regulation_context(regulations)}

Please provide:
1. OVERALL RISK LEVEL: Critical/High/Medium/Low
2. TOP 3 MOST URGENT REGULATIONS for this company
3. IMMEDIATE ACTION CHECKLIST: 5-7 specific actions
4. DEADLINE SUMMARY: quarterly
5. ESTIMATED COMPLIANCE EFFORT: Low/Medium/High

Be specific to this company's sector and jurisdiction.
""".strip()

    try:
        return llm.invoke([("system", SYSTEM_PROMPT), ("human", prompt)]).content
    except Exception as exc:
        return f"Error: {exc}"


def render_header():
    st.markdown(
        '<p class="main-header">🌍 ZenESG Regulatory Radar</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p class="sub-header">AI-powered ESG compliance intelligence</p>',
        unsafe_allow_html=True,
    )


def render_sidebar():
    stats = get_stats()
    with st.sidebar:
        st.image("https://img.icons8.com/color/96/000000/globe.png", width=80)
        st.title("ZenESG Radar")
        st.markdown("---")
        st.markdown("### System Stats")
        st.metric("RSS Articles", stats["rss"])
        st.metric("Parsed Articles", stats["parsed"])
        st.metric("High Impact", stats["high"])
        st.metric("Tavily Articles", stats["tavily"])
        st.markdown("---")
        st.markdown("### Recent Assessments")
        past_assessments = get_past_assessments()
        for name, sector, jurisdiction, assessed_at in past_assessments:
            st.markdown(f"**{name}**")
            st.caption(f"{sector} | {jurisdiction}")
            st.caption(str(assessed_at)[:16])
            st.markdown("---")
        if not past_assessments:
            st.info("No assessments yet.")


def company_form():
    st.markdown("### Enter Company Profile")
    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("Company Name", placeholder="e.g. ABC Steel Ltd")
        sector = st.selectbox("Sector", SECTORS)
        jurisdiction = st.selectbox("Primary Jurisdiction", JURISDICTIONS)
    with col2:
        size = st.selectbox(
            "Company Size",
            ["Select size...", "Small", "Medium", "Large", "Enterprise"],
        )
        description = st.text_area(
            "Brief Description",
            placeholder="e.g. Indian steel company exporting to EU markets",
            height=100,
        )
        top_k = st.slider("Number of regulations to analyze", 3, 10, 5)

    return {
        "name": name,
        "sector": sector,
        "jurisdiction": jurisdiction,
        "size": size,
        "description": description,
        "top_k": top_k,
    }


def form_is_valid(data):
    return all(
        [
            data["name"],
            data["sector"] != "Select sector...",
            data["jurisdiction"] != "Select location...",
            data["size"] != "Select size...",
        ]
    )


def render_regulation_matches(regulations):
    st.markdown("### Matched Regulations")
    for start in range(0, len(regulations), 4):
        cols = st.columns(min(4, len(regulations) - start))
        for col, reg in zip(cols, regulations[start : start + 4]):
            impact = str(reg.get("impact_level", "")).lower()
            with col:
                st.metric(
                    reg.get("regulation_name") or "General ESG",
                    f"{reg.get('score', 0)}%",
                    reg.get("jurisdiction") or "Global",
                )
                st.caption(f"{IMPACT_DOT.get(impact, 'Grey')} - {impact.upper()}")


def render_report(company, form_data, assessment):
    st.markdown("---")
    st.markdown("### Impact Assessment Report")
    cols = st.columns(3)
    labels = [
        f"**{form_data['name']}**",
        f"**{form_data['sector']}**",
        f"**{form_data['jurisdiction']}**",
    ]
    for col, label in zip(cols, labels):
        with col:
            st.info(label)

    if assessment.startswith("Error:"):
        st.error(assessment)
    else:
        st.markdown(assessment)

    report = f"""
ZenESG Regulatory Radar - Impact Assessment Report
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}

Company: {form_data['name']}
Sector: {form_data['sector']}
Location: {form_data['jurisdiction']}
Size: {form_data['size']}

{assessment}
""".strip()
    st.download_button(
        "Download Report",
        data=report,
        file_name=f"ESG_Report_{company['name']}_{datetime.now():%Y%m%d}.txt",
        mime="text/plain",
    )


def render_company_assessment():
    form_data = company_form()
    st.markdown("---")

    if not st.button("Run Regulatory Assessment", type="primary", use_container_width=True):
        return
    if not form_is_valid(form_data):
        st.error("Please fill all required fields.")
        return

    company = {
        "name": form_data["name"],
        "sector": form_data["sector"].lower(),
        "jurisdiction": form_data["jurisdiction"],
        "size": form_data["size"].lower(),
        "description": form_data["description"],
    }

    progress = st.progress(0)
    status = st.empty()
    status.info("Finding relevant regulations...")
    regulations = find_regulations(company, top_k=form_data["top_k"])
    progress.progress(50)

    if not regulations:
        st.error("No regulations found.")
        return

    render_regulation_matches(regulations)
    status.info("Assessing impact with AI...")
    assessment = assess_impact(company, regulations)
    progress.progress(90)

    if not assessment.startswith("Error:"):
        save_assessment(company, assessment, regulations)
    progress.progress(100)
    status.success("Assessment complete.")
    render_report(company, form_data, assessment)


def render_latest_regulations():
    st.markdown("### Latest ESG Regulations")
    col1, col2 = st.columns(2)
    impact_filter = col1.selectbox("Filter by Impact", ["All", "High", "Medium", "Low"])
    limit = col2.slider("Show articles", 5, 50, 20)

    where = "" if impact_filter == "All" else "WHERE p.impact_level = ?"
    params = (limit,) if impact_filter == "All" else (impact_filter.lower(), limit)
    try:
        rows = fetch_all(
            f"""
            SELECT p.regulation_name, p.jurisdiction, p.impact_level,
                   p.action_required, a.title, a.source, p.change_type
            FROM parsed_articles p
            JOIN articles a ON p.article_id = a.id
            {where}
            ORDER BY a.fetched_at DESC
            LIMIT ?
            """,
            params,
        )
    except sqlite3.Error as exc:
        st.error(f"Database error: {exc}")
        return

    if not rows:
        st.info("No regulations found for this filter.")
        return

    for reg, jurisdiction, impact, action, title, source, change_type in rows:
        dot = IMPACT_DOT.get(str(impact).lower(), "Grey")
        with st.expander(f"{dot} {reg or 'ESG'} - {(title or '')[:70]}"):
            cols = st.columns(3)
            cols[0].metric("Regulation", reg or "General ESG")
            cols[1].metric("Jurisdiction", jurisdiction or "Global")
            cols[2].metric("Impact", impact.upper() if impact else "N/A")
            if action:
                st.markdown(f"**Action Required:** {action}")
            st.caption(f"Source: {source or 'N/A'} | Type: {change_type or 'N/A'}")


def render_database_stats():
    st.markdown("### System Statistics")
    stats = get_stats()
    labels = [
        ("Total RSS Articles", stats["rss"], "Live"),
        ("AI Parsed", stats["parsed"], "Structured"),
        ("High Impact", stats["high"], "Critical"),
        ("Tavily Articles", stats["tavily"], "Real-time"),
    ]
    for col, (label, value, delta) in zip(st.columns(4), labels):
        col.metric(label, value, delta=delta)

    st.markdown("---")
    st.markdown("### Impact Distribution")
    try:
        impact_data = dict(
            fetch_all(
                """
                SELECT impact_level, COUNT(*)
                FROM parsed_articles
                GROUP BY impact_level
                """
            )
        )
        for col, impact in zip(st.columns(3), ["high", "medium", "low"]):
            col.metric(f"{impact.title()} Impact", impact_data.get(impact, 0))
    except sqlite3.Error as exc:
        st.error(f"Error: {exc}")

    st.markdown("---")
    st.markdown("### Top Regulations in Database")
    try:
        reg_data = fetch_all(
            """
            SELECT regulation_name, COUNT(*) AS count
            FROM parsed_articles
            WHERE regulation_name IS NOT NULL AND regulation_name != 'None'
            GROUP BY regulation_name
            ORDER BY count DESC
            LIMIT 10
            """
        )
    except sqlite3.Error as exc:
        st.error(f"Error: {exc}")
        return

    if not reg_data:
        st.info("No regulation data available yet.")
        return

    max_count = max(count for _, count in reg_data) or 1
    for reg, count in reg_data:
        st.progress(count / max_count, text=f"{reg} - {count} articles")


def main():
    load_rag()
    render_header()
    render_sidebar()
    tab1, tab2, tab3 , tab4, tab5 = st.tabs(
        ["Company Assessment", "Latest Regulations", "Database Stats","ESG chat","Daily Radar"]
    )
    with tab1:
        render_company_assessment()
    with tab2:
        render_latest_regulations()
    with tab3:
        render_database_stats()
    with tab4:
        st.markdown("### 💬 Ask ESG Assistant")
        st.caption("RAG → Web Search → LLM — auto routed!")
        if "messages" not in st.session_state:
            st.session_state.messages = []
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        if question := st.chat_input("Ask anything about ESG..."):
            st.session_state.messages.append({
            "role": "user",
            "content": question
        })
            with st.chat_message("user"):
                st.markdown(question)
            with st.spinner("Thinking..."):
                result = agent.invoke({
                "messages": [HumanMessage(content=question)]
            })
                answer = result["messages"][-1].content
            st.session_state.messages.append({
                "role": "assistant",
                "content": answer
            })
            with st.chat_message("assistant"):
                st.markdown(answer)

        if st.button("🗑️ Clear Chat"):
            st.session_state.messages = []
            st.rerun()
    with tab5:
        render_daily_radar()        
            
if __name__ == "__main__":
    main()
