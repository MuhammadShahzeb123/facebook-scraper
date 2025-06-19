# Facebook Scraper REST API

A comprehensive RESTful API for scraping Facebook data including ads, advertisers, pages, and posts. Built with FastAPI and SeleniumBase for reliable and scalable web scraping.

## 🚀 Features

- **4 Main Endpoints**: Ads search, advertiser search, page extraction, and post extraction
- **Production Ready**: Includes rate limiting, error handling, logging, and monitoring
- **Async Support**: Non-blocking operations with proper timeout handling
- **Docker Support**: Containerized deployment with Docker Compose
- **Load Balancing**: Nginx reverse proxy with rate limiting
- **Unit Tests**: Comprehensive test suite with pytest
- **Load Testing**: Built-in load testing tools
- **API Documentation**: Auto-generated OpenAPI/Swagger docs

## 📋 API Endpoints

### 1. Ads Search (`/ads_search`)
Scrape ads from Meta Ads Library based on filter conditions.

**Method**: `GET`

**Parameters**:
- `keyword` (required): Search term for filtering ads
- `category` (optional): Filter by category (default: "all")
- `location` (optional): Filter by location (default: "thailand")
- `language` (optional): Filter by language (default: "thai")
- `advertiser` (optional): Filter by advertiser (default: "all")
- `platform` (optional): Filter by platform (default: "all")
- `media_type` (optional): Filter by media type (default: "all")
- `status` (optional): Filter by status (default: "all")
- `start_date` (optional): Start date (default: "June 18, 2018")
- `end_date` (optional): End date (default: "today")
- `limit` (optional): Number of results (default: 1000, max: 1,000,000)

**Example**:
```bash
curl "http://localhost:8000/ads_search?keyword=coffee&location=thailand&limit=100"
```

### 2. Advertiser Search (`/advertiser_search`)
Get advertisers list and their page data based on keyword.

**Method**: `GET`

**Parameters**:
- `keyword` (required): Search term for filtering
- `scrape_page` (optional): Scrape advertiser page data (default: true)

**Example**:
```bash
curl "http://localhost:8000/advertiser_search?keyword=starbucks&scrape_page=true"
```

### 3. Page Extract (`/page_extract`)
Scrape Facebook page data from URL.

**Method**: `GET`

**Parameters**:
- `url` (required): Facebook page URL
- `extract_post` (optional): Extract posts from page (default: true)
- `post_limit` (optional): Number of posts to scrape (default: 100)

**Supported URL formats**:
- `https://www.facebook.com/thammasat.uni`
- `https://www.facebook.com/profile.php?id=61571049031016`

**Example**:
```bash
curl "http://localhost:8000/page_extract?url=https://facebook.com/starbucks&extract_post=true&post_limit=50"
```

### 4. Post Extract (`/post_extract`)
Scrape individual Facebook post data.

**Method**: `GET`

**Parameters**:
- `url` (required): Facebook post URL

**Supported URL formats**:
- `https://www.facebook.com/share/p/1CA6tAVYLE/`
- `https://www.facebook.com/page/posts/123456789`

**Example**:
```bash
curl "http://localhost:8000/post_extract?url=https://facebook.com/share/p/1CA6tAVYLE/"
```

## 🛠 Installation & Setup

### Prerequisites
- Python 3.11+
- Facebook account cookies
- Chrome/Chromium browser (for SeleniumBase)

### Local Development Setup

1. **Clone the repository**:
```bash
git clone <repository-url>
cd facebook-scraper
```

2. **Install dependencies**:
```bash
pip install -r requirements.txt
```

3. **Configure Facebook cookies**:
   - Export your Facebook cookies to `saved_cookies/facebook_cookies.txt`
   - Update `config.json` with your account details and proxy settings

4. **Run the API**:
```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

5. **Access API documentation**:
   - Swagger UI: http://localhost:8000/docs
   - ReDoc: http://localhost:8000/redoc

### Docker Deployment

1. **Build and run with Docker Compose**:
```bash
docker-compose up -d
```

2. **Check logs**:
```bash
docker-compose logs -f facebook-scraper-api
```

3. **Scale the service**:
```bash
docker-compose up -d --scale facebook-scraper-api=3
```

### Production Deployment

1. **Environment Variables**:
```bash
export LOG_LEVEL=info
export WORKERS=4
export MAX_REQUESTS=1000
```

2. **SSL Configuration** (nginx.conf):
```nginx
server {
    listen 443 ssl http2;
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    # ... rest of configuration
}
```

3. **Monitoring Setup**:
```bash
# Install monitoring tools
pip install prometheus-fastapi-instrumentator
```

## 🧪 Testing

### Run Unit Tests
```bash
# Run all tests
pytest test_api.py -v

# Run specific test class
pytest test_api.py::TestAPIEndpoints -v

# Run with coverage
pytest test_api.py --cov=app --cov-report=html
```

### Load Testing
```bash
# Basic load test
python load_test.py --users 10 --requests 5

