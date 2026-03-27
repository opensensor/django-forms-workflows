"""
Data migration: convert legacy notify_on_* flags on WorkflowDefinition into
granular WorkflowNotification rows with notify_submitter=True.

For each WorkflowDefinition we create up to four WorkflowNotification rows —
one per enabled legacy flag. Any additional_notify_emails are copied to
static_emails on the same row so existing CC behaviour is preserved.

Rows are only created if no WorkflowNotification of that type already exists
for the workflow, keeping the migration idempotent.
"""

from django.db import migrations

FLAG_MAP = [
    ("notify_on_submission", "submission_received"),
    ("notify_on_approval", "approval_notification"),
    ("notify_on_rejection", "rejection_notification"),
    ("notify_on_withdrawal", "withdrawal_notification"),
]


def convert_legacy_flags(apps, schema_editor):
    WorkflowDefinition = apps.get_model("django_forms_workflows", "WorkflowDefinition")
    WorkflowNotification = apps.get_model("django_forms_workflows", "WorkflowNotification")

    for workflow in WorkflowDefinition.objects.all():
        static_emails = (workflow.additional_notify_emails or "").strip()
        existing_types = set(
            WorkflowNotification.objects.filter(workflow=workflow).values_list(
                "notification_type", flat=True
            )
        )

        for flag_field, notification_type in FLAG_MAP:
            if not getattr(workflow, flag_field, False):
                continue
            if notification_type in existing_types:
                # Already configured via the new system — skip to avoid duplicates.
                continue
            WorkflowNotification.objects.create(
                workflow=workflow,
                notification_type=notification_type,
                notify_submitter=True,
                static_emails=static_emails,
            )


def reverse_migration(apps, schema_editor):
    """
    Reverse: remove WorkflowNotification rows that were created by this migration
    (identified by notify_submitter=True and no email_field set).
    We cannot distinguish them from manually-created rows with the same pattern,
    so we only remove rows that have notify_submitter=True and no email_field.
    """
    WorkflowNotification = apps.get_model("django_forms_workflows", "WorkflowNotification")
    WorkflowNotification.objects.filter(notify_submitter=True, email_field="").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("django_forms_workflows", "0066_add_notify_submitter_to_workflownotification"),
    ]

    operations = [
        migrations.RunPython(convert_legacy_flags, reverse_migration),
    ]

