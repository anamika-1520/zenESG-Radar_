import feedparser
import sqlite3
import re
import json
import schedule
import time
from datetime import datetime
from keyword_extractor import extract_keywords_from_pdf
from config import (
    RSS_FEEDS, 
    DATABASE, 
    FETCH_INTERVAL_HOURS,
    MAX_DESCRIPTION_LENGTH
)

# ============================================
# DATABASE SETUP
# ============================================

def setup_database():
    """create database and tables if not exist """
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            url TEXT UNIQUE,
            source TEXT,
            published TEXT,
            matched_keywords TEXT,
            relevance_score INTEGER DEFAULT 0,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fetch_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_url TEXT,
            total_articles INTEGER,
            relevant_articles INTEGER,
            status TEXT,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    print("✅ Database ready!")
    return conn

# ============================================
# ARTICLE PROCESSING
# ============================================

def clean_text(text):
    """remove HTML tags aur extra spaces"""
    if not text:
        return ""
    text = re.sub('<.*?>', '', text)
    text = re.sub('\s+', ' ', text)
    return text.strip()

def check_relevance(title, description, keywords):
    """
   check how many keywords match title and discription mein. return matched keywords aur relevance score (number of matches)
    """
    text = (title + " " + description).lower()
    matched = []
    
    for keyword in keywords:
        if keyword.lower() in text:
            matched.append(keyword)
    
    return matched, len(matched)

def save_article(conn, article):
    """save article to database."""
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO articles 
            (title, description, url, source, 
             published, matched_keywords, relevance_score)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            article['title'],
            article['description'],
            article['url'],
            article['source'],
            article['published'],
            json.dumps(article['matched_keywords']),
            article['relevance_score']
        ))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False  # Duplicate

def log_fetch(conn, source_url, total, relevant, status):
    """Fetch history save karo"""
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO fetch_logs 
        (source_url, total_articles, relevant_articles, status)
        VALUES (?, ?, ?, ?)
    """, (source_url, total, relevant, status))
    conn.commit()

# ============================================
# MAIN FETCHER
# ============================================

def fetch_from_feed(feed_url, keywords, conn):
    """fetch karo feed, check relevance, save karo database mein, aur log karo"""
    try:
        feed = feedparser.parse(feed_url)
        source_name = feed.feed.get('title', feed_url)
        
        total = len(feed.entries)
        relevant_count = 0
        new_count = 0
        
        for entry in feed.entries:
            title = entry.get('title', '')
            description = clean_text(
                entry.get('description', '') or
                entry.get('summary', '')
            )[:MAX_DESCRIPTION_LENGTH]
            
            url = entry.get('link', '')
            published = entry.get('published', 
                        str(datetime.now()))
            
            # Relevance check karo
            matched_kws, score = check_relevance(
                title, description, keywords
            )
            
            if score > 0:
                relevant_count += 1
                article = {
                    "title": title,
                    "description": description,
                    "url": url,
                    "source": source_name,
                    "published": published,
                    "matched_keywords": matched_kws,
                    "relevance_score": score
                }
                
                if save_article(conn, article):
                    new_count += 1
        
        # Log karo
        log_fetch(conn, feed_url, total, 
                 relevant_count, "success")
        
        print(f"  ✅ {source_name[:30]}")
        print(f"     Total: {total} | "
              f"Relevant: {relevant_count} | "
              f"New: {new_count}")
        
        return relevant_count
        
    except Exception as e:
        log_fetch(conn, feed_url, 0, 0, f"error: {e}")
        print(f"  ❌ Failed: {feed_url[:50]}")
        print(f"     Error: {e}")
        return 0

def run_ingestion():
    """Main function — fatch all feeds and process"""
    print("\n" + "="*50)
    print("🌍 ZenESG Regulatory Radar")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*50)
    
    # Step 1: PDF se keywords lo
    print("\n📚 Step 1: loading keywords...")
    keywords = extract_keywords_from_pdf()
    print(f"✅ {len(keywords)} keywords ready!")
    
    # Step 2: Database setup
    print("\n🗄️  Step 2: Database setup...")
    conn = setup_database()
    
    # Step 3: Sab feeds fetch karo
    print(f"\n📡 Step 3: {len(RSS_FEEDS)} fatching from feeds")
    
    total_relevant = 0
    working_feeds = 0
    
    for feed_url in RSS_FEEDS:
        count = fetch_from_feed(feed_url, keywords, conn)
        total_relevant += count
        if count >= 0:
            working_feeds += 1
    
    # Summary
    print("\n" + "="*50)
    print("📊 SUMMARY")
    print("="*50)
    print(f"✅ Sources checked : {len(RSS_FEEDS)}")
    print(f"✅ ESG articles     : {total_relevant}")
    
    # Top articles dikhao
    cursor = conn.cursor()
    cursor.execute("""
        SELECT title, source, relevance_score, 
               matched_keywords
        FROM articles 
        ORDER BY relevance_score DESC, 
                 fetched_at DESC
        LIMIT 5
    """)
    
    rows = cursor.fetchall()
    if rows:
        print("\n🏆 TOP 5 MOST RELEVANT ARTICLES:")
        for i, row in enumerate(rows, 1):
            kws = json.loads(row[3])[:3]
            print(f"\n{i}. {row[0][:60]}")
            print(f"   Source: {row[1]}")
            print(f"   Score: {row[2]} | "
                  f"Keywords: {', '.join(kws)}")
    
    conn.close()
    print("\n✅ Done! Next run in "
          f"{FETCH_INTERVAL_HOURS} hours")

# ============================================
# SCHEDULER
# ============================================

if __name__ == "__main__":
    # Pehli baar abhi run karo
    run_ingestion()
    
    # Phir har 6 ghante automatically
    schedule.every(FETCH_INTERVAL_HOURS).hours.do(
        run_ingestion
    )
    
    print(f"\n⏰ Scheduler started!")
    print(f"Next run in {FETCH_INTERVAL_HOURS} hours")
    print("Ctrl+C se band karo\n")
    
    while True:
        schedule.run_pending()
        time.sleep(60) # Check every minute for pending tasks