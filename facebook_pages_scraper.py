#!/usr/bin/env python3
# facebook_keyword_scraper.py – v3.6  (2025-06-10)

import csv, json, re, time, unicodedata, sys
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import urlparse, parse_qs, unquote
from datetime import datetime

from selenium.common.exceptions import (NoSuchElementException,
                                       StaleElementReferenceException)
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.common.by import By
from seleniumbase import SB

# ═══════════════════════ USER CONFIG ══════════════════════════════════════
COOKIE_FILE   = Path("saved_cookies/facebook_cookies.txt")
KEYWORDS_FILE = Path("keywords.csv")      # keyword , pages_to_visit
HEADLESS      = True
WAIT_SECS     = 2.0
SCROLLS       = 3        # scrolls before grabbing posts
POST_LIMIT    = 100      # number of posts to scrape per page
RETRY_LIMIT   = 2
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


def get_page_links(sb: SB) -> List[WebElement]:
    """Get page links with headless-friendly waiting and improved filtering."""
    print("Searching for page links...")
    try:
        sb.wait_for_element('//div[@role="article"]', "xpath", timeout=10)
    except:
        print("Couldn't find results container, proceeding anyway")

    # Scroll down a bit to load more
    for _ in range(2):
        sb.scroll_to_bottom()
        pause(1)

    selectors = [
        '//a[.//span[text()] and .//image]',                # Links with text + image
        '//div[@role="article"]//a[.//span]',                # Any link with text in article
        '//a[contains(@href, "facebook.com") and .//span]',  # Any FB link with text
    ]

    links = []
    for selector in selectors:
        try:
            elements = sb.find_elements(selector, "xpath")
            print(f"Found {len(elements)} elements with selector: {selector}")
            links.extend(elements)
            if links:
                break
        except Exception as e:
            print(f"Selector failed: {selector} - {str(e)}")

    valid_links = []
    for el in links:
        try:
            if not el.is_displayed() or el.size["width"] <= 0:
                continue

            href = el.get_attribute("href")
            if not href:
                continue

            # Skip non-page URLs
            if any(x in href for x in (
                "/groups/", "/events/", "/hashtag/",
                "facebook.com/stories", "facebook.com/watch"
            )):
                continue

            text = el.text.strip()
            if not text or len(text) < 2:
                continue

            valid_links.append(el)
            print(f"Found page link: {text[:50]} – {href[:50]}...")
        except StaleElementReferenceException:
            continue

    print(f"Total valid page links found: {len(valid_links)}")
    return valid_links


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


def extract_timestamp(container: WebElement) -> str:
    """Extract post timestamp via aria-label or fallback class combos."""
    try:
        timestamp = container.find_element(
            By.XPATH,
            './/a[contains(@href, "permalink")]//abbr | .//abbr[contains(@class, "xt0psk2")]'
        ).get_attribute("aria-label")
        if timestamp:
            return timestamp
    except:
        pass

    try:
        timestamp_el = container.find_element(
            By.XPATH,
            './/span[contains(concat(" ", normalize-space(@class), " x1rg5ohu ") '
            'and contains(concat(" ", normalize-space(@class), " x6ikm8r ") '
            'and contains(concat(" ", normalize-space(@class), " x10wlt62 ") '
            'and contains(concat(" ", normalize-space(@class), " x16dsc37 ") '
            'and contains(concat(" ", normalize-space(@class), " xt0b8zv ")]'
        )
        return timestamp_el.get_attribute("aria-label")
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


def extract_post_reactions(container: WebElement) -> int:
    """
    Given a single post container, find the “Reactions” number:
      1. <div data-ad-preview="reactions"> → parse text
      2. fallback: any <span> whose aria-label contains 'reaction(s)'
    """
    try:
        react_el = container.find_element(
            By.XPATH, './/div[@data-ad-preview="reactions"]'
        )
        raw_text = react_el.text.strip()
        return parse_engagement_text(raw_text)
    except:
        try:
            fallback_el = container.find_element(
                By.XPATH,
                './/span[contains(@aria-label, "reaction") or contains(@aria-label, "Reactions")]'
            )
            raw_text = fallback_el.text.strip()
            return parse_engagement_text(raw_text)
        except:
            return 0


