"""Drop and recreate the local dev database.

For local use only. Refuses to run when DJANGO_DEBUG is False.
"""

import os
import sys

import psycopg
from dotenv import load_dotenv

load_dotenv()

if os.environ.get("DJANGO_DEBUG", "False").lower() not in ("true", "1", "yes"):
    sys.exit("Refusing to run: DJANGO_DEBUG is not True")

db_name = os.environ["POSTGRES_DB"]
user = os.environ["POSTGRES_USER"]
password = os.environ["POSTGRES_PASSWORD"]
host = os.environ.get("POSTGRES_HOST", "127.0.0.1")
port = os.environ.get("POSTGRES_PORT", "5432")

# Connect to the maintenance database. Homebrew, Postgres.app, and Docker
# all ship with a "postgres" database by default.
conn = psycopg.connect(
    dbname="postgres",
    user=user,
    password=password,
    host=host,
    port=port,
    autocommit=True,
)

with conn.cursor() as cur:
    # Kick anyone off the database so we can drop it
    cur.execute(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        "WHERE datname = %s AND pid <> pg_backend_pid()",
        (db_name,),
    )
    cur.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
    cur.execute(f'CREATE DATABASE "{db_name}" OWNER "{user}"')

conn.close()
print(f"Recreated database: {db_name}")
