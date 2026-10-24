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

producer = subprocess.Popen(dump_cmd, stdout=subprocess.PIPE)
psql = subprocess.Popen(
    [
        "psql",
        "-h", host,
        "-p", port,
        "-U", user,
        "-d", db_name,
        "-q",
    ],
    stdin=producer.stdout,
    stderr=subprocess.PIPE,
)
producer.stdout.close()
_, psql_stderr = psql.communicate()

if psql.returncode != 0:
    sys.stderr.write(psql_stderr.decode(errors="replace"))
    sys.exit(f"psql exited with code {psql.returncode}")

print(f"Restored {dump_path.name} into {db_name}.")
print("\nNext:")
print("  uv run python manage.py showmigrations schedule")