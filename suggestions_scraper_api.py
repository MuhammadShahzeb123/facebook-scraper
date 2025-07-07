#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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

def scrape_suggestions_sync(country: str, keyword: str, scrape_ads: bool = False,
                           max_scrolls: int = 10, headless: bool = True) -> dict:
    """
    Main suggestions scraping function - exact v2 logic.

    Args:
        country: Country to scrape from
        keyword: Keyword to search for
        scrape_ads: Whether to also scrape ads from each advertiser found
        max_scrolls: Maximum number of scrolls when scraping advertiser ads
        headless: Whether to run in headless mode

    Returns:
        Dictionary with suggestions and optionally ads data
    """
    print(f"[INFO] Starting suggestions scraping for: {country} | {keyword}")

    with SB(uc=True, headless=headless) as sb:
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

    # Browser session is now closed, safe to run subprocess
    
    # ── Scrape Advertiser Ads (if requested) ──────────────────────────
    ads = []
    if scrape_ads:
        print(f"[INFO] Starting advertiser ads scraping for {len(suggestions)} suggestions...")
        print(f"[INFO] Browser session closed, starting subprocess...")

        # Use the main scraper with suggestions_with_ads mode
        import subprocess
        import os
        import glob

        # Set environment variables for the main scraper
        env = os.environ.copy()
        env.update({
            "MODE": "suggestions_with_ads",
            "HEADLESS": "true",
            "MAX_SCROLLS": str(max_scrolls),
            "TARGET_PAIRS": json.dumps([[country, keyword]]),
            "APPEND": "false"
        })

        try:
            # Run the main scraper
            print(f"[INFO] Running: python ads_and_suggestions_scraper.py")
            result = subprocess.run(
                ["python", "ads_and_suggestions_scraper.py"],
                env=env,
                capture_output=True,
                text=True,
                timeout=1800  # 30 minutes timeout
            )

            print(f"[INFO] Subprocess completed with return code: {result.returncode}")
            
            if result.returncode == 0:
                print(f"[INFO] Successfully ran main scraper for suggestions_with_ads mode")
                print(f"[INFO] Subprocess stdout: {result.stdout[-500:]}")  # Last 500 chars

                # Read the results from the output file
                result_files = glob.glob("Results/suggestions_with_ads*.json")
                print(f"[INFO] Found result files: {result_files}")
                
                if result_files:
                    # Get the most recent file
                    latest_file = max(result_files, key=os.path.getctime)
                    print(f"[INFO] Reading results from: {latest_file}")
                    
                    with open(latest_file, 'r', encoding='utf-8') as f:
                        scraper_results = json.load(f)

                    if scraper_results and len(scraper_results) > 0:
                        # Extract the nested structure from the latest result
                        latest_result = scraper_results[-1]
                        if "suggestions" in latest_result:
                            print(f"[INFO] Returning structured result with {len(latest_result['suggestions'])} suggestions")
                            return latest_result  # Return the properly structured result
                else:
                    print(f"[WARNING] No result files found in Results/ directory")
            else:
                print(f"[ERROR] Main scraper failed with return code: {result.returncode}")
                print(f"[ERROR] Stderr: {result.stderr}")
                print(f"[ERROR] Stdout: {result.stdout}")

        except subprocess.TimeoutExpired:
            print(f"[ERROR] Main scraper timed out after 30 minutes")
        except Exception as e:
            print(f"[ERROR] Failed to run main scraper: {e}")

        # ── Build Result (fallback for suggestions only) ──────────────────────────────────────────────
        result = {
            "country": country,
            "keyword": keyword,
            "suggestions": suggestions,
            "scrape_ads": scrape_ads,
            "max_scrolls": max_scrolls,
            "timestamp": datetime.now().isoformat(),
        }

        if scrape_ads:
            result["ads"] = ads

        print(f"[INFO] Completed scraping for {country} | {keyword}")
        print(f"[INFO] Results: {len(suggestions)} suggestions, {len(ads)} ads")

        return result

class SuggestionsScraperAPI:
    """API wrapper class for suggestions scraping functionality."""

    def __init__(self):
        self.output_dir = OUTPUT_DIR

    async def scrape_suggestions(self, target_pairs: List[List[str]],
                               scrape_advertiser_ads: bool = False,
                               headless: bool = True,
                               max_scrolls: int = 10) -> Dict[str, Any]:
        """
        Async wrapper for suggestions scraping.

        Args:
            target_pairs: List of [country, keyword] pairs
            scrape_advertiser_ads: Whether to also scrape ads from each advertiser found
            headless: Whether to run in headless mode
            max_scrolls: Maximum number of scrolls when scraping advertiser ads

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
                max_scrolls,
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

def extract_ads(sb: SB, limit: int = 1000) -> list[dict]:
    """Extract ads from the current page - simplified version"""
    ads = []

    # Make sure page is loaded
    sb.execute_script("window.scrollBy(0, 800);")
    time.sleep(1)

    # Try to find ad cards
    common_head = "/html/body/div[1]/div/div/div/div/div/div/div[1]/div/div/div"

    # Try different possible prefixes
    for row in (5, 4):
        prefix = f"{common_head}/div[{row}]/div[2]/div[2]/div[4]/div[1]"
        try:
            sb.driver.find_element("xpath", f"{prefix}/div[1]/div")
            break
        except:
            continue
    else:
        print("[WARNING] Could not find ad cards prefix")
        return ads

    # Extract ads
    try:
        sb.wait_for_element_visible(f"{prefix}/div[1]/div", by="xpath", timeout=15)
    except:
        print("[WARNING] No ads found on page")
        return ads

    n = 1
    while True:
        if limit and len(ads) >= limit:
            break

        xpath = f"{prefix}/div[{n}]/div"
        try:
            card_ele = sb.driver.find_element("xpath", xpath)

            # Parse the card - simplified version
            try:
                ad_data = {
                    "library_id": "",
                    "page": "",
                    "primary_text": "",
                    "status": "active",
                    "started": "",
                    "raw_text": card_ele.text.strip()
                }

                # Try to extract basic info
                try:
                    page_element = card_ele.find_element("xpath", './/a[starts-with(@href,"https://www.facebook.com/")]')
                    ad_data["page"] = page_element.text.strip()
                except:
                    pass

                # Try to extract library ID
                try:
                    lib_element = card_ele.find_element("xpath", './/span[contains(text(),"Library ID")]')
                    lib_text = lib_element.text.strip()
                    if ":" in lib_text:
                        ad_data["library_id"] = lib_text.split(":", 1)[1].strip()
                except:
                    pass

                # Try to extract primary text
                try:
                    text_elements = card_ele.find_elements("xpath", './/div[contains(@class,"")]')
                    for elem in text_elements:
                        text = elem.text.strip()
                        if len(text) > 20 and not text.startswith("Library ID"):
                            ad_data["primary_text"] = text[:200] + "..." if len(text) > 200 else text
                            break
                except:
                    pass

                ads.append(ad_data)

            except Exception as e:
                print(f"[DEBUG] Failed to parse ad card: {str(e)}")
                pass

        except:
            break

        n += 1

    print(f"[INFO] Extracted {len(ads)} ads from current page")
    return ads

# Example usage
if __name__ == "__main__":
    # Test the scraper
    result = scrape_suggestions_sync(
        country="Thailand",
        keyword="properties",
        scrape_ads=False,
        headless=False
    )

    print(f"Results: {len(result['suggestions'])} suggestions")
