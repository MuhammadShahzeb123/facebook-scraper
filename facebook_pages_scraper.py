#!/usr/bin/env python3
# facebook_keyword_scraper.py – v3.6  (2025-06-10)

import csv, json, re, time, unicodedata, sys, argparse, os
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import urlparse, parse_qs, unquote
from datetime import datetime

from selenium.common.exceptions import (NoSuchElementException, #type: ignore
                                       StaleElementReferenceException)#type: ignore
from selenium.webdriver.remote.webelement import WebElement #type: ignore
from selenium.webdriver.common.by import By #type: ignore
from seleniumbase import SB #type: ignore

# ═══════════════════════ USER CONFIG ══════════════════════════════════════
COOKIE_FILE   = Path("saved_cookies/facebook_cookies.txt")
KEYWORDS_FILE = Path("keywords.csv")      # keyword , pages_to_visit
HEADLESS      = True  # True / False
WAIT_SECS     = 2.0
SCROLLS       = 6        # scrolls before grabbing posts
POST_LIMIT    = 100      # number of posts to scrape per page
RETRY_LIMIT   = 2
MAX_PAGE_LINKS = 40        # hard cap (can tweak later)
ACCOUNT_NUMBER = 2          # 1 / 2 / 3  ← choose which FB account to use

# ── LOAD CONFIG FROM FILE OR COMMAND LINE ──────────────────────────────────
def load_config():
    """Load configuration from command line arguments or use defaults"""
    global SEARCH_METHOD, KEYWORDS, URLS, HEADLESS, POST_LIMIT, ACCOUNT_NUMBER

    parser = argparse.ArgumentParser(description='Facebook Pages Scraper')
    parser.add_argument('--config', type=str, help='Path to JSON config file')
    args = parser.parse_args()

    if args.config and Path(args.config).exists():
        try:
            with open(args.config, 'r') as f:
                config = json.load(f)

            SEARCH_METHOD = config.get('SEARCH_METHOD', SEARCH_METHOD)
            HEADLESS = config.get('HEADLESS', HEADLESS)
            POST_LIMIT = config.get('POST_LIMIT', POST_LIMIT)
            ACCOUNT_NUMBER = config.get('ACCOUNT_NUMBER', ACCOUNT_NUMBER)
            if 'KEYWORDS' in config:
                KEYWORDS = config['KEYWORDS']
            if 'URLS' in config:
                URLS = config['URLS']
        except Exception as e:
            print(f"[WARNING] Failed to load config file: {e}")

    # Also check environment variables as fallback
    SEARCH_METHOD = os.environ.get('SEARCH_METHOD', SEARCH_METHOD)
    HEADLESS = os.environ.get('HEADLESS', str(HEADLESS)).lower() == 'true'
    POST_LIMIT = int(os.environ.get('POST_LIMIT', POST_LIMIT))
    ACCOUNT_NUMBER = int(os.environ.get('ACCOUNT_NUMBER', ACCOUNT_NUMBER))

# ── CONTINUATION / AUTO-RESUME ──────────────────────────────────────────
CONFIG_FILE = Path("config.json")   # provides cookies-file & proxy per account
PROGRESS_FILE  = Path("progress.json")          # where we checkpoint progress
CFG_ROOT       = json.loads(CONFIG_FILE.read_text("utf-8"))
CONTINUATION = True  # or False, depending on your desired behavior
POST_RETRIES = 6          # how many times to re-extract one post

# ── SEARCH METHOD SELECTION ──────────────────────────────────────────────
SEARCH_METHOD = "url"  # "keyword" or "url"

# ── URL INPUT (when SEARCH_METHOD = "url") ─────────────────────────────────
URLS = [
    "https://www.facebook.com/CokePakistan",
    "https://www.facebook.com/pepsi",
    "https://www.facebook.com/burgerking",
]

# ── KEYWORD INPUT (when SEARCH_METHOD = "keyword") ──────────────────────────
KEYWORDS = [
    "coca cola",
    "pepsi",
    "burger king",
]

# Call load_config to initialize configuration
load_config()

# ══════════════════════════════════════════════════════════════════════════

DEBUG_DIR = Path("debug")
DEBUG_DIR.mkdir(exist_ok=True)

XP = {
    "search_box":  '//input[@placeholder="Search Facebook" and @type="search"]',
    "pages_chip":  '//span[.="Pages" or .="ページ"]/ancestor::*[@role="link" or @role="button"][1]',
    "page_links":  '//div[@role="article"]//a[contains(@href, "facebook.com")]',  # not used directly in updated code

    "about_tab":   '//span[.="About"]/ancestor::*[@role="tab" or @role="link"][1]',
    "transp_link": '//span[contains(.,"Page transparency")]/ancestor::a[1]',
    "see_all":     '//span[.="See All"]/ancestor::*[@role="button"][1]',

    "profile_g":   '//div[@role="banner"]//a[contains(@href, "facebook.com")]//svg[.//image]',
    "profile_img": '//div[@role="banner"]//a[contains(@href, "facebook.com")]//image',
    "profile_a":   '//div[@role="banner"]//a[contains(@href, "facebook.com")]',

    "intro":       [
        '//div[@data-pagelet="ProfileTilesFeed"]//span[@dir="auto"]',
        '//div[contains(text(), "We create") or contains(text(), "私たちは")]'
    ],

    # These XPaths get used inside extract_transparency
    "page_id":     '//div[contains(text(), "Page ID")]/following-sibling::div//span',
    "creation_date": '//div[contains(text(), "Creation date")]/following-sibling::div//span',
    "contact_phone": '//div[text()="Phone"]/following-sibling::div',
    "contact_email": '//div[text()="Email"]/following-sibling::div',
    "website_link": '//div[text()="Website"]/following-sibling::div//a',

    "posts_tab":   '//span[.="Posts"]/ancestor::a[1]',
}


