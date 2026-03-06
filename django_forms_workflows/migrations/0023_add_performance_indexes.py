from django.db import migrations


class Migration(migrations.Migration):
    # CREATE INDEX CONCURRENTLY cannot run inside a transaction block.
    # Setting atomic=False tells Django not to wrap this migration in BEGIN/COMMIT.
    atomic = False

    """
    Adds four performance indexes identified through EXPLAIN ANALYZE
    on the approval history and inbox views.

    All indexes use CONCURRENTLY via SeparateDatabaseAndState so they
    can run without locking the table in production.

    Indexes added:
      1. django_form_status_only_idx  — partial btree on status for all
         non-draft statuses; used by COUNT and pending-inbox queries.

      2. django_form_history_sort_idx — partial composite on
         (status, completed_at DESC, submitted_at DESC) covering the
         ORDER BY clause of the approval history view; eliminates the
         full-table quicksort that previously cost ~550 kB of memory
         per request.

      3. django_form_history_cat_idx  — partial composite on
         (status, form_definition_id) for the category-count GROUP BY
         aggregation on the history view; allows an index-only scan
         instead of a seq scan + hash join.

      4. django_form_task_status_idx  — btree on
         approvaltask(status) for the pending-tasks badge COUNT that
         fires on every inbox/history page load.
    """

    dependencies = [
        ("django_forms_workflows", "0022_add_bulk_pdf_export"),
    ]

    # SeparateDatabaseAndState lets us run CREATE INDEX CONCURRENTLY
    # (which cannot run inside a transaction) while still keeping
    # Django's migration state in sync.
    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="""
                        CREATE INDEX CONCURRENTLY IF NOT EXISTS django_form_status_only_idx
                        ON django_forms_workflows_formsubmission USING btree (status)
                        WHERE status IN (
                            'approved','rejected','withdrawn',
                            'submitted','pending_approval'
                        );
                    """,
                    reverse_sql="DROP INDEX CONCURRENTLY IF EXISTS django_form_status_only_idx;",
                    hints={"target_db": "default"},
                ),
                migrations.RunSQL(
                    sql="""
                        CREATE INDEX CONCURRENTLY IF NOT EXISTS django_form_history_sort_idx
                        ON django_forms_workflows_formsubmission
                            USING btree (status, completed_at DESC NULLS LAST, submitted_at DESC)
                        WHERE status IN ('approved','rejected','withdrawn');
                    """,
                    reverse_sql="DROP INDEX CONCURRENTLY IF EXISTS django_form_history_sort_idx;",
                    hints={"target_db": "default"},
                ),
                migrations.RunSQL(
                    sql="""
                        CREATE INDEX CONCURRENTLY IF NOT EXISTS django_form_history_cat_idx
                        ON django_forms_workflows_formsubmission
                            USING btree (status, form_definition_id)
                        WHERE status IN ('approved','rejected','withdrawn');
                    """,
                    reverse_sql="DROP INDEX CONCURRENTLY IF EXISTS django_form_history_cat_idx;",
                    hints={"target_db": "default"},
                ),
                migrations.RunSQL(
                    sql="""
                        CREATE INDEX CONCURRENTLY IF NOT EXISTS django_form_task_status_idx
                        ON django_forms_workflows_approvaltask USING btree (status);
                    """,
                    reverse_sql="DROP INDEX CONCURRENTLY IF EXISTS django_form_task_status_idx;",
                    hints={"target_db": "default"},
                ),
            ],
            # No model-state changes — these are pure DB indexes on existing fields.
            state_operations=[],
        ),
    ]

