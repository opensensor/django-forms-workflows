import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("django_forms_workflows", "0051_formdefinition_is_listed"),
    ]

    operations = [
        # 1. Add assignee_email_field to WorkflowStage
        migrations.AddField(
            model_name="workflowstage",
            name="assignee_email_field",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "Form field slug whose value is an email address. When set, the workflow "
                    "engine looks up the system user with that email and assigns this stage's "
                    "task directly to them (bypassing the approval groups). Falls back to "
                    "group assignment if the field is empty or no matching user is found."
                ),
                max_length=200,
            ),
        ),
        # 2. Create StageFormFieldNotification
        migrations.CreateModel(
            name="StageFormFieldNotification",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "stage",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="form_field_notifications",
                        to="django_forms_workflows.workflowstage",
                    ),
                ),
                (
                    "notification_type",
                    models.CharField(
                        choices=[
                            ("approval_request", "Approval Request (stage activated)"),
                            ("submission_received", "Submission Received"),
                            ("approval_notification", "Submission Approved (final)"),
                            ("rejection_notification", "Submission Rejected (final)"),
                        ],
                        default="approval_request",
                        help_text="Which notification email template to send.",
                        max_length=30,
                    ),
                ),
                (
                    "email_field",
                    models.CharField(
                        help_text=(
                            "Slug of the form field whose value is the recipient email address. "
                            "The value is read from the submission's form_data at send time."
                        ),
                        max_length=200,
                    ),
                ),
                (
                    "subject_template",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text=(
                            "Custom subject line. Leave blank to use the default for the "
                            "notification type. Supports {form_name} and {submission_id} placeholders."
                        ),
                        max_length=500,
                    ),
                ),
                (
                    "conditions",
                    models.JSONField(
                        blank=True,
                        null=True,
                        help_text=(
                            "Optional conditions that must be met (against form_data) for this "
                            "notification to be sent. Same format as stage trigger_conditions. "
                            "Leave blank to always send."
                        ),
                    ),
                ),
            ],
            options={
                "verbose_name": "Stage Form-Field Notification",
                "verbose_name_plural": "Stage Form-Field Notifications",
                "ordering": ["id"],
            },
        ),
    ]

