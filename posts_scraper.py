"""post_scraper_and_parser.py
================================

Self‑contained script that **fetches** a list of Facebook post URLs, **parses**
all Open Graph + Twitter‑card metadata (and any `<table>` elements), then
writes the combined results to JSON.

### How to use
1. Edit the **configuration block** at the top of the file – fill in your
   `LINKS`, choose whether to `APPEND_RESULTS`, and tweak `PROXY_ENDPOINT` or
   `HEADERS_POOL` if you like.
2. Run: `python post_scraper_and_parser.py`

Dependencies (install via pip if missing):
```
pip install beautifulsoup4 pandas requests
```

If **pandas** is not installed, table‑extraction will fall back to a lightweight
regex parser; everything else works fine.

---
"""
from __future__ import annotations

import json
import os
import random
import re
import sys
import time
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# ░█▀█░█▀▀░█▀▀░▀█▀░░░█▀▀░█▀▀░█▀█░█▀█░█▀▀░█▀▀
# ░█▀█░█▀▀░█░░░░█░░░░█░░░█▀▀░█▀▀░█░█░█░░░█▀▀
# ░▀░▀░▀▀▀░▀▀▀░░▀░░░░▀▀▀░▀▀▀░▀░░░▀▀▀░▀▀▀░▀░░
# Edit **only** this block to customise the run.
# ---------------------------------------------------------------------------

LINKS: List[str] = [
    "https://www.facebook.com/share/p/1CA6tAVYLE",
    "https://www.facebook.com/share/p/1C69DRmqvW",
    "https://www.facebook.com/share/v/16WCYTozyh"
]

APPEND_RESULTS: bool = False  # True → append to UNIVERSAL_JSON, False → new numbered file
OUTPUT_DIR: str = "Results"
UNIVERSAL_JSON: str = "all_posts.json"  # used only when APPEND_RESULTS is True

# HTTP  behaviour ----------------------------------------------------------
PROXY_ENDPOINT: str | None = (
    "http://250621Ev04e-resi_region-US_California:"  # type: ignore[assignment]
    "5PjDM1IoS0JSr2c@ca.proxy-jet.io:1010"
)
USE_PROXY: bool = True  # set False to disable proxy usage entirely
TIMEOUT: int = 15  # seconds

HEADERS_POOL: List[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.4; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 9 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36",
    "insomnia/11.2.0",
]

# ---------------------------------------------------------------------------
# Parsing engine (from previous PostParser) --------------------------------
# ---------------------------------------------------------------------------

# Optional but very handy – if pandas is missing we fall back gracefully
try:
    import pandas as pd  # type: ignore
except ModuleNotFoundError:
    pd = None  # type: ignore


class PostParser:
    """Parse a *single* Facebook post HTML page (desktop or mobile)."""

    _TYPE_MAP: Dict[str, str] = {
        "video": "video",
        "video.other": "video",
        "video.movie": "video",
        "video.tv_show": "video",
        "article": "article",
        "website": "link",
        "music.song": "audio",
        "photo": "picture",
    }

    def __init__(self, html: str):
        self.soup = BeautifulSoup(html, "html.parser")
        self.meta: Dict[str, str] = {}
        self.tables: List["pd.DataFrame" | List[Dict[str, Any]]] = []
        self.post_type: str = "unknown"
        self.media: List[str] = []

        self._parse_meta_tags()
        self._detect_post_type()
        self._collect_media_urls()
        self._parse_tables()

    # Public ----------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        serialisable_tables: List[List[Dict[str, Any]]] = []
        for tbl in self.tables:
            if pd is not None and isinstance(tbl, pd.DataFrame):
                serialisable_tables.append(tbl.to_dict(orient="records"))
            else:
                serialisable_tables.append(tbl)  # type: ignore[arg-type]
        return {
            "post_type": self.post_type,
            "meta": self.meta,
            "media": self.media,
            "tables": serialisable_tables,
        }

    # Internal helpers ------------------------------------------------------
    def _parse_meta_tags(self) -> None:
        for meta in self.soup.find_all("meta"):
            key = meta.get("property") or meta.get("name")
            if not key:
                continue
            key = key.lower().strip()
            if key.startswith("og:"):
                self.meta[key[3:]] = meta.get("content", "")
            elif key.startswith("twitter:"):
                self.meta[key] = meta.get("content", "")

    def _detect_post_type(self) -> None:
        og_type = self.meta.get("type", "")
        self.post_type = self._TYPE_MAP.get(og_type, og_type or "unknown")

    def _collect_media_urls(self) -> None:
        if "video" in self.post_type:
            for key in ("video", "video:url", "video:secure_url"):
                url = self.meta.get(key)
                if url:
                    self.media.append(url)
        if "image" in self.meta:
            self.media.append(self.meta["image"])

    def _parse_tables(self) -> None:
        html_str = str(self.soup)
        if pd is None:
            simple_tables = re.findall(r"<table.*?</table>", html_str, re.S | re.I)
            for raw in simple_tables:
                rows = re.findall(r"<tr.*?</tr>", raw, re.S | re.I)
                parsed_tbl: List[Dict[str, str]] = []
                header_cells: List[str] = []
                for ri, row in enumerate(rows):
                    cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S | re.I)
                    clean = [BeautifulSoup(c, "html.parser").get_text(strip=True) for c in cells]
                    if ri == 0:
                        header_cells = [c or f"col{ci}" for ci, c in enumerate(clean)]
                        continue
                    parsed_tbl.append({h: v for h, v in zip(header_cells, clean, strict=False)})
                self.tables.append(parsed_tbl)
        else:
            try:
                html_io = StringIO(html_str)
                self.tables.extend(pd.read_html(html_io))
            except (ValueError, AttributeError):
                pass


