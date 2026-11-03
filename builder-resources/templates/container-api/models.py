"""Persist entity records in SQLite; service transactions own mutations."""

from contextlib import contextmanager
from pathlib import Path
import sqlite3

from services.logger_service import log_function, LogStep


@contextmanager
def connection(path: str):
    """Close connections and commit or roll back a complete operation."""
    database = sqlite3.connect(path, timeout=10)
    database.row_factory = sqlite3.Row

    try:
        with LogStep('models.connection.transaction'), database:
            yield database
    finally:
        database.close()


@log_function
def initialize_database(path: str) -> None:
    """Create the durable record table without modifying existing data."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    with connection(path) as database:
        database.execute('CREATE TABLE IF NOT EXISTS records (entity TEXT NOT NULL, id TEXT NOT NULL, document TEXT NOT NULL, PRIMARY KEY(entity, id))')
