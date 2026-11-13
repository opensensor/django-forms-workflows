import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("django_forms_workflows", "0097_notificationlog_delivery_reconciliation"),
    ]

    operations = [
        migrations.AddField(
            model_name="notificationlog",
            name="approval_task",
            field=models.ForeignKey(
                to="django_forms_workflows.approvaltask",
                on_delete=django.db.models.deletion.SET_NULL,
                null=True,
                blank=True,
            ),
        ),
        migrations.AddField(
            model_name="notificationlog",
            name="notification_rule",
            field=models.ForeignKey(
                to="django_forms_workflows.notificationrule",
                on_delete=django.db.models.deletion.SET_NULL,
                null=True,
                blank=True,
            ),
        ),
    ]