def extract_post_shares(container: WebElement) -> int:
    """
    Given a single post container, find the “Shares” number:
      1. <div data-ad-preview="shares"> → parse text
      2. fallback: look for <span> containing “Share”/“Shares” → preceding-sibling::span
    """
    try:
        shares_el = container.find_element(
            By.XPATH, './/div[@data-ad-preview="shares"]'
        )
        raw_text = shares_el.text.strip()
        return parse_engagement_text(raw_text)
    except:
        try:
            fallback_el = container.find_element(
                By.XPATH,
                './/span[contains(text(), "Share") or contains(text(), "Shares")]'
            )
            sib = fallback_el.find_element(By.XPATH, './preceding-sibling::span[1]')
            raw_text = sib.text.strip()
            return parse_engagement_text(raw_text)
        except:
            return 0


def extract_post(container: WebElement) -> dict:
    """
    Extract all data from a single post container:
      - caption, url, timestamp, images, video_url
      - engagement metrics: likes, comments, shares
    """
    caption   = extract_with_retry(container, extract_caption) or ""
    url       = extract_with_retry(container, extract_url) or ""
    timestamp = extract_with_retry(container, extract_timestamp) or ""
    images    = extract_with_retry(container, extract_images) or []
    video_url = extract_with_retry(container, extract_video_url) or ""

    likes    = extract_post_reactions(container)
    comments = extract_with_retry(container, extract_post_engagement).get("comments", 0) if extract_with_retry(container, extract_post_engagement) else 0
    shares   = extract_post_shares(container)

    # Cap maxima just in case
    likes    = min(likes, 10000000)
    comments = min(comments, 1000000)
    shares   = min(shares, 1000000)

    return {
        "text":      caption[:500] if caption else "",
        "url":       url,
        "timestamp": timestamp,
        "images":    images,
        "video_url": video_url,
        "likes":     likes,
        "comments":  comments,
        "shares":    shares,
        "scraped_at": datetime.now().isoformat()
    }


def extract_posts(sb: SB, data: dict):
    """Extract up to POST_LIMIT recent posts from the current page."""
    # (We are not re-clicking "Posts"—you already land on the main feed.)
    last_height = sb.driver.execute_script("return document.body.scrollHeight")
    scroll_count = 0

    while scroll_count < SCROLLS:
        sb.driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.8);")
        pause(2)

        new_height = sb.driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height
        scroll_count += 1

    try:
        containers = sb.driver.find_elements(
            By.XPATH,
            '//div[contains(@class, "x1yztbdb") and .//div[contains(@data-ad-preview, "message")]]'
        )
        print(f"🔍 Found {len(containers)} post containers")
    except Exception as e:
        print(f"❌ Error finding post containers: {str(e)}")
        return

    posts = []
    for i, container in enumerate(containers):
        if len(posts) >= POST_LIMIT:
            break

        try:
            sb.execute_script(
                "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});",
                container
            )
            pause(0.5)

            post = extract_post(container)
            # If either text or URL is present, count it
            if post.get("text") or post.get("url"):
                posts.append(post)
                print(f"✅ Extracted post {len(posts)}/{POST_LIMIT}")
        except Exception as e:
            print(f"❌ Error processing post container {i+1}: {str(e)}")

    data["recent_posts"] = posts
    for _ in range(SCROLLS):
        sb.execute_script("window.scrollBy(0, -document.body.scrollHeight*0.7)")
        pause(1.2)


# ═════════════════════ PAGE EXTRACTION FUNCTIONS ══════════════════════════

