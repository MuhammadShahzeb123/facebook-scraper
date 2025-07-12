# Facebook Scraper Proxy Integration Guide

## Overview

This document explains the proxy integration implemented across the Facebook scrapers. The proxy system has been integrated into:

- ✅ `ads_and_suggestions_scraper2.py` - **NEW PROXY SUPPORT**
- ✅ `facebook_advertiser_ads.py` - **NEW PROXY SUPPORT**
- ✅ `facebook_pages_scraper.py` - **EXISTING PROXY SUPPORT**

## How It Works

### 1. Proxy Configuration File

The system uses `proxies.json` to store proxy configurations:

```json
[
   "122.8.43.208,8208,PXY_c1elo8vs,6ogyx88w3o",
   "45.207.142.74,9568,arudiba,1wgiRQDM2ZRIhzP"
]
```

**Format**: `"host,port,username,password"`

### 2. Proxy Utility System

The `proxy_utils.py` module provides:

- **`load_proxies()`** - Loads and parses proxies from `proxies.json`
- **`select_random_proxy()`** - Randomly selects a proxy from available ones
- **`format_proxy_string()`** - Formats proxy for SeleniumBase compatibility
- **`get_proxy_string()`** - Main function that returns a ready-to-use proxy string

### 3. Integration Pattern

Each scraper follows this pattern:

```python
from proxy_utils import get_proxy_string

def main():
    # Get proxy configuration
    proxy_string = get_proxy_string()
    if proxy_string:
        print(f"[INFO] Using proxy: {proxy_string.split('@')[-1]}")
        with SB(uc=True, headless=HEADLESS, proxy=proxy_string) as sb:
            run_scraping_logic(sb, ...)
    else:
        print("[INFO] No proxy configured - running without proxy")
        with SB(uc=True, headless=HEADLESS) as sb:
            run_scraping_logic(sb, ...)
```

## Features

### ✅ Automatic Proxy Selection
- Randomly selects from available proxies each time a scraper runs
- Provides load balancing across multiple proxies

### ✅ Graceful Fallback
- If no proxies are available, scrapers run without proxy
- No crashes or errors if `proxies.json` is missing or empty

### ✅ Secure Logging
- Masks passwords in console output
- Shows only host:port and username for security

### ✅ Format Validation
- Validates proxy format before use
- Handles malformed proxy entries gracefully

### ✅ Cross-Platform Compatibility
- Works on Windows, macOS, and Linux
- Handles Unicode characters properly

## Usage Examples

### Running Scrapers with Proxy

```bash
# All these now automatically use proxies:
python ads_and_suggestions_scraper2.py
python facebook_advertiser_ads.py
python facebook_pages_scraper.py
```

### Expected Console Output

```
[INFO] Using proxy: 122.8.43.208:8208
[INFO] Opening Facebook …
[INFO] Restoring session cookies …
```

### Testing Proxy Integration

```bash
python test_proxy_integration.py
```

## Configuration Details

### Adding New Proxies

1. Edit `proxies.json`
2. Add entries in format: `"host,port,username,password"`
3. Save the file
4. Run any scraper - it will automatically use the new proxies

### Removing Proxies

1. Remove entries from `proxies.json`
2. Save the file
3. Scrapers will use remaining proxies

### Disabling Proxies Temporarily

1. Rename `proxies.json` to `proxies.json.backup`
2. Scrapers will run without proxy
3. Rename back to re-enable proxies

## Error Handling

### Common Issues and Solutions

**Issue**: "No proxies available"
- **Solution**: Check if `proxies.json` exists and has valid entries

**Issue**: Proxy connection fails
- **Solution**: Verify proxy credentials and server availability

**Issue**: Scraper runs slowly
- **Solution**: Try different proxy or check proxy server performance

### Debug Mode

For debugging proxy issues, run:

```python
from proxy_utils import test_proxy_loading
test_proxy_loading()
```

This will show:
- Number of loaded proxies
- Formatted proxy strings
- Random selection testing

## Security Considerations

### ✅ Password Protection
- Passwords are never logged in plain text
- Console output masks sensitive information

### ✅ Connection Security
- All proxy connections use the credentials from `proxies.json`
- No hardcoded credentials in source code

### ✅ File Security
- `proxies.json` should be kept secure and not shared publicly
- Consider adding it to `.gitignore` if using version control

## Performance Impact

### Minimal Overhead
- Proxy loading happens once per scraper run
- Random selection is O(1) operation
- No performance impact on scraping speed

### Load Balancing
- Different scrapers may use different proxies
- Natural load distribution across proxy servers

## Compatibility

### SeleniumBase Integration
- Uses SeleniumBase's built-in proxy support
- Format: `username:password@host:port`
- Automatic proxy configuration for Chrome/Firefox

### Existing Configuration
- `facebook_pages_scraper.py` maintains its existing `config.json` proxy system
- New system is independent and doesn't conflict

## Migration Notes

### For Existing Users
- No changes needed to existing scripts
- Proxy functionality is automatically available
- Old proxy configurations continue to work

### For New Users
1. Create `proxies.json` with your proxy details
2. Run any scraper - proxy support is automatic
3. Use `test_proxy_integration.py` to verify setup

## Future Enhancements

Potential improvements for future versions:

- **Proxy Health Monitoring** - Automatic proxy health checks
- **Failover Support** - Switch proxies on connection failure
- **Geographic Routing** - Select proxies based on target location
- **Usage Statistics** - Track proxy usage and performance
- **Configuration UI** - Web interface for proxy management

## Support

For proxy-related issues:

1. Run `python test_proxy_integration.py` to diagnose problems
2. Check console logs for proxy selection messages
3. Verify proxy credentials and server availability
4. Ensure `proxies.json` format is correct

## Summary

The proxy integration provides:
- ✅ **Automatic proxy rotation** across multiple scrapers
- ✅ **Secure credential handling** with masked logging
- ✅ **Graceful fallback** when proxies are unavailable
- ✅ **Zero configuration** for basic usage
- ✅ **Cross-platform compatibility** for all environments

All Facebook scrapers now support proxy functionality out of the box!
