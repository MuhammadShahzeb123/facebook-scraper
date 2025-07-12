#!/usr/bin/env python3
"""
Enhanced proxy utility with connection testing and health checking
"""

import json
import random
import logging
import time
import requests
from pathlib import Path
from typing import List, Tuple, Optional, Dict

logger = logging.getLogger(__name__)

PROXIES_FILE = Path("proxies.json")

def load_proxies() -> List[Tuple[str, str, str, str]]:
    """
    Load proxies from proxies.json file.

    Returns:
        List of tuples: (host, port, username, password)
    """
    try:
        if not PROXIES_FILE.exists():
            logger.warning(f"Proxies file {PROXIES_FILE} not found. Running without proxy.")
            return []

        with open(PROXIES_FILE, 'r', encoding='utf-8') as f:
            proxy_strings = json.load(f)

        proxies = []
        for proxy_string in proxy_strings:
            try:
                if isinstance(proxy_string, str) and ',' in proxy_string:
                    # Format: "host,port,username,password"
                    parts = proxy_string.split(',', 3)
                    if len(parts) == 4:
                        host, port, username, password = parts
                        proxies.append((host.strip(), port.strip(), username.strip(), password.strip()))
                    else:
                        logger.warning(f"Invalid proxy format (expected 4 parts): {proxy_string}")
                else:
                    logger.warning(f"Invalid proxy format (not a comma-separated string): {proxy_string}")
            except Exception as e:
                logger.error(f"Error parsing proxy: {proxy_string} -> {e}")

        logger.info(f"Loaded {len(proxies)} proxies from {PROXIES_FILE}")
        return proxies

    except Exception as e:
        logger.error(f"Error loading proxies from {PROXIES_FILE}: {e}")
        return []

def test_proxy_connection(proxy_tuple: Tuple[str, str, str, str], timeout: int = 10) -> bool:
    """
    Test if a proxy is working by making a simple HTTP request.

    Args:
        proxy_tuple: Tuple of (host, port, username, password)
        timeout: Connection timeout in seconds

    Returns:
        True if proxy is working, False otherwise
    """
    host, port, username, password = proxy_tuple

    # Format proxy for requests library
    proxy_url = f"http://{username}:{password}@{host}:{port}"

    proxies = {
        'http': proxy_url,
        'https': proxy_url
    }

    test_urls = [
        'http://httpbin.org/ip',  # Simple IP check
        'https://www.google.com', # Test HTTPS
        'http://www.facebook.com' # Test Facebook accessibility
    ]

    for test_url in test_urls:
        try:
            logger.info(f"Testing proxy {username}@{host}:{port} with {test_url}")
            response = requests.get(
                test_url,
                proxies=proxies,
                timeout=timeout,
                allow_redirects=False
            )

            if response.status_code in [200, 301, 302, 403]:  # Accept various status codes
                logger.info(f"✅ Proxy {username}@{host}:{port} is working")
                return True

        except Exception as e:
            logger.warning(f"❌ Proxy {username}@{host}:{port} failed on {test_url}: {e}")
            continue

    logger.error(f"❌ Proxy {username}@{host}:{port} failed all tests")
    return False

def get_working_proxies(test_all: bool = False) -> List[Tuple[str, str, str, str]]:
    """
    Get list of working proxies by testing them.

    Args:
        test_all: If True, test all proxies. If False, stop after finding first working proxy.

    Returns:
        List of working proxy tuples
    """
    all_proxies = load_proxies()
    if not all_proxies:
        return []

    working_proxies = []

    logger.info(f"Testing {len(all_proxies)} proxies...")

    for proxy in all_proxies:
        if test_proxy_connection(proxy):
            working_proxies.append(proxy)
            if not test_all:  # Stop after finding first working proxy
                break
        time.sleep(1)  # Small delay between tests

    logger.info(f"Found {len(working_proxies)} working proxies out of {len(all_proxies)}")
    return working_proxies

def select_random_proxy(proxies: List[Tuple[str, str, str, str]]) -> Optional[Tuple[str, str, str, str]]:
    """
    Select a random proxy from the list.

    Args:
        proxies: List of proxy tuples (host, port, username, password)

    Returns:
        Random proxy tuple or None if list is empty
    """
    if not proxies:
        return None
    return random.choice(proxies)

def format_proxy_string(proxy: Tuple[str, str, str, str]) -> str:
    """
    Format proxy tuple into SeleniumBase-compatible proxy string.

    Args:
        proxy: Tuple of (host, port, username, password)

    Returns:
        Formatted proxy string: "username:password@host:port"
    """
    host, port, username, password = proxy
    if username and password:
        return f"{username}:{password}@{host}:{port}"
    else:
        return f"{host}:{port}"

