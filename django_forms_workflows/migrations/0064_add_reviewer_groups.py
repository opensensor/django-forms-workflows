import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("django_forms_workflows", "0063_formdefinition_api_enabled_apitoken"),
    ]

    operations = [
        migrations.AddField(
            model_name="formdefinition",
            name="reviewer_groups",
            field=models.ManyToManyField(
                blank=True,
                help_text=(
                    "Groups that can view all submissions and full approval history "
                    "for this form. Unlike admin groups, reviewers cannot manage the "
                    "form itself."
                ),
                related_name="can_review_forms",
                to="auth.group",
            ),
        ),
    ]

