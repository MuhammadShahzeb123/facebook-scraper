#!/usr/bin/env python3
"""
Simple test to check if the suggestions API is working
"""
import requests
import time
import json

def test_suggestions_api():
    print("🧪 Testing suggestions API...")    # Test data - simplified as requested (only required parameters)
    test_data = {
        "headless": False,  # Set to False for testing
        "target_pairs": [["Thailand", "properties"]],
        "scrape_advertiser_ads": False
    }

    try:
        # Send request to suggestions endpoint
        print("📤 Sending request to suggestions endpoint...")
        response = requests.post(
            "http://localhost:8000/scrape/suggestions",
            json=test_data,
            headers={"Content-Type": "application/json"},
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            job_id = data.get("job_id")
            print(f"✅ Successfully started suggestions job: {job_id}")

            # Wait a moment for the job to start
            print("⏳ Waiting for job to process...")
            time.sleep(10)

            # Check job status
            status_response = requests.get(f"http://localhost:8000/jobs/{job_id}")
            if status_response.status_code == 200:
                status_data = status_response.json()
                job_status = status_data.get("status", "unknown")
                print(f"📊 Job Status: {job_status}")

                if job_status == "completed":
                    print("✅ SUCCESS: Country selection works!")
                    print(f"🎯 Job completed successfully")
                elif job_status == "failed":
                    error = status_data.get("error", "Unknown error")
                    print("❌ FAILED: Country selection still has issues")
                    print(f"🔍 Error: {error}")
                elif job_status == "running":
                    print("⏳ Job is still running...")
                    print("💡 This might take a while for headless=False")
                else:
                    print(f"❓ Unexpected status: {job_status}")
            else:
                print(f"❌ Failed to get job status: {status_response.status_code}")
                print(f"🔍 Response: {status_response.text}")
        else:
            print(f"❌ Failed to start job: {response.status_code}")
            print(f"🔍 Response: {response.text}")

    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")

if __name__ == "__main__":
    test_suggestions_api()
