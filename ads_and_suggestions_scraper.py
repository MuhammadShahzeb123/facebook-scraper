#!/usr/bin/env python3
# facebook_ads_multi_tool.py   –  v1.0  (2025-06-05)
#
# HOW IT WORKS ─────────────────────────────────────────────────────────────
# • Set MODE at the very top to one of:
#       "ads"              → scrape ads only
#       "suggestions"      → scrape search-suggestions only
#       "ads_and_suggestions"
#                           → collect suggestions first, THEN press <Enter>
#                             and scrape ads – all in one pass per pair.
#
# • All (country, keyword) pairs live in TARGET_PAIRS (or targets.csv).
#
# • Each run writes a *single* JSON file whose name is derived from MODE:
#       ads.json / suggestions.json / ads_and_suggestions.json
#   – If the base file already exists from a previous run, the script will
#     create ads_2.json, ads_3.json … etc.  Nothing ever gets overwritten.
#
# • Inside that JSON you get one element per pair:
#       {
#         "country": "...",
#         "keyword": "...",
#         "suggestions": [ … ],    # absent if MODE=="ads"
#         "ads":          [ … ]     # absent if MODE=="suggestions"
#       }
#
# REQUIREMENTS
#   pip install seleniumbase==4.*
#   saved_cookies/facebook_cookies.txt   (exported once with SeleniumBase)
# -------------------------------------------------------------------------

############################################################################
# ── USER-EDITABLE SETTINGS ────────────────────────────────────────────────
MODE = "suggestions"        #  "ads" | "suggestions" | "ads_and_suggestions"
HEADLESS = False                     #  set False for visual debugging

# Hard-coded fallback pairs (overridden if targets.csv present)  ───────────
TARGET_PAIRS: list[tuple[str, str]] = [
    ("Ukraine",       "rental apartments"),
    ("United States", "rental properties"),
    ("Canada",        "vacation homes"),
]

############################################################################

import json, csv, time, re, sys
from pathlib import Path
from datetime import datetime
from typing   import List, Dict, Tuple, Any
from seleniumbase import SB # type: ignore
from selenium.common.exceptions import ( # type: ignore
    NoSuchElementException, StaleElementReferenceException,
    ElementNotInteractableException,
)#type: ignore

# ── CONSTANTS ─────────────────────────────────────────────────────────────
AD_LIBRARY_URL = (
    "https://www.facebook.com/ads/library/"
    "?active_status=active&ad_type=all&country=ALL"
    "&is_targeted_country=false&media_type=all"
)
COOKIE_FILE  = Path("./saved_cookies/facebook_cookies.txt")
TARGET_FILE  = Path("targets.csv")
SCROLLS      = 3                           # page-downs for ad loading
OUTPUT_DIR   = Path("Results")

OUTPUT_DIR.mkdir(exist_ok=True)
############################################################################
CONTINUATION = True  # set False to start fresh
CHECKPOINT_FILE = OUTPUT_DIR / f"{MODE}_checkpoint.json"
# Absolute-XPath prefix for one block of ad cards (we’ll append /div[n]/div)
ABS_CARD_PREFIX = (
    "/html/body/div[1]/div/div/div/div/div/div/div[1]/div/div/div"
    "/div[5]/div[2]/div[2]/div[4]/div[1]"
)


# ═════════════════════════════════ HELPERS ════════════════════════════════
def load_cookies() -> list[dict]:
    if not COOKIE_FILE.exists():
        raise FileNotFoundError(f"Cookie file not found: {COOKIE_FILE}")
    cookies = json.loads(COOKIE_FILE.read_text())
    for c in cookies:
        if "sameSite" in c and c["sameSite"].lower() not in {"strict", "lax", "none"}:
            c["sameSite"] = "None"
    return cookies


def wait_click(sb: SB, selector: str, *, by="css selector", timeout=10):
    sb.wait_for_element_visible(selector, by=by, timeout=timeout)
    sb.click(selector, by=by)

def next_output_path(mode: str) -> Path:
    """Return a consistent path for persistent appending."""
    return OUTPUT_DIR / f"{mode}.json"

def safe_type(sb: SB, selector: str, text: str, *,
              by="css selector", press_enter: bool = True, timeout: int = 10):
    from selenium.webdriver.common.keys import Keys # type: ignore

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

def next_output_path(mode: str) -> Path:
    """Return a consistent path for persistent appending."""
    return OUTPUT_DIR / f"{mode}.json"


# ══════════════════════ SUGGESTION SCRAPING LOGIC ════════════════════════
def extract_suggestions(sb: SB, keyword: str) -> list[Dict[str, Any]]:
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

    # Clear search box for next keyword (if MODE=="suggestions" only)
    sb.find_element(KEYWORD_INPUT, by="xpath").clear()
    return suggestions
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
        "raw_text": raw_block,
    }

