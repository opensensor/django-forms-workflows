from django.contrib.postgres.indexes import GinIndex
from django.db import migrations


class Migration(migrations.Migration):
    """
    Add a GIN index on FormSubmission.form_data (jsonb).

    Benefits
    --------
    * Accelerates @> (containment) queries, e.g.
      FormSubmission.objects.filter(form_data__contains={"key": "value"})
    * Accelerates ? (key-existence) checks used by Django's JSONField has_key
      lookups and some ORM introspection paths.
    * Lays the groundwork for per-form-field icontains search: when the
      queryset is already scoped to one form_definition the filtered row
      count is small, and the GIN index further reduces the pages PostgreSQL
      must examine when extracting individual keys via ->>.
    * Zero write overhead on idle-read tables; marginal on write-heavy ones
      because GIN updates are deferred and batched by PostgreSQL.
    """

    dependencies = [
        ("django_forms_workflows", "0026_alter_formfield_width"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="formsubmission",
            index=GinIndex(
                fields=["form_data"],
                name="dfwf_formsubmission_form_data_gin",
            ),
        ),
    ]

