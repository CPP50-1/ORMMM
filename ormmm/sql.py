from psycopg import sql


def build_create_table(cls) -> sql.Composed:
    """Generate CREATE TABLE DDL (Data Definition Language) for a model class.

    - Table name: lowercase class name (matches registry key & adapter contract).
    - id column: SERIAL PRIMARY KEY (skips the metaclass-injected IntField).
    - Other columns: rendered from cls._fields in declaration order.
    - Column types come from field.sql_type (trusted internal constants).
    """
    # Start with the auto-increment primary key
    columns: list[sql.Composable] = [sql.SQL("id SERIAL PRIMARY KEY")]

    for name, field in cls._fields.items():
        if name == "id":
            # Skip the metaclass-injected IntField; we render SERIAL PRIMARY KEY instead
            continue

        columns.append(sql.SQL("{} {}").format(sql.Identifier(name), sql.SQL(field.sql_type)))

    # Compose: CREATE TABLE IF NOT EXISTS table_name (col1, col2, ...)
    # IF NOT EXISTS makes setup idempotent, safe to re-run without teardown
    return sql.SQL("CREATE TABLE IF NOT EXISTS {} ({})").format(
        sql.Identifier(cls.__name__.lower()), sql.SQL(", ").join(columns)
    )


def build_insert(cls, values: dict) -> tuple[sql.Composed, list]:
    """Generate a parameterized INSERT ... RETURNING id for a model.

    - Table name: lowercase class name (matches registry key & adapter contract).
    - Only declared fields are inserted; 'id' is skipped (SERIAL PRIMARY KEY).
    - Column names go through sql.Identifier; values are passed as %s query
      parameters, never string-formatted (spec 5.3 — injection safety).
    - Keys in `values` that are not declared fields are ignored.
    """
    columns: list[str] = []
    params: list = []
    for name in cls._fields:
        if name == "id":
            continue
        if name in values:
            columns.append(name)
            params.append(values[name])

    if not columns:
        raise ValueError(f"no column values to insert for {cls.__name__}")

    query = sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING id").format(
        sql.Identifier(cls.__name__.lower()),
        sql.SQL(", ").join(sql.Identifier(name) for name in columns),
        sql.SQL(", ").join(sql.Placeholder() for _ in columns),
    )
    return query, params
