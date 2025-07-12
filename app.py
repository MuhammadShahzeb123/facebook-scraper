#!/usr/bin/env python3
"""
Facebook Scraper REST API
POST endpoints to start scraping jobs, GET endpoints to retrieve JSON data
"""

import asyncio
import logging
import time
import traceback
import json
import subprocess
import os
import sys
import re
from datetime import datetime, timedelta
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any, Literal
from pathlib import Path
import re

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks, Body, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, validator, ValidationError
import uvicorn
import sys


# Custom JSON Response class to ensure proper Unicode handling
class UnicodeJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            indent=None,
            separators=(",", ":"),
        ).encode("utf-8")


if os.name == "nt":
    sys.stdout.reconfigure(encoding="utf-8") #type: ignore
    sys.stderr.reconfigure(encoding="utf-8") #type: ignore

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('api.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Facebook Scraper API",
    description="POST endpoints to start scraping jobs, GET endpoints to retrieve JSON data",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    default_response_class=UnicodeJSONResponse
)

# Configure JSON responses to properly handle Unicode
@app.middleware("http")
async def unicode_json_middleware(request: Request, call_next):
    """Ensure all JSON responses use proper Unicode encoding"""
    response = await call_next(request)
    if response.headers.get("content-type") == "application/json":
        response.headers["content-type"] = "application/json; charset=utf-8"
    return response

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Results directory
RESULTS_DIR = Path("Results")
RESULTS_DIR.mkdir(exist_ok=True)

# Pydantic models for request bodies
class AdsScrapingRequest(BaseModel):
    headless: bool = Field(default=True, description="Run browser in headless mode")
    max_scrolls: int = Field(default=10, description="Maximum number of scrolls to prevent infinite scrolling", gt=0, le=50)
    ads_limit: int = Field(default=1000, description="Maximum number of ads to extract", gt=0, le=1000000)
    target_pairs: List[List[str]] = Field(
        default=[["Thailand", "properties"]],
        description="List of [country, keyword] pairs"
    )

    # Advanced filtering parameters
    ad_category: Literal["all", "issues", "properties", "employment", "financial"] = Field(
        default="all", description="Ad category filter"
    )
    status: Literal["active", "inactive", "all"] = Field(
        default="active", description="Ad status filter"
    )
    languages: List[str] = Field(
        default=[], description="List of language names or ISO-639-1 codes (e.g. ['English', 'fr', 'thai'])"
    )
    platforms: List[Literal["facebook", "instagram", "audience_network", "messenger", "threads"]] = Field(
        default=[], description="List of platforms to filter by"
    )
    media_type: Literal["all", "image", "video", "meme", "image_and_meme", "none"] = Field(
        default="all", description="Media type filter"
    )
    start_date: Optional[str] = Field(
        default=None, description="Start date in YYYY-MM-DD format"
    )
    end_date: Optional[str] = Field(
        default=None, description="End date in YYYY-MM-DD format"
    )
    append_mode: bool = Field(
        default=True, description="True to append to existing file, False to create numbered files"
    )
    advertisers: List[str] = Field(
        default=[], description="List of specific advertiser names to filter by (leave empty to disable)"
    )
    continuation: bool = Field(
        default=True, description="Continue from previous checkpoint if available"
    )

    @validator('target_pairs')
    def validate_target_pairs(cls, v):
        if not v or len(v) == 0:
            raise ValueError("At least one target pair is required")
        if len(v) > 20:
            raise ValueError("Maximum 20 target pairs allowed")
        for i, pair in enumerate(v):
            if not isinstance(pair, list) or len(pair) != 2:
                raise ValueError(f"Target pair {i+1} must be a list with exactly 2 elements [country, keyword], e.g., ['Thailand', 'properties']")
            if not all(isinstance(item, str) and item.strip() and item.lower() != "string" for item in pair):
                raise ValueError(f"Target pair {i+1}: Both country and keyword must be non-empty strings (not 'string'), e.g., ['Thailand', 'properties']")
        return v

    @validator('languages')
    def validate_languages(cls, v):
        if len(v) > 10:
            raise ValueError("Maximum 10 languages allowed")
        return v

    @validator('platforms')
    def validate_platforms(cls, v):
        if len(v) > 5:
            raise ValueError("Maximum 5 platforms allowed")
        return v

    @validator('advertisers')
    def validate_advertisers(cls, v):
        if len(v) > 20:
            raise ValueError("Maximum 20 advertisers allowed")
        return v

    @validator('start_date', 'end_date')
    def validate_dates(cls, v):
        if v is not None and v.strip() and v.lower() != "string":
            # Validate date format
            if not re.match(r'^\d{4}-\d{2}-\d{2}$', v):
                raise ValueError("Date must be in YYYY-MM-DD format (e.g., 2024-01-15)")
            try:
                datetime.strptime(v, '%Y-%m-%d')
            except ValueError:
                raise ValueError("Invalid date - please use YYYY-MM-DD format")
        # Return None for empty/invalid strings to make them optional
        return v if v and v.strip() and v.lower() != "string" else None

    class Config:
        extra = "forbid"

class SuggestionsScrapingRequest(BaseModel):
    headless: bool = Field(default=True, description="Run browser in headless mode")
    target_pairs: List[List[str]] = Field(
        default=[["Thailand", "properties"]],
        description="List of [country, keyword] pairs"
    )
    scrape_advertiser_ads: bool = Field(
        default=True, description="Also scrape ads from each advertiser found in suggestions"
    )
    advertiser_ads_limit: int = Field(
        default=100, description="Maximum number of ads to extract per advertiser page", gt=0, le=1000
    )

    @validator('target_pairs')
    def validate_target_pairs(cls, v):
        if not v or len(v) == 0:
            raise ValueError("At least one target pair is required")
        if len(v) > 20:
            raise ValueError("Maximum 20 target pairs allowed")
        for i, pair in enumerate(v):
            if not isinstance(pair, list) or len(pair) != 2:
                raise ValueError(f"Target pair {i+1} must be a list with exactly 2 elements [country, keyword], e.g., ['Thailand', 'properties']")
            if not all(isinstance(item, str) and item.strip() and item.lower() != "string" for item in pair):
                raise ValueError(f"Target pair {i+1}: Both country and keyword must be non-empty strings (not 'string'), e.g., ['Thailand', 'properties']")
        return v

    class Config:
        extra = "forbid"

