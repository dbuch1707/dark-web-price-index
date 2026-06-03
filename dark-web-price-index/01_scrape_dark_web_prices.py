"""
Dark Web Price Index — Web Scraper
===================================
Scrapes price tables from publicly available cybersecurity research pages.
Sources: Privacy Affairs, DeepStrike, Trustwave, SOCRadar

Usage:
    pip install requests beautifulsoup4 pandas openpyxl lxml
    python 01_scrape_dark_web_prices.py

Output:
    scraped_raw.csv        — raw scraped data, one row per price entry
    scraped_summary.xlsx   — cleaned, deduplicated, source-tagged
"""

import requests
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime
import time
import re
import warnings
warnings.filterwarnings("ignore")

# ── CONFIG ────────────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

SOURCES = [
    {
        "name":    "Privacy Affairs 2023",
        "url":     "https://privacyaffairs.com/dark-web-price-index-2023/",
        "year":    2023,
        "strategy": "table",          # look for <table> tags
    },
    {
        "name":    "Privacy Affairs 2022",
        "url":     "https://privacyaffairs.com/dark-web-price-index-2022/",
        "year":    2022,
        "strategy": "table",
    },
    {
        "name":    "DeepStrike 2025",
        "url":     "https://deepstrike.io/blog/dark-web-data-pricing-2025",
        "year":    2025,
        "strategy": "list",           # look for price patterns in text/lists
    },
]

# Price pattern: matches "$1", "$1,200", "$1.5K", "$200,000+"
PRICE_RE = re.compile(
    r'\$\s*([\d,]+(?:\.\d+)?)\s*(?:K|k)?(?:\s*[-–—]\s*\$?\s*([\d,]+(?:\.\d+)?)\s*(?:K|k)?)?'
)

# ── HELPERS ───────────────────────────────────────────────────────────────────

