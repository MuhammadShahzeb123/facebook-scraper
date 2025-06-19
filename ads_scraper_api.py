#!/usr/bin/env python3
"""
Ads Scraper API Wrapper
Integrates the existing ads scraping functionality into async API calls
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

from seleniumbase import SB
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Import existing scraping functions
import sys
import importlib.util

class AdsScraperAPI:
    """API wrapper for Facebook ads scraping functionality"""

    def __init__(self):
        self.cookie_file = Path("./saved_cookies/facebook_cookies.txt")
        self.ad_library_url = (
            "https://www.facebook.com/ads/library/"
            "?active_status=active&ad_type=all&country=ALL"
            "&is_targeted_country=false&media_type=all"
        )

    def load_cookies(self) -> list[dict]:
        """Load and sanitize cookies"""
        if not self.cookie_file.exists():
            raise FileNotFoundError(f"Cookie file not found: {self.cookie_file}")

        cookies = json.loads(self.cookie_file.read_text())
        for c in cookies:
            if "sameSite" in c and c["sameSite"].lower() not in {"strict", "lax", "none"}:
                c["sameSite"] = "None"
        return cookies

    def wait_click(self, sb: SB, selector: str, *, by="css selector", timeout=10):
        """Safe click with wait"""
        sb.wait_for_element_visible(selector, by=by, timeout=timeout)
        sb.click(selector, by=by)

    def safe_type(self, sb: SB, selector: str, text: str, *,
                  by="css selector", press_enter: bool = True, timeout: int = 10):
        """Safe type with error handling"""
        from selenium.webdriver.common.keys import Keys

        sb.wait_for_element_visible(selector, by=by, timeout=timeout)
        elm = sb.find_element(selector, by=by)
        elm.clear()
        elm.send_keys(text)
        time.sleep(1.0)
        if press_enter:
            elm.send_keys(Keys.RETURN)
            time.sleep(2.0)

    def human_scroll(self, sb: SB, px: int = 1800):
        """Human-like scrolling"""
        sb.execute_script(f"window.scrollBy(0,{px});")

    def _detect_card_prefix(self, sb: SB) -> str | None:
        """Detect the correct card prefix for current page layout"""
        common_head = "/html/body/div[1]/div/div/div/div/div/div/div[1]/div/div/div"

        for row in (5, 4):
            prefix = f"{common_head}/div[{row}]/div[2]/div[2]/div[4]/div[1]"
            try:
                sb.driver.find_element("xpath", f"{prefix}/div[1]/div")
                return prefix
            except NoSuchElementException:
                continue
        return None

    def _parse_card(self, card) -> Dict[str, Any]:
        """Parse individual ad card"""
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

        # Expand card
        _maybe_click('.//div[@role="button" and .="Open Drop-down"]')

        # Extract meta fields
        status = _t('.//span[contains(text(),"Active") or contains(text(),"Inactive")]')
        lib_raw = _t('.//span[contains(text(),"Library ID")]')
        library_id = lib_raw.split(":",1)[-1].strip() if lib_raw else None
        started_raw = _t('.//span[contains(text(),"Started running")]')
        page_name = _t('.//a[starts-with(@href,"https://www.facebook.com/")][1]')

        # Extract raw text
        raw_block = card.text.strip()

        # Extract primary text
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

        # CTA detection
        CTA_PHRASES = (
            "\nLearn More", "\nLearn more", "\nShop Now", "\nShop now", "\nBook Now",
            "\nBook now", "\nDonate", "\nDonate now", "\nApply Now", "\nApply now",
            "\nGet offer", "\nGet Offer", "\nGet quote", "\nSign Up", "\nSign up",
            "\nContact us", "\nSend message", "\nSend Message", "\nSubscribe", "\nRead more",
            "\nSend WhatsApp message", "\nSend WhatsApp Message", "\nWatch video", "\nWatch Video",
        )

        cta = None
        for phrase in CTA_PHRASES:
            label = _t(f'.//div[@role="button" and normalize-space(text())="{phrase}"]'
                      f' | .//span[normalize-space(text())="{phrase}"]')
            if label:
                cta = phrase
                break

        if not cta:
            m = re.search(r"\b(" + "|".join(map(re.escape, CTA_PHRASES)) + r")\b", raw_block)
            cta = m.group(1) if m else None

        # Link extraction
        facebook_domains = {"facebook.com", "fb.com", "facebookw.com", "fb.me", "fb.watch"}
        all_links = []
        image_urls = []

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
            except:
                continue

        return {
            "status": status,
            "library_id": library_id,
            "started": started_raw,
            "page": page_name,
            "primary_text": primary_text,
            "cta": cta,
            "links": all_links,
            "image_urls": image_urls,
            "raw_text": raw_block,
        }

    def extract_ads(self, sb: SB, limit: int = None) -> List[Dict[str, Any]]:
        """Extract ads from current page"""
        ads = []

        # Initial scroll to load content
        sb.execute_script("window.scrollBy(0, 800);")
        time.sleep(1)

        prefix = self._detect_card_prefix(sb)
        if not prefix:
            return ads

        # Wait for first card
        sb.wait_for_element_visible(f"{prefix}/div[1]/div", by="xpath", timeout=15)

        n = 1
        while True:
            if limit and len(ads) >= limit:
                break

            xpath = f"{prefix}/div[{n}]/div"
            try:
                card_ele = sb.driver.find_element("xpath", xpath)
            except NoSuchElementException:
                break

            try:
                ads.append(self._parse_card(card_ele))
            except Exception:
                pass
            n += 1

        return ads

    async def search_ads(self, keyword: str, category: str = "all", location: str = "thailand",
                        language: str = "thai", advertiser: str = "all", platform: str = "all",
                        media_type: str = "all", status: str = "all", start_date: str = "June 18, 2018",
                        end_date: str = "today", limit: int = 1000) -> Dict[str, Any]:
        """
        Main async method to search for ads
        """

        def _run_scraper():
            with SB(uc=True, headless=True) as sb:
                # Load Facebook with cookies
                sb.open("https://facebook.com")
                for ck in self.load_cookies():
                    try:
                        sb.driver.add_cookie(ck)
                    except Exception:
                        pass

                sb.open(self.ad_library_url)
                sb.sleep(5)

                # Country dropdown
                self.wait_click(sb, '//div[div/div/text()="All" or div/div/text()="Country"]/..', by="xpath")
                self.safe_type(sb, '//input[@placeholder="Search for country"]', location, by="xpath")
                self.wait_click(sb, f'//div[contains(@id,"js_") and text()="{location}"]', by="xpath")
                sb.sleep(2)

                # Ad category
                self.wait_click(sb, '//div[div/div/text()="Ad category"]/..', by="xpath")
                self.wait_click(sb, '//span[text()="All ads"]/../../..', by="xpath")
                sb.sleep(2)

                # Keyword search
                key_box = ('//input[@type="search" and contains(@placeholder,"keyword") '
                          'and not(@aria-disabled="true")]')
                self.safe_type(sb, key_box, keyword, by="xpath", press_enter=True)
                sb.sleep(4)

                # Scroll to load more ads
                for i in range(3):
                    self.human_scroll(sb)
                    sb.sleep(2 + i * 0.5)

                # Extract ads
                ads = self.extract_ads(sb, limit=limit)

                return {
                    "keyword": keyword,
                    "location": location,
                    "category": category,
                    "language": language,
                    "advertiser": advertiser,
                    "platform": platform,
                    "media_type": media_type,
                    "status": status,
                    "start_date": start_date,
                    "end_date": end_date,
                    "limit": limit,
                    "total_found": len(ads),
                    "ads": ads,
                    "extracted_at": datetime.now().isoformat()
                }

        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _run_scraper)
