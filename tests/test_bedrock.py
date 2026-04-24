import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, Polygon

from quarry_screen import analysis, bedrock, config


def test_dc_code_is_high():
    assert bedrock.classify_bedrock("Dc", None) == "high"
    assert bedrock.classify_bedrock("DC", None) == "high"
    assert bedrock.classify_bedrock("dc ", "some shale") == "high"


def test_dd_code_is_medium():
    assert bedrock.classify_bedrock("Dd", None) == "medium"


def test_dco_is_high():
    assert bedrock.classify_bedrock("Dco", None) == "high"


def test_shale_name_is_low():
    assert bedrock.classify_bedrock(None, "Ohio Shale") == "low"


def test_columbus_limestone_name_is_high():
    assert bedrock.classify_bedrock(None, "Columbus Limestone") == "high"


def test_generic_limestone_is_medium():
    assert bedrock.classify_bedrock(None, "Unnamed limestone unit") == "medium"


def test_unknown_defaults_low():
    assert bedrock.classify_bedrock(None, None) == "low"
    assert bedrock.classify_bedrock("", "") == "low"
    assert bedrock.classify_bedrock("Xyz", "Mystery Formation") == "low"


def _listing_gdf(lat: float, lon: float) -> gpd.GeoDataFrame:
    df = pd.DataFrame([{"lat": lat, "lon": lon, "acres": 40, "price": 400_000}])
    return analysis.listings_to_gdf(df)


def _bedrock_polygon(lat: float, lon: float, code: str, name: str) -> gpd.GeoDataFrame:
    poly = Polygon(
        [
            (lon - 0.1, lat - 0.1),
            (lon + 0.1, lat - 0.1),
            (lon + 0.1, lat + 0.1),
            (lon - 0.1, lat + 0.1),
        ]
    )
    return gpd.GeoDataFrame(
        {
            "unit_code": [code],
            "unit_name": [name],
            "bedrock_class": [bedrock.classify_bedrock(code, name)],
            "geometry": [poly],
        },
        crs=config.WGS84,
    )


def test_classify_parcels_assigns_class_by_point():
    listings = _listing_gdf(40.1261, -82.9291)
    bed = _bedrock_polygon(40.1261, -82.9291, "Dc", "Columbus Limestone")
    out = bedrock.classify_parcels(listings, bed)
    assert out.iloc[0]["bedrock_class"] == "high"
    assert out.iloc[0]["bedrock_unit_code"] == "Dc"


def test_classify_parcels_low_when_outside_any_polygon():
    listings = _listing_gdf(40.1261, -82.9291)
    # Put bedrock polygon far from the listing point.
    bed = _bedrock_polygon(41.5, -81.5, "Dc", "Columbus Limestone")
    out = bedrock.classify_parcels(listings, bed)
    assert out.iloc[0]["bedrock_class"] == "low"


def test_score_includes_bedrock_when_present():
    df = pd.DataFrame(
        [
            {"lat": 40.1261, "lon": -82.9291, "acres": 40, "price": 400_000, "title": "dc", "url": "a"},
            {"lat": 40.1261, "lon": -82.9291, "acres": 40, "price": 400_000, "title": "shale", "url": "b"},
        ]
    )
    df = analysis.filter_by_distance(df, radius_mi=40)
    gdf = analysis.listings_to_gdf(df)
    # Same surficial geology, so tons_est is identical for both.
    from quarry_screen.geology import classify_unit  # noqa: F401

    surficial = gpd.GeoDataFrame(
        {
            "unit_name": ["outwash"],
            "favorability": ["high"],
            "geometry": [
                Polygon(
                    [(-83.1, 40.0), (-82.7, 40.0), (-82.7, 40.3), (-83.1, 40.3)]
                )
            ],
        },
        crs=config.WGS84,
    )
    gdf = analysis.overlay_and_volume(gdf, surficial, thickness_ft=20, recovery=0.7)
    # Assign different bedrock classes manually.
    gdf = gdf.copy()
    gdf["bedrock_class"] = ["high", "low"]
    ranked = analysis.score(gdf)
    # The Dc parcel should outrank the shale parcel.
    assert ranked.iloc[0]["title"] == "dc"
