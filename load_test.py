#!/usr/bin/env python3
"""
Load testing script for Facebook Scraper API
"""

import asyncio
import aiohttp
import time
import json
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any

class LoadTester:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.results = []

    async def make_request(self, session: aiohttp.ClientSession, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Make a single API request and measure response time"""
        start_time = time.time()

        try:
            async with session.get(f"{self.base_url}/{endpoint}", params=params, timeout=300) as response:
                end_time = time.time()
                response_data = await response.json()

                return {
                    "endpoint": endpoint,
                    "status_code": response.status,
                    "response_time": end_time - start_time,
                    "success": response.status == 200,
                    "params": params
                }
        except Exception as e:
            end_time = time.time()
            return {
                "endpoint": endpoint,
                "status_code": 0,
                "response_time": end_time - start_time,
                "success": False,
                "error": str(e),
                "params": params
            }

    async def test_health_endpoint(self, session: aiohttp.ClientSession, num_requests: int = 10):
        """Test health endpoint with multiple concurrent requests"""
        tasks = []
        for i in range(num_requests):
            task = self.make_request(session, "health", {})
            tasks.append(task)

        results = await asyncio.gather(*tasks)
        self.results.extend(results)
        return results

    async def test_ads_search_endpoint(self, session: aiohttp.ClientSession, num_requests: int = 5):
        """Test ads search endpoint with different parameters"""
        test_cases = [
            {"keyword": "coffee", "location": "thailand", "limit": 10},
            {"keyword": "restaurant", "location": "united states", "limit": 20},
            {"keyword": "hotel", "location": "canada", "limit": 15},
            {"keyword": "technology", "location": "thailand", "limit": 25},
            {"keyword": "education", "location": "thailand", "limit": 30}
        ]

        tasks = []
        for i in range(num_requests):
            params = test_cases[i % len(test_cases)]
            task = self.make_request(session, "ads_search", params)
            tasks.append(task)

        results = await asyncio.gather(*tasks)
        self.results.extend(results)
        return results

    async def test_advertiser_search_endpoint(self, session: aiohttp.ClientSession, num_requests: int = 3):
        """Test advertiser search endpoint"""
        test_cases = [
            {"keyword": "starbucks", "scrape_page": False},
            {"keyword": "mcdonalds", "scrape_page": False},
            {"keyword": "nike", "scrape_page": False}
        ]

        tasks = []
        for i in range(num_requests):
            params = test_cases[i % len(test_cases)]
            task = self.make_request(session, "advertiser_search", params)
            tasks.append(task)

        results = await asyncio.gather(*tasks)
        self.results.extend(results)
        return results

    async def test_concurrent_mixed_requests(self, session: aiohttp.ClientSession, num_requests: int = 10):
        """Test mixed endpoint requests concurrently"""
        tasks = []

        # Mix of different endpoints
        endpoints_params = [
            ("health", {}),
            ("status", {}),
            ("ads_search", {"keyword": "test", "limit": 5}),
            ("advertiser_search", {"keyword": "test", "scrape_page": False}),
        ]

        for i in range(num_requests):
            endpoint, params = endpoints_params[i % len(endpoints_params)]
            task = self.make_request(session, endpoint, params)
            tasks.append(task)

        results = await asyncio.gather(*tasks)
        self.results.extend(results)
        return results

    async def run_load_test(self, concurrent_users: int = 5, requests_per_user: int = 4):
        """Run comprehensive load test"""
        print(f"Starting load test with {concurrent_users} concurrent users")
        print(f"Each user will make {requests_per_user} requests")

        connector = aiohttp.TCPConnector(limit=100, limit_per_host=20)
        timeout = aiohttp.ClientTimeout(total=300)

        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            # Test different scenarios
            print("\n1. Testing health endpoint...")
            await self.test_health_endpoint(session, 20)

            print("2. Testing ads search endpoint...")
            await self.test_ads_search_endpoint(session, 5)

            print("3. Testing advertiser search endpoint...")
            await self.test_advertiser_search_endpoint(session, 3)

            print("4. Testing concurrent mixed requests...")
            await self.test_concurrent_mixed_requests(session, 15)

        self.analyze_results()

    def analyze_results(self):
        """Analyze and display test results"""
        if not self.results:
            print("No results to analyze")
            return

        # Group results by endpoint
        endpoint_stats = {}
        for result in self.results:
            endpoint = result["endpoint"]
            if endpoint not in endpoint_stats:
                endpoint_stats[endpoint] = {
                    "total_requests": 0,
                    "successful_requests": 0,
                    "failed_requests": 0,
                    "response_times": [],
                    "status_codes": []
                }

            stats = endpoint_stats[endpoint]
            stats["total_requests"] += 1
            stats["response_times"].append(result["response_time"])
            stats["status_codes"].append(result["status_code"])

            if result["success"]:
                stats["successful_requests"] += 1
            else:
                stats["failed_requests"] += 1

        # Print analysis
        print("\n" + "="*80)
        print("LOAD TEST RESULTS")
        print("="*80)

        for endpoint, stats in endpoint_stats.items():
            print(f"\nEndpoint: /{endpoint}")
            print("-" * 40)
            print(f"Total Requests: {stats['total_requests']}")
            print(f"Successful: {stats['successful_requests']}")
            print(f"Failed: {stats['failed_requests']}")
            print(f"Success Rate: {(stats['successful_requests'] / stats['total_requests'] * 100):.1f}%")

            response_times = stats["response_times"]
            if response_times:
                print(f"Avg Response Time: {sum(response_times) / len(response_times):.2f}s")
                print(f"Min Response Time: {min(response_times):.2f}s")
                print(f"Max Response Time: {max(response_times):.2f}s")

                # Calculate percentiles
                sorted_times = sorted(response_times)
                p50 = sorted_times[len(sorted_times) // 2]
                p95 = sorted_times[int(len(sorted_times) * 0.95)]
                print(f"50th Percentile: {p50:.2f}s")
                print(f"95th Percentile: {p95:.2f}s")

        # Overall statistics
        total_requests = len(self.results)
        successful_requests = sum(1 for r in self.results if r["success"])
        all_response_times = [r["response_time"] for r in self.results]

        print(f"\nOVERALL STATISTICS")
        print("-" * 40)
        print(f"Total Requests: {total_requests}")
        print(f"Overall Success Rate: {(successful_requests / total_requests * 100):.1f}%")
        print(f"Average Response Time: {sum(all_response_times) / len(all_response_times):.2f}s")

        # Save results to file
        with open("load_test_results.json", "w") as f:
            json.dump({
                "summary": {
                    "total_requests": total_requests,
                    "successful_requests": successful_requests,
                    "overall_success_rate": successful_requests / total_requests * 100,
                    "average_response_time": sum(all_response_times) / len(all_response_times)
                },
                "endpoint_stats": endpoint_stats,
                "detailed_results": self.results
            }, f, indent=2)

        print(f"\nDetailed results saved to load_test_results.json")

def stress_test_specific_endpoint(endpoint: str, params: Dict[str, Any], num_requests: int = 50):
    """Stress test a specific endpoint"""
    async def run_stress_test():
        tester = LoadTester()
        connector = aiohttp.TCPConnector(limit=100)
        timeout = aiohttp.ClientTimeout(total=300)

        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            print(f"Stress testing /{endpoint} with {num_requests} requests...")

            tasks = []
            for i in range(num_requests):
                task = tester.make_request(session, endpoint, params)
                tasks.append(task)

            results = await asyncio.gather(*tasks)
            tester.results = results
            tester.analyze_results()

    asyncio.run(run_stress_test())

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Load test Facebook Scraper API")
    parser.add_argument("--url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--users", type=int, default=5, help="Number of concurrent users")
    parser.add_argument("--requests", type=int, default=4, help="Requests per user")
    parser.add_argument("--endpoint", help="Test specific endpoint only")
    parser.add_argument("--stress", type=int, help="Stress test with N requests")

    args = parser.parse_args()

    if args.endpoint and args.stress:
        # Stress test specific endpoint
        test_params = {
            "ads_search": {"keyword": "test", "limit": 10},
            "advertiser_search": {"keyword": "test", "scrape_page": False},
            "page_extract": {"url": "https://facebook.com/test", "extract_post": False},
            "post_extract": {"url": "https://facebook.com/share/p/test/"}
        }

        params = test_params.get(args.endpoint, {})
        stress_test_specific_endpoint(args.endpoint, params, args.stress)
    else:
        # Run full load test
        tester = LoadTester(args.url)
        asyncio.run(tester.run_load_test(args.users, args.requests))
