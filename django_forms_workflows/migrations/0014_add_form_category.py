# Generated migration — adds FormCategory model and category FK on FormDefinition.
# Non-destructive: all existing FormDefinition rows keep category=NULL.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("django_forms_workflows", "0013_add_database_query_key"),
    ]

    operations = [
        migrations.CreateModel(
            name="FormCategory",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        max_length=200,
                        unique=True,
                        help_text="Human-readable category name (e.g. 'HR', 'IT Requests')",
                    ),
                ),
                (
                    "slug",
                    models.SlugField(
                        unique=True,
                        help_text="URL-safe identifier; auto-populated from name",
                    ),
                ),
                (
                    "description",
                    models.TextField(
                        blank=True,
                        help_text="Optional description shown to administrators",
                    ),
                ),
                (
                    "order",
                    models.PositiveIntegerField(
                        default=0,
                        help_text="Controls display order in the form list (lower = first)",
                    ),
                ),
                (
                    "is_collapsed_by_default",
                    models.BooleanField(
                        default=False,
                        help_text="If True, the category section renders collapsed in the UI",
                    ),
                ),
                (
                    "icon",
                    models.CharField(
                        blank=True,
                        max_length=100,
                        help_text="Bootstrap icon class (e.g. 'bi-people-fill') shown in the section header",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "allowed_groups",
                    models.ManyToManyField(
                        blank=True,
                        related_name="form_categories",
                        to="auth.group",
                        help_text=(
                            "Groups that may see/access forms in this category. "
                            "Leave empty to allow all authenticated users."
                        ),
                    ),
                ),
            ],
            options={
                "verbose_name": "Form Category",
                "verbose_name_plural": "Form Categories",
                "ordering": ["order", "name"],
            },
        ),
        migrations.AddField(
            model_name="formdefinition",
            name="category",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="forms",
                to="django_forms_workflows.formcategory",
                help_text="Grouping category for this form. Leave blank for 'General/Other'.",
            ),
        ),
    ]

