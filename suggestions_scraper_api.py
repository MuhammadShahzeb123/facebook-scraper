#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# ── Unicode Output Fix for Windows ────────────────────────────────────────
import sys
import os

# Fix Windows console encoding for Unicode output
if sys.platform == "win32":
    # Set environment variable for UTF-8 encoding
    os.environ['PYTHONIOENCODING'] = 'utf-8'

    # Wrap print function to handle encoding errors gracefully
    original_print = print
    def safe_print(*args, **kwargs):
        try:
            return original_print(*args, **kwargs)
        except UnicodeEncodeError:
            # Convert all args to strings and handle encoding
            safe_args = []
            for arg in args:
                try:
                    safe_args.append(str(arg).encode('ascii', 'replace').decode('ascii'))
                except:
                    safe_args.append(repr(arg))
            return original_print(*safe_args, **kwargs)

    # Replace print function globally
    print = safe_print

"""
Suggestions Scraper API - v2 (Robust approach)
This module provides API endpoints for scraping Facebook Ad Library suggestions
using the exact same robust logic as ads_and_suggestions_scraper2.py
"""

import json
import time
import re
import unicodedata
import asyncio
import subprocess
import os
import glob
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse, quote
from datetime import datetime

from seleniumbase import SB
from proxy_utils_enhanced import get_proxy_string_with_fallback  # Import enhanced proxy utility
from selenium.common.exceptions import (
    NoSuchElementException, StaleElementReferenceException,
    ElementNotInteractableException,
)
from selenium.webdriver.common.keys import Keys

# Global settings
COOKIE_FILE = Path("./saved_cookies/facebook_cookies.txt")
OUTPUT_DIR = Path("Results")
OUTPUT_DIR.mkdir(exist_ok=True)

AD_LIBRARY_URL = (
    "https://www.facebook.com/ads/library/"
    "?active_status=active&ad_type=all&country=ALL"
    "&is_targeted_country=false&media_type=all"
)

# ── Constants for month-aware ad extraction ─────────────────────────────────
COMMON_HEAD = (
    "/html/body/div[1]/div/div/div/div/div/div/div[1]/div/div/div"
)
MONTH_BASE = f"{COMMON_HEAD}/div[5]/div[2]"   # COMMON_HEAD defined earlier
GAP_LIMIT  = 5                                # stop after 5 empty slots

def load_cookies() -> list[dict]:
    """Load cookies from file with proper error handling."""
    if not COOKIE_FILE.exists():
        print(f"[WARNING] Cookie file not found: {COOKIE_FILE}")
        return []

    try:
        raw_text = COOKIE_FILE.read_text(encoding="utf-8")
        cookies = json.loads(raw_text)
        print(f"[SUCCESS] Loaded {len(cookies)} cookies from {COOKIE_FILE}")
        return cookies
    except UnicodeDecodeError:
        print(f"[ERROR] Could not decode cookie file as UTF-8: {COOKIE_FILE}")
        return []
    except json.JSONDecodeError as e:
        print(f"[ERROR] Could not parse JSON in cookie file: {COOKIE_FILE} - {e}")
        return []
    except Exception as e:
        print(f"[ERROR] Unexpected error loading cookies: {e}")
        return []

def wait_click(sb, selector: str, *, by="css selector", timeout=10):
    """Wait for element to be visible and click it with error handling."""
    try:
        sb.wait_for_element_visible(selector, by=by, timeout=timeout)
        sb.click(selector, by=by)
        print(f"[SUCCESS] Clicked element: {selector}")
    except Exception as e:
        print(f"[ERROR] Failed to click element: {selector}")
        print(f"[ERROR] Error details: {str(e)}")

        # Try to provide helpful debugging info
        try:
            if by == "xpath":
                elements = sb.find_elements(selector, by=by)
                print(f"[DEBUG] Found {len(elements)} elements matching XPath")
                if len(elements) > 0:
                    for i, elem in enumerate(elements[:3]):  # Show first 3 elements
                        try:
                            print(f"[DEBUG] Element {i}: text='{elem.text}', visible={elem.is_displayed()}")
                        except:
                            print(f"[DEBUG] Element {i}: could not get details")
        except Exception as debug_error:
            print(f"[DEBUG] Could not get debugging info: {debug_error}")

        raise e

def safe_type(sb, selector: str, text: str, *, by="css selector", press_enter: bool = True, timeout: int = 10):
    """Safely type text into an input field with enhanced error handling."""
    try:
        sb.wait_for_element_visible(selector, by=by, timeout=timeout)
        elm = sb.find_element(selector, by=by)
        elm.clear()
        sb.sleep(0.5)  # Small delay after clearing
        elm.send_keys(text)
        time.sleep(1.0)
        if press_enter:
            elm.send_keys(Keys.RETURN)
            time.sleep(2.0)
        print(f"[SUCCESS] Typed '{text}' into element: {selector}")
    except Exception as e:
        print(f"[ERROR] Failed to type into element: {selector}")
        print(f"[ERROR] Text to type: '{text}'")
        print(f"[ERROR] Error details: {str(e)}")
        raise e

