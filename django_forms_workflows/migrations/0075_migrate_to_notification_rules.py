"""
Data migration: populate NotificationRule from the three legacy sources.

1. WorkflowNotification  → NotificationRule (stage=null)
2. StageFormFieldNotification → NotificationRule (stage=notif.stage)
3. WorkflowStage.notify_assignee_on_final_decision=True
     → two NotificationRule records (workflow_approved + workflow_denied)
       with notify_stage_assignees=True, scoped to that stage.

Event name mapping (old → new):
  approval_notification  → workflow_approved
  rejection_notification → workflow_denied
  withdrawal_notification → form_withdrawn
  submission_received    → submission_received  (unchanged)
  approval_request       → approval_request     (unchanged)
"""

from django.db import migrations


EVENT_MAP = {
    "approval_notification": "workflow_approved",
    "rejection_notification": "workflow_denied",
    "withdrawal_notification": "form_withdrawn",
    "submission_received": "submission_received",
    "approval_request": "approval_request",
}


def forwards(apps, schema_editor):
    NotificationRule = apps.get_model("django_forms_workflows", "NotificationRule")
    WorkflowNotification = apps.get_model(
        "django_forms_workflows", "WorkflowNotification"
    )
    StageFormFieldNotification = apps.get_model(
        "django_forms_workflows", "StageFormFieldNotification"
    )
    WorkflowStage = apps.get_model("django_forms_workflows", "WorkflowStage")

    # 1. WorkflowNotification → NotificationRule (workflow-scoped)
    for wn in WorkflowNotification.objects.all():
        NotificationRule.objects.create(
            workflow_id=wn.workflow_id,
            stage=None,
            event=EVENT_MAP.get(wn.notification_type, wn.notification_type),
            conditions=wn.conditions,
            subject_template=wn.subject_template or "",
            notify_submitter=wn.notify_submitter,
            email_field=wn.email_field or "",
            static_emails=wn.static_emails or "",
            notify_stage_assignees=False,
            notify_stage_groups=False,
        )

    # 2. StageFormFieldNotification → NotificationRule (stage-scoped)
    for sfn in StageFormFieldNotification.objects.select_related("stage").all():
        NotificationRule.objects.create(
            workflow_id=sfn.stage.workflow_id,
            stage_id=sfn.stage_id,
            event=EVENT_MAP.get(sfn.notification_type, sfn.notification_type),
            conditions=sfn.conditions,
            subject_template=sfn.subject_template or "",
            notify_submitter=False,
            email_field=sfn.email_field or "",
            static_emails=sfn.static_emails or "",
            notify_stage_assignees=False,
            notify_stage_groups=False,
        )

    # 3. WorkflowStage.notify_assignee_on_final_decision → two rules
    for stage in WorkflowStage.objects.filter(
        notify_assignee_on_final_decision=True
    ):
        for event in ("workflow_approved", "workflow_denied"):
            NotificationRule.objects.create(
                workflow_id=stage.workflow_id,
                stage_id=stage.id,
                event=event,
                conditions=None,
                subject_template="",
                notify_submitter=False,
                email_field="",
                static_emails="",
                notify_stage_assignees=True,
                notify_stage_groups=False,
            )


class Migration(migrations.Migration):

    dependencies = [
        ("django_forms_workflows", "0074_add_notification_rule"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]

