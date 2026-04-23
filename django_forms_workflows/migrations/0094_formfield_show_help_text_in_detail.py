from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("django_forms_workflows", "0093_normalize_conditional_operators"),
    ]

    operations = [
        migrations.AddField(
            model_name="formfield",
            name="show_help_text_in_detail",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "If checked, the field's help text is shown next to the value "
                    "in the submission and approval detail view. Use for "
                    "attestation or consent statements attached to "
                    "initials/signature fields."
                ),
            ),
        ),
    ]
