import logging
import os

import geopandas as gpd
import pandas as pd

logger = logging.getLogger(__name__)

# NYC county FIPS codes within New York State (FIPS 36)
NYC_COUNTIES = ["005", "047", "061", "081", "085"]


def download_tract_geojson(cache_path: str) -> gpd.GeoDataFrame:
    """Download NYC 2020 census tract boundaries via pygris (Census TIGER/Line).
    Caches the result locally as GeoJSON. Returns GeoDataFrame in EPSG:4326."""
    if os.path.exists(cache_path):
        logger.info("Loading tract boundaries from cache: %s", cache_path)
        return gpd.read_file(cache_path)

    from pygris import tracts

    logger.info("Downloading NYC 2020 census tract boundaries from Census TIGER ...")
    gdf = tracts(state="NY", county=NYC_COUNTIES, year=2020, cb=True)
    gdf = gdf.to_crs("EPSG:4326")
    gdf["tract_geoid"] = gdf["GEOID"].astype(str).str.strip()

    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    gdf[["tract_geoid", "geometry"]].to_file(cache_path, driver="GeoJSON")
    logger.info("Cached %d tracts to %s", len(gdf), cache_path)

    return gdf[["tract_geoid", "geometry"]]


def assign_tract_geoid(df: pd.DataFrame, tracts_gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    """Point-in-polygon spatial join: appends tract_geoid to df rows with lat/lon.
    Rows without coordinates or outside all tract boundaries get NULL tract_geoid."""
    has_coords = df["latitude"].notna() & df["longitude"].notna()
    logger.info("%d of %d rows have coordinates", has_coords.sum(), len(df))

    points_gdf = gpd.GeoDataFrame(
        df[has_coords].copy(),
        geometry=gpd.points_from_xy(df.loc[has_coords, "longitude"], df.loc[has_coords, "latitude"]),
        crs="EPSG:4326",
    )

    joined = gpd.sjoin(points_gdf, tracts_gdf[["tract_geoid", "geometry"]], how="left", predicate="within")
    # sjoin may produce duplicates if a point falls on a shared boundary; keep first
    joined = joined[~joined.index.duplicated(keep="first")]

    df = df.copy()
    df["tract_geoid"] = None
    df.loc[has_coords, "tract_geoid"] = joined["tract_geoid"].values

    matched = df["tract_geoid"].notna().sum()
    logger.info("Assigned tract_geoid to %d rows (%.1f%%)", matched, 100 * matched / len(df))
    return df.drop(columns=["geometry"], errors="ignore")
