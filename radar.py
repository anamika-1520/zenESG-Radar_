import json
import sqlite3
from contextlib import closing
from datetime import datetime
from html import escape

import streamlit as st

from config import DATABASE


REGIONS = ["All", "India", "UK", "EU", "US", "Singapore", "Global"]
IMPACTS = ["All", "High", "Medium", "Low"]
IMPACT_LABELS = {
    "high": ("High", "Critical"),
    "medium": ("Medium", "Watch"),
    "low": ("Low", "Monitor"),
}
IMPACT_CLASS = {"high": "impact-high", "medium": "impact-medium", "low": "impact-low"}


def inject_radar_css():
    st.markdown(
        """
<style>
.radar-hero {
    border: 1px solid #d8e2dc;
    border-radius: 14px;
    padding: 1.15rem 1.25rem;
    background: linear-gradient(135deg, #f7fbf8 0%, #eef6f2 54%, #fff8e8 100%);
    margin-bottom: 1rem;
}
.radar-hero h3 {
    margin: 0 0 .25rem 0;
    color: #12372a;
}
.radar-hero p {
    margin: 0;
    color: #496057;
}
.radar-chip-row {
    display: flex;
    flex-wrap: wrap;
    gap: .45rem;
    margin: .4rem 0 .65rem 0;
}
.radar-chip {
    display: inline-flex;
    align-items: center;
    border-radius: 999px;
    border: 1px solid #d7e4dd;
    background: #ffffff;
    color: #254238;
    font-size: .78rem;
    font-weight: 650;
    padding: .22rem .6rem;
}
.impact-high {
    border-color: #f2bbb6;
    background: #fff1ef;
    color: #9d2f25;
}
.impact-medium {
    border-color: #f1d58f;
    background: #fff8df;
    color: #805b05;
}
.impact-low {
    border-color: #b9dfc4;
    background: #eefaf1;
    color: #27633a;
}
.news-brief {
    border: 1px solid #e1e7e3;
    border-radius: 12px;
    padding: 1rem;
    background: #ffffff;
    box-shadow: 0 8px 22px rgba(18, 55, 42, .06);
    margin: .6rem 0;
}
.brief-title {
    color: #143b30;
    font-weight: 750;
    font-size: 1rem;
    margin-bottom: .35rem;
}
.brief-section {
    border-left: 4px solid #2f7d68;
    padding: .55rem .7rem;
    background: #f8fbf9;
    border-radius: 8px;
    margin: .65rem 0;
}
.brief-section strong {
    color: #143b30;
}
.source-box {
    border: 1px dashed #c8d8cf;
    border-radius: 10px;
    padding: .8rem;
    background: #fbfdfb;
    color: #263d35;
}
div[data-testid="stExpander"] {
    border: 1px solid #dbe6df;
    border-radius: 14px;
    background: #ffffff;
    box-shadow: 0 6px 18px rgba(25, 54, 45, .05);
}
div[data-testid="stMetric"] {
    background: #f8faf8;
    border: 1px solid #e5ece8;
    border-radius: 10px;
    padding: .65rem;
}
</style>
""",
        unsafe_allow_html=True,
    )


def fetch_rows(query, params=()):
    with closing(sqlite3.connect(DATABASE)) as conn:
        return conn.cursor().execute(query, params).fetchall()


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_source_text(url):
    if not url:
        return None
    try:
        import requests
        from bs4 import BeautifulSoup

        response = requests.get(
            url,
            timeout=8,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0 Safari/537.36"
                )
            },
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        article = soup.find("article") or soup.find("main") or soup.body
        if not article:
            return None

        paragraphs = [
            paragraph.get_text(" ", strip=True)
            for paragraph in article.find_all("p")
        ]
        text = "\n\n".join(p for p in paragraphs if len(p) > 35)
        return text[:6000] if len(text) > 500 else None
    except Exception:
        return None


def clean_text(value, fallback="N/A"):
    text = str(value or "").strip()
    return text if text else fallback


def impact_text(impact):
    label, status = IMPACT_LABELS.get(str(impact).lower(), ("Unknown", "Review"))
    return f"{label} impact - {status}"


def chip(label, css_class=""):
    return f'<span class="radar-chip {css_class}">{escape(clean_text(label))}</span>'


