#!/usr/bin/env python3
"""
Test script to verify the scroll-only API approach works.
This script tests the updated API with MAX_SCROLLS instead of ADS_LIMIT.
"""

import requests
import json
import time
import os
import subprocess

def test_scroll_only_api():
    """Test the API with scroll-only configuration."""
    print("=" * 60)
    print("TESTING SCROLL-ONLY API APPROACH")
    print("=" * 60)

    # Test different scroll limits
    test_cases = [
        {"max_scrolls": 2, "description": "Quick test with 2 scrolls"},
        {"max_scrolls": 5, "description": "Medium test with 5 scrolls"},
        {"max_scrolls": 10, "description": "Full test with 10 scrolls"}
    ]

    api_base_url = "http://localhost:8000"

    for i, test_case in enumerate(test_cases, 1):
        print(f"\n--- Test Case {i}: {test_case['description']} ---")

        # Test data
        payload = {
            "headless": True,
            "max_scrolls": test_case["max_scrolls"],
            "target_pairs": [["Thailand", "properties"]],
            "ad_category": "all",
            "status": "active",
            "append_mode": True
        }

        print(f"Payload: {json.dumps(payload, indent=2)}")

        try:
            # Start the scraping job
            print(f"Starting scraping job with {test_case['max_scrolls']} scrolls...")
            response = requests.post(f"{api_base_url}/scrape/ads", json=payload, timeout=30)

            if response.status_code == 200:
                result = response.json()
                job_id = result.get("job_id")
                print(f"✅ Job started successfully. Job ID: {job_id}")

                # Wait for completion and check results
                print("Waiting for job completion...")
                max_wait = 300  # 5 minutes
                wait_interval = 10

                for wait_time in range(0, max_wait, wait_interval):
                    time.sleep(wait_interval)

                    # Check job status
                    status_response = requests.get(f"{api_base_url}/job/{job_id}/status")
                    if status_response.status_code == 200:
                        job_status = status_response.json()
                        status = job_status.get("status")
                        print(f"Job status: {status}")

                        if status == "completed":
                            print("✅ Job completed successfully!")

                            # Get results
                            results_response = requests.get(f"{api_base_url}/job/{job_id}/results")
                            if results_response.status_code == 200:
                                results = results_response.json()
                                print(f"Results summary: {len(results.get('results', []))} pairs processed")

                                # Check if scroll limit was respected
                                for result in results.get('results', []):
                                    ads = result.get('ads', [])
                                    print(f"  - {result.get('country')}/{result.get('keyword')}: {len(ads)} ads")

                                    # Check filters
                                    filters = result.get('filters', {})
                                    max_scrolls_used = filters.get('max_scrolls', 'N/A')
                                    print(f"    MAX_SCROLLS used: {max_scrolls_used}")

                                    if 'ads_limit' in filters:
                                        print(f"    ❌ ERROR: ADS_LIMIT still present in filters!")
                                    else:
                                        print(f"    ✅ Good: No ADS_LIMIT in filters")

                            break
                        elif status == "failed":
                            print(f"❌ Job failed: {job_status.get('error', 'Unknown error')}")
                            break
                    else:
                        print(f"❌ Failed to check job status: {status_response.status_code}")
                        break
                else:
                    print(f"❌ Job timeout after {max_wait} seconds")

            else:
                print(f"❌ Failed to start job: {response.status_code}")
                print(f"Response: {response.text}")

        except requests.exceptions.RequestException as e:
            print(f"❌ Request error: {e}")
        except Exception as e:
            print(f"❌ Unexpected error: {e}")

        print(f"--- End of Test Case {i} ---")

    print("\n" + "=" * 60)
    print("SCROLL-ONLY API TEST COMPLETED")
    print("=" * 60)

def test_direct_scraper():
    """Test the scraper directly with environment variables."""
    print("\n" + "=" * 60)
    print("TESTING DIRECT SCRAPER WITH SCROLL-ONLY")
    print("=" * 60)

    # Set environment variables for scroll-only testing
    os.environ["MODE"] = "ads"
    os.environ["HEADLESS"] = "True"
    os.environ["MAX_SCROLLS"] = "3"  # Small number for quick test
    os.environ["TARGET_PAIRS"] = '[["Thailand", "properties"]]'

    # Remove ADS_LIMIT if set
    if "ADS_LIMIT" in os.environ:
        del os.environ["ADS_LIMIT"]

    print("Environment variables set:")
    for key in ["MODE", "HEADLESS", "MAX_SCROLLS", "TARGET_PAIRS"]:
        print(f"  {key}: {os.environ.get(key, 'NOT SET')}")

    print(f"  ADS_LIMIT: {os.environ.get('ADS_LIMIT', 'NOT SET (Good!)')}")

    try:
        print("\nRunning scraper directly...")
        result = subprocess.run(
            ["python", "ads_and_suggestions_scraper.py"],
            capture_output=True,
            text=True,
            timeout=120  # 2 minutes timeout
        )

        if result.returncode == 0:
            print("✅ Scraper completed successfully")
            print("Output:", result.stdout[-500:] if len(result.stdout) > 500 else result.stdout)
        else:
            print(f"❌ Scraper failed with return code: {result.returncode}")
            print("Error:", result.stderr[-500:] if len(result.stderr) > 500 else result.stderr)

    except subprocess.TimeoutExpired:
        print("❌ Scraper timeout after 2 minutes")
    except Exception as e:
        print(f"❌ Error running scraper: {e}")

if __name__ == "__main__":
    print("SCROLL-ONLY API TEST SUITE")
    print("Make sure the API server is running on http://localhost:8000")
    print("Press Enter to continue or Ctrl+C to exit...")

    try:
        input()
    except KeyboardInterrupt:
        print("\nExiting...")
        exit(0)

    # Test the API
    test_scroll_only_api()

    # Test direct scraper
    test_direct_scraper()
