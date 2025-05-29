#!/usr/bin/env python3
# facebook_keyword_scraper.py – v2.4  (2025-06-04)
# ──────────────────────────────────────────────────────────────────────────
# • fills every data-point required in §2.2
# • multi-layout selectors (2024-Q4, 2025-Q2 UI)
# • post metrics (captions / reactions / comments / shares)
# • full Transparency parsing: created-year, admin countries, name-change count
# • robust likes/followers detection (both “108M likes” and “108,000,000 likes”)
# • filters out every FB/CDN asset from links
# • duplicate-slug safeguard kept
# ──────────────────────────────────────────────────────────────────────────
import csv, json, re, time, unicodedata
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import urlparse, parse_qs, unquote

from seleniumbase import SB
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotInteractableException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.common.by import By          # ← already added
import datetime, itertools                            # new

# ═══════════════════════ USER CONFIG ══════════════════════════════════════
COOKIE_FILE   = Path("saved_cookies/facebook_cookies.txt")
KEYWORDS_FILE = Path("keywords.csv")          # keyword , pages_to_visit
HEADLESS      = False                         # set True once stable
POST_LIMIT    = 10
WAIT_SECS     = 2.0
# bad host fragments that aren’t “external links”
BAD_DOMAINS   = ("facebook.com", "fbcdn.net", "static.", "scontent.", "messenger.com")
# ══════════════════════════════════════════════════════════════════════════

SEL = dict(
    search_box  = '//input[@placeholder="Search Facebook" and @type="search"]',
    pages_chip  = (
        '//div[@aria-label="Filters"]//span[normalize-space()="Pages"]/ancestor::*[self::a or self::div][1]'
        ' | //span[normalize-space()="Pages"]/ancestor::*[@role="link" or @role="button"][1]'
        ' | //span[normalize-space()="Pages"]'
    ),
    page_links  = (
        '//div[@role="main"]//a'
        '[contains(@href,"facebook.com") and not(contains(@href,"search/"))]'
        '[.//span[normalize-space()]]'
    ),
    about_tab   = '//span[text()="About" or text()="About"]'
                  '/ancestor::a[@role="tab" or @role="link"][1]',
    transp_link = '//span[contains(.,"Page transparency")]/ancestor::a[1]',
    transparency_panel = '//div[@role="main"]//h2//*[text()="Page transparency"]/ancestor::div[@role="main"]',
    see_all_transp    = './/span[text()="See All"]/ancestor::*[@role="button"][1]',
)

# ───────────────────────── helpers ────────────────────────────────────────
def pause(t=WAIT_SECS):  time.sleep(t)
def extract_about(sb: SB, data: Dict):
    try:
        wait_click(sb, SEL["about_tab"]); pause(1)
        sb.execute_script("window.scrollBy(0, 600)")        # reveal “Intro”

        # page “Intro” paragraph (≥ 30 chars, skip generic sentences)
        for p in sb.find_elements('//div[@role="main"]//span[@dir="auto"]', "xpath"):
            txt = p.text.strip()
            if len(txt) > 30 and "responsible for this Page" not in txt:
                data["description"] = txt; break

        # external links
        for a in sb.find_elements('//a[starts-with(@href,"http")]',"xpath"):
            href = decode_fb_redirect(a.get_attribute("href"))
            if is_external(href):
                data.setdefault("links", []).append(href)
                if not data["website"]: data["website"] = href
    except Exception:
        pass
def extract_posts(sb: SB, limit=POST_LIMIT) -> list[dict]:
    posts = []
    while len(posts) < limit:
        cards = sb.find_elements('//div[@role="article" and .//a[contains(@href,"/posts/") or contains(@href,"/videos/")]]',"xpath")
        for c in cards[len(posts):]:
            try:
                link = c.find_element('.//a[contains(@href,"/posts/") or contains(@href,"/videos/")]',"xpath").get_attribute("href")
                caption = ""
                try:
                    cap = c.find_element('.//*[@data-ad-preview="message"]',"xpath")
                    caption = cap.text.strip()
                except Exception: pass
                metrics = {"reactions":0,"comments":0,"shares":0}
                for t in c.find_elements('.//span[@aria-label or contains(text(),"share") or contains(text(),"comment")]',"xpath"):
                    n = re.findall(r'[0-9.,]+[A-Za-z万億]*', t.text)
                    if not n: continue
                    if "share" in t.text.lower():    metrics["shares"]=n[0]
                    elif "comment" in t.text.lower(): metrics["comments"]=n[0]
                    else:                             metrics["reactions"]=n[0]
                posts.append({"url":link,"caption":caption,**metrics})
                if len(posts)==limit: break
            except Exception: continue
        # scroll to load more
        if len(posts) < limit:
            sb.execute_script("window.scrollBy(0, document.body.scrollHeight*0.7)")
            time.sleep(1.2)
            continue
    return posts
