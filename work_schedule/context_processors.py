"""Project-wide template context.

Exposes the app's brand name from settings so templates don't hardcode
"Work Schedule". Set APP_NAME in the environment to rebrand.
"""

from django.conf import settings


def app_name(request):
    return {"app_name": settings.APP_NAME}