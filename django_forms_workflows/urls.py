from django.urls import path

from . import views

app_name = "forms_workflows"

urlpatterns = [
    # Form list and submission
    path("", views.form_list, name="form_list"),
    path("<slug:slug>/submit/", views.form_submit, name="form_submit"),
    path("<slug:slug>/auto-save/", views.form_auto_save, name="form_auto_save"),
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
    # Approvals
    path("approvals/", views.approval_inbox, name="approval_inbox"),
    path(
        "approvals/<int:task_id>/approve/",
        views.approve_submission,
        name="approve_submission",
    ),
]