# ---------------------------------------------------------------------------
# Networking helpers --------------------------------------------------------
# ---------------------------------------------------------------------------

import urllib.parse as _ulib

_SESSION = requests.Session()
_SESSION.headers.update({"Accept-Language": "en-US,en;q=0.9"})

if USE_PROXY and PROXY_ENDPOINT:
    _SESSION.proxies.update({
        "http": PROXY_ENDPOINT,
        "https": PROXY_ENDPOINT,
    })


def _fallback_mbasic(url: str) -> str | None:
    """Transform `www.facebook.com/...` → `mbasic.facebook.com/...` (login-free)."""
    parsed = _ulib.urlparse(url)
    if parsed.netloc.startswith("www.facebook.com"):
        return _ulib.urlunparse(parsed._replace(netloc="mbasic.facebook.com"))
    return None


def fetch_html(url: str, max_retries: int = 3) -> str:
    """Fetch raw HTML for *url*.

    * random User-Agent (to reduce blocks); if that fails with 4xx we retry
      once via **mbasic.facebook.com** which often serves a lighter, login-free
      variant.
    * Retry mechanism: will retry up to max_retries times for each URL variant.
    """
    attempt_urls = [url]
    alt = _fallback_mbasic(url)
    if alt:
        attempt_urls.append(alt)

    for idx, target in enumerate(attempt_urls, 1):
        for retry in range(max_retries):
            headers = {"User-Agent": random.choice(HEADERS_POOL)}
            retry_suffix = f" (retry {retry + 1}/{max_retries})" if retry > 0 else ""
            print(f"→ GET {target}{retry_suffix}…", end=" ")
            try:
                r = _SESSION.get(target, headers=headers, timeout=TIMEOUT, allow_redirects=True)
                r.raise_for_status()
                print("✔︎")
                # Some feeds return x-frame wrappers – strip if present
                if "<iframe" in r.text[:1000] and "facebook.com/plugins/" in r.text:
                    # crude but works: follow first iframe src
                    src = re.search(r"src=\"([^\"]+)\"", r.text)
                    if src:
                        return fetch_html(src.group(1), max_retries)
                return r.text
            except requests.HTTPError as exc:
                code = exc.response.status_code if exc.response else "?"
                print(f"✘ HTTP {code}")
                if retry < max_retries - 1:
                    time.sleep(random.uniform(2, 5))  # Wait before retry
                elif idx == len(attempt_urls):
                    return ""
            except Exception as exc:
                print(f"✘ ({exc.__class__.__name__})")
                if retry < max_retries - 1:
                    time.sleep(random.uniform(2, 5))  # Wait before retry
                elif idx == len(attempt_urls):
                    return ""
    return ""

# ---------------------------------------------------------------------------
# Data validation helpers ---------------------------------------------------
# ---------------------------------------------------------------------------

