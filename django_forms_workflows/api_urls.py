"""
URL patterns for the optional REST API.

Include these in your project's urls.py to activate the API::

    from django.urls import include, path

    urlpatterns = [
        ...
        path("api/", include("django_forms_workflows.api_urls")),
    ]

Endpoints
---------
GET  /api/docs/                    Swagger UI  (staff session required)
GET  /api/schema/                  OpenAPI 3.0 JSON  (staff session required)
GET  /api/forms/                   List api_enabled forms  (Bearer token)
GET  /api/forms/<slug>/            Field schema for one form  (Bearer token)
POST /api/forms/<slug>/submit/     Submit a form  (Bearer token)
GET  /api/submissions/<id>/        Poll submission status  (Bearer token)
"""

from django.urls import path

from .api_views import (
    api_docs_view,
    api_form_detail_view,
    api_form_list_view,
    api_form_submit_view,
    api_schema_view,
    api_submission_status_view,
)

app_name = "forms_workflows_api"

urlpatterns = [
    # Documentation (staff-only, Django session auth)
    path("docs/", api_docs_view, name="docs"),
    path("schema/", api_schema_view, name="schema"),
    # Form discovery and field schema (Bearer token)
    path("forms/", api_form_list_view, name="form_list"),
    path("forms/<slug:slug>/", api_form_detail_view, name="form_detail"),
    path("forms/<slug:slug>/submit/", api_form_submit_view, name="form_submit"),
    # Submission status (Bearer token)
    path(
        "submissions/<int:submission_id>/",
        api_submission_status_view,
        name="submission_status",
    ),
]
