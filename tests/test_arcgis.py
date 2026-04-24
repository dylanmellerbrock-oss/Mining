from unittest.mock import patch

import pytest

from quarry_screen import arcgis


def test_is_arcgis_url():
    assert arcgis.is_arcgis_url(
        "https://gis.ohiodnr.gov/arcgis/rest/services/X/FeatureServer/3"
    )
    assert arcgis.is_arcgis_url(
        "https://example.com/arcgis/rest/services/Y/MapServer/0"
    )
    assert not arcgis.is_arcgis_url("https://example.com/data.zip")
    assert not arcgis.is_arcgis_url("/tmp/local.gpkg")
    assert not arcgis.is_arcgis_url("")


def _feature(x: float, y: float, **attrs):
    return {
        "type": "Feature",
        "properties": attrs,
        "geometry": {"type": "Point", "coordinates": [x, y]},
    }


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_query_feature_layer_paginates_until_short_page():
    pages = [
        {
            "type": "FeatureCollection",
            "features": [_feature(i, 0, name=f"p{i}") for i in range(1000)],
            "exceededTransferLimit": True,
        },
        {
            "type": "FeatureCollection",
            "features": [_feature(i, 0, name=f"p{i}") for i in range(1000, 1500)],
        },
    ]
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append(params)
        return _FakeResponse(pages[len(calls) - 1])

    with patch("quarry_screen.arcgis.requests.get", side_effect=fake_get):
        gdf = arcgis.query_feature_layer(
            "https://example.com/arcgis/rest/services/Foo/FeatureServer/0",
            page_size=1000,
        )

    assert len(gdf) == 1500
    assert len(calls) == 2
    assert calls[0]["resultOffset"] == 0
    assert calls[1]["resultOffset"] == 1000
    # Request asks for GeoJSON in WGS84
    assert calls[0]["f"] == "geojson"
    assert calls[0]["outSR"] == "4326"


def test_query_feature_layer_passes_bbox_and_where():
    payload = {"type": "FeatureCollection", "features": [_feature(0, 0, id=1)]}
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append(params)
        return _FakeResponse(payload)

    with patch("quarry_screen.arcgis.requests.get", side_effect=fake_get):
        gdf = arcgis.query_feature_layer(
            "https://example.com/arcgis/rest/services/Foo/FeatureServer/0",
            where="STATEAB='OH'",
            bbox=(-84.82, 38.40, -80.52, 42.33),
        )

    assert len(gdf) == 1
    assert calls[0]["where"] == "STATEAB='OH'"
    assert calls[0]["geometry"] == "-84.82,38.4,-80.52,42.33"
    assert calls[0]["geometryType"] == "esriGeometryEnvelope"
    assert calls[0]["spatialRel"] == "esriSpatialRelIntersects"


def test_query_feature_layer_raises_on_api_error():
    payload = {"error": {"code": 400, "message": "nope"}}
    with patch(
        "quarry_screen.arcgis.requests.get",
        side_effect=lambda *a, **kw: _FakeResponse(payload),
    ):
        with pytest.raises(RuntimeError, match="ArcGIS error"):
            arcgis.query_feature_layer(
                "https://example.com/arcgis/rest/services/Foo/FeatureServer/0"
            )


def test_query_feature_layer_handles_empty_result():
    payload = {"type": "FeatureCollection", "features": []}
    with patch(
        "quarry_screen.arcgis.requests.get",
        side_effect=lambda *a, **kw: _FakeResponse(payload),
    ):
        gdf = arcgis.query_feature_layer(
            "https://example.com/arcgis/rest/services/Foo/FeatureServer/0"
        )
    assert len(gdf) == 0
    assert gdf.crs.to_string() == "EPSG:4326"


def test_ohio_bbox_shape():
    w, s, e, n = arcgis.OHIO_BBOX
    assert w < e
    assert s < n
    assert -85 < w < -84
    assert 42 < n < 43
