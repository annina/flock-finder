#!/usr/bin/env python3

"""
import_osm_surveillance_stdin.py

Imports OSM/Overpass surveillance data into PostgreSQL/PostGIS.

The script asks for the filename via STDIN.

Requirements:
    pip install psycopg2-binary

Run:
    python import_osm_surveillance_stdin.py
"""

import json
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_batch, Json

# this program processes surveillance camera datadownloaded from open street map via overpass-turbo.eu. it enters it into a postgis database for offline use.


# =============================================================================
# CONFIG
# =============================================================================

CONFIG = {

    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
    "database": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PW"),

    "batch_size": 1000
}


# =============================================================================
# DATABASE
# =============================================================================

def connect():
    return psycopg2.connect(
        host=CONFIG["host"],
        port=CONFIG["port"],
        dbname=CONFIG["database"],
        user=CONFIG["user"],
        password=CONFIG["password"]
    )


# =============================================================================
# SQL
# =============================================================================

INSERT_SQL = """
INSERT INTO osm_surveillance_elements (
    osm_type,
    osm_id,

    version,
    generator,
    osm_timestamp,

    geom,

    raw_element,
    tags,

    man_made,

    surveillance,
    surveillance_type,
    surveillance_zone,

    camera_type,
    camera_mount,
    camera_direction,

    direction,

    manufacturer,
    manufacturer_wikidata,

    operator_name,

    highway
)
VALUES (
    %(osm_type)s,
    %(osm_id)s,

    %(version)s,
    %(generator)s,
    %(osm_timestamp)s,

    ST_SetSRID(
        ST_MakePoint(%(lon)s, %(lat)s),
        4326
    ),

    %(raw_element)s,
    %(tags)s,

    %(man_made)s,

    %(surveillance)s,
    %(surveillance_type)s,
    %(surveillance_zone)s,

    %(camera_type)s,
    %(camera_mount)s,
    %(camera_direction)s,

    %(direction)s,

    %(manufacturer)s,
    %(manufacturer_wikidata)s,

    %(operator_name)s,

    %(highway)s
)
ON CONFLICT (osm_type, osm_id)
DO UPDATE SET
    version = EXCLUDED.version,
    generator = EXCLUDED.generator,
    osm_timestamp = EXCLUDED.osm_timestamp,
    geom = EXCLUDED.geom,
    raw_element = EXCLUDED.raw_element,
    tags = EXCLUDED.tags,

    man_made = EXCLUDED.man_made,

    surveillance = EXCLUDED.surveillance,
    surveillance_type = EXCLUDED.surveillance_type,
    surveillance_zone = EXCLUDED.surveillance_zone,

    camera_type = EXCLUDED.camera_type,
    camera_mount = EXCLUDED.camera_mount,
    camera_direction = EXCLUDED.camera_direction,

    direction = EXCLUDED.direction,

    manufacturer = EXCLUDED.manufacturer,
    manufacturer_wikidata = EXCLUDED.manufacturer_wikidata,

    operator_name = EXCLUDED.operator_name,

    highway = EXCLUDED.highway,

    updated_at = now();
"""


# =============================================================================
# HELPERS
# =============================================================================

def to_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def normalize_element(element, root_json):

    tags = element.get("tags", {})

    lat = element.get("lat")
    lon = element.get("lon")

    # Skip non-point geometries
    if lat is None or lon is None:
        return None

    return {
        "osm_type": element.get("type"),
        "osm_id": element.get("id"),

        "version": root_json.get("version"),
        "generator": root_json.get("generator"),

        "osm_timestamp": (
            root_json
            .get("osm3s", {})
            .get("timestamp_osm_base")
        ),

        "lat": lat,
        "lon": lon,

        "raw_element": Json(element),
        "tags": Json(tags),

        "man_made": tags.get("man_made"),

        "surveillance": tags.get("surveillance"),
        "surveillance_type": tags.get("surveillance:type"),
        "surveillance_zone": tags.get("surveillance:zone"),

        "camera_type": tags.get("camera:type"),
        "camera_mount": tags.get("camera:mount"),
        "camera_direction": to_float(tags.get("camera:direction")),

        "direction": to_float(tags.get("direction")),

        "manufacturer": tags.get("manufacturer"),
        "manufacturer_wikidata": tags.get("manufacturer:wikidata"),

        "operator_name": tags.get("operator"),

        "highway": tags.get("highway")
    }


# =============================================================================
# IMPORT
# =============================================================================

def import_file(file_path):

    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    print(f"\nLoading file: {file_path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    elements = data.get("elements", [])

    print(f"Found {len(elements):,} elements")

    rows = []

    for element in elements:

        row = normalize_element(element, data)

        if row:
            rows.append(row)

    print(f"Prepared {len(rows):,} rows")

    if not rows:
        print("No rows to import")
        return

    conn = connect()

    try:
        cur = conn.cursor()

        print("Importing into PostgreSQL...")

        execute_batch(
            cur,
            INSERT_SQL,
            rows,
            page_size=CONFIG["batch_size"]
        )

        conn.commit()

        print(f"✓ Successfully imported {len(rows):,} rows")

        cur.close()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


# =============================================================================
# MAIN
# =============================================================================

def main():

    print("=" * 70)
    print("OSM SURVEILLANCE IMPORT")
    print("=" * 70)

    # Read filename from STDIN
    file_path = input("\nEnter path to JSON/TXT file: ").strip()

    if not file_path:
        print("No filename provided.")
        return

    try:
        import_file(file_path)

        print("\nDone.")

    except Exception as e:
        print("\nERROR:")
        print(e)


if __name__ == "__main__":
    main()
