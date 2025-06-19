#!/usr/bin/env python3
"""
Unit tests for Facebook Scraper API
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
import json

from app import app
from ads_scraper_api import AdsScraperAPI
from advertiser_scraper_api import AdvertiserScraperAPI
from page_scraper_api import PageScraperAPI
from post_scraper_api import PostScraperAPI

# Test client
client = TestClient(app)

class TestAPIEndpoints:
    """Test API endpoints"""

    def test_health_check(self):
        """Test health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        assert "status" in response.json()
        assert response.json()["status"] == "healthy"

    def test_status_endpoint(self):
        """Test status endpoint"""
        response = client.get("/status")
        assert response.status_code == 200
        data = response.json()
        assert "api_version" in data
        assert "endpoints" in data
        assert len(data["endpoints"]) == 4

    @patch('ads_scraper_api.AdsScraperAPI.search_ads')
    def test_ads_search_endpoint(self, mock_search_ads):
        """Test ads search endpoint"""
        # Mock response
        mock_response = {
            "keyword": "test",
            "location": "thailand",
            "total_found": 5,
            "ads": [
                {
                    "library_id": "123",
                    "status": "Active",
                    "page": "Test Page",
                    "primary_text": "Test ad content"
                }
            ]
        }
        mock_search_ads.return_value = mock_response

        response = client.get("/ads_search?keyword=test")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert "data" in data

    def test_ads_search_missing_keyword(self):
        """Test ads search without required keyword parameter"""
        response = client.get("/ads_search")
        assert response.status_code == 422  # Validation error

    @patch('advertiser_scraper_api.AdvertiserScraperAPI.search_advertisers')
    def test_advertiser_search_endpoint(self, mock_search_advertisers):
        """Test advertiser search endpoint"""
        mock_response = {
            "keyword": "test",
            "total_found": 3,
            "advertisers": [
                {
                    "advertiser_name": "Test Advertiser",
                    "page_url": "https://facebook.com/testadvertiser"
                }
            ]
        }
        mock_search_advertisers.return_value = mock_response

        response = client.get("/advertiser_search?keyword=test")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True

    @patch('page_scraper_api.PageScraperAPI.extract_page')
    def test_page_extract_endpoint(self, mock_extract_page):
        """Test page extract endpoint"""
        mock_response = {
            "page_name": "Test Page",
            "url": "https://facebook.com/testpage",
            "posts": []
        }
        mock_extract_page.return_value = mock_response

        response = client.get("/page_extract?url=https://facebook.com/testpage")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True

    def test_page_extract_invalid_url(self):
        """Test page extract with invalid URL"""
        response = client.get("/page_extract?url=https://google.com")
        assert response.status_code == 400

    @patch('post_scraper_api.PostScraperAPI.extract_post')
    def test_post_extract_endpoint(self, mock_extract_post):
        """Test post extract endpoint"""
        mock_response = {
            "post_id": "123",
            "text": "Test post content",
            "author_name": "Test Author"
        }
        mock_extract_post.return_value = mock_response

        response = client.get("/post_extract?url=https://facebook.com/share/p/123/")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True

class TestAdsScraperAPI:
    """Test AdsScraperAPI class"""

    def test_init(self):
        """Test AdsScraperAPI initialization"""
        scraper = AdsScraperAPI()
        assert scraper.cookie_file.name == "facebook_cookies.txt"
        assert "ads/library" in scraper.ad_library_url

    def test_load_cookies_file_not_found(self):
        """Test load_cookies when file doesn't exist"""
        scraper = AdsScraperAPI()
        scraper.cookie_file = "nonexistent_file.txt"

        with pytest.raises(FileNotFoundError):
            scraper.load_cookies()

    @patch('builtins.open', mock_open=True)
    @patch('json.loads')
    def test_load_cookies_success(self, mock_json_loads):
        """Test successful cookie loading"""
        mock_cookies = [
            {"name": "test", "value": "value", "sameSite": "invalid"},
            {"name": "test2", "value": "value2", "sameSite": "lax"}
        ]
        mock_json_loads.return_value = mock_cookies

        scraper = AdsScraperAPI()
        with patch('pathlib.Path.exists', return_value=True):
            with patch('pathlib.Path.read_text', return_value='[]'):
                cookies = scraper.load_cookies()
                assert len(cookies) == 2
                assert cookies[0]["sameSite"] == "None"  # Invalid sameSite corrected
                assert cookies[1]["sameSite"] == "lax"   # Valid sameSite preserved

class TestAdvertiserScraperAPI:
    """Test AdvertiserScraperAPI class"""

    def test_init(self):
        """Test AdvertiserScraperAPI initialization"""
        scraper = AdvertiserScraperAPI()
        assert scraper.cookie_file.name == "facebook_cookies.txt"

    def test_extract_advertiser_suggestions_empty(self):
        """Test empty suggestions extraction"""
        scraper = AdvertiserScraperAPI()

        # Mock SeleniumBase
        mock_sb = Mock()
        mock_sb.find_elements.return_value = []

        suggestions = scraper.extract_advertiser_suggestions(mock_sb, "test")
        assert suggestions == []