# ───────────────────── helper functions ───────────────────────────────────

def pause(t=WAIT_SECS):
    time.sleep(t)

def _select_account() -> tuple[list, str | None, str | None, str | None]:
    """
    Returns (sanitised_cookie_list , proxy_host_port , proxy_user , proxy_pass)

    Expects config.json of the form:
    {
      "accounts": {
        "1": {
          "proxy"  : "217.67.72.152,12323,14acfa7f9a57c,74f453f102",
          "cookies": [ { …raw chrome cookie… }, … ]
        },
        "2": { … },
        "3": { … }
      }
    }
    """
    cfg  = json.loads(CONFIG_FILE.read_text("utf-8"))
    acc  = cfg["accounts"][str(ACCOUNT_NUMBER)]

    raw_cookies = acc["cookies"]
    cookies = [_sanitise_cookie(c) for c in raw_cookies]

    phost, pport, puser, ppass = acc["proxy"].split(",", 3)
    return cookies, f"{phost}:{pport}", puser, ppass

# ───────────────── cookie helpers ──────────────────
def _sanitise_cookie(c: dict) -> dict:
    """
    Make a cookie dict Selenium-compatible:
      • keep only allowed keys
      • coerce SameSite → 'Strict' | 'Lax' | 'None'
      • ensure expiry is an int  (drop if unparsable / past)
      • add default domain & path when absent
    """
    ck = c.copy()

    # ----- SameSite normalisation -----
    ss = ck.get("sameSite") or ck.get("same_site")
    if ss:
        ss = str(ss).lower()
        if ss not in ("lax", "strict", "none"):
            ck.pop("sameSite", None)
        else:
            ck["sameSite"] = ss.title()

    # ----- expiry/int coercion --------
    exp = ck.get("expiry") or ck.get("expirationDate")
    if exp:
        try:
            ck["expiry"] = int(float(exp))
        except Exception:
            ck.pop("expiry", None)
    ck.pop("expirationDate", None)

    # ----- keep only Selenium-accepted keys -----
    allowed = {
        "name", "value", "domain", "path",
        "expiry", "secure", "httpOnly", "sameSite"
    }
    ck = {k: v for k, v in ck.items() if k in allowed}

    ck.setdefault("domain", ".facebook.com")
    ck.setdefault("path",   "/")
    return ck
# ── checkpoint helpers ──────────────────────────────────────────────────
def _save_checkpoint(kw_i: int, link_i: int) -> None:
    """Write current indices to disk so we can resume after a crash."""
    if CONTINUATION:
        PROGRESS_FILE.write_text(json.dumps({
            "method": SEARCH_METHOD,
            "kw": kw_i,
            "lnk": link_i
        }))

def _load_checkpoint() -> Tuple[int, int]:
    """(kw_index , link_index) stored from previous run (0,0) if none."""
    if CONTINUATION and PROGRESS_FILE.exists():
        try:
            obj = json.loads(PROGRESS_FILE.read_text())
            # Only resume if same search method
            if obj.get("method") == SEARCH_METHOD:
                return int(obj.get("kw", 0)), int(obj.get("lnk", 0))
        except Exception:
            pass
    return 0, 0

# ── round-robin account picker ──────────────────────────────────────────
_ACCOUNT_IDS = sorted(int(k) for k in CFG_ROOT["accounts"].keys())

def _next_account(cur: int) -> int:
    idx = (_ACCOUNT_IDS.index(cur) + 1) % len(_ACCOUNT_IDS)
    return _ACCOUNT_IDS[idx]

def click_pages_filter(sb: SB):
    """Improved pages filter click with headless mode support."""
    print("Clicking Pages filter...")

    # (If we're already on the 'Pages' tab, skip.)
    try:
        active_tab = sb.find_element(
            '//*[@aria-selected="true"]//span[text()="Pages"]',
            "xpath",
            timeout=1
        )
        if active_tab:
            print("Already on Pages tab")
            return True
    except:
        pass

    for attempt in range(3):
        try:
            chip = sb.find_element(XP["pages_chip"], "xpath")
            sb.highlight(chip, 2)  # Visual indicator for debugging
            sb.execute_script(
                "arguments[0].scrollIntoView({behavior: 'instant', block: 'center'});",
                chip
            )
            pause(0.5)
            sb.execute_script("arguments[0].click();", chip)
            pause(1.5)

            try:
                active_tab = sb.find_element(
                    '//*[@aria-selected="true"]//span[text()="Pages"]',
                    "xpath",
                    timeout=3
                )
                print("Successfully switched to Pages tab")
                return True
            except:
                if sb.find_elements(
                    '//div[contains(text(), "Page results for")]',
                    "xpath"
                ):
                    print("Detected page results")
                    return True
                if sb.find_elements('//div[@role="article"]', "xpath"):
                    print("Detected result articles")
                    return True

            print("Pages tab not activated, retrying...")
        except Exception as e:
            print(f"Attempt {attempt+1} failed: {str(e)}")
            pause(1)

    # Final fallback: JavaScript click by visible text
    try:
        print("Trying text-based click...")
        sb.js_click('span:contains("Pages")')
        return True
    except Exception as e:
        print(f"Final fallback failed: {str(e)}")
        return False
