import os

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from django.db import connection
import redis



def health_check(request):
    checks = {}

    try:
        connection.ensure_connection()
        checks["db"] = "ok"
    except Exception as e:
        checks["db"] = f"error: {e}"

    try:
        r = redis.from_url(settings.REDIS_URL, socket_connect_timeout=2, ssl_cert_reqs=None)
        r.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"

    all_ok = all(v == "ok" for v in checks.values())
    return JsonResponse(
        {"status": "ok" if all_ok else "degraded", **checks},
        status=200 if all_ok else 503,
    )


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health_check, name="health_check"),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/classes/", include("apps.classes.urls")),
    path("api/materials/", include("apps.materials.urls")),
    path("api/activities/", include("apps.activities.urls")),
    path("api/games/", include("apps.games.urls")),
    path("api/analytics/", include("apps.analytics.urls")),
]

from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView  # noqa: E402


class GatedSwaggerView(SpectacularSwaggerView):
    """Expose Swagger UI only when DEBUG or ALLOW_API_DOCS is enabled."""

    def dispatch(self, request, *args, **kwargs):
        if not (settings.DEBUG or getattr(settings, "ALLOW_API_DOCS", False)):
            return JsonResponse({"detail": "Not found."}, status=404)
        return super().dispatch(request, *args, **kwargs)


urlpatterns += [
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", GatedSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# Serve media locally when S3 is not configured (DEBUG or local-only PaaS setups).
# With S3, files have their own public/signed URLs so this is not needed.
if not os.environ.get("AWS_STORAGE_BUCKET_NAME"):
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)