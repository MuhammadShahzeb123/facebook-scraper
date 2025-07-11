#!/usr/bin/env python3
"""
Test script to verify the advertiser scraping endpoint fix
"""

import json
import requests
import time
from pathlib import Path

def test_advertiser_endpoint():
    """Test the fixed advertiser scraping endpoint"""

    # Test data
    test_request = {
        "headless": False,  # Set to False to see if Chrome opens
        "max_scrolls": 2,   # Small value for testing
        "ads_limit": 5,     # Small limit for testing
        "target_pairs": [["Thailand", "properties"]],
        "ad_category": "all",
        "status": "active",
        "languages": [],
        "platforms": [],
        "media_type": "all",
        "start_date": None,
        "end_date": None,
        "append_mode": True,
        "advertisers": [],
        "continuation": False
    }

    print("🚀 Testing the fixed advertiser scraping endpoint...")
    print(f"📝 Request data: {json.dumps(test_request, indent=2)}")

    try:
        # Make request to the API
        response = requests.post(
            "http://localhost:8000/scrape/advertisers",
            json=test_request,
            timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            print("✅ API endpoint is working!")
            print(f"📊 Response: {json.dumps(result, indent=2)}")

            job_id = result.get("job_id")
            if job_id:
                print(f"🔍 Job ID: {job_id}")
                print("⏱️  You can check job status at: http://localhost:8000/jobs/{job_id}")

                # Check job status after a short delay
                time.sleep(5)
                status_response = requests.get(f"http://localhost:8000/jobs/{job_id}")
                if status_response.status_code == 200:
                    status_data = status_response.json()
                    print(f"📈 Job Status: {status_data.get('status', 'unknown')}")

                    # If failed, show error details
                    if status_data.get('status') == 'failed':
                        print(f"❌ Error: {status_data.get('error', 'Unknown error')}")
                        if 'stdout' in status_data:
                            print(f"📄 Output: {status_data['stdout'][:500]}...")

        else:
            print(f"❌ API request failed with status {response.status_code}")
            print(f"📄 Response: {response.text}")

    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to API server.")
        print("💡 Make sure the API is running: python app.py")
        print("🌐 API should be available at: http://localhost:8000")

    except Exception as e:
        print(f"❌ Test failed with error: {str(e)}")

if __name__ == "__main__":
    print("=" * 60)
    print("🧪 Facebook Advertiser Scraper API Fix Test")
    print("=" * 60)

    test_advertiser_endpoint()

    print()
    print("=" * 60)
    print("📋 Fix Summary:")
    print("1. ✅ Fixed hardcoded headless=True in facebook_advertiser_ads.py")
    print("2. ✅ Added environment variable support to the script")
    print("3. ✅ Fixed API environment variable names to match script")
    print("4. ✅ Script now properly reads HEADLESS, SCROLLS, etc. from env")
    print("=" * 60)
