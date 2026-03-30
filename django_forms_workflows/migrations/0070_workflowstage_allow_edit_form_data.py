from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            "django_forms_workflows",
            "0069_add_signature_field_type",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="workflowstage",
            name="allow_edit_form_data",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Allow approvers at this stage to edit the original form submission "
                    "data. When enabled, the submission fields are shown as editable "
                    "inputs instead of a read-only table. Changes are saved when the "
                    "approver approves the submission."
                ),
            ),
        ),
    ]

