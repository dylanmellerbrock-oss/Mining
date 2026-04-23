"""Generate a demo map with synthetic Westerville-area data.

Produces `docs/demo_map.html` so non-technical reviewers can see what the
real screening output looks like without installing anything. The demo
data is illustrative, not real — do not use it for decisions.

Run: python scripts/build_demo.py
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon

from quarry_screen import analysis, config, mapview

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT = REPO_ROOT / "docs" / "demo_map.html"


def synthetic_listings() -> pd.DataFrame:
    # Mix of parcels at various distances, acreages, and prices.
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


def synthetic_geology() -> gpd.GeoDataFrame:
    # Rough, illustrative polygons. Real ODGS layers are much more detailed.
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


def main() -> None:
    listings = synthetic_listings()
    listings = analysis.filter_by_distance(listings, radius_mi=config.DEFAULT_RADIUS_MI)
    gdf = analysis.listings_to_gdf(listings)
    geo = synthetic_geology()
    gdf = analysis.overlay_and_volume(
        gdf, geo,
        thickness_ft=config.DEFAULT_THICKNESS_FT,
        recovery=config.DEFAULT_RECOVERY,
    )
    gdf = analysis.score(gdf)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    mapview.render(gdf, geo, OUT, radius_mi=config.DEFAULT_RADIUS_MI)
    print(f"Wrote {OUT}")
    cols = ["title", "acres", "price", "distance_mi", "tons_est", "score"]
    print(gdf[cols].to_string(index=False))


if __name__ == "__main__":
    main()
