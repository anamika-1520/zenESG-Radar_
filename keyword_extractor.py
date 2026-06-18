import fitz  # pymupdf
import re
from config import KEYWORDS_PDF

def extract_keywords_from_pdf(pdf_path=KEYWORDS_PDF):
    """
    PDF se automatically keywords extract karo
    Koi hardcoding nahi!
    """
    print(f"📄 starting to read: {pdf_path}")
    
    keywords = set()
    
    try:
        doc = fitz.open(pdf_path)
        full_text = ""
        
        # Poora PDF padhlo
        for page in doc:
            full_text += page.get_text()
        
        doc.close()
        print(f"✅ done — {len(full_text)} characters")
        
        # Table cells se keywords nikalo
        table_pattern = r'\|([^|\n]+)\|'
        table_matches = re.findall(table_pattern, full_text)
        
        for match in table_matches:
            kw = match.strip()
            if is_valid_keyword(kw):
                keywords.add(kw)
        
        # Alag lines se bhi nikalo
        lines = full_text.split('\n')
        for line in lines:
            line = line.strip()
            if is_valid_keyword(line):
                keywords.add(line)
        
        # Clean karo
        keywords = clean_keywords(keywords)
        
        print(f"✅ Total keywords extracted: {len(keywords)}")
        return list(keywords)
        
    except Exception as e:
        print(f"❌ PDF error: {e}")
        return get_fallback_keywords()

def is_valid_keyword(text):
    """
    Check if the text is a valid keyword candidate
    Simple rules: length, no digits only, no junk words
    """
    text = text.strip()
    
    # Too short ya too long nahi hona chahiye
    if len(text) < 3 or len(text) > 60:
        return False
    
    # Sirf numbers nahi hona chahiye
    if text.isdigit():
        return False
    
    # Headers aur junk words skip karo
    skip_words = [
        "keyword", "source", "url", "focus",
        "boolean", "search", "query", "template",
        "use these", "combine", "---", "===",
        "part 1", "part 2", "part 3", "part 4",
        "prompt", "linkedin", "hashtag"
    ]
    
    text_lower = text.lower()
    for skip in skip_words:
        if skip in text_lower:
            return False
    
    return True

def clean_keywords(keywords):
    """clean keywords by removing extra spaces and special characters"""
    cleaned = set()
    
    for kw in keywords:
        # Extra spaces hata do
        kw = ' '.join(kw.split())
        
        # Special characters clean karo
        kw = kw.strip('|#*-_.,')
        kw = kw.strip()
        
        if len(kw) > 2:
            cleaned.add(kw)
    
    return list(cleaned)

def get_fallback_keywords():
    """
   if PDF parsing fails, fallback keywords provide karo. Yeh hardcoded hain, but at least kuch toh hai!
    """
    print("⚠️using  Fallback keywords")
    return [
        "ESG", "CSRD", "TCFD", "GRI", "ISSB",
        "net zero", "carbon neutral", "sustainability",
        "climate risk", "ESG regulation", "BRSR"
    ]

if __name__ == "__main__":
    # Test karo
    keywords = extract_keywords_from_pdf()
    print(f"\n🔍 Sample keywords (first 20):")
    for kw in keywords[:20]:
        print(f"  - {kw}")