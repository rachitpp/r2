"""Shared fixtures.

Database tests run against a throwaway clone of the seeded template database,
which is the isolation mechanism ADR-0005 specifies. They skip cleanly when
TEST_DATABASE_URL is unset, so `pytest` is useful without a running Postgres.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

TEMPLATE_DB = os.environ.get("TEST_TEMPLATE_DB", "pos_template")


@pytest.fixture(scope="session")
def db_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set — run `make db` first")
    return url


@pytest.fixture(scope="session")
def conn(db_url: str):
    """A connection to a fresh clone of the seeded template.

    CREATE DATABASE ... TEMPLATE is a file copy, so this is cheap even at
    SEED_SIZE=full, and it means a test that writes cannot affect another.
    """
    psycopg = pytest.importorskip("psycopg")

    clone = "test_r2"
    admin = psycopg.connect(db_url, autocommit=True)
    try:
        admin.execute(f"DROP DATABASE IF EXISTS {clone} WITH (FORCE)")
        admin.execute(f"CREATE DATABASE {clone} TEMPLATE {TEMPLATE_DB}")
    except psycopg.errors.InvalidCatalogName:
        admin.close()
        pytest.skip(f"template database {TEMPLATE_DB} does not exist — run `make db`")
    finally:
        if not admin.closed:
            admin.close()

    target = db_url.rsplit("/", 1)[0] + "/" + clone
    connection = psycopg.connect(target)
    yield connection
    connection.close()

    admin = psycopg.connect(db_url, autocommit=True)
    admin.execute(f"DROP DATABASE IF EXISTS {clone} WITH (FORCE)")
    admin.close()


@pytest.fixture
def second_conn(db_url: str):
    """A SECOND connection to the same clone.

    `SKIP LOCKED` cannot be tested on one connection — the point is what happens
    when two transactions reach for the same row, and a single connection can
    only ever hold one of them. Built here rather than derived inside a test
    from `conn.info.dsn`, which psycopg strips the password out of, so
    reconnecting from it fails authentication and reads like the race failing.
    """
    psycopg = pytest.importorskip("psycopg")
    target = db_url.rsplit("/", 1)[0] + "/test_r2"
    connection = psycopg.connect(target)
    yield connection
    connection.close()


def fetch_one(conn, sql: str):
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchone()


def fetch_all(conn, sql: str):
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()
