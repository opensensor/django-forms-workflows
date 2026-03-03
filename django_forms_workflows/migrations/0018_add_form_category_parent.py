# Migration for hierarchical (nested) FormCategory support (v0.13.0).

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("django_forms_workflows", "0017_add_notification_batching"),
    ]

    operations = [
        migrations.AddField(
            model_name="formcategory",
            name="parent",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="children",
                to="django_forms_workflows.formcategory",
                help_text=(
                    "Optional parent category. Leave empty for a top-level category. "
                    "Allows arbitrary nesting for more granular organisation and permissioning."
                ),
            ),
        ),
    ]

