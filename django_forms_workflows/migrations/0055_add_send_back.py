"""
Migration 0055 – Send-Back for Correction feature.

Changes:
  * ApprovalTask.status – add "returned" choice (VARCHAR only, no constraint change).
  * WorkflowStage.allow_send_back – new BooleanField(default=False).
  * AuditLog.action – add "send_back" choice (VARCHAR only).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("django_forms_workflows", "0054_rename_approved_pending_to_pending_approval"),
    ]

    operations = [
        # WorkflowStage.allow_send_back
        migrations.AddField(
            model_name="workflowstage",
            name="allow_send_back",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Allow approvers at a later stage to return the submission to this "
                    "stage for correction, without terminating the workflow. When enabled, "
                    "this stage will appear as a 'Send Back' target option for all "
                    "subsequent stages."
                ),
            ),
        ),
        # ApprovalTask.status – extend choices to include "returned"
        migrations.AlterField(
            model_name="approvaltask",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("approved", "Approved"),
                    ("rejected", "Rejected"),
                    ("returned", "Returned for Correction"),
                    ("expired", "Expired"),
                    ("skipped", "Skipped"),
                ],
                default="pending",
                max_length=20,
            ),
        ),
        # AuditLog.action – extend choices to include "send_back"
        migrations.AlterField(
            model_name="auditlog",
            name="action",
            field=models.CharField(
                choices=[
                    ("create", "Created"),
                    ("update", "Updated"),
                    ("delete", "Deleted"),
                    ("submit", "Submitted"),
                    ("approve", "Approved"),
                    ("reject", "Rejected"),
                    ("send_back", "Returned for Correction"),
                    ("withdraw", "Withdrawn"),
                    ("assign", "Assigned"),
                    ("comment", "Commented"),
                ],
                max_length=20,
            ),
        ),
    ]