class AdvertiserScrapingRequest(BaseModel):
    headless: bool = Field(default=True, description="Run browser in headless mode")
    max_scrolls: int = Field(default=10, description="Maximum number of scrolls to prevent infinite scrolling", gt=0, le=50)
    ads_limit: int = Field(default=1000, description="Maximum number of ads to extract", gt=0, le=1000000)
    target_pairs: List[List[str]] = Field(
        default=[["Ukraine", "rental apartments"], ["United States", "rental properties"]],
        description="List of [country, keyword] pairs"
    )

    # Advanced filtering parameters
    ad_category: Literal["all", "issues", "properties", "employment", "financial"] = Field(
        default="all", description="Ad category filter"
    )
    status: Literal["active", "inactive", "all"] = Field(
        default="active", description="Ad status filter"
    )
    languages: List[str] = Field(
        default=[], description="List of language names or ISO-639-1 codes (e.g. ['English', 'fr', 'thai'])"
    )
    platforms: List[Literal["facebook", "instagram", "audience_network", "messenger", "threads"]] = Field(
        default=[], description="List of platforms to filter by"
    )
    media_type: Literal["all", "image", "video", "meme", "image_and_meme", "none"] = Field(
        default="all", description="Media type filter"
    )
    start_date: Optional[str] = Field(
        default=None, description="Start date in YYYY-MM-DD format"
    )
    end_date: Optional[str] = Field(
        default=None, description="End date in YYYY-MM-DD format"
    )
    append_mode: bool = Field(
        default=True, description="True to append to existing file, False to create numbered files"
    )
    advertisers: List[str] = Field(
        default=[], description="List of specific advertiser names to filter by (leave empty to disable)"
    )
    continuation: bool = Field(
        default=True, description="Continue from previous checkpoint if available"
    )

    @validator('target_pairs')
    def validate_target_pairs(cls, v):
        if not v or len(v) == 0:
            raise ValueError("At least one target pair is required")
        if len(v) > 20:
            raise ValueError("Maximum 20 target pairs allowed")
        for i, pair in enumerate(v):
            if not isinstance(pair, list) or len(pair) != 2:
                raise ValueError(f"Target pair {i+1} must be a list with exactly 2 elements [country, keyword], e.g., ['Ukraine', 'rental apartments']")
            if not all(isinstance(item, str) and item.strip() and item.lower() != "string" for item in pair):
                raise ValueError(f"Target pair {i+1}: Both country and keyword must be non-empty strings (not 'string'), e.g., ['Ukraine', 'rental apartments']")
        return v

    class Config:
        extra = "forbid"

class PageScrapingRequest(BaseModel):
    headless: bool = Field(default=True, description="Run browser in headless mode")
    post_limit: int = Field(default=100, description="Number of posts to scrape per page", gt=0, le=500)
    account_number: int = Field(default=2, description="Facebook account number to use (1, 2, or 3)", ge=1, le=3)
    search_method: Literal["keyword", "url"] = Field(default="keyword", description="Search method: 'keyword' to search for pages, 'url' to scrape specific page URLs")
    keywords: Optional[List[str]] = Field(
        default=None,
        description="Keywords to search for Facebook pages (required when search_method='keyword')"
    )
    urls: Optional[List[str]] = Field(
        default=None,
        description="Direct Facebook page URLs to scrape (required when search_method='url')"
    )

    def __init__(self, **data):
        super().__init__(**data)
        # Custom validation after object creation
        if self.search_method == 'keyword':
            if not self.keywords or len(self.keywords) == 0:
                raise ValueError("At least one keyword is required when search_method='keyword'")
            if len(self.keywords) > 10:
                raise ValueError("Maximum 10 keywords allowed")
            for keyword in self.keywords:
                if not isinstance(keyword, str) or not keyword.strip():
                    raise ValueError("All keywords must be non-empty strings")
        elif self.search_method == 'url':
            if not self.urls or len(self.urls) == 0:
                raise ValueError("At least one URL is required when search_method='url'")
            if len(self.urls) > 20:
                raise ValueError("Maximum 20 URLs allowed")
            for url in self.urls:
                if not isinstance(url, str) or not url.strip():
                    raise ValueError("All URLs must be non-empty strings")
                if not (url.startswith('http://') or url.startswith('https://')):
                    raise ValueError("All URLs must start with http:// or https://")
                if 'facebook.com' not in url.lower():
                    raise ValueError("All URLs must be Facebook page URLs")

    @validator('keywords')
    def validate_keywords(cls, v):
        if v is not None:
            if len(v) > 10:
                raise ValueError("Maximum 10 keywords allowed")
            for keyword in v:
                if not isinstance(keyword, str) or not keyword.strip():
                    raise ValueError("All keywords must be non-empty strings")
        return v

    @validator('urls')
    def validate_urls(cls, v):
        if v is not None:
            if len(v) > 20:
                raise ValueError("Maximum 20 URLs allowed")
            for url in v:
                if not isinstance(url, str) or not url.strip():
                    raise ValueError("All URLs must be non-empty strings")
                if not (url.startswith('http://') or url.startswith('https://')):
                    raise ValueError("All URLs must start with http:// or https://")
                if 'facebook.com' not in url.lower():
                    raise ValueError("All URLs must be Facebook page URLs")
        return v

    class Config:
        extra = "forbid"  # Reject unknown fields

class PostsScrapingRequest(BaseModel):
    links: List[str] = Field(
        description="List of Facebook post URLs to scrape"
    )

    @validator('links')
    def validate_links(cls, v):
        if not v or len(v) == 0:
            raise ValueError("At least one post URL is required")
        if len(v) > 50:
            raise ValueError("Maximum 50 post URLs allowed")
        for url in v:
            if not isinstance(url, str) or not url.strip():
                raise ValueError("All URLs must be non-empty strings")
            if not (url.startswith('http://') or url.startswith('https://')):
                raise ValueError("All URLs must start with http:// or https://")
            if 'facebook.com' not in url.lower():
                raise ValueError("All URLs must be Facebook post URLs")
        return v

    class Config:
        extra = "forbid"

