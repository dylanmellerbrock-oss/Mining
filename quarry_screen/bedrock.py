"""ODGS bedrock geology loader and Columbus/Delaware Limestone classifier."""

from __future__ import annotations

import logging
import shutil
import tempfile
import zipfile
from pathlib import Path

import geopandas as gpd
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from . import config

log = logging.getLogger(__name__)


_CODE_CANDIDATES = ("UNIT_CODE", "CODE", "MAP_UNIT", "MAPUNIT", "UNIT", "SYMBOL")
_NAME_CANDIDATES = ("UNIT_NAME", "DESCRIPTIO", "DESCRIPTION", "LITHOLOGY", "NAME", "FORMATION")


def classify_bedrock(unit_code: str | None, unit_name: str | None) -> str:
    """Map an ODGS bedrock unit code/name to 'high' | 'medium' | 'low'.

    Columbus Limestone ("Dc") is the prime sweet-spot host; Delaware
    Limestone ("Dd") is secondary. Shales, sandstones, siltstones, and coal
    are dealbreakers.
    """
    if unit_code:
        code = unit_code.strip().lower()
        if code in config.BEDROCK_CODE_RULES:
            return config.BEDROCK_CODE_RULES[code]
    if unit_name:
        haystack = unit_name.lower()
        for keyword, label in config.BEDROCK_NAME_RULES:
            if keyword in haystack:
                return label
    return "low"


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=2, min=2, max=16))
def _download(url: str, dest: Path) -> None:
    log.info("Downloading %s", url)
    headers = {"User-Agent": config.USER_AGENT}
    with requests.get(url, headers=headers, stream=True, timeout=120) as r:
        r.raise_for_status()
        with dest.open("wb") as f:
            shutil.copyfileobj(r.raw, f)


def fetch_bedrock(url: str | None = None, refresh: bool = False) -> Path:
    """Download and cache the ODGS bedrock geology layer as GeoPackage."""
    url = url or config.ODGS_BEDROCK_URL
    if not url:
        raise RuntimeError(
            "No ODGS bedrock source configured. Set ODGS_BEDROCK_URL or "
            "pass --source to a shapefile/GeoPackage URL or local path."
        )

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = config.BEDROCK_CACHE
    if out.exists() and not refresh:
        log.info("Using cached bedrock at %s", out)
        return out

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        src_local = Path(url)
        if src_local.exists():
            local_src = src_local
        else:
            download_name = url.split("?")[0].rsplit("/", 1)[-1] or "download.bin"
            local_src = tmp_path / download_name
            _download(url, local_src)

        if local_src.suffix.lower() == ".zip":
            with zipfile.ZipFile(local_src) as z:
                z.extractall(tmp_path)
            shp = next(tmp_path.rglob("*.shp"), None)
            if shp is None:
                raise RuntimeError(f"No .shp found in {local_src}")
            gdf = gpd.read_file(shp)
        else:
            gdf = gpd.read_file(local_src)

        gdf = _prepare_bedrock(gdf)
        gdf.to_file(out, driver="GPKG")
        log.info("Wrote %s (%d polygons)", out, len(gdf))
    return out


def _pick_column(gdf: gpd.GeoDataFrame, candidates: tuple[str, ...]) -> str | None:
    for cand in candidates:
        if cand in gdf.columns:
            return cand
    return None


def _prepare_bedrock(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Attach 'unit_code', 'unit_name', 'bedrock_class' columns."""
    code_col = _pick_column(gdf, _CODE_CANDIDATES)
    name_col = _pick_column(gdf, _NAME_CANDIDATES)
    if code_col is None and name_col is None:
        raise RuntimeError("Could not find bedrock unit code/name column")

    gdf = gdf.copy()
    gdf["unit_code"] = gdf[code_col].astype(str) if code_col else ""
    gdf["unit_name"] = gdf[name_col].astype(str) if name_col else ""
    gdf["bedrock_class"] = [
        classify_bedrock(c, n) for c, n in zip(gdf["unit_code"], gdf["unit_name"])
    ]
    if gdf.crs is None:
        log.warning("Bedrock layer has no CRS; assuming WGS84")
        gdf = gdf.set_crs(config.WGS84)
    return gdf[["unit_code", "unit_name", "bedrock_class", "geometry"]]


def load_bedrock(path: Path | None = None) -> gpd.GeoDataFrame:
    """Load cached bedrock with a bedrock_class column."""
    path = path or config.BEDROCK_CACHE
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run `quarry-screen fetch-bedrock` first."
        )
    gdf = gpd.read_file(path)
    if "bedrock_class" not in gdf.columns:
        gdf = _prepare_bedrock(gdf)
    return gdf


def classify_parcels(
    listings_gdf: gpd.GeoDataFrame,
    bedrock_gdf: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """Assign a bedrock_class to each parcel by point-in-polygon lookup.

    Uses the parcel *point* (not buffered footprint), since Ohio bedrock
    map units are large enough that the point is representative and it's
    far cheaper than an area-weighted join.
    """
    if listings_gdf.empty:
        out = listings_gdf.copy()
        out["bedrock_class"] = []
        out["bedrock_unit_code"] = []
        out["bedrock_unit_name"] = []
        return out

    pts = listings_gdf.to_crs(config.WORKING_CRS).reset_index(drop=True).copy()
    pts["__pid"] = pts.index
    bed = bedrock_gdf.to_crs(config.WORKING_CRS)[
        ["unit_code", "unit_name", "bedrock_class", "geometry"]
    ]
    joined = gpd.sjoin(
        pts[["__pid", "geometry"]], bed, how="left", predicate="within"
    )
    joined = joined.drop_duplicates(subset="__pid", keep="first").set_index("__pid")

    out = listings_gdf.copy().reset_index(drop=True)
    out["bedrock_class"] = (
        joined["bedrock_class"].reindex(range(len(out))).fillna("low").to_numpy()
    )
    out["bedrock_unit_code"] = (
        joined["unit_code"].reindex(range(len(out))).fillna("").to_numpy()
    )
    out["bedrock_unit_name"] = (
        joined["unit_name"].reindex(range(len(out))).fillna("").to_numpy()
    )
    return out
