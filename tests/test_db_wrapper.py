"""Unit tests for the DB connection wrapper (ormmm.db) on a throwaway instance."""

import pytest
from psycopg import sql

from ormmm.db import DB


@pytest.fixture
def db():
    database = DB()
    yield database
    database.close()


class TestDBWrapper:
    def test_execute_counts_and_logs(self, db):
        db.execute("SELECT 1")
        db.execute("SELECT %s", (2,))
        assert db.query_count() == 2
        log = db.query_log()
        assert len(log) == 2
        assert all(isinstance(entry, str) for entry in log)
        assert log[0] == "SELECT 1"

    def test_composed_queries_are_logged_as_text(self, db):
        db.execute(sql.SQL("SELECT {}").format(sql.Placeholder()), (42,))
        assert "SELECT %s" in db.query_log()[0]

    def test_raw_execute_is_invisible_to_counter_and_log(self, db):
        db.raw_execute("SELECT 1")
        db.raw_execute("SELECT 2")
        assert db.query_count() == 0
        assert db.query_log() == []

    def test_reset_clears_counter_and_log(self, db):
        db.execute("SELECT 1")
        db.reset_queries()
        assert db.query_count() == 0
        assert db.query_log() == []

    def test_close_shuts_both_connections(self):
        database = DB()
        database.close()
        assert database.conn.closed is True
        assert database.raw_conn.closed is True

    def test_query_log_returns_a_copy(self, db):
        db.execute("SELECT 1")
        snapshot = db.query_log()
        snapshot.clear()
        assert len(db.query_log()) == 1
