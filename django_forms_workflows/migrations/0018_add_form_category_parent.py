# Migration for hierarchical (nested) FormCategory support (v0.13.0).
# Uses SeparateDatabaseAndState + IF NOT EXISTS / IF EXISTS SQL so it is safe
# to run against a database where the column was already added manually.

import django.db.models.deletion
from django.db import migrations, models

ADD_PARENT_SQL = """
ALTER TABLE django_forms_workflows_formcategory
    ADD COLUMN IF NOT EXISTS parent_id BIGINT
        REFERENCES django_forms_workflows_formcategory(id) ON DELETE SET NULL;
"""

DROP_PARENT_SQL = """
ALTER TABLE django_forms_workflows_formcategory
    DROP COLUMN IF EXISTS parent_id;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("django_forms_workflows", "0017_add_notification_batching"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=ADD_PARENT_SQL,
                    reverse_sql=DROP_PARENT_SQL,
                ),
            ],
            state_operations=[
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
            ],
        ),
    ]

