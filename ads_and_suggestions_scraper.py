#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# facebook_ads_multi_tool_v1_1.py   –  v1.1  (2025‑06‑24)
#
# HOW IT WORKS ─────────────────────────────────────────────────────────────
# • Set MODE at the very top to one of:
#       "ads"              → scrape ads only
#       "suggestions"      → scrape search‑suggestions only
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
#         "country":      "...",
#         "keyword":      "...",
#         "suggestions": [ … ],     # absent if MODE=="ads"
#         "ads":          [ … ]      # absent if MODE=="suggestions"
#       }
#
# ── NEW IN 1.1 ────────────────────────────────────────────────────────────
#   Optional *filters* can now be supplied via simple variables.  If they are
#   left at their defaults, behaviour is identical to v1.0.
#   The filters are applied by *URL engineering* – after the page for a given
#   (country, keyword) pair has loaded, the script rewrites the query‑string
#   and reloads the page, instead of trying to click every dropdown.
#
#   Available filters (all optional):
#     AD_CATEGORY   – "all" | "issues" | "properties" | "employment" | "financial"
#     STATUS        – "active" | "inactive" | "all"
#     LANGUAGES     – list of language names or ISO‑639‑1 codes (e.g. ["English","fr"])
#     PLATFORMS     – list of {facebook,instagram,audience_network,messenger,threads}
#     MEDIA_TYPE    – "all" | "image" | "video" | "meme" | "image_and_meme" | "none"
#     START_DATE    – "YYYY‑MM‑DD" or None
#     END_DATE      – "YYYY‑MM‑DD" or None
#
#   Example: to get *inactive* VIDEO ads that ran between 2023‑01‑01 and
#   2024‑02‑15 on Facebook+Instagram only:
#       STATUS      = "inactive"
#       MEDIA_TYPE  = "video"
#       PLATFORMS   = ["facebook","instagram"]
#       START_DATE  = "2023‑01‑01"
#       END_DATE    = "2024‑02‑15"
#
# REQUIREMENTS ─────────────────────────────────────────────────────────────
#   pip install seleniumbase==4.*
#   saved_cookies/facebook_cookies.txt   (exported once with SeleniumBase)
# -------------------------------------------------------------------------

############################################################################

import json, csv, time, re, sys, unicodedata, os
from pathlib import Path
from datetime import datetime
from typing   import List, Dict, Tuple, Any
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse, quote
from itertools import product

from seleniumbase import SB   # type: ignore
from selenium.common.exceptions import (   # type: ignore
    NoSuchElementException, StaleElementReferenceException,
    ElementNotInteractableException,
)  # type: ignore

# ── USER‑EDITABLE SETTINGS ────────────────────────────────────────────────
# These can be overridden by environment variables or command line args
MODE = os.getenv("MODE", "ads")        #  "ads" | "suggestions" | "ads_and_suggestions"
HEADLESS = os.getenv("HEADLESS", "True").lower() == "true"      #  set False for visual debugging

# ── NEW CONFIGURATION OPTIONS (all optional) ─────────────────────────────
AD_CATEGORY = os.getenv("AD_CATEGORY", "all")           # Please check for Ad Categories and then put them here
STATUS      = os.getenv("STATUS", "active")        # "active" | "inactive" | "all"
LANGUAGES   = json.loads(os.getenv("LANGUAGES", "[]"))              # e.g. ["English", "fr", "thai"]
PLATFORMS   = json.loads(os.getenv("PLATFORMS", "[]"))              # e.g. ["facebook", "instagram"]
MEDIA_TYPE  = os.getenv("MEDIA_TYPE", "all")           # "all", "image", "video", "meme", "image_and_meme", "none"
START_DATE  = os.getenv("START_DATE") or None            # "YYYY‑MM‑DD"  – no minimum if None
END_DATE    = os.getenv("END_DATE") or None            # "YYYY‑MM‑DD"  – no maximum if None

ADS_LIMIT   = int(os.getenv("ADS_LIMIT", "1000"))            #  Maximum number of ads to extract per pair

####### ============================ IMPORTANT ========================= ####### !!!!!
APPEND      = os.getenv("APPEND", "True").lower() == "true"            #  True → append to existing file, False → numbered files
###### ============================ Now that you have read it, it's good! ========================= #######
# ── ADVERTISER FILTER ────────────────────────────────────────────────
# Give one or many page names exactly as they appear in the Ad Library.
# Leave empty (default) → feature is disabled.
ADVERTISERS = json.loads(os.getenv("ADVERTISERS", "[]"))                 # e.g. ["Vitabiotics", "Nike", "Coca-Cola"]
# ── END OF USER‑EDITABLE SETTINGS ────────────────────────────────────────
# Hard‑coded fallback pairs (overridden if targets.csv present or TARGET_PAIRS env var)  ───────────
_default_pairs = [("Thailand", "properties")]
TARGET_PAIRS: list[tuple[str, str]] = [
    tuple(pair) for pair in json.loads(os.getenv("TARGET_PAIRS", json.dumps(_default_pairs)))
]
############################################################################

