"""LandWatch scraper for Ohio land-for-sale listings.

LandWatch's detail pages embed structured JSON (Next.js __NEXT_DATA__ or
schema.org JSON-LD) with lat/lon, price, and acreage. This module pulls
search results, resolves each detail page, parses the structured payload,
and returns a clean DataFrame.

Notes:
- HTML selectors drift; treat this as a maintenance target. If LandWatch
  changes layout, update `_extract_from_detail`.
- Obey robots.txt. Rate-limited via `time.sleep` between requests.
- Terms of service are your responsibility — review before running at volume.
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.parse
import urllib.robotparser
from dataclasses import dataclass

import pandas as pd
import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from . import config

log = logging.getLogger(__name__)

LANDWATCH_BASE = "https://www.landwatch.com"
LANDWATCH_SEARCH = (
    LANDWATCH_BASE
    + "/ohio-land-for-sale/acres-{min_acres}-any/price-under-{max_price}/available/page-{page}"
)


@dataclass
class Listing:
    url: str
    title: str
    price: float | None
    acres: float | None
    lat: float | None
    lon: float | None
    county: str | None
    city: str | None


class LandWatchError(RuntimeError):
    pass


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": config.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    return s


def _robots_ok(url: str, ua: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = urllib.robotparser.RobotFileParser()
    try:
        rp.set_url(robots_url)
        rp.read()
    except Exception:
        log.warning("Could not read robots.txt at %s; proceeding cautiously", robots_url)
        return True
    return rp.can_fetch(ua, url)


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=2, min=2, max=16))
def _get(session: requests.Session, url: str) -> requests.Response:
    r = session.get(url, timeout=30)
    if r.status_code in (429, 500, 502, 503, 504):
        raise LandWatchError(f"{r.status_code} on {url}")
    r.raise_for_status()
    return r


_PRICE_RE = re.compile(r"\$\s*([\d,]+)")
_ACRES_RE = re.compile(r"([\d,]+(?:\.\d+)?)\s*ac", re.IGNORECASE)


def _parse_price(text: str | None) -> float | None:
    if not text:
        return None
    m = _PRICE_RE.search(text)
    return float(m.group(1).replace(",", "")) if m else None


def _parse_acres(text: str | None) -> float | None:
    if not text:
        return None
    m = _ACRES_RE.search(text)
    return float(m.group(1).replace(",", "")) if m else None


def _extract_next_data(html: str) -> dict | None:
    """LandWatch is a Next.js site — pull the hydration payload if present."""
    soup = BeautifulSoup(html, "lxml")
    tag = soup.find("script", id="__NEXT_DATA__")
    if tag and tag.string:
        try:
            return json.loads(tag.string)
        except json.JSONDecodeError:
            return None
    return None


def _extract_jsonld(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    out: list[dict] = []
    for tag in soup.find_all("script", type="application/ld+json"):
        if not tag.string:
            continue
        try:
            data = json.loads(tag.string)
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            out.extend(d for d in data if isinstance(d, dict))
        elif isinstance(data, dict):
            out.append(data)
    return out


def _deep_find(obj, keys: set[str], out: dict) -> None:
    """Recursively pull the first value for each requested key in a nested dict."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in keys and k not in out:
                out[k] = v
            _deep_find(v, keys, out)
    elif isinstance(obj, list):
        for item in obj:
            _deep_find(item, keys, out)


def _extract_from_detail(html: str, url: str) -> Listing | None:
    title = None
    price = acres = lat = lon = None
    county = city = None

    nd = _extract_next_data(html)
    if nd:
        found: dict = {}
        _deep_find(
            nd,
            {
                "latitude", "longitude", "lat", "lng", "lon",
                "price", "acres", "acreage", "totalAcres",
                "title", "headline", "county", "city", "locality",
            },
            found,
        )
        lat = found.get("latitude") or found.get("lat")
        lon = found.get("longitude") or found.get("lng") or found.get("lon")
        price = found.get("price")
        acres = found.get("acres") or found.get("acreage") or found.get("totalAcres")
        title = found.get("title") or found.get("headline")
        county = found.get("county")
        city = found.get("city") or found.get("locality")

    if lat is None or lon is None:
        for jd in _extract_jsonld(html):
            geo = jd.get("geo") if isinstance(jd, dict) else None
            if isinstance(geo, dict):
                lat = geo.get("latitude", lat)
                lon = geo.get("longitude", lon)
            if title is None:
                title = jd.get("name") or jd.get("headline")

    # Regex fallbacks from the raw HTML.
    if price is None:
        price = _parse_price(html)
    if acres is None:
        acres = _parse_acres(html)

    try:
        lat = float(lat) if lat is not None else None
        lon = float(lon) if lon is not None else None
    except (TypeError, ValueError):
        lat = lon = None
    try:
        price = float(price) if price is not None else None
    except (TypeError, ValueError):
        price = None
    try:
        acres = float(acres) if acres is not None else None
    except (TypeError, ValueError):
        acres = None

    if lat is None or lon is None:
        log.debug("No coordinates extracted from %s", url)
        return None

    return Listing(
        url=url,
        title=title or url,
        price=price,
        acres=acres,
        lat=lat,
        lon=lon,
        county=county,
        city=city,
    )


def _listing_urls_from_search(html: str) -> list[str]:
    """Pull detail-page URLs from a search results page."""
    soup = BeautifulSoup(html, "lxml")
    urls: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        # LandWatch detail URLs look like /<state>/<county>/<city>/<slug>/<id>
        # and typically end in a long numeric id.
        if re.search(r"/\d{5,}(?:/|$|\?)", href):
            full = urllib.parse.urljoin(LANDWATCH_BASE, href.split("?")[0])
            urls.add(full)
    return sorted(urls)


def scrape_landwatch(
    min_acres: int = config.DEFAULT_MIN_ACRES,
    max_price: int = config.DEFAULT_MAX_PRICE,
    max_pages: int = config.DEFAULT_MAX_PAGES,
    delay_s: float = config.DEFAULT_REQUEST_DELAY_S,
) -> pd.DataFrame:
    """Scrape LandWatch Ohio listings and return a DataFrame."""
    session = _session()
    rows: list[Listing] = []
    seen: set[str] = set()

    for page in range(1, max_pages + 1):
        search_url = LANDWATCH_SEARCH.format(
            min_acres=int(min_acres),
            max_price=int(max_price),
            page=page,
        )
        if not _robots_ok(search_url, config.USER_AGENT):
            raise LandWatchError(f"robots.txt disallows {search_url}")

        log.info("Search page %d: %s", page, search_url)
        try:
            resp = _get(session, search_url)
        except Exception as e:
            log.warning("Search page %d failed: %s", page, e)
            break

        detail_urls = [u for u in _listing_urls_from_search(resp.text) if u not in seen]
        if not detail_urls:
            log.info("No new detail URLs on page %d; stopping.", page)
            break

        for url in detail_urls:
            seen.add(url)
            time.sleep(delay_s)
            if not _robots_ok(url, config.USER_AGENT):
                log.info("robots.txt disallows %s; skipping", url)
                continue
            try:
                r = _get(session, url)
            except Exception as e:
                log.warning("Detail fetch failed for %s: %s", url, e)
                continue
            listing = _extract_from_detail(r.text, url)
            if listing is None:
                continue
            rows.append(listing)
        time.sleep(delay_s)

    df = pd.DataFrame([vars(r) for r in rows])
    log.info("Scraped %d listings", len(df))
    return df


def save_csv(df: pd.DataFrame, path) -> None:
    df.to_csv(path, index=False)


def load_csv(path) -> pd.DataFrame:
    return pd.read_csv(path)