def is_valid_extraction(post_dict: Dict[str, Any]) -> bool:
    """Check if the extracted data is meaningful and worth keeping.
    
    Returns False if:
    - Post type is unknown AND meta is empty
    - Only generic table data (like browser names) is found
    - No meaningful content extracted at all
    - Login/access wall detected
    """
    post_type = post_dict.get("post_type", "unknown")
    meta = post_dict.get("meta", {})
    media = post_dict.get("media", [])
    tables = post_dict.get("tables", [])
    
    # Check for login/access wall indicators
    title = meta.get("title", "").lower()
    description = meta.get("description", "").lower()
    
    login_indicators = [
        "log in or sign up",
        "log into facebook",
        "login to facebook", 
        "sign up for facebook",
        "see posts, photos and more on facebook",
        "facebook helps you connect",
        "create an account",
        "join facebook",
        "you must log in"
    ]
    
    for indicator in login_indicators:
        if indicator in title or indicator in description:
            return False
    
    # Check if tables contain only generic browser data (common false positive)
    if tables:
        for table in tables:
            if isinstance(table, list):
                for row in table:
                    if isinstance(row, dict):
                        values = list(row.values())
                        # Check for common browser names that indicate invalid extraction
                        browser_names = {"safari", "chrome", "firefox", "edge", "opera"}
                        if any(str(v).lower() in browser_names for v in values):
                            return False
    
    # If we have meaningful meta data (excluding login walls), it's likely valid
    if meta and any(key in meta for key in ["url", "image"]):
        # But make sure title/description aren't just login prompts
        if title and "log in" not in title and "sign up" not in title:
            return True
        if description and "see posts, photos and more" not in description:
            return True
    
    # If we have media URLs, it's likely valid
    if media:
        return True
    
    # If post type is not unknown, it's likely valid (but still check for login walls)
    if post_type != "unknown":
        return True
    
    # If we have no meaningful data at all, it's invalid
    if not meta and not media and post_type == "unknown" and not tables:
        return False
    
    # If we reach here with unknown post type and only login-related meta, it's invalid
    if post_type == "unknown" and not media and not tables:
        return False
    
    return True


# ---------------------------------------------------------------------------
# Orchestrator --------------------------------------------------------------
# ---------------------------------------------------------------------------

def ensure_output_dir() -> Path:
    out_dir = Path(OUTPUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def next_numbered_filename(out_dir: Path, stem: str = "results_") -> Path:
    existing = sorted(out_dir.glob(f"{stem}[0-9].json"))
    if not existing:
        return out_dir / f"{stem}1.json"
    last_num = int(existing[-1].stem.split("_")[-1])
    return out_dir / f"{stem}{last_num + 1}.json"


def load_existing_json(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_json(path: Path, data: List[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Main entry‑point ----------------------------------------------------------
# ---------------------------------------------------------------------------

def main() -> None:
    if not LINKS:
        print("No LINKS specified – edit the configuration block at the top of the file.")
        sys.exit(1)

    out_dir = ensure_output_dir()

    # Decide output path
    if APPEND_RESULTS:
        out_path = out_dir / UNIVERSAL_JSON
    else:
        out_path = next_numbered_filename(out_dir)

    results: List[Dict[str, Any]] = []
    if APPEND_RESULTS:
        results = load_existing_json(out_path)

    for url in LINKS:
        max_extraction_retries = 3
        successful_extraction = False
        
        for attempt in range(max_extraction_retries):
            html = fetch_html(url)
            if not html:
                continue
                
            parser = PostParser(html)
            post_dict = parser.to_dict()
            post_dict["source_url"] = url
            
            # Validate the extracted data
            if is_valid_extraction(post_dict):
                results.append(post_dict)
                successful_extraction = True
                print(f"✓ Successfully extracted valid data for {url}")
                break
            else:
                print(f"✗ Poor quality data extracted for {url} (attempt {attempt + 1}/{max_extraction_retries})")
                if attempt < max_extraction_retries - 1:
                    time.sleep(random.uniform(3, 6))  # Longer delay between extraction retries
        
        if not successful_extraction:
            print(f"⚠ Failed to extract valid data for {url} after {max_extraction_retries} attempts")
            
        # polite delay before next URL
        time.sleep(random.uniform(1.5, 3.0))

    # Validate and filter results
    valid_results = [r for r in results if is_valid_extraction(r)]

    save_json(out_path, valid_results)
    # print(f"Saved {len(valid_results)} valid post(s) → {out_path.relative_to(Path.cwd())}")


if __name__ == "__main__":
    main()