# ─────────────────────────────────────────────────────────────────────────
#  avatar-finder  –  replace the old _find_profile_pic()
# ─────────────────────────────────────────────────────────────────────────
# ───────────────── profile-picture extractor ──────────────────────────
def _extract_profile_pic(sb: SB) -> str:
    """
    Return the page’s profile-picture URL.

    Logic (requested):
      • grab every <image> element
      • take its xlink:href
      • keep only URLs that contain 's200x200'
        and DO NOT contain '_nc_cat=107'
      • if several remain, use the *last* one
    """
    js = """
    const ns = "http://www.w3.org/1999/xlink";
    const urls = Array.from(document.querySelectorAll("image"))
      .map(img => img.getAttributeNS(ns, "href"))
      .filter(u => u && u.includes("s200x200") && !u.includes("_nc_cat=107"));
    return urls;               // SeleniumBase gives this back to Python
    """
    try:
        urls = sb.execute_script(js)
        if urls and isinstance(urls, list):
            return urls[-1]     # ← choose the last candidate
    except Exception as e:
        print(f"[WARN] profile-pic JS failed: {e}")

    return ""                   # nothing found / error

def extract_contact_block(sb: SB, data: dict):
    """
    Parses the About-page contact chunk and fills:
        data["about_raw"]   (entire visible text)
        data["address"] , data["mobile"] , data["email"]
        data["social_links"]   (list[str])
    """
    try:
        box = sb.find_element(
            '//*[contains(@class,"xyamay9") and contains(@class,"xsfy40s") '
            'and contains(@class,"x1gan7if") and contains(@class,"xf7dkkf")]',
            "xpath", timeout=4
        )
        raw = box.text.strip()
        # data["about_raw"] = raw

        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        lbls = {"address": "Address", "mobile": "Mobile", "email": "Email"}
        for idx, ln in enumerate(lines):
            for key, lab in lbls.items():
                if ln.lower() == lab.lower() and idx > 0:
                    data[key] = lines[idx - 1]

        # social / website links
        urls = [ln for ln in lines if ln.lower().startswith("http")]
        if urls:
            data["social_links"] = urls
    except Exception as e:
        print(f"[INFO] contact-block missing – {e}")
def get_page_links(sb: SB) -> List[WebElement]:
    """Return at most MAX_PAGE_LINKS valid page links."""
    print("Searching for page links…")
    try:
        sb.wait_for_element('//div[@role="article"]', "xpath", timeout=10)
    except:
        print("Couldn't find results container, proceeding anyway")

    # small downward nudge helps additional cards load
    for _ in range(4):
        sb.scroll_to_bottom()
        pause(1)

    selectors = [
        '//a[.//span[text()] and .//image]',
        '//div[@role="article"]//a[.//span]',
        '//a[contains(@href, "facebook.com") and .//span]',
    ]
    links: list[WebElement] = []
    for sel in selectors:
        try:
            els = sb.find_elements(sel, "xpath")
            links.extend(els)
            if links:
                break
        except Exception as e:
            print(f"Selector failed: {sel} – {e}")

    valid: list[WebElement] = []
    for el in links:
        try:
            if not el.is_displayed() or el.size["width"] <= 0:
                continue
            href = el.get_attribute("href") or ""
            if any(x in href for x in ("/groups/", "/events/", "/hashtag/",
                                       "facebook.com/stories", "facebook.com/watch")):
                continue
            txt = el.text.strip()
            if txt and len(txt) >= 2:
                valid.append(el)
        except StaleElementReferenceException:
            continue

    print(f"Total valid page links found: {len(valid)}")

    return valid[:MAX_PAGE_LINKS]          # ← cap here


def decode(url: str) -> str:
    """Unwrap Facebook redirect links (e.g. l.facebook.com/l.php?u=…)."""
    if "l.facebook.com/l.php" not in url:
        return url
    return unquote(parse_qs(urlparse(url).query).get("u", [""])[0]) or url


