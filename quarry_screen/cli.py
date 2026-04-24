"""`quarry-screen` command-line interface."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click

from . import analysis, bedrock, config, geology, listings, mapview, rail


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging.")
@click.pass_context
def cli(ctx: click.Context, verbose: bool) -> None:
    """Small sand/gravel quarry site screening near Westerville, OH."""
    ctx.ensure_object(dict)
    _setup_logging(verbose)


@cli.command("fetch-geology")
@click.option("--source", default=None, help="Override ODGS URL or local path.")
@click.option("--refresh", is_flag=True, help="Ignore cache and re-download.")
def cmd_fetch_geology(source: str | None, refresh: bool) -> None:
    """Download and cache ODGS surficial/glacial geology."""
    path = geology.fetch_geology(url=source, refresh=refresh)
    click.echo(f"Geology cached at {path}")


@cli.command("fetch-bedrock")
@click.option("--source", default=None, help="Override ODGS bedrock URL or local path.")
@click.option("--refresh", is_flag=True, help="Ignore cache and re-download.")
def cmd_fetch_bedrock(source: str | None, refresh: bool) -> None:
    """Download and cache ODGS bedrock geology (Columbus/Delaware Limestone)."""
    path = bedrock.fetch_bedrock(url=source, refresh=refresh)
    click.echo(f"Bedrock cached at {path}")


@cli.command("fetch-rail")
@click.option("--source", default=None, help="Override Ohio rail URL or local path.")
@click.option("--refresh", is_flag=True, help="Ignore cache and re-download.")
def cmd_fetch_rail(source: str | None, refresh: bool) -> None:
    """Download and cache the Ohio rail network."""
    path = rail.fetch_rail(url=source, refresh=refresh)
    click.echo(f"Rail network cached at {path}")


@cli.command("scrape-listings")
@click.option("--min-acres", type=int, default=config.DEFAULT_MIN_ACRES, show_default=True)
@click.option("--max-price", type=int, default=config.DEFAULT_MAX_PRICE, show_default=True)
@click.option("--max-pages", type=int, default=config.DEFAULT_MAX_PAGES, show_default=True)
@click.option("--delay", type=float, default=config.DEFAULT_REQUEST_DELAY_S, show_default=True)
@click.option(
    "-o", "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    default=config.LISTINGS_CACHE,
    show_default=True,
)
def cmd_scrape_listings(
    min_acres: int, max_price: int, max_pages: int, delay: float, output: Path
) -> None:
    """Scrape LandWatch for Ohio listings and save to CSV."""
    df = listings.scrape_landwatch(
        min_acres=min_acres,
        max_price=max_price,
        max_pages=max_pages,
        delay_s=delay,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    listings.save_csv(df, output)
    click.echo(f"Wrote {len(df)} listings to {output}")


@cli.command("screen")
@click.option(
    "--listings", "listings_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=config.LISTINGS_CACHE,
    show_default=True,
)
@click.option(
    "--geology", "geology_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=config.GEOLOGY_CACHE,
    show_default=True,
)
@click.option(
    "--bedrock", "bedrock_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=config.BEDROCK_CACHE,
    show_default=True,
    help="Bedrock GeoPackage; skipped if the file is absent.",
)
@click.option(
    "--rail", "rail_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=config.RAIL_CACHE,
    show_default=True,
    help="Rail network GeoPackage; skipped if the file is absent.",
)
@click.option("--radius-mi", type=float, default=config.DEFAULT_RADIUS_MI, show_default=True)
@click.option("--thickness-ft", type=float, default=config.DEFAULT_THICKNESS_FT, show_default=True)
@click.option("--recovery", type=float, default=config.DEFAULT_RECOVERY, show_default=True)
@click.option(
    "-o", "--output",
    type=click.Path(file_okay=False, path_type=Path),
    default=config.OUTPUT_DIR,
    show_default=True,
)
def cmd_screen(
    listings_path: Path,
    geology_path: Path,
    bedrock_path: Path,
    rail_path: Path,
    radius_mi: float,
    thickness_ft: float,
    recovery: float,
    output: Path,
) -> None:
    """Overlay, score, and render map + ranked CSV."""
    listings_df = listings.load_csv(listings_path)
    if listings_df.empty:
        click.echo("No listings to screen.", err=True)
        sys.exit(1)

    listings_df = analysis.filter_by_distance(listings_df, radius_mi=radius_mi)
    click.echo(f"{len(listings_df)} listings within {radius_mi:g} mi of Westerville")

    geo = geology.load_geology(geology_path)
    gdf = analysis.listings_to_gdf(listings_df)
    gdf = analysis.overlay_and_volume(gdf, geo, thickness_ft=thickness_ft, recovery=recovery)

    if bedrock_path and Path(bedrock_path).exists():
        bed = bedrock.load_bedrock(bedrock_path)
        gdf = bedrock.classify_parcels(gdf, bed)
        click.echo(f"Bedrock layer: {len(bed)} polygons from {bedrock_path}")
    else:
        click.echo("Bedrock layer not found; skipping Dc/Dd filter.", err=True)

    if rail_path and Path(rail_path).exists():
        rails = rail.load_rail(rail_path)
        gdf = analysis.add_rail_distance(gdf, rails)
        click.echo(f"Rail layer: {len(rails)} features from {rail_path}")
    else:
        click.echo("Rail layer not found; skipping rail-proximity score.", err=True)

    gdf = analysis.score(gdf)

    output.mkdir(parents=True, exist_ok=True)
    ranked_csv = output / "ranked.csv"
    gdf[list(analysis.ranked_columns(gdf))].to_csv(ranked_csv, index=False)

    map_html = mapview.render(gdf, geo, output / "map.html", radius_mi=radius_mi)

    click.echo(f"Ranked CSV: {ranked_csv}")
    click.echo(f"Map: {map_html}")


@cli.command("run-all")
@click.option("--radius-mi", type=float, default=config.DEFAULT_RADIUS_MI, show_default=True)
@click.option("--min-acres", type=int, default=config.DEFAULT_MIN_ACRES, show_default=True)
@click.option("--max-price", type=int, default=config.DEFAULT_MAX_PRICE, show_default=True)
@click.option("--thickness-ft", type=float, default=config.DEFAULT_THICKNESS_FT, show_default=True)
@click.option("--recovery", type=float, default=config.DEFAULT_RECOVERY, show_default=True)
@click.pass_context
def cmd_run_all(
    ctx: click.Context,
    radius_mi: float,
    min_acres: int,
    max_price: int,
    thickness_ft: float,
    recovery: float,
) -> None:
    """Fetch geology, scrape listings, and screen in one shot."""
    ctx.invoke(cmd_fetch_geology, source=None, refresh=False)
    ctx.invoke(
        cmd_scrape_listings,
        min_acres=min_acres,
        max_price=max_price,
        max_pages=config.DEFAULT_MAX_PAGES,
        delay=config.DEFAULT_REQUEST_DELAY_S,
        output=config.LISTINGS_CACHE,
    )
    ctx.invoke(
        cmd_screen,
        listings_path=config.LISTINGS_CACHE,
        geology_path=config.GEOLOGY_CACHE,
        bedrock_path=config.BEDROCK_CACHE,
        rail_path=config.RAIL_CACHE,
        radius_mi=radius_mi,
        thickness_ft=thickness_ft,
        recovery=recovery,
        output=config.OUTPUT_DIR,
    )


if __name__ == "__main__":
    cli()
