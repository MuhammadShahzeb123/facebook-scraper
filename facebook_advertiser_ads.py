#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# facebook_ads_scraper.py  –  v2.3  (2025-06-18)

#  ▄───────────────────────────────────────────────────────────────────▄
#  │  NEW IN 2.3                                                      │
#  │    • Enhanced card parsing with link/image extraction            │
#  │    • Robust ad detection using XPath prefixes                    │
#  │    • Comprehensive non-Facebook link collection                  │
#  ▀───────────────────────────────────────────────────────────────────▀

import json, time, csv, re, os, argparse, sys
from pathlib import Path
from urllib.parse import urlparse
from collections import defaultdict
from seleniumbase import SB #type: ignore
from proxy_utils_enhanced import get_proxy_string_with_fallback  # Import enhanced proxy utility

# Set up proper encoding for Windows console output
if os.name == "nt":
    # Set environment variable for UTF-8 encoding
    os.environ['PYTHONIOENCODING'] = 'utf-8'

    try:
        # For Python 3.7+
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding="utf-8", errors='replace')
            sys.stderr.reconfigure(encoding="utf-8", errors='replace')
        else:
            # Fallback for older Python versions
            import codecs
            sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())
            sys.stderr = codecs.getwriter("utf-8")(sys.stderr.detach())
    except Exception:
        # Final fallback - just handle errors gracefully
        pass

def safe_print(*args, **kwargs):
    """Print function that handles Unicode encoding errors gracefully."""
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        # Convert all args to strings and handle encoding
        safe_args = []
        for arg in args:
            try:
                safe_args.append(str(arg).encode('ascii', 'replace').decode('ascii'))
            except:
                safe_args.append(repr(arg))
        print(*safe_args, **kwargs)
from selenium.common.exceptions import * #type: ignore
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException #type: ignore
from selenium.webdriver.common.by import By #type: ignore
from selenium.webdriver.common.keys import Keys #type: ignore
import string
from typing import Dict, Any, List

# ── CONFIG ───────────────────────────────────────────────────────────
SCROLLS_SEARCH = int(os.getenv("SCROLLS_SEARCH", "3"))
SCROLLS_PAGE   = int(os.getenv("SCROLLS_PAGE", "3"))
HEADLESS = os.getenv("HEADLESS", "True").lower() == "true"

# ── NEW CONFIGURATION OPTIONS ─────────────────────────────────────────
ADS_LIMIT = int(os.getenv("ADS_LIMIT", "1000"))    # Maximum number of ads to extract per (country, keyword) pair
APPEND = os.getenv("APPEND", "True").lower() == "true"       # True: append to existing file, False: create numbered files like combined_ads001.json
CONTINUATION = os.getenv("CONTINUATION", "False").lower() == "true"  # set to False to always start from scratch

COOKIE_FILE    = Path("./saved_cookies/facebook_cookies.txt")
TARGET_FILE    = Path("targets.csv")           # optional CSV (country,keyword)

OUTPUT_DIR = Path("Results")
OUTPUT_DIR.mkdir(exist_ok=True)
BASE_FILE_NAME = "combined_ads"

def get_output_file() -> Path:
    """Get the output file path based on APPEND setting"""
    if APPEND:
        return OUTPUT_DIR / f"{BASE_FILE_NAME}.json"
    else:
        # Find next available numbered file
        counter = 1
        while True:
            numbered_file = OUTPUT_DIR / f"{BASE_FILE_NAME}{counter:03d}.json"
            if not numbered_file.exists():
                return numbered_file
            counter += 1

OUTPUT_FILE = get_output_file()
CONTINUATION = False  # set to False to always start from scratch
CHECKPOINT_FILE = Path("ads_checkpoint.json")

TARGET_PAIRS: list[tuple[str,str]] = [
    ("Ukraine",       "rental apartments"),
    ("United States", "rental properties"),
    ("Canada",        "vacation homes"),
]

# Override from environment if available
target_pairs_env = os.getenv("TARGET_PAIRS")
if target_pairs_env:
    try:
        TARGET_PAIRS = [tuple(pair) for pair in json.loads(target_pairs_env)]
    except Exception:
        pass  # Keep default if parsing fails

