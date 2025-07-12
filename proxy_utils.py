#!/usr/bin/env python3
"""
Proxy utility functions for Facebook scrapers
Handles proxy loading and selection from proxies.json
"""

import json
import random
import logging
from pathlib import Path
from typing import List, Tuple, Optional

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

def get_proxy_string() -> Optional[str]:
    """
    Get a random proxy string ready for SeleniumBase.

    Returns:
        Formatted proxy string or None if no proxies available
    """
    proxies = load_proxies()
    if not proxies:
        logger.warning("No proxies available. Running without proxy.")
        return None

    proxy = select_random_proxy(proxies)
    if proxy:
        proxy_string = format_proxy_string(proxy)
        host, port, username, _ = proxy
        logger.info(f"Selected proxy: {username}@{host}:{port}")
        return proxy_string

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

def test_proxy_loading():
    """Test function to verify proxy loading works correctly."""
    print("Testing proxy loading...")

    proxies = load_proxies()
    print(f"Loaded {len(proxies)} proxies:")

    for i, proxy in enumerate(proxies, 1):
        host, port, username, password = proxy
        proxy_string = format_proxy_string(proxy)
        print(f"  {i}. {username}@{host}:{port} -> {proxy_string}")

    if proxies:
        random_proxy = select_random_proxy(proxies)
        if random_proxy:
            random_string = format_proxy_string(random_proxy)
            print(f"\nRandom proxy selected: {random_string}")

    final_proxy = get_proxy_string()
    print(f"Final proxy string: {final_proxy}")

if __name__ == "__main__":
    # Configure logging for testing
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    test_proxy_loading()
