"""Reset the local dev DB and restore a backup into it.

Designed to be run as a Zed task (or any shell) with no arguments —
prompts for the backup filename.

Usage:
    uv run python scripts/restore_local_db.py

Assumes the backup file lives in ~/Downloads. Accepts either .sql.gz
(compressed) or plain .sql. Resets the DB via reset_local_db.py first,
then pipes the dump into psql.

Refuses to run when DJANGO_DEBUG is False, matching reset_local_db.py's
guard.

Robustness (Session 8.5, BUG-005):
- PGPASSWORD is injected into the psql child environment so the
  restore can authenticate non-interactively against a password-
  protected server. Value comes from POSTGRES_PASSWORD in .env.
- psql runs with -v ON_ERROR_STOP=1 and --single-transaction, so any
  SQL error aborts and rolls back everything. A partial restore is
  impossible.
- -X (--no-psqlrc) prevents a user's ~/.psqlrc from overriding
  ON_ERROR_STOP (e.g. a stray `\\set ON_ERROR_STOP off` would silently
  disable fail-fast, defeating --single-transaction's rollback).
- psql's stderr streams to the terminal live, not captured — errors
  surface immediately with psql's full context.
- Both subprocess return codes are checked. psql first: under
  ON_ERROR_STOP, a psql failure closes the pipe and producer exits
  with SIGPIPE (-13), so blaming producer first would misreport the
  cause. If psql succeeded but producer failed, that's the silent-
  truncation case and gets its own message.
"""

import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

if os.environ.get("DJANGO_DEBUG", "False").lower() not in ("true", "1", "yes"):
    sys.exit("Refusing to run: DJANGO_DEBUG is not True")

downloads = Path.home() / "Downloads"

# Show a hint of what's available so the user doesn't have to tab over
# to Finder to remember the filename. Only the most recent few, sorted
# descending, filtered to plausible dump files.
candidates = sorted(
    [
        p
        for p in downloads.glob("work_schedule_*.sql*")
        if p.is_file()
    ],
    key=lambda p: p.stat().st_mtime,
    reverse=True,
)[:5]

if candidates:
    print("Recent backups in ~/Downloads:")
    for p in candidates:
        print(f"  {p.name}")
    print()

raw = input("Backup filename: ").strip()
if not raw:
    sys.exit("No filename entered.")

dump_path = downloads / raw
if not dump_path.exists():
    sys.exit(f"Not found: {dump_path}")

db_name = os.environ["POSTGRES_DB"]
user = os.environ["POSTGRES_USER"]
host = os.environ.get("POSTGRES_HOST", "127.0.0.1")
port = os.environ.get("POSTGRES_PORT", "5432")
password = os.environ.get("POSTGRES_PASSWORD", "")

project_root = Path(__file__).resolve().parent.parent

# Step 1 — reset the DB by delegating to reset_local_db.py so the
# drop-and-recreate logic lives in one place.
print(f"\nResetting {db_name}...")
reset = subprocess.run(
    [sys.executable, "scripts/reset_local_db.py"],
    cwd=project_root,
)
if reset.returncode != 0:
    sys.exit(f"reset_local_db.py exited with code {reset.returncode}")

# Step 2 — pipe the dump into psql. Use gunzip for .gz, cat otherwise.
if dump_path.suffix == ".gz":
    dump_cmd = ["gunzip", "-c", str(dump_path)]
else:
    dump_cmd = ["cat", str(dump_path)]

print(f"Restoring {dump_path.name} into {db_name}...")

# Inject PGPASSWORD into the child env only — do NOT mutate
# os.environ, which would leak the credential to every subsequent
# subprocess this process spawns. Skip the injection when the env
# var is unset or empty so pg_hba.conf's trust/peer auth is
# exercised as configured (a local dev box may not need a password).
child_env = os.environ.copy()
if password:
    child_env["PGPASSWORD"] = password

producer = subprocess.Popen(dump_cmd, stdout=subprocess.PIPE)
psql = subprocess.Popen(
    [
        "psql",
        "-X",                              # ignore ~/.psqlrc
        "-h", host,
        "-p", port,
        "-U", user,
        "-d", db_name,
        "-q",
        "-v", "ON_ERROR_STOP=1",
        "--single-transaction",
    ],
    stdin=producer.stdout,
    env=child_env,
    # stderr not captured: psql's error messages stream live with
    # full context (line number, offending SQL fragment). Capturing
    # hides errors until the very end and forces the user to hunt
    # through a buffer to find the actual problem.
)
# Close our copy of the pipe's read end so the producer receives
# SIGPIPE if psql exits early (which it will under ON_ERROR_STOP).
# Without this, gunzip/cat can hang waiting for a reader that's gone.
producer.stdout.close()

psql_rc = psql.wait()
producer_rc = producer.wait()

# Report psql's error first. When psql fails under ON_ERROR_STOP,
# producer gets SIGPIPE and exits with a non-zero status (typically
# -13 / 141) — that's a consequence of psql's failure, not the cause.
# Reporting producer's return code first would blame gunzip for what
# psql actually did wrong.
if psql_rc != 0:
    sys.exit(f"psql exited with code {psql_rc}")

# psql succeeded but producer failed. Silent-truncation risk: psql
# may have been fed a partial dump and (perversely) restored
# successfully if the failure happened after the last complete SQL
# statement. Under --single-transaction this is unlikely to have
# committed real damage, but the restore is still unreliable —
# surface it.
if producer_rc != 0:
    sys.exit(
        f"{dump_cmd[0]} exited with code {producer_rc} — restore may be "
        f"incomplete"
    )

print(f"Restored {dump_path.name} into {db_name}.")
print("\nNext:")
print("  uv run python manage.py showmigrations schedule")