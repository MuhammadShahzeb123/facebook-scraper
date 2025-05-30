#!/usr/bin/env python3
# facebook_keyword_scraper.py – v3.6  (2025-06-10)
# ───────────────────────────────────────────────────────────────────────────
# • Enhanced page ID extraction with strict pattern matching
# • Improved creation date detection using context analysis
# • More reliable description extraction with multiple fallbacks
# ───────────────────────────────────────────────────────────────────────────
import csv, json, re, time, unicodedata
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import urlparse, parse_qs, unquote

from seleniumbase import SB
from selenium.webdriver.common.by import By

# ═══════════════════════ USER CONFIG ══════════════════════════════════════
COOKIE_FILE   = Path("saved_cookies/facebook_cookies.txt")
KEYWORDS_FILE = Path("keywords.csv")      # keyword , pages_to_visit
HEADLESS      = False
WAIT_SECS     = 2.0
SCROLLS       = 3                        # scrolls before grabbing posts
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
        el.click()
    except:
        sb.execute_script("arguments[0].scrollIntoView(true);", el)
        pause(0.2)
        try: el.click()
        except: sb.execute_script("arguments[0].click();", el)

def wait_click(sb: SB, xp: str, timeout=15):
    sb.wait_for_element_visible(xp, "xpath", timeout=timeout)
    sb.click(xp, "xpath")

# ═══════════════════ core extractors ══════════════════════════════════════
def extract_home(sb: SB) -> Dict:
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
    # Exact XPath for description
    xpath = '/html/body/div[1]/div/div[1]/div/div[3]/div/div/div[3]/div[1]/div/div/div[4]/div[2]/div/div[1]/div[2]/div/div[1]/div/div/div/div/div[2]/div[1]/div/div/span'
    fallback_xpath = '//*[@id="mount_0_0_ZA"]/div/div[1]/div/div[3]/div/div/div[2]/div[1]/div/div/div[4]/div[2]/div/div[1]/div[2]/div/div[1]/div/div/div/div/div[2]/div[1]/div/div/span', 
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
                        
        try:
            # Contact Phone
            data["contact_phone"] = sb.get_text(XP["contact_phone"], "xpath", timeout=1).strip()
        except:
            pass
            
        try:
            # Contact Email
            data["contact_email"] = sb.get_text(XP["contact_email"], "xpath", timeout=1).strip()
        except:
            pass
            
        try:
            # Website
            website_el = sb.find_element(XP["website_link"], "xpath", timeout=1)
            data["website"] = website_el.get_attribute("href") or data.get("website", "")
        except:
            pass

        # 3) Click See All (if present)
        try:
            wait_click(sb, XP["see_all"], timeout=4)
            pause(1)
        except:
            pass

        # Try direct extraction first
        try:
            # Page ID - strict pattern matching
            pid_text = sb.get_text(XP["page_id"], "xpath", timeout=2).strip()
            if re.fullmatch(r'\d{10,}', pid_text):
                data["page_id"] = pid_text
        except:
            pass
            
        try:
            # Creation Date - context verification
            date_text = sb.get_text(XP["creation_date"], "xpath", timeout=2).strip()
            # Verify it's a real date, not a name change
            if re.search(r'\d{1,2}\s+[A-Za-z]+\s+\d{4}', date_text):
                data["created_date"] = date_text
        except:
            pass
            
        try:
            # Contact Phone
            data["contact_phone"] = sb.get_text(XP["contact_phone"], "xpath", timeout=1).strip()
        except:
            pass
            
        try:
            # Contact Email
            data["contact_email"] = sb.get_text(XP["contact_email"], "xpath", timeout=1).strip()
        except:
            pass
            
        try:
            # Website
            website_el = sb.find_element(XP["website_link"], "xpath", timeout=1)
            data["website"] = website_el.get_attribute("href") or data.get("website", "")
        except:
            pass

        try:
            modal = sb.find_element('//div[@role="dialog"]', "xpath", timeout=5)
            transparency_text = modal.text
            
            page_id_found = False
        except:
            pass
        # Method 1: Direct XPath extraction
        try:
            pid_text = sb.get_text(XP["page_id"], "xpath", timeout=2).strip()
            if re.fullmatch(r'\d{10,}', pid_text):
                data["page_id"] = pid_text
                page_id_found = True
        except:
            pass
            
        # Method 2: Extract from transparency text
        if not page_id_found:
            try:
                modal = sb.find_element('//div[@role="dialog"]', "xpath", timeout=5)
                transparency_text = modal.text
                # Look for "Page ID" followed by numbers
                pid_match = re.search(r'Page ID[^\d]*(\d{10,})', transparency_text)
                if pid_match:
                    data["page_id"] = pid_match.group(1)
                    page_id_found = True
                else:
                    # Look for any long number in the transparency section
                    numbers = re.findall(r'\d{10,}', transparency_text)
                    if numbers:
                        # The first long number is usually the page ID
                        data["page_id"] = numbers[0]
                        page_id_found = True
            except:
                pass
            
        # Method 3: Extract from page URL
        if not page_id_found:
            try:
                current_url = sb.get_current_url()
                # Extract page ID from URL patterns
                patterns = [
                    r'facebook\.com/(\d+)/',          # facebook.com/1234567890/
                    r'facebook\.com/pages/[^/]+/(\d+)',  # facebook.com/pages/.../1234567890
                    r'fbid=(\d+)'                      # facebook.com/page?fbid=1234567890
                ]
                for pattern in patterns:
                    match = re.search(pattern, current_url)
                    if match:
                        data["page_id"] = match.group(1)
                        page_id_found = True
                        break
            except:
                pass
            
        # Method 4: Extract from page source metadata
        if not page_id_found:
            try:
                src = sb.get_page_source()
                # Look for page ID in meta tags
                meta_match = re.search(r'<meta[^>]+content="(\d+)"[^>]+page_id', src)
                if meta_match:
                    data["page_id"] = meta_match.group(1)
                else:
                    # Look for FB page ID in scripts
                    script_match = re.search(r'"pageID":"(\d+)"', src)
                    if script_match:
                        data["page_id"] = script_match.group(1)
            except:
                pass
            
            # 2. Creation Date extraction
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
            name_changes = re.findall(r'Changed name to [^\n]+\n\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})', transparency_text)
            data["name_changes"] = len(name_changes)
            
            # 5. Ads Flag
            if "currently running ads" in transparency_text:
                data["is_running_ads"] = True
            
            # 6. Verified Status
            if "Verified" in transparency_text:
                data["verified"] = True
                
        # except Exception as e:
        #     print(f"Transparency parsing error: {str(e)}")
            
        # Close the transparency modal
        try:
            close_btn = sb.find_element('//div[@role="dialog"]//*[@aria-label="Close"]', "xpath")
            close_btn.click()
            pause(0.5)
        except:
            pass
    
    except Exception as e:
        print(f"Transparency section error: {str(e)}")
