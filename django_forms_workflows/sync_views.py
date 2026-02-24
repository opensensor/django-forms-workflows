"""
Sync HTTP API views.

GET  /forms-sync/export/
    Returns a JSON payload of serialized form definitions.
    Optional query param: ?slugs=slug1,slug2  (comma-separated; omit to export all)
    Requires: Authorization: Bearer <FORMS_SYNC_API_TOKEN>

POST /forms-sync/import/
    Accepts a JSON payload (as produced by the export endpoint) and imports forms.
    Optional query param: ?conflict=update|skip|new_slug  (default: update)
    Requires: Authorization: Bearer <FORMS_SYNC_API_TOKEN>
"""

import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import FormDefinition
from .sync_api import build_export_payload, import_payload, verify_sync_token

logger = logging.getLogger(__name__)

_UNAUTHORIZED = JsonResponse(
    {
        "error": "Unauthorized. Provide a valid Bearer token via the Authorization header."
    },
    status=401,
)
_DISABLED = JsonResponse(
    {"error": "Sync API is disabled. Set FORMS_SYNC_API_TOKEN in Django settings."},
    status=403,
)


@require_GET
def sync_export_view(request):
    """
    Export form definitions as JSON.

    GET /forms-sync/export/
    GET /forms-sync/export/?slugs=slug1,slug2
    """
    if not verify_sync_token(request):
        from .sync_api import get_sync_token

        return _DISABLED if not get_sync_token() else _UNAUTHORIZED

    slugs_param = request.GET.get("slugs", "").strip()
    if slugs_param:
        slugs = [s.strip() for s in slugs_param.split(",") if s.strip()]
        qs = FormDefinition.objects.filter(slug__in=slugs)
    else:
        qs = FormDefinition.objects.all()

    payload = build_export_payload(qs)
    return JsonResponse(payload, json_dumps_params={"indent": 2})


@csrf_exempt
@require_POST
def sync_import_view(request):
    """
    Import form definitions from a JSON payload.

    POST /forms-sync/import/
    POST /forms-sync/import/?conflict=skip
    """
    if not verify_sync_token(request):
        from .sync_api import get_sync_token

        return _DISABLED if not get_sync_token() else _UNAUTHORIZED

    conflict = request.GET.get("conflict", "update")
    if conflict not in ("update", "skip", "new_slug"):
        return JsonResponse(
            {
                "error": f"Invalid conflict mode '{conflict}'. Use update, skip, or new_slug."
            },
            status=400,
        )

    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return JsonResponse({"error": f"Invalid JSON: {exc}"}, status=400)

    try:
        results = import_payload(payload, conflict=conflict)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Sync import failed")
        return JsonResponse({"error": str(exc)}, status=500)

    summary = [
        {"slug": form_obj.slug, "action": action} for form_obj, action in results
    ]
    counts = {"created": 0, "updated": 0, "skipped": 0}
    for _, action in results:
        counts[action] = counts.get(action, 0) + 1

    return JsonResponse(
        {
            "imported": len(results),
            "counts": counts,
            "forms": summary,
        }
    )
