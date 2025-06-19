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
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from pathlib import Path
import re

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import uvicorn

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
    mode: str = Field(default="ads", description="ads, suggestions, or ads_and_suggestions")
    headless: bool = Field(default=True, description="Run browser in headless mode")
    ads_limit: int = Field(default=1000, description="Maximum number of ads to extract")
    target_pairs: List[List[str]] = Field(
        default=[["Ukraine", "rental apartments"], ["United States", "rental properties"]],
        description="List of [country, keyword] pairs"
    )

class AdvertiserScrapingRequest(BaseModel):
    headless: bool = Field(default=True, description="Run browser in headless mode")
    ads_limit: int = Field(default=1000, description="Maximum number of ads to extract")
    target_pairs: List[List[str]] = Field(
        default=[["Ukraine", "rental apartments"], ["United States", "rental properties"]],
        description="List of [country, keyword] pairs"
    )

class PageScrapingRequest(BaseModel):
    search_method: str = Field(default="keyword", description="keyword or url")
    headless: bool = Field(default=True, description="Run browser in headless mode")
    post_limit: int = Field(default=100, description="Number of posts to scrape per page")
    account_number: int = Field(default=2, description="Facebook account number to use (1, 2, or 3)")
    keywords: List[str] = Field(
        default=["coca cola", "pepsi", "burger king"],
        description="Keywords to search for (when search_method=keyword)"
    )
    urls: List[str] = Field(
        default=["https://www.facebook.com/CokePakistan"],
        description="URLs to scrape (when search_method=url)"
    )

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
    client_ip = request.client.host

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

# Async functions to run scrapers
async def run_ads_scraper(job_id: str, request_data: AdsScrapingRequest):
    """Run ads scraper in background"""
    try:
        active_jobs[job_id] = {"status": "running", "type": "ads", "started_at": datetime.now().isoformat()}

        # Create temporary config for this job
        temp_config = {
            "MODE": request_data.mode,
            "HEADLESS": request_data.headless,
            "ADS_LIMIT": request_data.ads_limit,
            "TARGET_PAIRS": request_data.target_pairs
        }

        # Save temporary config
        temp_config_path = f"temp_ads_config_{job_id}.json"
        with open(temp_config_path, 'w') as f:
            json.dump(temp_config, f)

        # Create command arguments
        cmd = [
            "python", "ads_and_suggestions_scraper.py",
            "--config", temp_config_path
        ]

        # Set environment variables as fallback
        env = {
            "MODE": request_data.mode,
            "HEADLESS": str(request_data.headless),
            "ADS_LIMIT": str(request_data.ads_limit),
            **dict(os.environ)
        }

        # Run scraper
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )

        stdout, stderr = await process.communicate()

        # Clean up temp config
        try:
            os.remove(temp_config_path)
        except:
            pass

        if process.returncode == 0:
            active_jobs[job_id]["status"] = "completed"
            active_jobs[job_id]["completed_at"] = datetime.now().isoformat()
        else:
            active_jobs[job_id]["status"] = "failed"
            active_jobs[job_id]["error"] = stderr.decode()
    except Exception as e:
        active_jobs[job_id]["status"] = "failed"
        active_jobs[job_id]["error"] = str(e)

async def run_advertiser_scraper(job_id: str, request_data: AdvertiserScrapingRequest):
    """Run advertiser scraper in background"""
    try:
        active_jobs[job_id] = {"status": "running", "type": "advertiser", "started_at": datetime.now().isoformat()}

        # Create temporary config for this job
        temp_config = {
            "ADS_LIMIT": request_data.ads_limit,
            "TARGET_PAIRS": request_data.target_pairs,
            "HEADLESS": request_data.headless
        }

        # Save temporary config
        temp_config_path = f"temp_advertiser_config_{job_id}.json"
        with open(temp_config_path, 'w') as f:
            json.dump(temp_config, f)

        # Set environment variables
        env = {
            "ADS_LIMIT": str(request_data.ads_limit),
            "HEADLESS": str(request_data.headless),
            **dict(os.environ)
        }

        cmd = ["python", "facebook_advertiser_ads.py", "--config", temp_config_path]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )

        stdout, stderr = await process.communicate()

        # Clean up temp config
        try:
            os.remove(temp_config_path)
        except:
            pass

        if process.returncode == 0:
            active_jobs[job_id]["status"] = "completed"
            active_jobs[job_id]["completed_at"] = datetime.now().isoformat()
        else:
            active_jobs[job_id]["status"] = "failed"
            active_jobs[job_id]["error"] = stderr.decode()
    except Exception as e:
        active_jobs[job_id]["status"] = "failed"
        active_jobs[job_id]["error"] = str(e)

async def run_pages_scraper(job_id: str, request_data: PageScrapingRequest):
    """Run pages scraper in background"""
    try:
        active_jobs[job_id] = {"status": "running", "type": "pages", "started_at": datetime.now().isoformat()}

        # Create temporary config for this job
        temp_config = {
            "SEARCH_METHOD": request_data.search_method,
            "HEADLESS": request_data.headless,
            "POST_LIMIT": request_data.post_limit,
            "ACCOUNT_NUMBER": request_data.account_number,
            "KEYWORDS": request_data.keywords,
            "URLS": request_data.urls
        }

        # Save temporary config
        temp_config_path = f"temp_pages_config_{job_id}.json"
        with open(temp_config_path, 'w') as f:
            json.dump(temp_config, f)

        # Set environment variables
        env = {
            "SEARCH_METHOD": request_data.search_method,
            "HEADLESS": str(request_data.headless),
            "POST_LIMIT": str(request_data.post_limit),
            "ACCOUNT_NUMBER": str(request_data.account_number),
            **dict(os.environ)
        }

        cmd = ["python", "facebook_pages_scraper.py", "--config", temp_config_path]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )

        stdout, stderr = await process.communicate()

        # Clean up temp config
        try:
            os.remove(temp_config_path)
        except:
            pass

        if process.returncode == 0:
            active_jobs[job_id]["status"] = "completed"
            active_jobs[job_id]["completed_at"] = datetime.now().isoformat()
        else:
            active_jobs[job_id]["status"] = "failed"
            active_jobs[job_id]["error"] = stderr.decode()
    except Exception as e:
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
        limit_concurrency=10
    )
