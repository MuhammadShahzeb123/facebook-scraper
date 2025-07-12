# Facebook Scraper Project Context

## Current Status: COMPREHENSIVE UNICODE ENCODING FIXES COMPLETED ✅

### Latest Update: Complete Unicode Support Across All API Endpoints (July 12, 2025)

**Problem**: Unicode encoding errors when processing Thai characters ("คุณสมบัติ") across multiple scraper endpoints:
```
UnicodeEncodeError: 'charmap' codec can't encode characters in position 17-25: character maps to <undefined>
```

**Root Cause**:
- Windows PowerShell console using cp1252 encoding by default
- Thai and other Unicode characters cannot be encoded in cp1252
- Errors occurred in print statements and subprocess output handling

**Comprehensive Solution Applied**:

1. **Enhanced Unicode handling in ALL scraper files**:
   - ✅ `ads_and_suggestions_scraper2.py`: Complete Unicode wrapper with safe print function
   - ✅ `suggestions_scraper_api.py`: Added Windows Unicode encoding fix
   - ✅ `facebook_advertiser_ads.py`: Enhanced existing Unicode handling, removed duplicate functions
   - ✅ `facebook_pages_scraper.py`: Upgraded from 'strict' to 'replace' error handling with safe print function
   - ✅ `app.py`: All subprocess calls now include `errors='replace'` parameter

2. **Consistent Unicode Strategy**:
   - Set `PYTHONIOENCODING='utf-8'` environment variable for all Windows systems
   - Wrapped print functions to handle encoding errors gracefully
   - Used `errors='replace'` in subprocess calls to prevent propagation of encoding errors
   - All Unicode characters now converted to ASCII-safe representations when console cannot display them

**API Endpoint Coverage**:
- ✅ `/scrape/ads` - Fixed in ads_and_suggestions_scraper2.py
- ✅ `/scrape/suggestions` - Fixed in suggestions_scraper_api.py
- ✅ `/scrape/advertisers` - Fixed in facebook_advertiser_ads.py
- ✅ `/scrape/pages` - Enhanced in facebook_pages_scraper.py
- ✅ All subprocess communications in app.py

**Testing**: All endpoints now handle Thai text "คุณสมบัติ" and other Unicode characters without crashing.

## Post URL Scraping Process Documentation (July 12, 2025)

### How Post URLs Are Extracted:

The system extracts Facebook post URLs using a multi-step process in `facebook_pages_scraper.py`:

1. **Main Function**: `extract_url(container: WebElement) -> str`
   - Located in lines 547-555
   - Uses XPath selector: `.//a[contains(@href, "/posts/") or contains(@href, "/videos/")][@role="link"]`
   - Targets anchor elements that contain either "/posts/" or "/videos/" in their href attribute
   - Specifically looks for elements with `@role="link"` to ensure they're actual clickable links

2. **Retry Mechanism**: `extract_with_retry()`
   - Wraps the URL extraction with retry logic (up to RETRY_LIMIT attempts)
   - Handles `NoSuchElementException` and `StaleElementReferenceException`
   - Waits 0.5 seconds between retry attempts
   - Returns None if all attempts fail

3. **Integration in Post Extraction**:
   ```python
   url = extract_with_retry(container, extract_url) or ""
   ```
   - Called within `extract_post()` function on line 611
   - Falls back to empty string if extraction fails
   - URL becomes part of the post data dictionary

4. **Post Container Detection**:
   - Searches for post containers using XPath: `//div[contains(@class,"x1yztbdb") and .//div[contains(@data-ad-preview,"message")]]`
   - Each container represents an individual Facebook post
   - URL extraction is performed on each container

5. **Validation**: Posts are only saved if they contain:
   - Text content OR URL OR likes/engagement OR images
   - This ensures empty/invalid posts are filtered out

The extracted URLs are Facebook permalinks that point directly to individual posts, allowing for later access or verification.

### Enhanced URL Extraction with Regex (July 12, 2025)

**IMPROVEMENT**: Updated `extract_url()` function to use regex pattern matching instead of relying solely on XPath selectors.

**Benefits**:
- **More Robust**: Searches entire HTML content of post containers rather than specific DOM elements
- **Flexible Pattern Matching**: Uses multiple regex patterns to catch various URL formats
- **Better Success Rate**: Can extract URLs even when DOM structure changes
- **Fallback Support**: Still uses original XPath method if regex fails

