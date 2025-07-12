#!/usr/bin/env python3
"""
Facebook Proxy Connectivity Diagnostic Tool

This script helps diagnose proxy connectivity issues when getting ERR_EMPTY_RESPONSE from Facebook.
"""

import json
import logging
import requests
import time
from pathlib import Path
from proxy_utils_enhanced import load_proxies, test_proxy_connection, create_proxy_health_report

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('proxy_diagnostics.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def test_direct_facebook_access():
    """Test if Facebook is accessible without proxy."""
    print("\n" + "="*60)
    print("TESTING DIRECT FACEBOOK ACCESS (NO PROXY)")
    print("="*60)

    test_urls = [
        'https://www.facebook.com',
        'https://m.facebook.com',
        'https://facebook.com/login',
        'https://www.facebook.com/robots.txt'
    ]

    for url in test_urls:
        try:
            print(f"\nTesting: {url}")
            response = requests.get(url, timeout=10, allow_redirects=False)
            print(f"✅ Status: {response.status_code}")
            print(f"   Headers: {dict(list(response.headers.items())[:3])}")

        except Exception as e:
            print(f"❌ Failed: {e}")

def test_proxy_facebook_access():
    """Test Facebook access through each proxy."""
    print("\n" + "="*60)
    print("TESTING FACEBOOK ACCESS THROUGH PROXIES")
    print("="*60)

    proxies = load_proxies()
    if not proxies:
        print("❌ No proxies found in proxies.json")
        return

    facebook_urls = [
        'https://www.facebook.com',
        'https://m.facebook.com',
        'http://www.facebook.com'  # Try HTTP instead of HTTPS
    ]

    for i, proxy_tuple in enumerate(proxies, 1):
        host, port, username, password = proxy_tuple
        print(f"\n--- PROXY {i}: {username}@{host}:{port} ---")

        proxy_url = f"http://{username}:{password}@{host}:{port}"
        proxy_config = {
            'http': proxy_url,
            'https': proxy_url
        }

        for url in facebook_urls:
            try:
                print(f"Testing {url}")
                response = requests.get(
                    url,
                    proxies=proxy_config,
                    timeout=15,
                    allow_redirects=False,
                    headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                    }
                )
                print(f"✅ Status: {response.status_code}")
                if response.status_code == 200:
                    print(f"   Content length: {len(response.content)} bytes")

            except requests.exceptions.ProxyError as e:
                print(f"❌ Proxy Error: {e}")
            except requests.exceptions.ConnectTimeout as e:
                print(f"❌ Connection Timeout: {e}")
            except requests.exceptions.ConnectionError as e:
                print(f"❌ Connection Error: {e}")
            except Exception as e:
                print(f"❌ Other Error: {e}")

        time.sleep(2)  # Delay between proxy tests

def test_proxy_basic_connectivity():
    """Test basic proxy connectivity to non-Facebook sites."""
    print("\n" + "="*60)
    print("TESTING BASIC PROXY CONNECTIVITY")
    print("="*60)

    proxies = load_proxies()
    if not proxies:
        print("❌ No proxies found in proxies.json")
        return

    test_sites = [
        'http://httpbin.org/ip',
        'https://www.google.com',
        'https://httpbin.org/headers',
        'http://www.example.com'
    ]

    for i, proxy_tuple in enumerate(proxies, 1):
        host, port, username, password = proxy_tuple
        print(f"\n--- PROXY {i}: {username}@{host}:{port} ---")

        working_sites = 0
        for site in test_sites:
            if test_single_site_through_proxy(proxy_tuple, site):
                working_sites += 1

        print(f"Summary: {working_sites}/{len(test_sites)} sites accessible")

        time.sleep(1)

def test_single_site_through_proxy(proxy_tuple, url):
    """Test a single site through a proxy."""
    host, port, username, password = proxy_tuple
    proxy_url = f"http://{username}:{password}@{host}:{port}"

    try:
        response = requests.get(
            url,
            proxies={'http': proxy_url, 'https': proxy_url},
            timeout=10,
            allow_redirects=False
        )
        print(f"✅ {url}: {response.status_code}")
        return True
    except Exception as e:
        print(f"❌ {url}: {str(e)[:50]}...")
        return False

