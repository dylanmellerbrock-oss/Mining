import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString, Polygon

from quarry_screen import analysis, config, rail


def test_rail_score_frontage_is_one():
    assert rail.rail_score(0.0) == pytest.approx(1.0)
    assert rail.rail_score(config.RAIL_FRONTAGE_MI) == pytest.approx(1.0)


def test_rail_score_at_near_threshold_is_half():
    assert rail.rail_score(config.RAIL_NEAR_MI) == pytest.approx(0.5, abs=1e-6)


def test_rail_score_at_far_threshold_is_tenth():
    assert rail.rail_score(config.RAIL_FAR_MI) == pytest.approx(0.1, abs=1e-6)


def test_rail_score_beyond_far_is_zero():
    assert rail.rail_score(50.0) == 0.0


def test_rail_score_nan_is_zero():
    assert rail.rail_score(float("nan")) == 0.0


def _listings(*points: tuple[float, float]) -> gpd.GeoDataFrame:
    df = pd.DataFrame(
        [{"lat": lat, "lon": lon, "acres": 40, "price": 400_000} for lat, lon in points]
    )
    return analysis.listings_to_gdf(df)


def _rail_line_through(lat: float, lon: float) -> gpd.GeoDataFrame:
    # East-west line passing through the point.
    line = LineString([(lon - 0.5, lat), (lon + 0.5, lat)])
    return gpd.GeoDataFrame({"geometry": [line]}, crs=config.WGS84)


def test_compute_rail_distance_direct_hit_is_near_zero():
    lat, lon = 40.1261, -82.9291
    pts = _listings((lat, lon))
    rails = _rail_line_through(lat, lon)
    d = rail.compute_rail_distance_mi(pts, rails)
    # Straight WGS84 line bows slightly when projected to UTM; ~0.1 mi is
    # well inside the "direct frontage" bucket.
    assert d.iloc[0] == pytest.approx(0.0, abs=0.2)


def test_compute_rail_distance_matches_expected_offset():
    lat, lon = 40.1261, -82.9291
    pts = _listings((lat + 0.05, lon))  # ~3.45 mi north
    rails = _rail_line_through(lat, lon)
    d = rail.compute_rail_distance_mi(pts, rails)
    assert 3.0 < d.iloc[0] < 4.0


def test_add_rail_distance_handles_missing_rail_layer():
    pts = _listings((40.1261, -82.9291))
    out = analysis.add_rail_distance(pts, None)
    assert "rail_dist_mi" in out.columns
    assert pd.isna(out.iloc[0]["rail_dist_mi"])


def test_score_prefers_rail_adjacent_parcel():
    a = (40.1261, -82.9291)  # on rail
    b = (40.30, -82.9291)    # ~12 mi away
    df = pd.DataFrame(
        [
            {"lat": a[0], "lon": a[1], "acres": 40, "price": 400_000, "title": "on-rail", "url": "a"},
            {"lat": b[0], "lon": b[1], "acres": 40, "price": 400_000, "title": "far-rail", "url": "b"},
        ]
    )
    df = analysis.filter_by_distance(df, radius_mi=40)
    gdf = analysis.listings_to_gdf(df)

    surficial = gpd.GeoDataFrame(
        {
            "unit_name": ["outwash"],
            "favorability": ["high"],
            "geometry": [Polygon([(-83.2, 40.0), (-82.7, 40.0), (-82.7, 40.5), (-83.2, 40.5)])],
        },
        crs=config.WGS84,
    )
    gdf = analysis.overlay_and_volume(gdf, surficial, thickness_ft=20, recovery=0.7)

    rails = _rail_line_through(a[0], a[1])
    gdf = analysis.add_rail_distance(gdf, rails)
    ranked = analysis.score(gdf)
    assert ranked.iloc[0]["title"] == "on-rail"
