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
