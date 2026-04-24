"""Synthetic demo data — illustrative parcels, surficial geology, bedrock,
and rail near Westerville, OH.

Imported by both `scripts/build_demo.py` and the Streamlit UI so the two
share a single source of truth. The data is NOT real — anything flagged
here is purely illustrative of what the pipeline produces.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, Polygon

from . import bedrock as bedrock_mod
from . import config


def listings() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"title": "Alum Creek tract (demo)", "url": "https://example.com/alum",
             "price": 650_000, "acres": 55, "lat": 40.210, "lon": -82.980,
             "county": "Delaware", "city": "Galena"},
            {"title": "Big Walnut bottomland (demo)", "url": "https://example.com/bigwalnut",
             "price": 420_000, "acres": 32, "lat": 40.180, "lon": -82.870,
             "county": "Delaware", "city": "Sunbury"},
            {"title": "Scioto outwash parcel (demo)", "url": "https://example.com/scioto",
             "price": 900_000, "acres": 85, "lat": 40.080, "lon": -83.120,
             "county": "Franklin", "city": "Dublin"},
            {"title": "Till upland (demo)", "url": "https://example.com/till",
             "price": 280_000, "acres": 40, "lat": 40.260, "lon": -82.700,
             "county": "Licking", "city": "Johnstown"},
            {"title": "Hoover reservoir edge (demo)", "url": "https://example.com/hoover",
             "price": 550_000, "acres": 22, "lat": 40.150, "lon": -82.890,
             "county": "Delaware", "city": "Westerville"},
            {"title": "South of town (demo)", "url": "https://example.com/south",
             "price": 310_000, "acres": 48, "lat": 40.030, "lon": -82.930,
             "county": "Franklin", "city": "Gahanna"},
            {"title": "Far east (demo)", "url": "https://example.com/east",
             "price": 190_000, "acres": 70, "lat": 40.180, "lon": -82.500,
             "county": "Licking", "city": "Newark"},
        ]
    )


def surficial_geology() -> gpd.GeoDataFrame:
    outwash = Polygon([(-83.20, 40.06), (-82.92, 40.06), (-82.92, 40.14), (-83.20, 40.14)])
    alum_alluvium = Polygon([(-83.00, 40.17), (-82.94, 40.17), (-82.94, 40.26), (-83.00, 40.26)])
    big_walnut_terrace = Polygon([(-82.92, 40.15), (-82.83, 40.15), (-82.83, 40.22), (-82.92, 40.22)])
    hoover_kame = Polygon([(-82.91, 40.14), (-82.86, 40.14), (-82.86, 40.17), (-82.91, 40.17)])
    till_plain = Polygon([(-82.80, 40.20), (-82.55, 40.20), (-82.55, 40.32), (-82.80, 40.32)])
    lake_clay = Polygon([(-82.98, 39.98), (-82.86, 39.98), (-82.86, 40.06), (-82.98, 40.06)])
    return gpd.GeoDataFrame(
        {
            "unit_name": [
                "Scioto River outwash",
                "Alum Creek alluvium",
                "Big Walnut terrace",
                "Kame complex (Hoover area)",
                "Ground moraine till",
                "Lacustrine clay",
            ],
            "favorability": ["high", "high", "medium", "high", "low", "low"],
            "geometry": [
                outwash, alum_alluvium, big_walnut_terrace,
                hoover_kame, till_plain, lake_clay,
            ],
        },
        crs=config.WGS84,
    )


def bedrock_geology() -> gpd.GeoDataFrame:
    columbus = Polygon([(-83.20, 40.00), (-82.85, 40.00), (-82.85, 40.20), (-83.20, 40.20)])
    delaware = Polygon([(-82.85, 40.10), (-82.70, 40.10), (-82.70, 40.30), (-82.85, 40.30)])
    ohio_shale = Polygon([(-82.70, 40.10), (-82.45, 40.10), (-82.45, 40.35), (-82.70, 40.35)])
    codes = ["Dc", "Dd", "Ods"]
    names = ["Columbus Limestone", "Delaware Limestone", "Ohio Shale"]
    polys = [columbus, delaware, ohio_shale]
    classes = [bedrock_mod.classify_bedrock(c, n) for c, n in zip(codes, names)]
    return gpd.GeoDataFrame(
        {
            "unit_code": codes,
            "unit_name": names,
            "bedrock_class": classes,
            "geometry": polys,
        },
        crs=config.WGS84,
    )


def rail_network() -> gpd.GeoDataFrame:
    # Rough illustrative rail corridors through central Ohio.
    columbus_east = LineString([(-83.15, 40.00), (-82.50, 40.00)])
    olentangy_north = LineString([(-83.05, 39.95), (-83.00, 40.30)])
    newark_spur = LineString([(-82.70, 40.10), (-82.40, 40.05)])
    return gpd.GeoDataFrame(
        {"geometry": [columbus_east, olentangy_north, newark_spur]},
        crs=config.WGS84,
    )
