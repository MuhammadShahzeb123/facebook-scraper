#!/usr/bin/env python3
# facebook_ads_suggestions_scraper.py
#
# REQUIREMENTS
#   pip install seleniumbase==4.* or latest
#   A file ./saved_cookies/facebook_cookies.txt  (exported with SeleniumBase or any FB cookie-grabber)
#
# USAGE
#   python facebook_ads_suggestions_scraper.py --keywords "rental properties" "apartments" --country "United States"
#
# (c) 2025 – adjust selectors if Facebook changes its markup.

import json
import argparse
import time
from pathlib import Path
from seleniumbase import SB
from selenium.common.exceptions import (NoSuchElementException,
                                        ElementNotInteractableException,
                                        StaleElementReferenceException)

##############################################################################
# 1) CLI arguments
##############################################################################
parser = argparse.ArgumentParser(description="Scrape Facebook Ad Library search suggestions")
parser.add_argument("--keywords", nargs='+', required=False, 
                    help="Ad Library keywords/phrases to get suggestions for")
parser.add_argument("--country", default="United States", help="Target country")
parser.add_argument("--debug", action="store_true", help="Enable debug mode with screenshots and HTML dumps")
args = parser.parse_args()

##############################################################################
# 1) Configurable Parameters (overridden by CLI args if provided)
##############################################################################
# Default keywords list if no CLI args provided
KEYWORDS = args.keywords if args.keywords else [
    "rental apartments", 
    "rental properties", 
    "real estate", 
    "vacation rentals", 
    "luxury apartments",
    "apartment for rent",
    "houses for rent",
    "condos for rent"
]
COUNTRY = args.country if args.country else "United States"
DEBUG = args.debug

##############################################################################
# 2) Helpers
##############################################################################
COOKIE_FILE = Path("./saved_cookies/facebook_cookies.txt")

def load_cookies():
    if not COOKIE_FILE.exists():
        raise FileNotFoundError(f"Cookie file not found: {COOKIE_FILE}")
    cookies = json.loads(COOKIE_FILE.read_text())
    for c in cookies:
        # SeleniumBase / Chromium requires exact strings
        if 'sameSite' in c and c['sameSite'].lower() not in {'strict', 'lax', 'none'}:
            c['sameSite'] = 'None'
    return cookies

def wait_click(sb, selector, by="css selector", timeout=10):
    """Generic wait-until-visible then click helper."""
    if by == "css":
        sb.wait_for_element_visible(selector, timeout=timeout)
        sb.click(selector)
    elif by == "xpath":
        sb.wait_for_element_visible(selector, by="xpath", timeout=timeout)
        sb.click(selector, by="xpath")

from selenium.webdriver.common.keys import Keys

def safe_type(sb, selector, text, by="css selector", press_enter=True, timeout=10):
    """Force-stable input into FB's JS-controlled search box."""
    sb.wait_for_element_visible(selector, by=by, timeout=timeout)
    element = sb.find_element(selector, by=by)
    element.clear()
    element.send_keys(text)
    time.sleep(1.0)  # let Facebook JS settle
    if press_enter:
        element.send_keys(Keys.RETURN)
        time.sleep(2.0)  # allow results to render

