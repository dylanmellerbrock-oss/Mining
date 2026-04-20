"""Folium map rendering for quarry-screen."""

from __future__ import annotations

from pathlib import Path

import folium
import geopandas as gpd

from . import config


def _popup_html(row) -> str:
    price = f"${row['price']:,.0f}" if row.get("price") and row["price"] == row["price"] else "—"
    acres = f"{row['acres']:.1f}" if row.get("acres") and row["acres"] == row["acres"] else "—"
    tons = f"{row['tons_est']:,.0f}" if row.get("tons_est") else "—"
    yd3 = f"{row['volume_yd3']:,.0f}" if row.get("volume_yd3") else "—"
    ppt = (
        f"${row['price_per_ton']:.2f}"
        if row.get("price_per_ton") and row["price_per_ton"] == row["price_per_ton"]
        else "—"
    )
    score = f"{row['score']:.2f}" if row.get("score") is not None else "—"
    title = row.get("title") or "(listing)"
    url = row.get("url") or "#"
    dist = f"{row['distance_mi']:.1f} mi" if row.get("distance_mi") is not None else "—"
    return (
        f"<b><a href='{url}' target='_blank'>{title}</a></b><br>"
        f"Score: {score}<br>"
        f"Distance: {dist}<br>"
        f"Acres: {acres}<br>"
        f"Price: {price}<br>"
        f"Est. volume: {yd3} yd³ ({tons} tons)<br>"
        f"$/ton: {ppt}"
    )


def _marker_color(score: float) -> str:
    if score is None or score != score:  # NaN
        return "gray"
    if score >= 0.66:
        return "green"
    if score >= 0.33:
        return "orange"
    return "red"


def render(
    listings_gdf: gpd.GeoDataFrame,
    geology_gdf: gpd.GeoDataFrame,
    out_path: Path,
    radius_mi: float = config.DEFAULT_RADIUS_MI,
) -> Path:
    """Write an interactive map of listings over the favorability geology."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    m = folium.Map(
        location=[config.WESTERVILLE_LAT, config.WESTERVILLE_LON],
        zoom_start=9,
        tiles="OpenStreetMap",
    )

    # Westerville anchor + search radius.
    folium.Marker(
        location=[config.WESTERVILLE_LAT, config.WESTERVILLE_LON],
        tooltip="Westerville, OH",
        icon=folium.Icon(color="blue", icon="home"),
    ).add_to(m)
    folium.Circle(
        location=[config.WESTERVILLE_LAT, config.WESTERVILLE_LON],
        radius=radius_mi * 1609.344,
        color="#1f77b4",
        weight=2,
        fill=False,
        tooltip=f"{radius_mi:.0f} mi screening radius",
    ).add_to(m)

    # Geology layers by favorability.
    geo_wgs = geology_gdf.to_crs(config.WGS84)
    for label in ("high", "medium", "low"):
        subset = geo_wgs[geo_wgs["favorability"] == label]
        if subset.empty:
            continue
        color = config.FAVORABILITY_COLOR[label]
        folium.GeoJson(
            subset.__geo_interface__,
            name=f"Geology: {label} favorability",
            style_function=lambda _f, c=color: {
                "fillColor": c,
                "color": c,
                "weight": 0,
                "fillOpacity": 0.35 if _f["properties"].get("favorability") != "low" else 0.12,
            },
            tooltip=folium.GeoJsonTooltip(fields=["unit_name", "favorability"]),
            show=(label != "low"),
        ).add_to(m)

    # Listings.
    listings_layer = folium.FeatureGroup(name="Listings", show=True)
    for _, row in listings_gdf.iterrows():
        if row.get("lat") is None or row.get("lon") is None:
            continue
        folium.CircleMarker(
            location=[row["lat"], row["lon"]],
            radius=7,
            color=_marker_color(row.get("score")),
            fill=True,
            fill_opacity=0.85,
            popup=folium.Popup(_popup_html(row), max_width=320),
        ).add_to(listings_layer)
    listings_layer.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    m.save(str(out_path))
    return out_path