def format_sectors(raw_value):
    if not raw_value:
        return "Not specified"
    try:
        parsed = json.loads(raw_value)
        if isinstance(parsed, list):
            return ", ".join(str(item) for item in parsed if item) or "Not specified"
    except (json.JSONDecodeError, TypeError):
        pass
    return str(raw_value)


def render_chip_row(*items):
    chips = []
    for label, css_class in items:
        if clean_text(label, ""):
            chips.append(chip(label, css_class))
    st.markdown(
        f'<div class="radar-chip-row">{"".join(chips)}</div>',
        unsafe_allow_html=True,
    )


def render_full_news_brief(
    title,
    description,
    summary,
    action,
    reg_name,
    jurisdiction,
    regulator,
    sectors,
    deadline,
    change_type,
):
    st.markdown(
        f"""
<div class="news-brief">
  <div class="brief-title">{escape(clean_text(title, "Regulatory update"))}</div>
  <div class="brief-section">
    <strong>What happened:</strong><br>
    {escape(clean_text(description, summary or "The feed did not include a long article body, but the parsed regulatory summary is available below."))}
  </div>
  <div class="brief-section">
    <strong>Regulatory meaning:</strong><br>
    {escape(clean_text(summary, "No parsed summary is available yet."))}
  </div>
  <div class="brief-section">
    <strong>Who should care:</strong><br>
    Jurisdiction: {escape(clean_text(jurisdiction, "Global"))}. 
    Regulator: {escape(clean_text(regulator, "Not specified"))}. 
    Affected sectors: {escape(format_sectors(sectors))}.
  </div>
  <div class="brief-section">
    <strong>Compliance action:</strong><br>
    {escape(clean_text(action, "Review the source update and map it against current ESG reporting, disclosure, and governance obligations."))}
  </div>
  <div class="brief-section">
    <strong>Tracking details:</strong><br>
    Regulation: {escape(clean_text(reg_name, "General ESG"))}. 
    Change type: {escape(clean_text(change_type, "update"))}. 
    Deadline: {escape(clean_text(deadline, "Not specified"))}.
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_daily_radar():
    inject_radar_css()
    today = datetime.now().strftime("%B %d, %Y")
    st.markdown(
        f"""
<div class="radar-hero">
  <h3>ESG Regulatory Radar - {today}</h3>
  <p>Full news-style briefings from saved RSS articles and Tavily web intelligence.</p>
</div>
""",
        unsafe_allow_html=True,
    )

    col1, col2, col3, col4 = st.columns([2, 2, 1.4, 1])
    with col1:
        region_filter = st.selectbox("Region", REGIONS)
    with col2:
        impact_filter = st.selectbox("Impact", IMPACTS)
    with col3:
        limit = st.slider("Updates", 5, 25, 10)
    with col4:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Refresh", use_container_width=True):
            st.rerun()

    st.markdown("---")

    try:
        query = """
            SELECT
                p.regulation_name,
                p.jurisdiction,
                p.impact_level,
                p.change_type,
                p.action_required,
                p.summary,
                p.regulator,
                p.affected_sectors,
                p.deadline,
                a.title,
                a.description,
                a.source,
                a.url,
                a.fetched_at,
                a.relevance_score
            FROM parsed_articles p
            JOIN articles a ON p.article_id = a.id
            WHERE 1=1
        """
        params = []

        if region_filter != "All":
            query += " AND LOWER(p.jurisdiction) LIKE ?"
            params.append(f"%{region_filter.lower()}%")

        if impact_filter != "All":
            query += " AND p.impact_level = ?"
            params.append(impact_filter.lower())

        query += """
            ORDER BY
                CASE p.impact_level
                    WHEN 'high' THEN 1
                    WHEN 'medium' THEN 2
                    WHEN 'low' THEN 3
                    ELSE 4
                END,
                a.fetched_at DESC
            LIMIT ?
        """
        params.append(limit)
        news = fetch_rows(query, params)
    except sqlite3.Error as exc:
        st.error(f"Database error: {exc}")
        return

    if not news:
        st.info("No regulatory updates found for this filter.")
        return

    high_count = sum(1 for row in news if row[2] == "high")
    if high_count:
        st.error(f"{high_count} high impact regulation(s) need attention.")

    st.markdown(f"### Top {len(news)} Regulatory Updates")

    for index, row in enumerate(news, 1):
        (
            reg_name,
            jurisdiction,
            impact,
            change_type,
            action,
            summary,
            regulator,
            sectors,
            deadline,
            title,
            description,
            source,
            url,
            fetched_at,
            relevance_score,
        ) = row

        heading = f"#{index} | {reg_name or 'General ESG'} | {(title or '')[:70]}"
        with st.expander(heading):
            render_chip_row(
                (impact_text(impact), IMPACT_CLASS.get(str(impact).lower(), "")),
                (jurisdiction or "Global", ""),
                (change_type or "update", ""),
                (source or "Unknown source", ""),
            )

            col1, col2, col3 = st.columns(3)
            col1.metric("Regulation", reg_name or "General ESG")
            col2.metric("Jurisdiction", jurisdiction or "Global")
            col3.metric("Impact", impact_text(impact))

            st.markdown(f"#### {title or reg_name or 'Regulatory update'}")
            st.caption(
                f"Source: {source or 'Unknown'} | "
                f"Fetched: {str(fetched_at)[:16] if fetched_at else 'N/A'} | "
                f"Type: {change_type or 'update'} | "
                f"Feed score: {relevance_score or 0}"
            )

            overview_tab, full_tab, compliance_tab = st.tabs(
                ["Overview", "Full News Brief", "Compliance"]
            )
            with overview_tab:
                st.markdown("**Short summary**")
                st.markdown(summary or description or "No summary available for this update.")
                if action:
                    st.success(f"Action Required: {action}")

            with full_tab:
                render_full_news_brief(
                    title,
                    description,
                    summary,
                    action,
                    reg_name,
                    jurisdiction,
                    regulator,
                    sectors,
                    deadline,
                    change_type,
                )
                st.markdown("**Original feed text saved in database**")
                st.markdown(
                    f'<div class="source-box">{escape(clean_text(description, "No original RSS description was saved."))}</div>',
                    unsafe_allow_html=True,
                )
                if url and st.button(
                    "Fetch full source text",
                    key=f"fetch_full_source_{index}_{abs(hash(url))}",
                ):
                    with st.spinner("Fetching full source text..."):
                        source_text = fetch_source_text(url)
                    if source_text:
                        st.markdown("**Full source text fetched from URL**")
                        st.markdown(
                            f'<div class="source-box">{escape(source_text)}</div>',
                            unsafe_allow_html=True,
                        )
                    else:
                        st.warning(
                            "Full text could not be extracted from this source. "
                            "The saved database brief and source link are still available."
                        )

            with compliance_tab:
                col_a, col_b = st.columns(2)
                col_a.info(f"Regulator: {regulator or 'Not specified'}")
                col_b.info(f"Deadline: {deadline or 'Not specified'}")
                st.markdown(f"**Affected sectors:** {format_sectors(sectors)}")
                st.markdown(f"**Recommended next step:** {action or 'Review source and assess internal impact.'}")

            if url:
                st.link_button("Open source article", url)

    st.markdown("---")
    st.markdown("### Latest Web Intelligence")
    st.caption("High relevance Tavily results already saved in the database.")

    try:
        tavily_news = fetch_rows(
            """
            SELECT title, content, source, url, query_used, relevance_score
            FROM tavily_articles
            WHERE relevance_score >= 0.85
            ORDER BY relevance_score DESC, fetched_at DESC
            LIMIT 5
            """
        )
    except sqlite3.Error as exc:
        st.error(f"Tavily database error: {exc}")
        return

    if not tavily_news:
        st.info("No high relevance web intelligence found yet.")
        return

    for title, content, source, url, query, score in tavily_news:
        with st.expander(f"{(title or 'Web result')[:80]} | Score: {score:.2f}"):
            render_chip_row(
                (f"Relevance {score:.2f}", "impact-low" if score < 0.9 else "impact-high"),
                (source or "Web", ""),
                (query or "Regulatory query", ""),
            )
            st.markdown(f"#### {title or 'Web result'}")
            st.caption(
                f"Source: {source or 'Web'} | "
                f"Relevance: {score:.2f} | "
                f"Query: {query or 'N/A'}"
            )
            if content:
                st.markdown("**Full saved web content**")
                st.markdown(
                    f'<div class="source-box">{escape(content)}</div>',
                    unsafe_allow_html=True,
                )
            if url:
                st.link_button("Open web source", url)