def extract_suggestions(sb, keyword, debug_dir=None):
    """
    Extract search suggestions that appear after entering a keyword
    """
    suggestions = []
    
    # Input keyword but don't press enter to see suggestions
    KEYWORD_INPUT = '//input[@type="search" and contains(@placeholder,"keyword") and not(@aria-disabled="true")]'
    safe_type(sb, KEYWORD_INPUT, keyword, by="xpath", press_enter=False)
    time.sleep(3)  # Wait longer for suggestions to appear
    
    # Save debug information if requested
    if debug_dir:
        sb.save_page_source(str(debug_dir / f"page_after_typing_{keyword.replace(' ', '_')}.html"))
        sb.save_screenshot(str(debug_dir / f"screenshot_after_typing_{keyword.replace(' ', '_')}.png"))
    
    try:
        # Primary container path from the user's example
        SUGGESTIONS_CONTAINER = '/html/body/div[1]/div/div/div/div/div/div/div[2]/div/div/div[1]/div[1]/div/div[1]/div/ul/div[4]/li'
        
        # Try to find the suggestions container
        if sb.is_element_visible(SUGGESTIONS_CONTAINER, by="xpath"):
            print("  > Found suggestions container using provided XPath")
            
            # We need to find the UL element containing all suggestions
            try:
                # First, try the exact path the user provided
                suggestion_list = sb.find_element(f"{SUGGESTIONS_CONTAINER}/ul", by="xpath")
                suggestion_items = suggestion_list.find_elements("xpath", "./div")
            except:
                # If that fails, try a more generalized approach to find all div containers within the li
                suggestion_items = sb.find_elements(f"{SUGGESTIONS_CONTAINER}//div[.//li[@role='option']]", by="xpath")
                
                if not suggestion_items:
                    # Fallback to a very general approach to find any option divs
                    suggestion_items = sb.find_elements("//li[@role='option']", by="xpath")
        else:
            # Fallback to a more general approach
            print("  > Using fallback selector for suggestions")
            suggestion_items = sb.find_elements("//li[@role='option']", by="xpath")
        
        print(f"  > Found {len(suggestion_items)} suggestion items")
        
        # If we still don't have suggestions, try one more approach
        if not suggestion_items:
            print("  > Trying alternative selectors")
            # Look for any li elements that might be suggestions
            suggestion_items = sb.find_elements("//li[contains(@class, 'xh8yej3')]", by="xpath")
            print(f"  > Found {len(suggestion_items)} items with alternative selector")
            
            # If still no results, try the specific container you provided
            if not suggestion_items:
                try:
                    # Try using the exact markup structure from the example
                    suggestion_items = sb.find_elements("//div/li[contains(@class, 'xh8yej3')]", by="xpath")
                    print(f"  > Found {len(suggestion_items)} items with exact selector from example")
                except:
                    pass
        
        # Process each suggestion item
        for item in suggestion_items:
            try:
                # We'll build a complete data structure for each suggestion
                suggestion_data = {}
                
                # Get the page ID directly from the li if possible
                try:
                    if item.tag_name.lower() == 'li':
                        page_id = item.get_attribute("id")
                    else:
                        li_element = item.find_element("xpath", ".//li")
                        page_id = li_element.get_attribute("id")
                    
                    if page_id and page_id.startswith("pageID:"):
                        suggestion_data["page_id"] = page_id.split("pageID:")[1]
                    else:
                        suggestion_data["page_id"] = page_id
                except:
                    suggestion_data["page_id"] = ""
                
                # Get the main text from the heading element if available
                try:
                    heading = item.find_element("xpath", ".//*[@role='heading']")
                    suggestion_data["name"] = heading.text.strip()
                except:
                    # If no heading, try to get the main text directly
                    text_parts = item.text.strip().split("\n")
                    suggestion_data["name"] = text_parts[0] if text_parts else ""
                
                # Get description/category 
                try:
                    # Look for smaller text elements that might contain descriptions
                    desc_elements = item.find_elements("xpath", ".//div[contains(@class, 'xw23nyj') or contains(@class, 'x63nzvj')]")
                    if desc_elements:
                        suggestion_data["description"] = desc_elements[0].text.strip()
                    else:
                        # Try to extract from secondary text lines
                        text_parts = item.text.strip().split("\n")
                        if len(text_parts) > 1:
                            suggestion_data["description"] = text_parts[1] if len(text_parts) > 1 else ""
                        else:
                            suggestion_data["description"] = ""
                except:
                    suggestion_data["description"] = ""
                
                # Get image URL if available
                try:
                    img = item.find_element("xpath", ".//img")
                    suggestion_data["image_url"] = img.get_attribute("src")
                except:
                    suggestion_data["image_url"] = ""
                
                # Extract any available follow count
                try:
                    follow_text = ""
                    if suggestion_data["description"] and "follow" in suggestion_data["description"].lower():
                        follow_parts = suggestion_data["description"].split("·")
                        for part in follow_parts:
                            if "follow" in part.lower():
                                follow_text = part.strip()
                                break
                    suggestion_data["follow_count"] = follow_text
                except:
                    suggestion_data["follow_count"] = ""
                
                # Extract any other useful data
                try:
                    # Check for category type (like "Real Estate", "Business", etc.)
                    text_parts = item.text.strip().split("\n")
                    category = ""
                    for part in text_parts:
                        if "·" in part:
                            categories = part.split("·")
                            if len(categories) > 1:
                                category = categories[-1].strip()
                                break
                    suggestion_data["category"] = category
                except:
                    suggestion_data["category"] = ""
                
                # Save HTML of the element for debugging
                if debug_dir:
                    item_html = item.get_attribute("outerHTML")
                    suggestion_data["html"] = item_html
                
                # Store all raw text for debugging
                suggestion_data["raw_text"] = item.text.strip()
                
                # Only add non-empty suggestions
                if suggestion_data["name"] or suggestion_data["description"]:
                    suggestions.append(suggestion_data)
            except Exception as e:
                print(f"  > Error extracting suggestion: {str(e)}")
                continue
    
    except Exception as e:
        print(f"  > Error finding suggestions container: {str(e)}")
        # Save page source for debugging
        if debug_dir:
            sb.save_page_source(str(debug_dir / f"error_page_{keyword.replace(' ', '_')}.html"))
            sb.save_screenshot(str(debug_dir / f"error_screenshot_{keyword.replace(' ', '_')}.png"))
    
    # Clear the input to reset for next keyword
    sb.find_element(KEYWORD_INPUT, by="xpath").clear()
    
    return suggestions

