#!/usr/bin/env python3
# facebook_ads_scraper.py  –  v2.2  (2025-06-04)

#  ▄───────────────────────────────────────────────────────────────────▄
#  │  NEW IN 2.2                                                      │
#  │    • robust page-id collection via page-source regex             │
#  │    • for every id → open “view_all_page_id” url and scrape ads   │
#  ▀───────────────────────────────────────────────────────────────────▀

import json, time, csv, re, os
from pathlib import Path
from collections import defaultdict
from seleniumbase import SB #type: ignore
from selenium.common.exceptions import * #type: ignore 
from selenium.webdriver.common.by import By #type: ignore
from selenium.webdriver.common.keys import Keys #type: ignore
import string
# ── CONFIG ───────────────────────────────────────────────────────────
SCROLLS_SEARCH = 3
SCROLLS_PAGE   = 3
COOKIE_FILE    = Path("./saved_cookies/facebook_cookies.txt")
TARGET_FILE    = Path("targets.csv")           # optional CSV (country,keyword)

OUTPUT_DIR = Path("Results")
OUTPUT_DIR.mkdir(exist_ok=True)
OUTPUT_FILE = OUTPUT_DIR / "combined_ads.json"
CONTINUATION = True  # set to False to always start from scratch
CHECKPOINT_FILE = Path("ads_checkpoint.json")

TARGET_PAIRS: list[tuple[str,str]] = [
    ("Ukraine",       "rental apartments"),
    ("United States", "rental properties"),
    ("Canada",        "vacation homes"),
]

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
        from selenium.webdriver.common.keys import Keys #type: ignore
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

# from utils_collect import collect_page_ids_current_query   # ← new import

# ── extraction primitives ────────────────────────────────────────────
LIB_ID_RE   = re.compile(r'"ad_archive_id":"(\d{5,})"')
PAGE_NAME_RE= re.compile(r'"page_name":"([^"]+)"')
def collect_one_lib_per_page(sb: SB) -> dict[str, str]:
    """
    Returns a mapping  {page_name -> ONE library_id}  taken from the *current*
    search-results grid (whatever is already loaded after the keyword query
    and a couple of scrolls).

    We simply reuse `extract_cards()` and keep the first lib-id seen for
    every distinct page name.
    """
    unique: dict[str, str] = {}         # {page → lib_id}

    for ad in extract_cards(sb):        # ← unchanged helper
        pn = (ad.get("page") or "").strip()
        lid = (ad.get("library_id") or "").strip()
        if pn and lid and pn not in unique:
            unique[pn] = lid            # keep the very first one we met
    return unique
def _txt(el, xp):
    try:
        return el.find_element("xpath", xp).text.strip()
    except NoSuchElementException: # type: ignore
        return ""


def extract_cards(sb: SB) -> list[dict]:
    ads, cards = [], sb.find_elements("div.xh8yej3")
    for card in cards:
        try:
            meta = card.find_element(
                "css selector", "div.x1plvlek.xryxfnj.x1gzqxud.x178xt8z.x1lun4ml.xso031l.xpilrb4.xb9moi8.xe76qn7.x21b0me.x142aazg.xhk9q7s.x1otrzb0.x1i1ezom.x1o6z2jb.x1kmqopl.x13fuv20.x18b5jzi.x1q0q8m5.x1t7ytsu.x9f619"

            )
            status      = _txt(meta, './/span[contains(text(),"Active") or contains(text(),"Inactive")]')
            library_id  = _txt(meta, './/span[contains(text(),"Library ID")]').split(":")[-1].strip()
            started_raw = _txt(meta, './/span[contains(text(),"Started running")]')

            creative = card.find_element("css selector", "div._7jyg")
            page_name    = _txt(creative, ".//a[1]")
            primary_text = _txt(creative, './/div[@role="button"][1]')
            cta_button   = _txt(
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
                dict(
                    status=status, library_id=library_id, started=started_raw,
                    page=page_name, primary_text=primary_text,
                    cta=cta_button, external_url=link,
                )
            )
        except (NoSuchElementException, # type: ignore
                StaleElementReferenceException, # type: ignore
                ElementNotInteractableException): # type: ignore
            continue
    return ads
def close_popup_if_present(sb):
    try:
        btn=sb.driver.find_element(
            By.XPATH,
            '//div[@role="button" and (.="Close" or @aria-label="Close dialog")]')
        btn.click()
        sb.sleep(1)
    except NoSuchElementException: # type: ignore
        pass

# ── scrape a single “view_all_page_id=” page ─────────────────────────
def scrape_lib_page(sb: SB, iso: str, page_name: str, lib_id: str) -> None:
    sb.open(AD_BY_ID_URL.format(iso=iso, lib_id=lib_id))
    sb.sleep(4)

    try:
        sb.click(POPUP_XPATH_CLOSE, by="xpath")
        sb.sleep(1)
    except Exception:
        pass

    for i in range(SCROLLS_PAGE):
        human_scroll(sb)
        sb.sleep(2 + i * 0.5)

    ads = extract_cards(sb)
    print(f"    ↳ {len(ads):3d} ads  •  {page_name}  •  lib_id={lib_id}")

    return {
        "page_name": page_name,
        "lib_id": lib_id,
        "ads": ads
    }
# ── scrape one (country, keyword) search ──────────────────────────────
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

    # 3) Keyword box → type + <Enter>
    KEY_BOX = ('//input[@type="search" and contains(@placeholder,"keyword") '
               'and not(@aria-disabled="true")]')
    safe_type(sb, KEY_BOX, keyword, by="xpath", press_enter=True)
    sb.sleep(4)

    # 4) Scroll a few times to load results
    for i in range(SCROLLS_SEARCH):
        human_scroll(sb)
        sb.sleep(2 + i * 0.5)

    # 5) Collect one lib‐ID per distinct page name
    libs = collect_one_lib_per_page(sb)
    print(f"[INFO] collected {len(libs)} distinct pages (1 lib-id each)")

    # 6) Derive current ISO code from the URL
    iso_match = re.search(r"country=([A-Z]{2})", sb.get_current_url())
    iso = iso_match.group(1) if iso_match else "ALL"

    # 7) Accumulate all pages/ads under this (country,keyword):
    pages_list = []
    for page_name, lib_id in libs.items():
        result = scrape_lib_page(sb, iso, page_name, lib_id)
        # result already is { "page_name": ..., "lib_id": ..., "ads": [...] }
        pages_list.append(result)

    # 8) Build the object to append:
    pair_object = {
        "country": country,
        "keyword": keyword,
        "pages": pages_list
    }

    # 9) Load existing array from combined_ads.json, append, and overwrite
    try:
        existing_array = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
        if not isinstance(existing_array, list):
            existing_array = []
    except Exception:
        existing_array = []

    existing_array.append(pair_object)

    OUTPUT_FILE.write_text(
        json.dumps(existing_array, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    print(f"[INFO] Appended branch → combined_ads.json")


# ── main ──────────────────────────────────────────────────────────────
def main() -> None:
    pairs = get_target_pairs()
    if not pairs:
        print("[WARN] No (country, keyword) pairs supplied.")
        return

    done_pairs = load_checkpoint()

    with SB(uc=True, headless=True) as sb:
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
                print(f"[ERROR] Failed: {country} | {keyword} → {e}")

            sb.open(AD_LIBRARY_URL)
            sb.sleep(4)

        print("\n[DONE] All pairs processed – browser stays open for 3 min.")
        sb.sleep(180)

if __name__ == "__main__":
    main()
