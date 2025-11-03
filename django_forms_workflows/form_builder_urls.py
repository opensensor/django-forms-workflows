"""
URL Configuration for Visual Form Builder

These URLs are meant to be included in the Django admin site.
"""

from django.urls import path

from . import form_builder_views

app_name = "form_builder"

urlpatterns = [
    # Main builder view
    path("new/", form_builder_views.form_builder_view, name="builder_new"),
    path("<int:form_id>/", form_builder_views.form_builder_view, name="builder_edit"),
    # API endpoints
    path(
        "api/load/<int:form_id>/", form_builder_views.form_builder_load, name="api_load"
    ),
    path("api/save/", form_builder_views.form_builder_save, name="api_save"),
    path("api/preview/", form_builder_views.form_builder_preview, name="api_preview"),
]
