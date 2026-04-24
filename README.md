# quarry-screen

A first-pass screening tool for small sand & gravel quarry sites near
Westerville, OH. Overlays land-for-sale listings on Ohio Geological Survey
(ODGS) surficial/glacial geology, filters by proximity, and estimates rough
recoverable volume per parcel.

**This is a screening tool, not a reserve report.** Anything it flags still
needs ODGS map review, test borings, zoning/setback checks, hydrology work,
and legal diligence before any money moves.

## Install

```
python -m venv .venv && source .venv/bin/activate
pip install -e .[dev]
```

Geopandas pulls in GDAL; on Debian/Ubuntu you may need `apt-get install gdal-bin libgdal-dev` first.

## Usage

```
quarry-screen fetch-geology                   # cache ODGS glacial data (once)
quarry-screen fetch-bedrock                   # cache ODGS bedrock (Dc/Dd filter)
quarry-screen fetch-rail                      # cache Ohio rail network
quarry-screen scrape-listings --radius-mi 40 --min-acres 20 -o data/listings.csv
quarry-screen screen --listings data/listings.csv -o output/
```

Open `output/map.html` for the interactive map, and `output/ranked.csv` for
the sorted shortlist. The `fetch-bedrock` and `fetch-rail` steps are
optional — `screen` falls back to surficial-only scoring if those caches
are missing.

Or do it all in one go:

```
quarry-screen run-all --radius-mi 40 --min-acres 20 --thickness-ft 20 --recovery 0.7
```

### Interactive dashboard

```
pip install -e .[ui]
quarry-screen ui            # opens a Streamlit dashboard on :8501
```

The dashboard lets you toggle layers, tweak radius/thickness/recovery
sliders, and see the ranked parcels + map update live. If no real ODGS
caches are present, pick **Demo data** in the sidebar to run against the
synthetic Westerville fixtures.

## How it works

1. **Surficial geology** — downloads ODGS glacial/surficial polygons,
   classifies each unit as High / Medium / Low favorability based on
   lithology (outwash, kames, eskers, and alluvium are High; tills are Low).
2. **Bedrock geology** (optional) — loads ODGS bedrock map units. Columbus
   Limestone (code `Dc`) = High, Delaware Limestone (`Dd`) / generic
   carbonates = Medium, shale / sandstone / siltstone = Low. Each parcel
   gets a `bedrock_class` by point-in-polygon lookup.
3. **Rail proximity** (optional) — loads the Ohio rail network and computes
   the distance from each parcel to the nearest rail. Direct frontage
   (≤ 0.1 mi) scores 1.0; ≤ 2 mi scores 0.5; ≤ 10 mi linearly falls to 0.1;
   beyond that scores 0.
4. **Listings** — scrapes LandWatch for Ohio parcels; pulls price, acres,
   lat/lon, URL. Rate-limited; obeys robots.txt.
5. **Proximity** — haversine-filters listings within a user radius of
   Westerville (40.1261°N, −82.9291°W).
6. **Overlay** — buffers each parcel point by its acreage-equivalent radius,
   intersects with the favorability polygons, weights High=1.0 / Med=0.5.
7. **Volume** — `favorable_area × thickness × recovery`, reported in cubic
   yards and short tons.
8. **Score** — weighted composite of surficial tons, bedrock class, rail
   proximity, distance-to-Westerville, and price-per-ton. Components that
   aren't available (e.g. no bedrock cache) drop out and the remaining
   weights rebalance automatically.

## Known limitations

- Parcels are approximated as circles around the listing point. True
  polygon geometry would come from county auditor GIS (future work).
- LandWatch scraping is fragile and ToS-sensitive; selectors may drift and
  you should review their terms before running at any volume.
- Favorability mapping is a heuristic over ODGS unit names — audit
  `quarry_screen/config.py:FAVORABILITY_RULES` before trusting output.
- Thickness is user-assumed; only ODGS isopachs (not yet integrated) give
  real numbers.

## Data provenance

- Ohio Geological Survey (Ohio DNR, Division of Geological Survey) — public
  GIS downloads for Quaternary / glacial geology.
- LandWatch public listing pages.

Set `ODGS_GLACIAL_URL`, `ODGS_BEDROCK_URL`, and `OHIO_RAIL_URL` env vars to
the current shapefile/GeoPackage downloads (or local paths) before running
the corresponding `fetch-*` command.
