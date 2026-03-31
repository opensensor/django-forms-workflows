from django.urls import include, path

from . import views
from .reporting_views import analytics_dashboard
from .sso_backends import is_sso_available
from .sync_views import sync_export_view, sync_import_view

app_name = "forms_workflows"

urlpatterns = [
    # Form list and submission
    path("", views.form_list, name="form_list"),
    path("<slug:slug>/submit/", views.form_submit, name="form_submit"),
    path("<slug:slug>/auto-save/", views.form_auto_save, name="form_auto_save"),
    # Batch import
    path(
        "<slug:slug>/batch-template/",
        views.batch_template_download,
        name="batch_template_download",
    ),
    path(
        "<slug:slug>/batch-import/",
        views.batch_import_upload,
        name="batch_import_upload",
    ),
    # User submissions
    path("my-submissions/", views.my_submissions, name="my_submissions"),
    path(
        "submissions/<int:submission_id>/",
        views.submission_detail,
        name="submission_detail",
    ),
    path(
        "submissions/<int:submission_id>/withdraw/",
        views.withdraw_submission,
        name="withdraw_submission",
    ),
    path(
        "submissions/<int:submission_id>/discard/",
        views.discard_draft,
        name="discard_draft",
    ),
    path(
        "submissions/<int:submission_id>/resubmit/",
        views.resubmit_submission,
        name="resubmit_submission",
    ),
    path(
        "submissions/<int:submission_id>/pdf/",
        views.submission_pdf,
        name="submission_pdf",
    ),
    # Bulk export
    path(
        "submissions/bulk-export/",
        views.bulk_export_submissions,
        name="bulk_export_submissions",
    ),
    path(
        "submissions/bulk-export-pdf/",
        views.bulk_export_submissions_pdf,
        name="bulk_export_submissions_pdf",
    ),
    # Sync API
    path("forms-sync/export/", sync_export_view, name="sync_export"),
    path("forms-sync/import/", sync_import_view, name="sync_import"),
    # Sub-workflow instances
    path(
        "sub-workflows/<int:instance_id>/",
        views.sub_workflow_detail,
        name="sub_workflow_detail",
    ),
    # Approvals
    path("approvals/", views.approval_inbox, name="approval_inbox"),
    path("approvals/completed/", views.completed_approvals, name="completed_approvals"),
    path(
        "approvals/<int:task_id>/approve/",
        views.approve_submission,
        name="approve_submission",
    ),
    path(
        "approvals/<int:task_id>/reassign/",
        views.reassign_task,
        name="reassign_task",
    ),
    # Analytics dashboard
    path("analytics/", analytics_dashboard, name="analytics_dashboard"),
    # Server-side DataTables AJAX endpoints
    path("my-submissions/data/", views.my_submissions_ajax, name="my_submissions_ajax"),
    path("approvals/data/", views.approval_inbox_ajax, name="approval_inbox_ajax"),
    path(
        "approvals/completed/data/",
        views.completed_approvals_ajax,
        name="completed_approvals_ajax",
    ),
]

# Conditionally include SSO URLs if SSO dependencies are available
if is_sso_available():
    urlpatterns += [
        path("sso/", include("django_forms_workflows.sso_urls")),
    ]
