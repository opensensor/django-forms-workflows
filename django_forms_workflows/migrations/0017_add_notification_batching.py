# Migration for notification batching feature (v0.11.0).

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("django_forms_workflows", "0016_add_pdf_generation"),
    ]

    operations = [
        # --- WorkflowDefinition batching fields ---
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
        # --- PendingNotification model ---
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
    ]

