#!/usr/bin/env python3
"""
Advertiser Scraper API Wrapper
Integrates the existing advertiser scraping functionality into async API calls
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

from seleniumbase import SB
from selenium.common.exceptions import TimeoutException, NoSuchElementException

class AdvertiserScraperAPI:
    """API wrapper for Facebook advertiser scraping functionality"""

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

    def extract_advertiser_suggestions(self, sb: SB, keyword: str) -> List[Dict[str, Any]]:
        """Extract advertiser suggestions from search dropdown"""
        suggestions = []
        keyword_input = ('//input[@type="search" and contains(@placeholder,"keyword") '
                        'and not(@aria-disabled="true")]')

        # Type without Enter to keep dropdown open
        self.safe_type(sb, keyword_input, keyword, by="xpath", press_enter=False)
        time.sleep(3)

        # Harvest suggestion items
        try:
            items = sb.find_elements("//li[@role='option']", by="xpath")
            for item in items:
                try:
                    raw_text = item.text.strip()
                    lines = raw_text.split("\n")

                    data = {
                        "page_id": item.get_attribute("id") or "",
                        "name": lines[0].strip() if lines else "",
                        "description": lines[1].strip() if len(lines) > 1 else "",
                        "raw_text": raw_text,
                        "is_advertiser": True
                    }
                    if data["name"]:
                        suggestions.append(data)
                except Exception:
                    continue
        except Exception:
            pass

        # Clear search box
        try:
            sb.find_element(keyword_input, by="xpath").clear()
        except:
            pass

        return suggestions

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
        """Parse individual ad card for advertiser info"""
        import re
        from urllib.parse import urlparse

        def _t(xp: str) -> str | None:
            try:
                return card.find_element("xpath", xp).text.strip()
            except NoSuchElementException:
                return None

        # Extract advertiser/page info
        page_name = _t('.//a[starts-with(@href,"https://www.facebook.com/")][1]')
        page_link = None
        try:
            page_element = card.find_element("xpath", './/a[starts-with(@href,"https://www.facebook.com/")][1]')
            page_link = page_element.get_attribute("href")
        except:
            pass

        # Extract library ID for this advertiser
        lib_raw = _t('.//span[contains(text(),"Library ID")]')
        library_id = lib_raw.split(":",1)[-1].strip() if lib_raw else None

        return {
            "advertiser_name": page_name,
            "page_url": page_link,
            "library_id": library_id,
            "raw_text": card.text.strip(),
        }

    def extract_advertisers_from_search(self, sb: SB) -> List[Dict[str, Any]]:
        """Extract unique advertisers from search results"""
        sb.execute_script("window.scrollBy(0, 800);")
        time.sleep(1)

        prefix = self._detect_card_prefix(sb)
        if not prefix:
            return []

        try:
            sb.wait_for_element_visible(f"{prefix}/div[1]/div", by="xpath", timeout=15)
        except:
            return []

        advertisers = {}  # Use dict to avoid duplicates
        n = 1

        while True:
            xpath = f"{prefix}/div[{n}]/div"
            try:
                card_ele = sb.driver.find_element("xpath", xpath)
            except NoSuchElementException:
                break

            try:
                advertiser_data = self._parse_card(card_ele)
                advertiser_name = advertiser_data.get("advertiser_name")
                if advertiser_name and advertiser_name not in advertisers:
                    advertisers[advertiser_name] = advertiser_data
            except Exception:
                pass
            n += 1

        return list(advertisers.values())

    def scrape_advertiser_page(self, sb: SB, page_url: str) -> Dict[str, Any]:
        """Scrape individual advertiser page data"""
        try:
            sb.open(page_url)
            time.sleep(3)

            page_data = {}

            # Extract page name
            try:
                page_name = sb.find_element("//h1", by="xpath").text.strip()
                page_data["page_name"] = page_name
            except:
                pass

            # Extract follower count
            try:
                followers_element = sb.find_element("//a[contains(@href, 'followers')]", by="xpath")
                followers_text = followers_element.text.strip()
                page_data["followers"] = followers_text
            except:
                pass

            # Extract page category
            try:
                category_elements = sb.find_elements("//span[contains(text(), '·')]", by="xpath")
                for element in category_elements:
                    text = element.text.strip()
                    if "·" in text and len(text) < 100:
                        page_data["category"] = text.replace("·", "").strip()
                        break
            except:
                pass

            # Extract about section
            try:
                about_section = sb.find_element("//div[@data-pagelet='ProfileTilesFeed']", by="xpath")
                page_data["about"] = about_section.text.strip()
            except:
                pass

            # Extract contact info
            try:
                contact_info = {}

                # Website
                try:
                    website_link = sb.find_element("//a[contains(@href, 'http') and not(contains(@href, 'facebook.com'))]", by="xpath")
                    contact_info["website"] = website_link.get_attribute("href")
                except:
                    pass

                # Phone (if visible)
                try:
                    phone_elements = sb.find_elements("//a[contains(@href, 'tel:')]", by="xpath")
                    if phone_elements:
                        contact_info["phone"] = phone_elements[0].get_attribute("href").replace("tel:", "")
                except:
                    pass

                if contact_info:
                    page_data["contact_info"] = contact_info
            except:
                pass

            return page_data

        except Exception as e:
            return {"error": f"Failed to scrape page: {str(e)}"}

    async def search_advertisers(self, keyword: str, scrape_page: bool = True) -> Dict[str, Any]:
        """
        Main async method to search for advertisers
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

                # Get suggestions first
                suggestions = self.extract_advertiser_suggestions(sb, keyword)

                # Search for ads to find advertisers
                key_box = ('//input[@type="search" and contains(@placeholder,"keyword") '
                          'and not(@aria-disabled="true")]')
                self.safe_type(sb, key_box, keyword, by="xpath", press_enter=True)
                sb.sleep(4)

                # Scroll to load more results
                for i in range(3):
                    self.human_scroll(sb)
                    sb.sleep(2 + i * 0.5)

                # Extract advertisers from search results
                advertisers_from_search = self.extract_advertisers_from_search(sb)

                # Combine suggestions and search results
                all_advertisers = []
                seen_names = set()

                # Add suggestions
                for suggestion in suggestions:
                    name = suggestion.get("name")
                    if name and name not in seen_names:
                        seen_names.add(name)
                        all_advertisers.append({
                            "advertiser_name": name,
                            "source": "suggestion",
                            "page_id": suggestion.get("page_id"),
                            "description": suggestion.get("description"),
                            "raw_text": suggestion.get("raw_text")
                        })

                # Add search results
                for advertiser in advertisers_from_search:
                    name = advertiser.get("advertiser_name")
                    if name and name not in seen_names:
                        seen_names.add(name)
                        advertiser["source"] = "search_result"
                        all_advertisers.append(advertiser)

                # Scrape individual pages if requested
                if scrape_page:
                    for i, advertiser in enumerate(all_advertisers):
                        page_url = advertiser.get("page_url")
                        if page_url:
                            try:
                                page_data = self.scrape_advertiser_page(sb, page_url)
                                advertiser["page_data"] = page_data
                            except Exception as e:
                                advertiser["page_data"] = {"error": str(e)}

                return {
                    "keyword": keyword,
                    "total_found": len(all_advertisers),
                    "advertisers": all_advertisers,
                    "scraped_pages": scrape_page,
                    "extracted_at": datetime.now().isoformat()
                }

        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _run_scraper)
