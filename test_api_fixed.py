#!/usr/bin/env python3
"""
Test the fixed API with browser session properly closed before subprocess
"""
import requests
import json
import time

def test_suggestions_with_ads_api():
    """Test the suggestions API with ads scraping enabled"""
    
    # API endpoint
    url = "http://localhost:8000/scrape/suggestions"
    
    # Test payload - small test to verify the fix
    payload = {
        "headless": True,
        "target_pairs": [["Thailand", "properties"]],
        "scrape_advertiser_ads": True,
        "max_scrolls": 3  # Small number for testing
    }
    
    print("Testing suggestions API with ads scraping...")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    try:
        # Start the scraping job
        response = requests.post(url, json=payload)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            job_id = result["job_id"]
            print(f"Job started successfully! Job ID: {job_id}")
            
            # Check job status
            check_url = f"http://localhost:8000/jobs/{job_id}"
            
            # Wait for completion (with timeout)
            timeout = 600  # 10 minutes
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                check_response = requests.get(check_url)
                if check_response.status_code == 200:
                    job_status = check_response.json()
                    status = job_status["status"]
                    print(f"Job status: {status}")
                    
                    if status == "completed":
                        print("✅ Job completed successfully!")
                        
                        # Check if we have suggestions with ads
                        if "results" in job_status:
                            results = job_status["results"]
                            if "results" in results and len(results["results"]) > 0:
                                first_result = results["results"][0]
                                if "suggestions" in first_result:
                                    suggestions = first_result["suggestions"]
                                    print(f"Found {len(suggestions)} suggestions")
                                    
                                    # Check if any suggestions have ads
                                    ads_found = False
                                    for suggestion in suggestions:
                                        if "advertiser" in suggestion and "ads" in suggestion["advertiser"]:
                                            ads_count = len(suggestion["advertiser"]["ads"])
                                            if ads_count > 0:
                                                print(f"✅ Found {ads_count} ads for advertiser: {suggestion['advertiser']['name']}")
                                                ads_found = True
                                    
                                    if not ads_found:
                                        print("❌ No ads found in any suggestions")
                                else:
                                    print("❌ No suggestions found in results")
                            else:
                                print("❌ No results found")
                        
                        return True
                    
                    elif status == "failed":
                        print("❌ Job failed!")
                        print(f"Error: {job_status.get('error', 'Unknown error')}")
                        return False
                    
                    else:
                        print(f"Job still running... ({status})")
                        time.sleep(10)
                else:
                    print(f"Error checking job status: {check_response.status_code}")
                    return False
            
            print("❌ Job timed out!")
            return False
            
        else:
            print(f"❌ Failed to start job: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    success = test_suggestions_with_ads_api()
    print(f"\nTest result: {'✅ SUCCESS' if success else '❌ FAILED'}")
