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

Safety model (Session 9, BUG-005 + CodeRabbit passes):

- Pre-flight catches FAILURE MODES, not data loss. Before the
  destructive reset, we verify psql, the streaming tool (gunzip for
  .gz, cat for plain .sql), and — for .gz — that the compressed file
  decompresses cleanly. If any check fails, the
  current DB is left untouched. `gzip -t` specifically guards against
  truncated backups: without it, a gunzip failure mid-stream would
  feed psql a truncated dump, which under --single-transaction would
  commit whatever SQL made it through before EOF.

- Pre-flight does NOT protect against invalid SQL. Once reset runs,
  the DB is dropped and recreated empty. If psql then rejects the
  dump (schema mismatch, syntax error, missing role, etc.),
  --single-transaction rolls back the restore portion, but the
  database is still empty — the pre-restore data is gone. There is no
  automatic restore-of-last-good here. If you need that, back up
  before running this script.

- Runtime hardening:
  - PGPASSWORD injected into psql's child env from POSTGRES_PASSWORD
    so non-interactive auth works against password-protected servers.
    Child env only — os.environ untouched.
  - psql runs with -X (ignore ~/.psqlrc), -v ON_ERROR_STOP=1, and
    --single-transaction. Any SQL error aborts and rolls back the
    restore. See caveat above about reset-already-happened.
  - psql stderr streams to the terminal live (not captured) so errors
    surface with psql's full context.
  - Return codes checked with psql-first ordering — producer's SIGPIPE
    is a consequence of psql's failure, not the cause. If psql
    succeeded but producer failed, that's a truncation case that
    slipped past gzip -t and gets its own message.
"""

import os
import shutil
import subprocess
import sys
import tempfile
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

# ---------------------------------------------------------------------------
# Pre-flight — everything below this line runs BEFORE the destructive
# reset. If any check fails, the current DB is left untouched.
#
# Scope: these checks catch MISSING TOOLS (psql, plus gunzip or cat
# depending on file type) and CORRUPT .gz files. They do NOT catch
# invalid SQL. Reset will drop and recreate the DB; if
# psql then rejects the dump, the pre-restore data is gone regardless
# of --single-transaction (which only rolls back the restore portion,
# leaving an empty database).
# ---------------------------------------------------------------------------

if not shutil.which("psql"):
    sys.exit(
        "psql not found on PATH — install postgresql-client or add it "
        "to PATH before restoring"
    )

if dump_path.suffix == ".gz":
    if not shutil.which("gunzip"):
        sys.exit("gunzip not found on PATH")
    print(f"Verifying {dump_path.name}...")
    check = subprocess.run(
        ["gunzip", "-t", str(dump_path)],
        stderr=subprocess.PIPE,
    )
    if check.returncode != 0:
        sys.stderr.write(check.stderr.decode(errors="replace"))
        sys.exit(
            f"{dump_path.name} failed integrity check — not resetting DB"
        )
else:
    # Non-.gz dumps are streamed via `cat`; if it's missing on this
    # system, detect now rather than after the destructive reset.
    if not shutil.which("cat"):
        sys.exit("cat not found on PATH")

# ---------------------------------------------------------------------------
# Step 1 — reset the DB by delegating to reset_local_db.py so the
# drop-and-recreate logic lives in one place. THIS IS DESTRUCTIVE.
# ---------------------------------------------------------------------------

print(f"\nResetting {db_name}...")
reset = subprocess.run(
    [sys.executable, "scripts/reset_local_db.py"],
    cwd=project_root,
)
if reset.returncode != 0:
    sys.exit(f"reset_local_db.py exited with code {reset.returncode}")

# ---------------------------------------------------------------------------
# Step 2 — pipe the dump into psql. Use gunzip for .gz, cat otherwise.
# ---------------------------------------------------------------------------

if dump_path.suffix == ".gz":
    dump_cmd = ["gunzip", "-c", str(dump_path)]
else:
    dump_cmd = ["cat", str(dump_path)]

print(f"Restoring {dump_path.name} into {db_name}...")

# Build the psql child env. Do NOT mutate os.environ — that would
# leak the credential to every subsequent subprocess this process
# spawns. Skip auth entirely when POSTGRES_PASSWORD is unset/empty
# so pg_hba.conf's trust/peer auth is exercised as configured (a
# local dev box may not need a password).
#
# Password is passed via PGPASSFILE (temp file, 0600, cleaned up in
# finally) rather than PGPASSWORD (env var, visible to `ps e`). Both
# are equivalent security-wise for a dev-only script whose password
# also lives in .env on the same disk; PGPASSFILE is the more
# idiomatic libpq mechanism and gets explicit cleanup.
child_env = os.environ.copy()

passfile_path = None
if password:
    # mkstemp creates with 0600 already; chmod is defensive in case
    # of a filesystem that doesn't honor the default.
    fd, passfile_path = tempfile.mkstemp(prefix="pgpass-", suffix=".txt")
    os.close(fd)
    os.chmod(passfile_path, 0o600)
    with open(passfile_path, "w") as f:
        # libpq pgpass format: hostname:port:database:username:password
        f.write(f"{host}:{port}:{db_name}:{user}:{password}\n")
    child_env["PGPASSFILE"] = passfile_path

try:
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
        sys.exit(
            f"psql exited with code {psql_rc} — DB has been reset and the "
            f"restore was rolled back. Current DB is empty."
        )

    # psql succeeded but producer failed. Silent-truncation risk: psql
    # may have been fed a partial dump and (perversely) restored
    # successfully if the failure happened after the last complete SQL
    # statement. The gzip -t pre-flight above catches the common case
    # (corrupt/truncated gzip), but this check remains as a belt-and-
    # braces for any producer failure that slips past.
    if producer_rc != 0:
        sys.exit(
            f"{dump_cmd[0]} exited with code {producer_rc} — restore may be "
            f"incomplete"
        )
finally:
    # Remove the passfile on every path: success, psql failure,
    # producer failure, or any unexpected exception between Popen
    # calls. sys.exit raises SystemExit which propagates through
    # finally, so cleanup runs before process termination.
    if passfile_path and os.path.exists(passfile_path):
        try:
            os.unlink(passfile_path)
        except OSError:
            pass

print(f"Restored {dump_path.name} into {db_name}.")
print("\nNext:")
print("  uv run python manage.py showmigrations schedule")