AD_LIBRARY_URL = (
    "https://www.facebook.com/ads/library/"
    "?active_status=active&ad_type=all&country=ALL"
    "&is_targeted_country=false&media_type=all"
)
PAGE_BY_LIB_URL = (
    "https://www.facebook.com/ads/library/"
    "?active_status=active&ad_type=all&country={iso}&id={libid}"
)
AD_BY_ID_URL = (
    "https://www.facebook.com/ads/library/"
    "?active_status=active&ad_type=all&country={iso}&id={lib_id}"
)
POPUP_XPATH_CLOSE = (
    '//div[@role="button" and .//div[contains(@data-sscoverage-ignore,"true")]'
    ' and .//*[text()="Close"]]'
)

# ── XPath constants ──────────────────────────────────────────────────
COMMON_HEAD = (
    "/html/body/div[1]/div/div/div/div/div/div/div[1]/div/div/div"
)

# ── helpers ──────────────────────────────────────────────────────────
def load_cookies() -> list[dict]:
    if not COOKIE_FILE.exists():
        raise FileNotFoundError(f"Cookie file not found: {COOKIE_FILE}")
    data = json.loads(COOKIE_FILE.read_text())
    for c in data:
        if "sameSite" in c and c["sameSite"].lower() not in {"strict", "lax", "none"}:
            c["sameSite"] = "None"
    return data

def sanitize_filename(name: str) -> str:
    """Sanitize to be safe as a filename on all OSes (esp. Windows)."""
    valid = f"-_.() {string.ascii_letters}{string.digits}"
    return "".join(c if c in valid else "_" for c in name).strip("_")

def wait_click(sb: SB, selector: str, *, by="css selector", timeout=10):
    sb.wait_for_element_visible(selector, by=by, timeout=timeout)
    sb.click(selector, by=by)

def safe_type(sb: SB, selector: str, text: str, *, by="css selector",
              press_enter=True, timeout=10):
    sb.wait_for_element_visible(selector, by=by, timeout=timeout)
    elm = sb.find_element(selector, by=by)
    elm.clear()
    elm.send_keys(text)
    time.sleep(1.0)
    if press_enter:
        elm.send_keys(Keys.RETURN)
        time.sleep(2.0)

def human_scroll(sb: SB, px: int = 1800):
    sb.execute_script(f"window.scrollBy(0,{px});")

def load_checkpoint() -> set[tuple[str, str]]:
    if not CONTINUATION or not CHECKPOINT_FILE.exists():
        return set()
    try:
        data = json.loads(CHECKPOINT_FILE.read_text())
        return {tuple(p) for p in data}
    except Exception:
        return set()

def save_checkpoint(done_pairs: set[tuple[str, str]]) -> None:
    with CHECKPOINT_FILE.open("w", encoding="utf-8") as fh:
        json.dump([list(p) for p in done_pairs], fh, indent=2)

def pairs_from_csv() -> list[tuple[str, str]]:
    if not TARGET_FILE.exists():
        return []
    pairs: list[tuple[str, str]] = []
    with TARGET_FILE.open(newline="", encoding="utf-8") as fh:
        for row in csv.reader(fh):
            if not row or row[0].strip().startswith("#") or len(row) < 2:
                continue
            pairs.append((row[0].strip(), row[1].strip()))
    return pairs

def get_target_pairs() -> list[tuple[str, str]]:
    return pairs_from_csv() or TARGET_PAIRS