def extract_suggestions(sb, keyword: str) -> list[Dict[str, Any]]:
    """Extract suggestions from the keyword dropdown - exact v2 logic."""
    suggestions: list[dict] = []
    KEYWORD_INPUT = ('//input[@type="search" and contains(@placeholder,"keyword") '
                     'and not(@aria-disabled="true")]')

    # Type WITHOUT <Enter> so the dropdown stays open
    safe_type(sb, KEYWORD_INPUT, keyword, by="xpath", press_enter=False)
    time.sleep(3)

    # Try to harvest all <li role="option"> nodes
    items = sb.find_elements("//li[@role='option']", by="xpath")
    for item in items:
        try:
            data = {
                "page_id":    item.get_attribute("id") or "",
                "name":       item.text.split("\n")[0].strip(),
                "raw_text":   item.text.strip(),
            }
            if data["name"]:
                suggestions.append(data)
        except Exception:
            continue

    # Clear search box for next keyword
    sb.find_element(KEYWORD_INPUT, by="xpath").clear()
    return suggestions

def _extract_page_id_from_suggestion(suggestion: Dict[str, Any]) -> str | None:
    """Extract page_id from suggestion, handling both direct pageID and quoted formats."""
    page_id = suggestion.get("page_id", "")

    # Handle pageID:123456 format
    if page_id.startswith("pageID:"):
        return page_id.split(":", 1)[1]

    # Handle quoted format like "properties" - skip this as it's not a real page
    if page_id.startswith('"') and page_id.endswith('"'):
        return None

    # If it's already a numeric ID, return it
    if page_id.isdigit():
        return page_id

    return None


def _build_advertiser_url(country: str, page_id: str) -> str:
    """Build URL for advertiser's ads page."""
    # Map country names to country codes (add more as needed)
    country_code_map = {
        "Thailand": "TH",
        "United States": "US",
        "United Kingdom": "GB",
        "Canada": "CA",
        "Australia": "AU",
        "Germany": "DE",
        "France": "FR",
        "Italy": "IT",
        "Spain": "ES",
        "Netherlands": "NL",
        "Belgium": "BE",
        "Sweden": "SE",
        "Norway": "NO",
        "Denmark": "DK",
        "Finland": "FI",
        "Poland": "PL",
        "Czech Republic": "CZ",
        "Hungary": "HU",
        "Austria": "AT",
        "Switzerland": "CH",
        "Ireland": "IE",
        "Portugal": "PT",
        "Greece": "GR",
        "Turkey": "TR",
        "India": "IN",
        "Japan": "JP",
        "South Korea": "KR",
        "Singapore": "SG",
        "Malaysia": "MY",
        "Indonesia": "ID",
        "Philippines": "PH",
        "Vietnam": "VN",
        "Brazil": "BR",
        "Mexico": "MX",
        "Argentina": "AR",
        "Chile": "CL",
        "Colombia": "CO",
        "South Africa": "ZA",
        "Egypt": "EG",
        "Nigeria": "NG",
        "Kenya": "KE",
        "Morocco": "MA",
        "Israel": "IL",
        "United Arab Emirates": "AE",
        "Saudi Arabia": "SA",
        "Russia": "RU",
        "Ukraine": "UA",
        "China": "CN",
        "Taiwan": "TW",
        "Hong Kong": "HK",
        "New Zealand": "NZ",
    }

    # Get country code, fallback to country name if not found
    country_code = country_code_map.get(country, country)

    # Build the URL
    return (
        f"https://www.facebook.com/ads/library/"
        f"?active_status=active&ad_type=all&country=ALL"
        f"&is_targeted_country=false&media_type=all"
        f"&search_type=page&view_all_page_id={page_id}"
    )


def extract_advertiser_ads(sb, country: str, page_id: str, advertiser_name: str, limit: int = None):
    """Extract ads from a specific advertiser's page."""
    print(f"[INFO] Scraping ads from advertiser: {advertiser_name} (Page ID: {page_id})")

    # Build and navigate to advertiser URL
    advertiser_url = _build_advertiser_url(country, page_id)

    # Apply filters to the URL (if available)
    filtered_url = advertiser_url  # Basic implementation, can be enhanced with filters

    print(f"[INFO] Navigating to: {filtered_url}")
    sb.open(filtered_url)
    sb.sleep(5)

    # Extract ads using the existing logic (with infinite scroll)
    ads = extract_ads(sb, limit=limit)

    # Add advertiser info to each ad
    for ad in ads:
        ad["scraped_from_advertiser"] = advertiser_name
        ad["advertiser_page_id"] = page_id

    print(f"[INFO] Found {len(ads)} ads from advertiser: {advertiser_name}")
    return ads

    # Handle quoted format like "properties" - skip this as it's not a real page
    if page_id.startswith('"') and page_id.endswith('"'):
        return None

    # If it's already a numeric ID, return it
    if page_id.isdigit():
        return page_id

    return None

