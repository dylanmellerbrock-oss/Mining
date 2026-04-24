"""Minimal paginated ArcGIS REST FeatureServer query client.

Every public Ohio geology / rail dataset we care about is hosted on an
ArcGIS REST feature service. This module issues GeoJSON-format queries,
handles pagination (resultOffset / resultRecordCount), and returns a
GeoDataFrame in WGS84 — exactly what the rest of the pipeline already
expects.
"""

from __future__ import annotations

import io
import json
import logging
from typing import Iterable

import geopandas as gpd
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from . import config

log = logging.getLogger(__name__)


# Ohio statewide bounding box (WGS84: west, south, east, north). Use this
# to clip statewide or national services (NTAD rail, etc.) to Ohio.
OHIO_BBOX: tuple[float, float, float, float] = (-84.82, 38.40, -80.52, 42.33)


def is_arcgis_url(url: str) -> bool:
    """True when the URL looks like an ArcGIS REST feature/map layer."""
    if not url:
        return False
    return ("/FeatureServer/" in url) or ("/MapServer/" in url)


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=2, min=2, max=16))
def _get(url: str, params: dict, timeout: int) -> dict:
    headers = {"User-Agent": config.USER_AGENT}
    r = requests.get(url, params=params, headers=headers, timeout=timeout)
    r.raise_for_status()
    try:
        return r.json()
    except ValueError as exc:
        raise RuntimeError(f"ArcGIS response was not JSON: {r.text[:200]}") from exc


def query_feature_layer(
    layer_url: str,
    where: str = "1=1",
    out_fields: str = "*",
    bbox: tuple[float, float, float, float] | None = None,
    page_size: int = 1000,
    timeout: int = 120,
    max_pages: int = 200,
) -> gpd.GeoDataFrame:
    """Page through an ArcGIS REST feature layer and return a GeoDataFrame.

    Parameters
    ----------
    layer_url : URL of the feature layer (ends in `/FeatureServer/<id>`).
    where     : SQL filter (default `1=1` returns everything).
    out_fields: Comma-separated field list (default `*`).
    bbox      : Optional WGS84 envelope (west, south, east, north) to clip
                the query on the server. Use `OHIO_BBOX` for national
                services.
    page_size : Rows per request (service may cap this below the ask).
    max_pages : Hard cap to avoid runaway requests.
    """
    base = {
        "where": where,
        "outFields": out_fields,
        "outSR": "4326",
        "returnGeometry": "true",
        "f": "geojson",
    }
    if bbox is not None:
        west, south, east, north = bbox
        base.update(
            {
                "geometry": f"{west},{south},{east},{north}",
                "geometryType": "esriGeometryEnvelope",
                "inSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
            }
        )

    query_url = layer_url.rstrip("/") + "/query"

    features: list[dict] = []
    offset = 0
    for _ in range(max_pages):
        params = {**base, "resultOffset": offset, "resultRecordCount": page_size}
        payload = _get(query_url, params=params, timeout=timeout)

        if isinstance(payload, dict) and payload.get("error"):
            raise RuntimeError(f"ArcGIS error: {payload['error']}")

        page = payload.get("features", []) or []
        features.extend(page)

        more = payload.get("exceededTransferLimit") or (
            isinstance(payload.get("properties"), dict)
            and payload["properties"].get("exceededTransferLimit")
        )
        if not more and len(page) < page_size:
            break
        if not page:
            break
        offset += len(page)
    else:
        log.warning(
            "Hit max_pages=%d at offset=%d; truncating results", max_pages, offset
        )

    if not features:
        return gpd.GeoDataFrame(geometry=[], crs=config.WGS84)

    geojson = {"type": "FeatureCollection", "features": features}
    gdf = gpd.read_file(io.StringIO(json.dumps(geojson)))
    if gdf.crs is None:
        gdf = gdf.set_crs(config.WGS84)
    log.info("Fetched %d features from %s", len(gdf), layer_url)
    return gdf


def save_gpkg(gdf: gpd.GeoDataFrame, path, layer: str = "layer") -> None:
    """Write a GeoDataFrame to GeoPackage, creating parent dirs as needed."""
    from pathlib import Path

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(out, driver="GPKG", layer=layer)


def fields_of(layer_url: str, timeout: int = 30) -> Iterable[str]:
    """Return the field names advertised by a feature layer (for sanity
    checks / field-name discovery)."""
    headers = {"User-Agent": config.USER_AGENT}
    r = requests.get(layer_url, params={"f": "pjson"}, headers=headers, timeout=timeout)
    r.raise_for_status()
    meta = r.json()
    return [f["name"] for f in meta.get("fields", [])]
