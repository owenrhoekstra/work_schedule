"""Project-wide template context.

Exposes the app's brand name. Prefers `request.company.app_name` (per-
tenant branding, Branch 2) and falls back to `settings.APP_NAME` (env-
derived, single-tenant default).
"""

from django.conf import settings


def app_name(request):
    company = getattr(request, "company", None)
    if company and company.app_name:
        return {"app_name": company.app_name}
    return {"app_name": settings.APP_NAME}