def save_data_immediately(pair_object: dict) -> None:
    """Save data immediately to prevent data loss if script stops"""
    try:
        if OUTPUT_FILE.exists() and APPEND:
            existing_array = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
            if not isinstance(existing_array, list):
                existing_array = []
        else:
            existing_array = []

        existing_array.append(pair_object)

        OUTPUT_FILE.write_text(
            json.dumps(existing_array, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        print(f"[INFO] Data saved immediately to {OUTPUT_FILE}")
    except Exception as e:
        print(f"[ERROR] Failed to save data: {e}")

# ── extraction primitives ────────────────────────────────────────────
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
    try:
        raw_block = card.text.strip() if card.text else ""
    except Exception:
        raw_block = ""

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
        "\nContact us", "\nSend message", "\nSend Message", "\nSubscribe", "\nRead more",
        "\nSend WhatsApp message", "\nSend WhatsApp Message", "\nWatch video", "\nWatch Video",
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

    try:
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
            except (StaleElementReferenceException, Exception):
                continue
    except Exception as e:
        print(f"[WARNING] Failed to extract links: {e}")
        pass

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
        "raw_text": raw_block,
    }

def _detect_card_prefix(sb: SB) -> str | None:
    """
    Return the correct ABS_CARD_PREFIX for the current page
    """
    for row in (5, 4):  # try logged-in layout first
        prefix = f"{COMMON_HEAD}/div[{row}]/div[2]/div[2]/div[4]/div[1]"
        try:
            sb.driver.find_element("xpath", f"{prefix}/div[1]/div")
            return prefix
        except NoSuchElementException:
            continue
    return None

def extract_cards(sb: SB, limit: int = None) -> List[Dict[str, Any]]:
    """Find the right prefix, scroll once, then walk /div[n]/div and parse."""
    ads: List[Dict[str, Any]] = []

    try:
        # Make sure Facebook injected the grid
        sb.execute_script("window.scrollBy(0, 800);")
        time.sleep(1)

        prefix = _detect_card_prefix(sb)
        if not prefix:
            print("[WARNING] Could not detect card prefix - no ads found")
            return ads

        # Guarantee first card is present
        sb.wait_for_element_visible(f"{prefix}/div[1]/div", by="xpath", timeout=15)

        n = 1
        while True:
            # Check if we've reached the limit
            if limit and len(ads) >= limit:
                print(f"[INFO] Reached ads limit: {limit}")
                break

            xpath = f"{prefix}/div[{n}]/div"
            try:
                card_ele = sb.driver.find_element("xpath", xpath)
            except NoSuchElementException:
                break

            try:
                parsed_card = _parse_card(card_ele)
                if parsed_card:  # Only add if parsing was successful
                    ads.append(parsed_card)
            except Exception as e:
                print(f"[WARNING] Failed to parse card {n}: {e}")
                pass
            n += 1

        print(f"[INFO] Found {len(ads)} ads on this page.")
        return ads

    except Exception as e:
        print(f"[ERROR] Failed to extract cards: {e}")
        return ads

def close_popup_if_present(sb):
    try:
        btn = sb.driver.find_element(
            By.XPATH,
            '//div[@role="button" and (.="Close" or @aria-label="Close dialog")]'
        )
        btn.click()
        sb.sleep(1)
    except NoSuchElementException:
        pass

# ── scrape a single "view_all_page_id=" page ─────────────────────────
def scrape_lib_page(sb: SB, iso: str, page_name: str, lib_id: str, remaining_limit: int = None) -> dict:
    sb.open(AD_BY_ID_URL.format(iso=iso, lib_id=lib_id))
    sb.sleep(4)
    close_popup_if_present(sb)

    for i in range(SCROLLS_PAGE):
        human_scroll(sb)
        sb.sleep(2 + i * 0.5)

    ads = extract_cards(sb, limit=remaining_limit)
    # Use safe_print to handle Unicode characters for Windows console
    safe_print(f"    -> {len(ads):3d} ads  |  {page_name}  |  lib_id={lib_id}")

    return {
        "page_name": page_name,
        "lib_id": lib_id,
        "ads": ads
    }

# ── scrape one (country, keyword) search ──────────────────────────────
def scrape_pair(sb: SB, country: str, keyword: str) -> None:
    safe_print(f"\n=== {country}  |  {keyword} ===")

    # 1) Country chooser
    wait_click(sb, '//div[div/div/text()="All" or div/div/text()="Country"]/..', by="xpath")
    safe_type(sb, '//input[@placeholder="Search for country"]', country, by="xpath")
    wait_click(sb, f'//div[contains(@id,"js_") and text()="{country}"]', by="xpath")
    sb.sleep(2)

    # 2) Ad category -> All ads
    wait_click(sb, '//div[div/div/text()="Ad category"]/..', by="xpath")
    wait_click(sb, '//span[text()="All ads"]/../../..', by="xpath")
    sb.sleep(2)

    # 3) Keyword box -> type + <Enter>
    KEY_BOX = ('//input[@type="search" and contains(@placeholder,"keyword") '
               'and not(@aria-disabled="true")]')
    safe_type(sb, KEY_BOX, keyword, by="xpath", press_enter=True)
    sb.sleep(4)

    # 4) Scroll a few times to load results
    for i in range(SCROLLS_SEARCH):
        human_scroll(sb)
        sb.sleep(2 + i * 0.5)

    # 5) Collect one lib‐ID per distinct page name
    try:
        ads_grid = extract_cards(sb)
        if not ads_grid:
            safe_print(f"[WARNING] No ads found for {country} | {keyword}")
            return
    except Exception as e:
        safe_print(f"[ERROR] Failed to extract cards for {country} | {keyword}: {e}")
        return

    libs = {}
    for ad in ads_grid:
        page = ad.get('page')
        lib_id = ad.get('library_id')
        if page and lib_id and page not in libs:
            libs[page] = lib_id
    print(f"[INFO] collected {len(libs)} distinct pages (1 lib-id each)")

    # 6) Derive current ISO code from the URL
    iso_match = re.search(r"country=([A-Z]{2})", sb.get_current_url())
    iso = iso_match.group(1) if iso_match else "ALL"

    # 7) Accumulate all pages/ads under this (country,keyword) with limit:
    pages_list = []
    total_ads_extracted = 0
    remaining_limit = ADS_LIMIT

    for page_name, lib_id in libs.items():
        if total_ads_extracted >= ADS_LIMIT:
            print(f"[INFO] Reached total ads limit: {ADS_LIMIT}")
            break

        result = scrape_lib_page(sb, iso, page_name, lib_id, remaining_limit)
        pages_list.append(result)

        # Update counters
        ads_count = len(result.get('ads', []))
        total_ads_extracted += ads_count
        remaining_limit = max(0, ADS_LIMIT - total_ads_extracted)

        print(f"[INFO] Total ads extracted so far: {total_ads_extracted}/{ADS_LIMIT}")

    # 8) Build the object to save immediately:
    pair_object = {
        "country": country,
        "keyword": keyword,
        "total_ads_extracted": total_ads_extracted,
        "pages": pages_list
    }

    # 9) Save data immediately
    save_data_immediately(pair_object)
    safe_print(f"[INFO] Saved data for {country} | {keyword} with {total_ads_extracted} ads")

# ── main ──────────────────────────────────────────────────────────────
def main() -> None:
    pairs = get_target_pairs()
    if not pairs:
        print("[WARN] No (country, keyword) pairs supplied.")
        return

    done_pairs = load_checkpoint()

    # Get proxy configuration
    proxy_string = get_proxy_string_with_fallback()
    if proxy_string:
        print(f"[INFO] Using proxy: {proxy_string.split('@')[-1] if '@' in proxy_string else proxy_string}")
    else:
        print("[INFO] No proxy configured - running without proxy")

    # Initialize SeleniumBase with proxy if available
    if proxy_string:
        with SB(uc=True, headless=HEADLESS, proxy=proxy_string) as sb:
            run_advertiser_scraping_logic(sb, pairs, done_pairs)
    else:
        with SB(uc=True, headless=HEADLESS) as sb:
            run_advertiser_scraping_logic(sb, pairs, done_pairs)


def run_advertiser_scraping_logic(sb, pairs, done_pairs):
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

    if not OUTPUT_FILE.exists():
        OUTPUT_FILE.write_text("[]", encoding="utf-8")
        print(f"[INFO] Created new output file: {OUTPUT_FILE}")

    for country, keyword in pairs:
        if (country, keyword) in done_pairs:
            print(f"[SKIP] Already processed: {country} | {keyword}")
            continue

        try:
            scrape_pair(sb, country, keyword)
            done_pairs.add((country, keyword))
            save_checkpoint(done_pairs)
        except Exception as e:
            print(f"[ERROR] Failed: {country} | {keyword} -> {e}")

        sb.open(AD_LIBRARY_URL)
        sb.sleep(4)

    print("\n[DONE] All pairs processed – browser stays open for 3 min.")
    sb.sleep(180)

# ── LOAD CONFIG FROM FILE OR COMMAND LINE ──────────────────────────────────
def load_config():
    """Load configuration from command line arguments or use defaults"""
    global ADS_LIMIT, APPEND, TARGET_PAIRS

    parser = argparse.ArgumentParser(description='Facebook Advertiser Ads Scraper')
    parser.add_argument('--config', type=str, help='Path to JSON config file')
    args = parser.parse_args()

    if args.config and Path(args.config).exists():
        try:
            with open(args.config, 'r') as f:
                config = json.load(f)

            ADS_LIMIT = config.get('ADS_LIMIT', ADS_LIMIT)
            APPEND = config.get('APPEND', APPEND)
            if 'TARGET_PAIRS' in config:
                TARGET_PAIRS = [tuple(pair) for pair in config['TARGET_PAIRS']]
        except Exception as e:
            print(f"[WARNING] Failed to load config file: {e}")

    # Also check environment variables as fallback
    ADS_LIMIT = int(os.environ.get('ADS_LIMIT', ADS_LIMIT))
    APPEND = os.environ.get('APPEND', str(APPEND)).lower() == 'true'

# Call load_config to initialize configuration
load_config()

if __name__ == "__main__":
    main()