def slugify(s: str) -> str:
    """Convert a string to a safe filename (lowercase, dashes, ASCII)."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^\w\s-]", "", s).strip().lower()
    return re.sub(r"[-\s]+", "-", s) or "page"


def load_cookies() -> List[dict]:
    """Read cookies from disk and normalize sameSite values."""
    data = json.load(COOKIE_FILE.open())
    for ck in data:
        ss = ck.get("sameSite", "").lower()
        ck["sameSite"] = "None" if ss not in {"strict", "lax", "none"} else ss.title()
    return data


def safe_click(sb: SB, el: WebElement):
    """
    Click an element safely:
      1. Re-locate by href
      2. Attempt normal click
      3. Scroll+click via JS fallback
      4. If all fails, open its href directly
    """
    try:
        href = el.get_attribute("href")
        xpath = f'//a[@href="{href}"]'
        new_el = sb.wait_for_element(xpath, "xpath", timeout=10)
        new_el.click()
    except:
        try:
            sb.execute_script("arguments[0].scrollIntoView(true);", el)
            pause(0.5)
            el.click()
        except:
            try:
                sb.execute_script("arguments[0].click();", el)
            except Exception as e:
                print(f"Click failed: {str(e)}")
                url = el.get_attribute("href")
                if url:
                    sb.open(url)
                    pause(3)


def wait_click(sb: SB, xp: str, timeout=15):
    """Wait until an element is visible, then click it."""
    sb.wait_for_element_visible(xp, "xpath", timeout=timeout)
    sb.click(xp, "xpath")


def parse_engagement_text(text: str) -> int:
    """
    Turn strings like "1.2K", "3M", "456" into an integer.
    """
    if not text:
        return 0

    t = text.replace(",", "").lower().strip()
    multiplier = 1
    if "k" in t:
        multiplier = 1000
        t = t.replace("k", "")
    elif "m" in t:
        multiplier = 1000000
        t = t.replace("m", "")

    nums = re.findall(r"\d+", t)
    if not nums:
        return 0
    try:
        return int(nums[0]) * multiplier
    except ValueError:
        return 0


def extract_with_retry(container: WebElement, extract_func, *args, **kwargs):
    """
    Call extract_func(container, *args, **kwargs). If it throws or returns falsy,
    retry up to RETRY_LIMIT times. Return None if still no result.
    """
    for attempt in range(RETRY_LIMIT + 1):
        try:
            result = extract_func(container, *args, **kwargs)
            if result:
                return result
        except (NoSuchElementException, StaleElementReferenceException):
            if attempt < RETRY_LIMIT:
                time.sleep(0.5)
                continue
            else:
                return None
    return None


# ═════════════════════ POST EXTRACTION FUNCTIONS ══════════════════════════

def extract_caption(container: WebElement) -> str:
    """Extract post caption text via data-ad-preview or fallback classes."""
    try:
        caption_el = container.find_element(
            By.XPATH, './/div[@data-ad-preview="message"]'
        )
        if (caps := caption_el.text.strip()):
            print(f"Caption found through data-ad-preview: {caps[:50]}...")
            return caps
    except:
        pass

    try:
        caption_el = container.find_element(
            By.XPATH,
            './/div[contains(concat(" ", normalize-space(@class), " xdj266r ") '
            'and contains(concat(" ", normalize-space(@class), " x11i5rnm ") '
            'and contains(concat(" ", normalize-space(@class), " xat24cr ") '
            'and contains(concat(" ", normalize-space(@class), " x1mh8g0r ") '
            'and contains(concat(" ", normalize-space(@class), " x1vvkbs ") '
            'and contains(concat(" ", normalize-space(@class), " x126k92a ")]'
        )
        return caption_el.text.strip()
    except:
        return ""


def extract_url(container: WebElement) -> str:
    """Extract post URL/permalink (either /posts/ or /videos/)."""
    try:
        return container.find_element(
            By.XPATH,
            './/a[contains(@href, "/posts/") or contains(@href, "/videos/")][@role="link"]'
        ).get_attribute("href")
    except:
        return ""

def extract_images(container: WebElement) -> List[str]:
    """Extract any <img> whose src contains 'scontent'."""
    try:
        img_elements = container.find_elements(
            By.XPATH, './/img[contains(@src, "scontent")]'
        )
        return [img.get_attribute("src") for img in img_elements if img.get_attribute("src")]
    except:
        return []


def extract_video_url(container: WebElement) -> str:
    """Extract any <video> or <video>/source src attribute."""
    try:
        return container.find_element(By.XPATH, './/video | .//video/source').get_attribute("src")
    except:
        return ""


def extract_post_engagement(container: WebElement) -> dict:
    """
    Extract all engagement metrics from the post’s 'toolbar' (likes, comments, shares).
    """
    try:
        engagement_bar = container.find_element(
            By.XPATH,
            './/div[@role="toolbar" and contains(@aria-label, "Reactions")]'
        )
        metrics = {"likes": 0, "comments": 0, "shares": 0}

        spans = engagement_bar.find_elements(By.XPATH, './/span')
        for span in spans:
            txt = span.text.strip()
            if not txt:
                continue
            low = txt.lower()
            if "like" in low or "reaction" in low:
                metrics["likes"] = parse_engagement_text(txt)
            elif "comment" in low:
                metrics["comments"] = parse_engagement_text(txt)
            elif "share" in low:
                metrics["shares"] = parse_engagement_text(txt)
        return metrics
    except:
        return {"likes": 0, "comments": 0, "shares": 0}

def extract_post(container: WebElement) -> dict:
    """
    Extract all data from a single post container:
      · caption, url, timestamp, images, video_url
      · likes & shares (parsed from raw text)
      · comments always 0 for now
    """
    caption   = extract_with_retry(container, extract_caption) or ""
    url       = extract_with_retry(container, extract_url) or ""
    images    = extract_with_retry(container, extract_images) or []
    # video_url = extract_with_retry(container, extract_video_url) or ""

    likes, comments, shares = _extract_likes_shares_from_text(container)
    # likes  = min(likes, 10_000_000)         # safety caps
    # shares = min(shares, 1_000_000)

    return {
        "text":       caption[:500],
        "url":        url,
        "images":     images,
        # "video_url":  video_url,
        "likes":      likes,
        "comments":   comments,
        "shares":     shares,
        "scraped_at": datetime.now().isoformat()
    }

def extract_posts(sb: SB, data: dict):
    last_height = sb.driver.execute_script("return document.body.scrollHeight")
    sc = 0
    while sc < SCROLLS:
        sb.driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.8);")
        pause(2)
        h = sb.driver.execute_script("return document.body.scrollHeight")
        if h == last_height: break
        last_height, sc = h, sc + 1

    containers = sb.driver.find_elements(
        By.XPATH,
        '//div[contains(@class,"x1yztbdb") and .//div[contains(@data-ad-preview,"message")]]'
    )
    print(f"[SEARCH] Found {len(containers)} post containers")
    posts = []
    for idx, c in enumerate(containers):
        if len(posts) >= POST_LIMIT:
            break

        sb.execute_script("arguments[0].scrollIntoView({block:'center'});", c)
        pause(0.5)

        post = {}
        for _ in range(POST_RETRIES):
            post = extract_post(c)
            if post.get("url") or post.get("likes") or post.get("images") or post.get("video_url"):
                break          # got something useful
            pause(0.4)         # short pause then try again
        if idx == 0 and not any(post.get(k) for k in ("likes", "comments", "shares")):
            print("[INFO] Skipping pinned/featured post (no engagement shown yet)")
            continue
        if post.get("text") or post.get("url"):
            posts.append(post)


    data["recent_posts"] = posts
    for _ in range(SCROLLS):
        sb.execute_script("window.scrollBy(0, -document.body.scrollHeight*0.7)")
        pause(1.2)
# ═════════════════════ PAGE EXTRACTION FUNCTIONS ══════════════════════════
def extract_home(sb: SB) -> Dict:
    sb.execute_script("window.scrollTo(0,0)")
    out = {
        "name": "", "profile_pic": "", "verified": False,
        "followers": "", "likes": "", "category": "",

        "description": ""
    }

    # Name & verified
    try:
        h1 = sb.wait_for_element('//div[@role="main"]//h1', "xpath", timeout=4)
        out["name"] = h1.text.strip()
        out["verified"] = bool(
            h1.find_elements(By.XPATH, './/svg[@title="Verified account"]'))
    except: pass

    # Profile-picture  (single helper covers all cases)
    out["profile_pic"] = _extract_profile_pic(sb)


    # Followers / Likes   (regex over page-source)
    src = sb.get_page_source()
    m = re.search(r'([0-9.,]+[A-Za-z万億]*)\s+likes?', src, re.I)
    if m: out["likes"] = m.group(1).replace(" ", "")
    m = re.search(r'([0-9.,]+[A-Za-z万億]*)\s+(followers?|フォロワー)', src, re.I)
    if m: out["followers"] = m.group(1).replace(" ", "")

    # Category
    try:
        cat = sb.find_element(
            '//span[./strong[text()="Page" or text()="ページ"]]', "xpath").text
        out["category"] = (
            cat.split("·", 1)[-1].strip() if "·" in cat else cat.strip("ページ").strip()
        )
    except: pass

    # # Out-links & website
    # for a in sb.find_elements('//a[starts-with(@href,"http")]', "xpath"):
    #     href = decode(a.get_attribute("href"))
    #     if href.startswith("http"):
    #         if not out["website"] and "facebook.com" not in href:
    #             out["website"] = href
    #         out["links"].append(href)
    # out["links"] = list(dict.fromkeys(out["links"]))

    # Intro-block parsing  → description & website-label
    blobs = get_texts_by_class(sb, "x193iq5w")
    desc, wlabel = _parse_intro_and_website(blobs)
    if desc:   out["description"]   = desc
    if wlabel: out["website_label"] = wlabel

    return out
# ── NEW ────────────────────────────────────────────────────────────────────
def _extract_likes_shares_from_text(container: WebElement) -> tuple[str,str,str]:
    """
    Robustly pull “likes / comments / shares” from *any* post, including
    pinned/featured ones where Facebook inserts a newline between every char.
    Returns the raw strings exactly as they appear on the UI.
    """
    # 1️⃣ Get the raw text and squash weird spacing
    raw = container.text.replace("\n", " ").replace("  ", " ")

    # 2️⃣ Do a fast bailout – if the keywords aren’t there, try forcing
    #     the toolbar to load by scrolling the element into view once.
    if "Like" not in raw and "Comment" not in raw and "Share" not in raw:
        container.parent.execute_script(
            "arguments[0].scrollIntoView({block:'center'});", container)
        time.sleep(0.4)
        raw = container.text.replace("\n", " ").replace("  ", " ")

    # 3️⃣ Regexes that survive most language variants
    like_pat     = r'All reactions:\s*([0-9.,KkMm]+)|([0-9.,KkMm]+)\s+Like'
    comment_pat  = r'([0-9.,KkMm]+)\s+Comment'
    share_pat    = r'([0-9.,KkMm]+)\s+Share'

    likes    = next((g for g in re.findall(like_pat, raw) if any(g)), ('',''))[0] or ''
    comments = _first_group(raw, comment_pat)
    shares   = _first_group(raw, share_pat)

    return likes, comments, shares


def _first_group(text, pat):
    m = re.search(pat, text, re.I)
    return m.group(1) if m else ''

def extract_intro(sb: SB, data: Dict):
    """
    If fetch_front_description didn't catch anything,
    try each fallback XPath in XP["intro"].
    """
    if data.get("description"):
        return

    for fxp in XP["intro"]:
        try:
            desc_el = sb.find_element(fxp, "xpath", timeout=2)
            dtext = desc_el.text.strip()
            if dtext and len(dtext) > 20:
                data["description"] = dtext
                return
        except:
            continue
    data["description"] = ""


def extract_transparency(sb: SB, data: Dict):
    """
    1) Click About → Page Transparency → See All
    2) Scrape the modal’s text to fill:
       - data["page_id"]
       - data["created_date"]
       - data["admin_countries"]
       - data["name_changes"]
       - data["is_running_ads"]
       - data["transparency_raw"]
    3) Close the modal
    """
    try:
        # 1) Click About (if present)
        # try:
        #     wait_click(sb, XP["about_tab"])
        #     pause(1)
        # except:
        #     pass
        # 2) Click Page Transparency
        wait_click(sb, XP["transp_link"])
        pause(1)
        try:
            # Try the specific XPath provided by the user
            page_id_element = sb.find_element(
                '/html/body/div[1]/div/div[1]/div/div[3]/div/div/div[2]/div[1]/div/div/div[4]/div/div/div/div[1]/div/div/div/div/div[2]/div/div/div/div/div[2]/div/div/div[2]/div[1]/span',
                "xpath",
                timeout=3
            )
            page_id_text = page_id_element.text.strip()
            if re.fullmatch(r'\d{10,}', page_id_text):
                data["page_id"] = page_id_text
        except:
            # Fallback to other methods if specific XPath fails
            try:
                # Try the alternative XPath format
                page_id_element = sb.find_element(
                    '//*[contains(@id, "mount_")]/div/div[1]/div/div[3]/div/div/div[2]/div[1]/div/div/div[4]/div/div/div/div[1]/div/div/div/div/div[2]/div/div/div/div/div[2]/div/div/div[2]/div[1]/span',
                    "xpath",
                    timeout=2
                )
                page_id_text = page_id_element.text.strip()
                if re.fullmatch(r'\d{10,}', page_id_text):
                    data["page_id"] = page_id_text
            except:
                # Try pattern matching in text
                try:
                    modal = sb.find_element('//div[@role="dialog"]', "xpath", timeout=5)
                    transparency_text = modal.text

                    # Look for long digit string near "Page ID"
                    pid_match = re.search(r'Page ID\D*(\d{10,})', transparency_text)
                    if pid_match:
                        data["page_id"] = pid_match.group(1)
                    else:
                        # Look for any long digit string in the text
                        numbers = re.findall(r'\d{10,}', transparency_text)
                        if numbers:
                            data["page_id"] = numbers[0]
                except:
                    pass


        see_all_xpath = (
            '//span[contains(translate(normalize-space(.), "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "see all")]/ancestor::*[@role="button"][1]'
        )
        try:
            btn = sb.wait_for_element(see_all_xpath, "xpath", timeout=5)
            # Scroll it into view
            sb.execute_script("arguments[0].scrollIntoView({behavior:'instant', block:'center'});", btn)
            pause(0.5)
            btn.click()
            pause(1)
            print("[OK] Clicked See All")
        except Exception as e:
            print(f"[WARN] ‘See All’ button not found or clickable: {e}")
        for _ in range(2):                      # click/parse up to 2 times
            transparency_text = ""              # reset each round

        # 5) Now parse the raw admin info in the modal for dates, countries, name changes, ads, etc.
        try:
            admin_texts = sb.find_elements(
                '//span[text()="Admin info"]/ancestor::div[contains(@class,"x9f619")]//span[position()=1]',
                "xpath"
            )
            transparency_text = "\n".join([t.text for t in admin_texts if t.text])
            # data["transparency_raw"] = transparency_text
            # modal = sb.find_element('//div[@role="dialog"]', "xpath", timeout=5)
            # raw   = modal.text
            # Page ID (again, just in case)
            m1 = re.search(r'Page ID[^\d]*(\d{10,})', transparency_text)
            if m1:
                data["page_id"] = m1.group(1)

            # Creation date
            cd = ""
            match_cd = re.search(r'(?:Created|Creation date)[^\n]*\n\D*(\d{1,2}\s+[A-Za-z]+\s+\d{4})', transparency_text)
            if match_cd:
                cd = match_cd.group(1)
            else:
                dm = re.search(r'Creation date[^\n]*\n\D*(\d{1,2}\s+[A-Za-z]+\s+\d{4})', transparency_text)
                if not dm:
                    dm = re.search(r'Created[^\n]*\n\D*(\d{1,2}\s+[A-Za-z]+\s+\d{4})', transparency_text)
                if dm:
                    cd = dm.group(1)

            if cd:
                data["created_date"] = cd

            # Admin countries
            cm = re.search(r'Primary country/region[^\n]*\n((?:\s*[\w\s]+\(\d+\)\n?)+)', transparency_text)
            if cm:
                countries = re.findall(r'[\w\s]+\(\d+\)', cm.group(1))
                data["admin_countries"] = [c.strip() for c in countries]

            # -------- refined NAME-CHANGE counter -----------------------------
            changes = []
            for line in transparency_text.splitlines():
                if line.lower().startswith("changed name to "):
                    new_name = line[15:].strip()           # len("Changed name to ")
                    # ignore if empty OR looks like a date
                    if new_name and not re.match(r'\d{1,2}\s+\w+\s+\d{4}', new_name):
                        changes.append(new_name)
            data["name_changes"]      = len(changes)
            data["name_change_lines"] = changes        # ← new field

            # Ads flag & Verified fallback
            data["is_running_ads"] = ("currently running ads" in transparency_text.lower())
            if "verified" in transparency_text:
                data["verified"] = True
            # ------ likes / followers (override home-page regex if present) ------
            likes_str, foll_str = _parse_likes_followers_from_transparency(transparency_text)
            if likes_str:
                data["likes"] = likes_str
            if foll_str:
                data["followers"] = foll_str

        except Exception as e:
            print(f"[WARN] Transparency modal parsing failed: {str(e)}")

        # 6) Close the modal
        try:
            close_btn = sb.find_element(
                '//div[@role="dialog"]//*[@aria-label="Close"]',
                "xpath"
            )
            close_btn.click()
            pause(0.5)
        except:
            pass

    except Exception as e:
        print(f"[ERROR] extract_transparency(): {str(e)}")

# ─────────────────────────────────────────────────────────────────────────────
#  helper functions to “fetch all visible text” under certain XPaths or classes
# ─────────────────────────────────────────────────────────────────────────────

def get_texts_by_xpath(sb: SB, xpath: str) -> list:
    """
    Find all elements matching the given XPath, return a list of their text contents (stripped).
    If none are found, returns an empty list.
    Usage:
        texts = get_texts_by_xpath(sb, '//div[@class="x193iq5w"]//span')
        print(texts)
    """
    try:
        elements = sb.find_elements(xpath, "xpath")
    except Exception:
        return []
    results = []
    for el in elements:
        try:
            txt = el.text.strip()
            if txt:
                results.append(txt)
        except Exception:
            continue
    return results

def _parse_likes_followers_from_transparency(raw: str) -> tuple[str, str]:
    """
    Extract the first “### likes” and “### followers” tokens from the
    raw transparency text. Returns (likes_str, followers_str) – either
    may be empty if not found.
    """
    likes = followers = ""
    m = re.search(r'([0-9.,KkMm]+)\s+likes?', raw)
    if m:
        likes = m.group(1)
    m = re.search(r'([0-9.,KkMm]+)\s+followers?', raw)
    if m:
        followers = m.group(1)
    return likes, followers
# ── NEW ────────────────────────────────────────────────────────────────────
def _parse_intro_and_website(text_blobs: list[str]) -> tuple[str, str]:
    """
    Given a *flat* list of visible texts (e.g. class `x193iq5w`),
    return  ➜ ( description , website_label )

    • description  – the first line that comes *immediately* after the literal
      'Intro' line, cut off at the first “\\n” or when the line starts with
      'Page ·'  (category) – exactly the slice the user asked for.

    • website_label – the first token that *looks like* a domain, i.e. it
      contains at least one dot and no whitespace.
    """
    desc = ""
    website_label = ""

    # --- DESCRIPTION ------------------------------------------------------
    try:
        i = text_blobs.index("Intro")
        if i + 1 < len(text_blobs):
            nxt = text_blobs[i + 1].split("\n", 1)[0]          # keep text up to 1st \n
            if not nxt.startswith("Page ·"):                   # ignore category line
                desc = nxt.strip()
    except ValueError:
        pass                                                   # no 'Intro' found

    # --- WEBSITE LABEL ----------------------------------------------------
    for t in text_blobs:
        if "." in t and " " not in t and "\n" not in t:        # simple domain heuristic
            website_label = t.strip()
            break

    return desc, website_label


def get_texts_by_class(sb: SB, class_name: str) -> list:
    """
    Find all elements having the given CSS class (exact match in the @class string),
    return a list of their text contents (stripped). If none, returns [].
    Usage:
        texts = get_texts_by_class(sb, 'x193iq5w')  # all <… class="x193iq5w …">
        print(texts)
    """
    try:
        elements = sb.find_elements(
            f'//*[contains(concat(" ", normalize-space(@class), " "), " {class_name} ")]',
            "xpath"
        )
    except Exception:
        return []
    results = []
    for el in elements:
        try:
            txt = el.text.strip()
            if txt:
                results.append(txt)
        except Exception:
            continue
    return results


def get_all_attribute_values(sb: SB, xpath: str, attribute: str) -> list:
    """
    Find all elements matching the given XPath, collect the specified attribute (e.g. 'href' or 'src').
    Returns a list of non-empty attribute strings. If none, returns [].
    Usage:
        hrefs = get_all_attribute_values(sb, '//a[contains(@href, "facebook.com")]', 'href')
        print(hrefs)
    """
    try:
        elements = sb.find_elements(xpath, "xpath")
    except Exception:
        return []
    results = []
    for el in elements:
        try:
            val = el.get_attribute(attribute)
            if val:
                results.append(val.strip())
        except Exception:
            continue
    return results

# ───────────────────── scrape_one_page ───────────────────────────────────
AGG_FILE = Path("Results/all_pages.json")
# ───────────────────────── main loop ──────────────────────────────────────
def scrape_one_page(sb: SB, link_el: WebElement, save_dir: Path, kw_i: int, link_i: int, serp_avatar: str = ""):
    # Get the page URL from the link element
    page_url = link_el.get_attribute("href")

    safe_click(sb, link_el); pause(5)
    class_texts = get_texts_by_class(sb, 'x193iq5w')
    # Grab fallback description under data-pagelet="ProfileTilesFeed"
    desc_fallback = get_texts_by_xpath(sb, '//div[@data-pagelet="ProfileTilesFeed"]//span[@dir="auto"]')
    description = ""
    for t in class_texts + desc_fallback:
        if t.startswith("Intro"):
            parts = t.split("\n", 1)
            if len(parts) == 2:
                # take text up to next newline or category dot
                desc_line = parts[1].split("\n")[0].strip()
                description = desc_line
                break
    data = extract_home(sb)
    data["page_url"] = page_url  # Add the page URL to results
    if not data.get("profile_pic") and serp_avatar:
        data["profile_pic"] = serp_avatar
    if description:
        data["description"] = description
    extract_posts(sb, data)

    try:
        wait_click(sb, XP["about_tab"]); pause(1)
        extract_contact_block(sb, data)
    except:
        pass

    extract_transparency(sb, data)

    # append to a single running file
    AGG_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        blob = json.loads(AGG_FILE.read_text("utf-8"))
        if not isinstance(blob, list):
            blob = []
    except FileNotFoundError:
        blob = []
    blob.append(data)
    AGG_FILE.write_text(
    json.dumps(blob, indent=2, ensure_ascii=False),
    encoding="utf-8"
)

    print(f"[OK] appended to {AGG_FILE}")
    _save_checkpoint(kw_i, link_i + 1)   # mark the next link as pending    sb.driver.back(); sb.driver.back(); pause(1)

def scrape_from_urls(sb: SB, urls: List[str], url_start: int = 0):
    """
    Scrape Facebook pages directly from a list of URLs.

    Args:
        sb: SeleniumBase instance
        urls: List of Facebook page URLs to scrape
        url_start: Starting index for resuming (from checkpoint)
    """
    print(f"\n=== SCRAPING {len(urls)} PAGES FROM URLs ===")

    for url_i, url in enumerate(urls):
        if url_i < url_start:  # Skip already processed URLs
            continue

        print(f"\n--- Processing URL {url_i + 1}/{len(urls)}: {url} ---")

        try:
            # Save checkpoint before processing each URL
            _save_checkpoint(url_i, 0)

            # Navigate directly to the page
            sb.open(url)
            pause(3)

            # Check if page loaded successfully
            if "facebook.com" not in sb.get_current_url().lower():
                print(f"[ERROR] Failed to load page: {url}")
                continue

            # Check for page not found or access denied
            if any(text in sb.get_page_source().lower() for text in [
                "this content isn't available",
                "page not found",
                "content not found",
                "sorry, this page isn't available"
            ]):
                print(f"[ERROR] Page not accessible: {url}")
                continue

            # Extract data from the page
            class_texts = get_texts_by_class(sb, 'x193iq5w')
            desc_fallback = get_texts_by_xpath(sb, '//div[@data-pagelet="ProfileTilesFeed"]//span[@dir="auto"]')
            description = ""
            for t in class_texts + desc_fallback:
                if t.startswith("Intro"):
                    parts = t.split("\n", 1)
                    if len(parts) == 2:
                        desc_line = parts[1].split("\n")[0].strip()
                        description = desc_line
                        break

            # Extract home page data
            data = extract_home(sb)
            data["page_url"] = url  # Add the page URL to results
            if description:
                data["description"] = description

            # Add source URL to data
            data["source_url"] = url
            data["scrape_method"] = "url"

            # Extract posts
            extract_posts(sb, data)

            # Try to get About page info
            try:
                wait_click(sb, XP["about_tab"])
                pause(1)
                extract_contact_block(sb, data)
            except:
                pass

            # Extract transparency info
            extract_transparency(sb, data)

            # Save to aggregated file
            AGG_FILE.parent.mkdir(parents=True, exist_ok=True)
            try:
                blob = json.loads(AGG_FILE.read_text("utf-8"))
                if not isinstance(blob, list):
                    blob = []
            except FileNotFoundError:
                blob = []

            blob.append(data)
            AGG_FILE.write_text(
                json.dumps(blob, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )

            print(f"[OK] Successfully scraped and saved: {data.get('name', 'Unknown Page')}")

        except Exception as e:
            print(f"[ERROR] Failed to scrape {url}: {str(e)}")
            continue

    print("\n=== URL SCRAPING COMPLETED ===")

def main():
    global ACCOUNT_NUMBER

    kw_start, link_start = _load_checkpoint()   # ← where we left off

    print(f"=== FACEBOOK SCRAPER STARTING ===")
    print(f"Search Method: {SEARCH_METHOD.upper()}")

    if SEARCH_METHOD.lower() == "url":
        print(f"URLs to scrape: {len(URLS)}")
        if kw_start > 0:
            print(f"Resuming from URL index: {kw_start}")
    else:
        print(f"Keywords to search: {len(KEYWORDS)}")
        if kw_start > 0:
            print(f"Resuming from keyword index: {kw_start}, link index: {link_start}")

    while True:                                 # keeps trying new accounts
        try:
            # (re-select cookies & proxy for whichever account we’re on)
            cookies, proxy_hp, proxy_user, proxy_pass = _select_account()
            proxy_string = (
                f"{proxy_user}:{proxy_pass}@{proxy_hp}"
                if proxy_user and proxy_pass else proxy_hp
            )

            with SB(headless=HEADLESS, proxy=proxy_string) as sb:
                sb.open("https://facebook.com")
                for ck in cookies:
                    try:
                        # Fix sameSite attribute if it's invalid
                        if 'sameSite' in ck and ck['sameSite'] not in ["Strict", "Lax", "None"]:
                            ck['sameSite'] = "Lax"  # Default to Lax if invalid
                        sb.driver.add_cookie(ck)
                    except Exception as e:
                        print(f"[cookie error] {ck.get('name')} → {e}")
                sb.refresh(); pause(2)

                # Choose scraping method based on SEARCH_METHOD
                if SEARCH_METHOD.lower() == "url":
                    # Direct URL scraping
                    scrape_from_urls(sb, URLS, kw_start)

                else:
                    # Keyword-based search scraping (existing logic)
                    for kw_i, kw in enumerate(KEYWORDS):
                        if kw_i < kw_start:                 # skip done keywords
                            continue

                        print(f"\n=== {kw!r} ===")
                        wait_click(sb, XP["search_box"])
                        sb.type(XP["search_box"], kw + "\n", "xpath")
                        pause(2)
                        wait_click(sb, XP["pages_chip"]); pause(1.5)

                        if not click_pages_filter(sb):
                            print(f"[ERROR] Pages filter failed for {kw}")
                            continue

                        link_elements = get_page_links(sb)
                        if not link_elements:
                            print("[WARN] No valid page links found")
                            continue

                        for link_i, el in enumerate(link_elements):
                            # resume inside the keyword if needed
                            if kw_i == kw_start and link_i < link_start:
                                continue

                            _save_checkpoint(kw_i, link_i)       # 🔑 save
                            avatar = _extract_profile_pic(sb) or ""
                            print(f"\n--- Processing link {link_i + 1}/{len(link_elements)}: {el.text} ---")

                            scrape_one_page(sb, el, Path("scraped_pages"), kw_i, link_i, avatar)


                        # finished this keyword – next restart should begin fresh
                        _save_checkpoint(kw_i + 1, 0)

                        sb.open("https://facebook.com"); pause(1)

                # 🎉 success – wipe checkpoint & exit outer while
                if CONTINUATION and PROGRESS_FILE.exists():
                    PROGRESS_FILE.unlink()
                print("\n=== SCRAPING COMPLETED SUCCESSFULLY ===")
                break

        except Exception as e:
            print(f"[CRASH] Account {ACCOUNT_NUMBER} died -> {e}")
            ACCOUNT_NUMBER = _next_account(ACCOUNT_NUMBER)
            kw_start, link_start = _load_checkpoint()
            print(f"[INFO] Switching to account {ACCOUNT_NUMBER} "
                  f"& resuming kw={kw_start} link={link_start}")
            time.sleep(5)         # brief cool-down before retry
            continue


if __name__ == "__main__":
    main()