#!/usr/bin/env python3
# facebook_keyword_scraper.py – v3.6  (2025-06-10)
# ───────────────────────────────────────────────────────────────────────────
# • Enhanced page ID extraction with strict pattern matching
# • Improved creation date detection using context analysis
# • More reliable description extraction with multiple fallbacks
# ───────────────────────────────────────────────────────────────────────────
import csv, json, re, time, unicodedata, sys
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import urlparse, parse_qs, unquote
from datetime import datetime
from selenium.common.exceptions import (NoSuchElementException, 
                                      StaleElementReferenceException)

from seleniumbase import SB
from selenium.webdriver.common.by import By

# ═══════════════════════ USER CONFIG ══════════════════════════════════════
COOKIE_FILE   = Path("saved_cookies/facebook_cookies.txt")
KEYWORDS_FILE = Path("keywords.csv")      # keyword , pages_to_visit
HEADLESS      = False
WAIT_SECS     = 2.0
SCROLLS       = 3                        # scrolls before grabbing posts
POST_LIMIT    = 100                        # number of posts to scrape per page
RETRY_LIMIT   = 2
# ══════════════════════════════════════════════════════════════════════════

XP = {
    "search_box":  '//input[@placeholder="Search Facebook" and @type="search"]',
    "pages_chip":  '//span[.="Pages"]/ancestor::*[@role="link" or @role="button"][1]',
    "page_links":  '//div[@role="main"]//a[contains(@href,"facebook.com")][.//span]',

    "about_tab":   '//span[.="About"]/ancestor::*[@role="tab" or @role="link"][1]',
    "transp_link": '//span[contains(.,"Page transparency")]/ancestor::a[1]',
    "see_all":     '//span[.="See All"]/ancestor::*[@role="button"][1]',

    "profile_g":   '//div[@role="banner"]//a[contains(@href, "facebook.com")]//svg[.//image]',
    "profile_img": '//div[@role="banner"]//a[contains(@href, "facebook.com")]//image',
    "profile_a":   '//div[@role="banner"]//a[contains(@href, "facebook.com")]',
    
    "intro":       [
        '//div[@data-pagelet="ProfileTilesFeed"]//div[contains(@class, "x1iorvi4")]//span',
        '//div[contains(text(), "We create") or contains(text(), "私たちは")]'
    ],
    
    "page_id":     '//div[contains(text(), "Page ID")]/following-sibling::div//span',
    "creation_date": '//div[contains(text(), "Creation date")]/following-sibling::div//span',
    "contact_phone": '//div[text()="Phone"]/following-sibling::div',
    "contact_email": '//div[text()="Email"]/following-sibling::div',
    "website_link": '//div[text()="Website"]/following-sibling::div//a',
    
    "posts_tab":   '//span[.="Posts"]/ancestor::a[1]',
}

# ───────────────────── helper functions ───────────────────────────────────
def pause(t=WAIT_SECS): time.sleep(t)

def decode(url: str) -> str:
    if "l.facebook.com/l.php" not in url:
        return url
    return unquote(parse_qs(urlparse(url).query).get("u", [""])[0]) or url

def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii","ignore").decode()
    s = re.sub(r"[^\w\s-]", "", s).strip().lower()
    return re.sub(r"[-\s]+", "-", s) or "page"

def load_cookies() -> List[dict]:
    data = json.load(COOKIE_FILE.open())
    for ck in data:
        ss = ck.get("sameSite", "").lower()
        ck["sameSite"] = "None" if ss not in {"strict","lax","none"} else ss.title()
    return data

def safe_click(sb: SB, el):
    try:
        # Re-locate the element before interacting
        xpath = f'//a[@href="{el.get_attribute("href")}"]'
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
                # Fallback to URL navigation
                url = el.get_attribute("href")
                if url:
                    sb.open(url)
                    pause(3)

def wait_click(sb: SB, xp: str, timeout=15):
    sb.wait_for_element_visible(xp, "xpath", timeout=timeout)
    sb.click(xp, "xpath")

def parse_engagement_text(text):
    """Parse engagement text into numbers (handles K/M abbreviations)"""
    if not text:
        return 0
    
    # Clean and normalize text
    text = text.replace(',', '').lower().strip()
    
    # Handle abbreviations (K/M)
    multiplier = 1
    if 'k' in text:
        multiplier = 1000
        text = text.replace('k', '')
    elif 'm' in text:
        multiplier = 1000000
        text = text.replace('m', '')
    
    # Extract numbers
    numbers = re.findall(r'\d+', text)
    if not numbers:
        return 0
    
    try:
        return int(numbers[0]) * multiplier
    except ValueError:
        return 0

