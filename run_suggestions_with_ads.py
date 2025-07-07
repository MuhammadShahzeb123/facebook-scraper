#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Example usage of the new suggestions_with_ads mode
"""

import os

# ============================================================================
# CONFIGURATION - Edit these values as needed
# ============================================================================

# Set the mode to the new unified scraping
os.environ["MODE"] = "suggestions_with_ads"

# Set target pairs (country, keyword)
os.environ["TARGET_PAIRS"] = '[["Thailand", "properties"], ["United States", "real estate"]]'

# Set limits and options
os.environ["ADS_LIMIT"] = "100"  # Max ads per advertiser
os.environ["HEADLESS"] = "True"  # Set to "False" to see browser
os.environ["CONTINUATION"] = "True"  # Resume from checkpoint if interrupted

# Optional filters
os.environ["AD_CATEGORY"] = "all"  # "all", "properties", "employment", etc.
os.environ["STATUS"] = "active"  # "active", "inactive", "all"
os.environ["PLATFORMS"] = "[]"  # e.g., ["facebook", "instagram"]
os.environ["LANGUAGES"] = "[]"  # e.g., ["English", "Thai"]

# ============================================================================
# RUN THE SCRAPER
# ============================================================================

if __name__ == "__main__":
    print("=" * 80)
    print("FACEBOOK AD LIBRARY SCRAPER - SUGGESTIONS WITH ADS MODE")
    print("=" * 80)
    print()
    print("This script will:")
    print("1. Search for advertiser suggestions using your keywords")
    print("2. For each advertiser found, scrape their active ads")
    print("3. Save results in nested JSON structure to ./Results/ folder")
    print()
    print("Configuration:")
    print(f"  MODE: {os.getenv('MODE')}")
    print(f"  TARGET_PAIRS: {os.getenv('TARGET_PAIRS')}")
    print(f"  ADS_LIMIT: {os.getenv('ADS_LIMIT')} ads per advertiser")
    print(f"  HEADLESS: {os.getenv('HEADLESS')}")
    print()

    # Import and run the main scraper
    try:
        from ads_and_suggestions_scraper import main

        print("Starting scraper...")
        print("=" * 80)
        main()

        print("=" * 80)
        print("SCRAPING COMPLETED!")
        print("Check the ./Results/ folder for your data files.")
        print("=" * 80)

    except KeyboardInterrupt:
        print("\n" + "=" * 80)
        print("SCRAPING INTERRUPTED BY USER")
        print("Progress has been saved. You can resume by running this script again.")
        print("=" * 80)

    except Exception as e:
        print(f"\n" + "=" * 80)
        print(f"ERROR: {str(e)}")
        print("=" * 80)
        import traceback
        traceback.print_exc()