# ── shared path head --------------------------------------------------
COMMON_HEAD = (
    "/html/body/div[1]/div/div/div/div/div/div/div[1]/div/div/div"
)
# ──────────────────────────────────────────────────────────────────────
def _detect_card_prefix(sb: SB) -> str | None:
    """
    Return the correct ABS_CARD_PREFIX for the current page:
      …/div[5]/… if present, otherwise …/div[4]/…
    Uses *presence* (find_element) so the card doesn’t have to be in view.
    """
    for row in (5, 4):                                     # try logged-in layout first
        prefix = f"{COMMON_HEAD}/div[{row}]/div[2]/div[2]/div[4]/div[1]"
        try:
            sb.driver.find_element("xpath", f"{prefix}/div[1]/div")
            return prefix                                  # found!
        except NoSuchElementException:
            continue
    return None                                            # nothing matched
# ──────────────────────────────────────────────────────────────────────
def extract_ads(sb: SB) -> List[Dict[str, Any]]:
    """Find the right prefix, scroll once, then walk /div[n]/div and parse."""
    ads: List[Dict[str, Any]] = []

    # make sure Facebook injected the grid: a tiny scroll usually does it
    sb.execute_script("window.scrollBy(0, 800);")
    time.sleep(1)

    prefix = _detect_card_prefix(sb)
    if not prefix:
        return ads                                         # 0 ads found

    # guarantee first card is present before iterating
    sb.wait_for_element_visible(f"{prefix}/div[1]/div", by="xpath", timeout=15)

    n = 1
    while True:
        xpath = f"{prefix}/div[{n}]/div"
        try:
            card_ele = sb.driver.find_element("xpath", xpath)
        except NoSuchElementException:
            break                                          # end of list
        try:
            ads.append(_parse_card(card_ele))
        except Exception:
            pass                                           # malformed card
        n += 1
    print(f"[INFO] Found {n-1} ads on this page.")
    return ads



# ═════════════════════════════════ MAIN ══════════════════════════════════
def main():
    pairs = get_target_pairs()
    if MODE not in {"ads", "suggestions", "ads_and_suggestions"}:
        sys.exit(f"[ERR] MODE must be 'ads', 'suggestions' or 'ads_and_suggestions' (got {MODE!r})")
    if not pairs:
        sys.exit("[ERR] No (country, keyword) pairs found.")

    out_path   = next_output_path(MODE)
    run_data: List[Dict[str, Any]] = []

    with SB(uc=True, headless=HEADLESS) as sb:
        # ── Login bootstrap ────────────────────────────────────────────────
        print("[INFO] Opening Facebook …")
        sb.open("https://facebook.com")
        print("[INFO] Restoring session cookies …")
        for ck in load_cookies():
            try: sb.driver.add_cookie(ck)
            except Exception: pass
        sb.open(AD_LIBRARY_URL)
        sb.sleep(5)

        # LOOP over all (country, keyword) pairs  ───────────────────────────
        done_pairs = load_checkpoint()

        for country, keyword in pairs:
            if (country, keyword) in done_pairs:
                print(f"[SKIP] Already processed: {country} | {keyword}")
                continue

            print(f"\n=== {country} | {keyword} ===")

            # 1) Country dropdown
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

            suggestions, ads = [], []

            if MODE == "suggestions":
                suggestions = extract_suggestions(sb, keyword)

            elif MODE == "ads":
                # type + <Enter> straight away
                safe_type(sb, KEY_BOX, keyword, by="xpath", press_enter=True)
                sb.sleep(4)
                # scroll to load more
                for i in range(SCROLLS):
                    human_scroll(sb); sb.sleep(2+i*0.5)
                ads = extract_ads(sb)

            elif MODE == "ads_and_suggestions":
                # 3a) suggestions first (no enter)
                suggestions = extract_suggestions(sb, keyword)
                # 3b) now hit <Enter> and scrape ads
                safe_type(sb, KEY_BOX, keyword, by="xpath", press_enter=True)
                sb.sleep(4)
                for i in range(SCROLLS):
                    human_scroll(sb); sb.sleep(2+i*0.5)
                ads = extract_ads(sb)

            # store run-unit
            run_data.append({
                "country":     country,
                "keyword":     keyword,
                **({"suggestions": suggestions} if MODE != "ads" else {}),
                **({"ads": ads}             if MODE != "suggestions" else {}),
            })
            done_pairs.add((country, keyword))
            save_checkpoint(done_pairs)
            print(f"  > {len(suggestions):>3} suggestions   |   {len(ads):>3} ads")

            # Back to Ad-Library home for next pair
            sb.open(AD_LIBRARY_URL)
            sb.sleep(4)
    # ── APPEND TO EXISTING OUTPUT FILE ────────────────────────────────────
    if out_path.exists():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
            if not isinstance(existing, list):
                existing = []
        except Exception:
            existing = []
    else:
        existing = []

    existing.extend(run_data)

    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(existing, fh, indent=2, ensure_ascii=False)

    print(f"\n[DONE] Appended {len(run_data)} new entries to {out_path}")

    print(f"\n[DONE] Saved {len(run_data)} pairs to {out_path}")

# ──────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
