from django.db import connection, migrations

_INDEX = "dfwf_sub_form_data_gin"
_TABLE = "django_forms_workflows_formsubmission"


def _add_gin_index(apps, schema_editor):
    """Only run on PostgreSQL – GIN is a postgres-specific index type."""
    if connection.vendor != "postgresql":
        return
    schema_editor.execute(
        f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {_INDEX} "
        f"ON {_TABLE} USING GIN (form_data);"
    )


def _drop_gin_index(apps, schema_editor):
    if connection.vendor != "postgresql":
        return
    schema_editor.execute(f"DROP INDEX IF EXISTS {_INDEX};")


class Migration(migrations.Migration):
    """
    Add a GIN index on FormSubmission.form_data (jsonb) for PostgreSQL only.

    Benefits
    --------
    * Accelerates @> (containment) and ? (key-existence) operators.
    * Reduces page scans when PostgreSQL extracts individual keys via ->>
      for icontains lookups on a form-scoped queryset.
    * CONCURRENTLY means the table is not locked during index build.
    * No-ops silently on SQLite / MySQL so the package stays db-agnostic.

    Raw SQL + RunPython is used instead of GinIndex() so that
    django.contrib.postgres does not need to be in INSTALLED_APPS.
    """

    atomic = False  # required for CREATE INDEX CONCURRENTLY

    dependencies = [
        ("django_forms_workflows", "0026_alter_formfield_width"),
    ]

    operations = [
        migrations.RunPython(_add_gin_index, reverse_code=_drop_gin_index),
    ]

