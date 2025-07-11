# Facebook Scraper Project Context

## Project Overview

This is a comprehensive Facebook scraper project that includes web scraping capabilities for ads, suggestions, pages, and advertisers. The project provides both standalone Python scripts and REST API endpoints.

## Issue Resolution (July 11, 2025)

**Problem 1**: The ads scraping endpoint was not working but the standalone file was working.

**Root Cause**: The API endpoint in `app.py` was calling `ads_and_suggestions_scraper.py` but the working, updated file is `ads_and_suggestions_scraper2.py`.

**Solution Applied**:

1. **Fixed the file reference** in `app.py` line 484:
   - Changed: `cmd = [sys.executable, "ads_and_suggestions_scraper.py"]`
   - To: `cmd = [sys.executable, "ads_and_suggestions_scraper2.py"]`

2. **Added missing SCROLLS parameter** support:
   - Updated `ads_and_suggestions_scraper2.py` to accept `SCROLLS` from environment variable
   - Added `"SCROLLS": str(request_data.max_scrolls)` to API environment variables

3. **Added missing advertiser parameters**:
   - Added `"SCRAPE_ADVERTISER_ADS": "False"` (disabled for ads mode)
   - Added `"ADVERTISER_ADS_LIMIT": "100"` (default value)

**Problem 2**: The advertiser scraping endpoint was not spawning Chrome browser.

**Root Cause**: Multiple issues in advertiser endpoint:
1. Hardcoded `headless=True` in `facebook_advertiser_ads.py`
2. Missing environment variable support
3. Incorrect environment variable names between API and scraper

**Solution Applied**:

1. **Fixed environment variable names** in `app.py`:
   - Added proper environment variables: HEADLESS, SCROLLS_SEARCH, SCROLLS_PAGE, CONTINUATION, TARGET_PAIRS

2. **Added environment variable support** to `facebook_advertiser_ads.py`:
   - Made HEADLESS configurable via environment variable
   - Added support for SCROLLS_SEARCH, SCROLLS_PAGE, CONTINUATION, TARGET_PAIRS

**Problem 3**: Unicode encoding error in advertiser scraper output.

**Root Cause**: Windows console cannot display Unicode characters (e.g., Turkish İ character '\u0130') in page names.

**Solution Applied**:

1. **Added Unicode handling** to `facebook_advertiser_ads.py`:
   - Added proper encoding setup for Windows console
   - Created `safe_print()` function to handle Unicode encoding errors
   - Replaced problematic print statements with safe Unicode handling

2. **Error Details**:
   - Error: `'charmap' codec can't encode character '\u0130' in position 28`
   - Fixed by implementing fallback character replacement for Windows console compatibility

## Working vs Non-Working Files

- ✅ **Working**: `ads_and_suggestions_scraper2.py` - Contains the latest, functional scraping logic
- ❌ **Old Version**: `ads_and_suggestions_scraper.py` - Older version (was being called by API)

## Key Features in Working File (ads_and_suggestions_scraper2.py)

- Advanced filtering options (category, status, languages, platforms, media type, date ranges)
- Robust error handling and retry logic
- Cookie management for Facebook authentication
- Multiple scraping modes: ads, suggestions, ads_and_suggestions
- Advertiser ads scraping capability
- Continuation/checkpoint system for long-running jobs
- Proper URL engineering for applying filters

## API Structure

- FastAPI-based REST API
- Background task processing for scraping jobs
- CORS enabled for web integration
- Comprehensive request/response models
- Job status tracking

## Files Structure

- `app.py` - Main FastAPI application (✅ Fixed to call correct scraper)
- `ads_and_suggestions_scraper2.py` - Working scraper implementation (✅ Enhanced with SCROLLS support)
- `ads_and_suggestions_scraper.py` - Older scraper version (not used by API anymore)
- `config.json` - Account configurations with cookies and proxies
- Various API wrapper files for different scraping types

## API Environment Variables Now Properly Passed

- ✅ MODE (set to "ads")
- ✅ HEADLESS
- ✅ ADS_LIMIT
- ✅ SCROLLS (newly added)
- ✅ TARGET_PAIRS
- ✅ AD_CATEGORY
- ✅ STATUS
- ✅ LANGUAGES
- ✅ PLATFORMS
- ✅ MEDIA_TYPE
- ✅ START_DATE / END_DATE
- ✅ APPEND
- ✅ ADVERTISERS
- ✅ CONTINUATION
- ✅ SCRAPE_ADVERTISER_ADS
- ✅ ADVERTISER_ADS_LIMIT

## How to Test the Fix

1. Start the API: `python app.py`
2. API will run on `http://localhost:8000`
3. Access docs at `http://localhost:8000/docs`
4. Use the `/scrape/ads` endpoint with proper parameters
5. Monitor job status via job ID endpoints

## Additional Issue Fixed (July 11, 2025)

**Problem**: The advertiser scraping endpoint (`/scrape/advertisers`) was not working - it didn't spawn Chrome or scrape any data.

**Root Causes**:
1. The `facebook_advertiser_ads.py` script had hardcoded `headless=True` instead of reading from environment
2. The script wasn't properly reading environment variables for configuration
3. The API was passing wrong environment variable names that didn't match the script

**Solution Applied**:

1. **Fixed hardcoded headless mode** in `facebook_advertiser_ads.py`:
   - Changed: `with SB(uc=True, headless=True) as sb:`
   - To: `with SB(uc=True, headless=HEADLESS) as sb:`

2. **Added environment variable support** to config section:
   - Added: `HEADLESS = os.getenv("HEADLESS", "True").lower() == "true"`
   - Added: `SCROLLS_SEARCH = int(os.getenv("SCROLLS_SEARCH", "3"))`
   - Added: `SCROLLS_PAGE = int(os.getenv("SCROLLS_PAGE", "3"))`
   - Added: `CONTINUATION = os.getenv("CONTINUATION", "False").lower() == "true"`
   - Added proper TARGET_PAIRS environment variable support

3. **Fixed API environment variables** in `app.py`:
   - Updated environment variable names to match what the script expects
   - Simplified to only pass variables the script actually uses
   - Fixed variable name from `MAX_SCROLLS` to `SCROLLS_SEARCH` and `SCROLLS_PAGE`

## Status: ✅ BOTH ENDPOINTS FIXED

Both the ads scraping endpoint (`/scrape/ads`) and advertiser scraping endpoint (`/scrape/advertisers`) should now work properly with proper Chrome spawning and parameter passing.
