# Facebook Scraper REST API

A powerful REST API for automated Facebook scraping with zero manual intervention. This API provides endpoints to start scraping jobs and retrieve data from various Facebook sources including ads, pages, and advertiser information.

## 🚀 Features

- **Zero Manual Labor**: Fully automated scraping with RESTful API endpoints
- **Three Main Scrapers**: Ads & Suggestions, Facebook Pages, and Advertiser Ads
- **Job Management**: Start scraping jobs and track their progress
- **JSON Data Retrieval**: Get scraped data in structured JSON format
- **Background Processing**: Non-blocking scraping operations
- **Rate Limiting**: Built-in protection against API abuse
- **Comprehensive Documentation**: Auto-generated OpenAPI docs

## 📋 Table of Contents

- [Quick Start](#quick-start)
- [API Endpoints](#api-endpoints)
- [Installation](#installation)
- [Usage Examples](#usage-examples)
- [Data Formats](#data-formats)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)

## ⚡ Quick Start

1. **Install Dependencies**:

```bash
pip install -r requirements.txt
```

2. **Start the API Server**:

```bash
python app.py
```

3. **Access the API**:
   - API Base URL: `http://localhost:8000`
   - Interactive Docs: `http://localhost:8000/docs`
   - Alternative Docs: `http://localhost:8000/redoc`

## 🔌 API Endpoints

### Health & Status

- `GET /health` - Health check
- `GET /status` - API status and available endpoints

### Scraping Jobs (POST)

- `POST /scrape/ads` - Start ads & suggestions scraping
- `POST /scrape/advertisers` - Start advertiser ads scraping
- `POST /scrape/pages` - Start Facebook pages scraping

### Data Retrieval (GET)

- `GET /data/ads` - Get ads & suggestions data
- `GET /data/advertisers` - Get advertiser ads data
- `GET /data/pages` - Get Facebook pages data

### Job Management

- `GET /jobs` - List all jobs
- `GET /jobs/{job_id}` - Get specific job status

## 📦 Installation

### Prerequisites

- Python 3.9+
- Chrome/Chromium browser (for Selenium)

### Setup Steps

1. **Clone the repository**:

```bash
git clone <repository-url>
cd facebook-scraper
```

2. **Install Python dependencies**:

```bash
pip install -r requirements.txt
```

3. **Prepare Facebook cookies** (Place in `saved_cookies/facebook_cookies.txt`)

4. **Configure target data** (Optional - can be done via API)

5. **Start the API server**:

```bash
python app.py
```

## 💡 Usage Examples

### Starting Scraping Jobs

#### 1. Ads & Suggestions Scraper

**Endpoint**: `POST /scrape/ads`

**Purpose**: Scrapes Facebook ads and search suggestions for specified country-keyword pairs.

**Request Body**:

```json
{
  "mode": "ads",
  "headless": true,
  "ads_limit": 1000,
  "target_pairs": [
    ["Ukraine", "rental apartments"],
    ["United States", "rental properties"],
    ["Canada", "vacation homes"]
  ]
}
```

**Example with curl**:

```bash
curl -X POST "http://localhost:8000/scrape/ads" \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "ads_and_suggestions",
    "headless": true,
    "ads_limit": 500,
    "target_pairs": [
      ["Germany", "apartments"],
      ["France", "houses"]
    ]
  }'
```

#### 2. Facebook Pages Scraper

**Endpoint**: `POST /scrape/pages`

**Purpose**: Searches Facebook for pages based on keywords and scrapes their posts.

**Request Body**:

```json
{
  "headless": true,
  "post_limit": 100,
  "account_number": 2,
  "keywords": [
    "coca cola",
    "pepsi",
    "burger king"
  ]
}
```

**Parameters**:
- `headless` (bool): Run browser in headless mode (default: true)
- `post_limit` (int): Number of posts to scrape per page (1-500, default: 100)
- `account_number` (int): Facebook account to use (1-3, default: 2)
- `keywords` (array): Keywords to search for (required, 1-10 keywords)

#### 3. Advertiser Ads Scraper

**Endpoint**: `POST /scrape/advertisers`

**Purpose**: Scrapes advertiser-specific ads from Facebook's Ad Library.

**Request Body**:

```json
{
  "headless": true,
  "ads_limit": 1000,
  "target_pairs": [
    ["Ukraine", "rental apartments"],
    ["United States", "rental properties"]
  ]
}
```

### Retrieving Data

#### Get Ads Data

```bash
curl -X GET "http://localhost:8000/data/ads"
```

**Response**:

```json
{
  "success": true,
  "data": [
    {
      "country": "Ukraine",
      "keyword": "rental apartments",
      "ads": [...],
      "suggestions": [...]
    }
  ],
  "file_info": {
    "file_path": "Results/ads.json",
    "size_mb": 2.5,
    "last_modified": "2025-06-20T03:14:16"
  },
  "timestamp": "2025-06-20T03:14:16"
}
```

#### Get Pages Data

```bash
curl -X GET "http://localhost:8000/data/pages"
```

#### Get Job Status

```bash
curl -X GET "http://localhost:8000/jobs/job_1713456789_1234"
```

**Response**:

```json
{
  "job_id": "job_1713456789_1234",
  "status": "completed",
  "details": {
    "status": "completed",
    "type": "ads",
    "started_at": "2025-06-20T03:10:00",
    "completed_at": "2025-06-20T03:14:16"
  },
  "timestamp": "2025-06-20T03:14:16"
}
```

## 📊 Data Formats

### Ads & Suggestions Data Structure

```json
{
  "country": "Ukraine",
  "keyword": "rental apartments",
  "suggestions": [
    {
      "suggestion_text": "apartment rental ukraine",
      "timestamp": "2025-06-20T03:14:16"
    }
  ],
  "ads": [
    {
      "ad_id": "123456789",
      "advertiser_name": "Property Co",
      "ad_text": "Find your perfect apartment...",
      "image_url": "https://...",
      "timestamp": "2025-06-20T03:14:16"
    }
  ]
}
```

### Pages Data Structure

```json
{
  "page_name": "Coca Cola Pakistan",
  "page_url": "https://www.facebook.com/CokePakistan",
  "posts": [
    {
      "post_id": "123456789",
      "post_text": "Enjoy the refreshing taste...",
      "likes": 1250,
      "comments": 45,
      "shares": 23,
      "timestamp": "2025-06-20T03:14:16"
    }
  ],
  "page_info": {
    "followers": 150000,
    "likes": 145000,
    "description": "Official Coca Cola page..."
  }
}
```

### Advertiser Ads Data Structure

```json
{
  "advertiser_name": "Property Solutions Inc",
  "country": "Ukraine",
  "keyword": "rental apartments",
  "ads": [
    {
      "ad_id": "987654321",
      "ad_text": "Premium apartments available...",
      "impressions": "1K-5K",
      "spend": "$100-$500",
      "timestamp": "2025-06-20T03:14:16"
    }
  ]
}
```

## ⚙️ Configuration

### Environment Variables

You can set these environment variables to override default settings:

```bash
# For ads scraper
export MODE="ads_and_suggestions"
export HEADLESS="true"
export ADS_LIMIT="1000"

# For pages scraper
export SEARCH_METHOD="keyword"
export POST_LIMIT="100"
export ACCOUNT_NUMBER="2"
```

### Config Files

The API automatically generates temporary config files for each scraping job, so no manual configuration is needed.

### Facebook Cookies

Place your Facebook session cookies in:
- `saved_cookies/facebook_cookies.txt`
- `saved_cookies/facebook_cookies2.txt`
- `saved_cookies/facebook_cookies3.txt`

## 🔧 Troubleshooting

### Common Issues

1. **API Server Won't Start**
   ```bash
   # Check if port 8000 is available
   netstat -an | find "8000"

   # Kill any process using the port
   taskkill /f /pid <PID>
   ```

2. **Scraping Jobs Fail**
   - Check Facebook cookies are valid
   - Ensure Chrome/Chromium is installed
   - Verify target data format

3. **No Data Returned**
   - Check if scraping job completed successfully
   - Verify JSON files exist in `Results/` directory
   - Check job status via `/jobs/{job_id}` endpoint

### Debug Mode

Start the API with debug logging:

```bash
python app.py --log-level debug
```

### Checking Logs

View API logs:

```bash
tail -f api.log
```

## 🌐 API Documentation

### Interactive Documentation

Visit `http://localhost:8000/docs` for interactive Swagger UI documentation where you can:

- View all available endpoints
- Test API calls directly from the browser
- See request/response schemas
- Download OpenAPI specification

### Alternative Documentation

Visit `http://localhost:8000/redoc` for ReDoc-style documentation.

## 📈 Rate Limiting

The API includes built-in rate limiting:
- 10 requests per minute per IP address
- Configurable in `app.py`

## 🚦 API Status Codes

- `200` - Success
- `400` - Bad Request (invalid parameters)
- `404` - Not Found (job/data not found)
- `429` - Too Many Requests (rate limited)
- `500` - Internal Server Error

## 📁 Output Files

All scraped data is saved in the `Results/` directory:

- `ads.json` - Ads & suggestions data
- `all_pages.json` - Facebook pages data
- `combined_ads.json` - Advertiser ads data
- `*_checkpoint.json` - Progress checkpoints

## 🎯 Best Practices

1. **Start Small**: Begin with small target lists to test
2. **Monitor Jobs**: Use `/jobs` endpoint to track progress
3. **Handle Rate Limits**: Space out API requests appropriately
4. **Backup Data**: Regularly backup the `Results/` directory
5. **Valid Cookies**: Keep Facebook cookies fresh and valid

## 📞 Support

For issues or questions:
1. Check the troubleshooting section
2. Review API logs
3. Test with the interactive documentation
4. Ensure all prerequisites are met

---

**Note**: This tool is for educational and research purposes. Ensure compliance with Facebook's Terms of Service and applicable laws.
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