def extract_home(sb: SB) -> Dict:
    """
    Extract basic page information from the top of the page:
      - name, profile_pic, verified, followers, likes, category, website, links
    """
    sb.execute_script("window.scrollTo(0,0)")

    out = {
        "name":         "",
        "profile_pic":  "",
        "verified":     False,
        "followers":    "",
        "likes":        "",
        "category":     "",
        "website":      "",
        "links":        [],
        "description":  "",
        "contact_phone": "",
        "contact_email": ""
    }

    # — Name & Verified —
    try:
        h1 = sb.wait_for_element('//div[@role="main"]//h1', "xpath", timeout=4)
        out["name"] = h1.text.strip()
        out["verified"] = bool(
            h1.find_elements(By.XPATH, './/svg[@title="Verified account"]')
        )
    except:
        pass

    # — Profile Picture (3 fallbacks) —
    try:
        img = sb.find_element(
            '//img[contains(@src, "profile") or contains(@src, "fbcdn")]', 
            "xpath",
            timeout=3
        )
        out["profile_pic"] = img.get_attribute("src") or ""
    except:
        try:
            img = sb.find_element(XP["profile_img"], "xpath", timeout=3)
            out["profile_pic"] = (
                img.get_attribute("xlink:href") or img.get_attribute("href") or ""
            )
        except:
            try:
                link = sb.find_element(XP["profile_a"], "xpath", timeout=3)
                style = link.get_attribute("style")
                if style and "url(" in style:
                    match = re.search(r'url\("?(https://[^")]+)"?\)', style)
                    if match:
                        out["profile_pic"] = match.group(1)
            except:
                out["profile_pic"] = ""

    # — Followers / Likes (regex over page source) —
    src = sb.get_page_source()
    m = re.search(r'([0-9.,]+[A-Za-z万億]*)\s+likes?', src, re.I)
    if m:
        out["likes"] = m.group(1).replace(" ", "")
    m = re.search(r'([0-9.,]+[A-Za-z万億]*)\s+(followers?|フォロワー)', src, re.I)
    if m:
        out["followers"] = m.group(1).replace(" ", "")

    # — Category —
    try:
        cat = sb.find_element(
            '//span[./strong[text()="Page" or text()="ページ"]]', "xpath"
        ).text
        if "·" in cat:
            out["category"] = cat.split("·", 1)[1].strip()
        else:
            out["category"] = cat.replace("ページ", "").strip()
    except:
        pass

    # — Collect all <a href="http..."> links, dedupe, and store in out["links"].
    for a in sb.find_elements('//a[starts-with(@href,"http")]', "xpath"):
        href = decode(a.get_attribute("href"))
        if href.startswith("http"):
            if not out["website"] and "facebook.com" not in href:
                out["website"] = href
            out["links"].append(href)

    out["links"] = list(dict.fromkeys(out["links"]))
    return out


def fetch_front_description(sb: SB) -> str:
    """
    1) Try the exact XPath you provided for the <span> containing the "description" text.
    2) If that fails, look for any <span> under data-pagelet="ProfileTilesFeed" with dir="auto".
    """
    # First: the exact, deep absolute XPath (from your snippet).
    try:
        DESC_XPATH = (
            "/html/body/div[1]/div/div[1]/div/div[3]/div/div/div[1]/"
            "div[1]/div/div/div[4]/div[2]/div/div[1]/div[2]/div/"
            "div[1]/div/div/div/div/div[2]/div[1]/div/div/span"
        )
        desc_el = sb.find_element(DESC_XPATH, "xpath", timeout=3)
        txt = desc_el.text.strip()
        if txt:
            return txt
    except:
        pass

    # Fallback: anything under data-pagelet="ProfileTilesFeed" that has dir="auto"
    try:
        fallback = sb.find_element(
            '//div[@data-pagelet="ProfileTilesFeed"]//span[@dir="auto"]',
            "xpath",
            timeout=3
        )
        txt2 = fallback.text.strip()
        return txt2
    except:
        return ""


