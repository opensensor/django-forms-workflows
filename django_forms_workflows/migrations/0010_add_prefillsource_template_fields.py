# Generated migration for PrefillSource template fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("django_forms_workflows", "0009_add_formfield_readonly"),
    ]

    operations = [
        migrations.AddField(
            model_name="prefillsource",
            name="db_columns",
            field=models.JSONField(
                blank=True,
                null=True,
                help_text="List of columns to fetch for template (e.g., ['FIRST_NAME', 'LAST_NAME'])",
            ),
        ),
        migrations.AddField(
            model_name="prefillsource",
            name="db_template",
            field=models.CharField(
                blank=True,
                max_length=500,
                help_text="Template for combining columns (e.g., '{FIRST_NAME} {LAST_NAME}')",
            ),
        ),
        migrations.AlterField(
            model_name="prefillsource",
            name="db_column",
            field=models.CharField(
                blank=True,
                help_text="Database column name (e.g., 'FIRST_NAME') - for single column lookup",
                max_length=100,
            ),
        ),
    ]