def _build_advertiser_url(country: str, page_id: str) -> str:
    """Build URL for advertiser's ads page."""
    # Map country names to country codes (add more as needed)
    country_code_map = {
        "Thailand": "TH",
        "United States": "US",
        "United Kingdom": "GB",
        "Canada": "CA",
        "Australia": "AU",
        "Germany": "DE",
        "France": "FR",
        "Italy": "IT",
        "Spain": "ES",
        "Netherlands": "NL",
        "Belgium": "BE",
        "Sweden": "SE",
        "Norway": "NO",
        "Denmark": "DK",
        "Finland": "FI",
        "Poland": "PL",
        "Czech Republic": "CZ",
        "Hungary": "HU",
        "Austria": "AT",
        "Switzerland": "CH",
        "Ireland": "IE",
        "Portugal": "PT",
        "Greece": "GR",
        "Turkey": "TR",
        "India": "IN",
        "Japan": "JP",
        "South Korea": "KR",
        "Singapore": "SG",
        "Malaysia": "MY",
        "Indonesia": "ID",
        "Philippines": "PH",
        "Vietnam": "VN",
        "Brazil": "BR",
        "Mexico": "MX",
        "Argentina": "AR",
        "Chile": "CL",
        "Colombia": "CO",
        "South Africa": "ZA",
        "Egypt": "EG",
        "Nigeria": "NG",
        "Kenya": "KE",
        "Morocco": "MA",
        "Israel": "IL",
        "United Arab Emirates": "AE",
        "Saudi Arabia": "SA",
        "Russia": "RU",
        "Ukraine": "UA",
        "China": "CN",
        "Taiwan": "TW",
        "Hong Kong": "HK",
        "New Zealand": "NZ",
    }

    # Get country code, fallback to country name if not found
    country_code = country_code_map.get(country, country)

    # Build the URL
    return (
        f"https://www.facebook.com/ads/library/"
        f"?active_status=active&ad_type=all&country=ALL"
        f"&is_targeted_country=false&media_type=all"
        f"&search_type=page&view_all_page_id={page_id}"
    )

# ── Data saving functionality ─────────────────────────────────────────────

def next_output_path(mode: str = "suggestions") -> Path:
    """Return output file path based on APPEND setting (hardcoded to True)"""
    APPEND = True  # Hardcoded append mode

    if APPEND:
        return OUTPUT_DIR / f"{mode}.json"
    else:
        counter = 1
        while True:
            p = OUTPUT_DIR / f"{mode}_{counter:03d}.json"
            if not p.exists():
                return p
            counter += 1


