import pytest
from psycopg.conninfo import conninfo_to_dict

from app.db_urls import psycopg_connection_url


def test_sqlalchemy_psycopg_url_is_normalized_for_direct_psycopg_connect():
    normalized = psycopg_connection_url(
        "postgresql+psycopg://devpilot:p%40ss%3Dword%2F%25@localhost:5432/devpilot"
        "?sslmode=require&application_name=legacy-check",
        database="postgres",
    )

    parsed = conninfo_to_dict(normalized)
    assert normalized.startswith("postgresql://")
    assert "+psycopg" not in normalized
    assert parsed["user"] == "devpilot"
    assert parsed["password"] == "p@ss=word/%"
    assert parsed["host"] == "localhost"
    assert parsed["port"] == "5432"
    assert parsed["dbname"] == "postgres"
    assert parsed["sslmode"] == "require"
    assert parsed["application_name"] == "legacy-check"


def test_psycopg_url_rejects_non_postgresql_backends():
    with pytest.raises(ValueError, match="PostgreSQL"):
        psycopg_connection_url("sqlite+pysqlite:///./devpilot.db")