##############################################################################
# 3) Main browser session
##############################################################################
with SB(uc=True, headless=False) as sb:
    print("[INFO] Opening Facebook …")
    sb.open("https://facebook.com")

    # ── Inject cookies ──────────────────────────────────────────────────────
    print("[INFO] Restoring session cookies …")
    for cookie in load_cookies():
        try:
            sb.driver.add_cookie(cookie)
        except Exception as e:
            # Ignore non-essential cookies ( e.g. SameSite / domain mismatch )
            print(f"  > could not add cookie {cookie.get('name')}: {e}")

    sb.refresh()
    sb.sleep(2)

    # ── Search for "Facebook Ad Library" from the FB top search bar ─────────
    print("[INFO] Navigating to Facebook Ad Library …")
    SEARCHBAR = 'input[placeholder*="Search"]'

    safe_type(sb, SEARCHBAR, "Facebook Ad Library", press_enter=True)
    sb.sleep(3)                       # page populates results
    # click the first visible result that contains the phrase
    sb.click('//span[contains(text(),"Ad Library")]', by="xpath", timeout=10)

    sb.sleep(5)                       # wait for redirect

    # Ad Library now loaded inside a FB shell ( domain may be "facebook.com/ads/library" )
    print("[INFO] Setting country …")
    # 1. open country chooser
    COUNTRY_CHOOSER = '//div[div/div/text()="Pakistan" or div/div/text()="Country"]/..'
    wait_click(sb, COUNTRY_CHOOSER, by="xpath")
    # 2. type desired country
    COUNTRY_INPUT   = '//input[@placeholder="Search for country"]'
    safe_type(sb, COUNTRY_INPUT, COUNTRY, by="xpath")
    sb.sleep(1)
    # 3. click suggestion exact match
    COUNTRY_OPTION  = f'//div[contains(@id,"js_") and text()="{COUNTRY}"]'
    wait_click(sb, COUNTRY_OPTION, by="xpath")
    sb.sleep(2)

    print("[INFO] Selecting Ad category = All ads …")
    # 1. open category chooser
    CAT_CHOOSER = '//div[div/div/text()="Ad category"]/..'
    wait_click(sb, CAT_CHOOSER, by="xpath")
    # 2. click "All ads"
    ALL_ADS_OPTION = '//span[text()="All ads"]/../../..'   # walks up to clickable radio wrapper
    wait_click(sb, ALL_ADS_OPTION, by="xpath")
    sb.sleep(2)

    # Create debug directory if needed
    debug_dir = None
    if DEBUG:
        debug_dir = Path("./debug_suggestions")
        debug_dir.mkdir(exist_ok=True)
        # Take a screenshot of the initial state
        sb.save_screenshot(str(debug_dir / "initial_state.png"))
        sb.save_page_source(str(debug_dir / "initial_state.html"))

    # ── Get search suggestions for each keyword ─────────────────────────────
    all_results = []
    
    for keyword in KEYWORDS:
        print(f"[INFO] Getting suggestions for keyword: '{keyword}'")
        
        # First attempt to get suggestions
        keyword_suggestions = extract_suggestions(sb, keyword, debug_dir)
        
        # If no suggestions found, try again with a different approach
        if not keyword_suggestions and DEBUG:
            print("  > No suggestions found, trying again with a different approach")
            
            # Try again with a different timing
            safe_type(sb, KEYWORD_INPUT, keyword, by="xpath", press_enter=False)
            time.sleep(5)  # Wait longer
            
            # Try a more generic approach - look for any dropdown items
            try:
                # Look for any dropdown/suggestion items on the page
                all_options = sb.find_elements("//li[contains(@class, 'xh8yej3')]", by="xpath")
                print(f"  > Found {len(all_options)} potential suggestion elements in retry")
                
                fallback_suggestions = []
                for opt in all_options:
                    try:
                        suggestion_data = {
                            "name": opt.text.strip().split("\n")[0] if opt.text else "",
                            "raw_text": opt.text.strip(),
                            "page_id": opt.get_attribute("id") or "",
                            "image_url": "",
                            "description": "",
                            "follow_count": "",
                            "category": "",
                            "html": opt.get_attribute("outerHTML") if DEBUG else ""
                        }
                        if suggestion_data["name"]:
                            fallback_suggestions.append(suggestion_data)
                    except Exception as e:
                        print(f"  > Error in fallback extraction: {e}")
                
                if fallback_suggestions:
                    keyword_suggestions = fallback_suggestions
                    print(f"  > Recovered {len(fallback_suggestions)} suggestions with fallback method")
            except Exception as e:
                print(f"  > Error in fallback extraction: {e}")
                
            # If still no suggestions, save debug info
            if not keyword_suggestions and debug_dir:
                sb.save_page_source(str(debug_dir / f"no_results_{keyword.replace(' ', '_')}.html"))
                sb.save_screenshot(str(debug_dir / f"no_results_{keyword.replace(' ', '_')}.png"))
        
        # Format the result in the desired structure
        result = {
            "region": COUNTRY,
            "keyword": keyword,
            "recommendations": keyword_suggestions
        }
        
        all_results.append(result)
        print(f"  > Found {len(keyword_suggestions)} suggestions for '{keyword}'")
        time.sleep(2)  # Slightly longer pause between keywords
    
    # ── Persist ───────────────────────────────────────────────────────────
    out_name = f"ad_suggestions_{'-'.join([k.replace(' ', '_') for k in KEYWORDS])}.json"
    Path(out_name).write_text(
        json.dumps(all_results, indent=2, ensure_ascii=False),
        encoding="utf-8"          # always write UTF-8 on Windows
    )
    print(f"[INFO] Saved suggestions to {out_name}")
    
    # Print sample of suggestions for first keyword
    if all_results:
        first_result = all_results[0]
        sample_recommendations = first_result["recommendations"][:2] if len(first_result["recommendations"]) > 2 else first_result["recommendations"]
        sample_output = {
            "region": first_result["region"],
            "keyword": first_result["keyword"],
            "recommendations": sample_recommendations
        }
        print("Sample output ↓")
        print(json.dumps(sample_output, indent=2, ensure_ascii=False))