# Also update the CONTINUATION setting
CONTINUATION = os.getenv("CONTINUATION", "True").lower() == "true"  # set False to start fresh

# ── CONSTANTS ─────────────────────────────────────────────────────────────
AD_LIBRARY_URL = (
    "https://www.facebook.com/ads/library/"
    "?active_status=active&ad_type=all&country=ALL"
    "&is_targeted_country=false&media_type=all"
)
COOKIE_FILE  = Path("./saved_cookies/facebook_cookies.txt")
TARGET_FILE  = Path("targets.csv")
SCROLLS      = 3                           # page‑downs for ad loading
OUTPUT_DIR   = Path("Results")

OUTPUT_DIR.mkdir(exist_ok=True)

# ── INTERNAL MAPS ─────────────────────────────────────────────────────────
AD_CATEGORY_MAP: dict[str | None, str] = {
    None:                        "all",          # fall‑back
    "all":                      "all",
    "all_ads":                  "all",
    "issues":                   "issue_ads",
    "politics":                 "issue_ads",
    "issues_elections_politics":"issue_ads",
    "properties":               "housing_ads",
    "employment":               "employment_ads",
    "financial":                "credit_ads",
}

PLATFORM_SET = {"facebook", "instagram", "audience_network", "messenger", "threads"}
MEDIA_TYPE_SET = {"all", "image", "video", "meme", "image_and_meme", "none"}

# ISO‑639‑1 language name → code  (add more freely)
LANG_MAP: dict[str, str] = {
    "arabic": "ar",    "bulgarian": "bg",  "burmese": "my",    "chinese": "zh",
    "czech": "cs",     "dutch": "nl",      "danish": "da",     "vietnamese": "vi",
    "turkish": "tr",   "thai": "th",       "swedish": "sv",    "spanish": "es",
    "slovak": "sk",    "romanian": "ro",   "portuguese": "pt", "polish": "pl",
    "norwegian": "nb", "malay": "ms",      "italian": "it",    "indonesian": "id",
    "hungarian": "hu", "greek": "el",      "german": "de",     "french": "fr",
    "english": "en",   "russian": "ru",    "ukrainian": "uk",  "amharic": "am",
}
############################################################################
CONTINUATION    = os.getenv("CONTINUATION", "True").lower() == "true"  # set False to start fresh
CHECKPOINT_FILE = OUTPUT_DIR / f"{MODE}_checkpoint.json"

# Absolute‑XPath prefix for one block of ad cards (we’ll append /div[n]/div)
ABS_CARD_PREFIX = (
    "/html/body/div[1]/div/div/div/div/div/div/div[1]/div/div/div"
    "/div[5]/div[2]/div[2]/div[4]/div[1]"
)

# ═════════════════════════════════ HELPERS ════════════════════════════════

def slugify(text: str) -> str:
    """Lower‑case, strip accents and collapse blanks – for map look‑ups."""
    norm = unicodedata.normalize("NFKD", text)
    return re.sub(r"\s+", " ", "".join(c for c in norm if not unicodedata.combining(c))).strip().lower()


def lang_to_code(name_or_code: str) -> str | None:
    "Return ISO‑639‑1 code for a given language *name* or pass‑through known codes."""
    if re.fullmatch(r"[a-z]{2}", name_or_code.strip(), flags=re.I):
        return name_or_code.lower()
    return LANG_MAP.get(slugify(name_or_code))

def _match_page(page: str | None, target: str) -> bool:
    """Case-insensitive, unicode-normalised equality test."""
    if not page:
        return False
    return unicodedata.normalize("NFKD", page).casefold() == \
           unicodedata.normalize("NFKD", target).casefold()

# ──────────────────────────────────────────────────────────────────────────
#  URL‑ENGINEERING LAYER  (v1.1 addition)
# ──────────────────────────────────────────────────────────────────────────

