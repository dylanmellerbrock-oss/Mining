"""Ohio Geological Survey glacial/surficial geology loader and classifier."""

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


def classify_unit(name: str | None) -> str:
    """Map an ODGS unit name/description to 'high' | 'medium' | 'low'."""
    if not name:
        return "low"
    haystack = name.lower()
    for keyword, label in config.FAVORABILITY_RULES:
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


def fetch_geology(url: str | None = None, refresh: bool = False) -> Path:
    """Download and cache the ODGS glacial geology layer as GeoPackage.

    Accepts either a remote URL (zipped shapefile or direct .gpkg) or a
    local filesystem path. Returns the path to the cached .gpkg.
    """
    url = url or config.ODGS_GLACIAL_URL
    if not url:
        raise RuntimeError(
            "No ODGS source configured. Set ODGS_GLACIAL_URL env var "
            "or pass --source to a shapefile/GeoPackage URL or local path."
        )

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = config.GEOLOGY_CACHE
    if out.exists() and not refresh:
        log.info("Using cached geology at %s", out)
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

        gdf = _prepare_favorability(gdf)
        gdf.to_file(out, driver="GPKG")
        log.info("Wrote %s (%d polygons)", out, len(gdf))
    return out


def _prepare_favorability(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Attach a 'favorability' column based on unit-name heuristics."""
    # ODGS fields vary by release; probe common candidates.
    name_col = None
    for cand in ("UNIT_NAME", "UNIT", "DESCRIPTIO", "DESCRIPTION", "LITHOLOGY", "NAME", "MAP_UNIT"):
        if cand in gdf.columns:
            name_col = cand
            break
    if name_col is None:
        # Fall back to the first string-ish column.
        str_cols = [c for c in gdf.columns if gdf[c].dtype == object and c != "geometry"]
        if not str_cols:
            raise RuntimeError("Could not find a unit-name column in ODGS data")
        name_col = str_cols[0]

    gdf = gdf.rename(columns={name_col: "unit_name"})
    gdf["favorability"] = gdf["unit_name"].map(classify_unit)
    if gdf.crs is None:
        log.warning("Geology layer has no CRS; assuming WGS84")
        gdf = gdf.set_crs(config.WGS84)
    return gdf[["unit_name", "favorability", "geometry"]]


def load_geology(path: Path | None = None) -> gpd.GeoDataFrame:
    """Load cached geology with a favorability column."""
    path = path or config.GEOLOGY_CACHE
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run `quarry-screen fetch-geology` first."
        )
    gdf = gpd.read_file(path)
    if "favorability" not in gdf.columns:
        gdf = _prepare_favorability(gdf)
    return gdf
