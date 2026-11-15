"""NinjaAPI instance for /api/v1/.

The `docs_decorator=staff_member_required` gates both /docs and
/openapi.json on `is_staff`. That is the platform-admin signal per
AGENTS.md — it does not imply company admin, and the docs are an
internal tool, not a tenant-facing surface.

CSRF note: endpoints that must be public (login) use an auth class
that returns True for anonymous users — NOT `auth=None`. django-ninja
marks `auth=None` endpoints as `csrf_exempt`, which would disable
Django's CsrfViewMiddleware. A truthy auth keeps CSRF enforcement
intact.
"""

from django.contrib.admin.views.decorators import staff_member_required
from ninja import NinjaAPI

api = NinjaAPI(
    version="1",
    title="Docket API",
    description="Programmatic access to Docket.",
    docs_url="/docs",
    openapi_url="/openapi.json",
    docs_decorator=staff_member_required,
)
