# Dark Web Price Index — Python Scripts

Two scripts that power the data pipeline behind the Tableau dashboard.

---

## Scripts

### `01_scrape_dark_web_prices.py` — Web Scraper
Scrapes price tables from publicly available cybersecurity research pages.

**Sources targeted:**
- Privacy Affairs Dark Web Price Index (2022, 2023)
- DeepStrike Dark Web Pricing 2025
- Trustwave / SOCRadar (extend by adding URLs to the `SOURCES` list)

**Output:**
- `scraped_raw.csv` — every price found, one row per item
- `scraped_summary.xlsx` — cleaned and deduplicated

**How it works:**
1. Fetches each source URL with a browser-like User-Agent
2. Tries `<table>` extraction first — finds HTML tables and maps columns
3. Falls back to list/text pattern matching — finds `$` patterns in `<li>`, `<p>` tags
4. Classifies each item into a category (Credit Card Data, Corporate Access, etc.)
5. Parses price strings like `$1`, `$1,200`, `$10K`, `$10K–$200K` into Low/High/Mid

---

### `02_interpolate_2024.py` — 2024 Estimator
Generates estimated 2024 price values since no public index was published for 2024.

**Method:** Linear interpolation
```
2024_value = (2023_actual + 2025_actual) / 2
```

For items only in 2025 (no 2023 baseline), the 2025 value is held flat.

**Output:**
- `Dark_Web_Price_Index_With_2024.csv` — full 2020–2025 dataset
- `Dark_Web_Price_Index_With_2024.xlsx` — Excel, yellow rows = 2024 estimates
- `interpolation_report.txt` — full audit trail of every estimate

**Transparency flags on every 2024 row:**
- `Is_Estimated = "Yes"`
- `Price_Note = "Estimated – linear interpolation 2023→2025"`
- Yellow cell fill in Excel

---

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run scraper first
python 01_scrape_dark_web_prices.py

# 3. Then run interpolation
python 02_interpolate_2024.py

# 4. Import Dark_Web_Price_Index_With_2024.xlsx into Tableau
```

---

## Extending the scraper

To add a new source, add an entry to the `SOURCES` list in `01_scrape_dark_web_prices.py`:

```python
{
    "name":     "My Source 2024",
    "url":      "https://example.com/dark-web-prices-2024",
    "year":     2024,
    "strategy": "table",   # or "list"
}
```

Strategy guide:
- `"table"` — use when the page has clear `<table>` HTML elements
- `"list"` — use when prices are in bullet points, paragraphs, or unstructured text

---

## Notes

- Scripts use a polite 2-second delay between requests to avoid rate limiting
- All scraping is of **publicly available** research reports — no dark web access
- 2024 data is clearly labeled as estimated — do not present as primary research
