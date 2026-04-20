"""Proximity filter, spatial overlay, volume estimation, and scoring."""

from __future__ import annotations

import math
from typing import Iterable

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from . import config


def haversine_mi(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in statute miles."""
    r_mi = 3958.7613
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * r_mi * math.asin(math.sqrt(a))


def filter_by_distance(
    df: pd.DataFrame,
    center: tuple[float, float] = (config.WESTERVILLE_LAT, config.WESTERVILLE_LON),
    radius_mi: float = config.DEFAULT_RADIUS_MI,
) -> pd.DataFrame:
    """Drop listings outside `radius_mi` of `center`."""
    if df.empty:
        return df
    lat0, lon0 = center
    dist = df.apply(lambda r: haversine_mi(lat0, lon0, r["lat"], r["lon"]), axis=1)
    out = df.assign(distance_mi=dist)
    return out[out["distance_mi"] <= radius_mi].reset_index(drop=True)


def acres_to_radius_m(acres: float) -> float:
    """Radius of a circle with the given acreage, in meters."""
    return math.sqrt((acres * config.SQ_M_PER_ACRE) / math.pi)


def listings_to_gdf(df: pd.DataFrame) -> gpd.GeoDataFrame:
    geom = [Point(xy) for xy in zip(df["lon"], df["lat"])]
    return gpd.GeoDataFrame(df.copy(), geometry=geom, crs=config.WGS84)


def overlay_and_volume(
    listings: gpd.GeoDataFrame,
    geology: gpd.GeoDataFrame,
    thickness_ft: float = config.DEFAULT_THICKNESS_FT,
    recovery: float = config.DEFAULT_RECOVERY,
) -> gpd.GeoDataFrame:
    """Buffer listings into circles, intersect with favorability polygons,
    and compute a weighted recoverable-volume estimate per parcel.

    Adds columns: favorable_area_m2, volume_yd3, tons_est, price_per_ton.
    """
    if listings.empty:
        return listings.assign(
            favorable_area_m2=[], volume_yd3=[], tons_est=[], price_per_ton=[]
        )

    parcels = listings.to_crs(config.WORKING_CRS).copy()
    parcels["buffer_radius_m"] = parcels["acres"].fillna(0).map(acres_to_radius_m)
    parcels["geometry"] = parcels.geometry.buffer(parcels["buffer_radius_m"])

    geo = geology.to_crs(config.WORKING_CRS)[["favorability", "geometry"]].copy()
    geo = geo[geo["favorability"].isin(config.FAVORABILITY_WEIGHT)]

    # Identifier that survives overlay.
    parcels = parcels.reset_index(drop=True)
    parcels["__pid"] = parcels.index

    inter = gpd.overlay(
        parcels[["__pid", "geometry"]],
        geo,
        how="intersection",
        keep_geom_type=True,
    )
    if inter.empty:
        parcels["favorable_area_m2"] = 0.0
    else:
        inter["weight"] = inter["favorability"].map(config.FAVORABILITY_WEIGHT)
        inter["weighted_m2"] = inter.geometry.area * inter["weight"]
        area_by_pid = inter.groupby("__pid")["weighted_m2"].sum()
        parcels["favorable_area_m2"] = (
            parcels["__pid"].map(area_by_pid).fillna(0.0).astype(float)
        )

    thickness_m = thickness_ft * config.M_PER_FT
    parcels["volume_m3"] = parcels["favorable_area_m2"] * thickness_m * recovery
    parcels["volume_yd3"] = parcels["volume_m3"] * config.YD3_PER_M3
    parcels["tons_est"] = parcels["volume_yd3"] * config.TONS_PER_YD3_SANDGRAVEL
    parcels["price_per_ton"] = parcels.apply(
        lambda r: (r["price"] / r["tons_est"])
        if pd.notna(r.get("price")) and r["tons_est"] > 0
        else float("nan"),
        axis=1,
    )

    # Keep original point geometry (more useful for mapping listings).
    out = listings.copy()
    for col in ("favorable_area_m2", "volume_m3", "volume_yd3", "tons_est", "price_per_ton"):
        out[col] = parcels[col].to_numpy()
    return out


def score(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Composite score: higher = better. Normalized tons minus normalized
    distance and price-per-ton.
    """
    if gdf.empty:
        return gdf.assign(score=[])

    def _norm(series: pd.Series, higher_is_better: bool) -> pd.Series:
        s = pd.to_numeric(series, errors="coerce")
        lo, hi = s.min(skipna=True), s.max(skipna=True)
        if pd.isna(lo) or pd.isna(hi) or hi == lo:
            return pd.Series([0.5] * len(s), index=s.index)
        normed = (s - lo) / (hi - lo)
        return normed if higher_is_better else 1 - normed

    tons_n = _norm(gdf["tons_est"], higher_is_better=True).fillna(0)
    dist_n = _norm(gdf["distance_mi"], higher_is_better=False).fillna(0)
    ppt_n = _norm(gdf["price_per_ton"], higher_is_better=False).fillna(0.5)

    out = gdf.copy()
    out["score"] = 0.55 * tons_n + 0.25 * dist_n + 0.20 * ppt_n
    return out.sort_values("score", ascending=False).reset_index(drop=True)


def ranked_columns() -> Iterable[str]:
    return (
        "score",
        "title",
        "url",
        "county",
        "city",
        "acres",
        "price",
        "distance_mi",
        "favorable_area_m2",
        "volume_yd3",
        "tons_est",
        "price_per_ton",
        "lat",
        "lon",
    )
