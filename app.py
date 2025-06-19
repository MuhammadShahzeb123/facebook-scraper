#!/usr/bin/env python3
"""
Facebook Scraper REST API
Provides endpoints for scraping Facebook ads, advertisers, pages, and posts
"""

import asyncio
import logging
import time
import traceback
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse, parse_qs
import re

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, validator
import uvicorn

# Import our existing scraping modules
from ads_scraper_api import AdsScraperAPI
from advertiser_scraper_api import AdvertiserScraperAPI
from page_scraper_api import PageScraperAPI
from post_scraper_api import PostScraperAPI

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
    description="RESTful API for scraping Facebook ads, advertisers, pages, and posts",
    version="1.0.0",
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

# Initialize scraper APIs
ads_scraper = AdsScraperAPI()
advertiser_scraper = AdvertiserScraperAPI()
page_scraper = PageScraperAPI()
post_scraper = PostScraperAPI()

# Response models
class APIResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    timestamp: str
    processing_time: float

class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    timestamp: str

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

def validate_facebook_url(url: str) -> bool:
    """Validate if URL is a Facebook URL"""
    try:
        parsed = urlparse(url)
        return parsed.netloc in ['facebook.com', 'www.facebook.com', 'm.facebook.com']
    except:
        return False

def normalize_facebook_url(url: str) -> str:
    """Normalize Facebook URL to standard format"""
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    # Handle different Facebook URL formats
    parsed = urlparse(url)
    if 'profile.php' in parsed.path:
        # Extract ID from profile.php?id=123456
        query_params = parse_qs(parsed.query)
        if 'id' in query_params:
            return f"https://www.facebook.com/profile.php?id={query_params['id'][0]}"

    return url

@app.middleware("http")
async def log_requests(request, call_next):
    """Log all API requests"""
    start_time = time.time()
    client_ip = request.client.host

    # Rate limiting check
    if not rate_limit_check(client_ip):
        return JSONResponse(
            status_code=429,
            content=ErrorResponse(
                error="Rate limit exceeded. Try again later.",
                timestamp=datetime.now().isoformat()
            ).dict()
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
        content=ErrorResponse(
            error="Internal server error occurred",
            timestamp=datetime.now().isoformat()
        ).dict()
    )

# API Endpoints

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/ads_search", response_model=APIResponse)
async def ads_search(
    keyword: str = Query(..., description="Search term for filtering ads by keyword"),
    category: str = Query("all", description="Filter ads by category"),
    location: str = Query("thailand", description="Filter ads by location"),
    language: str = Query("thai", description="Filter ads by language"),
    advertiser: str = Query("all", description="Filter ads by advertiser"),
    platform: str = Query("all", description="Filter ads by platform"),
    media_type: str = Query("all", description="Filter ads by media type"),
    status: str = Query("all", description="Filter ads by status (active/inactive)"),
    start_date: str = Query("June 18, 2018", description="Start date for ads filtering"),
    end_date: str = Query("today", description="End date for ads filtering"),
    limit: int = Query(1000, ge=1, le=1000000, description="Number of results per page")
):
    """
    Scrape all pages from Meta Ads library based on given filter conditions
    """
    start_time = time.time()

    try:
        logger.info(f"Starting ads search for keyword: {keyword}")

        # Convert end_date if "today"
        if end_date.lower() == "today":
            end_date = datetime.now().strftime("%B %d, %Y")

        # Call the ads scraper
        result = await ads_scraper.search_ads(
            keyword=keyword,
            category=category,
            location=location,
            language=language,
            advertiser=advertiser,
            platform=platform,
            media_type=media_type,
            status=status,
            start_date=start_date,
            end_date=end_date,
            limit=limit
        )

        processing_time = time.time() - start_time

        return APIResponse(
            success=True,
            message=f"Successfully retrieved {len(result.get('ads', []))} ads",
            data=result,
            timestamp=datetime.now().isoformat(),
            processing_time=processing_time
        )

    except Exception as e:
        logger.error(f"Error in ads_search: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/advertiser_search", response_model=APIResponse)
async def advertiser_search(
    keyword: str = Query(..., description="Search term for filtering ads by keyword"),
    scrape_page: bool = Query(True, description="If True, scrape the advertiser's page data")
):
    """
    Get an advertisers list and their page data based on the given keyword
    """
    start_time = time.time()

    try:
        logger.info(f"Starting advertiser search for keyword: {keyword}")

        result = await advertiser_scraper.search_advertisers(
            keyword=keyword,
            scrape_page=scrape_page
        )

        processing_time = time.time() - start_time

        return APIResponse(
            success=True,
            message=f"Successfully retrieved {len(result.get('advertisers', []))} advertisers",
            data=result,
            timestamp=datetime.now().isoformat(),
            processing_time=processing_time
        )

    except Exception as e:
        logger.error(f"Error in advertiser_search: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/page_extract", response_model=APIResponse)
async def page_extract(
    url: str = Query(..., description="URL of the Facebook page"),
    extract_post: bool = Query(True, description="If yes, scrape posts from the page"),
    post_limit: int = Query(100, ge=1, le=1000, description="Number of posts to scrape per page")
):
    """
    Scrape page data based on given page URL
    Supports hybrid URL types:
    - https://www.facebook.com/thammasat.uni
    - https://www.facebook.com/profile.php?id=61571049031016
    """
    start_time = time.time()

    try:
        # Validate URL
        if not validate_facebook_url(url):
            raise HTTPException(status_code=400, detail="Invalid Facebook URL provided")

        # Normalize URL
        normalized_url = normalize_facebook_url(url)

        logger.info(f"Starting page extraction for URL: {normalized_url}")

        result = await page_scraper.extract_page(
            url=normalized_url,
            extract_posts=extract_post,
            post_limit=post_limit
        )

        processing_time = time.time() - start_time

        return APIResponse(
            success=True,
            message=f"Successfully extracted page data with {len(result.get('posts', []))} posts",
            data=result,
            timestamp=datetime.now().isoformat(),
            processing_time=processing_time
        )

    except Exception as e:
        logger.error(f"Error in page_extract: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/post_extract", response_model=APIResponse)
async def post_extract(
    url: str = Query(..., description="URL of the Facebook post")
):
    """
    Scrape post data based on given post URL
    Supports URLs like: https://www.facebook.com/share/p/1CA6tAVYLE/
    """
    start_time = time.time()

    try:
        # Validate URL
        if not validate_facebook_url(url):
            raise HTTPException(status_code=400, detail="Invalid Facebook URL provided")

        logger.info(f"Starting post extraction for URL: {url}")

        result = await post_scraper.extract_post(url=url)

        processing_time = time.time() - start_time

        return APIResponse(
            success=True,
            message="Successfully extracted post data",
            data=result,
            timestamp=datetime.now().isoformat(),
            processing_time=processing_time
        )

    except Exception as e:
        logger.error(f"Error in post_extract: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/status")
async def get_status():
    """Get API status and statistics"""
    return {
        "api_version": "1.0.0",
        "status": "operational",
        "endpoints": [
            "/ads_search",
            "/advertiser_search",
            "/page_extract",
            "/post_extract"
        ],
        "uptime": "Available",
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