def fetch_website_name(sb: SB, all_links: List[str]) -> str:
    """
    Among all_links, pick the first href that:
      - doesn’t contain "facebook.com"
      - doesn’t contain "api.whatsapp.com"
    Then look up its child <span> to get the visible label (e.g. "coca-cola.com.pk").
    """
    candidate = None
    for href in all_links:
        if "facebook.com" not in href and "api.whatsapp.com" not in href:
            candidate = href
            break
    if not candidate:
        return ""

    # Now find <a href="{candidate}">//span</span> and return its text
    try:
        # Use normalize-space() around the @href to avoid stray quotes/encoding issues
        xpath = f'//a[@href="{candidate}"]//span'
        el = sb.find_element(xpath, "xpath", timeout=3)
        return el.text.strip()
    except:
        return ""


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
        try:
            wait_click(sb, XP["about_tab"])
            pause(1)
        except:
            pass

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
                        

        # 4) Click “See All” (if present)
        try:
            wait_click(sb, XP["see_all"], timeout=4)
            pause(1)
        except:
            pass

        # 5) Now parse the raw admin info in the modal for dates, countries, name changes, ads, etc.
        try:
            admin_texts = sb.find_elements(
                '//span[text()="Admin info"]/ancestor::div[contains(@class,"x9f619")]//span[position()=1]',
                "xpath"
            )
            transparency_text = "\n".join([t.text for t in admin_texts if t.text])
            data["transparency_raw"] = transparency_text

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

            # Name changes
            name_changes = re.findall(
                r'(?m)^Changed name to\s+[^\n]+',
                transparency_text,
                re.IGNORECASE
            )
            data["name_changes"] = len(name_changes)

            # Ads flag & Verified fallback
            data["is_running_ads"] = ("currently running ads" in transparency_text.lower())
            if "verified" in transparency_text:
                data["verified"] = True

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

def scrape_one_page(sb: SB, link_el, save_dir: Path):
    # 1) Click into the page
    safe_click(sb, link_el)
    pause(5)

    # ───────────────────────────────────────────────────────────────────────────
    # 2) “Dump everything” from the XPaths & classes you mentioned, so you can inspect:
    # ───────────────────────────────────────────────────────────────────────────
    print("\n────────── DEBUG: Grab all text under the 'description' XPaths ──────────")
    # (a) the absolute XPath you gave for the <span> containing description—
    #     if it actually exists, you’ll see it here. Otherwise, list is empty.
    desc_texts_exact = get_texts_by_xpath(
        sb,
        '/html/body/div[1]/div/div[1]/div/div[3]/div/div/div[1]/'
        'div[1]/div/div/div[4]/div[2]/div/div[1]/div[2]/div/'
        'div[1]/div/div/div/div/div[2]/div[1]/div/div/span'
    )
    print("  desc_texts_exact (len={}):".format(len(desc_texts_exact)), desc_texts_exact)

    # (b) fallback: under data-pagelet="ProfileTilesFeed" any <span dir="auto">
    desc_texts_fallback = get_texts_by_xpath(
        sb,
        '//div[@data-pagelet="ProfileTilesFeed"]//span[@dir="auto"]'
    )
    print("  desc_texts_fallback (len={}):".format(len(desc_texts_fallback)), desc_texts_fallback)

    print("\n────────── DEBUG: All <span> with class='x193iq5w' (often site‐name) ──────────")
    class_texts_x193iq5w = get_texts_by_class(sb, 'x193iq5w')
    print("  class_texts_x193iq5w (len={}):".format(len(class_texts_x193iq5w)), class_texts_x193iq5w)

    print("\n────────── DEBUG: All <a href=‘http…’ → span text (likely website labels) ──────────")
    # If you want to see which <a> tags have a child <span> (visible label),
    # you can grab all spans under all <a> on the page:
    all_anchor_spans = get_texts_by_xpath(sb, '//a//span')
    print("  all_anchor_spans (len={}):".format(len(all_anchor_spans)), all_anchor_spans[:20], "…")

    print("\n────────── DEBUG: All 'href' attributes of non‐FB / non‐WhatsApp links ──────────")
    # First collect all <a> hrefs, then filter out those containing “facebook.com” or “api.whatsapp.com”
    all_hrefs = get_all_attribute_values(sb, '//a[@href]', 'href')
    filtered_hrefs = [h for h in all_hrefs if "facebook.com" not in h and "api.whatsapp.com" not in h]
    print("  filtered_hrefs (len={}):".format(len(filtered_hrefs)), filtered_hrefs[:10], "…")

    print("\n────────── DEBUG: All <div data-ad-preview='reactions'> text ──────────")
    reactions_texts = get_texts_by_xpath(sb, './/div[@data-ad-preview="reactions"]')
    print("  reactions_texts (len={}):".format(len(reactions_texts)), reactions_texts)

    print("\n────────── DEBUG: All <div data-ad-preview='shares'> text ──────────")
    shares_texts = get_texts_by_xpath(sb, './/div[@data-ad-preview="shares"]')
    print("  shares_texts (len={}):".format(len(shares_texts)), shares_texts)
    # ───────────────────────────────────────────────────────────────────────────

    # 3) Now you can still call extract_home(), extract_posts(), extract_transparency() as before:
    data = extract_home(sb)
    data.update({
        "page_id":         "",
        "created_date":    "",
        "admin_countries": [],
        "name_changes":    0,
        "is_running_ads":  False,
        "recent_posts":    []
    })

    # If you want to pick “description” out of one of the lists above, you would do:
    # data["description"] = desc_texts_exact[0] if desc_texts_exact else (desc_texts_fallback[0] if desc_texts_fallback else "")

    # And if you want the website’s visible label, you might do:
    # data["website_name_exact"] = None
    # if filtered_hrefs:
    #     candidate = filtered_hrefs[0]
    #     # find <a href="candidate"><span>…</span></a>
    #     try:
    #         el = sb.find_element(f'//a[@href="{candidate}"]//span', "xpath")
    #         data["website_name_exact"] = el.text.strip()
    #     except:
    #         data["website_name_exact"] = ""

    extract_intro(sb, data)
    extract_posts(sb, data)
    extract_transparency(sb, data)

    # 4) Print the final JSON so you can see which values you want to keep:
    print("\n" + "="*60)
    print(f"FULL RAW DATA for page → {data.get('name','<unknown>')}")
    print("="*60 + "\n")
    print(json.dumps(data, indent=2, ensure_ascii=False))
    print("\n" + "="*60 + "\n")

    # 5) Save to disk as before (if desired):
    fname = slugify(data["name"] or "page")
    path  = save_dir / f"{fname}.json"
    i = 2
    while path.exists():
        path = save_dir / f"{fname}_{i}.json"
        i += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")
    print(f"[OK] saved → {path}")

    # 6) Navigate back:
    sb.driver.back()
    sb.driver.back()
    pause(1)

