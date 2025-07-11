# Facebook Scraper API

This project provides a REST API for scraping data from Facebook. It allows you to start scraping jobs for ads, advertisers, pages, and posts, and then retrieve the scraped data.

## Getting Started

### Prerequisites

- Python 3.8+
- Pip

### Installation

1. **Install dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

### Running the API

To start the FastAPI server, run the following command in the project's root directory:

```bash
uvicorn app:app --reload
```

The API will be available at `http://127.0.0.1:8000`.

## API Endpoints

The API provides several endpoints to start scraping jobs and retrieve data.

### Start Scraping Jobs

These `POST` endpoints initiate background scraping tasks.

#### `POST /scrape/ads`

Starts a job to scrape ads from the Facebook Ad Library.

**Request Body:**

```json
{
  "headless": true,
  "max_scrolls": 10,
  "ads_limit": 1000,
  "target_pairs": [["Thailand", "properties"]],
  "ad_category": "all",
  "status": "active",
  "languages": [],
  "platforms": [],
  "media_type": "all",
  "start_date": null,
  "end_date": null,
  "append_mode": true,
  "advertisers": [],
  "continuation": true
}
```

**Response:**

```json
{
  "success": true,
  "message": "Scraping job for ads started successfully.",
  "job_id": "job_1678886400_1234",
  "status": "running",
  "timestamp": "2025-07-08T12:00:00Z"
}
```

#### `POST /scrape/advertisers`

Starts a job to scrape advertisers.

**Request Body:**

```json
{
  "headless": true,
  "max_scrolls": 10,
  "ads_limit": 1000,
  "target_pairs": [["Ukraine", "rental apartments"]]
}
```

**Response:**

```json
{
  "success": true,
  "message": "Scraping job for advertisers started successfully.",
  "job_id": "job_1678886401_5678",
  "status": "running",
  "timestamp": "2025-07-08T12:00:01Z"
}
```

#### `POST /scrape/pages`

Starts a job to scrape Facebook pages based on keywords or URLs.

**Request Body (by keyword):**

```json
{
  "headless": true,
  "post_limit": 100,
  "account_number": 2,
  "search_method": "keyword",
  "keywords": ["real estate", "property management"]
}
```

**Request Body (by URL):**

```json
{
  "headless": true,
  "post_limit": 100,
  "account_number": 2,
  "search_method": "url",
  "urls": ["https://www.facebook.com/somepage"]
}
```

**Response:**

```json
{
  "success": true,
  "message": "Scraping job for pages started successfully.",
  "job_id": "job_1678886402_9012",
  "status": "running",
  "timestamp": "2025-07-08T12:00:02Z"
}
```

#### `POST /scrape/suggestions`

Starts a job to scrape suggested advertisers.

**Request Body:**

```json
{
  "headless": true,
  "target_pairs": [["Thailand", "properties"]],
  "scrape_advertiser_ads": true,
  "advertiser_ads_limit": 100
}
```

**Response:**

```json
{
  "success": true,
  "message": "Scraping job for suggestions started successfully.",
  "job_id": "job_1678886403_3456",
  "status": "running",
  "timestamp": "2025-07-08T12:00:03Z"
}
```

#### `POST /scrape/posts`

Starts a job to scrape specific Facebook posts from a list of URLs.

**Request Body:**

```json
{
  "links": ["https://www.facebook.com/somepost"]
}
```

**Response:**

```json
{
  "success": true,
  "message": "Scraping job for posts started successfully.",
  "job_id": "job_1678886404_7890",
  "status": "running",
  "timestamp": "2025-07-08T12:00:04Z"
}
```

### Retrieve Scraped Data

These `GET` endpoints retrieve the data collected by the scraping jobs.

#### `GET /scrape/ads`

Retrieves scraped ads data.

**Response:**

```json
{
  "success": true,
  "data": [/* array of ad objects */],
  "file_info": {
    "path": "Results/ads.json",
    "size": 10240,
    "last_modified": "2025-07-08T12:30:00Z"
  },
  "timestamp": "2025-07-08T12:30:05Z"
}
```

#### `GET /data/advertisers`

Retrieves scraped advertisers data.

#### `GET /data/suggestions`

Retrieves scraped suggestions data.

#### `GET /data/pages`

Retrieves scraped pages data.

#### `GET /data/posts`

Retrieves scraped posts data.

### Job and System Status

#### `GET /jobs/{job_id}`

Get the status of a specific scraping job.

**Response:**

```json
{
  "job_id": "job_1678886400_1234",
  "status": "completed",
  "start_time": "2025-07-08T12:00:00Z",
  "end_time": "2025-07-08T12:15:00Z",
  "duration": "15 minutes",
  "result_file": "Results/ads.json"
}
```

#### `GET /jobs`

Get the status of all active jobs.

#### `GET /status`

A health check endpoint to verify that the API is running.

**Response:**

```json
{
  "status": "ok",
  "timestamp": "2025-07-08T12:45:00Z"
}
```
