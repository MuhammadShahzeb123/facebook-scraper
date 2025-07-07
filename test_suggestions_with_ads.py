#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for the new suggestions_with_ads mode
"""

import os
import sys
import json
from pathlib import Path

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_suggestions_with_ads():
    """Test the new suggestions_with_ads mode"""

    # Set environment variables for testing
    os.environ["MODE"] = "suggestions_with_ads"
    os.environ["HEADLESS"] = "True"  # Set to "False" for visual debugging
    os.environ["TARGET_PAIRS"] = '[["Thailand", "properties"]]'
    os.environ["ADS_LIMIT"] = "50"  # Limit ads per advertiser for testing

    print("=== Testing suggestions_with_ads mode ===")
    print(f"MODE: {os.getenv('MODE')}")
    print(f"HEADLESS: {os.getenv('HEADLESS')}")
    print(f"TARGET_PAIRS: {os.getenv('TARGET_PAIRS')}")
    print(f"ADS_LIMIT: {os.getenv('ADS_LIMIT')}")

    try:
        # Import and run the main scraper
        from ads_and_suggestions_scraper import main
        main()

        # Check if results were saved
        results_dir = Path("Results")
        if results_dir.exists():
            result_files = list(results_dir.glob("suggestions_with_ads*.json"))
            if result_files:
                latest_file = max(result_files, key=lambda f: f.stat().st_mtime)
                print(f"\n=== Results saved to: {latest_file} ===")
                  # Load and display structure
                with open(latest_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                if isinstance(data, list) and len(data) > 0:
                    # The file contains a list of results
                    sample = data[-1]  # Get the latest result
                    print(f"Sample result structure:")

                    # Handle both dict and list formats
                    if isinstance(sample, dict):
                        print(f"  - keyword: {sample.get('keyword', 'N/A')}")
                        print(f"  - country: {sample.get('country', 'N/A')}")
                        print(f"  - suggestions count: {len(sample.get('suggestions', []))}")

                        # Show first advertiser details
                        suggestions = sample.get('suggestions', [])
                        if suggestions:
                            first_advertiser = suggestions[0]
                            advertiser_data = first_advertiser.get('advertiser', {})
                            print(f"  - first advertiser: {advertiser_data.get('name', 'N/A')}")
                            print(f"  - first advertiser ads count: {len(advertiser_data.get('ads', []))}")
                    elif isinstance(sample, list):
                        print(f"  - sample is a list with {len(sample)} elements")
                        if len(sample) > 0 and isinstance(sample[0], dict):
                            item = sample[0]
                            print(f"  - first item keyword: {item.get('keyword', 'N/A')}")
                            print(f"  - first item country: {item.get('country', 'N/A')}")
                            print(f"  - first item suggestions count: {len(item.get('suggestions', []))}")

                    print("\n=== SUCCESS: New mode working correctly! ===")
                else:
                    print("=== WARNING: No data found in results file ===")
                    print(f"Data type: {type(data)}")
                    print(f"Data: {data}")
                    if isinstance(data, dict):
                        print(f"Keys: {list(data.keys())}")
                    elif isinstance(data, list):
                        print(f"Length: {len(data)}")
                        if len(data) > 0:
                            print(f"First item type: {type(data[0])}")
                            print(f"First item: {data[0]}")
                    else:
                        print("Data is neither dict nor list")
            else:
                print("=== WARNING: No suggestions_with_ads result files found ===")
        else:
            print("=== WARNING: Results directory not found ===")

    except Exception as e:
        print(f"=== ERROR: Test failed with exception: {str(e)} ===")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_suggestions_with_ads()
