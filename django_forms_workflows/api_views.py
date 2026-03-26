"""
REST API views for Django Forms Workflows.

Opt-in feature — only active when the caller includes these URLs:

    # urls.py
    path("api/", include("django_forms_workflows.api_urls")),

Authentication
--------------
All endpoints except /api/docs/ and /api/schema/ require a Bearer token::

    Authorization: Bearer <APIToken.token>

Tokens are created in Django Admin → API Tokens.
Only forms with ``api_enabled=True`` are exposed.

Schema / docs
-------------
GET /api/schema/  — OpenAPI 3.0 JSON (staff only, session or basic auth)
GET /api/docs/    — Swagger UI (staff only)

Submission endpoints
--------------------
GET  /api/forms/                   — list api-enabled forms the token user may submit
GET  /api/forms/<slug>/            — field schema for one form
POST /api/forms/<slug>/submit/     — submit (JSON or multipart/form-data)
                                     ?draft=1 saves as draft instead of submitting
GET  /api/submissions/<id>/        — poll status of a submission
"""

import json
import logging
from functools import wraps

from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from .forms import DynamicForm
from .models import APIToken, AuditLog, FormDefinition, FormSubmission
from .utils import user_can_submit_form, user_can_view_form
from .views import (
    _re_evaluate_calculated_fields,
    create_approval_tasks,
    get_client_ip,
    serialize_form_data,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OpenAPI field-type → JSON Schema mapping
# ---------------------------------------------------------------------------

_FIELD_SCHEMA: dict[str, dict] = {
    "text": {"type": "string"},
    "phone": {"type": "string"},
    "textarea": {"type": "string"},
    "number": {"type": "integer"},
    "decimal": {"type": "number", "format": "float"},
    "currency": {"type": "number", "format": "float"},
    "date": {"type": "string", "format": "date"},
    "datetime": {"type": "string", "format": "date-time"},
    "time": {"type": "string"},
    "email": {"type": "string", "format": "email"},
    "url": {"type": "string", "format": "uri"},
    "select": {"type": "string"},
    "multiselect": {"type": "array", "items": {"type": "string"}},
    "multiselect_list": {"type": "array", "items": {"type": "string"}},
    "radio": {"type": "string"},
    "checkbox": {"type": "boolean"},
    "checkboxes": {"type": "array", "items": {"type": "string"}},
    "file": {"type": "string", "format": "binary"},
    "multifile": {"type": "array", "items": {"type": "string", "format": "binary"}},
    "hidden": {"type": "string"},
    "calculated": {"type": "string", "readOnly": True},
    "spreadsheet": {"type": "string", "format": "binary"},
    "country": {"type": "string"},
    "us_state": {"type": "string"},
}

_FILE_FIELD_TYPES = {"file", "multifile", "spreadsheet"}


# ---------------------------------------------------------------------------
# Auth decorator
# ---------------------------------------------------------------------------


def require_api_token(view_func):
    """Authenticate via Bearer token; attaches request.api_user and request.api_token."""

    @wraps(view_func)
    @csrf_exempt
    def wrapper(request, *args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return JsonResponse(
                {"error": "Authorization required. Use: Authorization: Bearer <token>"},
                status=401,
            )
        raw = auth.removeprefix("Bearer ").strip()
        try:
            token_obj = APIToken.objects.select_related("user").get(
                token=raw, is_active=True
            )
        except (APIToken.DoesNotExist, ValueError, Exception):  # noqa: BLE001
            return JsonResponse({"error": "Invalid or inactive token."}, status=401)

        # Bump last_used_at without loading the full object again
        APIToken.objects.filter(pk=token_obj.pk).update(last_used_at=timezone.now())
        request.api_user = token_obj.user
        request.api_token = token_obj
        return view_func(request, *args, **kwargs)

    return wrapper


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _api_form_queryset(user):
    """Forms that are active, api_enabled, and visible to this user."""
    qs = FormDefinition.objects.filter(is_active=True, api_enabled=True)
    # Filter further by view_groups if the form has restrictions
    accessible = [f for f in qs if user_can_view_form(user, f)]
    return accessible


def _field_schema(field) -> dict:
    """Return an OpenAPI property dict for a single FormField."""
    base = dict(_FIELD_SCHEMA.get(field.field_type, {"type": "string"}))
    if field.help_text:
        base["description"] = field.help_text
    if field.choices:
        choices = field.choices
        if isinstance(choices, str):
            choices = [c.strip() for c in choices.split(",") if c.strip()]
        values = [c["value"] if isinstance(c, dict) else c for c in choices]
        if field.field_type in ("multiselect", "multiselect_list", "checkboxes"):
            base.setdefault("items", {})["enum"] = values
        else:
            base["enum"] = values
    if field.field_type == "calculated":
        base["readOnly"] = True
    return base


def _form_openapi_path(form, base_url: str) -> dict:
    """Build OpenAPI path item for a single form's submit endpoint."""
    fields = form.fields.exclude(field_type="section").order_by("order")
    required_names = [
        f.field_name for f in fields if f.required and f.field_type != "calculated"
    ]
    has_file = fields.filter(field_type__in=_FILE_FIELD_TYPES).exists()

    properties = {
        f.field_name: _field_schema(f) for f in fields if f.field_type != "section"
    }

    json_schema = {
        "type": "object",
        "properties": properties,
        "required": required_names,
    }

    if has_file:
        content = {"multipart/form-data": {"schema": json_schema}}
    else:
        content = {
            "application/json": {"schema": json_schema},
            "multipart/form-data": {"schema": json_schema},
        }

    return {
        "post": {
            "summary": f"Submit: {form.name}",
            "description": form.description or "",
            "tags": [form.category.name if form.category else "Forms"],
            "parameters": [
                {
                    "name": "draft",
                    "in": "query",
                    "required": False,
                    "schema": {"type": "integer", "enum": [0, 1]},
                    "description": "Set to 1 to save as draft instead of submitting.",
                }
            ],
            "requestBody": {"required": True, "content": content},
            "responses": {
                "201": {"description": "Submission created successfully."},
                "400": {"description": "Validation errors."},
                "401": {"description": "Missing or invalid Bearer token."},
                "403": {"description": "Permission denied."},
                "404": {"description": "Form not found or not API-enabled."},
            },
            "security": [{"bearerAuth": []}],
        }
    }


def _build_openapi_spec(request) -> dict:
    """Generate a complete OpenAPI 3.0.3 document from api_enabled FormDefinitions."""
    base_url = request.build_absolute_uri("/").rstrip("/")
    paths = {}
    forms = FormDefinition.objects.filter(
        is_active=True, api_enabled=True
    ).prefetch_related("fields", "category")
    for form in forms:
        path_key = f"/api/forms/{form.slug}/submit/"
        paths[path_key] = _form_openapi_path(form, base_url)

    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Forms Workflows API",
            "version": "1.0.0",
            "description": (
                "REST API for submitting and tracking forms managed by "
                "Django Forms Workflows. Only forms with **api_enabled=True** appear here. "
                "Authenticate with `Authorization: Bearer <token>` on all endpoints "
                "except /api/schema/ and /api/docs/ (which require Django staff session)."
            ),
        },
        "servers": [{"url": base_url}],
        "components": {
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "UUID",
                    "description": "API token created in Django Admin → API Tokens.",
                }
            }
        },
        "paths": paths,
    }


