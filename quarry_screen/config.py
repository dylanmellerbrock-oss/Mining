"""Defaults and tunables for quarry-screen."""

from __future__ import annotations

import os
from pathlib import Path

# Westerville, OH — screening origin.
WESTERVILLE_LAT = 40.1261
WESTERVILLE_LON = -82.9291

# Screening defaults (override via CLI flags).
DEFAULT_RADIUS_MI = 40
DEFAULT_MIN_ACRES = 20
DEFAULT_MAX_PRICE = 2_000_000
DEFAULT_THICKNESS_FT = 20
DEFAULT_RECOVERY = 0.7
DEFAULT_MAX_PAGES = 10
DEFAULT_REQUEST_DELAY_S = 3.0

# Paths.
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
OUTPUT_DIR = REPO_ROOT / "output"
GEOLOGY_CACHE = DATA_DIR / "odgs_glacial.gpkg"
LISTINGS_CACHE = DATA_DIR / "listings.csv"

# Scraper identity — please set a real contact.
USER_AGENT = os.environ.get(
    "QUARRY_SCREEN_UA",
    "quarry-screen/0.1 (+https://github.com/your-org/quarry-screen)",
)

# ODGS GIS download. Override with env var once a stable URL is pinned.
# ODGS publishes Quaternary/glacial geology as a zipped shapefile on their
# GIS downloads page (geosurvey.ohiodnr.gov). We accept either a direct
# .zip/.gpkg URL or a local path.
ODGS_GLACIAL_URL = os.environ.get(
    "ODGS_GLACIAL_URL",
    # Placeholder — operators should set this env var to the current ODGS
    # download link (or a local file path) before running fetch-geology.
    "",
)

# Projection for area math in central Ohio (UTM 17N, meters).
WORKING_CRS = "EPSG:26917"
WGS84 = "EPSG:4326"

# Unit conversions.
SQ_M_PER_ACRE = 4046.8564224
FT_PER_M = 3.28084
M_PER_FT = 1 / FT_PER_M
YD3_PER_M3 = 1.30795
TONS_PER_YD3_SANDGRAVEL = 1.4  # loose short tons per cubic yard.
MI_PER_M = 1 / 1609.344

# Favorability rules — keyword → class. First match wins, checked in order.
# Applied against the ODGS unit name (case-insensitive, substring).
FAVORABILITY_RULES: list[tuple[str, str]] = [
    # Exclusions first so "till-cored kame" doesn't fall through to "till".
    ("outwash", "high"),
    ("kame", "high"),
    ("esker", "high"),
    ("ice-contact", "high"),
    ("ice contact", "high"),
    ("stratified drift", "high"),
    ("alluvium", "high"),
    ("alluvial", "high"),
    ("terrace", "medium"),
    ("valley train", "high"),
    ("lacustrine sand", "medium"),
    ("beach", "medium"),
    ("dune", "medium"),
    ("loess", "low"),
    ("till", "low"),
    ("lacustrine clay", "low"),
    ("lake clay", "low"),
    ("peat", "low"),
    ("organic", "low"),
    ("bedrock", "low"),
    ("shale", "low"),
    ("limestone", "low"),
]

FAVORABILITY_WEIGHT = {"high": 1.0, "medium": 0.5, "low": 0.0}
FAVORABILITY_COLOR = {"high": "#2a9d8f", "medium": "#e9c46a", "low": "#adb5bd"}