# ───────────────────────── main loop ──────────────────────────────────────

def main():
    pairs: List[Tuple[str,int]] = []
    if KEYWORDS_FILE.exists():
        with KEYWORDS_FILE.open(encoding="utf-8") as fh:
            for kw, depth, *_ in csv.reader(fh):
                if kw and depth.isdigit():
                    pairs.append((kw.strip(), int(depth)))
    else:
        pairs = [
            ("coca cola", 2),
            ("pepsi", 1),
            ("burger king", 3),
        ]

    with SB(uc=False, headless=HEADLESS) as sb:
        sb.open("https://facebook.com")
        for ck in load_cookies():
            try:
                sb.driver.add_cookie(ck)
            except:
                pass
        sb.refresh()
        pause(2)

        for kw, depth in pairs:
            print(f"\n=== {kw!r} → first {depth} page(s) ===")
            wait_click(sb, XP["search_box"])
            sb.type(XP["search_box"], kw + "\n", "xpath")
            pause(2)
            wait_click(sb, XP["pages_chip"])
            pause(1.5)

            if not click_pages_filter(sb):
                print(f"[ERROR] Failed to click Pages filter for {kw}")
                continue

            pause(2.5)
            links = get_page_links(sb)
            if not links:
                print("[WARN] no pages!")
                continue

            save_dir = Path("scraped_pages") / slugify(kw)
            for el in links[:depth]:
                scrape_one_page(sb, el, save_dir)

            sb.open("https://facebook.com")
            pause(1)

        print("[DONE] – browser stays open 60s for inspection.")
        time.sleep(60)


if __name__ == "__main__":
    main()
