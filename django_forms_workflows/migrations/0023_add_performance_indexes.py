from django.db import migrations


# PostgreSQL-specific SQL (CONCURRENTLY avoids table locks in production).
_PG_CREATE = [
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS django_form_status_only_idx
    ON django_forms_workflows_formsubmission USING btree (status)
    WHERE status IN (
        'approved','rejected','withdrawn',
        'submitted','pending_approval'
    )
    """,
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS django_form_history_sort_idx
    ON django_forms_workflows_formsubmission
        USING btree (status, completed_at DESC NULLS LAST, submitted_at DESC)
    WHERE status IN ('approved','rejected','withdrawn')
    """,
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS django_form_history_cat_idx
    ON django_forms_workflows_formsubmission
        USING btree (status, form_definition_id)
    WHERE status IN ('approved','rejected','withdrawn')
    """,
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS django_form_task_status_idx
    ON django_forms_workflows_approvaltask USING btree (status)
    """,
]

_PG_DROP = [
    "DROP INDEX CONCURRENTLY IF EXISTS django_form_status_only_idx",
    "DROP INDEX CONCURRENTLY IF EXISTS django_form_history_sort_idx",
    "DROP INDEX CONCURRENTLY IF EXISTS django_form_history_cat_idx",
    "DROP INDEX CONCURRENTLY IF EXISTS django_form_task_status_idx",
]

# Generic SQL for SQLite (and any other backend used in tests/dev).
# No CONCURRENTLY, no USING btree, no NULLS LAST.
_OTHER_CREATE = [
    """
    CREATE INDEX IF NOT EXISTS django_form_status_only_idx
    ON django_forms_workflows_formsubmission (status)
    WHERE status IN (
        'approved','rejected','withdrawn',
        'submitted','pending_approval'
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS django_form_history_sort_idx
    ON django_forms_workflows_formsubmission (status, completed_at, submitted_at)
    WHERE status IN ('approved','rejected','withdrawn')
    """,
    """
    CREATE INDEX IF NOT EXISTS django_form_history_cat_idx
    ON django_forms_workflows_formsubmission (status, form_definition_id)
    WHERE status IN ('approved','rejected','withdrawn')
    """,
    "CREATE INDEX IF NOT EXISTS django_form_task_status_idx ON django_forms_workflows_approvaltask (status)",
]

_OTHER_DROP = [
    "DROP INDEX IF EXISTS django_form_status_only_idx",
    "DROP INDEX IF EXISTS django_form_history_sort_idx",
    "DROP INDEX IF EXISTS django_form_history_cat_idx",
    "DROP INDEX IF EXISTS django_form_task_status_idx",
]


def create_indexes(apps, schema_editor):
    stmts = _PG_CREATE if schema_editor.connection.vendor == "postgresql" else _OTHER_CREATE
    for sql in stmts:
        schema_editor.execute(sql)


def drop_indexes(apps, schema_editor):
    stmts = _PG_DROP if schema_editor.connection.vendor == "postgresql" else _OTHER_DROP
    for sql in stmts:
        schema_editor.execute(sql)


class Migration(migrations.Migration):
    """
    Adds four performance indexes identified through EXPLAIN ANALYZE
    on the approval history and inbox views.

    On PostgreSQL indexes are created CONCURRENTLY to avoid table locks.
    On other backends (SQLite for tests/dev) plain CREATE INDEX is used.

    Indexes added:
      1. django_form_status_only_idx  — partial on status for all non-draft rows.
      2. django_form_history_sort_idx — partial composite covering the ORDER BY
         used by the approval-history view.
      3. django_form_history_cat_idx  — partial composite for the category-count
         GROUP BY aggregation on the history view.
      4. django_form_task_status_idx  — on approvaltask(status) for badge COUNTs.
    """

    # CONCURRENTLY cannot run inside a transaction; atomic=False prevents Django
    # from wrapping the whole migration in BEGIN/COMMIT on PostgreSQL.
    atomic = False

    dependencies = [
        ("django_forms_workflows", "0022_add_bulk_pdf_export"),
    ]

    operations = [
        migrations.RunPython(create_indexes, reverse_code=drop_indexes),
    ]