def _apply_filters_to_url(base_url: str) -> str:
    """Return *base_url* augmented with the filters defined at the top."""
    pr = urlparse(base_url)
    q = parse_qs(pr.query, keep_blank_values=True)

    # 1) STATUS (active_status)
    if STATUS in {"active", "inactive", "all"}:
        q["active_status"] = [STATUS]

    # 2) AD_CATEGORY  → ad_type
    ad_type_val = AD_CATEGORY_MAP.get(slugify(AD_CATEGORY) if AD_CATEGORY else None, "all")
    q["ad_type"] = [ad_type_val]

    # 3) LANGUAGE(S)   → content_languages[n]
    #     clear previous keys then re‑insert sequentially, if any were supplied.
    q = {k: v for k, v in q.items() if not k.startswith("content_languages[")}
    if LANGUAGES:
        for idx, item in enumerate(LANGUAGES):
            code = lang_to_code(item)
            if not code:
                raise ValueError(f"Unknown language: {item!r}")
            q[f"content_languages[{idx}]"] = [code]

    # 4) PLATFORMS  → publisher_platforms[n]
    q = {k: v for k, v in q.items() if not k.startswith("publisher_platforms[")}
    if PLATFORMS:
        bad = set(PLATFORMS) - PLATFORM_SET
        if bad:
            raise ValueError(f"Unknown platform(s): {', '.join(bad)}")
        for idx, p in enumerate(PLATFORMS):
            q[f"publisher_platforms[{idx}]"] = [p]

    # 5) MEDIA_TYPE
    if MEDIA_TYPE not in MEDIA_TYPE_SET:
        raise ValueError(f"Unsupported MEDIA_TYPE: {MEDIA_TYPE!r}")
    q["media_type"] = [MEDIA_TYPE]

    # 6) DATE RANGE
    for k in ("start_date[min]", "start_date[max]"):
        q.pop(k, None)                     # wipe existing
    if START_DATE:
        q["start_date[min]"] = [START_DATE]
    if END_DATE:
        q["start_date[max]"] = [END_DATE]

    new_query = urlencode(q, doseq=True, quote_via=quote)
    return urlunparse(pr._replace(query=new_query))

# ────────────────────────────────────────────────────────────────────────
#  Everything below is *mostly unchanged* from v1.0 except for a small
#  insertion point inside the country/keyword loop where we call the new
#  _apply_filters_to_url() helper.
# ────────────────────────────────────────────────────────────────────────

def load_cookies() -> list[dict]:
    if not COOKIE_FILE.exists():
        raise FileNotFoundError(f"Cookie file not found: {COOKIE_FILE}")
    try:
        cookies = json.loads(COOKIE_FILE.read_text(encoding="utf-8"))
        for c in cookies:
            if "sameSite" in c and c["sameSite"].lower() not in {"strict", "lax", "none"}:
                c["sameSite"] = "None"
        return cookies
    except UnicodeDecodeError as e:
        print(f"[ERROR] Encoding error reading cookie file: {e}")
        print(f"[INFO] Trying to read cookie file with different encodings...")
        # Try alternative encodings
        for encoding in ['cp1252', 'latin1', 'iso-8859-1']:
            try:
                cookies = json.loads(COOKIE_FILE.read_text(encoding=encoding))
                print(f"[SUCCESS] Successfully read cookie file with {encoding} encoding")
                for c in cookies:
                    if "sameSite" in c and c["sameSite"].lower() not in {"strict", "lax", "none"}:
                        c["sameSite"] = "None"
                return cookies
            except Exception:
                continue
        raise e


def wait_click(sb: SB, selector: str, *, by="css selector", timeout=10):
    """
    Wait for element to be visible and click it with error handling
    """
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


def next_output_path(mode: str) -> Path:
    """Return output file path based on APPEND setting"""
    if APPEND:
        return OUTPUT_DIR / f"{mode}.json"
    counter = 1
    while True:
        p = OUTPUT_DIR / f"{mode}{counter:03d}.json"
        if not p.exists():
            return p
        counter += 1