def _parse_request_data(request):
    """
    Return (data_dict, files_dict) suitable for passing to DynamicForm.

    Handles both ``application/json`` and ``multipart/form-data`` request bodies.
    For JSON, multi-value fields (arrays) are preserved as lists.
    """
    ct = request.content_type or ""
    if "multipart/form-data" in ct or "application/x-www-form-urlencoded" in ct:
        return request.POST, request.FILES

    # JSON body → plain dict
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, None

    if not isinstance(body, dict):
        return None, None

    return body, {}


# ---------------------------------------------------------------------------
# Schema / docs views (staff-only, session auth)
# ---------------------------------------------------------------------------


@staff_member_required
@require_GET
def api_schema_view(request):
    """GET /api/schema/ — OpenAPI 3.0 JSON spec. Requires Django staff session."""
    spec = _build_openapi_spec(request)
    return JsonResponse(spec, json_dumps_params={"indent": 2})


@staff_member_required
def api_docs_view(request):
    """GET /api/docs/ — Swagger UI. Requires Django staff session."""
    from django.shortcuts import render

    # Use a root-relative URL so the browser inherits the page's scheme
    # (avoids mixed-content errors when Django sits behind a TLS-terminating proxy).
    schema_url = "/api/schema/"
    return render(
        request, "django_forms_workflows/api/docs.html", {"schema_url": schema_url}
    )


# ---------------------------------------------------------------------------
# Token-authenticated endpoints
# ---------------------------------------------------------------------------


@require_api_token
@require_GET
def api_form_list_view(request):
    """GET /api/forms/ — list api_enabled forms the token user can view."""
    forms = _api_form_queryset(request.api_user)
    return JsonResponse(
        {
            "count": len(forms),
            "forms": [
                {
                    "slug": f.slug,
                    "name": f.name,
                    "description": f.description,
                    "category": f.category.name if f.category else None,
                    "allow_draft": f.allow_save_draft,
                    "submit_url": request.build_absolute_uri(
                        f"/api/forms/{f.slug}/submit/"
                    ),
                }
                for f in forms
            ],
        }
    )