def load_cookies() -> list[dict]:
    data = json.load(COOKIE_FILE.open())
    for ck in data:
        ss = ck.get("sameSite","").lower()
        ck["sameSite"] = ss.title() if ss in {"strict","lax","none"} else "None"
    return data

def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^\w\s-]", "", s).strip().lower()
    return re.sub(r"[-\s]+", "-", s) or "page"
def load_cookies() -> List[dict]:
    data = json.load(COOKIE_FILE.open())
    for ck in data:
        ss = ck.get("sameSite", "").lower()
        ck["sameSite"] = "None" if ss not in {"strict", "lax", "none"} else ss.title()
    return data
# ─── utilities ────────────────────────────────────────────────────────────
def safe_click(sb: SB, el):
    """Try a normal .click(), scroll-into-view, and JS click fallback"""
    try:
        el.click(); return
    except Exception:
        pass
    try:
        sb.execute_script("arguments[0].scrollIntoView({block:'center'})", el)
        time.sleep(0.2); el.click(); return
    except Exception:
        pass
    # last resort – JS click (works on <div role=link> etc.)
    sb.execute_script("arguments[0].click()", el)

def decode_fb_redirect(url: str) -> str:
    if "l.facebook.com/l.php" not in url: return url
    q = parse_qs(urlparse(url).query).get("u", [""])[0]
    return unquote(q) or url

def clean_num(txt: str) -> str:
    """'108M'→'108M'  '108 000 000'→'108000000'  keep 'K/M/B' suffixes"""
    txt = txt.replace(" ", "").replace(",", "")
    return txt

def is_external(url: str) -> bool:
    u = url.lower()
    return url.startswith("http") and \
           not any(dom in u for dom in BAD_DOMAINS) and \
           not re.search(r"\.(css|js)(\?|$)", u)

def wait_click(sb: SB, xp: str, to=15):
    sb.wait_for_element_visible(xp, "xpath", timeout=to)
    sb.click(xp, "xpath")
# ─── helper lives near top of the file ──────────────────────────────
def load_cookies() -> list[dict]:
    """Fix legacy 'sameSite':'no_restriction' → 'None' before adding."""
    data = json.load(COOKIE_FILE.open())
    for ck in data:
        ss = ck.get("sameSite", "").lower()
        ck["sameSite"] = ss.title() if ss in {"strict", "lax", "none"} else "None"
    return data

# ───────────────────── core extractors ─────────────────────────────────────
# ─── drop-in replacement for extract_home() ────────────────────────
def extract_home(sb: SB) -> Dict:
    out = {
    "name": "",
    "profile_pic": "",
    "verified": False,
    "followers": "",
    "likes": "",
    "category": "",
    "website": "",
    "description": ""
}
                                 # (same keys)

    sb.execute_script("window.scrollTo(0,0)")

    # ── NAME / VERIFIED ─────────────────────────────────────────────
    h1 = None
    for xp in ['//h1[contains(@class,"html-h1")]',
               '//div[@role="main"]//h1[normalize-space()]',
               '//span/h1[normalize-space()]']:
        try:
            h1 = sb.wait_for_element(xp, "xpath", timeout=4); break
        except Exception:
            continue
    if h1:
        out["name"] = sb.execute_script("return arguments[0].innerText", h1).split("\n")[0]
        out["verified"] = bool(h1.find_elements(By.XPATH,
                                        './/svg[@title="Verified account"]'))


    # ── LIKES / FOLLOWERS (handles “109M followers”, “1.3万フォロワー” …) ───
    header_text = sb.get_page_source()
    m = re.search(r'([0-9.,]+[A-Za-z万億]*)\s+likes?', header_text, re.I)
    if m: out["likes"] = m.group(1).lower()
    m = re.search(r'([0-9.,]+[A-Za-z万億]*)\s+(followers?|フォロワー)', header_text, re.I)
    if m: out["followers"] = m.group(1).lower()

    # ── CATEGORY ( Page · Food and drink / 会社 など ) ────────────────────
    try:
        cat = sb.find_element('//span[./strong[text()="Page" or text()="ページ"]]',"xpath").text
        if "·" in cat: out["category"] = cat.split("·",1)[1].strip()
        else:          out["category"] = cat.replace("ページ","").strip()
    except Exception: pass

    # ── PROFILE PIC ─────────────────────────────────────────────────
    try:
        img = sb.find_element('//image|//img[@role="img"]', "xpath")
        src = img.get_attribute("src") or img.get_attribute("xlink:href")
        if src and "scontent" in src: out["profile_pic"] = src
    except Exception: pass

    # ── FIRST external link in header (cta buttons / website / WhatsApp) ─
    try:
        a = sb.find_element('//div[@role="main"]//a[starts-with(@href,"http")]',"xpath")
        link = decode_fb_redirect(a.get_attribute("href"))
        if is_external(link): out["website"] = link
    except Exception: pass

    return out


