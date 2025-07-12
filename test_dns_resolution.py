#!/usr/bin/env python3
"""
Test to diagnose ERR_NAME_NOT_RESOLVED issue with Facebook access
"""

import requests
import socket
from proxy_utils_enhanced import load_proxies, get_proxy_string_with_fallback

def test_dns_resolution():
    """Test DNS resolution for Facebook."""
    print("Testing DNS resolution...")
    
    facebook_domains = [
        'facebook.com',
        'www.facebook.com',
        'm.facebook.com'
    ]
    
    for domain in facebook_domains:
        try:
            ip = socket.gethostbyname(domain)
            print(f"✅ {domain} resolves to: {ip}")
        except socket.gaierror as e:
            print(f"❌ {domain} DNS resolution failed: {e}")

def test_facebook_direct_access():
    """Test direct Facebook access without proxy."""
    print("\nTesting direct Facebook access...")
    
    try:
        response = requests.get('https://www.facebook.com', timeout=10)
        print(f"✅ Direct access status: {response.status_code}")
        print(f"   Content length: {len(response.content)} bytes")
    except Exception as e:
        print(f"❌ Direct access failed: {e}")

def test_proxy_dns_resolution():
    """Test DNS resolution through proxy."""
    print("\nTesting proxy DNS resolution...")
    
    proxies = load_proxies()
    if not proxies:
        print("❌ No proxies configured")
        return
    
    for i, proxy_tuple in enumerate(proxies, 1):
        host, port, username, password = proxy_tuple
        print(f"\n--- PROXY {i}: {username}@{host}:{port} ---")
        
        proxy_url = f"http://{username}:{password}@{host}:{port}"
        proxy_config = {
            'http': proxy_url,
            'https': proxy_url
        }
        
        # Test if proxy can resolve DNS
        try:
            # Test with a simple HTTP request
            response = requests.get(
                'http://httpbin.org/ip', 
                proxies=proxy_config, 
                timeout=10
            )
            print(f"✅ Proxy basic connectivity: {response.status_code}")
            
            # Test DNS resolution through proxy
            response = requests.get(
                'https://www.facebook.com', 
                proxies=proxy_config, 
                timeout=15,
                allow_redirects=False
            )
            print(f"✅ Facebook through proxy: {response.status_code}")
            
        except requests.exceptions.ProxyError as e:
            print(f"❌ Proxy connection failed: {e}")
        except requests.exceptions.ConnectTimeout as e:
            print(f"❌ Connection timeout: {e}")
        except requests.exceptions.SSLError as e:
            print(f"❌ SSL error: {e}")
        except Exception as e:
            print(f"❌ Other error: {e}")

def test_selenium_dns_with_proxy():
    """Test SeleniumBase DNS resolution with proxy."""
    print("\nTesting SeleniumBase DNS resolution with proxy...")
    
    try:
        from seleniumbase import SB
        
        proxy_string = get_proxy_string_with_fallback()
        if not proxy_string:
            print("❌ No working proxy available")
            return
        
        print(f"Using proxy: {proxy_string.split('@')[-1] if '@' in proxy_string else proxy_string}")
        
        # Test with proxy
        try:
            with SB(uc=True, proxy=proxy_string, headless=True) as sb:
                print("✅ SeleniumBase with proxy initialized")
                
                # Test simple site first
                try:
                    sb.open("http://httpbin.org/ip")
                    ip_text = sb.get_text("body")
                    print(f"✅ Basic connectivity: {ip_text.strip()}")
                except Exception as e:
                    print(f"❌ Basic connectivity failed: {e}")
                
                # Test Facebook
                try:
                    sb.open("https://www.facebook.com")
                    title = sb.get_title()
                    print(f"✅ Facebook access: {title}")
                except Exception as e:
                    if "ERR_NAME_NOT_RESOLVED" in str(e):
                        print("❌ DNS resolution failed through proxy")
                    else:
                        print(f"❌ Facebook access failed: {e}")
                        
        except Exception as e:
            print(f"❌ SeleniumBase setup failed: {e}")
    
    except ImportError:
        print("❌ SeleniumBase not available")

def main():
    """Run comprehensive DNS and connectivity tests."""
    print("Facebook DNS Resolution Diagnostics")
    print("=" * 50)
    
    test_dns_resolution()
    test_facebook_direct_access()
    test_proxy_dns_resolution()
    test_selenium_dns_with_proxy()
    
    print("\n" + "=" * 50)
    print("RECOMMENDATIONS:")
    print("1. If DNS resolution fails: Check your internet connection")
    print("2. If proxy DNS fails: Proxy may not support DNS resolution")
    print("3. If only Facebook fails: Facebook may be blocking proxy IPs")
    print("4. Try using different proxy servers or residential proxies")

if __name__ == "__main__":
    main()
