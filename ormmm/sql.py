from psycopg import sql

APPROVED_OPS = {
    "=": sql.SQL("="),
    "!=": sql.SQL("!="),
    "<": sql.SQL("<"),
    ">": sql.SQL(">"),
    "<=": sql.SQL("<="),
    ">=": sql.SQL(">="),
    "like": sql.SQL("LIKE"),
    "ilike": sql.SQL("ILIKE"),
    "in": sql.SQL("= ANY"),
}


def build_where_clause(domain: list) -> tuple[sql.Composed | None, list]:
    """Parse custom QueryExpressions or classic Odoo tuples into a parameterized WHERE clause.

    - Supports both Model.field == value AND ('field', '=', value) for test acceptance.
    - Validates operators against the internal APPROVED_OPS allowlist.
    """
    if not domain:
        return None, []

    where_clauses: list[sql.Composable] = []
    params: list = []

    # Local import to avoid circular dependencies
    from .fields import QueryExpression

    for expr in domain:
        if isinstance(expr, QueryExpression):
            # Format 1 : Pythonic expression
            if expr.field_name is None:
                raise ValueError("QueryExpression field_name cannot be None")
            field_name = expr.field_name
            op_key = str(expr.operator).lower().strip()
            value = expr.value
        elif isinstance(expr, tuple) and len(expr) == 3:
            # Format 2 : Odoo-style format, needed for test validation (ex: ('city', '=', 'Liege'))
            field_name, op_key, value = expr
            op_key = str(op_key).lower().strip()
        else:
            raise TypeError(
                f"Unsupported domain element: {expr!r}. "
                f"Expected a QueryExpression or a 3-element tuple."
            )

        # Fail loudly on typos: silently mapping to '=' would make a bad
        # operator match every row instead of erroring out.
        if op_key not in APPROVED_OPS:
            raise ValueError(f"unsupported operator {op_key!r} — allowed: {sorted(APPROVED_OPS)}")

        sql_op = APPROVED_OPS[op_key]

        if op_key == "in":
            # id = ANY(%s)  syntax for lists
            where_clauses.append(
                sql.SQL("{} {} ({})").format(sql.Identifier(field_name), sql_op, sql.Placeholder())
            )
            params.append(list(value))
        else:
            # Standard syntax for other operators (==, <, >, etc.)
            where_clauses.append(
                sql.SQL("{} {} {}").format(sql.Identifier(field_name), sql_op, sql.Placeholder())
            )
            params.append(value)

    # Joins all individual conditions with ' AND '
    composed_where = sql.SQL(" AND ").join(where_clauses)
    return composed_where, params


def build_create_table(cls) -> sql.Composed:
    """Generate CREATE TABLE DDL (Data Definition Language) for a model class.

    - Table name: lowercase class name (matches registry key & adapter contract).
    - id column: SERIAL PRIMARY KEY (skips the metaclass-injected IntField).
    - Other columns: rendered from cls._fields in declaration order.
    - Column types come from field.sql_type (trusted internal constants).
    - Many2one fields: INTEGER with FOREIGN KEY constraint.
    """
    # Local import to avoid circular dependencies
    from .fields import Many2oneField

    # Start with the auto-increment primary key
    columns: list[sql.Composable] = [sql.SQL("id SERIAL PRIMARY KEY")]

    for name, field in cls._fields.items():
        if name == "id":
            # Skip the metaclass-injected IntField; we render SERIAL PRIMARY KEY instead
            continue

        if isinstance(field, Many2oneField):
            # Many2one field: INTEGER with FOREIGN KEY
            target_table = field.target_model.__name__.lower()
            columns.append(
                sql.SQL("{} INTEGER REFERENCES {} (id)").format(
                    sql.Identifier(name),
                    sql.Identifier(target_table)
                )
            )
        else:
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


def build_delete(cls, record_id: int) -> tuple[sql.Composed, list]:
    """Generate a parameterized DELETE for a model by id."""
    query = sql.SQL("DELETE FROM {} WHERE id = {}").format(
        sql.Identifier(cls.__name__.lower()),
        sql.Placeholder(),
    )
    return query, [record_id]


def build_update(cls, values: dict) -> tuple[sql.Composed, list]:
    """Generate a parameterized UPDATE ... WHERE id = %s for a model.

    - Table name: lowercase class name (matches registry key & adapter contract).
    - Only declared fields are updated; 'id' is excluded from SET clause.
    - Column names are from cls._fields (trusted internal data).
    - Values use %s placeholders (psycopg3 parameter binding, spec 5.3 — injection safety).
    - Keys in `values` that are not declared fields are ignored.
    """
    set_parts: list = []
    params: list = []
    for name in cls._fields:
        if name == "id":
            continue
        if name in values:
            # Build "name = %s" using psycopg3 SQL composition
            set_parts.append(sql.Identifier(name))
            set_parts.append(sql.Placeholder())
            params.append(values[name])

    if not set_parts:
        raise ValueError(f"no column values to update for {cls.__name__}")

    # Build SET clause: "name1 = %s, name2 = %s"
    set_clause = sql.SQL(", ").join(
        sql.SQL("{} = {}").format(set_parts[i], set_parts[i + 1]) for i in range(0, len(set_parts), 2)
    )

    # Compose: UPDATE table SET col1 = %s, col2 = %s WHERE id = %s
    query = sql.SQL("UPDATE {} SET {} WHERE id = {}").format(
        sql.Identifier(cls.__name__.lower()),
        set_clause,
        sql.Placeholder(),
    )
    return query, params


def build_search(cls, domain: list) -> tuple[sql.Composed, list]:
    """Generate a parameterized SELECT * FROM table statement for a model.

    - Table name: lowercase class name (matches registry key & adapter contract).
    - Delegates domain and placeholder generation to build_where_clause() (spec 5.3).
    """
    table_name = getattr(cls, "_table", cls.__name__.lower())
    table_identifier = sql.Identifier(table_name)

    # 1. Get the fragment of the where clause and its associated parameters
    where_fragment, params = build_where_clause(domain)

    # 2. If domain is empty (and therefore where_fragment is None) : "naked" SELECT all
    if where_fragment is None:
        return sql.SQL("SELECT * FROM {}").format(table_identifier), []

    # 3. Otherwise, rebuild everything together with the where clause [5.3]
    query = sql.SQL("SELECT * FROM {} WHERE {}").format(table_identifier, where_fragment)
    return query, params


def build_search_by_ids(cls, ids: list) -> tuple[sql.Composed, list]:
    """Generate a parameterized SELECT * ... WHERE id = ANY(%s) for batch loading.

    - Used by RecordSet.prefetch() to fetch many rows in ONE query (spec 5.6).
    - The id list is passed as a %s parameter (psycopg adapts a Python list
      to a PostgreSQL array), never string-formatted (spec 5.3).
    """
    table_name = getattr(cls, "_table", cls.__name__.lower())
    query = sql.SQL("SELECT * FROM {} WHERE id = ANY(%s)").format(sql.Identifier(table_name))
    return query, [list(ids)]