def get_proxy_string(test_connection: bool = True) -> Optional[str]:
    """
    Get a random working proxy string ready for SeleniumBase.

    Args:
        test_connection: If True, test proxy connectivity before returning

    Returns:
        Formatted proxy string or None if no working proxies available
    """
    if test_connection:
        # Get working proxies
        working_proxies = get_working_proxies(test_all=False)  # Stop after finding first working
        if not working_proxies:
            logger.warning("No working proxies found. Trying without connection test...")
            # Fallback: try without testing
            all_proxies = load_proxies()
            if all_proxies:
                proxy = select_random_proxy(all_proxies)
                if proxy:
                    proxy_string = format_proxy_string(proxy)
                    host, port, username, _ = proxy
                    logger.warning(f"Using untested proxy: {username}@{host}:{port}")
                    return proxy_string
            return None

        proxy = select_random_proxy(working_proxies)
    else:
        # No testing, just pick random proxy
        all_proxies = load_proxies()
        if not all_proxies:
            return None
        proxy = select_random_proxy(all_proxies)

    if proxy:
        proxy_string = format_proxy_string(proxy)
        host, port, username, _ = proxy
        logger.info(f"Selected proxy: {username}@{host}:{port}")
        return proxy_string

    return None

def get_proxy_string_with_fallback() -> Optional[str]:
    """
    Get proxy string with multiple fallback strategies.

    Returns:
        Formatted proxy string or None if no proxies available
    """
    # Strategy 1: Test connectivity and use working proxy
    logger.info("Strategy 1: Testing proxy connectivity...")
    proxy_string = get_proxy_string(test_connection=True)
    if proxy_string:
        return proxy_string

    # Strategy 2: Use random proxy without testing
    logger.info("Strategy 2: Using random proxy without testing...")
    proxy_string = get_proxy_string(test_connection=False)
    if proxy_string:
        return proxy_string

    # Strategy 3: No proxies available
    logger.warning("No proxies available. Running without proxy.")
    return None

def validate_proxy_format(proxy_string: str) -> bool:
    """
    Validate if a proxy string has the correct format.

    Args:
        proxy_string: Proxy string in format "host,port,username,password"

    Returns:
        True if format is valid, False otherwise
    """
    try:
        parts = proxy_string.split(',')
        if len(parts) != 4:
            return False

        host, port, username, password = parts

        # Basic validation
        if not all([host.strip(), port.strip(), username.strip(), password.strip()]):
            return False

        # Port should be numeric
        int(port.strip())

        return True
    except (ValueError, AttributeError):
        return False

def create_proxy_health_report() -> Dict[str, any]:
    """
    Create a comprehensive health report of all proxies.

    Returns:
        Dictionary containing proxy health information
    """
    all_proxies = load_proxies()
    if not all_proxies:
        return {"total_proxies": 0, "working_proxies": 0, "failed_proxies": 0, "details": []}

    report = {
        "total_proxies": len(all_proxies),
        "working_proxies": 0,
        "failed_proxies": 0,
        "details": []
    }

    for proxy in all_proxies:
        host, port, username, password = proxy
        proxy_info = {
            "proxy": f"{username}@{host}:{port}",
            "working": False,
            "test_results": []
        }

        if test_proxy_connection(proxy):
            proxy_info["working"] = True
            report["working_proxies"] += 1
        else:
            report["failed_proxies"] += 1

        report["details"].append(proxy_info)

    return report

def test_proxy_loading():
    """Test function to verify proxy loading works correctly."""
    print("=" * 60)
    print("ENHANCED PROXY TESTING")
    print("=" * 60)

    # Test 1: Load proxies
    print("\n1. Loading proxies...")
    proxies = load_proxies()
    print(f"Loaded {len(proxies)} proxies:")

    for i, proxy in enumerate(proxies, 1):
        host, port, username, password = proxy
        proxy_string = format_proxy_string(proxy)
        print(f"  {i}. {username}@{host}:{port}")

    if not proxies:
        print("No proxies to test!")
        return

    # Test 2: Test connectivity
    print(f"\n2. Testing proxy connectivity...")
    working_proxies = get_working_proxies(test_all=True)

    print(f"\n3. Proxy Health Summary:")
    print(f"   Total proxies: {len(proxies)}")
    print(f"   Working proxies: {len(working_proxies)}")
    print(f"   Failed proxies: {len(proxies) - len(working_proxies)}")

    # Test 3: Get recommended proxy
    print(f"\n4. Getting recommended proxy...")
    final_proxy = get_proxy_string_with_fallback()
    if final_proxy:
        print(f"Recommended proxy: {final_proxy.split('@')[-1] if '@' in final_proxy else final_proxy}")
    else:
        print("No proxy available - would run without proxy")

if __name__ == "__main__":
    # Configure logging for testing
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    test_proxy_loading()