**Regex Patterns Used**:
1. `https://www\.facebook\.com/[^/]+/posts/[^"\s<>&]+` - Standard posts
2. `https://www\.facebook\.com/[^/]+/videos/[^"\s<>&]+` - Video posts
3. `https://m\.facebook\.com/[^/]+/posts/[^"\s<>&]+` - Mobile URLs
4. `https://[^"]*facebook\.com/[^"]*posts/[^"\s<>&]+` - Generic fallback

**URL Cleaning**: Automatically removes query parameters and HTML artifacts for cleaner URLs.

This approach successfully handles complex Facebook URLs like:
`https://www.facebook.com/<anything>/posts/pfbid02PPECF3af9eZo17o9pAhN12ZydrXgHarYkTqe1yRW2XSVS468RtoYN4yrokiMzeJpl?__cft__[0]=...`

## Previous Status: PROXY CONNECTIVITY ISSUE DIAGNOSED ✅

### Proxy Implementation Status
✅ **COMPLETED**: Full proxy integration across all target scrapers
- ✅ `proxy_utils_enhanced.py`: Advanced proxy management with health checking
- ✅ `ads_and_suggestions_scraper2.py`: Uses enhanced proxy utilities
- ✅ `facebook_advertiser_ads.py`: Uses enhanced proxy utilities
- ✅ API endpoints automatically use proxies via subprocess execution
- ✅ Comprehensive testing and diagnostic tools implemented

### Current Issue: ERR_EMPTY_RESPONSE Root Cause Identified

**Diagnostic Results (2025-07-12 06:58:00):**

**Proxy Status:**
- ✅ **WORKING**: PXY_c1elo8vs@122.8.43.208:8208 - Fully functional
- ❌ **FAILED**: arudiba@45.207.142.74:9568 - Connection refused (proxy server down)

**Facebook Access Test Results:**
- ✅ Direct Facebook access (no proxy): **200 OK** - Facebook is accessible
- ✅ Working proxy basic connectivity: **4/4 sites accessible**
- ⚠️ Facebook through working proxy: **400/301 status** - Facebook detecting proxy but responding

**Key Findings:**
1. **One proxy is completely functional** (122.8.43.208:8208)
2. **Second proxy is dead** (45.207.142.74:9568) - "Remote end closed connection"
3. **Facebook responds through working proxy** but with 400/301 status codes
4. **SeleniumBase integration working** - Successfully connects and shows proxy IP

### Root Cause Analysis
The ERR_EMPTY_RESPONSE is likely caused by:
1. **Dead proxy selection**: Random selection was picking the failed proxy 50% of the time
2. **Facebook proxy detection**: Working proxy gets 400 responses indicating Facebook detects/limits proxy traffic
3. **Connection timeouts**: Dead proxy causes connection failures that manifest as empty responses

### Solution Strategy
1. **Remove dead proxy** from proxies.json configuration
2. **Enhanced proxy testing** now automatically filters out dead proxies
3. **Browser behavior improvements** needed for better Facebook compatibility
4. **Consider residential proxies** if datacenter proxy blocking continues

### Technical Implementation
- ✅ Enhanced proxy utilities with connection testing and fallback mechanisms
- ✅ Automatic dead proxy filtering to prevent ERR_EMPTY_RESPONSE
- ✅ SeleniumBase integration confirmed working with proxy IP verification
- ✅ Comprehensive diagnostic tools for ongoing proxy health monitoring

### Next Steps
1. **Remove dead proxy** (45.207.142.74:9568) from proxies.json
2. **Test scrapers** with only working proxy to confirm ERR_EMPTY_RESPONSE resolution
3. **Monitor Facebook responses** for rate limiting or blocking patterns
4. **Consider proxy rotation strategy** with multiple working proxies for scale

### Files Updated in This Session
- `proxy_utils_enhanced.py`: Advanced proxy management with testing
- `proxy_diagnostics.py`: Comprehensive proxy connectivity diagnostics
- `test_working_proxy.py`: Simple Facebook access validation
- `ads_and_suggestions_scraper2.py`: Updated to use enhanced proxy utilities
- `facebook_advertiser_ads.py`: Updated to use enhanced proxy utilities

## Issue Resolution History


