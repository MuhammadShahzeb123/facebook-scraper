#!/usr/bin/env python3
"""
Test script to verify the suggestions_with_ads API works correctly.
This script tests the API endpoint with scroll-only extraction (no ads limit).
"""

import requests
import json
import time
from pprint import pprint

def test_suggestions_with_ads():
    """Test the suggestions scraping with ads extraction"""

    # API endpoint
    url = "http://localhost:8000/scrape/suggestions"

    # Test payload with suggestions_with_ads mode
    payload = {
        "headless": True,
        "target_pairs": [["Thailand", "properties"]],
        "scrape_advertiser_ads": True,  # This should trigger the suggestions_with_ads mode
        "max_scrolls": 5  # Test with 5 scrolls for faster testing
    }

    print("=" * 60)
    print("TESTING SUGGESTIONS WITH ADS API")
    print("=" * 60)
    print(f"URL: {url}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    print("=" * 60)

    try:
        # Make the request
        response = requests.post(url, json=payload)

        if response.status_code == 200:
            result = response.json()
            print(f"✅ SUCCESS! Status: {response.status_code}")
            print("\n📊 RESPONSE STRUCTURE:")
            print(f"Job ID: {result.get('job_id')}")
            print(f"Status: {result.get('status')}")
            print(f"Message: {result.get('message')}")

            # Get the job ID for polling
            job_id = result.get('job_id')
            if job_id:
                print(f"\n⏳ Polling job {job_id}...")

                # Poll for results
                for i in range(60):  # Poll for up to 10 minutes
                    try:
                        status_response = requests.get(f"http://localhost:8000/jobs/{job_id}")
                        if status_response.status_code == 200:
                            job_status = status_response.json()
                            print(f"   Poll {i+1}: Status = {job_status.get('status')}")

                            if job_status.get('status') == 'completed':
                                print("\n🎉 JOB COMPLETED!")

                                # Check the results
                                results = job_status.get('results', {})
                                if 'results' in results:
                                    data = results['results']
                                    if data and len(data) > 0:
                                        first_result = data[0]
                                        print(f"\n📋 RESULTS SUMMARY:")
                                        print(f"Country: {first_result.get('country')}")
                                        print(f"Keyword: {first_result.get('keyword')}")
                                        print(f"Suggestions count: {len(first_result.get('suggestions', []))}")

                                        # Check if we have the nested structure
                                        suggestions = first_result.get('suggestions', [])
                                        if suggestions:
                                            print(f"\n🔍 CHECKING NESTED STRUCTURE:")
                                            ads_found = False
                                            for i, suggestion in enumerate(suggestions[:3]):  # Check first 3
                                                if isinstance(suggestion, dict) and 'advertiser' in suggestion:
                                                    advertiser = suggestion['advertiser']
                                                    ads = advertiser.get('ads', [])
                                                    print(f"   Suggestion {i+1}: {advertiser.get('name')} -> {len(ads)} ads")
                                                    if ads:
                                                        ads_found = True
                                                else:
                                                    print(f"   Suggestion {i+1}: {suggestion.get('name', 'Unknown')} -> No nested structure")

                                            if ads_found:
                                                print("\n✅ SUCCESS: Found nested structure with ads!")

                                                # Save results to file for inspection
                                                with open('test_results_suggestions_with_ads.json', 'w', encoding='utf-8') as f:
                                                    json.dump(results, f, indent=2, ensure_ascii=False)
                                                print("💾 Results saved to test_results_suggestions_with_ads.json")

                                                return True
                                            else:
                                                print("\n❌ FAILED: No ads found in nested structure!")
                                                return False
                                        else:
                                            print("\n❌ FAILED: No suggestions found!")
                                            return False
                                    else:
                                        print("\n❌ FAILED: Empty results!")
                                        return False
                                else:
                                    print("\n❌ FAILED: No results in response!")
                                    return False

                            elif job_status.get('status') == 'failed':
                                print(f"\n❌ JOB FAILED: {job_status.get('error', 'Unknown error')}")
                                return False

                        time.sleep(10)  # Wait 10 seconds between polls

                    except Exception as e:
                        print(f"   Poll error: {e}")
                        time.sleep(10)

                print("\n⏰ TIMEOUT: Job did not complete within expected time")
                return False
            else:
                print("❌ FAILED: No job_id in response")
                return False

        else:
            print(f"❌ FAILED! Status: {response.status_code}")
            print(f"Error: {response.text}")
            return False

    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

if __name__ == "__main__":
    success = test_suggestions_with_ads()
    if success:
        print("\n🎉 TEST PASSED: API correctly extracts suggestions with ads!")
    else:
        print("\n💥 TEST FAILED: API did not work as expected!")
