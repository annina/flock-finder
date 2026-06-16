#!/usr/bin/env python3

"""
create_postgis_db.py

Creates:
- PostgreSQL database
- PostGIS extension
- OSM surveillance schema
- Indexes
- Triggers
- Views

No data is inserted.

Requirements:
    pip install psycopg2-binary

Run:
    python create_postgis_db.py
"""

import sys
import os
import psycopg2
from psycopg2 import sql

from dotenv import load_dotenv
load_dotenv()



# =============================================================================
# CONFIGURATION
# =============================================================================

CONFIG = {
    # PostgreSQL admin connection
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
    "admin_db": "postgres",
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PW")

    # Database to create
    "new_database": os.getenv("DB_NAME"),
}


# =============================================================================
# SQL DEFINITIONS
# =============================================================================

EXTENSIONS_SQL = [
    "CREATE EXTENSION IF NOT EXISTS postgis;",
    "CREATE EXTENSION IF NOT EXISTS pg_trgm;",
    "CREATE EXTENSION IF NOT EXISTS btree_gin;"
]

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS osm_surveillance_elements (
    -- =========================================================================
    -- OSM Identity
    -- =========================================================================
    osm_type TEXT NOT NULL,
    osm_id BIGINT NOT NULL,

    -- =========================================================================
    -- Metadata
    -- =========================================================================
    version NUMERIC(3,1),
    generator TEXT,
    osm_timestamp TIMESTAMPTZ,

    -- =========================================================================
    -- Geometry
    -- =========================================================================
    geom geometry(Geometry, 4326),

    -- =========================================================================
    -- Raw JSON
    -- =========================================================================
    raw_element JSONB NOT NULL,
    tags JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- =========================================================================
    -- Normalized fields
    -- =========================================================================
    man_made TEXT,

    surveillance TEXT,
    surveillance_type TEXT,
    surveillance_zone TEXT,

    camera_type TEXT,
    camera_mount TEXT,
    camera_direction NUMERIC,

    direction NUMERIC,

    manufacturer TEXT,
    manufacturer_wikidata TEXT,

    operator_name TEXT,

    highway TEXT,

    -- =========================================================================
    -- Audit
    -- =========================================================================
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- =========================================================================
    -- Constraints
    -- =========================================================================
    PRIMARY KEY (osm_type, osm_id)
);
"""

INDEX_SQL = [
    # Spatial
    """
    CREATE INDEX IF NOT EXISTS idx_osm_surveillance_geom
    ON osm_surveillance_elements
    USING GIST (geom);
    """,

    # JSONB
    """
    CREATE INDEX IF NOT EXISTS idx_osm_surveillance_tags_gin
    ON osm_surveillance_elements
    USING GIN (tags);
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_osm_surveillance_raw_gin
    ON osm_surveillance_elements
    USING GIN (raw_element);
    """,

    # Attributes
    """
    CREATE INDEX IF NOT EXISTS idx_osm_surveillance_type
    ON osm_surveillance_elements (surveillance_type);
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_osm_surveillance_manufacturer
    ON osm_surveillance_elements (manufacturer);
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_osm_surveillance_operator
    ON osm_surveillance_elements (operator_name);
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_osm_surveillance_zone
    ON osm_surveillance_elements (surveillance_zone);
    """,

    """
    CREATE INDEX IF NOT EXISTS idx_osm_surveillance_camera_type
    ON osm_surveillance_elements (camera_type);
    """
]

TRIGGER_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

TRIGGER_SQL = """
DROP TRIGGER IF EXISTS trg_osm_surveillance_updated
ON osm_surveillance_elements;

CREATE TRIGGER trg_osm_surveillance_updated
BEFORE UPDATE ON osm_surveillance_elements
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();
"""

VIEW_SQL = [
    """
    CREATE OR REPLACE VIEW v_alpr_cameras AS
    SELECT *
    FROM osm_surveillance_elements
    WHERE surveillance_type ILIKE 'ALPR';
    """,

    """
    CREATE OR REPLACE VIEW v_flock_cameras AS
    SELECT *
    FROM osm_surveillance_elements
    WHERE manufacturer ILIKE 'Flock Safety';
    """
]


# =============================================================================
# HELPERS
# =============================================================================

def connect(dbname):
    """
    Create PostgreSQL connection.
    """
    return psycopg2.connect(
        host=CONFIG["host"],
        port=CONFIG["port"],
        dbname=dbname,
        user=CONFIG["user"],
        password=CONFIG["password"]
    )


def execute_statements(cursor, statements, label="SQL"):
    """
    Execute multiple SQL statements.
    """
    for stmt in statements:
        cursor.execute(stmt)

    print(f"✓ {label}")


# =============================================================================
# DATABASE CREATION
# =============================================================================

def create_database():
    """
    Create database if it does not exist.
    """

    db_name = CONFIG["new_database"]

    conn = connect(CONFIG["admin_db"])
    conn.autocommit = True

    cur = conn.cursor()

    print(f"Checking database '{db_name}'...")

    cur.execute(
        "SELECT 1 FROM pg_database WHERE datname = %s",
        (db_name,)
    )

    exists = cur.fetchone()

    if exists:
        print(f"✓ Database already exists: {db_name}")
    else:
        print(f"Creating database: {db_name}")

        cur.execute(
            sql.SQL("CREATE DATABASE {}").format(
                sql.Identifier(db_name)
            )
        )

        print(f"✓ Database created: {db_name}")

    cur.close()
    conn.close()


# =============================================================================
# SCHEMA CREATION
# =============================================================================

def create_schema():
    """
    Create PostGIS schema objects.
    """

    db_name = CONFIG["new_database"]

    conn = connect(db_name)
    conn.autocommit = True

    cur = conn.cursor()

    print("\nCreating extensions...")
    execute_statements(cur, EXTENSIONS_SQL, "Extensions created")

    print("\nCreating table...")
    cur.execute(TABLE_SQL)
    print("✓ Table created")

    print("\nCreating indexes...")
    execute_statements(cur, INDEX_SQL, "Indexes created")

    print("\nCreating trigger function...")
    cur.execute(TRIGGER_FUNCTION_SQL)
    print("✓ Trigger function created")

    print("\nCreating trigger...")
    cur.execute(TRIGGER_SQL)
    print("✓ Trigger created")

    print("\nCreating views...")
    execute_statements(cur, VIEW_SQL, "Views created")

    cur.close()
    conn.close()


# =============================================================================
# MAIN
# =============================================================================

def main():

    print("=" * 70)
    print("POSTGIS DATABASE SETUP")
    print("=" * 70)

    try:
        create_database()
        create_schema()

        print("\n" + "=" * 70)
        print("SUCCESS")
        print("=" * 70)

        print(f"""
Database ready:

    Name: {CONFIG["new_database"]}
    Host: {CONFIG["host"]}
    Port: {CONFIG["port"]}

Main table:

    osm_surveillance_elements

Views:

    v_alpr_cameras
    v_flock_cameras
""")

    except psycopg2.Error as e:
        print("\nPostgreSQL Error:")
        print(e)
        sys.exit(1)

    except Exception as e:
        print("\nUnexpected Error:")
        print(e)
        sys.exit(1)


if __name__ == "__main__":
    main()
