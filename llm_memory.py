from psycopg_pool import ConnectionPool
from langgraph.checkpoint.postgres import PostgresSaver


def build_checkpointer(db_uri: str, schema: str = "public") -> PostgresSaver:
    def set_search_path(conn):
        if schema != "public":
            with conn.cursor() as cur:
                cur.execute(f"SET search_path TO {schema};")

    pool = ConnectionPool(
        conninfo=db_uri,
        max_size=5,
        open=True,
        configure=set_search_path,
        kwargs={"autocommit": True}
    )

    # Ensure schema exists if not public
    if schema != "public":
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema};")
                cur.execute(f"SET search_path TO {schema};")

    checkpointer = PostgresSaver(pool)
    checkpointer.setup()

    return checkpointer, pool
