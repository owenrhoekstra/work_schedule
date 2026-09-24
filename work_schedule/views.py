from django.db import connection
from django.http import HttpResponse, HttpResponseServerError


def healthz(request):
    """Liveness/readiness probe. Returns 200 if the app and DB are up."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return HttpResponseServerError("db unavailable", content_type="text/plain")
    return HttpResponse("ok", content_type="text/plain")
