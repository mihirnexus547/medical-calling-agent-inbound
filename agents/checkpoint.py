"""PostgresSaver checkpointer for LangGraph persistent multi-agent checkpoints."""

import os
from dotenv import load_dotenv
from psycopg_pool import ConnectionPool
from langgraph.checkpoint.postgres import PostgresSaver

load_dotenv()

DB_URI = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/patient_db"
)

# Shared connection pool for Postgres checkpointer
pool = ConnectionPool(
    conninfo=DB_URI,
    max_size=20,
    kwargs={"autocommit": True}
)

postgres_checkpointer = PostgresSaver(pool)

# Ensure checkpoint tables are created
try:
    postgres_checkpointer.setup()
except Exception as exc:
    # If already set up or concurrent setup
    pass