def extract_with_retry(container, extract_func, *args, **kwargs):
    """Helper function to retry extraction on failure"""
    for attempt in range(RETRY_LIMIT + 1):
        try:
            result = extract_func(container, *args, **kwargs)
            if result:  # Only return if we got a meaningful result
                return result
        except (NoSuchElementException, StaleElementReferenceException) as e:
            if attempt < RETRY_LIMIT:
                time.sleep(0.5)
                continue
            else:
                return None
    return None

# ═════════════════════ POST EXTRACTION FUNCTIONS ══════════════════════════
def extract_caption(container):
    """Extract post caption text"""
    try:
        # First try: data-ad-preview attribute
        caption_el = container.find_element(By.XPATH, './/div[@data-ad-preview="message"]')
        if caption := caption_el.text.strip():
            return caption
    except:
        pass
    
    try:
        # Second try: specific class combination
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

def extract_url(container):
    """Extract post URL/permalink"""
    try:
        return container.find_element(
            By.XPATH,
            './/a[contains(@href, "/posts/") or contains(@href, "/videos/")][@role="link"]'
        ).get_attribute("href")
    except:
        return ""

def extract_timestamp(container):
    """Extract post timestamp"""
    try:
        # First method: aria-label on abbr element
        timestamp = container.find_element(
            By.XPATH,
            './/a[contains(@href, "permalink")]//abbr | '
            './/abbr[contains(@class, "xt0psk2")]'
        ).get_attribute("aria-label")
        if timestamp:
            return timestamp
    except:
        pass
    
    try:
        # Second method: specific class combination
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

def extract_images(container):
    """Extract images from post"""
    try:
        img_elements = container.find_elements(By.XPATH, './/img[contains(@src, "scontent")]')
        return [img.get_attribute("src") for img in img_elements if img.get_attribute("src")]
    except:
        return []

def extract_video_url(container):
    """Extract video URL from post"""
    try:
        return container.find_element(By.XPATH, './/video | .//video/source').get_attribute("src")
    except:
        return ""

def extract_post_engagement(container):
    """Extract post engagement metrics (likes, comments, shares)"""
    try:
        # Find the engagement bar - container for post metrics
        engagement_bar = container.find_element(
            By.XPATH, 
            './/div[@role="toolbar" and contains(@aria-label, "Reactions")]'
        )
        
        # Extract all metrics from the toolbar
        metrics = {
            "likes": 0,
            "comments": 0,
            "shares": 0
        }
        
        # Get all span elements within the engagement bar
        spans = engagement_bar.find_elements(By.XPATH, './/span')
        for span in spans:
            text = span.text.strip()
            if not text:
                continue
                
            # Check for likes/reactions
            if "like" in text.lower() or "reaction" in text.lower():
                metrics["likes"] = parse_engagement_text(text)
            
            # Check for comments
            elif "comment" in text.lower():
                metrics["comments"] = parse_engagement_text(text)
            
            # Check for shares
            elif "share" in text.lower():
                metrics["shares"] = parse_engagement_text(text)
                
        return metrics
        
    except Exception as e:
        return {
            "likes": 0,
            "comments": 0,
            "shares": 0
        }

def extract_post(container):
    """Extract all data from a single post container"""
    caption = extract_with_retry(container, extract_caption) or ""
    url = extract_with_retry(container, extract_url) or ""
    timestamp = extract_with_retry(container, extract_timestamp) or ""
    images = extract_with_retry(container, extract_images) or []
    video_url = extract_with_retry(container, extract_video_url) or ""
    
    # Extract engagement metrics
    engagement = extract_with_retry(container, extract_post_engagement) or {
        "likes": 0,
        "comments": 0,
        "shares": 0
    }
    
    # Validate metrics
    likes = min(engagement["likes"], 10000000)
    comments = min(engagement["comments"], 1000000)
    shares = min(engagement["shares"], 1000000)
    
    return {
        "text": caption[:500] if caption else "",
        "url": url,
        "timestamp": timestamp,
        "images": images,
        "video_url": video_url,
        "likes": likes,
        "comments": comments,
        "shares": shares,
        "scraped_at": datetime.now().isoformat()
    }