def extract_about(sb: SB, data: Dict):
    try:
        wait_click(sb, SEL["about_tab"]); pause(1)
        # description (first <div> that isn't “Page transparency” etc.)
        try:
            p = sb.find_element('//div[@role="main"]//span[@dir="auto" and string-length(normalize-space())>20]',"xpath")
            data["description"] = p.text.strip()
        except Exception: pass

        for a in sb.find_elements('//a[starts-with(@href,"http")]',"xpath"):
            href = decode_fb_redirect(a.get_attribute("href"))
            if is_external(href):
                if not data["website"]: data["website"] = href
                data.setdefault("links", []).append(href)
    except Exception: pass

def extract_transparency(sb: SB, data: Dict):
    try:
        wait_click(sb, SEL["transp_link"]); pause(1.2)
        src = sb.get_page_source()

        # creation year
        m = re.search(r'Created on[^0-9]*([0-9]{4})', src);     data["created_year"]=m.group(1) if m else ""
        # page id
        m = re.search(r'Page ID[^0-9]*([0-9]{8,})', src);       data["page_id"]=m.group(1) if m else ""
        # admin countries
        countries = re.findall(r'Admin location.*?<span[^>]*>([^<]+)', src, re.S)
        data["admin_countries"] = list(dict.fromkeys(countries))   # uniq preserve order
        # name changes
        nmc = re.search(r'Page name changed ([0-9]+) times?', src)
        data["name_changes"] = int(nmc.group(1)) if nmc else 0
        data["is_running_ads"] = 'is currently running ads' in src
    except Exception: pass

def extract_posts(sb: SB, limit=POST_LIMIT) -> List[Dict]:
    posts: List[Dict] = []
    cards = sb.find_elements(
        '//div[@role="article" and .//a[contains(@href,"/posts/")]]', "xpath")
    for card in cards[:limit]:
        try:
            link = card.find_element('.//a[contains(@href,"/posts/")]',"xpath").get_attribute("href")
            caption = ""
            try:
                cap_el = card.find_element('.//div[@data-ad-preview="message"]',"xpath")
                caption = cap_el.text.strip()
            except Exception: pass
            metrics = {"reactions":0,"comments":0,"shares":0}
            for span in card.find_elements('.//span[contains(@aria-label,"Reaction") or contains(text(),"comment") or contains(text(),"share")]',"xpath"):
                t = span.text.lower()
                n = re.findall(r'[0-9,.MK]+', t)
                if not n: continue
                num = n[0]
                if "comment" in t: metrics["comments"]=num
                elif "share" in t: metrics["shares"]=num
                else: metrics["reactions"]=num
            posts.append({"url":link,"caption":caption,**metrics})
        except Exception:
            continue
    return posts

# ───────────────────── scrape one page ─────────────────────────────────────
def scrape_one_page(sb: SB, link_el, save_dir: Path):
    page_name = link_el.text.strip() or "page"
    safe_click(sb, link_el)
    pause(2)


    data = extract_home(sb)
    extract_about(sb, data)
    extract_transparency(sb, data)
    data["links"] = sorted(set(filter(is_external, data.get("links",[]))))
    data["recent_posts"] = extract_posts(sb)

    # file path (avoid overwrite)
    fname = slugify(page_name)
    path  = save_dir / f"{fname}.json"
    i=2
    while path.exists():
        path = save_dir / f"{fname}_{i}.json"; i+=1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")
    print(f"    [OK] saved → {path}")

    sb.driver.back(); sb.driver.back(); pause(1)

# ───────────────────────── main loop ───────────────────────────────────────
def main():
    pairs: List[Tuple[str,int]] = []
    if KEYWORDS_FILE.exists():
        with KEYWORDS_FILE.open(encoding="utf-8") as fh:
            for kw, depth, *_ in csv.reader(fh):
                if kw and depth.isdigit(): pairs.append((kw.strip(), int(depth)))
    else: pairs = [
    ("coca cola", 2),
    ("pepsi", 1),
    ("burger king", 3),
]
    
    with SB(uc=True, headless=HEADLESS) as sb:
        sb.open("https://facebook.com")
        for ck in load_cookies():
            try: sb.driver.add_cookie(ck)
            except Exception: pass

        sb.refresh(); pause(2)

        for kw, depth in pairs:
            print(f"\n=== {kw!r} → first {depth} page(s) ===")
            wait_click(sb, SEL["search_box"]); sb.type(SEL["search_box"], kw+"\n", "xpath")
            pause(2); wait_click(sb, SEL["pages_chip"]); pause(1.5)

            links = sb.find_elements(SEL["page_links"],"xpath")
            if not links: print("   [WARN] no page results!"); continue

            save_dir = Path("scraped_pages") / slugify(kw)
            for el in links[:depth]:
                scrape_one_page(sb, el, save_dir)

            sb.open("https://facebook.com"); pause(1)

        print("[DONE] – browser stays open 90 s for inspection."); time.sleep(90)

if __name__ == "__main__":
    main()
