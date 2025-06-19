#!/usr/bin/env python3
"""
Post Scraper API Wrapper
Integrates post scraping functionality into async API calls
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

class PostScraperAPI:
    """API wrapper for Facebook post scraping functionality"""

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

    def extract_post_content(self, sb: SB) -> Dict[str, Any]:
        """Extract comprehensive post data"""
        post_data = {}

        try:
            # Post text content
            text_selectors = [
                "//div[@data-ad-preview='message']",
                "//div[contains(@class, 'userContent')]",
                "//span[@dir='auto' and string-length(text()) > 10]"
            ]

            for selector in text_selectors:
                try:
                    text_elements = sb.find_elements(selector, by="xpath")
                    if text_elements:
                        texts = []
                        for elem in text_elements:
                            text = elem.text.strip()
                            if text and len(text) > 10:
                                texts.append(text)
                        if texts:
                            post_data["text"] = "\n".join(texts)
                            break
                except:
                    continue
        except:
            pass

        try:
            # Author information
            author_selectors = [
                "//h3//a[contains(@href, 'facebook.com')]",
                "//strong//a[contains(@href, 'facebook.com')]"
            ]

            for selector in author_selectors:
                try:
                    author_element = sb.find_element(selector, by="xpath")
                    post_data["author_name"] = author_element.text.strip()
                    post_data["author_url"] = author_element.get_attribute("href")
                    break
                except:
                    continue
        except:
            pass

        try:
            # Post timestamp
            timestamp_selectors = [
                "//abbr[@data-utime]",
                "//a[contains(@href, '/posts/')]/@aria-label",
                "//time"
            ]

            for selector in timestamp_selectors:
                try:
                    if "@aria-label" in selector:
                        time_element = sb.find_element("//a[contains(@href, '/posts/')]", by="xpath")
                        post_data["timestamp"] = time_element.get_attribute("aria-label")
                    elif "abbr" in selector:
                        time_element = sb.find_element(selector, by="xpath")
                        post_data["timestamp_unix"] = time_element.get_attribute("data-utime")
                        post_data["timestamp"] = time_element.get_attribute("title")
                    else:
                        time_element = sb.find_element(selector, by="xpath")
                        post_data["timestamp"] = time_element.get_attribute("datetime") or time_element.text
                    break
                except:
                    continue
        except:
            pass

        try:
            # Post images and media
            images = []
            video_urls = []

            # Images
            image_elements = sb.find_elements("//img[contains(@src, 'scontent')]", by="xpath")
            for img in image_elements:
                src = img.get_attribute("src")
                if src and ("scontent" in src or "fbcdn" in src):
                    images.append({
                        "url": src,
                        "alt": img.get_attribute("alt") or ""
                    })

            if images:
                post_data["images"] = images

            # Videos
            video_elements = sb.find_elements("//video", by="xpath")
            for video in video_elements:
                src = video.get_attribute("src")
                if src:
                    video_urls.append(src)

            if video_urls:
                post_data["videos"] = video_urls

        except:
            pass

        try:
            # Engagement metrics
            engagement = {}

            # Reactions/Likes
            reaction_selectors = [
                "//span[contains(@aria-label, 'reaction')]",
                "//span[contains(@aria-label, 'like')]",
                "//a[contains(@aria-label, 'people reacted')]"
            ]

            for selector in reaction_selectors:
                try:
                    reaction_element = sb.find_element(selector, by="xpath")
                    engagement["reactions"] = reaction_element.get_attribute("aria-label")
                    break
                except:
                    continue

            # Comments
            try:
                comment_elements = sb.find_elements("//a[contains(@aria-label, 'comment')]", by="xpath")
                if comment_elements:
                    engagement["comments"] = comment_elements[0].get_attribute("aria-label")
            except:
                pass

            # Shares
            try:
                share_elements = sb.find_elements("//a[contains(@aria-label, 'share')]", by="xpath")
                if share_elements:
                    engagement["shares"] = share_elements[0].get_attribute("aria-label")
            except:
                pass

            if engagement:
                post_data["engagement"] = engagement

        except:
            pass

        try:
            # Extract comments (first few)
            comments = []
            comment_elements = sb.find_elements("//div[@role='article']//div[contains(@class, 'comment')]", by="xpath")

            for i, comment_elem in enumerate(comment_elements[:5]):  # Limit to first 5 comments
                try:
                    comment_data = {}

                    # Comment author
                    author_link = comment_elem.find_element("xpath", ".//a[contains(@href, 'facebook.com')]")
                    comment_data["author"] = author_link.text.strip()
                    comment_data["author_url"] = author_link.get_attribute("href")

                    # Comment text
                    text_element = comment_elem.find_element("xpath", ".//span[@dir='auto']")
                    comment_data["text"] = text_element.text.strip()

                    comments.append(comment_data)
                except:
                    continue

            if comments:
                post_data["comments"] = comments

        except:
            pass

        try:
            # External links in post
            external_links = []
            link_elements = sb.find_elements("//a[contains(@href, 'http') and not(contains(@href, 'facebook.com'))]", by="xpath")

            for link in link_elements:
                href = link.get_attribute("href")
                text = link.text.strip()
                if href:
                    external_links.append({
                        "url": href,
                        "text": text
                    })

            if external_links:
                post_data["external_links"] = external_links

        except:
            pass

        return post_data

    def extract_post_id_from_url(self, url: str) -> str:
        """Extract post ID from Facebook URL"""
        try:
            # Handle different URL formats
            if "/posts/" in url:
                post_id = url.split("/posts/")[1].split("/")[0].split("?")[0]
            elif "/share/p/" in url:
                post_id = url.split("/share/p/")[1].split("/")[0].split("?")[0]
            elif "story_fbid=" in url:
                parsed = urlparse(url)
                query_params = parse_qs(parsed.query)
                post_id = query_params.get("story_fbid", [""])[0]
            else:
                post_id = "unknown"

            return post_id
        except:
            return "unknown"

    def normalize_post_url(self, url: str) -> str:
        """Normalize Facebook post URL"""
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        # Remove tracking parameters
        if "?" in url:
            url = url.split("?")[0]

        return url

    async def extract_post(self, url: str) -> Dict[str, Any]:
        """
        Main async method to extract Facebook post data
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

                    # Navigate to the post
                    normalized_url = self.normalize_post_url(url)
                    sb.open(normalized_url)
                    time.sleep(5)

                    # Extract post data
                    post_data = self.extract_post_content(sb)

                    # Add metadata
                    post_data["url"] = normalized_url
                    post_data["original_url"] = url
                    post_data["post_id"] = self.extract_post_id_from_url(url)
                    post_data["extracted_at"] = datetime.now().isoformat()

                    # Try to get page context
                    try:
                        page_element = sb.find_element("//a[contains(@href, 'facebook.com') and not(contains(@href, '/posts/')) and not(contains(@href, '/share/'))]", by="xpath")
                        post_data["page_context"] = {
                            "page_name": page_element.text.strip(),
                            "page_url": page_element.get_attribute("href")
                        }
                    except:
                        pass

                    return post_data

            except Exception as e:
                return {
                    "error": str(e),
                    "url": url,
                    "post_id": self.extract_post_id_from_url(url),
                    "extracted_at": datetime.now().isoformat()
                }

        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _run_scraper)
