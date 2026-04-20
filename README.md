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
quarry-screen fetch-geology                   # cache ODGS data (once)
quarry-screen scrape-listings --radius-mi 40 --min-acres 20 -o data/listings.csv
quarry-screen screen --listings data/listings.csv -o output/
```

Open `output/map.html` for the interactive map, and `output/ranked.csv` for
the sorted shortlist.

Or do it all in one go:

```
quarry-screen run-all --radius-mi 40 --min-acres 20 --thickness-ft 20 --recovery 0.7
```

## How it works

1. **Geology** — downloads ODGS glacial/surficial polygons, classifies each
   unit as High / Medium / Low favorability based on lithology (outwash,
   kames, eskers, and alluvium are High; tills are Low).
2. **Listings** — scrapes LandWatch for Ohio parcels; pulls price, acres,
   lat/lon, URL. Rate-limited; obeys robots.txt.
3. **Proximity** — haversine-filters listings within a user radius of
   Westerville (40.1261°N, −82.9291°W).
4. **Overlay** — buffers each parcel point by its acreage-equivalent radius,
   intersects with the favorability polygons, weights High=1.0 / Med=0.5.
5. **Volume** — `favorable_area × thickness × recovery`, reported in cubic
   yards and short tons.
6. **Score** — composite of tons, distance, and price-per-ton. Writes
   Folium HTML and a ranked CSV.

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

Set `ODGS_GLACIAL_URL` as an env var to override the geology source.