def fetch(url: str) -> BeautifulSoup | None:
    """Fetch a URL and return parsed BeautifulSoup, or None on failure."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")
    except Exception as e:
        print(f"  ✗ Failed to fetch {url}: {e}")
        return None


def parse_price(raw: str) -> tuple[float | None, float | None]:
    """
    Parse a raw price string into (low, high) USD floats.
    Examples:
        "$1"          → (1.0, 1.0)
        "$1 – $6"     → (1.0, 6.0)
        "$1,200"      → (1200.0, 1200.0)
        "$14,760"     → (14760.0, 14760.0)
        "$10K"        → (10000.0, 10000.0)
        "$10K–$200K"  → (10000.0, 200000.0)
    """
    raw = raw.strip().replace(",", "")
    matches = PRICE_RE.findall(raw)
    if not matches:
        return None, None

    def to_float(s, is_k=False):
        try:
            v = float(s.replace(",", ""))
            if is_k or "k" in raw.lower():
                v *= 1000
            return v
        except Exception:
            return None

    # Check if K suffix present
    is_k = bool(re.search(r'\d\s*[Kk]', raw))

    first = matches[0]
    lo = to_float(first[0], is_k)
    hi = to_float(first[1], is_k) if first[1] else lo

    return lo, hi


def classify_category(text: str) -> str:
    """Assign a category based on keywords in the item description."""
    t = text.lower()
    if any(w in t for w in ["passport", "driver", "id card", "forged", "physical", "scan"]):
        return "Forged Documents – Physical"
    if any(w in t for w in ["ssn", "social security", "fullz", "full identity", "medical", "dob"]):
        return "Identity – PII"
    if any(w in t for w in ["credit card", "cvv", "debit card"]):
        return "Credit Card Data"
    if any(w in t for w in ["bank", "paypal", "wire", "financial account", "loan"]):
        return "Financial Accounts"
    if any(w in t for w in ["crypto", "bitcoin", "coinbase", "kraken", "binance", "ethereum"]):
        return "Crypto Accounts"
    if any(w in t for w in ["gmail", "facebook", "instagram", "twitter", "social media", "hacked"]):
        return "Hacked Services"
    if any(w in t for w in ["ddos", "attack", "botnet", "malware", "ransomware", "infostealer"]):
        return "Cybercrime Services"
    if any(w in t for w in ["admin", "vpn", "rdp", "domain", "corporate", "zero-day", "exploit"]):
        return "Corporate Access"
    if any(w in t for w in ["email", "database", "dump", "list"]):
        return "Email Database Dumps"
    return "Other"


# ── STRATEGY: TABLE ──────────────────────────────────────────────────────────

def scrape_tables(soup: BeautifulSoup, source_name: str, year: int) -> list[dict]:
    """Extract price data from HTML <table> elements."""
    rows_out = []
    tables   = soup.find_all("table")

    if not tables:
        print(f"  ℹ No <table> tags found — trying list strategy instead")
        return scrape_lists(soup, source_name, year)

    for table_idx, table in enumerate(tables):
        headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
        rows    = table.find_all("tr")

        for row in rows:
            cells = [td.get_text(strip=True) for td in row.find_all(["td","th"])]
            if len(cells) < 2:
                continue

            # Try to identify which column is the product and which is the price
            product_col = 0
            price_col   = 1

            # If we have headers, use them to find price column
            for i, h in enumerate(headers):
                if any(w in h for w in ["price", "cost", "usd", "$", "amount"]):
                    price_col = i
                elif any(w in h for w in ["item", "product", "service", "type", "name", "category"]):
                    product_col = i

            if price_col >= len(cells) or product_col >= len(cells):
                continue

            product   = cells[product_col]
            price_raw = cells[price_col]

            if not product or product.lower() in ["item", "product", "service", "type"]:
                continue

            lo, hi = parse_price(price_raw)
            if lo is None:
                continue

            rows_out.append({
                "Year":          year,
                "Category":      classify_category(product),
                "Product":       product,
                "Country":       "United States",   # default; override manually if known
                "Organization":  "Various",
                "Price_Low_USD": lo,
                "Price_High_USD":hi,
                "Price_Mid_USD": round((lo + hi) / 2, 2),
                "Price_Note":    "Actual",
                "Source":        source_name,
                "Is_Estimated":  "No",
                "Scraped_At":    datetime.now().isoformat(),
            })

    print(f"  ✓ Tables: extracted {len(rows_out)} rows")
    return rows_out


# ── STRATEGY: LIST / TEXT PATTERN ────────────────────────────────────────────

def scrape_lists(soup: BeautifulSoup, source_name: str, year: int) -> list[dict]:
    """
    Extract price data from unstructured text / list items.
    Looks for lines that contain both a product description and a price.
    """
    rows_out = []
    # Gather text from <li>, <p>, <td>, headings
    candidates = soup.find_all(["li", "p", "td", "h3", "h4"])

    for el in candidates:
        text = el.get_text(separator=" ", strip=True)

        # Must contain a price pattern
        if "$" not in text:
            continue

        lo, hi = parse_price(text)
        if lo is None or lo < 0.5:  # skip $0 noise
            continue

        # Clean the text to extract the product name
        # Remove the price portion from the text
        product = re.sub(r'\$[\d,\.]+\s*(?:[Kk])?\s*(?:[-–—]\s*\$[\d,\.]+\s*(?:[Kk])?)?', '', text).strip()
        product = re.sub(r'\s{2,}', ' ', product).strip(" :·-–—")

        if len(product) < 5 or len(product) > 120:
            continue

        # Skip navigation/boilerplate
        skip_words = ["cookie", "privacy policy", "subscribe", "newsletter", "read more", "click here"]
        if any(w in product.lower() for w in skip_words):
            continue

        rows_out.append({
            "Year":          year,
            "Category":      classify_category(product),
            "Product":       product,
            "Country":       "United States",
            "Organization":  "Various",
            "Price_Low_USD": lo,
            "Price_High_USD":hi,
            "Price_Mid_USD": round((lo + hi) / 2, 2),
            "Price_Note":    "Actual",
            "Source":        source_name,
            "Is_Estimated":  "No",
            "Scraped_At":    datetime.now().isoformat(),
        })

    # Deduplicate by product+price
    seen    = set()
    deduped = []
    for r in rows_out:
        key = (r["Product"][:40].lower(), r["Price_Low_USD"])
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    print(f"  ✓ Lists: extracted {len(deduped)} rows")
    return deduped


# ── MAIN SCRAPER ─────────────────────────────────────────────────────────────

def scrape_all() -> pd.DataFrame:
    all_rows = []

    for source in SOURCES:
        print(f"\n→ Scraping: {source['name']}")
        print(f"  URL: {source['url']}")

        soup = fetch(source["url"])
        if not soup:
            continue

        if source["strategy"] == "table":
            rows = scrape_tables(soup, source["name"], source["year"])
        else:
            rows = scrape_lists(soup, source["name"], source["year"])

        all_rows.extend(rows)
        time.sleep(2)   # polite delay between requests

    if not all_rows:
        print("\n⚠ No data scraped. Check your internet connection or source URLs.")
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)

    # Clean up
    df = df.dropna(subset=["Price_Low_USD"])
    df = df[df["Price_Low_USD"] > 0]
    df = df.sort_values(["Year","Category","Price_Mid_USD"], ascending=[True,True,False])
    df = df.reset_index(drop=True)

    # Save raw CSV
    df.to_csv("scraped_raw.csv", index=False)
    print(f"\n✓ Saved scraped_raw.csv — {len(df)} total rows")

    # Save clean Excel with auto-column widths
    with pd.ExcelWriter("scraped_summary.xlsx", engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Scraped_Data")
        ws = writer.sheets["Scraped_Data"]
        for col in ws.columns:
            max_len = max(len(str(c.value)) for c in col if c.value) + 4
            ws.column_dimensions[col[0].column_letter].width = min(max_len, 50)

    print(f"✓ Saved scraped_summary.xlsx")
    return df


if __name__ == "__main__":
    print("=" * 60)
    print("Dark Web Price Index — Web Scraper")
    print(f"Run at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    df = scrape_all()

    if not df.empty:
        print("\n── Summary by Source ──")
        print(df.groupby(["Year","Source"])["Product"].count().to_string())
        print("\n── Categories found ──")
        print(df["Category"].value_counts().to_string())
        print("\n── Price range ──")
        print(f"  Min: ${df['Price_Low_USD'].min():,.2f}")
        print(f"  Max: ${df['Price_High_USD'].max():,.2f}")
        print(f"  Avg mid: ${df['Price_Mid_USD'].mean():,.2f}")