class TestPageScraperAPI:
    """Test PageScraperAPI class"""

    def test_init(self):
        """Test PageScraperAPI initialization"""
        scraper = PageScraperAPI()
        assert scraper.config_file.name == "config.json"
        assert scraper.account_number == 2

    def test_normalize_facebook_url(self):
        """Test Facebook URL normalization"""
        scraper = PageScraperAPI()

        # Test regular URL
        url1 = "facebook.com/testpage"
        normalized1 = scraper.normalize_facebook_url(url1)
        assert normalized1.startswith("https://")

        # Test profile.php URL
        url2 = "https://facebook.com/profile.php?id=123456"
        normalized2 = scraper.normalize_facebook_url(url2)
        assert "profile.php?id=123456" in normalized2

    def test_sanitize_cookie(self):
        """Test cookie sanitization"""
        scraper = PageScraperAPI()

        cookie = {"name": "test", "sameSite": "invalid_value"}
        sanitized = scraper._sanitize_cookie(cookie)
        assert sanitized["sameSite"] == "None"

class TestPostScraperAPI:
    """Test PostScraperAPI class"""

    def test_init(self):
        """Test PostScraperAPI initialization"""
        scraper = PostScraperAPI()
        assert scraper.config_file.name == "config.json"

    def test_extract_post_id_from_url(self):
        """Test post ID extraction from various URL formats"""
        scraper = PostScraperAPI()

        # Test /posts/ format
        url1 = "https://facebook.com/page/posts/123456789"
        post_id1 = scraper.extract_post_id_from_url(url1)
        assert post_id1 == "123456789"

        # Test /share/p/ format
        url2 = "https://facebook.com/share/p/ABC123DEF/"
        post_id2 = scraper.extract_post_id_from_url(url2)
        assert post_id2 == "ABC123DEF"

        # Test unknown format
        url3 = "https://facebook.com/unknown/format"
        post_id3 = scraper.extract_post_id_from_url(url3)
        assert post_id3 == "unknown"

    def test_normalize_post_url(self):
        """Test post URL normalization"""
        scraper = PostScraperAPI()

        # Test URL without protocol
        url1 = "facebook.com/share/p/123/"
        normalized1 = scraper.normalize_post_url(url1)
        assert normalized1.startswith("https://")

        # Test URL with query parameters
        url2 = "https://facebook.com/share/p/123/?ref=share"
        normalized2 = scraper.normalize_post_url(url2)
        assert "?" not in normalized2

class TestUtilityFunctions:
    """Test utility functions from app.py"""

    def test_validate_facebook_url(self):
        """Test Facebook URL validation"""
        from app import validate_facebook_url

        # Valid URLs
        assert validate_facebook_url("https://facebook.com/page") == True
        assert validate_facebook_url("https://www.facebook.com/page") == True
        assert validate_facebook_url("https://m.facebook.com/page") == True

        # Invalid URLs
        assert validate_facebook_url("https://google.com") == False
        assert validate_facebook_url("invalid-url") == False

    def test_normalize_facebook_url(self):
        """Test Facebook URL normalization utility"""
        from app import normalize_facebook_url

        # Test regular URL
        url1 = "facebook.com/page"
        normalized1 = normalize_facebook_url(url1)
        assert normalized1.startswith("https://")

        # Test profile URL
        url2 = "https://facebook.com/profile.php?id=123&extra=param"
        normalized2 = normalize_facebook_url(url2)
        assert "profile.php?id=123" in normalized2

class TestRateLimiting:
    """Test rate limiting functionality"""

    def test_rate_limit_check(self):
        """Test rate limiting logic"""
        from app import rate_limit_check, request_tracker

        # Clear tracker
        request_tracker.clear()

        # Test within limit
        for i in range(5):
            assert rate_limit_check("127.0.0.1", limit=10, window=60) == True

        # Test exceed limit
        for i in range(10):
            rate_limit_check("127.0.0.1", limit=5, window=60)

        assert rate_limit_check("127.0.0.1", limit=5, window=60) == False

# Integration Tests
class TestAPIIntegration:
    """Integration tests for API endpoints"""

    def test_multiple_endpoint_calls(self):
        """Test calling multiple endpoints in sequence"""
        # Health check
        response1 = client.get("/health")
        assert response1.status_code == 200

        # Status
        response2 = client.get("/status")
        assert response2.status_code == 200

        # Invalid endpoint
        response3 = client.get("/nonexistent")
        assert response3.status_code == 404

# Performance Tests
class TestPerformance:
    """Basic performance tests"""

    def test_health_endpoint_response_time(self):
        """Test health endpoint response time"""
        import time

        start_time = time.time()
        response = client.get("/health")
        end_time = time.time()

        assert response.status_code == 200
        assert (end_time - start_time) < 1.0  # Should respond within 1 second

if __name__ == "__main__":
    pytest.main([__file__])