def save_data_to_results(data: Dict[str, Any]) -> None:
    """Save data to Results directory with append functionality"""
    try:
        out_file = next_output_path("suggestions")

        if out_file.exists():
            try:
                existing = json.loads(out_file.read_text(encoding="utf-8"))
                if not isinstance(existing, list):
                    existing = []
            except Exception as e:
                print(f"[WARNING] Error reading existing file {out_file}: {e}, starting fresh")
                existing = []
        else:
            existing = []

        existing.append(data)

        # Save data with UTF-8 encoding
        out_file.write_text(
            json.dumps(existing, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        print(f"[INFO] Data saved to {out_file}")
        print(f"[INFO] Total records in file: {len(existing)}")

    except Exception as e:
        print(f"[ERROR] Failed to save data: {e}")
        # Try to save to a backup file
        try:
            backup_file = OUTPUT_DIR / f"backup_suggestions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            backup_file.write_text(
                json.dumps([data], indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
            print(f"[INFO] Data saved to backup file: {backup_file}")
        except Exception as backup_error:
            print(f"[ERROR] Failed to save backup file: {backup_error}")


# ── Main scraping functions ───────────────────────────────────────────────

def scrape_suggestions_sync(country: str, keyword: str, scrape_ads: bool = False,
                           advertiser_ads_limit: int = 100, headless: bool = True) -> dict:
    """
    Main suggestions scraping function - exact v2 logic.

    Args:
        country: Country to scrape from
        keyword: Keyword to search for
        scrape_ads: Whether to also scrape ads from each advertiser found
        advertiser_ads_limit: Maximum number of ads to extract per advertiser page
        headless: Whether to run in headless mode

    Returns:
        Dictionary with suggestions and optionally ads data
    """
    print(f"[INFO] Starting suggestions scraping for: {country} | {keyword}")

    # Get proxy configuration
    proxy_string = get_proxy_string_with_fallback()
    if proxy_string:
        print(f"[INFO] Using proxy: {proxy_string.split('@')[-1] if '@' in proxy_string else proxy_string}")
    else:
        print("[INFO] No proxy available, running without proxy")

    # Initialize SeleniumBase with or without proxy
    sb_kwargs = {"uc": True, "headless": headless}
    if proxy_string:
        sb_kwargs["proxy"] = proxy_string

    with SB(**sb_kwargs) as sb:
        try:
            # ── Login bootstrap ───────────────────────────────────────────────
            print("[INFO] Opening Facebook...")
            sb.open("https://facebook.com")
            print("[INFO] Restoring session cookies...")
            for ck in load_cookies():
                try:
                    if hasattr(sb, 'driver') and sb.driver:
                        sb.driver.add_cookie(ck)
                except Exception:
                    pass
            sb.open(AD_LIBRARY_URL)
            sb.sleep(5)

        except Exception as e:
            error_msg = str(e)
            if "ERR_NAME_NOT_RESOLVED" in error_msg:
                print(f"[ERROR] DNS resolution failed - cannot reach Facebook through proxy")
                print(f"[ERROR] This might be caused by:")
                print(f"        - Proxy server DNS issues")
                print(f"        - Proxy server blocking Facebook")
                print(f"        - Network connectivity problems")
            else:
                print(f"[ERROR] Failed to initialize Facebook connection: {error_msg}")

            # Re-raise the exception to be handled by the calling function
            raise e

        # ── Country Selection (EXACT v2 logic) ────────────────────────────
        print(f"[INFO] Selecting country: {country}")

        # 1) Country dropdown
        wait_click(sb, '//div[div/div/text()="All" or div/div/text()="Country"]/..', by="xpath")
        safe_type(sb, '//input[@placeholder="Search for country"]', country, by="xpath")

        # More robust country selection with multiple fallback selectors
        country_selectors = [
            f'//div[contains(@id,"js_") and text()="{country}"]',
            f'//div[contains(@id,"js_") and contains(text(),"{country}")]',
            f'//div[text()="{country}"]',
            f'//div[contains(text(),"{country}")]',
            f'//span[text()="{country}"]',
            f'//span[contains(text(),"{country}")]',
            f'//*[text()="{country}"]'
        ]

        country_clicked = False
        for selector in country_selectors:
            try:
                sb.wait_for_element_visible(selector, by="xpath", timeout=5)
                sb.click(selector, by="xpath")
                country_clicked = True
                print(f"[SUCCESS] Selected country using selector: {selector}")
                break
            except Exception as e:
                print(f"[DEBUG] Country selector failed: {selector} - {str(e)}")
                continue

        if not country_clicked:
            print(f"[ERROR] Could not find country '{country}' with any selector")
            # Try to get available options for debugging
            try:
                available_options = sb.find_elements('//div[contains(@id,"js_")]', by="xpath")
                print(f"[DEBUG] Available options: {[opt.text for opt in available_options[:10]]}")
            except:
                pass
            raise Exception(f"Could not select country: {country}")

        sb.sleep(2)

        # 2) Ad category → All ads
        wait_click(sb, '//div[div/div/text()="Ad category"]/..', by="xpath")
        wait_click(sb, '//span[text()="All ads"]/../../..', by="xpath")
        sb.sleep(2)

        # ── Extract Suggestions ───────────────────────────────────────────
        suggestions = extract_suggestions(sb, keyword)
        print(f"[INFO] Found {len(suggestions)} suggestions for keyword: {keyword}")

    # ── Scrape Advertiser Ads (if requested) ─────────────────────────
    ads = []
    if scrape_ads:
        print(f"[INFO] Starting advertiser ads scraping for {len(suggestions)} suggestions...")

        # Start a new browser session for advertiser ads scraping
        with SB(uc=True, headless=headless) as sb:
            # Login bootstrap again
            print("[INFO] Opening Facebook for advertiser ads scraping...")
            sb.open("https://facebook.com")
            print("[INFO] Restoring session cookies...")
            for ck in load_cookies():
                try:
                    if hasattr(sb, 'driver') and sb.driver:
                        sb.driver.add_cookie(ck)
                except Exception:
                    pass
            sb.open(AD_LIBRARY_URL)
            sb.sleep(5)

            # Iterate through suggestions and scrape ads from each advertiser
            for idx, suggestion in enumerate(suggestions, 1):
                page_id = _extract_page_id_from_suggestion(suggestion)
                if page_id:
                    try:
                        advertiser_name = suggestion.get("name", "Unknown")
                        print(f"[INFO] ({idx}/{len(suggestions)}) Scraping ads from advertiser: {advertiser_name}")

                        # Extract ads from this advertiser with specific limit
                        ads_from_advertiser = extract_advertiser_ads(
                            sb, country, page_id, advertiser_name, limit=advertiser_ads_limit
                        )

                        # Add advertiser ads to the main ads list
                        ads.extend(ads_from_advertiser)

                        print(f"[INFO] Collected {len(ads_from_advertiser)} ads from {advertiser_name}. Total: {len(ads)}")

                        # Small delay between advertiser pages
                        sb.sleep(2)

                    except Exception as e:
                        print(f"[ERROR] Failed to scrape ads from advertiser {suggestion.get('name', 'Unknown')}: {e}")
                        continue
                else:
                    print(f"[INFO] Skipping suggestion '{suggestion.get('name', 'Unknown')}' - no valid page ID")

            print(f"[INFO] Completed advertiser ads scraping. Total ads collected: {len(ads)}")

    # ── Build nested result object ────────────────────────────────────
    # Create nested structure: each suggestion with its ads
    nested_suggestions = []

    if scrape_ads:
        # Group ads by advertiser and create nested structure
        for suggestion in suggestions:
            suggestion_copy = suggestion.copy()
            page_id = _extract_page_id_from_suggestion(suggestion)
            advertiser_name = suggestion.get("name", "Unknown")

            # Find ads for this specific advertiser
            advertiser_ads = [ad for ad in ads if ad.get("scraped_from_advertiser") == advertiser_name]

            # Add ads to the suggestion
            suggestion_copy["ads"] = advertiser_ads
            suggestion_copy["ads_count"] = len(advertiser_ads)

            nested_suggestions.append(suggestion_copy)
    else:
        # If not scraping ads, just add empty ads array to each suggestion
        for suggestion in suggestions:
            suggestion_copy = suggestion.copy()
            suggestion_copy["ads"] = []
            suggestion_copy["ads_count"] = 0
            nested_suggestions.append(suggestion_copy)

    result = {
        "country": country,
        "keyword": keyword,
        "suggestions": nested_suggestions,
        "timestamp": datetime.now().isoformat(),
        "scrape_advertiser_ads": scrape_ads,
        "total_suggestions": len(nested_suggestions),
        "total_ads": len(ads) if scrape_ads else 0
    }

    # ── Save data immediately to Results directory ─────────────────────
    save_data_to_results(result)

    print(f"[INFO] Completed scraping for {country} | {keyword}")
    print(f"[INFO] Results: {len(nested_suggestions)} suggestions, {len(ads) if scrape_ads else 0} ads")

    return result


class SuggestionsScraperAPI:
    """API wrapper class for suggestions scraping functionality."""

    def __init__(self):
        self.output_dir = OUTPUT_DIR

    async def scrape_suggestions(self, target_pairs: List[List[str]],
                               scrape_advertiser_ads: bool = False,
                               headless: bool = True,
                               advertiser_ads_limit: int = 100) -> Dict[str, Any]:
        """
        Async wrapper for suggestions scraping.

        Args:
            target_pairs: List of [country, keyword] pairs
            scrape_advertiser_ads: Whether to also scrape ads from each advertiser found
            headless: Whether to run in headless mode
            advertiser_ads_limit: Maximum number of ads to extract per advertiser page

        Returns:
            Dictionary with suggestions and optionally ads data
        """
        # Run the synchronous scraper in a thread pool
        loop = asyncio.get_event_loop()

        all_results = []

        for country, keyword in target_pairs:
            # Use run_in_executor to run the sync function in a thread
            result = await loop.run_in_executor(
                None,
                scrape_suggestions_sync,
                country,
                keyword,
                scrape_advertiser_ads,
                advertiser_ads_limit,
                headless
            )
            all_results.append(result)

        # Combine all results
        combined_result = {
            "results": all_results,
            "total_pairs": len(target_pairs),
            "timestamp": datetime.now().isoformat(),
        }

        return combined_result

    def save_separate_files(self, result: Dict[str, Any]) -> Dict[str, str]:
        """
        Save different data types to separate files.

        Args:
            result: The scraping result dictionary

        Returns:
            Dictionary with file paths for each data type
        """
        files_saved = {}
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save full results
        suggestions_file = self.output_dir / f"suggestions_{timestamp}.json"
        suggestions_file.write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        files_saved["suggestions"] = str(suggestions_file)

        # Extract and save individual data types
        all_suggestions = []
        all_pages = []
        all_ads = []

        for pair_result in result.get("results", []):
            # Collect suggestions
            suggestions = pair_result.get("suggestions", [])
            all_suggestions.extend(suggestions)

            # Extract pages data from suggestions
            for suggestion in suggestions:
                page_data = {
                    "page_id": suggestion.get("page_id", ""),
                    "name": suggestion.get("name", ""),
                    "raw_text": suggestion.get("raw_text", ""),
                    "country": pair_result.get("country", ""),
                    "keyword": pair_result.get("keyword", ""),
                    "timestamp": pair_result.get("timestamp", ""),
                }
                all_pages.append(page_data)

            # Collect ads if any
            ads = pair_result.get("ads", [])
            all_ads.extend(ads)

        # Save pages data
        if all_pages:
            pages_file = self.output_dir / f"pages_{timestamp}.json"
            pages_file.write_text(
                json.dumps(all_pages, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
            files_saved["pages"] = str(pages_file)

        # Save ads data
        if all_ads:
            ads_file = self.output_dir / f"ads_{timestamp}.json"
            ads_file.write_text(
                json.dumps(all_ads, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
            files_saved["ads"] = str(ads_file)

            # Save advertiser ads data separately
            advertiser_ads = [ad for ad in all_ads if ad.get("advertiser_context", {}).get("scraped_from") == "advertiser_page"]
            if advertiser_ads:
                advertiser_ads_file = self.output_dir / f"advertiser_ads_{timestamp}.json"
                advertiser_ads_file.write_text(
                    json.dumps(advertiser_ads, indent=2, ensure_ascii=False),
                    encoding="utf-8"
                )
                files_saved["advertiser_ads"] = str(advertiser_ads_file)

        return files_saved

def scrape_suggestions_with_ads_sync(country: str, keyword: str, max_scrolls: int = 10, headless: bool = True) -> dict:
    """
    Unified scraping function that gets suggestions and ads for each advertiser.

    Args:
        country: Country to scrape from
        keyword: Keyword to search for
        max_scrolls: Maximum number of scrolls when scraping advertiser ads
        headless: Whether to run in headless mode

    Returns:
        Dictionary with suggestions and ads data in nested structure
    """
    print(f"[INFO] Starting unified scraping for: {country} | {keyword}")

    with SB(uc=True, headless=headless) as sb:
        # ── Login bootstrap ───────────────────────────────────────────────
        print("[INFO] Opening Facebook...")
        sb.open("https://facebook.com")
        print("[INFO] Restoring session cookies...")
        for ck in load_cookies():
            try:
                sb.driver.add_cookie(ck)
            except Exception:
                pass
        sb.open(AD_LIBRARY_URL)
        sb.sleep(5)

        # ── Country Selection ─────────────────────────────────────────────
        print(f"[INFO] Selecting country: {country}")

        # Country dropdown
        wait_click(sb, '//div[div/div/text()="All" or div/div/text()="Country"]/..', by="xpath")
        safe_type(sb, '//input[@placeholder="Search for country"]', country, by="xpath")

        # Country selection with fallback selectors
        country_selectors = [
            f'//div[contains(@id,"js_") and text()="{country}"]',
            f'//div[contains(@id,"js_") and contains(text(),"{country}")]',
            f'//div[text()="{country}"]',
            f'//div[contains(text(),"{country}")]',
            f'//span[text()="{country}"]',
            f'//span[contains(text(),"{country}")]',
            f'//*[text()="{country}"]'
        ]

        country_clicked = False
        for selector in country_selectors:
            try:
                sb.wait_for_element_visible(selector, by="xpath", timeout=5)
                sb.click(selector, by="xpath")
                country_clicked = True
                print(f"[SUCCESS] Selected country using selector: {selector}")
                break
            except Exception as e:
                print(f"[DEBUG] Country selector failed: {selector} - {str(e)}")
                continue

        if not country_clicked:
            print(f"[ERROR] Could not find country '{country}' with any selector")
            raise Exception(f"Could not select country: {country}")

        sb.sleep(2)

        # Ad category → All ads
        wait_click(sb, '//div[div/div/text()="Ad category"]/..', by="xpath")
        wait_click(sb, '//span[text()="All ads"]/../../..', by="xpath")
        sb.sleep(2)

        # ── Extract Suggestions ───────────────────────────────────────────
        suggestions = extract_suggestions(sb, keyword)
        print(f"[INFO] Found {len(suggestions)} suggestions for keyword: {keyword}")

        # ── Scrape Ads for Each Advertiser ───────────────────────────────
        nested_suggestions = []

        for idx, suggestion in enumerate(suggestions, 1):
            advertiser_name = suggestion.get("name", "").strip()
            if not advertiser_name:
                continue

            print(f"[INFO] ({idx}/{len(suggestions)}) Scraping ads for: {advertiser_name}")

            try:
                # Extract page_id from suggestion
                page_id = _extract_page_id_from_suggestion(suggestion)

                if page_id:
                    # Build URL for this advertiser's ads
                    advertiser_url = _build_advertiser_url(country, page_id)

                    # Navigate to advertiser's ads page
                    sb.open(advertiser_url)
                    sb.sleep(4)

                    # Scroll to load ads
                    for i in range(3):
                        human_scroll(sb)
                        sb.sleep(2 + i * 0.5)

                    # Extract ads from the page
                    ads = extract_ads(sb, limit=100)  # Default limit since we use scroll-based approach

                    # Filter ads to only include those from this specific advertiser
                    filtered_ads = [ad for ad in ads if _match_page(ad.get("page"), advertiser_name)]

                    print(f"[INFO] Found {len(filtered_ads)} ads for {advertiser_name}")

                    # Build nested structure
                    advertiser_data = {
                        "advertiser": {
                            "name": advertiser_name,
                            "page_id": page_id,
                            "description": suggestion.get("description", ""),
                            "raw_text": suggestion.get("raw_text", ""),
                            "ads": filtered_ads
                        }
                    }

                    nested_suggestions.append(advertiser_data)

                else:
                    print(f"[WARNING] No valid page_id found for {advertiser_name}")
                    # Still add the advertiser without ads
                    advertiser_data = {
                        "advertiser": {
                            "name": advertiser_name,
                            "page_id": "",
                            "description": suggestion.get("description", ""),
                            "raw_text": suggestion.get("raw_text", ""),
                            "ads": []
                        }
                    }
                    nested_suggestions.append(advertiser_data)

            except Exception as e:
                print(f"[ERROR] Failed to scrape ads for {advertiser_name}: {str(e)}")
                # Still add the advertiser without ads
                advertiser_data = {
                    "advertiser": {
                        "name": advertiser_name,
                        "page_id": suggestion.get("page_id", ""),
                        "description": suggestion.get("description", ""),
                        "raw_text": suggestion.get("raw_text", ""),
                        "ads": []
                    }
                }
                nested_suggestions.append(advertiser_data)

        # ── Build Final Result ────────────────────────────────────────────
        result = {
            "keyword": keyword,
            "country": country,
            "timestamp": datetime.now().isoformat(),
            "suggestions": nested_suggestions
        }

        print(f"[INFO] Completed unified scraping for {country} | {keyword}")
        print(f"[INFO] Results: {len(nested_suggestions)} advertisers with ads")

        return result

def _match_page(page: str | None, target: str) -> bool:
    """Case-insensitive, unicode-normalised equality test."""
    if not page:
        return False
    import unicodedata
    return unicodedata.normalize("NFKD", page).casefold() == \
           unicodedata.normalize("NFKD", target).casefold()

def human_scroll(sb: SB, px: int = 1800):
    """Human-like scrolling"""
    sb.execute_script(f"window.scrollBy(0,{px});")

def extract_ads(sb, limit: int | None = None) -> list[dict[str, Any]]:
    """
    Month-aware scrolling scraper.
    • Scrolls page-bottom-wards until no new cards appear (or `limit` reached).
    • After each scroll it *immediately* parses only the newly discovered cards,
      so you never re-parse what you already have.
    """
    ads: list[dict[str, Any]] = []
    seen_cards = 0            # how many cards we have already parsed
    dead_scrolls = 0          # consecutive scrolls that yielded 0 new cards
    MAX_DEAD = 2              # stop after this many idle scrolls

    # nudge page so FB injects first batch
    sb.execute_script("window.scrollBy(0,600);")
    time.sleep(1)

    print("[INFO] Month-aware scraping starts…")

    while True:
        # ── 1. find every month strip currently present
        prefixes = _discover_month_prefixes(sb)

        # ── 2. compute *total* cards now in DOM
        total_now = sum(_count_cards_in_prefix(p, sb) for p in prefixes)

        if total_now > seen_cards:
            # Parse only the *new* tail in each strip
            print(f"[INFO] New cards detected: {total_now-seen_cards} (total {total_now})")
            parsed_this_round = 0
            cumulative = 0    # running count across prefixes (newest → oldest)

            for prefix in prefixes:
                n_cards = _count_cards_in_prefix(prefix, sb)
                # how many of those have we already parsed inside this strip?
                already = max(0, seen_cards - cumulative)
                cumulative += n_cards

                for idx in range(already + 1, n_cards + 1):
                    if limit and len(ads) >= limit:
                        print(f"[INFO] Hit ads limit {limit}.")
                        return ads
                    try:
                        card = sb.driver.find_element("xpath", f"{prefix}/div[{idx}]/div")
                        ads.append(_parse_card(card))
                        # print(f" ads data {ads[-1]}")
                        parsed_this_round += 1
                    except Exception as e:
                        print(f"[WARN] failed to parse card {idx} in {prefix}: {e}")

            seen_cards = total_now
            dead_scrolls = 0
            print(f"[INFO] Parsed {parsed_this_round} new ads (running total {len(ads)}).")

        else:
            dead_scrolls += 1
            if dead_scrolls >= MAX_DEAD:
                print("[INFO] No new cards after several scrolls – finishing.")
                return ads

        # ── 3. scroll one viewport further
        sb.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1.2)

def _discover_month_prefixes(sb) -> list[str]:
    """
    Return *all* month-strip prefixes currently in the DOM.
    Order: newest first, then older and older…  (Good for parsing tail-first.)
    """
    prefixes: list[str] = []
    m = 2                                      # first month = div[2]
    while True:
        month_base = f"{MONTH_BASE}/div[{m}]"
        found = None

        # latest month => /div[4]/div[1]   |   older months => /div[3]/div[1]
        for inner in (4, 3):
            prefix = f"{month_base}/div[{inner}]/div[1]"
            try:
                sb.driver.find_element("xpath", f"{prefix}/div[1]/div")
                found = prefix
                break
            except NoSuchElementException:
                continue

        if not found:                         # no more month sections
            break

        prefixes.append(found)
        m += 1

    return prefixes


def _count_cards_in_prefix(prefix: str, sb, gap: int = GAP_LIMIT) -> int:
    """Count cards in one strip, tolerant of ≤ gap missing indices."""
    total = misses = idx = 0
    while misses < gap:
        idx += 1
        try:
            sb.driver.find_element("xpath", f"{prefix}/div[{idx}]/div")
            total += 1
            misses = 0
        except NoSuchElementException:
            misses += 1
    return total


def _parse_card(card) -> Dict[str, Any]:
    """
    Parse a single Ad-Library card with enhanced link extraction.
    """
    import re
    from urllib.parse import urlparse

    def _maybe_click(xp: str):
        try:
            card.find_element("xpath", xp).click()
        except NoSuchElementException:
            pass

    def _t(xp: str) -> str | None:
        try:
            return card.find_element("xpath", xp).text.strip()
        except NoSuchElementException:
            return None

    # ── 1. Expand (headless-safe) ───────────────────────────────────────
    _maybe_click('.//div[@role="button" and .="Open Drop-down"]')

    # ── 2. Meta fields ─────────────────────────────────────────────────
    status       = _t('.//span[contains(text(),"Active") or contains(text(),"Inactive")]')
    lib_raw      = _t('.//span[contains(text(),"Library ID")]')
    library_id   = lib_raw.split(":",1)[-1].strip() if lib_raw else None
    started_raw  = _t('.//span[contains(text(),"Started running")]')
    page_name    = _t('.//a[starts-with(@href,"https://www.facebook.com/")][1]')

    # ── 3. Raw creative block text ────────────────────────────────────
    raw_block = card.text.strip()
    # print(f"[DEBUG] Raw block text: {raw_block}")
    #   PRIMARY TEXT extraction
    primary_text = ""
    if "Sponsored" in raw_block:
        after = raw_block.split("Sponsored", 1)[1].lstrip()
        lines = []
        for ln in after.splitlines():
            if re.match(r"https?://|^[A-Z0-9._%+-]+\.[A-Z]{2,}$", ln, flags=re.I):
                break
            if re.match(r"^\w.*\b(Shop|Learn|Contact|Apply|Sign)\b", ln) and len(ln) < 40:
                break
            lines.append(ln.rstrip())
        primary_text = "\n".join(lines).strip()

    # ── 4. CTA detection ───────────────────────────────────────────────
    CTA_PHRASES = (
        "\nLearn More", "\nLearn more", "\nShop Now", "\nShop now", "\nBook Now",
        "\nBook now", "\nDonate", "\nDonate now", "\nApply Now", "\nApply now",
        "\nGet offer", "\nGet Offer", "\nGet quote", "\nSign Up", "\nSign up",
        "\nContact us", "\nSend message", "\nSend Message", "\nSubscribe", "\nRead more","\nSend WhatsApp message",
        "\nSend WhatsApp Message", "\nWatch video", "\nWatch Video",
    )

    # (a) DOM: any footer button/span whose text is in CTA_WORDS
    cta = None
    for phrase in CTA_PHRASES:
        label = _t(f'.//div[@role="button" and normalize-space(text())="{phrase}"]'
                   f' | .//span[normalize-space(text())="{phrase}"]')
        if label:
            cta = phrase
            break

    # (b) fallback: look for the first CTA_PHRASE inside raw_block
    if not cta:
        m = re.search(r"\b(" + "|".join(map(re.escape, CTA_PHRASES)) + r")\b", raw_block)
        cta = m.group(1) if m else None

    # ── 5. Enhanced Link Extraction ───────────────────────────────────
    facebook_domains = {"facebook.com", "fb.com", "facebookw.com", "fb.me", "fb.watch"}
    all_links = []
    image_urls = []

    # Extract all <a> tags and <img> tags
    for element in card.find_elements("xpath", ".//*[self::a or self::img]"):
        try:
            if element.tag_name == "a":
                href = element.get_attribute("href")
                if href:
                    parsed = urlparse(href)
                    if parsed.netloc.replace("www.", "") not in facebook_domains:
                        all_links.append({
                            "type": "link",
                            "url": href,
                            "text": element.text.strip() if element.text else ""
                        })

            elif element.tag_name == "img":
                for attr in ["src", "data-src", "xlink:href"]:
                    src = element.get_attribute(attr)
                    if src and src.startswith(("http:", "https:")):
                        image_urls.append(src)
                        break
        except StaleElementReferenceException:
            continue

    # ── 6. Build record ───────────────────────────────────────────────
    return {
        "status": status,
        "library_id": library_id,
        "started": started_raw,
        "page": page_name,
        "primary_text": primary_text,
        "cta": cta,
        "links": all_links,          # All non-Facebook links
        "image_urls": image_urls,     # All image URLs
        # "raw_text": raw_block,
    }
