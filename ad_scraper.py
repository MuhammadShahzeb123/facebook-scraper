#!/usr/bin/env python3
# facebook_ads_scraper.py
#
# REQUIREMENTS
#   pip install seleniumbase==4.* or latest
#   A file ./saved_cookies/facebook_cookies.txt  (exported with SeleniumBase or any FB cookie-grabber)
#
# USAGE
#   python facebook_ads_scraper.py --keyword "rental properties" --country "United States" --scrolls 3
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
# parser = argparse.ArgumentParser(description="Scrape Facebook Ad Library ads")
# parser.add_argument("--keyword", required=True, help="Ad Library keyword/phrase")
# parser.add_argument("--country", default="United States", help="Target country")
# parser.add_argument("--scrolls", type=int, default=3,
#                     help="How many times to scroll down (≈ ‘pages’ of ads)")
# args = parser.parse_args()

# # KEYWORD  = args.keyword
# KEYWORD = "rental properties"  # default for testing
# # COUNTRY  = args.country
# COUNTRY = "United States"
# SCROLLS  = max(args.scrolls, 1)
##############################################################################
# 1) Configurable Parameters (no CLI)
##############################################################################
KEYWORD = "rental Apartments"
COUNTRY = "Ukraine"
SCROLLS = 3  # Set how many times to scroll down

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



def human_scroll(sb, amount_px=1500):
    sb.execute_script(f"window.scrollBy(0,{amount_px});")

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

    sb.open("https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=ALL&is_targeted_country=false&media_type=all")
    # Ad Library now loaded inside a FB shell ( domain may be “facebook.com/ads/library” )
    print("[INFO] Setting country …")
    # 1. open country chooser
    COUNTRY_CHOOSER = '//div[div/div/text()="All" or div/div/text()="Country"]/..'
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
    # 2. click “All ads”
    ALL_ADS_OPTION = '//span[text()="All ads"]/../../..'   # walks up to clickable radio wrapper
    wait_click(sb, ALL_ADS_OPTION, by="xpath")
    sb.sleep(2)

    print("[INFO] Entering keyword …")
    # keyword input unlocks after category selection
    KEYWORD_INPUT = '//input[@type="search" and ''contains(@placeholder,"keyword") and ''not(@aria-disabled="true")]'
    safe_type(sb, KEYWORD_INPUT, KEYWORD, by="xpath", press_enter=True)
    sb.sleep(4)  # results load
    # ── Scroll N times so lazy-loader fetches more ads ─────────────────────
    print(f"[INFO] Scrolling {SCROLLS} × …")
    for i in range(SCROLLS):
        human_scroll(sb, 1800)
        sb.sleep(2 + i * 0.5)  # small incremental wait
    # ── Scrape ad cards ────────────────────────────────────────────────────
    print("[INFO] Scraping ad cards …")
    ads = []
    cards = sb.find_elements("div.xh8yej3")                # ← 1 wrapper per ad
    print(f"  > found {len(cards)} candidate nodes")

    def _txt(el, xp):
        "helper: safe .text for a relative XPath"
        try:
            return el.find_element("xpath", xp).text.strip()
        except NoSuchElementException:
            return ""

    for card in cards:
        try:
            # 1) META strip (status / ID / dates / platforms)
            meta = card.find_element(
                "css selector",                       # ← strategy first
                'div.x1cy8zhl.x78zum5.xyamay9.x1pi30zi'
            )


            status      = _txt(meta, './/span[contains(text(),"Active") or contains(text(),"Inactive")]')
            library_id  = _txt(meta, './/span[contains(text(),"Library ID")]').split(":")[-1].strip()
            started_raw = _txt(meta, './/span[contains(text(),"Started running")]')

            # 2) CREATIVE header/body
            creative = card.find_element(
                "css selector",
                'div._7jyg'
            )
            page_name     = _txt(creative, './/a[1]')
            primary_text  = _txt(creative, './/div[@role="button"][1]')   # first text-block inside the ad
            cta_button    = _txt(creative, './/span[text()="Learn More" or text()="Contact us" or text()="Book Now" or text()="Send message"]')

            # external link (if any) – take the first link that isn’t the Page link
            link = ""
            for a in creative.find_elements("tag name", "a"):
                href = a.get_attribute("href") or ""
                if "facebook.com" not in href.lower():
                    link = href
                    break

            ads.append(
                {
                    "status":       status,
                    "library_id":   library_id,
                    "started":      started_raw,
                    "page":         page_name,
                    "primary_text": primary_text,
                    "cta":          cta_button,
                    "external_url": link,
                }
            )

        except (NoSuchElementException,
                StaleElementReferenceException,
                ElementNotInteractableException):
            # skip cards that don’t match the expected structure
            continue

    print(f"[SUCCESS] Extracted {len(ads)} ads")

    # ── Persist ───────────────────────────────────────────────────────────
    out_name = f"ads_{KEYWORD.replace(' ', '_')}.json"
    Path(out_name).write_text(
        json.dumps(ads, indent=2, ensure_ascii=False),
        encoding="utf-8"          # always write UTF-8 on Windows
    )
    print(f"[INFO] Saved to {out_name}")
    print("Sample ↓")
    print(json.dumps(ads[:3], indent=2, ensure_ascii=False))
