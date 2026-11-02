# Production deployment

Production runs on a Linux server with Docker Compose. Ingress is
handled by a Cloudflare Tunnel — no ports are exposed on the host.
Staging sits alongside prod on the same host with its own isolated
stack. See `docs/STAGING.md` for staging setup.

## Branch flow

Code reaches production through staging:

- feature branch → `staging` (deploy to staging env, verify)
- → `staging` → `main` (deploy to prod env)

Prod only ever sees commits that have run on staging first.

## Server layout

```
/srv/storage/work_schedule/
├── docker-compose.yml
├── .env
├── backup.sh
└── app/                ← git clone of this repo
```

`app/` tracks `main`. `docker-compose.yml`, `.env`, and `backup.sh`
live one level up — server-specific infrastructure, not tracked by
the repo.

## First deploy

1. Install Docker and Docker Compose on the server.
2. Clone the repo into `app/`:
   ```bash
   cd /srv/storage/work_schedule
   git clone git@github.com:owenrhoekstra/work_schedule.git app
   ```
3. Create a `.env` at the deploy root. Same variables as dev, with:
   - `DJANGO_DEBUG=False`
   - `DJANGO_SECURE=True`
   - `DJANGO_ALLOWED_HOSTS=<your-domain>`
   - `DJANGO_CSRF_TRUSTED_ORIGINS=https://<your-domain>`
   - A fresh `DJANGO_SECRET_KEY`
   - `RESEND_API_KEY` — production sends real email
   - `CLOUDFLARE_TUNNEL_SECRET` — from the Cloudflare Tunnel setup
4. Build and start:
   ```bash
   docker compose up -d
   ```
5. Create the first superuser:
   ```bash
   docker compose exec -it web python manage.py createsuperuser
   ```

## Redeploy

```bash
cd /srv/storage/work_schedule/app
git pull
cd ..
docker compose build web
docker compose up -d
docker compose logs -f web
```

Watch the startup log until `Listening at: http://0.0.0.0:8000`. The
`entrypoint.sh` runs `migrate`, `collectstatic`, and starts Gunicorn
in sequence — if either step fails, the container exits and the log
shows why.

Verify after startup:

```bash
docker compose exec web python manage.py check --deploy
curl -i http://localhost:8000/healthz/
```

`check --deploy` should be clean — every `SECURE_*` warning is
addressed by the `DJANGO_SECURE` gate in `settings.py`. `/healthz/`
should return 200.

## Rollback

```bash
cd /srv/storage/work_schedule/app
git log --oneline -5
git checkout <previous-commit>
cd ..
docker compose build web
docker compose up -d
```

If the rollback commit predates a migration, the container will fail
to start — the database still has the newer migration applied and
Django's `migrate` won't reverse it automatically. In that case,
either roll forward to a commit whose migrations match the schema, or
restore the most recent backup and start over. Backups make this
recoverable, not free — roll forward when possible.

## Services

| Service       | Purpose                                                                    |
| ------------- | -------------------------------------------------------------------------- |
| `db`          | PostgreSQL 18. Data in a named volume `postgres_data`.                     |
| `redis`       | Redis 7 for sessions and OTP. Data in `redis_data`.                        |
| `web`         | Gunicorn + Django. Built from `app/Dockerfile`.                            |
| `cloudflared` | Cloudflare Tunnel connector. Reads `CLOUDFLARE_TUNNEL_SECRET` from `.env`. |

The `db` and `redis` volumes are the only persistent state. The `web`
container is stateless — `docker compose build web && docker compose
up -d` is always safe for it. Removing volumes is never safe.

## Backups

Local and offsite backups run nightly via a systemd timer on the
server. Two destinations, same retention policy.

- **Local:** `/srv/storage/work_schedule/backups/` — 30-day retention.
- **Offsite:** Backblaze B2, encrypted client-side via `rclone crypt`.
- **Retention:** 30 days both places.

The backup script runs `pg_dump` inside the `db` container, gzips the
result, and pipes it through rclone for the offsite copy.

### Manual run

```bash
sudo systemctl start work-schedule-backup.service
sudo journalctl -u work-schedule-backup.service -n 20 --no-pager
```

### Verifying offsite backups exist

```bash
sudo rclone ls b2-workschedule-crypt:
```

Should show one file per day, going back 30 days. If it shows fewer,
check the timer (`systemctl status work-schedule-backup.timer`) and
the journal.

### Crypt key custody

The rclone crypt passphrases must be stored somewhere durable and off
the server — a password manager entry, a printed copy in a safe,
whatever works for you. **Losing them means the offsite backups are
unrecoverable.** Local backups don't need the crypt keys (they're not
encrypted) but local only covers 30 days and lives on the same disk
as the database.

## Deployment caveats

Facts that matter when touching `settings.py` or the proxy config.
Full context in `docs/design/CSP_PLAN.md` under "Deployment caveats."

- **HSTS is one-way in practice.** Browsers cache the
  `Strict-Transport-Security` header for the configured duration. The
  current config is at `SECURE_HSTS_SECONDS = 31536000`, confirmed
  stable. Don't enable `SECURE_HSTS_PRELOAD` unless committed to
  HTTPS forever.
- **`SECURE_SSL_REDIRECT` in dev** breaks local HTTP testing. The
  code gates this on `DJANGO_SECURE` — not on `not DEBUG`. Keep it
  that way.
- **`SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`**
  requires the reverse proxy to send `X-Forwarded-Proto: https`.
  Cloudflare Tunnel does this correctly — verified in prod.
- **`check --deploy` should be clean.** If you add a new `SECURE_*`
  warning, address it in `settings.py` (gated on `DJANGO_SECURE`),
  not by suppressing the warning.

## Related docs

- `docs/STAGING.md` — staging environment setup (tunnel, access,
  isolated data). The staging counterpart to this file.
- `docs/design/CSP_PLAN.md` — deferred CSP branch plan, including
  deployment caveats around HSTS, `SECURE_PROXY_SSL_HEADER`, and CSP
  enforcement. Read this before touching `SECURE_*` flags.
- `README.md` — project overview. No deployment content there;
  everything deployment-related lives here or in `STAGING.md`.