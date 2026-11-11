"""Helpers for passing SQLAlchemy database URLs to psycopg directly."""

from sqlalchemy.engine import make_url


def psycopg_connection_url(database_url: str, *, database: str | None = None) -> str:
    """Return a libpq-compatible PostgreSQL URI without logging credentials.

    SQLAlchemy URLs may include a driver suffix such as ``+psycopg``. psycopg's
    direct ``connect`` accepts the PostgreSQL URI scheme, so normalize that
    driver name while retaining SQLAlchemy's correct percent-quoting.
    """
    url = make_url(database_url)
    if url.get_backend_name() != "postgresql":
        raise ValueError("A PostgreSQL DATABASE_URL is required")
    url = url.set(drivername="postgresql")
    if database is not None:
        url = url.set(database=database)
    return url.render_as_string(hide_password=False)
