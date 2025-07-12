#!/usr/bin/env python3
"""
Quick test for suggestions scraper with proxy integration
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

from suggestions_scraper_api import scrape_suggestions_sync

def test_suggestions_scraper():
    """Test the suggestions scraper with proxy integration."""
    print("Testing Suggestions Scraper with Proxy Integration")
    print("=" * 60)
    
    try:
        # Test with a simple country/keyword pair
        result = scrape_suggestions_sync(
            country="United States",
            keyword="coffee",
            scrape_ads=False,  # Don't scrape ads for quick test
            headless=True
        )
        
        print("✅ SUCCESS: Suggestions scraper completed successfully!")
        print(f"Results: {result.get('total_suggestions', 0)} suggestions found")
        print(f"Country: {result.get('country')}")
        print(f"Keyword: {result.get('keyword')}")
        
        # Show first few suggestions
        suggestions = result.get('suggestions', [])
        if suggestions:
            print("\nFirst few suggestions:")
            for i, suggestion in enumerate(suggestions[:3], 1):
                name = suggestion.get('name', 'Unknown')
                print(f"  {i}. {name}")
        
        return True
        
    except Exception as e:
        error_msg = str(e)
        print(f"❌ FAILED: {error_msg}")
        
        if "ERR_NAME_NOT_RESOLVED" in error_msg:
            print("\n🔍 DNS Resolution Issue:")
            print("  - The proxy might have DNS problems")
            print("  - Try a different proxy server")
            print("  - Check if proxy supports HTTPS connections")
        elif "ERR_EMPTY_RESPONSE" in error_msg:
            print("\n🔍 Empty Response Issue:")
            print("  - Facebook might be blocking the proxy IP")
            print("  - Try using residential proxies instead")
        else:
            print(f"\n🔍 Other Error: {error_msg}")
        
        return False

if __name__ == "__main__":
    success = test_suggestions_scraper()
    exit(0 if success else 1)