def save_data_immediately(pair_object: dict, mode: str) -> None:
    out_file = None
    try:
        out_file = next_output_path(mode)
        if out_file.exists() and APPEND:
            try:
                existing = json.loads(out_file.read_text(encoding="utf-8"))
                if not isinstance(existing, list):
                    existing = []
            except UnicodeDecodeError as e:
                print(f"[WARNING] Encoding error reading existing file {out_file}: {e}")
                print(f"[INFO] Trying to read existing file with different encodings...")
                # Try alternative encodings
                for encoding in ['cp1252', 'latin1', 'iso-8859-1']:
                    try:
                        existing = json.loads(out_file.read_text(encoding=encoding))
                        if not isinstance(existing, list):
                            existing = []
                        print(f"[SUCCESS] Successfully read existing file with {encoding} encoding")
                        break
                    except Exception:
                        continue
                else:
                    print(f"[WARNING] Could not read existing file with any encoding, starting fresh")
                    existing = []
            except Exception as e:
                print(f"[WARNING] Error reading existing file {out_file}: {e}, starting fresh")
                existing = []
        else:
            existing = []

        existing.append(pair_object)

        # Ensure the data is saved with UTF-8 encoding
        out_file.write_text(
            json.dumps(existing, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        print(f"[INFO] Data saved immediately to {out_file}")
        print(f"[INFO] Total records in file: {len(existing)}")

    except Exception as e:
        # Use a fallback path for error messages
        out_file_str = str(out_file) if out_file else "unknown_file"

        print(f"[ERROR] Failed to save data to {out_file_str}: {e}")
        # Try to save to a backup file
        try:
            if out_file:
                backup_file = out_file.parent / f"backup_{out_file.name}"
            else:
                backup_file = OUTPUT_DIR / f"backup_{mode}.json"
            backup_file.write_text(
                json.dumps([pair_object], indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
            print(f"[INFO] Data saved to backup file: {backup_file}")
        except Exception as backup_error:
            print(f"[ERROR] Failed to save backup file: {backup_error}")
            raise e


def safe_type(sb: SB, selector: str, text: str, *, by="css selector", press_enter: bool = True, timeout: int = 10):
    """
    Safely type text into an input field with enhanced error handling
    """
    from selenium.webdriver.common.keys import Keys  # type: ignore
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


def human_scroll(sb: SB, px: int = 1800):
    sb.execute_script(f"window.scrollBy(0,{px});")


def load_checkpoint() -> set[tuple[str, str, str | None]]:
    if not CONTINUATION or not CHECKPOINT_FILE.exists():
        return set()
    try:
        data = json.loads(CHECKPOINT_FILE.read_text(encoding="utf-8"))
        return {tuple(p) for p in data}
    except UnicodeDecodeError as e:
        print(f"[WARNING] Encoding error reading checkpoint file: {e}")
        print(f"[INFO] Trying to read checkpoint file with different encodings...")
        # Try alternative encodings
        for encoding in ['cp1252', 'latin1', 'iso-8859-1']:
            try:
                data = json.loads(CHECKPOINT_FILE.read_text(encoding=encoding))
                print(f"[SUCCESS] Successfully read checkpoint file with {encoding} encoding")
                return {tuple(p) for p in data}
            except Exception:
                continue
        print(f"[WARNING] Could not read checkpoint file with any encoding, starting fresh")
        return set()
    except Exception as e:
        print(f"[WARNING] Error reading checkpoint file: {e}, starting fresh")
        return set()


def save_checkpoint(done_pairs: set[tuple[str, str, str | None]]) -> None:
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

# ══════════════════════ SUGGESTION SCRAPING LOGIC (unchanged) ════════════
#  … (functions extract_suggestions, _parse_card, _detect_card_prefix,
#     extract_ads) are *identical* to v1.0 and omitted here for brevity.
#  They can be copied verbatim from the previous version.
############################################################################

#  (For the sake of keeping this file self‑contained we re‑insert them in full
#    below.  Nothing inside these functions was touched.)

# ──────────────────────────────────────────────────────────────────────────
#  … (FULL CONTENT OF extract_suggestions, _parse_card, _detect_card_prefix,
#     extract_ads – unchanged – SNIPPED FOR CLARITY IN THIS CODE SAMPLE) …
# ──────────────────────────────────────────────────────────────────────────

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
        # "raw_text": raw_block,
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
def extract_ads(sb: SB, limit: int = None) -> List[Dict[str, Any]]:
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
        # Check if we've reached the limit
        if limit and len(ads) >= limit:
            print(f"[INFO] Reached ads limit: {limit}")
            break

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
    print(f"[INFO] Found {len(ads)} ads on this page.")
    return ads

############################################################################
# ═════════════════════════════════ MAIN ══════════════════════════════════

def main():
    pairs = get_target_pairs()
    if MODE not in {"ads", "suggestions", "ads_and_suggestions"}:
        sys.exit(f"[ERR] MODE must be 'ads', 'suggestions' or 'ads_and_suggestions' (got {MODE!r})")
    if not pairs:
        sys.exit("[ERR] No (country, keyword) pairs found.")

    out_path = next_output_path(MODE)

    with SB(uc=True, headless=HEADLESS) as sb:
        # ── Login bootstrap ───────────────────────────────────────────────
        print("[INFO] Opening Facebook …")
        sb.open("https://facebook.com")
        print("[INFO] Restoring session cookies …")
        for ck in load_cookies():
            try:
                sb.driver.add_cookie(ck)
            except Exception:
                pass
        sb.open(AD_LIBRARY_URL)
        sb.sleep(5)

        # Build an iterable of (country, keyword, advertiser)
        #  – if ADVERTISERS is empty we feed through a single [None] sentinel
        triples = product(pairs, ADVERTISERS or [None])

        # LOOP over all (country, keyword, advertiser) triples  ───────────
        done_pairs = load_checkpoint()

        for (country, keyword), advertiser in triples:
            # Skip logic now tracks advertiser as well
            if (country, keyword, advertiser) in done_pairs:
                print(f"[SKIP] Already processed: {country} | {keyword} | {advertiser}")
                continue

            search_term = advertiser or keyword     # <- what we will type in the box
            print(f"\n=== {country} | {search_term} {'(advertiser search)' if advertiser else ''} ===")            # 1) Country dropdown
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

            # 2) Ad category → All ads (we will *override* via URL later if needed)
            wait_click(sb, '//div[div/div/text()="Ad category"]/..', by="xpath")
            wait_click(sb, '//span[text()="All ads"]/../../..', by="xpath")
            sb.sleep(2)            # 3) Keyword box
            KEY_BOX = ('//input[@type="search" and contains(@placeholder,"keyword") '
                       'and not(@aria-disabled="true")]')

            suggestions, ads = [], []

            if MODE == "suggestions":
                suggestions = extract_suggestions(sb, search_term)

            elif MODE == "ads":
                safe_type(sb, KEY_BOX, search_term, by="xpath", press_enter=True)
                sb.sleep(4)

                # ── v1.1 INSERTION POINT – apply filters via URL───────────
                filtered_url = _apply_filters_to_url(sb.driver.current_url)
                if filtered_url != sb.driver.current_url:
                    sb.open(filtered_url)
                    sb.sleep(5)

                for i in range(SCROLLS):
                    human_scroll(sb); sb.sleep(2+i*0.5)
                ads = extract_ads(sb, limit=ADS_LIMIT)

                # Filter scraped cards by advertiser
                if advertiser:
                    before = len(ads)
                    ads = [ad for ad in ads if _match_page(ad.get("page"), advertiser)]
                    print(f"[INFO] Kept {len(ads)}/{before} ads that belong to \"{advertiser}\".")

            elif MODE == "ads_and_suggestions":
                # suggestions first (no enter)
                suggestions = extract_suggestions(sb, search_term)
                # hit <Enter> and scrape ads
                safe_type(sb, KEY_BOX, search_term, by="xpath", press_enter=True)
                sb.sleep(4)

                filtered_url = _apply_filters_to_url(sb.driver.current_url)
                if filtered_url != sb.driver.current_url:
                    sb.open(filtered_url)
                    sb.sleep(5)

                for i in range(SCROLLS):
                    human_scroll(sb); sb.sleep(2+i*0.5)
                ads = extract_ads(sb, limit=ADS_LIMIT)

                # Filter scraped cards by advertiser
                if advertiser:
                    before = len(ads)
                    ads = [ad for ad in ads if _match_page(ad.get("page"), advertiser)]
                    print(f"[INFO] Kept {len(ads)}/{before} ads that belong to \"{advertiser}\".")            # Build filter details for this run
            filter_details = {
                "mode": MODE,
                "ad_category": AD_CATEGORY,                "status": STATUS,
                "languages": LANGUAGES,
                "platforms": PLATFORMS,
                "media_type": MEDIA_TYPE,
                "start_date": START_DATE,
                "end_date": END_DATE,
                "ads_limit": ADS_LIMIT,
                "advertiser": advertiser,
                "timestamp": datetime.now().isoformat()
            }

            # Build and save data immediately
            pair_object = {
                "country":     country,
                "keyword":     keyword,
                "advertiser":  advertiser,
                "filters":     filter_details,
                **({"suggestions": suggestions} if MODE != "ads" else {}),
                **({"ads": ads}             if MODE != "suggestions" else {}),
            }

            save_data_immediately(pair_object, MODE)
            print(f"[INFO] Saved data for {country} | {search_term} {'(advertiser)' if advertiser else ''} – Suggestions: {len(suggestions)}, Ads: {len(ads)}")
            done_pairs.add((country, keyword, advertiser))
            save_checkpoint(done_pairs)

            # Back to Ad‑Library home for next pair
            sb.open(AD_LIBRARY_URL)
            sb.sleep(4)

    print("\n[DONE] All pairs processed with immediate saving.")

# ──────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