def extract_posts(sb: SB, data: dict):
    """Extract recent posts from the current page"""
    # Switch to the Posts tab
    # try:
    #     wait_click(sb, XP["posts_tab"])
    #     pause(3)
    # except Exception as e:
    #     print(f"⚠️ Couldn't switch to Posts tab: {str(e)}")
    #     return
    
    # Scroll to load more posts
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
    
    # Find post containers
    try:
        containers = sb.driver.find_elements(
            By.XPATH, 
            '//div[contains(@class, "x1yztbdb") and .//div[contains(@data-ad-preview, "message")]]'
        )
        print(f"🔍 Found {len(containers)} post containers")
    except Exception as e:
        print(f"❌ Error finding post containers: {str(e)}")
        return
    
    # Extract posts
    posts = []
    for i, container in enumerate(containers):
        if len(posts) >= POST_LIMIT:
            break
            
        try:
            sb.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", container)
            pause(0.5)
            
            post = extract_post(container)
            if post.get('text') or post.get('url'):
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
    """Extract basic page information from home"""
    sb.execute_script("window.scrollTo(0,0)")
    out = {
        "name": "", "profile_pic": "", "verified": False,
        "followers": "", "likes": "", "category": "",
        "website": "", "links": [], "description": "",
        "contact_phone": "", "contact_email": ""
    }

    # Name & Verified
    try:
        h1 = sb.wait_for_element('//div[@role="main"]//h1', "xpath", timeout=4)
        out["name"] = h1.text.strip()
        out["verified"] = bool(
            h1.find_elements(By.XPATH, './/svg[@title="Verified account"]')
        )
    except:
        pass

    # Profile pic - multiple fallbacks
    try:
        # First try: regular image
        img = sb.find_element(
            '//img[contains(@src, "profile") or contains(@src, "fbcdn")]', 
            "xpath", 
            timeout=3
        )
        out["profile_pic"] = img.get_attribute("src") or ""
    except:
        try:
            # Second try: SVG profile picture
            img = sb.find_element(XP["profile_img"], "xpath", timeout=3)
            out["profile_pic"] = img.get_attribute("xlink:href") or img.get_attribute("href") or ""
        except:
            try:
                # Third try: Link to profile picture
                link = sb.find_element(XP["profile_a"], "xpath", timeout=3)
                style = link.get_attribute("style")
                if style and "url(" in style:
                    match = re.search(r'url\("?(https://[^")]+)"?\)', style)
                    if match:
                        out["profile_pic"] = match.group(1)
            except:
                out["profile_pic"] = ""

    # Followers / Likes
    src = sb.get_page_source()
    m = re.search(r'([0-9.,]+[A-Za-z万億]*)\s+likes?', src, re.I)
    if m: out["likes"] = m.group(1).replace(" ", "")
    m = re.search(r'([0-9.,]+[A-Za-z万億]*)\s+(followers?|フォロワー)', src, re.I)
    if m: out["followers"] = m.group(1).replace(" ", "")

    # Category
    try:
        cat = sb.find_element(
            '//span[./strong[text()="Page" or text()="ページ"]]', "xpath"
        ).text
        out["category"] = (
            cat.split("·",1)[1].strip()
            if "·" in cat else cat.replace("ページ","").strip()
        )
    except:
        pass

    # CTA & Links
    for a in sb.find_elements('//a[starts-with(@href,"http")]', "xpath"):
        href = decode(a.get_attribute("href"))
        if href.startswith("http"):
            if not out["website"] and "facebook.com" not in href:
                out["website"] = href
            out["links"].append(href)
    out["links"] = list(dict.fromkeys(out["links"]))

    return out

def extract_intro(sb: SB, data: Dict):
    """Extract page description/intro text"""
    # Exact XPath for description
    xpath = '/html/body/div[1]/div/div[1]/div/div[3]/div/div/div[3]/div[1]/div/div/div[4]/div[2]/div/div[1]/div[2]/div/div[1]/div/div/div/div/div[2]/div[1]/div/div/span'
    fallback_xpath = '//*[@id="mount_0_0_ZA"]/div/div[1]/div/div[3]/div/div/div[2]/div[1]/div/div/div[4]/div[2]/div/div[1]/div[2]/div/div[1]/div/div/div/div/div[2]/div[1]/div/div/span'
    try:
        desc_el = sb.find_element(xpath, "xpath", timeout=3)
        data["description"] = desc_el.text.strip()
    except:
        # Fallback to previous methods
        for fallback_xpath in XP["intro"]:
            try:
                desc_el = sb.find_element(fallback_xpath, "xpath", timeout=1)
                desc_text = desc_el.text.strip()
                if desc_text and len(desc_text) > 20:
                    data["description"] = desc_text
                    return
            except:
                continue
        data["description"] = ""

