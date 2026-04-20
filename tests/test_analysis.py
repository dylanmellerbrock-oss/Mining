import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Polygon

from quarry_screen import analysis, config


def test_haversine_zero():
    assert analysis.haversine_mi(40.0, -82.0, 40.0, -82.0) == pytest.approx(0)


def test_haversine_known():
    # Westerville -> Columbus OH (~12 mi)
    d = analysis.haversine_mi(40.1261, -82.9291, 39.9612, -82.9988)
    assert 10 < d < 14


def test_filter_by_distance_drops_far():
    df = pd.DataFrame(
        [
            {"lat": 40.1261, "lon": -82.9291, "acres": 10},  # origin
            {"lat": 39.1031, "lon": -84.5120, "acres": 10},  # Cincinnati, ~100 mi
        ]
    )
    kept = analysis.filter_by_distance(df, radius_mi=40)
    assert len(kept) == 1
    assert kept.iloc[0]["distance_mi"] == pytest.approx(0, abs=1e-6)


def test_acres_to_radius():
    # 40 acres ≈ 161,874 m² → radius ≈ 227 m
    r = analysis.acres_to_radius_m(40)
    assert 220 < r < 235


def _parcel_df(lat=40.1261, lon=-82.9291, acres=40, price=400_000):
    return pd.DataFrame(
        [{"lat": lat, "lon": lon, "acres": acres, "price": price, "title": "t", "url": "u"}]
    )


def _geology_covering(lat: float, lon: float, favorability: str = "high") -> gpd.GeoDataFrame:
    # Big square around the point in WGS84 (~0.1° ≈ 11 km), safe cover.
    poly = Polygon(
        [
            (lon - 0.1, lat - 0.1),
            (lon + 0.1, lat - 0.1),
            (lon + 0.1, lat + 0.1),
            (lon - 0.1, lat + 0.1),
        ]
    )
    return gpd.GeoDataFrame(
        {"unit_name": ["test"], "favorability": [favorability], "geometry": [poly]},
        crs=config.WGS84,
    )


def test_volume_for_40ac_20ft_07_recovery_fully_covered():
    df = _parcel_df()
    g = analysis.listings_to_gdf(df)
    geo = _geology_covering(40.1261, -82.9291, "high")
    out = analysis.overlay_and_volume(g, geo, thickness_ft=20, recovery=0.7)

    # Expected volume: 40 ac × 4046.86 m² × 20 ft × 0.3048 m/ft × 0.7 × 1.30795 yd³/m³
    expected_yd3 = 40 * 4046.8564 * 20 * 0.3048 * 0.7 * 1.30795
    assert out.iloc[0]["volume_yd3"] == pytest.approx(expected_yd3, rel=0.01)
    assert out.iloc[0]["tons_est"] == pytest.approx(expected_yd3 * 1.4, rel=0.01)


def test_volume_zero_when_geology_is_low():
    df = _parcel_df()
    g = analysis.listings_to_gdf(df)
    geo = _geology_covering(40.1261, -82.9291, "low")
    out = analysis.overlay_and_volume(g, geo, thickness_ft=20, recovery=0.7)
    assert out.iloc[0]["tons_est"] == pytest.approx(0, abs=1)


def test_medium_is_half_of_high():
    df = _parcel_df()
    g = analysis.listings_to_gdf(df)
    high = analysis.overlay_and_volume(
        g, _geology_covering(40.1261, -82.9291, "high"), thickness_ft=20, recovery=0.7
    )
    med = analysis.overlay_and_volume(
        g, _geology_covering(40.1261, -82.9291, "medium"), thickness_ft=20, recovery=0.7
    )
    assert med.iloc[0]["tons_est"] == pytest.approx(high.iloc[0]["tons_est"] * 0.5, rel=0.01)


def test_score_orders_by_tons_when_all_else_equal():
    df = pd.DataFrame(
        [
            {"lat": 40.1261, "lon": -82.9291, "acres": 10, "price": 100_000, "title": "small", "url": "a"},
            {"lat": 40.1261, "lon": -82.9291, "acres": 80, "price": 100_000, "title": "big", "url": "b"},
        ]
    )
    df = analysis.filter_by_distance(df, radius_mi=40)
    g = analysis.listings_to_gdf(df)
    geo = _geology_covering(40.1261, -82.9291, "high")
    out = analysis.overlay_and_volume(g, geo, thickness_ft=20, recovery=0.7)
    ranked = analysis.score(out)
    assert ranked.iloc[0]["title"] == "big"
