"""Generate a demo map with synthetic Westerville-area data.

Produces `docs/demo_map.html` so non-technical reviewers can see what the
real screening output looks like without installing anything. The demo
data is illustrative, not real — do not use it for decisions.

Run: python scripts/build_demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from quarry_screen import analysis, bedrock, config, demo, mapview

OUT = REPO_ROOT / "docs" / "demo_map.html"


def main() -> None:
    listings = analysis.filter_by_distance(demo.listings(), radius_mi=config.DEFAULT_RADIUS_MI)
    gdf = analysis.listings_to_gdf(listings)

    geo = demo.surficial_geology()
    gdf = analysis.overlay_and_volume(
        gdf, geo,
        thickness_ft=config.DEFAULT_THICKNESS_FT,
        recovery=config.DEFAULT_RECOVERY,
    )

    gdf = bedrock.classify_parcels(gdf, demo.bedrock_geology())
    gdf = analysis.add_rail_distance(gdf, demo.rail_network())
    gdf = analysis.score(gdf)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    mapview.render(gdf, geo, OUT, radius_mi=config.DEFAULT_RADIUS_MI)
    print(f"Wrote {OUT}")
    cols = ["title", "acres", "price", "distance_mi", "tons_est", "bedrock_class", "rail_dist_mi", "score"]
    print(gdf[cols].to_string(index=False))


if __name__ == "__main__":
    main()
