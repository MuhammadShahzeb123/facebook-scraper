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


if os.name == "nt":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('api.log'),
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
    redoc_url="/redoc"
)

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
    mode: Literal["ads", "suggestions", "ads_and_suggestions"] = Field(default="ads", description="Scraping mode")
    headless: bool = Field(default=True, description="Run browser in headless mode")
    ads_limit: int = Field(default=1000, description="Maximum number of ads to extract", gt=0, le=5000)
    target_pairs: List[List[str]] = Field(
        default=[["Thailand", "properties"]],
        description="List of [country, keyword] pairs"
    )

    # New advanced filtering parameters
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

class AdvertiserScrapingRequest(BaseModel):
    headless: bool = Field(default=True, description="Run browser in headless mode")
    ads_limit: int = Field(default=1000, description="Maximum number of ads to extract", gt=0, le=5000)
    target_pairs: List[List[str]] = Field(
        default=[["Ukraine", "rental apartments"], ["United States", "rental properties"]],
        description="List of [country, keyword] pairs"
    )

    @validator('target_pairs')
    def validate_target_pairs(cls, v):
        if not v or len(v) == 0:
            raise ValueError("At least one target pair is required")
        if len(v) > 20:
            raise ValueError("Maximum 20 target pairs allowed")
        for pair in v:
            if not isinstance(pair, list) or len(pair) != 2:
                raise ValueError("Each target pair must be a list with exactly 2 elements [country, keyword]")
            if not all(isinstance(item, str) and item.strip() for item in pair):
                raise ValueError("Both country and keyword must be non-empty strings")
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

def rate_limit_check(client_ip: str, limit: int = 10, window: int = 60) -> bool:
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
        return JSONResponse(
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
    return JSONResponse(
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

    return JSONResponse(
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
        return JSONResponse(
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
    try:
        active_jobs[job_id] = {"status": "running", "type": "ads", "started_at": datetime.now().isoformat()}

        # Create environment variables for all parameters
        env = dict(os.environ)
        env.update({
            "MODE": request_data.mode,
            "HEADLESS": str(request_data.headless),
            "ADS_LIMIT": str(request_data.ads_limit),
            "TARGET_PAIRS": json.dumps(request_data.target_pairs),
            "AD_CATEGORY": request_data.ad_category,
            "STATUS": request_data.status,
            "LANGUAGES": json.dumps(request_data.languages),
            "PLATFORMS": json.dumps(request_data.platforms),
            "MEDIA_TYPE": request_data.media_type,
            "START_DATE": request_data.start_date or "",
            "END_DATE": request_data.end_date or "",
            "APPEND": str(request_data.append_mode),
            "ADVERTISERS": json.dumps(request_data.advertisers),
            "CONTINUATION": str(request_data.continuation)
        })

        # Create command to run the scraper
        cmd = [sys.executable, "ads_and_suggestions_scraper.py"]

        # Use regular subprocess instead of asyncio subprocess (Windows compatibility)
        process = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,  # Automatically decode output as text
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

        # Check process result - return code takes priority
        if process.returncode == 0:
            active_jobs[job_id]["status"] = "completed"
            active_jobs[job_id]["completed_at"] = datetime.now().isoformat()
            # Store stdout for successful jobs
            if stdout_text:
                active_jobs[job_id]["output"] = stdout_text
            # Also check if output files exist
            output_files = list(RESULTS_DIR.glob("ads*.json"))
            if output_files:
                active_jobs[job_id]["output_files"] = [str(f) for f in output_files]
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

def run_advertiser_scraper(job_id: str, request_data: AdvertiserScrapingRequest):
    """Run advertiser scraper in background"""
    try:
        active_jobs[job_id] = {"status": "running", "type": "advertiser", "started_at": datetime.now().isoformat()}

        # Create temporary config for this job
        temp_config = {
            "ADS_LIMIT": request_data.ads_limit,
            "TARGET_PAIRS": request_data.target_pairs,
            "HEADLESS": request_data.headless
        }        # Save temporary config
        temp_config_path = f"temp_advertiser_config_{job_id}.json"
        with open(temp_config_path, 'w', encoding='utf-8') as f:
            json.dump(temp_config, f, ensure_ascii=False, indent=2)

        # Set environment variables
        env = {
            "ADS_LIMIT": str(request_data.ads_limit),
            "HEADLESS": str(request_data.headless),
            **dict(os.environ)
        }

        cmd = [sys.executable, "facebook_advertiser_ads.py", "--config", temp_config_path]        # Use regular subprocess instead of asyncio subprocess (Windows compatibility)
        process = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,  # Automatically decode output as text
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
    Start ads and suggestions scraping job
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

# GET endpoints to retrieve data from JSON files

@app.get("/data/ads", response_model=DataResponse)
async def get_ads_data():
    """
    Get ads data from JSON files
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

@app.get("/data/advertisers", response_model=DataResponse)
async def get_advertisers_data():
    """
    Get advertisers data from JSON files
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

@app.get("/data/pages", response_model=DataResponse)
async def get_pages_data():
    """
    Get pages data from JSON files
    """
    try:
        data_files = []
        pages_files = list(RESULTS_DIR.glob("all_pages*.json"))

        all_data = []
        for file_path in pages_files:
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
        logger.error(f"Error retrieving pages data: {str(e)}")
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
            "POST /scrape/pages"
        ],
        "data_endpoints": [
            "GET /data/ads",
            "GET /data/advertisers",
            "GET /data/pages"
        ],
        "active_jobs": len(active_jobs),
        "timestamp": datetime.now().isoformat()
    }

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
