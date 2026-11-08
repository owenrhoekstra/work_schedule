# Staging environment

Parallel stack on the same host as production. Isolated data,
isolated tunnel, isolated Cloudflare Access.

## Shape

- **Host:** same server as prod, `/srv/storage/work_schedule-staging`
- **Branch:** `staging` (prod tracks `main`)
- **Domain:** `staging.work-schedule.principiasystems.ca`
- **Tunnel:** dedicated Cloudflare Tunnel (`work-schedule-staging`)
- **Access:** Cloudflare Access, one-time-PIN via your email
- **Data:** separate Postgres + Redis containers. No shared volumes,
  no shared DB, no shared Redis keys.
- **Email:** Mailpit — every outbound email is caught in the Mailpit
  container. Resend is never called from staging.
- **Debug:** `DJANGO_DEBUG=false` — staging mirrors prod behavior.
  Errors surface through container logs, not Django's debug pages.

## Branch flow

- feature branch → staging (deploy to staging env)
- → verify
- → staging → main (deploy to prod env)

- Prod only ever sees commits that have run on staging first.

## First-time setup

### 1. Create the staging Cloudflare Tunnel

Cloudflare dashboard → Zero Trust → Networks → Tunnels → Create a
tunnel → name it `work-schedule-staging`.

Copy the token. Save it as `CLOUDFLARE_TUNNEL_SECRET_STAGING` in
`.env.staging` (see step 3).

### 2. Add the public hostname to the tunnel

In the tunnel config, add a Public Hostname:

- Subdomain: `staging.work-schedule`
- Domain: `principiasystems.ca`
- Service: `http://web:8000`

Cloudflare auto-creates the DNS CNAME.

### 3. Create the Cloudflare Access policy

Zero Trust → Access → Applications → Add an application → Self-hosted.

- Name: `Staging`
- Application domain: `staging.work-schedule.principiasystems.ca`
- Session duration: 24 hours

Add a policy:

- Action: Allow
- Include: Emails → your email address

Auth method: One-time PIN (email) is simplest. Google or GitHub also
work if you'd prefer.

### 4. Clone the repo alongside prod

```bash
cd /srv/storage
git clone <repo-url> work_schedule-staging
cd work_schedule-staging
git checkout staging    # creates and tracks origin/staging if it exists