def extract_posts(sb: SB, data: Dict):
    # Save page source for debugging
    with open("debug_page.html", "w", encoding="utf-8") as f:
        f.write(sb.get_page_source())
    print("Saved page source to debug_page.html")
    
    # Scroll to load more posts
    for _ in range(SCROLLS):
        sb.execute_script("window.scrollBy(0, document.body.scrollHeight*0.7)")
        pause(1.2)
    
    # NEW APPROACH: Target specific class structure
    post_containers = sb.find_elements(
        '//div[contains(@class, "x9f619") and contains(@class, "x1n2onr6") and contains(@class, "x1ja2u2z")]',
        "xpath"
    )
    
    if not post_containers:
        print("No post containers found with the specified class structure!")
        # Fallback to other selectors
        post_containers = sb.find_elements(
            '//div[@role="article"] | //div[contains(@class, "x1yztbdb")]',
            "xpath"
        )
        if not post_containers:
            print("No fallback containers found either!")
            return
    
    print(f"Found {len(post_containers)} post containers")
    posts = []
    
    for container in post_containers:
        try:
            post = {
                "url": "",
                "caption": "",
                "image_url": "",
                "video_url": "",
                "reactions": "0",
                "comments": "0",
                "shares": "0",
                "timestamp": ""
            }
            
            # 1. URL extraction
            try:
                # Look for permalink in multiple locations
                link = container.find_element(By.XPATH, 
                    './/a[contains(@href, "/posts/") or contains(@href, "/videos/") or contains(@href, "story_fbid")]')
                post["url"] = link.get_attribute("href")
            except:
                pass
            
            # 2. Caption extraction - focus on text content
            try:
                # First method: Look for the main text container
                caption = container.find_element(By.XPATH, 
                    './/div[@dir="auto" and @style="text-align: start;"] | '
                    './/div[contains(@class, "xdj266r")]')
                post["caption"] = caption.text.strip()
            except:
                try:
                    # Second method: Collect all text spans
                    spans = container.find_elements(By.XPATH, './/span[@dir="auto"]')
                    texts = [span.text.strip() for span in spans if span.text.strip()]
                    post["caption"] = " ".join(texts)
                except:
                    pass
            
            # 3. Media extraction
            try:
                # Image extraction
                img = container.find_element(By.XPATH, 
                    './/img[contains(@src, "scontent") or contains(@src, "fbcdn")]')
                post["image_url"] = img.get_attribute("src")
            except:
                pass
            
            try:
                # Video extraction
                video = container.find_element(By.XPATH, './/video/source')
                post["video_url"] = video.get_attribute("src")
            except:
                pass
            
            # 4. Engagement metrics - look for specific patterns
            try:
                # Reactions
                reactions = container.find_element(By.XPATH, 
                    './/*[contains(., "reactions") or contains(., "Reactions") or contains(@aria-label, "reactions")]')
                post["reactions"] = reactions.text.split()[0] or reactions.get_attribute("aria-label").split()[0]
            except:
                pass
            
            try:
                # Comments
                comments = container.find_element(By.XPATH,
                    './/*[contains(., "comment") or contains(., "Comment") or contains(., "comments")]')
                post["comments"] = comments.text.split()[0]
            except:
                pass
            
            try:
                # Shares
                shares = container.find_element(By.XPATH,
                    './/*[contains(., "share") or contains(., "Share") or contains(., "shares")]')
                post["shares"] = shares.text.split()[0]
            except:
                pass
            
            # 5. Timestamp
            try:
                time_el = container.find_element(By.XPATH, 
                    './/a[.//abbr or .//time]//span | '
                    './/span[contains(text(), "hr") or contains(text(), "min") or contains(text(), "day")]')
                post["timestamp"] = time_el.text.strip()
            except:
                pass
            
            # Add the post even if some fields are empty
            posts.append(post)
        except Exception as e:
            print(f"Error processing post: {str(e)}")
            continue
    
    data["recent_posts"] = posts
    print(f"Extracted {len(posts)} posts (including partial data)")
    
    # Scroll back up
    for _ in range(SCROLLS):
        sb.execute_script("window.scrollBy(0, -document.body.scrollHeight*0.7)")
        pause(1.2)
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
    # Wait specifically for posts to load
    try:
        sb.wait_for_element('//div[@role="article"]', "xpath", timeout=10)
    except:
        print("Timed out waiting for posts to load")
    extract_posts(sb, data)
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

    with SB(uc=True, headless=HEADLESS) as sb:
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