#!/usr/bin/env python3
"""
Startup script for Facebook Scraper API
Handles setup, validation, and launch
"""

import os
import sys
import json
import subprocess
from pathlib import Path

def check_requirements():
    """Check if all requirements are installed"""
    try:
        import fastapi
        import uvicorn
        import seleniumbase
        import pydantic
        print("✅ All required packages are installed")
        return True
    except ImportError as e:
        print(f"❌ Missing requirement: {e}")
        print("Please run: pip install -r requirements.txt")
        return False

def check_config_files():
    """Check if necessary config files exist"""
    required_files = [
        "config.json",
        "saved_cookies/facebook_cookies.txt"
    ]

    missing_files = []
    for file_path in required_files:
        if not Path(file_path).exists():
            missing_files.append(file_path)

    if missing_files:
        print("❌ Missing required files:")
        for file in missing_files:
            print(f"   - {file}")
        print("\nPlease ensure you have:")
        print("1. Facebook cookies exported to saved_cookies/facebook_cookies.txt")
        print("2. Account configuration in config.json")
        return False

    print("✅ All required config files found")
    return True

def validate_config():
    """Validate config.json structure"""
    try:
        with open("config.json", "r") as f:
            config = json.load(f)

        if "accounts" not in config:
            print("❌ config.json missing 'accounts' section")
            return False

        for account_id, account_data in config["accounts"].items():
            if "cookies" not in account_data or "proxy" not in account_data:
                print(f"❌ Account {account_id} missing cookies or proxy")
                return False

        print("✅ config.json structure is valid")
        return True
    except Exception as e:
        print(f"❌ Error validating config.json: {e}")
        return False

def create_directories():
    """Create necessary directories"""
    directories = [
        "saved_cookies",
        "Results",
        "debug"
    ]

    for directory in directories:
        Path(directory).mkdir(exist_ok=True)

    print("✅ Required directories created")

def run_tests():
    """Run basic tests to ensure everything works"""
    print("🧪 Running basic tests...")

    try:
        result = subprocess.run([
            sys.executable, "-m", "pytest", "test_api.py::TestAPIEndpoints::test_health_check", "-v"
        ], capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            print("✅ Basic tests passed")
            return True
        else:
            print("❌ Tests failed:")
            print(result.stdout)
            print(result.stderr)
            return False
    except subprocess.TimeoutExpired:
        print("⚠️  Tests timed out - continuing anyway")
        return True
    except Exception as e:
        print(f"⚠️  Could not run tests: {e}")
        return True

def start_api(port=8000, workers=1, reload=True):
    """Start the FastAPI server"""
    print(f"🚀 Starting Facebook Scraper API on port {port}")
    print(f"📖 API Documentation will be available at: http://localhost:{port}/docs")
    print(f"🔄 ReDoc Documentation at: http://localhost:{port}/redoc")
    print(f"💓 Health Check at: http://localhost:{port}/health")

    cmd = [
        "uvicorn", "app:app",
        "--host", "0.0.0.0",
        "--port", str(port),
        "--workers", str(workers)
    ]

    if reload:
        cmd.append("--reload")

    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\n👋 API server stopped")

def main():
    """Main startup routine"""
    print("🔧 Facebook Scraper API Startup")
    print("=" * 40)

    # Step 1: Check requirements
    if not check_requirements():
        sys.exit(1)

    # Step 2: Create directories
    create_directories()

    # Step 3: Check config files
    if not check_config_files():
        sys.exit(1)

    # Step 4: Validate configuration
    if not validate_config():
        sys.exit(1)

    # Step 5: Run tests (optional)
    run_tests()

    # Step 6: Start the API
    print("\n" + "=" * 40)
    start_api()

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Start Facebook Scraper API")
    parser.add_argument("--port", type=int, default=8000, help="Port to run the API on")
    parser.add_argument("--workers", type=int, default=1, help="Number of worker processes")
    parser.add_argument("--no-reload", action="store_true", help="Disable auto-reload")
    parser.add_argument("--skip-tests", action="store_true", help="Skip running tests")

    args = parser.parse_args()

    # Override main function for custom arguments
    print("🔧 Facebook Scraper API Startup")
    print("=" * 40)

    if not check_requirements():
        sys.exit(1)

    create_directories()

    if not check_config_files():
        sys.exit(1)

    if not validate_config():
        sys.exit(1)

    if not args.skip_tests:
        run_tests()

    print("\n" + "=" * 40)
    start_api(port=args.port, workers=args.workers, reload=not args.no_reload)
