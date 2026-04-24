"""Streamlit UI for quarry-screen.

Launches a browser dashboard that lets you adjust screening parameters,
toggle bedrock / rail layers, and see the ranked parcels + folium map
live. If real ODGS/rail caches aren't present, the "Use demo data" toggle
runs against the synthetic fixtures in `quarry_screen.demo`.

Run via: `quarry-screen ui` (wraps `streamlit run`).
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path

import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from . import analysis, bedrock, config, demo, geology, listings, mapview, rail


st.set_page_config(page_title="quarry-screen", layout="wide")


@st.cache_data(show_spinner=False)
def _load_demo_listings() -> pd.DataFrame:
    return demo.listings()


@st.cache_data(show_spinner=False)
def _load_demo_surficial_bytes() -> bytes:
    # GeoDataFrame isn't directly hashable; cache a serialized form instead
    # by routing through GeoJSON.
    return demo.surficial_geology().to_json().encode("utf-8")


def _demo_surficial():
    import geopandas as gpd
    return gpd.read_file(StringIO(_load_demo_surficial_bytes().decode("utf-8")))


def _demo_bedrock():
    import geopandas as gpd
    return gpd.read_file(StringIO(demo.bedrock_geology().to_json()))


def _demo_rail():
    import geopandas as gpd
    return gpd.read_file(StringIO(demo.rail_network().to_json()))


def _read_csv_upload(upload) -> pd.DataFrame:
    return pd.read_csv(upload)


def _fetch_all_with_progress(force: bool) -> None:
    steps = [
        ("Surficial geology (ODNR Quaternary 500K)", geology.fetch_geology),
        ("Bedrock geology (ODNR Bedrock 500K)", bedrock.fetch_bedrock),
        ("Rail network (NTAD North American Rail)", rail.fetch_rail),
    ]
    for label, fn in steps:
        with st.spinner(f"Fetching: {label}"):
            try:
                path = fn(refresh=force)
                st.success(f"{label} → {path}")
            except Exception as exc:
                st.error(f"{label} failed: {exc}")
                break


def _load_real_layers(use_bedrock: bool, use_rail: bool):
    geo = geology.load_geology() if config.GEOLOGY_CACHE.exists() else None
    bed = bedrock.load_bedrock() if (use_bedrock and config.BEDROCK_CACHE.exists()) else None
    rails = rail.load_rail() if (use_rail and config.RAIL_CACHE.exists()) else None
    return geo, bed, rails


def main() -> None:
    st.title("quarry-screen")
    st.caption(
        "Screening tool — not a reserve report. Everything flagged still "
        "needs ODGS map review, test borings, zoning, and legal diligence."
    )

    with st.sidebar:
        st.header("Data source")
        source = st.radio(
            "Input mode",
            ["Demo data", "Upload listings CSV", "Use cached data/ files"],
            index=0,
        )
        uploaded = None
        if source == "Upload listings CSV":
            uploaded = st.file_uploader(
                "Listings CSV (title, url, price, acres, lat, lon, county, city)",
                type=["csv"],
            )

        with st.expander("Fetch real GIS data (ArcGIS REST)"):
            st.caption(
                "Pulls surficial geology, bedrock geology, and rail from the "
                "ODNR / NTAD feature services configured in `config.py`. "
                "Writes to `data/*.gpkg`."
            )
            force = st.checkbox("Ignore cache and re-fetch", value=False)
            if st.button("Fetch surficial + bedrock + rail"):
                _fetch_all_with_progress(force=force)

        st.header("Screening parameters")
        radius_mi = st.slider("Radius from Westerville (mi)", 5, 100, int(config.DEFAULT_RADIUS_MI), 5)
        thickness_ft = st.slider("Assumed deposit thickness (ft)", 5, 100, int(config.DEFAULT_THICKNESS_FT), 5)
        recovery = st.slider("Recovery fraction", 0.3, 1.0, float(config.DEFAULT_RECOVERY), 0.05)

        st.header("Layers")
        use_bedrock = st.checkbox("Apply bedrock (Dc/Dd) filter", value=True)
        use_rail = st.checkbox("Apply rail-proximity score", value=True)

        run = st.button("Run screen", type="primary", use_container_width=True)

    if not run:
        st.info("Adjust parameters in the sidebar and click **Run screen**.")
        return

    # --- Load inputs -------------------------------------------------------
    if source == "Demo data":
        parcels_df = _load_demo_listings()
        geo = _demo_surficial()
        bed = _demo_bedrock() if use_bedrock else None
        rails = _demo_rail() if use_rail else None
    elif source == "Upload listings CSV":
        if uploaded is None:
            st.warning("Upload a CSV in the sidebar to continue.")
            return
        parcels_df = _read_csv_upload(uploaded)
        geo, bed, rails = _load_real_layers(use_bedrock, use_rail)
        if geo is None:
            st.error(
                f"Surficial geology cache not found at {config.GEOLOGY_CACHE}. "
                "Run `quarry-screen fetch-geology` first."
            )
            return
    else:
        if config.LISTINGS_CACHE.exists():
            parcels_df = listings.load_csv(config.LISTINGS_CACHE)
        else:
            st.error(f"No listings at {config.LISTINGS_CACHE}. Scrape or upload first.")
            return
        geo, bed, rails = _load_real_layers(use_bedrock, use_rail)
        if geo is None:
            st.error(
                f"Surficial geology cache not found at {config.GEOLOGY_CACHE}. "
                "Run `quarry-screen fetch-geology` first."
            )
            return

    # --- Run pipeline ------------------------------------------------------
    parcels_df = analysis.filter_by_distance(parcels_df, radius_mi=radius_mi)
    if parcels_df.empty:
        st.warning(f"No listings within {radius_mi} mi of Westerville.")
        return

    gdf = analysis.listings_to_gdf(parcels_df)
    gdf = analysis.overlay_and_volume(gdf, geo, thickness_ft=thickness_ft, recovery=recovery)
    if bed is not None:
        gdf = bedrock.classify_parcels(gdf, bed)
    if rails is not None:
        gdf = analysis.add_rail_distance(gdf, rails)
    gdf = analysis.score(gdf)

    # --- Summary + detail --------------------------------------------------
    top = gdf.head(5)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Parcels screened", len(gdf))
    c2.metric("Total tons (est.)", f"{gdf['tons_est'].sum():,.0f}")
    c3.metric("Top score", f"{gdf['score'].iloc[0]:.2f}")
    c4.metric("Top parcel tons", f"{top['tons_est'].iloc[0]:,.0f}")

    st.subheader("Top parcels")
    display_cols = [c for c in analysis.ranked_columns(gdf) if c in gdf.columns]
    st.dataframe(top[display_cols], use_container_width=True)

    st.subheader("Full ranking")
    st.dataframe(gdf[display_cols], use_container_width=True, height=260)

    csv_bytes = gdf[display_cols].to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download ranked.csv",
        data=csv_bytes,
        file_name="ranked.csv",
        mime="text/csv",
    )

    # --- Map --------------------------------------------------------------
    st.subheader("Map")
    out_path = Path(st.session_state.get("_ui_map_path", config.OUTPUT_DIR / "map.html"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    mapview.render(gdf, geo, out_path, radius_mi=radius_mi)
    fmap = mapview_to_folium_obj(gdf, geo, radius_mi=radius_mi)
    st_folium(fmap, height=600, use_container_width=True)


def mapview_to_folium_obj(gdf, geo, radius_mi: float):
    """Build the same Folium map the CLI renders, but return the live
    object (not a saved HTML) so Streamlit can mount it directly."""
    import folium

    m = folium.Map(
        location=[config.WESTERVILLE_LAT, config.WESTERVILLE_LON],
        zoom_start=9,
        tiles="OpenStreetMap",
    )
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

    geo_wgs = geo.to_crs(config.WGS84)
    for label in ("high", "medium", "low"):
        subset = geo_wgs[geo_wgs["favorability"] == label]
        if subset.empty:
            continue
        color = config.FAVORABILITY_COLOR[label]
        folium.GeoJson(
            subset.__geo_interface__,
            name=f"Geology: {label}",
            style_function=lambda _f, c=color: {
                "fillColor": c,
                "color": c,
                "weight": 0,
                "fillOpacity": 0.35 if _f["properties"].get("favorability") != "low" else 0.12,
            },
            tooltip=folium.GeoJsonTooltip(fields=["unit_name", "favorability"]),
            show=(label != "low"),
        ).add_to(m)

    for _, row in gdf.iterrows():
        lat = row.get("lat")
        lon = row.get("lon")
        if lat is None or lon is None:
            continue
        score = row.get("score")
        color = "green" if (score is not None and score >= 0.66) else (
            "orange" if (score is not None and score >= 0.33) else "red"
        )
        popup = mapview._popup_html(row)  # reuse the CLI popup
        folium.CircleMarker(
            location=[lat, lon],
            radius=7,
            color=color,
            fill=True,
            fill_opacity=0.85,
            popup=folium.Popup(popup, max_width=320),
        ).add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    return m


if __name__ == "__main__":
    main()
