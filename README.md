# Facebook Scraper Tools

This repository contains a collection of Python scripts for scraping different types of data from Facebook, including ads, page information, and search suggestions.

## Table of Contents

- [Requirements](#requirements)
- [Setup](#setup)
- [Scripts Overview](#scripts-overview)
  - [1. Ads and Suggestions Scraper](#1-ads-and-suggestions-scraper)
  - [2. Facebook Pages Scraper](#2-facebook-pages-scraper)
  - [3. Facebook Advertiser Ads Scraper](#3-facebook-advertiser-ads-scraper)
- [Configuration](#configuration)
- [Output Files](#output-files)
- [Troubleshooting](#troubleshooting)

## Requirements

- Python 3.9+
- SeleniumBase 4.x (`pip install seleniumbase==4.*`)
- Facebook account cookies (stored in `saved_cookies/`)

## Setup

1. **Clone the repository**

2. **Install dependencies**:
   ```bash
   pip install seleniumbase==4.* 
   ```

3. **Configure Facebook cookies**:
   - The scripts require Facebook authentication cookies
   - Default cookie files are stored in `saved_cookies/` directory:
     - `facebook_cookies.txt` (main cookie file)
     - `facebook_cookies2.txt` and `facebook_cookies3.txt` (alternative accounts)

4. **Configure target data**:
   - Edit script variables directly or use CSV files as described in each script section

## Scripts Overview

### 1. Ads and Suggestions Scraper

**File**: `ads_and_suggestions_scraper.py`

**Purpose**: Scrapes Facebook ads and/or search suggestions for specified (country, keyword) pairs.

**Configuration**:
- Edit the following variables at the top of the script:
  ```python
  MODE = "ads"        # Options: "ads" | "suggestions" | "ads_and_suggestions"
  HEADLESS = True     # Set to False for visual debugging
  ```
- Target pairs can be defined in the script or in a CSV file:
  ```python
  TARGET_PAIRS: list[tuple[str, str]] = [
      ("Ukraine",       "rental apartments"),
      ("United States", "rental properties"),
      ("Canada",        "vacation homes"),
  ]
  ```
- Alternatively, create a `targets.csv` file with country-keyword pairs (one per line)

**Usage**:
```bash
python ads_and_suggestions_scraper.py
```

**Outputs**:
- Generates JSON files in the `Results/` directory:
  - `ads.json` (if MODE="ads")
  - `suggestions.json` (if MODE="suggestions") 
  - `ads_and_suggestions.json` (if MODE="ads_and_suggestions")
- Files are never overwritten; new runs append to existing files

### 2. Facebook Pages Scraper

**File**: `facebook_pages_scraper.py`

**Purpose**: Scrapes detailed information about Facebook pages based on search keywords.

**Configuration**:
- Edit the following variables at the top of the script:
  ```python
  COOKIE_FILE = Path("saved_cookies/facebook_cookies.txt")
  HEADLESS = True
  SCROLLS = 6        # Number of scrolls before grabbing posts
  POST_LIMIT = 100   # Number of posts to scrape per page
  ACCOUNT_NUMBER = 1 # Choose which FB account to use (1/2/3)
  ```
- Define keywords directly in the script:
  ```python
  KEYWORDS = [
      "coca cola",
      "pepsi",
      "burger king",
  ]
  ```
- Or create a `keywords.csv` file with keywords and pages to visit

**Usage**:
```bash
python facebook_pages_scraper.py
```

**Outputs**:
- Generates a JSON file in `Results/all_pages.json`
- Contains detailed page information including:
  - Profile information
  - Page descriptions
  - Contact details
  - Transparency data
  - Recent posts

### 3. Facebook Advertiser Ads Scraper

**File**: `facebook_advertiser_ads.py`

**Purpose**: Scrapes ads from Facebook's Ad Library based on (country, keyword) pairs, focusing on collecting detailed ad information per advertiser page.

**Configuration**:
- Edit the following variables:
  ```python
  SCROLLS_SEARCH = 3
  SCROLLS_PAGE = 3
  COOKIE_FILE = Path("./saved_cookies/facebook_cookies.txt")
  ```
- Target pairs are defined the same way as in the ads_and_suggestions_scraper:
  ```python
  TARGET_PAIRS: list[tuple[str, str]] = [
      ("Ukraine",       "rental apartments"),
      ("United States", "rental properties"),
      ("Canada",        "vacation homes"),
  ]
  ```
- Or create a `targets.csv` file with country-keyword pairs

**Usage**:
```bash
python facebook_advertiser_ads.py
```

**Outputs**:
- Generates a JSON file in `Results/combined_ads.json`
- Each entry in the JSON contains:
  - Country and keyword used
  - List of pages with their ads
  - Detailed ad information for each page

## Configuration

### Main Configuration File

**File**: `config.json`

This file contains:
- Facebook account cookies for different accounts
- Proxy configuration (if used)

Format:
```json
{
  "accounts": {
    "1": {
      "proxy": "host,port,username,password",
      "cookies": [ ... ]
    },
    "2": { ... },
    "3": { ... }
  }
}
```

### Cookie Files

- Primary cookie file: `saved_cookies/facebook_cookies.txt`
- Additional cookie files:
  - `saved_cookies/facebook_cookies2.txt`
  - `saved_cookies/facebook_cookies3.txt`

## Output Files

All output files are stored in the `Results/` directory:

- `ads.json` - Facebook ads for specified country-keyword pairs
- `suggestions.json` - Search suggestions for specified country-keyword pairs
- `ads_and_suggestions.json` - Combined ads and suggestions
- `all_pages.json` - Detailed information about Facebook pages
- `combined_ads.json` - Detailed ad information per advertiser page

## Troubleshooting

### Common Issues

1. **Authentication Problems**:
   - Ensure your cookie files are up to date
   - If cookies are expired, log into Facebook manually and export new cookies

2. **Rate Limiting/Blocking**:
   - Facebook may block automated access
   - Try:
     - Reducing scraping speed (increase sleep times)
     - Using multiple accounts (ACCOUNT_NUMBER setting)
     - Using proxies

3. **Browser Issues**:
   - If you encounter browser crashes, set `HEADLESS = False` for debugging
   - Ensure you have the latest Chrome/Chromium browser installed

4. **Empty Results**:
   - Facebook's UI changes frequently
   - Check the XPath selectors in the scripts
   - Monitor with `HEADLESS = False` to see what's happening

### Proxy Configuration

The scripts support proxy usage via the config.json file. Format:
```
"proxy": "host,port,username,password"
```

### Debug Information

Debug files may be saved in the `debug/` directory.
