from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("django_forms_workflows", "0021_alter_pendingnotification_scheduled_for_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="workflowdefinition",
            name="allow_bulk_pdf_export",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Allow users to select and bulk-export submissions for this form "
                    "into a single merged PDF from the approval and submissions list views."
                ),
            ),
        ),
    ]

