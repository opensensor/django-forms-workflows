# Migration for notification batching feature (v0.11.0).
# Uses SeparateDatabaseAndState + IF NOT EXISTS / IF EXISTS SQL so it is safe
# to run against a database where the columns/table were already added manually.

import django.db.models.deletion
from django.db import migrations, models

# ---- WorkflowDefinition: batching columns ----
ADD_BATCHING_COLUMNS_SQL = """
ALTER TABLE django_forms_workflows_workflowdefinition
    ADD COLUMN IF NOT EXISTS notification_cadence VARCHAR(20) NOT NULL DEFAULT 'immediate',
    ADD COLUMN IF NOT EXISTS notification_cadence_day INTEGER,
    ADD COLUMN IF NOT EXISTS notification_cadence_time TIME,
    ADD COLUMN IF NOT EXISTS notification_cadence_form_field VARCHAR(50) NOT NULL DEFAULT '';
"""

DROP_BATCHING_COLUMNS_SQL = """
ALTER TABLE django_forms_workflows_workflowdefinition
    DROP COLUMN IF EXISTS notification_cadence,
    DROP COLUMN IF EXISTS notification_cadence_day,
    DROP COLUMN IF EXISTS notification_cadence_time,
    DROP COLUMN IF EXISTS notification_cadence_form_field;
"""

# ---- PendingNotification table ----
CREATE_PENDING_NOTIFICATION_SQL = """
CREATE TABLE IF NOT EXISTS django_forms_workflows_pendingnotification (
    id BIGSERIAL PRIMARY KEY,
    notification_type VARCHAR(30) NOT NULL,
    recipient_email VARCHAR(254) NOT NULL,
    scheduled_for TIMESTAMP WITH TIME ZONE NOT NULL,
    sent BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    workflow_id BIGINT NOT NULL
        REFERENCES django_forms_workflows_workflowdefinition(id) ON DELETE CASCADE,
    submission_id BIGINT
        REFERENCES django_forms_workflows_formsubmission(id) ON DELETE CASCADE,
    approval_task_id BIGINT
        REFERENCES django_forms_workflows_approvaltask(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS
    idx_pendingnotif_scheduled_for
    ON django_forms_workflows_pendingnotification(scheduled_for);
CREATE INDEX IF NOT EXISTS
    idx_pendingnotif_sent
    ON django_forms_workflows_pendingnotification(sent);
"""

DROP_PENDING_NOTIFICATION_SQL = """
DROP TABLE IF EXISTS django_forms_workflows_pendingnotification;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("django_forms_workflows", "0016_add_pdf_generation"),
    ]

    operations = [
        # --- WorkflowDefinition batching fields ---
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=ADD_BATCHING_COLUMNS_SQL,
                    reverse_sql=DROP_BATCHING_COLUMNS_SQL,
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="workflowdefinition",
                    name="notification_cadence",
                    field=models.CharField(
                        choices=[
                            ("immediate", "Immediate (send right away)"),
                            ("daily", "Daily digest"),
                            ("weekly", "Weekly digest"),
                            ("monthly", "Monthly digest"),
                            ("form_field_date", "On date from a form field"),
                        ],
                        default="immediate",
                        max_length=20,
                    ),
                ),
                migrations.AddField(
                    model_name="workflowdefinition",
                    name="notification_cadence_day",
                    field=models.IntegerField(blank=True, null=True),
                ),
                migrations.AddField(
                    model_name="workflowdefinition",
                    name="notification_cadence_time",
                    field=models.TimeField(blank=True, null=True),
                ),
                migrations.AddField(
                    model_name="workflowdefinition",
                    name="notification_cadence_form_field",
                    field=models.SlugField(blank=True),
                ),
            ],
        ),
        # --- PendingNotification model ---
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=CREATE_PENDING_NOTIFICATION_SQL,
                    reverse_sql=DROP_PENDING_NOTIFICATION_SQL,
                ),
            ],
            state_operations=[
                migrations.CreateModel(
                    name="PendingNotification",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("notification_type", models.CharField(choices=[("submission_received", "Submission Received"), ("approval_request", "Approval Request")], max_length=30)),
                        ("recipient_email", models.EmailField()),
                        ("scheduled_for", models.DateTimeField(db_index=True)),
                        ("sent", models.BooleanField(db_index=True, default=False)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("workflow", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="pending_notifications", to="django_forms_workflows.workflowdefinition")),
                        ("submission", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="pending_notifications", to="django_forms_workflows.formsubmission")),
                        ("approval_task", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="pending_notifications", to="django_forms_workflows.approvaltask")),
                    ],
                    options={"verbose_name": "Pending Notification", "verbose_name_plural": "Pending Notifications", "ordering": ["scheduled_for", "notification_type"]},
                ),
            ],
        ),
    ]

