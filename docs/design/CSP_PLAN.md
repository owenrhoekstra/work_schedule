# Content Security Policy — deferred branch plan

Working draft for the CSP branch. Pulled out of `SECURITY_SWEEP.md`
at that branch's close so the plan survives without keeping the full
sweep record alive.

CSP was investigated during Session 10 (security sweep) and
deliberately deferred. This file captures the policy draft, the
reason for deferring, and the Phase 2 requirements so a future branch
doesn't re-derive them.

---

## Why deferred

Phase 1 with `'unsafe-inline'` doesn't block the inline-script XSS
surface this app actually has:

- Alpine `x-data` / `x-effect` / `x-init` attributes throughout
- Inline `onclick=` handlers (the Pattern B modal idiom)
- Seven inline `<script>` blocks in modals/partials

Phase 1 only blocks external-script injection, which Django's
autoescape already makes hard. Phase 2 (nonces + Alpine CSP build)
is the meaningful version and is a session of its own — Alpine 3's
default build uses `new Function()` internally, which CSP blocks
outright, so switching to nonces requires the CSP-compatible Alpine
build and rewriting every `x-data` component.

Shipping Phase 1 alone would add template noise (a policy header, a
middleware, QA overhead) for a marginal security gain. Not worth it.

---

## Policy — Phase 1 draft

```
Content-Security-Policy:
  default-src 'self';
  script-src 'self' 'unsafe-inline';
  style-src 'self' 'unsafe-inline' https://fonts.googleapis.com;
  font-src 'self' https://fonts.gstatic.com;
  img-src 'self' data:;
  connect-src 'self';
  frame-ancestors 'none';
  base-uri 'self';
  form-action 'self';
```

### Justifications per directive

- **`script-src 'unsafe-inline'`** — Alpine `x-data` / `x-effect` /
  `x-init` attributes and every HTMX-fragment `<script>` block
  (`_page_state.html`, `_pattern_form_body.html`, `_saved_patterns.html`,
  the modal scripts). Phase 2 will convert these to nonces.
- **`style-src 'unsafe-inline'`** — Tailwind's `@starting-style` in
  `base.html`, Alpine `:class` transitions, and any inline
  `style="..."` attributes.
- **`fonts.googleapis.com` / `fonts.gstatic.com`** — the
  `@import url(...)` at the top of `styles.css` (served same-origin
  but loads CSS from googleapis) and the Space Grotesk / Inter font
  files from gstatic.
- **`frame-ancestors 'none'`** — overlaps with `X-Frame-Options: DENY`
  (already set). Defense in depth; both are harmless together.
- **No `report-uri` on day one.** Deploy enforce mode, watch the
  browser console manually for `Content-Security-Policy` blocks during
  QA. If something breaks, temporarily switch to
  `Content-Security-Policy-Report-Only` while iterating.

---

## Phase 2 — nonces

The meaningful version. Requires:

1. **Per-request nonce middleware.** Generates a random nonce, stores
   it on `request.csp_nonce`, adds it to the `Content-Security-Policy`
   header's `script-src` (replacing `'unsafe-inline'`).
2. **`nonce="{{ request.csp_nonce }}"` on every inline `<script>`**
   across ~10 partials. Any inline script without the nonce gets
   blocked — the browser console will surface the misses during QA.
3. **Alpine's CSP build** (`@alpinejs/csp`). Alpine 3's default build
   uses `new Function()` internally for expression evaluation, which
   `script-src` blocks. The CSP build compiles expressions at init
   time instead of eval time. Switching means rewriting every
   `x-data="{ ... }"` to the CSP-compatible form — the biggest single
   chunk of work in this branch.

Estimated as a session of its own. Not warranted until the app's
inline-script surface actually justifies the effort (i.e. if user-
generated content ever renders into templates, or if third-party
script embedding becomes a requirement).

---

## Deployment caveats

Facts that bite anyone touching CSP, HSTS, or proxy settings. Some of
these will eventually migrate to `AGENTS.md` under "Settings you'll
reach for" — until that section covers them, they live here.

- **HSTS is one-way in practice.** Browsers cache the
  `Strict-Transport-Security` header for the configured duration.
  Current config at `SECURE_HSTS_SECONDS = 31536000`, confirmed
  stable. Do not enable `SECURE_HSTS_PRELOAD` unless committed to
  HTTPS forever.
- **`SECURE_SSL_REDIRECT` in dev** breaks local HTTP testing. The
  code gates this on `DJANGO_SECURE` (not on `not DEBUG`) — see
  `settings.py`.
- **`SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`**
  requires the reverse proxy to send `X-Forwarded-Proto: https`.
  Cloudflare Tunnel does this correctly (verified in prod).
- **CSP enforce mode ships hot.** If a template conditionally loads
  an external resource you forgot to allowlist, users see a broken
  page. First-hour monitoring matters when the CSP branch ships.
  Have a one-line rollback ready (comment out the middleware).

---

## Related docs

- `docs/design/SESSIONS.md` — Session 10 (security sweep) item 12
  records the decision to defer; Session 10 items 10–15 record the
  surrounding work.
- `docs/worklog/BUGREPORT.md` and `docs/worklog/FIXED.md` — cleared
  at each branch's merge; the reason this plan and the deployment
  caveats live in a persistent file rather than the sweep record.