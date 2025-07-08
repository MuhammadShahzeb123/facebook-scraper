# Facebook Scraper API - Context

## Recent Changes (2025-07-08)

### Enhanced Posts Data Endpoint

1. **Updated `/data/posts` endpoint** to accept specific links as query parameters:
   - **Method**: GET
   - **Parameters**:
     - `links` (required): List of Facebook post URLs to retrieve data for
   - **Functionality**:
     - Searches through existing `results_*.json` files for posts matching the provided URLs
     - Automatically scrapes missing links using the `/scrape/posts` endpoint
     - Returns combined data from existing files and newly scraped posts
     - Provides detailed metadata about found vs. newly scraped data

### Fixed Unicode Encoding Issues in Advertiser Scraper

1. **Fixed Windows Unicode encoding errors in `facebook_advertiser_ads.py`**:
   - Replaced Unicode characters (`↳`, `→`, `•`, `…`) with ASCII equivalents (`->`, `|`, `...`)
   - Fixed `UnicodeEncodeError: 'charmap' codec can't encode character` errors on Windows
   - Ensured compatibility with Windows CP1252 encoding in console output

### Fixed Advertiser Scraper Error Handling

1. **Enhanced error handling in `facebook_advertiser_ads.py`**:
   - Added try-catch blocks around `extract_cards()` function calls
   - Added error handling in `_parse_card()` function to prevent crashes from malformed elements
   - Added error handling in link and image extraction to prevent stale element reference errors
   - Added graceful handling when no ads are found for a country/keyword pair

2. **Updated `AdvertiserScrapingRequest` model** with comprehensive parameters:
   - Added all parameters from `AdsScrapingRequest` to match PDF specifications
   - Includes: `max_scrolls`, `ad_category`, `status`, `languages`, `platforms`, `media_type`, `start_date`, `end_date`, `append_mode`, `advertisers`, `continuation`
   - Updated validation to provide better error messages

3. **Updated `run_advertiser_scraper()` function** to handle all new parameters:
   - Pass all filtering parameters to the scraper configuration
   - Properly handle environment variables for all parameter types
   - Enhanced error logging and debugging

### Updated Ads Scraping Endpoints

1. **Added missing `ads_limit` parameter** to `AdsScrapingRequest` model
   - Now supports limits from 1 to 1,000,000 ads
   - Properly integrated with the scraper's `ADS_LIMIT` environment variable

2. **Implemented new GET endpoint `/scrape/ads`** following PDF specifications:
   - **Method**: GET
   - **Parameters**:
     - `keyword` (required): Search term for filtering ads
     - `category` (optional, default="all"): Filter by ad category
     - `location` (optional, default="thailand"): Filter by location
     - `language` (optional, default="thai"): Filter by language
     - `advertiser` (optional, default="all"): Filter by advertiser
     - `platform` (optional, default="all"): Filter by platform
     - `media_type` (optional, default="all"): Filter by media type
     - `status` (optional, default="all"): Filter by status (active/inactive)
     - `start_date` (optional, default="June 18, 2018"): Start date filter
     - `end_date` (optional, default="today"): End date filter
     - `limit` (optional, default=1000, max=1,000,000): Results per page

3. **Implemented new GET endpoint `/scrape/advertisers`** following PDF specifications:
   - **Method**: GET
   - **Parameters**:
     - `keyword` (required): Search term for filtering ads by keyword
     - `scrape_page` (optional, default=True): If True, it will scrape the advertiser's page data

4. **Updated POST endpoint `/scrape/advertisers`** to match comprehensive parameter set:
   - **Method**: POST
   - **Parameters**:
     - `headless` (optional, default=True): Run browser in headless mode
     - `max_scrolls` (optional, default=10): Maximum number of scrolls
     - `ads_limit` (optional, default=1000): Maximum number of ads to extract
     - `target_pairs` (required): List of [country, keyword] pairs
     - `ad_category` (optional, default="all"): Ad category filter
     - `status` (optional, default="active"): Ad status filter
     - `languages` (optional, default=[]): List of language names or codes
     - `platforms` (optional, default=[]): List of platforms to filter by
     - `media_type` (optional, default="all"): Media type filter
     - `start_date` (optional): Start date in YYYY-MM-DD format
     - `end_date` (optional): End date in YYYY-MM-DD format
     - `append_mode` (optional, default=True): True to append to existing file
     - `advertisers` (optional, default=[]): List of specific advertiser names
     - `continuation` (optional, default=True): Continue from previous checkpoint

5. **Maintained backward compatibility** with original `/data/ads` and `/data/advertisers` endpoints

### Parameter Mapping Analysis

All PDF parameters are supported by the scraper:

| PDF Parameter | POST Endpoint Parameter | Scraper Support |
|---------------|------------------------|-----------------|
| keyword | target_pairs keyword | ✅ Full support |
| category | ad_category | ✅ Full support |
| location | target_pairs country | ✅ Full support |
| language | languages | ✅ Full support |
| advertiser | advertisers | ✅ Full support |
| platform | platforms | ✅ Full support |
| media_type | media_type | ✅ Full support |
| status | status | ✅ Full support |
| start_date | start_date | ✅ Full support |
| end_date | end_date | ✅ Full support |
| limit | ads_limit | ✅ Full support |

### File Structure

- All endpoints work with existing JSON files in `Results/` directory
- GET endpoints apply filtering to existing scraped data
- POST endpoints start new scraping jobs with specified parameters
- Advertiser scraper outputs to `combined_ads.json` file

### Technical Details

- Fixed function naming conflict between `/scrape/advertisers` and `/data/advertisers` endpoints
- Updated `run_advertiser_scraper` to handle all new parameters
- All parameters are passed through environment variables and config files to the scraper
- Comprehensive validation for all input parameters

### Next Steps

- Test the updated POST `/scrape/advertisers` endpoint functionality
- Verify all parameters are correctly handled by the underlying scraper
- Consider performance optimizations for large-scale scraping jobs