@require_api_token
@require_GET
def api_form_detail_view(request, slug):
    """GET /api/forms/<slug>/ — field definitions for one form."""
    form_def = get_object_or_404(
        FormDefinition, slug=slug, is_active=True, api_enabled=True
    )
    if not user_can_view_form(request.api_user, form_def):
        return JsonResponse({"error": "Permission denied."}, status=403)

    fields = form_def.fields.exclude(field_type="section").order_by("order")
    return JsonResponse(
        {
            "slug": form_def.slug,
            "name": form_def.name,
            "description": form_def.description,
            "allow_draft": form_def.allow_save_draft,
            "fields": [
                {
                    "name": f.field_name,
                    "label": f.field_label,
                    "type": f.field_type,
                    "required": f.required,
                    "readonly": f.readonly,
                    "help_text": f.help_text,
                    "schema": _field_schema(f),
                }
                for f in fields
            ],
        }
    )


@require_api_token
@csrf_exempt
def api_form_submit_view(request, slug):
    """
    POST /api/forms/<slug>/submit/

    Accepts ``application/json`` or ``multipart/form-data``.
    Add ``?draft=1`` to save as a draft instead of submitting.

    Runs the identical validation pipeline as the browser UX view:
    DynamicForm → serialize_form_data → _re_evaluate_calculated_fields
    → FormSubmission.save → create_approval_tasks.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed. Use POST."}, status=405)

    form_def = get_object_or_404(
        FormDefinition, slug=slug, is_active=True, api_enabled=True
    )

    if not user_can_view_form(request.api_user, form_def):
        return JsonResponse({"error": "Permission denied."}, status=403)
    if not user_can_submit_form(request.api_user, form_def):
        return JsonResponse(
            {"error": "You do not have permission to submit this form."}, status=403
        )

    is_draft = request.GET.get("draft") == "1"
    if is_draft and not form_def.allow_save_draft:
        return JsonResponse(
            {"error": "Draft saving is not enabled for this form."}, status=400
        )

    data, files = _parse_request_data(request)
    if data is None:
        return JsonResponse(
            {"error": "Invalid or unparseable request body."}, status=400
        )

    # Reuse an existing draft if one exists for this user/form
    existing_draft = FormSubmission.objects.filter(
        form_definition=form_def, submitter=request.api_user, status="draft"
    ).first()

    form = DynamicForm(
        form_definition=form_def,
        user=request.api_user,
        data=data,
        files=files or {},
    )

    if not form.is_valid():
        return JsonResponse({"errors": form.errors}, status=400)

    submission = existing_draft or FormSubmission(
        form_definition=form_def,
        submitter=request.api_user,
        submission_ip=get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "API"),
    )
    if not submission.pk:
        submission.form_data = {}
        submission.save()

    submission.form_data = serialize_form_data(
        form.cleaned_data, submission_id=submission.pk
    )
    submission.form_data = _re_evaluate_calculated_fields(
        submission.form_data, form_def
    )

    if is_draft:
        submission.status = "draft"
        submission.save()
        AuditLog.objects.create(
            action="update" if existing_draft else "create",
            object_type="FormSubmission",
            object_id=submission.id,
            user=request.api_user,
            user_ip=get_client_ip(request),
            comments="Saved as draft via API",
        )
        return JsonResponse(
            {"id": submission.id, "status": "draft", "message": "Draft saved."},
            status=201,
        )

    submission.status = "submitted"
    submission.submitted_at = timezone.now()
    submission.save()
    AuditLog.objects.create(
        action="submit",
        object_type="FormSubmission",
        object_id=submission.id,
        user=request.api_user,
        user_ip=get_client_ip(request),
        comments="Submitted via API",
    )
    create_approval_tasks(submission)

    return JsonResponse(
        {
            "id": submission.id,
            "status": submission.status,
            "message": "Form submitted successfully.",
            "status_url": request.build_absolute_uri(
                f"/api/submissions/{submission.id}/"
            ),
        },
        status=201,
    )


@require_api_token
@require_GET
def api_submission_status_view(request, submission_id):
    """GET /api/submissions/<id>/ — poll status and approval task summary."""
    submission = get_object_or_404(
        FormSubmission, id=submission_id, submitter=request.api_user
    )

    tasks = [
        {
            "id": t.id,
            "stage": t.step_name,
            "status": t.status,
            "assigned_group": t.assigned_group.name if t.assigned_group else None,
            "assigned_to": t.assigned_to.get_full_name() if t.assigned_to else None,
            "due_date": t.due_date.isoformat() if t.due_date else None,
        }
        for t in submission.approval_tasks.select_related(
            "assigned_group", "assigned_to"
        ).order_by("stage_number", "id")
    ]

    return JsonResponse(
        {
            "id": submission.id,
            "form": submission.form_definition.slug,
            "status": submission.status,
            "submitted_at": submission.submitted_at.isoformat()
            if submission.submitted_at
            else None,
            "approval_tasks": tasks,
        }
    )
