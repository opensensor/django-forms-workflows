import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("django_forms_workflows", "0098_notificationlog_dispatch_scope"),
    ]

    operations = [
        migrations.AddField(
            model_name="pendingnotification",
            name="notification_rule",
            field=models.ForeignKey(
                to="django_forms_workflows.notificationrule",
                on_delete=django.db.models.deletion.SET_NULL,
                null=True,
                blank=True,
            ),
        ),
    ]
