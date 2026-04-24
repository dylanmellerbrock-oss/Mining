"""Ohio rail network loader and per-parcel nearest-rail distance."""

from __future__ import annotations

import logging
import shutil
import tempfile
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from . import config

log = logging.getLogger(__name__)


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=2, min=2, max=16))
def _download(url: str, dest: Path) -> None:
    log.info("Downloading %s", url)
    headers = {"User-Agent": config.USER_AGENT}
    with requests.get(url, headers=headers, stream=True, timeout=120) as r:
        r.raise_for_status()
        with dest.open("wb") as f:
            shutil.copyfileobj(r.raw, f)


def fetch_rail(url: str | None = None, refresh: bool = False) -> Path:
    """Download and cache the Ohio rail network as GeoPackage."""
    url = url or config.OHIO_RAIL_URL
    if not url:
        raise RuntimeError(
            "No rail source configured. Set OHIO_RAIL_URL or pass --source "
            "to a shapefile/GeoPackage URL or local path."
        )

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = config.RAIL_CACHE
    if out.exists() and not refresh:
        log.info("Using cached rail network at %s", out)
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

        if gdf.crs is None:
            log.warning("Rail layer has no CRS; assuming WGS84")
            gdf = gdf.set_crs(config.WGS84)
        gdf = gdf[["geometry"]].copy()
        gdf.to_file(out, driver="GPKG")
        log.info("Wrote %s (%d features)", out, len(gdf))
    return out


def load_rail(path: Path | None = None) -> gpd.GeoDataFrame:
    """Load cached rail network."""
    path = path or config.RAIL_CACHE
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run `quarry-screen fetch-rail` first."
        )
    return gpd.read_file(path)


def compute_rail_distance_mi(
    listings_gdf: gpd.GeoDataFrame,
    rail_gdf: gpd.GeoDataFrame,
) -> pd.Series:
    """Distance in statute miles from each parcel point to the nearest rail."""
    if listings_gdf.empty:
        return pd.Series([], dtype=float)
    if rail_gdf.empty:
        return pd.Series([float("nan")] * len(listings_gdf), index=listings_gdf.index)

    pts = listings_gdf.to_crs(config.WORKING_CRS).reset_index(drop=True).copy()
    pts["__pid"] = pts.index
    rails = rail_gdf.to_crs(config.WORKING_CRS)[["geometry"]]

    near = gpd.sjoin_nearest(
        pts[["__pid", "geometry"]], rails, distance_col="__dist_m"
    )
    # A parcel may tie with multiple rail segments; keep the minimum.
    nearest = near.groupby("__pid")["__dist_m"].min()
    dist_m = nearest.reindex(range(len(pts))).to_numpy()
    return pd.Series(dist_m * config.MI_PER_M, index=listings_gdf.index)


def rail_score(distance_mi: float) -> float:
    """Map a nearest-rail distance to a 0..1 proximity score."""
    if distance_mi is None or distance_mi != distance_mi:  # NaN
        return 0.0
    if distance_mi <= config.RAIL_FRONTAGE_MI:
        return 1.0
    if distance_mi <= config.RAIL_NEAR_MI:
        span = config.RAIL_NEAR_MI - config.RAIL_FRONTAGE_MI
        return 1.0 - 0.5 * (distance_mi - config.RAIL_FRONTAGE_MI) / span
    if distance_mi <= config.RAIL_FAR_MI:
        span = config.RAIL_FAR_MI - config.RAIL_NEAR_MI
        return 0.5 - 0.4 * (distance_mi - config.RAIL_NEAR_MI) / span
    return 0.0