def diagnose_err_empty_response():
    """Main diagnostic function for ERR_EMPTY_RESPONSE issues."""
    print("Facebook Proxy Connectivity Diagnostics")
    print("=" * 60)
    print("This tool will help diagnose ERR_EMPTY_RESPONSE issues with Facebook scraping.")
    print()

    # Check if proxies.json exists
    if not Path("proxies.json").exists():
        print("❌ ERROR: proxies.json file not found!")
        print("Please ensure proxies.json exists with your proxy configuration.")
        return

    # Load and validate proxies
    proxies = load_proxies()
    print(f"📊 Found {len(proxies)} proxies in configuration")

    if not proxies:
        print("❌ No valid proxies found. Please check your proxies.json format.")
        return

    # Test 1: Direct Facebook access
    test_direct_facebook_access()

    # Test 2: Basic proxy connectivity
    test_proxy_basic_connectivity()

    # Test 3: Facebook through proxies
    test_proxy_facebook_access()

    # Test 4: Generate health report
    print("\n" + "="*60)
    print("PROXY HEALTH REPORT")
    print("="*60)
    health_report = create_proxy_health_report()

    print(f"Total proxies: {health_report['total_proxies']}")
    print(f"Working proxies: {health_report['working_proxies']}")
    print(f"Failed proxies: {health_report['failed_proxies']}")

    if health_report['working_proxies'] == 0:
        print("\n❌ CRITICAL: No working proxies found!")
        print("Possible causes:")
        print("1. Proxy servers are down or unreachable")
        print("2. Proxy credentials are incorrect")
        print("3. Proxy servers are blocked by your ISP")
        print("4. Facebook is blocking your proxy IP addresses")

    # Generate recommendations
    print("\n" + "="*60)
    print("RECOMMENDATIONS")
    print("="*60)

    if health_report['working_proxies'] > 0:
        working_count = health_report['working_proxies']
        total_count = health_report['total_proxies']

        if working_count == total_count:
            print("✅ All proxies are working for basic connectivity")
            print("   The ERR_EMPTY_RESPONSE issue might be:")
            print("   - Facebook detecting and blocking proxy IPs")
            print("   - Rate limiting from Facebook")
            print("   - Need for more realistic browser headers/behavior")
        else:
            print(f"⚠️  Only {working_count}/{total_count} proxies are working")
            print("   Consider:")
            print("   - Removing failed proxies from configuration")
            print("   - Contacting proxy provider about failed IPs")
            print("   - Testing at different times of day")

    print("\nNext steps:")
    print("1. If all proxies fail basic connectivity: Check proxy credentials")
    print("2. If proxies work but Facebook fails: Try different proxy IPs")
    print("3. Consider using residential proxies instead of datacenter proxies")
    print("4. Test with different user agents and browser behaviors")

    print(f"\nDiagnostic results saved to: proxy_diagnostics.log")

def test_selenium_proxy_integration():
    """Test if SeleniumBase can use the proxies properly."""
    print("\n" + "="*60)
    print("TESTING SELENIUMBASE PROXY INTEGRATION")
    print("="*60)

    try:
        from seleniumbase import SB
        from proxy_utils_enhanced import get_proxy_string_with_fallback

        proxy_string = get_proxy_string_with_fallback()
        if not proxy_string:
            print("❌ No proxy available for SeleniumBase test")
            return

        print(f"Testing SeleniumBase with proxy: {proxy_string.split('@')[-1] if '@' in proxy_string else proxy_string}")

        with SB(uc=True, proxy=proxy_string, headless=True) as sb:
            # Test 1: Check IP
            sb.open("http://httpbin.org/ip")
            ip_info = sb.get_text("body")
            print(f"✅ IP through proxy: {ip_info}")

            # Test 2: Try Facebook
            try:
                sb.open("https://www.facebook.com", timeout=15)
                title = sb.get_title()
                print(f"✅ Facebook title: {title}")
            except Exception as e:
                print(f"❌ Facebook failed: {e}")

    except ImportError:
        print("❌ SeleniumBase not installed. Cannot test browser integration.")
    except Exception as e:
        print(f"❌ SeleniumBase test failed: {e}")

def main():
    """Run full diagnostic suite."""
    print("Starting comprehensive proxy diagnostics...")
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    diagnose_err_empty_response()
    test_selenium_proxy_integration()

    print("\n" + "="*60)
    print("DIAGNOSTIC COMPLETE")
    print("="*60)
    print("Check proxy_diagnostics.log for detailed logs")

if __name__ == "__main__":
    main()