# Response models
class ScrapingResponse(BaseModel):
    success: bool
    message: str
    job_id: str
    status: str
    timestamp: str

class DataResponse(BaseModel):
    success: bool
    data: Optional[List[Dict[str, Any]]] = None
    file_info: Optional[Dict[str, Any]] = None
    timestamp: str

# Job tracking
active_jobs = {}

def generate_job_id() -> str:
    """Generate unique job ID"""
    return f"job_{int(time.time())}_{hash(str(time.time())) % 10000}"

# Request tracking for rate limiting
request_tracker = {}

def rate_limit_check(client_ip: str, limit: int = 1000, window: int = 60) -> bool:
    """Simple rate limiting implementation"""
    now = time.time()
    if client_ip not in request_tracker:
        request_tracker[client_ip] = []

    # Clean old requests
    request_tracker[client_ip] = [
        req_time for req_time in request_tracker[client_ip]
        if now - req_time < window
    ]

    if len(request_tracker[client_ip]) >= limit:
        return False

    request_tracker[client_ip].append(now)
    return True

@app.middleware("http")
async def log_requests(request, call_next):
    """Log all API requests"""
    start_time = time.time()
    client_ip = request.client.host if request.client else "unknown"

    # Rate limiting check
    if not rate_limit_check(client_ip):
        return UnicodeJSONResponse(
            status_code=429,
            content={
                "success": False,
                "error": "Rate limit exceeded. Try again later.",
                "timestamp": datetime.now().isoformat()
            }
        )

    response = await call_next(request)
    process_time = time.time() - start_time

    logger.info(
        f"{request.method} {request.url.path} - "
        f"Status: {response.status_code} - "
        f"Time: {process_time:.2f}s - "
        f"IP: {client_ip}"
    )

    return response

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler"""
    logger.error(f"Global exception: {str(exc)}\n{traceback.format_exc()}")
    return UnicodeJSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "Internal server error occurred",
            "timestamp": datetime.now().isoformat()
        }
    )

# Exception handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors with proper 400 status codes"""
    error_details = []
    for error in exc.errors():
        field = " -> ".join(str(loc) for loc in error["loc"])
        error_details.append(f"{field}: {error['msg']}")

    return UnicodeJSONResponse(
        status_code=400,
        content={
            "success": False,
            "message": "Validation Error",
            "errors": error_details,
            "timestamp": datetime.now().isoformat()
        }
    )

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Apply rate limiting to all requests"""
    client_ip = request.client.host if request.client else "unknown"
      # Skip rate limiting for health checks
    if request.url.path in ["/health", "/docs", "/openapi.json"]:
        return await call_next(request)

    if not rate_limit_check(client_ip):
        return UnicodeJSONResponse(
            status_code=429,
            content={
                "success": False,
                "message": "Rate limit exceeded. Maximum 10 requests per minute.",
                "timestamp": datetime.now().isoformat()
            }
        )

    return await call_next(request)

# Async functions to run scrapers
def run_ads_scraper(job_id: str, request_data: AdsScrapingRequest):
    """Run ads scraper in background"""
    process = None
    stdout_text = ""
    stderr_text = ""

    try:
        active_jobs[job_id] = {"status": "running", "type": "ads", "started_at": datetime.now().isoformat()}

        # Create environment variables for all parameters
        env = dict(os.environ)
        env.update({
            "MODE": "ads",  # Always set to ads mode
            "HEADLESS": str(request_data.headless),
            "ADS_LIMIT": str(request_data.ads_limit),
            "SCROLLS": str(request_data.max_scrolls),
            "TARGET_PAIRS": json.dumps(request_data.target_pairs, ensure_ascii=False),
            "AD_CATEGORY": request_data.ad_category,
            "STATUS": request_data.status,
            "LANGUAGES": json.dumps(request_data.languages, ensure_ascii=False),
            "PLATFORMS": json.dumps(request_data.platforms, ensure_ascii=False),
            "MEDIA_TYPE": request_data.media_type,
            "START_DATE": request_data.start_date or "",
            "END_DATE": request_data.end_date or "",
            "APPEND": str(request_data.append_mode),
            "ADVERTISERS": json.dumps(request_data.advertisers, ensure_ascii=False),
            "CONTINUATION": str(request_data.continuation),
            "SCRAPE_ADVERTISER_ADS": "False",  # For ads mode, we don't need advertiser ads
            "ADVERTISER_ADS_LIMIT": "100"  # Default value
        })

        # Create command to run the scraper
        cmd = [sys.executable, "ads_and_suggestions_scraper2.py"]

        # Use regular subprocess instead of asyncio subprocess (Windows compatibility)
        process = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,  # Automatically decode output as text
            encoding='utf-8',  # Explicitly specify UTF-8 encoding
            cwd=os.getcwd()  # Ensure correct working directory
        )

        stdout_text = process.stdout if process.stdout else ""
        stderr_text = process.stderr if process.stderr else ""

        # Log the output for debugging
        logger.info(f"Job {job_id} - Process return code: {process.returncode}")
        if stdout_text:
            logger.info(f"Job {job_id} - STDOUT: {stdout_text[:500]}...")
        if stderr_text:
            logger.error(f"Job {job_id} - STDERR: {stderr_text[:500]}...")

        # Update job status based on process result
        if process.returncode == 0:
            active_jobs[job_id]["status"] = "completed"
            active_jobs[job_id]["completed_at"] = datetime.now().isoformat()
            logger.info(f"Job {job_id} completed successfully")
        else:
            active_jobs[job_id]["status"] = "failed"
            active_jobs[job_id]["error"] = stderr_text
            logger.error(f"Job {job_id} failed with return code {process.returncode}")

    except Exception as e:
        error_msg = f"Job {job_id} failed with exception: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        active_jobs[job_id] = {
            "status": "failed",
            "error": error_msg,
            "started_at": active_jobs.get(job_id, {}).get("started_at", datetime.now().isoformat())
        }

    # Final status check
    if process and process.returncode == 0:
        active_jobs[job_id]["status"] = "completed"
        active_jobs[job_id]["completed_at"] = datetime.now().isoformat()
        if stdout_text:
            active_jobs[job_id]["output"] = stdout_text
        output_files = list(RESULTS_DIR.glob("ads*.json"))
        if output_files:
            active_jobs[job_id]["output_files"] = [str(f) for f in output_files]
    elif process:
        active_jobs[job_id]["status"] = "failed"
        active_jobs[job_id]["error"] = stderr_text if stderr_text else "Process failed with no error output"
        active_jobs[job_id]["stdout"] = stdout_text
        active_jobs[job_id]["return_code"] = process.returncode

def run_advertiser_scraper(job_id: str, request_data: AdvertiserScrapingRequest):
    """Run advertiser scraper in background"""
    try:
        active_jobs[job_id] = {"status": "running", "type": "advertiser", "started_at": datetime.now().isoformat()}

        # Create temporary config for this job
        temp_config = {
            "ADS_LIMIT": request_data.ads_limit,
            "TARGET_PAIRS": request_data.target_pairs,
            "HEADLESS": request_data.headless,
            "MAX_SCROLLS": request_data.max_scrolls,
            "AD_CATEGORY": request_data.ad_category,
            "STATUS": request_data.status,
            "LANGUAGES": request_data.languages,
            "PLATFORMS": request_data.platforms,
            "MEDIA_TYPE": request_data.media_type,
            "START_DATE": request_data.start_date,
            "END_DATE": request_data.end_date,
            "APPEND": request_data.append_mode,
            "ADVERTISERS": request_data.advertisers,
            "CONTINUATION": request_data.continuation
        }

        # Save temporary config
        temp_config_path = f"temp_advertiser_config_{job_id}.json"
        with open(temp_config_path, 'w', encoding='utf-8') as f:
            json.dump(temp_config, f, ensure_ascii=False, indent=2)

        # Set environment variables
        env = {
            "ADS_LIMIT": str(request_data.ads_limit),
            "HEADLESS": str(request_data.headless),
            "SCROLLS_SEARCH": str(request_data.max_scrolls),
            "SCROLLS_PAGE": str(request_data.max_scrolls),
            "APPEND": str(request_data.append_mode),
            "CONTINUATION": str(request_data.continuation),
            "TARGET_PAIRS": json.dumps(request_data.target_pairs, ensure_ascii=False),
            **dict(os.environ)
        }

        cmd = [sys.executable, "facebook_advertiser_ads.py", "--config", temp_config_path]

        # Use regular subprocess instead of asyncio subprocess (Windows compatibility)
        process = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,  # Automatically decode output as text
            encoding='utf-8',  # Explicitly specify UTF-8 encoding
            cwd=os.getcwd()  # Ensure correct working directory
        )

        stdout_text = process.stdout if process.stdout else ""
        stderr_text = process.stderr if process.stderr else ""

        # Log the output for debugging
        logger.info(f"Job {job_id} - Process return code: {process.returncode}")
        if stdout_text:
            logger.info(f"Job {job_id} - STDOUT: {stdout_text[:500]}...")
        if stderr_text:
            logger.error(f"Job {job_id} - STDERR: {stderr_text[:500]}...")

        # Clean up temp config
        try:
            os.remove(temp_config_path)
        except:
            pass

        # Check process result - return code takes priority
        if process.returncode == 0:
            active_jobs[job_id]["status"] = "completed"
            active_jobs[job_id]["completed_at"] = datetime.now().isoformat()
            # Store stdout for successful jobs
            if stdout_text:
                active_jobs[job_id]["output"] = stdout_text
            # Also check if output file exists
            output_file = RESULTS_DIR / "combined_ads.json"
            if output_file.exists():
                active_jobs[job_id]["output_file"] = str(output_file)
        else:
            active_jobs[job_id]["status"] = "failed"
            active_jobs[job_id]["error"] = stderr_text if stderr_text else "Process failed with no error output"
            active_jobs[job_id]["stdout"] = stdout_text
            active_jobs[job_id]["return_code"] = process.returncode
    except ValueError as e:
        logger.error(f"Job {job_id} - ValueError: {str(e)}")
        active_jobs[job_id]["status"] = "failed"
        active_jobs[job_id]["error"] = str(e)
    except Exception as e:
        logger.error(f"Job {job_id} - Exception: {str(e)}")
        logger.error(f"Job {job_id} - Traceback: {traceback.format_exc()}")
        active_jobs[job_id]["status"] = "failed"
        active_jobs[job_id]["error"] = str(e)

def run_pages_scraper(job_id: str, request_data: PageScrapingRequest):
    """Run pages scraper in background"""
    try:
        active_jobs[job_id] = {"status": "running", "type": "pages", "started_at": datetime.now().isoformat()}

        # Validate inputs based on search method
        if request_data.search_method == "keyword":
            if not request_data.keywords or len(request_data.keywords) == 0:
                raise ValueError("At least one keyword is required when search_method='keyword'")
            if len(request_data.keywords) > 10:
                raise ValueError("Maximum 10 keywords allowed")
        elif request_data.search_method == "url":
            if not request_data.urls or len(request_data.urls) == 0:
                raise ValueError("At least one URL is required when search_method='url'")
            if len(request_data.urls) > 20:
                raise ValueError("Maximum 20 URLs allowed")

        # Create temporary config for this job
        temp_config = {
            "SEARCH_METHOD": request_data.search_method,
            "HEADLESS": request_data.headless,
            "POST_LIMIT": request_data.post_limit,
            "ACCOUNT_NUMBER": request_data.account_number,
        }

        # Add method-specific configuration
        if request_data.search_method == "keyword":
            temp_config["KEYWORDS"] = request_data.keywords
        elif request_data.search_method == "url":
            temp_config["URLS"] = request_data.urls        # Save temporary config
        temp_config_path = f"temp_pages_config_{job_id}.json"
        with open(temp_config_path, 'w', encoding='utf-8') as f:
            json.dump(temp_config, f, ensure_ascii=False, indent=2)

        # Set environment variables
        env = {
            "SEARCH_METHOD": request_data.search_method,
            "HEADLESS": str(request_data.headless),
            "POST_LIMIT": str(request_data.post_limit),
            "ACCOUNT_NUMBER": str(request_data.account_number),
            **dict(os.environ)
        }        # Get the current Python executable (from the virtual environment)
        python_executable = sys.executable

        cmd = [python_executable, "facebook_pages_scraper.py", "--config", temp_config_path]

        # Use regular subprocess instead of asyncio subprocess (Windows compatibility)
        process = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,  # Automatically decode output as text
            encoding='utf-8',  # Explicitly specify UTF-8 encoding
            cwd=os.getcwd()  # Ensure correct working directory
        )

        stdout_text = process.stdout if process.stdout else ""
        stderr_text = process.stderr if process.stderr else ""

        # Log the output for debugging
        logger.info(f"Job {job_id} - Process return code: {process.returncode}")
        if stdout_text:
            logger.info(f"Job {job_id} - STDOUT: {stdout_text[:500]}...")
        if stderr_text:
            logger.error(f"Job {job_id} - STDERR: {stderr_text[:500]}...")        # Clean up temp config
        try:
            os.remove(temp_config_path)
        except:
            pass

        # Check process result - return code takes priority
        if process.returncode == 0:
            active_jobs[job_id]["status"] = "completed"
            active_jobs[job_id]["completed_at"] = datetime.now().isoformat()
            # Store stdout for successful jobs
            if stdout_text:
                active_jobs[job_id]["output"] = stdout_text
            # Also check if output file exists
            output_file = RESULTS_DIR / "all_pages.json"
            if output_file.exists():
                active_jobs[job_id]["output_file"] = str(output_file)
        else:
            active_jobs[job_id]["status"] = "failed"
            active_jobs[job_id]["error"] = stderr_text if stderr_text else "Process failed with no error output"
            active_jobs[job_id]["stdout"] = stdout_text
            active_jobs[job_id]["return_code"] = process.returncode
    except ValueError as e:
        logger.error(f"Job {job_id} - ValueError: {str(e)}")
        active_jobs[job_id]["status"] = "failed"
        active_jobs[job_id]["error"] = str(e)
    except Exception as e:
        logger.error(f"Job {job_id} - Exception: {str(e)}")
        logger.error(f"Job {job_id} - Traceback: {traceback.format_exc()}")
        active_jobs[job_id]["status"] = "failed"
        active_jobs[job_id]["error"] = str(e)

def run_suggestions_scraper(job_id: str, request_data: SuggestionsScrapingRequest):
    """Run suggestions scraper in background"""
    try:
        active_jobs[job_id] = {"status": "running", "type": "suggestions", "started_at": datetime.now().isoformat()}

        # Import and use the suggestions scraper directly
        from suggestions_scraper_api import SuggestionsScraperAPI

        scraper = SuggestionsScraperAPI()

        # Use asyncio.run to handle the async function
        import asyncio
        result = asyncio.run(scraper.scrape_suggestions(
            target_pairs=request_data.target_pairs,
            scrape_advertiser_ads=request_data.scrape_advertiser_ads,
            headless=request_data.headless,
            advertiser_ads_limit=request_data.advertiser_ads_limit
        ))

        # Update job status
        active_jobs[job_id]["status"] = "completed"
        active_jobs[job_id]["completed_at"] = datetime.now().isoformat()
        active_jobs[job_id]["results"] = result
        logger.info(f"Suggestions job {job_id} completed successfully")

    except Exception as e:
        error_msg = f"Suggestions job {job_id} failed with exception: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        active_jobs[job_id] = {
            "status": "failed",
            "error": error_msg,
            "started_at": active_jobs.get(job_id, {}).get("started_at", datetime.now().isoformat())
        }

def run_posts_scraper(job_id: str, request_data: PostsScrapingRequest):
    """Run posts scraper in background"""
    process = None
    stdout_text = ""
    stderr_text = ""

    try:
        active_jobs[job_id] = {"status": "running", "type": "posts", "started_at": datetime.now().isoformat()}

        # Create environment variables with default settings and always use proxy
        env = dict(os.environ)
        env.update({
            "LINKS": json.dumps(request_data.links, ensure_ascii=False),
            "APPEND_RESULTS": "false",  # Always create new numbered files
            "USE_PROXY": "true",        # Always use proxy
            "PROXY_ENDPOINT": "http://250621Ev04e-resi_region-US_California:5PjDM1IoS0JSr2c@ca.proxy-jet.io:1010",
            "TIMEOUT": "15",            # Default timeout
            "MAX_RETRIES": "3"          # Default retries
        })

        # Create command to run the scraper
        cmd = [sys.executable, "posts_scraper.py"]

        # Use regular subprocess instead of asyncio subprocess (Windows compatibility)
        process = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,  # Automatically decode output as text
            encoding='utf-8',  # Explicitly specify UTF-8 encoding
            cwd=os.getcwd()  # Ensure correct working directory
        )

        stdout_text = process.stdout if process.stdout else ""
        stderr_text = process.stderr if process.stderr else ""

        # Log the output for debugging
        logger.info(f"Job {job_id} - Process return code: {process.returncode}")
        if stdout_text:
            logger.info(f"Job {job_id} - STDOUT: {stdout_text[:500]}...")
        if stderr_text:
            logger.error(f"Job {job_id} - STDERR: {stderr_text[:500]}...")

        # Update job status based on process result
        if process.returncode == 0:
            active_jobs[job_id]["status"] = "completed"
            active_jobs[job_id]["completed_at"] = datetime.now().isoformat()
            logger.info(f"Job {job_id} completed successfully")
        else:
            active_jobs[job_id]["status"] = "failed"
            active_jobs[job_id]["error"] = stderr_text
            logger.error(f"Job {job_id} failed with return code {process.returncode}")

    except Exception as e:
        error_msg = f"Job {job_id} failed with exception: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        active_jobs[job_id] = {
            "status": "failed",
            "error": error_msg,
            "started_at": active_jobs.get(job_id, {}).get("started_at", datetime.now().isoformat())
        }

    # Final status check
    if process and process.returncode == 0:
        active_jobs[job_id]["status"] = "completed"
        active_jobs[job_id]["completed_at"] = datetime.now().isoformat()
        if stdout_text:
            active_jobs[job_id]["output"] = stdout_text
        output_files = list(RESULTS_DIR.glob("*posts*.json")) + list(RESULTS_DIR.glob("results_*.json"))
        if output_files:
            active_jobs[job_id]["output_files"] = [str(f) for f in output_files]
    elif process:
        active_jobs[job_id]["status"] = "failed"
        active_jobs[job_id]["error"] = stderr_text if stderr_text else "Process failed with no error output"
        active_jobs[job_id]["stdout"] = stdout_text
        active_jobs[job_id]["return_code"] = process.returncode

# API Endpoints

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

# POST endpoints to start scraping jobs

@app.post("/scrape/ads", response_model=ScrapingResponse)
async def start_ads_scraping(
    background_tasks: BackgroundTasks,
    request_data: AdsScrapingRequest = Body(...)
):
    """
    Start ads scraping job
    """
    try:
        job_id = generate_job_id()

        # Add background task
        background_tasks.add_task(run_ads_scraper, job_id, request_data)

        logger.info(f"Started ads scraping job: {job_id}")

        return ScrapingResponse(
            success=True,
            message="Ads scraping job started successfully",
            job_id=job_id,
            status="running",
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error starting ads scraping: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/scrape/advertisers", response_model=ScrapingResponse)
async def start_advertiser_scraping(
    background_tasks: BackgroundTasks,
    request_data: AdvertiserScrapingRequest = Body(...)
):
    """
    Start advertiser scraping job
    """
    try:
        job_id = generate_job_id()

        # Add background task
        background_tasks.add_task(run_advertiser_scraper, job_id, request_data)

        logger.info(f"Started advertiser scraping job: {job_id}")

        return ScrapingResponse(
            success=True,
            message="Advertiser scraping job started successfully",
            job_id=job_id,
            status="running",
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error starting advertiser scraping: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/scrape/pages", response_model=ScrapingResponse)
async def start_pages_scraping(
    background_tasks: BackgroundTasks,
    request_data: PageScrapingRequest = Body(...)
):
    """
    Start Facebook pages scraping job
    """
    try:
        job_id = generate_job_id()

        # Add background task
        background_tasks.add_task(run_pages_scraper, job_id, request_data)

        logger.info(f"Started pages scraping job: {job_id}")

        return ScrapingResponse(
            success=True,
            message="Pages scraping job started successfully",
            job_id=job_id,
            status="running",
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error starting pages scraping: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/scrape/suggestions", response_model=ScrapingResponse)
async def start_suggestions_scraping(
    background_tasks: BackgroundTasks,
    request_data: SuggestionsScrapingRequest = Body(...)
):
    """
    Start suggestions scraping job
    """
    try:
        job_id = generate_job_id()

        # Add background task
        background_tasks.add_task(run_suggestions_scraper, job_id, request_data)

        logger.info(f"Started suggestions scraping job: {job_id}")

        return ScrapingResponse(
            success=True,
            message="Suggestions scraping job started successfully",
            job_id=job_id,
            status="running",
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error starting suggestions scraping: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/scrape/posts", response_model=ScrapingResponse)
async def start_posts_scraping(
    background_tasks: BackgroundTasks,
    request_data: PostsScrapingRequest = Body(...)
):
    """
    Start Facebook posts scraping job
    """
    try:
        job_id = generate_job_id()

        # Add background task
        background_tasks.add_task(run_posts_scraper, job_id, request_data)

        logger.info(f"Started posts scraping job: {job_id}")

        return ScrapingResponse(
            success=True,
            message="Posts scraping job started successfully",
            job_id=job_id,
            status="running",
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error starting posts scraping: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# GET endpoints to retrieve data from JSON files

@app.get("/scrape/ads", response_model=DataResponse)
async def get_ads_data(
    keyword: str = Query(..., description="Search term for filtering ads by keyword"),
    category: str = Query(default="all", description="Filter ads by category"),
    location: str = Query(default="thailand", description="Filter ads by location"),
    language: str = Query(default="thai", description="Filter ads by language"),
    advertiser: str = Query(default="all", description="Filter ads by advertiser"),
    platform: str = Query(default="all", description="Filter ads by platform"),
    media_type: str = Query(default="all", description="Filter ads by media type"),
    status: str = Query(default="all", description="Filter ads by status (active/inactive)"),
    start_date: str = Query(default="June 18, 2018", description="Filter ads from this date"),
    end_date: str = Query(default="today", description="Filter ads until this date"),
    limit: int = Query(default=1000, description="Number of results per page", ge=1, le=1000000)
):
    """
    Get ads data with filtering parameters as specified in the PDF
    """
    try:
        # Convert "today" to current date
        if end_date.lower() == "today":
            end_date = datetime.now().strftime("%Y-%m-%d")

        # Convert start_date if needed
        if start_date == "June 18, 2018":
            start_date = "2018-06-18"

        # Load and filter ads data from JSON files
        data_files = []
        ads_files = list(RESULTS_DIR.glob("ads*.json"))

        all_data = []
        for file_path in ads_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    file_data = json.load(f)
                    if isinstance(file_data, list):
                        # Each item in the list represents a country-keyword pair result
                        for item in file_data:
                            if isinstance(item, dict):
                                # Filter based on keyword (search within country-keyword pairs)
                                item_keyword = item.get("keyword", "").lower()
                                if keyword.lower() in item_keyword:
                                    # Filter ads within this pair
                                    ads_in_pair = item.get("ads", [])
                                    filtered_ads = []

                                    for ad in ads_in_pair:
                                        # Apply filters
                                        if category != "all" and ad.get("category", "").lower() != category.lower():
                                            continue
                                        if location != "thailand" and item.get("country", "").lower() != location.lower():
                                            continue
                                        if language != "thai" and not any(lang.lower() == language.lower() for lang in ad.get("languages", [])):
                                            continue
                                        if advertiser != "all" and ad.get("page", "").lower() != advertiser.lower():
                                            continue
                                        if platform != "all" and not any(plat.lower() == platform.lower() for plat in ad.get("platforms", [])):
                                            continue
                                        if media_type != "all" and ad.get("media_type", "").lower() != media_type.lower():
                                            continue
                                        if status != "all" and ad.get("status", "").lower() != status.lower():
                                            continue

                                        # Add to filtered results
                                        filtered_ads.append(ad)

                                        # Check limit
                                        if len(all_data) + len(filtered_ads) >= limit:
                                            break

                                    all_data.extend(filtered_ads)

                                    # Check limit
                                    if len(all_data) >= limit:
                                        break
                            else:
                                # If it's not a dict, treat it as raw data
                                all_data.append({"data": item})
                    else:
                        # If file_data is not a list, add it as is
                        all_data.append(file_data if isinstance(file_data, dict) else {"data": file_data})

                data_files.append({
                    "file": file_path.name,
                    "size": file_path.stat().st_size,
                    "modified": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
                })

                # Check limit
                if len(all_data) >= limit:
                    break

            except Exception as e:
                logger.error(f"Error reading {file_path}: {e}")

        # Apply final limit
        all_data = all_data[:limit]

        return DataResponse(
            success=True,
            data=all_data,
            file_info={
                "total_files": len(data_files),
                "total_records": len(all_data),
                "files": data_files,
                "filters_applied": {
                    "keyword": keyword,
                    "category": category,
                    "location": location,
                    "language": language,
                    "advertiser": advertiser,
                    "platform": platform,
                    "media_type": media_type,
                    "status": status,
                    "start_date": start_date,
                    "end_date": end_date,
                    "limit": limit
                }
            },
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error retrieving ads data: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/data/advertisers", response_model=DataResponse)
async def get_advertisers_data_legacy():
    """
    Get advertisers data from JSON files (legacy endpoint)
    """
    try:
        data_files = []
        advertiser_files = list(RESULTS_DIR.glob("combined_ads*.json"))

        all_data = []
        for file_path in advertiser_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    file_data = json.load(f)
                    if isinstance(file_data, list):
                        all_data.extend(file_data)
                    else:
                        all_data.append(file_data)
                data_files.append({
                    "file": file_path.name,
                    "size": file_path.stat().st_size,
                    "modified": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
                })
            except Exception as e:
                logger.error(f"Error reading {file_path}: {e}")

        return DataResponse(
            success=True,
            data=all_data,
            file_info={
                "total_files": len(data_files),
                "total_records": len(all_data),
                "files": data_files
            },
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error retrieving advertisers data: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/data/suggestions", response_model=DataResponse)
async def get_suggestions_data():
    """
    Get suggestions data from JSON files
    """
    try:
        data_files = []
        suggestions_files = list(RESULTS_DIR.glob("suggestions*.json"))

        all_data = []
        for file_path in suggestions_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    file_data = json.load(f)
                    if isinstance(file_data, list):
                        all_data.extend([item if isinstance(item, dict) else {"data": item} for item in file_data])
                    else:
                        all_data.append(file_data if isinstance(file_data, dict) else {"data": file_data})
                data_files.append({
                    "file": file_path.name,
                    "size": file_path.stat().st_size,
                    "modified": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
                })
            except Exception as e:
                logger.error(f"Error reading {file_path}: {e}")

        return DataResponse(
            success=True,
            data=all_data,
            file_info={
                "total_files": len(data_files),
                "total_records": len(all_data),
                "files": data_files
            },
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error retrieving suggestions data: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/data/pages", response_model=DataResponse)
async def get_pages_data():
    """
    Get pages data from JSON files
    """
    try:
        data_files = []
        pages_files = list(RESULTS_DIR.glob("pages*.json"))

        all_data = []
        for file_path in pages_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    file_data = json.load(f)
                    if isinstance(file_data, list):
                        all_data.extend([item if isinstance(item, dict) else {"data": item} for item in file_data])
                    else:
                        all_data.append(file_data if isinstance(file_data, dict) else {"data": file_data})
                data_files.append({
                    "file": file_path.name,
                    "size": file_path.stat().st_size,
                    "modified": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
                })
            except Exception as e:
                logger.error(f"Error reading {file_path}: {e}")

        return DataResponse(
            success=True,
            data=all_data,
            file_info={
                "total_files": len(data_files),
                "total_records": len(all_data),
                "files": data_files
            },
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error retrieving pages data: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/data/posts", response_model=DataResponse)
async def get_posts_data(
    links: List[str] = Query(..., description="List of Facebook post URLs to retrieve data for")
):
    """
    Get posts data for specific links from JSON files.
    If links are not found in existing files, automatically scrape them.
    """
    try:
        data_files = []
        found_data = []
        missing_links = []

        # Look for results files that contain post data
        results_files = list(RESULTS_DIR.glob("results_*.json"))

        # Create a mapping of source URLs to their data
        url_to_data = {}

        # Read all existing result files and map URLs to data
        for file_path in results_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    file_data = json.load(f)

                    if isinstance(file_data, list):
                        for item in file_data:
                            if isinstance(item, dict):
                                # Try to get source_url from meta or directly from item
                                source_url = None
                                if 'meta' in item and isinstance(item['meta'], dict):
                                    source_url = item['meta'].get('source_url')
                                if not source_url:
                                    source_url = item.get('source_url')

                                if source_url:
                                    url_to_data[source_url] = item
                    else:
                        # Single item file
                        if isinstance(file_data, dict):
                            source_url = None
                            if 'meta' in file_data and isinstance(file_data['meta'], dict):
                                source_url = file_data['meta'].get('source_url')
                            if not source_url:
                                source_url = file_data.get('source_url')

                            if source_url:
                                url_to_data[source_url] = file_data

                data_files.append({
                    "file": file_path.name,
                    "size": file_path.stat().st_size,
                    "modified": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
                })

            except Exception as e:
                logger.error(f"Error reading {file_path}: {e}")

        # Check which links we have data for and which are missing
        for link in links:
            if link in url_to_data:
                found_data.append(url_to_data[link])
            else:
                missing_links.append(link)

        # If we have missing links, scrape them automatically
        scraped_data = []
        if missing_links:
            logger.info(f"Found {len(missing_links)} missing links, starting automatic scraping...")

            try:
                # Create a scraping request for missing links
                from fastapi import BackgroundTasks

                # Generate a job ID for the scraping task
                scrape_job_id = generate_job_id()

                # Create the request data for posts scraping
                scrape_request = PostsScrapingRequest(links=missing_links)

                # Run the scraper synchronously (wait for completion)
                run_posts_scraper(scrape_job_id, scrape_request)

                # Wait for the scraping job to complete (poll the job status)
                import time
                max_wait_time = 120  # 2 minutes max wait
                wait_interval = 2  # Check every 2 seconds
                elapsed_time = 0

                while elapsed_time < max_wait_time:
                    if scrape_job_id in active_jobs:
                        job_status = active_jobs[scrape_job_id].get("status")
                        if job_status == "completed":
                            logger.info(f"Scraping job {scrape_job_id} completed successfully")
                            break
                        elif job_status == "failed":
                            logger.error(f"Scraping job {scrape_job_id} failed")
                            break

                    time.sleep(wait_interval)
                    elapsed_time += wait_interval

                # Try to read the newly scraped data
                new_results_files = list(RESULTS_DIR.glob("results_*.json"))

                # Find the newest files (created after our scraping started)
                for file_path in new_results_files:
                    if file_path not in [f["file"] for f in data_files]:  # New file
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                file_data = json.load(f)

                                if isinstance(file_data, list):
                                    for item in file_data:
                                        if isinstance(item, dict):
                                            source_url = None
                                            if 'meta' in item and isinstance(item['meta'], dict):
                                                source_url = item['meta'].get('source_url')
                                            if not source_url:
                                                source_url = item.get('source_url')

                                            if source_url and source_url in missing_links:
                                                scraped_data.append(item)
                                else:
                                    # Single item file
                                    if isinstance(file_data, dict):
                                        source_url = None
                                        if 'meta' in file_data and isinstance(file_data['meta'], dict):
                                            source_url = file_data['meta'].get('source_url')
                                        if not source_url:
                                            source_url = file_data.get('source_url')

                                        if source_url and source_url in missing_links:
                                            scraped_data.append(file_data)

                        except Exception as e:
                            logger.error(f"Error reading newly scraped file {file_path}: {e}")

            except Exception as e:
                logger.error(f"Error during automatic scraping: {e}")

        # Combine found data and newly scraped data
        all_data = found_data + scraped_data

        # Update data files info to include any new files
        current_files = list(RESULTS_DIR.glob("results_*.json"))
        for file_path in current_files:
            if file_path.name not in [f["file"] for f in data_files]:
                data_files.append({
                    "file": file_path.name,
                    "size": file_path.stat().st_size,
                    "modified": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
                })

        return DataResponse(
            success=True,
            data=all_data,
            file_info={
                "total_files": len(data_files),
                "total_records": len(all_data),
                "files": data_files,
                "requested_links": len(links),
                "found_in_existing_files": len(found_data),
                "newly_scraped": len(scraped_data),
                "missing_links": [link for link in missing_links if link not in [item.get('meta', {}).get('source_url') or item.get('source_url') for item in scraped_data]]
            },
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error retrieving posts data: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """
    Get status of a specific job
    """
    if job_id not in active_jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": job_id,
        "status": active_jobs[job_id]["status"],
        "details": active_jobs[job_id],
        "timestamp": datetime.now().isoformat()
    }

@app.get("/jobs")
async def get_all_jobs():
    """
    Get status of all jobs
    """
    return {
        "jobs": active_jobs,
        "total_jobs": len(active_jobs),
        "timestamp": datetime.now().isoformat()
    }

@app.get("/status")
async def get_status():
    """Get API status and statistics"""
    return {
        "api_version": "2.0.0",
        "status": "operational",
        "scraping_endpoints": [
            "POST /scrape/ads",
            "POST /scrape/advertisers",
            "POST /scrape/pages",
            "POST /scrape/suggestions",
            "POST /scrape/posts"
        ],
        "data_endpoints": [
            "GET /data/ads",
            "GET /data/advertisers",
            "GET /data/pages",
            "GET /data/suggestions",
            "GET /data/advertiser-ads",
            "GET /data/posts"
        ],
        "active_jobs": len(active_jobs),
        "timestamp": datetime.now().isoformat()
    }

# Keep the original /data/ads endpoint for backward compatibility
@app.get("/data/ads", response_model=DataResponse)
async def get_ads_data_legacy():
    """
    Get all ads data from JSON files (legacy endpoint)
    """
    try:
        data_files = []
        ads_files = list(RESULTS_DIR.glob("ads*.json"))

        all_data = []
        for file_path in ads_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    file_data = json.load(f)
                    if isinstance(file_data, list):
                        all_data.extend([item if isinstance(item, dict) else {"data": item} for item in file_data])
                    else:
                        all_data.append(file_data if isinstance(file_data, dict) else {"data": file_data})
                data_files.append({
                    "file": file_path.name,
                    "size": file_path.stat().st_size,
                    "modified": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
                })
            except Exception as e:
                logger.error(f"Error reading {file_path}: {e}")

        return DataResponse(
            success=True,
            data=all_data,
            file_info={
                "total_files": len(data_files),
                "total_records": len(all_data),
                "files": data_files
            },
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error retrieving ads data: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
        timeout_keep_alive=300,
        limit_concurrency=1000
    )
