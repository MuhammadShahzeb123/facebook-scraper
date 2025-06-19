#!/usr/bin/env python3
"""
Page Scraper API Wrapper
Integrates the existing page scraping functionality into async API calls
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime
from urllib.parse import urlparse, parse_qs

from seleniumbase import SB
from selenium.common.exceptions import TimeoutException, NoSuchElementException

class PageScraperAPI:
    """API wrapper for Facebook page scraping functionality"""

    def __init__(self):
        self.config_file = Path("config.json")
        self.account_number = 2  # Default account

    def load_account_config(self) -> tuple[list, str]:
        """Load account cookies and proxy configuration"""
        try:
            cfg = json.loads(self.config_file.read_text("utf-8"))
            acc = cfg["accounts"][str(self.account_number)]

            raw_cookies = acc["cookies"]
            cookies = [self._sanitize_cookie(c) for c in raw_cookies]

            proxy_parts = acc["proxy"].split(",", 3)
            proxy_string = f"{proxy_parts[2]}:{proxy_parts[3]}@{proxy_parts[0]}:{proxy_parts[1]}"

            return cookies, proxy_string
        except Exception as e:
            raise Exception(f"Failed to load account config: {e}")

    def _sanitize_cookie(self, cookie: dict) -> dict:
        """Sanitize cookie for selenium"""
        sanitized = cookie.copy()
        if "sameSite" in sanitized:
            if sanitized["sameSite"].lower() not in {"strict", "lax", "none"}:
                sanitized["sameSite"] = "None"
        return sanitized

    def wait_click(self, sb: SB, selector: str, *, by="xpath", timeout=10):
        """Safe click with wait"""
        try:
            sb.wait_for_element_visible(selector, by=by, timeout=timeout)
            sb.click(selector, by=by)
            return True
        except:
            return False

    def safe_click(self, sb: SB, element):
        """Safe click on web element"""
        try:
            element.click()
            return True
        except:
            return False

    def get_texts_by_xpath(self, sb: SB, xpath: str) -> List[str]:
        """Get all text content from xpath matches"""
        try:
            elements = sb.find_elements(xpath, by="xpath")
            return [elem.text.strip() for elem in elements if elem.text.strip()]
        except:
            return []

    def get_texts_by_class(self, sb: SB, class_name: str) -> List[str]:
        """Get all text content from class matches"""
        try:
            elements = sb.find_elements(f"//div[@class='{class_name}']", by="xpath")
            return [elem.text.strip() for elem in elements if elem.text.strip()]
        except:
            return []

    def extract_home_data(self, sb: SB) -> Dict[str, Any]:
        """Extract basic page information from home page"""
        data = {}

        try:
            # Page name
            page_name = sb.find_element("//h1", by="xpath").text.strip()
            data["page_name"] = page_name
        except:
            pass

        try:
            # Profile picture
            profile_img = sb.find_element("//div[@role='banner']//img", by="xpath")
            data["profile_pic"] = profile_img.get_attribute("src")
        except:
            pass

        try:
            # Follower count
            followers_element = sb.find_element("//a[contains(@href, 'followers')]", by="xpath")
            data["followers"] = followers_element.text.strip()
        except:
            pass

        try:
            # Page category
            category_elements = sb.find_elements("//span[contains(text(), '·')]", by="xpath")
            for element in category_elements:
                text = element.text.strip()
                if "·" in text and len(text) < 100:
                    data["category"] = text.replace("·", "").strip()
                    break
        except:
            pass

        try:
            # About/Intro section
            about_section = sb.find_element("//div[@data-pagelet='ProfileTilesFeed']", by="xpath")
            data["about"] = about_section.text.strip()
        except:
            pass

        return data

    def extract_posts(self, sb: SB, limit: int = 100) -> List[Dict[str, Any]]:
        """Extract posts from the page"""
        posts = []

        # Scroll to load posts
        for i in range(6):  # Adjust scroll count as needed
            sb.execute_script("window.scrollBy(0, 1500);")
            time.sleep(2)

        try:
            # Find post containers
            post_elements = sb.find_elements("//div[@role='article']", by="xpath")

            for i, post_element in enumerate(post_elements):
                if i >= limit:
                    break

                try:
                    post_data = {}

                    # Post text content
                    try:
                        text_element = post_element.find_element("xpath", ".//div[@data-ad-preview='message']")
                        post_data["text"] = text_element.text.strip()
                    except:
                        try:
                            # Alternative text extraction
                            text_elements = post_element.find_elements("xpath", ".//span[@dir='auto']")
                            text_content = []
                            for elem in text_elements:
                                text = elem.text.strip()
                                if text and len(text) > 10:  # Filter short/empty text
                                    text_content.append(text)
                            if text_content:
                                post_data["text"] = " ".join(text_content[:3])  # Take first 3 meaningful texts
                        except:
                            pass

                    # Post timestamp
                    try:
                        time_element = post_element.find_element("xpath", ".//a[contains(@href, '/posts/') or contains(@href, '/videos/')]")
                        post_data["timestamp"] = time_element.get_attribute("aria-label") or ""
                    except:
                        pass

                    # Post URL
                    try:
                        link_element = post_element.find_element("xpath", ".//a[contains(@href, '/posts/') or contains(@href, '/videos/')]")
                        post_data["post_url"] = link_element.get_attribute("href")
                    except:
                        pass

                    # Post images
                    try:
                        image_elements = post_element.find_elements("xpath", ".//img")
                        images = []
                        for img in image_elements:
                            src = img.get_attribute("src")
                            if src and "scontent" in src:  # Facebook content images
                                images.append(src)
                        if images:
                            post_data["images"] = images
                    except:
                        pass

                    # Engagement metrics (likes, comments, shares)
                    try:
                        reaction_elements = post_element.find_elements("xpath", ".//span[@aria-label and contains(@aria-label, 'reaction')]")
                        if reaction_elements:
                            post_data["reactions"] = reaction_elements[0].get_attribute("aria-label")
                    except:
                        pass

                    if post_data:  # Only add if we extracted some data
                        post_data["post_index"] = i
                        posts.append(post_data)

                except Exception:
                    continue

        except Exception:
            pass

        return posts

    def extract_contact_info(self, sb: SB) -> Dict[str, Any]:
        """Extract contact information from About page"""
        contact_info = {}

        try:
            # Navigate to About tab
            about_tab = sb.find_element("//span[text()='About']/ancestor::*[@role='tab' or @role='link'][1]", by="xpath")
            about_tab.click()
            time.sleep(2)

            # Website
            try:
                website_elements = sb.find_elements("//a[contains(@href, 'http') and not(contains(@href, 'facebook.com'))]", by="xpath")
                if website_elements:
                    contact_info["website"] = website_elements[0].get_attribute("href")
            except:
                pass

            # Phone
            try:
                phone_elements = sb.find_elements("//a[contains(@href, 'tel:')]", by="xpath")
                if phone_elements:
                    contact_info["phone"] = phone_elements[0].get_attribute("href").replace("tel:", "")
            except:
                pass

            # Email
            try:
                email_elements = sb.find_elements("//a[contains(@href, 'mailto:')]", by="xpath")
                if email_elements:
                    contact_info["email"] = email_elements[0].get_attribute("href").replace("mailto:", "")
            except:
                pass

            # Address
            try:
                address_elements = sb.find_elements("//div[contains(text(), 'Address') or contains(text(), 'Location')]/following-sibling::div", by="xpath")
                if address_elements:
                    contact_info["address"] = address_elements[0].text.strip()
            except:
                pass

        except:
            pass

        return contact_info

    def extract_transparency_info(self, sb: SB) -> Dict[str, Any]:
        """Extract page transparency information"""
        transparency_info = {}

        try:
            # Look for transparency link
            transparency_link = sb.find_element("//span[contains(text(),'Page transparency')]/ancestor::a[1]", by="xpath")
            transparency_link.click()
            time.sleep(3)

            # Page ID
            try:
                page_id_element = sb.find_element("//div[contains(text(), 'Page ID')]/following-sibling::div//span", by="xpath")
                transparency_info["page_id"] = page_id_element.text.strip()
            except:
                pass

            # Creation date
            try:
                creation_date_element = sb.find_element("//div[contains(text(), 'Creation date')]/following-sibling::div//span", by="xpath")
                transparency_info["creation_date"] = creation_date_element.text.strip()
            except:
                pass

            # Go back
            sb.driver.back()
            time.sleep(2)

        except:
            pass

        return transparency_info

    def normalize_facebook_url(self, url: str) -> str:
        """Normalize Facebook URL to handle different formats"""
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        # Handle profile.php URLs
        parsed = urlparse(url)
        if 'profile.php' in parsed.path:
            query_params = parse_qs(parsed.query)
            if 'id' in query_params:
                return f"https://www.facebook.com/profile.php?id={query_params['id'][0]}"

        return url

    async def extract_page(self, url: str, extract_posts: bool = True, post_limit: int = 100) -> Dict[str, Any]:
        """
        Main async method to extract Facebook page data
        """

        def _run_scraper():
            try:
                cookies, proxy_string = self.load_account_config()

                with SB(headless=True, proxy=proxy_string) as sb:
                    # Load Facebook with cookies
                    sb.open("https://facebook.com")
                    for ck in cookies:
                        try:
                            sb.driver.add_cookie(ck)
                        except Exception:
                            pass

                    # Navigate to the target page
                    normalized_url = self.normalize_facebook_url(url)
                    sb.open(normalized_url)
                    time.sleep(5)

                    # Extract basic page data
                    page_data = self.extract_home_data(sb)
                    page_data["url"] = normalized_url
                    page_data["original_url"] = url

                    # Extract posts if requested
                    if extract_posts:
                        posts = self.extract_posts(sb, limit=post_limit)
                        page_data["posts"] = posts
                        page_data["posts_count"] = len(posts)

                    # Extract contact information
                    contact_info = self.extract_contact_info(sb)
                    if contact_info:
                        page_data["contact_info"] = contact_info

                    # Extract transparency information
                    transparency_info = self.extract_transparency_info(sb)
                    if transparency_info:
                        page_data["transparency_info"] = transparency_info

                    page_data["extracted_at"] = datetime.now().isoformat()
                    page_data["extraction_parameters"] = {
                        "extract_posts": extract_posts,
                        "post_limit": post_limit
                    }

                    return page_data

            except Exception as e:
                return {
                    "error": str(e),
                    "url": url,
                    "extracted_at": datetime.now().isoformat()
                }

        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _run_scraper)
