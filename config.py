# RSS Feed sources 
RSS_FEEDS = [
    # ESG News
    "https://www.esgtoday.com/feed",
    "https://www.esgnews.com/feed",
    "https://www.esginvestor.net/feed",
    "https://www.esgdive.com/feeds/news.rss",
    
    # Climate & Sustainability  
    "https://www.carbonbrief.org/feed",
    "https://climate.nasa.gov/rss/api/?feed=news",
    "https://www.climatechangenews.com/feed",
    "https://www.responsible-investor.com/rss",
    
    # Finance & Investment
    "https://www.environmental-finance.com/rss",
    "https://www.unepfi.org/news/rss",
    
    # Official Regulatory
    "https://eur-lex.europa.eu/rss/rss.xml",
    "https://www.eba.europa.eu/rss.xml",
    "https://www.esma.europa.eu/rss.xml",
    
    # India Specific
    "https://www.sebi.gov.in/rss.xml",
    "https://www.eco-business.com/feed",
    
    # General Sustainability
    "https://sustainabilitymag.com/feed",
    "https://www.greenbiz.com/feeds/rss",
    "https://www.businessgreen.com/feed",
    "https://www.weforum.org/rss.xml",
    "https://www.theguardian.com/environment/sustainability/rss",
]


KEYWORDS_PDF = "sustainability_keywords.pdf"


DATABASE = "esg_radar.db"

FETCH_INTERVAL_HOURS = 6

# Ek article ka description kitna lamba rakho
MAX_DESCRIPTION_LENGTH = 500
# ChromaDB settings
CHROMA_PATH = "./chroma_db"
COLLECTION_NAME = "esg_regulations"