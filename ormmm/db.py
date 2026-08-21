"""Database connection wrapper with query counter (ADR §4.3).

Two connections:
- counted_conn: every execute() increments counter + logs SQL (for ORM queries)
- raw_conn: executes without counting (for test introspection via adapter.raw_sql)
"""

import psycopg
from psycopg import sql


class DB:
    """Wrapper around a psycopg3 connection that counts and logs queries."""

    def __init__(self, dsn: str = "dbname=mini_orm_test"):
        # Main connection — all ORM queries go through this (counted)
        self.conn = psycopg.connect(dsn, autocommit=True)
        # Second connection for raw introspection queries — NOT counted
        self.raw_conn = psycopg.connect(dsn, autocommit=True)

        self._query_count = 0
        self._query_log = []

    def execute(self, query, params=None):
        """Execute a query on the counted connection.

        Increments the query counter and appends to the log.
        Accepts both SQL strings and psycopg.sql.Composable objects.
        """
        self._query_count += 1
        # Materialize composable to string for logging
        if isinstance(query, sql.Composable):
            sql_str = query.as_string(self.conn)
        else:
            sql_str = query
        self._query_log.append(sql_str)

        # Execute with parameters (params may be None)
        return self.conn.execute(sql_str, params)

    def raw_execute(self, query, params=None):
        """Execute on the raw connection — NOT counted or logged.

        Used by adapter.raw_sql() for schema introspection without polluting counts.
        """
        if isinstance(query, sql.Composable):
            sql_str = query.as_string(self.raw_conn)
        else:
            sql_str = query
        return self.raw_conn.execute(sql_str, params)

    def reset_queries(self):
        """Reset the query counter and log — called by adapter.reset_queries()."""
        self._query_count = 0
        self._query_log.clear()

    def query_count(self) -> int:
        """Return number of counted queries since last reset."""
        return self._query_count

    def query_log(self) -> list[str]:
        """Return list of executed SQL strings since last reset."""
        return list(self._query_log)

    def close(self):
        """Close both connections."""
        self.conn.close()
        self.raw_conn.close()