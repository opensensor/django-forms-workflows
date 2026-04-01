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
    # Document template API endpoints
    path(
        "api/doc-templates/<int:form_id>/",
        form_builder_views.document_template_list,
        name="api_doc_templates",
    ),
    path(
        "api/doc-templates/<int:form_id>/save/",
        form_builder_views.document_template_save,
        name="api_doc_template_save",
    ),
    path(
        "api/doc-templates/<int:form_id>/delete/<int:template_id>/",
        form_builder_views.document_template_delete,
        name="api_doc_template_delete",
    ),
]
