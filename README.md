# Work Schedule

![Tests](https://github.com/owenrhoekstra/work_schedule/actions/workflows/tests.yml/badge.svg)

A small internal tool for managing employee schedules. Built for a home-services team: managers define weekly shift patterns, employees see their upcoming schedule, and notification emails are opt-in per action.

---

## Features

- **Weekly schedule grid** — every active employee and their shifts, Mon–Sat, scrollable by week with a date picker for jumping.
- **Multi-week cycle patterns** — support for 1, 2, 3, or 4-week rotations (e.g. mornings this week, afternoons next).
- **Per-day overrides** — click any cell to change that employee's shift for one specific day without touching their default pattern. Overridden cells render in coral.
- **Day-level overrides** — mark a whole date as Closed or Holiday; every employee's cell for that day is suppressed.
- **Employment periods** — an employee can be deactivated and later reactivated without losing their history. The schedule correctly shows gaps between periods.
- **Last-day semantics** — deactivating an employee sets their final day on the schedule. Everything internal (period closure, user deactivation) is anchored to the day after.
- **Invite-only signup** — a manager adds an employee, the employee signs up with that email, verifies with a one-time code, and waits for manager approval.
- **OTP-gated password change** — changing a password requires a fresh email code, valid for 5 minutes.
- **Rate limiting** — django-axes locks out repeated failed logins per username+IP, with the real client IP resolved through Cloudflare Tunnel.
- **Email notifications** — welcome, account-approved, shift-changed, and deactivation emails, all opt-in via checkboxes. Plain-text fallbacks for every HTML template.
- **Custom error pages** — branded 404, 403, 500, and lockout pages.
- **Mobile responsive** — nav, home schedule, and auth pages work at phone widths.

---

## Tech Stack

| Layer              | Tool                                 |
| ------------------ | ------------------------------------ |
| Framework          | Django 6.1                           |
| Language           | Python 3.14                          |
| Database           | PostgreSQL 18                        |
| Cache / sessions   | Redis 7                              |
| Email              | Resend via django-anymail            |
| Rate limiting      | django-axes                          |
| Static files       | WhiteNoise                           |
| Styling            | Tailwind CSS 4 (via django-tailwind) |
| Dependency manager | uv                                   |
| Deployment         | Docker Compose                       |
| Ingress            | Cloudflare Tunnel                    |
| Offsite backups    | Backblaze B2 via rclone (encrypted)  |

---

## Local Development

### Prerequisites

- Python 3.14
- [uv](https://docs.astral.sh/uv/)
- PostgreSQL 18 running locally
- Redis running locally

On macOS:

```bash
brew install postgresql@18 redis
brew services start postgresql@18
brew services start redis
```

Create the dev database and user:

```sql
psql postgres
CREATE USER work_schedule_user WITH PASSWORD 'changeme';
CREATE DATABASE work_schedule OWNER work_schedule_user;
\q
```

### Setup

```bash
git clone git@github.com:owenrhoekstra/work_schedule.git
cd work_schedule
uv sync
```

Create a `.env` file at the project root:

```bash
DJANGO_SECRET_KEY=<generate with: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())">
DJANGO_DEBUG=True
DJANGO_SECURE=False
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=

POSTGRES_DB=work_schedule
POSTGRES_USER=work_schedule_user
POSTGRES_PASSWORD=changeme
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432

REDIS_URL=redis://127.0.0.1:6379/0

SITE_URL=http://localhost:8000
DEFAULT_FROM_EMAIL="Work Schedule <noreply@example.com>"
# RESEND_API_KEY=re_...   # leave unset to print emails to the console
```

Apply migrations and create a superuser:

```bash
uv run python manage.py migrate
uv run python manage.py createsuperuser
```

Build the Tailwind stylesheet:

```bash
uv run python manage.py tailwind build
```

### Running

```bash
uv run python manage.py runserver
```

Open http://localhost:8000. The root redirects to `/schedule/home/`.

For iterative frontend work, run Tailwind in watch mode in a separate terminal:

```bash
uv run python manage.py tailwind start
```

### Environment variables

| Variable                      | Purpose                                                                        |
| ----------------------------- | ------------------------------------------------------------------------------ |
| `DJANGO_SECRET_KEY`           | Django's signing key. Required.                                                |
| `DJANGO_DEBUG`                | `True` in dev, `False` in prod.                                                |
| `DJANGO_SECURE`               | Set to `True` in prod to enable SSL redirect, HSTS, secure cookies.            |
| `DJANGO_ALLOWED_HOSTS`        | Comma-separated list of valid `Host` headers.                                  |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Comma-separated list of full origins (`https://…`) allowed for POST requests.  |
| `POSTGRES_*`                  | Database connection.                                                           |
| `REDIS_URL`                   | Redis connection string for sessions and OTP storage.                          |
| `SITE_URL`                    | Public base URL used in outgoing email links.                                  |
| `DEFAULT_FROM_EMAIL`          | Sender address for all outgoing email. Must be a verified domain in Resend.    |
| `RESEND_API_KEY`              | API key from Resend. If unset, emails print to the console instead of sending. |

---

## Testing

Run the full suite:

```bash
uv run python manage.py test
```

With coverage:

```bash
uv run coverage run manage.py test
uv run coverage report --skip-covered
```

Tests run automatically on every push via GitHub Actions (`.github/workflows/tests.yml`). The workflow spins up a fresh Postgres and runs `collectstatic` before the suite — both are required for tests to pass in a clean environment.

### Pre-commit checks

Three commands to run before any push that touches code:

```bash
uv run python manage.py check          # Django system check
uv run python manage.py test           # full test suite
uv lock --check                        # confirm lockfile is current
```

If `uv lock --check` fails, run `uv lock` to regenerate.

---

## Deployment

Production runs on a Linux server with Docker Compose. Ingress is handled by a Cloudflare Tunnel — no ports are exposed on the host.

### Layout

```
/srv/storage/work_schedule/
├── docker-compose.yml
├── .env
├── backup.sh
└── app/                ← git clone of this repo
```

### First deploy

1. Install Docker and Docker Compose on the server.
2. Clone the repo into `app/`:
   ```bash
   cd /srv/storage/work_schedule
   git clone git@github.com:owenrhoekstra/work_schedule.git app
   ```
3. Create a `.env` at the deploy root — same variables as dev, with `DJANGO_DEBUG=False`, `DJANGO_SECURE=True`, `DJANGO_ALLOWED_HOSTS=<your-domain>`, and a fresh `DJANGO_SECRET_KEY`.
4. Build and start:
   ```bash
   docker compose up -d
   ```
5. Create the first superuser:
   ```bash
   docker compose exec -it web python manage.py createsuperuser
   ```

### Redeploy

```bash
cd /srv/storage/work_schedule/app
git pull
cd ..
docker compose build web
docker compose up -d
docker compose logs -f web
```

Watch the startup log until `Listening at: http://0.0.0.0:8000`. Then verify:

```bash
docker compose exec web python manage.py check --deploy
curl -i http://localhost:8000/healthz/
```

### Rollback

```bash
cd /srv/storage/work_schedule/app
git log --oneline -5
git checkout <previous-commit>
cd ..
docker compose build web
docker compose up -d
```

### Services

| Service       | Purpose                                                                    |
| ------------- | -------------------------------------------------------------------------- |
| `db`          | PostgreSQL 18. Data in a named volume `postgres_data`.                     |
| `redis`       | Redis 7 for sessions and OTP. Data in `redis_data`.                        |
| `web`         | Gunicorn + Django. Built from `app/Dockerfile`.                            |
| `cloudflared` | Cloudflare Tunnel connector. Reads `CLOUDFLARE_TUNNEL_SECRET` from `.env`. |

---

## Backups

Local and offsite backups run nightly via a systemd timer on the server.

- **Local:** `/srv/storage/work_schedule/backups/` — 30-day retention.
- **Offsite:** Backblaze B2, encrypted client-side via `rclone crypt`.
- **Retention:** 30 days both places.

The backup script runs `pg_dump` inside the `db` container, gzips the result, and pipes it through rclone.

To run a backup manually:

```bash
sudo systemctl start work-schedule-backup.service
sudo journalctl -u work-schedule-backup.service -n 20 --no-pager
```

To verify an offsite backup exists:

```bash
sudo rclone ls b2-workschedule-crypt:
```

The rclone crypt passphrases must be stored somewhere durable — losing them means the offsite backups are unrecoverable.

---

## Project Structure

```
work_schedule/
├── accounts/                  # auth, signup, profile, OTP, approval flow
│   ├── emails.py              # send_email() wrapper
│   ├── otp.py                 # OTP generation, storage, verification
│   ├── views.py
│   └── tests/
├── schedule/                  # the schedule itself
│   ├── middleware.py          # enforces last_day at request time
│   ├── models.py              # Employee, EmploymentPeriod, Shift, ShiftOverride, DayOverride, Role, Title
│   ├── notifications.py       # email helpers for welcome/approved/shift/deactivation
│   ├── signals.py             # EmploymentPeriod creation, User↔Employee sync
│   ├── views.py
│   └── tests/
├── theme/                     # Tailwind app
│   └── static_src/src/styles.css
├── templates/                 # project-level templates
│   ├── base.html
│   ├── emails/                # HTML + .txt email templates
│   └── registration/          # auth pages
├── work_schedule/             # project config
│   ├── settings.py
│   ├── urls.py
│   └── views.py               # healthz
├── Dockerfile
├── entrypoint.sh              # builds Tailwind, collects static, migrates
├── docker-compose.yml
├── pyproject.toml
└── uv.lock
```

---

## Design Notes

### Employment periods

An `Employee` can have multiple `EmploymentPeriod` rows. The schedule asks "was this person employed on this specific date?" rather than reading a single start/end pair. This lets a rehire preserve their prior history without creating duplicate employee records.

### Last day vs. inactivated on

The UI says "last day" everywhere. Internally, `Employee.last_day` is the final working day; `EmploymentPeriod.end_date` is exclusive (the day after). The middleware enforces user deactivation on `last_day + 1` by checking `last_day < today` at every authenticated request, rather than relying on a scheduled task.

### Cycle patterns

Employees can have a 1–4 week repeating schedule. All cycles share a global epoch (`CYCLE_EPOCH` in `settings.py`) so different employees on different cycle lengths stay synchronized — a manager can look at a week and say "this is Week B for everyone on a 2-week cycle."

### Notifications are opt-in

Adding an employee, changing a shift, approving an account, and deactivating an employee all have a "notify" checkbox. No emails go out automatically. This keeps the manager in control of what the employee receives and prevents noise during setup.

---

## License

Private project. Not licensed for redistribution.