# Stress test specific endpoint
python load_test.py --endpoint ads_search --stress 100

# Test against production
python load_test.py --url https://your-api-domain.com --users 20
```

## 📊 Response Format

All endpoints return a consistent JSON response format:

```json
{
  "success": true,
  "message": "Successfully retrieved 45 ads",
  "data": {
    "keyword": "coffee",
    "location": "thailand",
    "total_found": 45,
    "ads": [...],
    "extracted_at": "2025-06-20T10:30:00"
  },
  "timestamp": "2025-06-20T10:30:00",
  "processing_time": 23.45
}
```

### Error Response Format
```json
{
  "success": false,
  "error": "Invalid Facebook URL provided",
  "timestamp": "2025-06-20T10:30:00"
}
```

## ⚡ Performance & Limits

### Rate Limiting
- **Default**: 10 requests per minute per IP
- **Ads Search**: 5 requests per minute (burst)
- **Page Extract**: 3 requests per minute (burst)
- **Configurable** via nginx.conf

### Timeouts
- **Connection**: 60 seconds
- **Ads/Advertiser Search**: 300 seconds
- **Page Extract**: 300 seconds
- **Post Extract**: 120 seconds

### Concurrency
- **Default Workers**: 4 (configurable)
- **Max Concurrent Requests**: 10
- **Connection Pool**: 100 connections

## 🔧 Configuration

### config.json Structure
```json
{
  "accounts": {
    "1": {
      "proxy": "host,port,username,password",
      "cookies": [
        {
          "domain": ".facebook.com",
          "name": "cookie_name",
          "value": "cookie_value",
          "sameSite": "lax"
        }
      ]
    }
  }
}
```

### Environment Variables
- `LOG_LEVEL`: Logging level (default: info)
- `WORKERS`: Number of worker processes
- `MAX_REQUESTS`: Max requests per worker
- `PYTHONPATH`: Python module path

## 🚨 Production Considerations

### Security
- **Rate Limiting**: Implemented at nginx and application level
- **Input Validation**: All parameters validated with Pydantic
- **Error Handling**: Comprehensive exception handling
- **Logging**: Detailed logging for monitoring and debugging

### Monitoring
- **Health Checks**: `/health` endpoint for load balancer
- **Metrics**: Processing time, success rates, error rates
- **Logs**: Structured logging with timestamps and request IDs

### Scaling
- **Horizontal**: Scale with Docker Compose or Kubernetes
- **Vertical**: Increase worker processes and memory
- **Load Balancing**: Nginx with upstream servers

### Backup & Recovery
- **Data**: Results stored in `Results/` directory
- **Cookies**: Backup `saved_cookies/` directory
- **Config**: Version control for configuration files

## 🐛 Troubleshooting

### Common Issues

1. **Cookie Expiration**:
```bash
# Check cookie validity
curl "http://localhost:8000/health"
# Re-export cookies from browser
```

2. **Rate Limiting**:
```bash
# Check rate limit headers
curl -I "http://localhost:8000/ads_search?keyword=test"
```

3. **Timeout Issues**:
```bash
# Check logs
docker-compose logs facebook-scraper-api
# Increase timeout in nginx.conf
```

4. **Memory Issues**:
```bash
# Monitor memory usage
docker stats
# Reduce concurrent requests or increase memory limit
```

### Debug Mode
```bash
# Enable debug logging
export LOG_LEVEL=debug
uvicorn app:app --reload --log-level debug
```

## 📈 Monitoring & Alerting

### Health Monitoring
```bash
# Health check endpoint
curl http://localhost:8000/health

# Status with metrics
curl http://localhost:8000/status
```

### Log Analysis
```bash
# Real-time logs
tail -f api.log

# Error analysis
grep "ERROR" api.log | tail -20
```

### Performance Monitoring
```bash
# Load test results
cat load_test_results.json | jq '.summary'

# Response time analysis
grep "processing_time" api.log | awk '{print $NF}'
```

## 📚 API Examples

### Complete Workflow Example
```python
import requests
import time

base_url = "http://localhost:8000"

# 1. Search for ads
ads_response = requests.get(f"{base_url}/ads_search", params={
    "keyword": "coffee shop",
    "location": "thailand",
    "limit": 50
})

# 2. Get advertisers for the keyword
advertisers_response = requests.get(f"{base_url}/advertiser_search", params={
    "keyword": "coffee shop",
    "scrape_page": True
})

# 3. Extract specific page data
page_response = requests.get(f"{base_url}/page_extract", params={
    "url": "https://facebook.com/starbucks",
    "extract_post": True,
    "post_limit": 20
})

# 4. Extract specific post
post_response = requests.get(f"{base_url}/post_extract", params={
    "url": "https://facebook.com/share/p/example/"
})

print("Workflow completed successfully!")
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Run the test suite
6. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 📞 Support

For support and questions:
- Create an issue in the repository
- Check the troubleshooting section
- Review the API documentation at `/docs`
