from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Consolidate the approved_pending status into pending_approval.

    The approved_pending value was set on a parent FormSubmission while
    non-detached sub-workflow instances were still running.  It displayed
    identically to pending_approval in the UI and was confusing.  This
    migration:

    1. Converts all existing approved_pending rows to pending_approval.
    2. Removes approved_pending from the STATUS_CHOICES on FormSubmission
       so it can no longer be stored.
    """

    dependencies = [
        (
            "django_forms_workflows",
            "0053_stageformfieldnotification_static_emails",
        ),
    ]

    operations = [
        # Data migration: rewrite any existing approved_pending rows
        migrations.RunSQL(
            sql="""
                UPDATE django_forms_workflows_formsubmission
                SET status = 'pending_approval'
                WHERE status = 'approved_pending';
            """,
            reverse_sql="""
                -- Not reversible: we cannot know which pending_approval rows
                -- were originally approved_pending.
            """,
        ),
        # Schema migration: remove approved_pending from choices
        migrations.AlterField(
            model_name="formsubmission",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("submitted", "Submitted"),
                    ("pending_approval", "Pending Approval"),
                    ("approved", "Approved"),
                    ("rejected", "Rejected"),
                    ("withdrawn", "Withdrawn"),
                ],
                default="draft",
                max_length=20,
            ),
        ),
    ]

