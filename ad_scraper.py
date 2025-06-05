#!/usr/bin/env python3
# facebook_ads_scraper.py  –  v2.1  (2025-06-04)
#
# WHAT’S NEW (vs your previous single-pair version)
#   • Scrapes several (country, keyword) pairs in one browser session.
#   • Pairs can be hard-coded in TARGET_PAIRS or read from targets.csv
#     (same CSV format as the reference multi-pair script).
#   • After each pair it jumps straight back to the Ad-Library home URL;
#     no other behaviour has been altered.
#
# REQUIREMENTS
#   pip install seleniumbase==4.*
#   saved_cookies/facebook_cookies.txt   (exported with SeleniumBase or similar)

import json, time, csv
from pathlib import Path
from seleniumbase import SB
from selenium.common.exceptions import (
    NoSuchElementException,
    ElementNotInteractableException,
    StaleElementReferenceException,
)

##############################################################################
# ── CONFIG ­───────────────────────────────────────────────────────────────
SCROLLS      = 3
COOKIE_FILE  = Path("./saved_cookies/facebook_cookies.txt")
TARGET_FILE  = Path("targets.csv")          # optional CSV (country,keyword)

# Hard-coded fallback list (comment / edit as you like)
TARGET_PAIRS: list[tuple[str, str]] = [
    ("Ukraine",      "rental apartments"),
    ("United States","rental properties"),
    ("Canada",     "vacation homes"),
]

AD_LIBRARY_URL = (
    "https://www.facebook.com/ads/library/"
    "?active_status=active&ad_type=all&country=ALL"
    "&is_targeted_country=false&media_type=all"
)
##############################################################################
# ── HELPERS (unchanged) ­──────────────────────────────────────────────────
def load_cookies() -> list[dict]:
    if not COOKIE_FILE.exists():
        raise FileNotFoundError(f"Cookie file not found: {COOKIE_FILE}")
    data = json.loads(COOKIE_FILE.read_text())
    for c in data:
        if "sameSite" in c and c["sameSite"].lower() not in {"strict", "lax", "none"}:
            c["sameSite"] = "None"
    return data


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
        from selenium.webdriver.common.keys import Keys
        elm.send_keys(Keys.RETURN)
        time.sleep(2.0)


def human_scroll(sb: SB, px: int = 1800):
    sb.execute_script(f"window.scrollBy(0,{px});")
##############################################################################
# ── IO for target pairs ­──────────────────────────────────────────────────
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
    csv_pairs = pairs_from_csv()
    return csv_pairs or TARGET_PAIRS
##############################################################################
# ── SCRAPING ROUTINE (logic unchanged, now parameterised) ­───────────────
def scrape_pair(sb: SB, country: str, keyword: str) -> None:
    print(f"\n=== {country}  |  {keyword} ===")

    # 1) Country chooser
    wait_click(sb, '//div[div/div/text()="All" or div/div/text()="Country"]/..', by="xpath")
    safe_type(sb, '//input[@placeholder="Search for country"]', country, by="xpath")
    wait_click(sb, f'//div[contains(@id,"js_") and text()="{country}"]', by="xpath")
    sb.sleep(2)

    # 2) Ad category → All ads
    wait_click(sb, '//div[div/div/text()="Ad category"]/..', by="xpath")
    wait_click(sb, '//span[text()="All ads"]/../../..', by="xpath")
    sb.sleep(2)

    # 3) Keyword box
    KEY_BOX = ('//input[@type="search" and contains(@placeholder,"keyword") '
               'and not(@aria-disabled="true")]')
    safe_type(sb, KEY_BOX, keyword, by="xpath", press_enter=True)
    sb.sleep(4)

    # 4) Scroll to load more ads
    for i in range(SCROLLS):
        human_scroll(sb)
        sb.sleep(2 + i * 0.5)

    # 5) Scrape cards (unchanged)
    ads, cards = [], sb.find_elements("div.xh8yej3")
    print(f"[INFO] found {len(cards)} candidate nodes")

    def _txt(el, xp):
        try:
            return el.find_element("xpath", xp).text.strip()
        except NoSuchElementException:
            return ""

    for card in cards:
        try:
            meta = card.find_element(
                "css selector",
                "div.x1plvlek.xryxfnj.x1gzqxud.x178xt8z.x1lun4ml.xso031l.xpilrb4.xb9moi8.xe76qn7.x21b0me.x142aazg.xhk9q7s.x1otrzb0.x1i1ezom.x1o6z2jb.x1kmqopl.x13fuv20.x18b5jzi.x1q0q8m5.x1t7ytsu.x9f619"

            )
            status      = _txt(meta, './/span[contains(text(),"Active") or contains(text(),"Inactive")]')
            library_id  = _txt(meta, './/span[contains(text(),"Library ID")]').split(":")[-1].strip()
            started_raw = _txt(meta, './/span[contains(text(),"Started running")]')

            creative = card.find_element("css selector", "div._7jyg")
            page_name     = _txt(creative, ".//a[1]")
            primary_text  = _txt(creative, './/div[@role="button"][1]')
            cta_button    = _txt(
                creative,
                './/span[text()="Learn More" or text()="Contact us" or '
                'text()="Book Now" or text()="Send message"]',
            )

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
            continue

    print(f"[SUCCESS] extracted {len(ads)} ads")
    out_name = f"ads_{country.replace(' ','_')}_{keyword.replace(' ','_')}.json"
    Path(out_name).write_text(
        json.dumps(ads, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"[INFO] saved → {out_name}")

##############################################################################
# ── MAIN ­─────────────────────────────────────────────────────────────────
def main() -> None:
    pairs = get_target_pairs()
    if not pairs:
        print("[WARN] No (country, keyword) pairs supplied.")
        return

    with SB(uc=True, headless=False) as sb:        # headless=False kept as in original
        # First page-load and cookie injection (unchanged)
        print("[INFO] Opening Facebook …")
        sb.open("https://facebook.com")
        print("[INFO] Restoring session cookies …")
        for ck in load_cookies():
            try: sb.driver.add_cookie(ck)
            except Exception: pass

        # Jump straight to the Ad-Library start page
        sb.open(AD_LIBRARY_URL)
        sb.sleep(5)

        # Loop over all pairs
        for country, keyword in pairs:
            scrape_pair(sb, country, keyword)

            # Return to Ad-Library home screen for next iteration
            sb.open(AD_LIBRARY_URL)
            sb.sleep(4)

        print("\n[DONE] All pairs processed – browser stays open for review.")
        sb.sleep(180)    # keep window alive for manual inspection (3 min)

##############################################################################
if __name__ == "__main__":
    main()