def extract_transparency(sb: SB, data: Dict):
    """Extract page transparency information"""
    try:
        # 1) Click About
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
                        
        # 3) Click See All (if present)
        try:
            wait_click(sb, XP["see_all"], timeout=4)
            pause(1)
        except:
            pass

        # Try direct extraction first
        # 4) Extract modal text
        try:
            
            admin_texts = sb.find_elements('//span[text()="Admin info"]/ancestor::div[contains(@class,"x9f619")]//span[position()=1]', "xpath")
            transparency_text = [t.text for t in admin_texts if t.text]
            
            transparency_text = "\n".join(transparency_text)

            # modal = sb.find_element('//div[@role="dialog"]', "xpath", timeout=5)
            # transparency_text = modal.text
            data["transparency_raw"] = transparency_text  # optional, for debugging

            # 1. Page ID
            match = re.search(r'Page ID[^\d]*(\d{10,})', transparency_text)
            if match:
                data["page_id"] = match.group(1)

            # 2. Creation Date
            match = re.search(r'(?:Created|Creation date)[^\n]*\n\D*(\d{1,2}\s+[A-Za-z]+\s+\d{4})', transparency_text)
            if match:
                data["created_date"] = match.group(1)

            if not data["created_date"]:
                # Look for creation date specifically
                date_match = re.search(r'Creation date[^\n]*\n\D*(\d{1,2}\s+[A-Za-z]+\s+\d{4})', transparency_text)
                if not date_match:
                    # Fallback to created date
                    date_match = re.search(r'Created[^\n]*\n\D*(\d{1,2}\s+[A-Za-z]+\s+\d{4})', transparency_text)
                if date_match:
                    data["created_date"] = date_match.group(1)
            # 3. Admin Countries
            country_match = re.search(r'Primary country/region[^\n]*\n((?:\s*\w+\s*\(\d+\)\n?)+)', transparency_text)
            if country_match:
                countries = re.findall(r'\w[\w\s]+\(\d+\)', country_match.group(1))
                data["admin_countries"] = [c.strip() for c in countries]
            
            # 4. Name Changes
            name_changes = re.findall(
                r'^Changed name to\s+[^\n]+', 
                transparency_text, 
                re.MULTILINE | re.IGNORECASE
            )
            data["name_changes"] = len(name_changes)

            # 5. Ads Flag
            if "currently running ads" in transparency_text:
                data["is_running_ads"] = True

            # 6. Verified (fallback)
            if "Verified" in transparency_text:
                data["verified"] = True

        except Exception as e:
            print(f"[WARN] Transparency modal parsing failed: {str(e)}")

        # 5) Close the modal
        try:
            close_btn = sb.find_element('//div[@role="dialog"]//*[@aria-label="Close"]', "xpath")
            close_btn.click()
            pause(0.5)
        except:
            pass

    except Exception as e:
        print(f"[ERROR] extract_transparency(): {str(e)}")

# ───────────────────── scrape one page ───────────────────────────────────
def scrape_one_page(sb: SB, link_el, save_dir: Path):
    safe_click(sb, link_el)
    pause(5)

    data = extract_home(sb)
    data.update({
        "page_id": "", "created_date": "", "admin_countries": [],
        "name_changes": 0, "is_running_ads": False, "recent_posts": []
    })

    extract_intro(sb, data)
    extract_posts(sb, data)  # Extract posts here
    extract_transparency(sb, data)
    
    # save JSON
    fname = slugify(data["name"] or "page")
    path  = save_dir / f"{fname}.json"
    i = 2
    while path.exists():
        path = save_dir / f"{fname}_{i}.json"
        i += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")
    print(f"[OK] saved → {path}")

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
        pairs = [("coca cola",2)]

    with SB(uc=False, headless=HEADLESS) as sb:
        sb.open("https://facebook.com")
        for ck in load_cookies():
            try: sb.driver.add_cookie(ck)
            except: pass
        sb.refresh()
        pause(2)

        for kw, depth in pairs:
            print(f"\n=== {kw!r} → first {depth} page(s) ===")
            wait_click(sb, XP["search_box"])
            sb.type(XP["search_box"], kw+"\n", "xpath")
            pause(2)
            wait_click(sb, XP["pages_chip"])
            pause(1.5)

            links = sb.find_elements(XP["page_links"], "xpath")
            if not links:
                print("[WARN] no pages!")
                continue

            save_dir = Path("scraped_pages")/slugify(kw)
            for el in links[:depth]:
                scrape_one_page(sb, el, save_dir)

            sb.open("https://facebook.com")
            pause(1)

        print("[DONE] – browser stays open 60s for inspection.")
        time.sleep(60)

if __name__=="__main__":
    main()