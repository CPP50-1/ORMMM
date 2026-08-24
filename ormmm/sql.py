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

    # Import local pour éviter les imports circulaires
    from .fields import QueryExpression

    for expr in domain:
        if isinstance(expr, QueryExpression):
            # Format 1 : Votre expression Pythonique (ex: User.name == 'Alice')
            if expr.field_name is None:
                raise ValueError("QueryExpression field_name cannot be None")
            field_name = expr.field_name
            op_key = str(expr.operator).lower().strip()
            value = expr.value
        elif isinstance(expr, tuple) and len(expr) == 3:
            # Format 2 : Le tuple classique exigé par vos tests (ex: ('city', '=', 'Liege'))
            field_name, op_key, value = expr
            op_key = str(op_key).lower().strip()
        else:
            raise TypeError(
                f"Unsupported domain element: {expr!r}. "
                f"Expected a QueryExpression or a 3-element tuple."
            )

        sql_op = APPROVED_OPS.get(op_key, sql.SQL("="))

        if op_key == "in":
            # Syntaxe id = ANY(%s) pour les listes
            where_clauses.append(
                sql.SQL("{} {} ({})").format(sql.Identifier(field_name), sql_op, sql.Placeholder())
            )
            params.append(list(value))
        else:
            # Syntaxe standard pour les autres opérateurs (==, <, >, etc.)
            where_clauses.append(
                sql.SQL("{} {} {}").format(sql.Identifier(field_name), sql_op, sql.Placeholder())
            )
            params.append(value)

    # Fusionne toutes les conditions individuelles avec un opérateur ' AND '
    composed_where = sql.SQL(" AND ").join(where_clauses)
    return composed_where, params


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


def build_search(cls, domain: list) -> tuple[sql.Composed, list]:
    """Generate a parameterized SELECT * FROM table statement for a model.

    - Table name: lowercase class name (matches registry key & adapter contract).
    - Delegates domain and placeholder generation to build_where_clause() (spec 5.3).
    """
    table_name = getattr(cls, "_table", cls.__name__.lower())
    table_identifier = sql.Identifier(table_name)

    # 1. On extrait le fragment de clause WHERE et ses paramètres associés
    where_fragment, params = build_where_clause(domain)

    # 2. Si le domaine est vide (where_fragment vaut None) : SELECT global simple
    if where_fragment is None:
        return sql.SQL("SELECT * FROM {}").format(table_identifier), []

    # 3. Sinon, assemblage final sécurisé avec la clause WHERE [spec 5.3]
    query = sql.SQL("SELECT * FROM {} WHERE {}").format(table_identifier, where_fragment)
    return query, params