**Problem 4**: Incorrect verified status and ads detection in Facebook pages scraper.

**Root Cause**: The scraper was using unreliable methods to detect verified pages and running ads status.

**Solution Applied**:

1. **Fixed verified status detection** in `extract_home()` function:
   - Changed from checking SVG elements to searching for exact text `<title>Verified account</title>` in page source
   - This provides more reliable verification status detection

2. **Fixed ads running status detection** in `extract_transparency()` function:
   - Changed from checking transparency modal text to searching for exact text `"This Page is currently running ads"` in page source
   - This provides more accurate ads status detection

3. **Improved page ID extraction** in `extract_transparency()` function:
   - Added primary method: Extract page ID from page source using regex pattern `purpose of this Page\.(\d+)Page ID`
   - This looks for a number that appears after text ending with "purpose of this Page." and before "Page ID"
   - Kept existing XPath methods as fallbacks for robustness
   - Added proper error handling and logging for page ID extraction failures

**Changes Made**:
- Modified `extract_home()` function to use page source for verified status
- Modified `extract_transparency()` function to use page source for ads status
- Enhanced page ID extraction with new regex pattern and fallback methods
- All changes maintain backward compatibility with existing functionality

## Latest Update (July 12, 2025 - Advanced Page ID Extraction with Debugging)

**Problem 6**: Page ID extraction still failing despite multiple regex patterns.

**Root Cause**: The regex patterns were not specific enough to match the exact HTML structure that Facebook uses for page IDs.

**Solution Applied**:

1. **Added HTML-structure-specific regex patterns** based on user-provided HTML:
   - Primary pattern: `(\d{10,})</span></div><div><div><span><span[^>]*>Page ID` - matches the exact structure
   - Alternative patterns: `<span[^>]*>(\d{10,})</span>.*?Page ID` and variations
   - Added class-specific pattern: `class="[^"]*x193iq5w[^"]*"[^>]*>(\d{10,})</span>.*?Page ID`

2. **Enhanced debugging capabilities**:
   - Added comprehensive logging to show which patterns are being tried
   - Added context extraction to show 400 characters around "Page ID" text
   - Added fallback debugging to find any numbers near "Page ID" text
   - Added pattern match validation and length checking with debug output

3. **Improved regex matching**:
   - Added `re.DOTALL` flag to handle newlines in HTML structure
   - Enhanced pattern specificity to match Facebook's exact HTML structure

## Proxy Implementation (July 12, 2025)

**Task Completed**: Successfully implemented proxy support across all Facebook scrapers.

**Solution Applied**:

1. **Created `proxy_utils.py`** - A robust utility module that:
   - Loads proxies from `proxies.json` file
   - Randomly selects proxies for load balancing
   - Formats them properly for SeleniumBase
   - Handles errors gracefully with fallbacks

2. **Updated scrapers with proxy support**:
   - `ads_and_suggestions_scraper2.py` - Added proxy import and integration
   - `facebook_advertiser_ads.py` - Added proxy import and integration
   - `facebook_pages_scraper.py` - Already had proxy support (no changes needed)

3. **Key features implemented**:
   - Automatic proxy rotation - Different runs use different proxies
   - Secure logging - Passwords are masked in console output
   - Graceful fallback - Works without proxy if none available
   - Zero configuration changes - Uses existing `proxies.json`
   - API compatibility - Proxy support works through API endpoints

**Current Issue (July 12, 2025)**: ERR_EMPTY_RESPONSE from Facebook when using proxies

**Root Cause**: Proxy connection issues or blocked proxy servers

**Investigation Needed**:
- Test proxy connectivity
- Check if proxies are blocked by Facebook
- Implement proxy health checking and rotation
- Add fallback mechanisms for failed proxy connections
   - Added multiple fallback patterns for different page layouts

**Technical Implementation**:
- Pattern 1: Exact HTML structure match based on provided element
- Pattern 2-4: Variations handling different span structures
- Pattern 5-9: Original fallback patterns for backward compatibility
- Debug logging shows page source length, context around "Page ID", and pattern matching results

**Changes Made**:
- Enhanced `extract_transparency()` function with 9 different regex patterns
- Added comprehensive debugging output for troubleshooting
- Improved error handling and pattern validation
- All changes maintain backward compatibility

This should now successfully extract page IDs from the specific HTML structure you provided: `127304827127079`.