from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            "django_forms_workflows",
            "0082_add_document_template_model",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="workflowdefinition",
            name="start_trigger",
            field=models.CharField(
                choices=[
                    ("on_submission", "On Submission (default)"),
                    (
                        "on_all_complete",
                        "After All Other Workflows Complete",
                    ),
                ],
                default="on_submission",
                help_text=(
                    "When this workflow should start. "
                    '"On Submission" starts immediately when the form is submitted. '
                    '"After All Other Workflows Complete" waits until every other '
                    "on_submission workflow on this form has finished before starting."
                ),
                max_length=20,
            ),
        ),
    ]
